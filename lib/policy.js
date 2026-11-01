/**
 * Risk policy for SolidWorks tool calls.
 *
 * The plugin never trusts the model to decide what is safe. Every call passes
 * through `Policy.evaluate()` before it reaches the Python MCP server, and the
 * answer is one of: allowed, refused (with an actionable code), or
 * confirmation-required (the model must obtain a one-shot grant bound to the
 * exact tool + arguments first).
 *
 * Tiers are deliberately coarse and defensible:
 *   read   — never mutates the document or the session
 *   write  — mutates the active document or session state
 *   high   — persists, exports, deletes, closes, or runs a solver (irreversible
 *            or expensive from the user's point of view)
 */

import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

export const READ = 'read';
export const WRITE = 'write';
export const HIGH = 'high';

/**
 * Explicit classification for every tool the bundled server actually offers.
 *
 * Reconciled on 2026-10-29 against a live `tools/list` of the vendored server
 * (`solidworks_mcp 1.30.0`, MCP protocol 2025-06-18, 66 tools) — see
 * `tests/probe-server.mjs`, which fails if the table and the server drift apart
 * in either direction. `design_spec_validate` and `solidworks_health_check` are
 * shipped by the server; the `cadstudio_*` family is its neutral-CAD half.
 */
export const RISK_TABLE = Object.freeze({
  // ---- read: no document, session, or disk mutation ---------------------
  solidworks_health_check: READ,
  solidworks_list_edges: READ,
  solidworks_mass_properties: READ,
  solidworks_bounding_box: READ,
  solidworks_interference_check: READ,
  solidworks_inspect_configurations: READ,
  solidworks_inspect_hole_features: READ,
  solidworks_inspect_motion_studies: READ,
  solidworks_inspect_native_geometry: READ,
  solidworks_validate_motion_study: READ,
  solidworks_addin_host_status: READ,
  design_spec_validate: READ,
  cadstudio_resolve_backend: READ,
  cadstudio_routing_preflight: READ,
  cadstudio_fea_preflight: READ,
  cadstudio_read_artifact: READ,

  // ---- write: mutates the document or session, nothing persisted yet ----
  solidworks_connect: WRITE,
  solidworks_open_document: WRITE,
  solidworks_new_document: WRITE,
  solidworks_create_basic_part: WRITE,
  solidworks_sketch_and_extrude: WRITE,
  solidworks_revolve: WRITE,
  solidworks_fillet: WRITE,
  solidworks_chamfer: WRITE,
  solidworks_shell: WRITE,
  solidworks_pattern: WRITE,
  solidworks_mirror_feature: WRITE,
  solidworks_create_hole_feature: WRITE,
  solidworks_build_round_sweeps: WRITE,
  solidworks_add_component: WRITE,
  solidworks_set_component_fixed: WRITE,
  solidworks_add_coincident_mate: WRITE,
  solidworks_add_distance_mate: WRITE,
  solidworks_add_concentric_mate: WRITE,
  solidworks_set_appearance: WRITE,
  solidworks_document_units: WRITE,
  solidworks_create_configuration: WRITE,
  solidworks_activate_configuration: WRITE,
  solidworks_update_dimension: WRITE,
  solidworks_set_custom_properties: WRITE,
  solidworks_add_rotary_motor: WRITE,
  design_spec_build: WRITE,

  // ---- high: persists, exports, deletes, closes, or runs a solver -------
  solidworks_save_document: HIGH,
  solidworks_close_documents: HIGH,
  solidworks_export_active: HIGH,
  solidworks_batch_export_files: HIGH,
  solidworks_export_assembly_bom: HIGH,
  solidworks_pack_and_go: HIGH,
  solidworks_import_step_part: HIGH,
  solidworks_replace_component_preserving_transform: HIGH,
  solidworks_exclude_reviewed_bodies: HIGH,
  solidworks_recover: HIGH,
  solidworks_review_active: HIGH,
  solidworks_generate_drawing: HIGH,
  solidworks_review_drawing: HIGH,
  solidworks_inspect_drawing: HIGH,
  cadstudio_write_open_format: HIGH,
  cadstudio_prepare_fea: HIGH,
  cadstudio_run_fea: HIGH,
  cadstudio_run_fea_convergence: HIGH,
  cadstudio_create_ocp_loft: HIGH,
  cadstudio_create_ocp_surface: HIGH,
  cadstudio_check_dfm: HIGH,
  cadstudio_check_routing: HIGH,
  cadstudio_review_advanced_geometry: HIGH,
  cadstudio_build_dxf_preview_scene: HIGH,
});

const HIGH_PATTERN = /(?:^|_)(save|export|close|delete|pack|remove|recover|write|install|uninstall)(?:_|$)/i;
const WRITE_PATTERN = /(?:^|_)(add|create|set|update|activate|combine|revolve|fillet|chamfer|shell|pattern|mirror|sketch|build|generate|open|connect|insert|apply|prepare)(?:_|$)/i;
const WINDOWS_RESERVED_NAMES = /^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$/i;

/**
 * Classify a tool name.
 * Security default (Zero-Trust): Unknown tools default to HIGH, never READ.
 */
export function classify(name) {
  const known = RISK_TABLE[name];
  if (known) return known;
  if (HIGH_PATTERN.test(name)) return HIGH;
  if (WRITE_PATTERN.test(name)) return WRITE;
  return HIGH;
}

/** Stable serialisation used for grant binding and audit digests. */
export function canonicalArgs(args) {
  if (args === null || typeof args !== 'object' || Array.isArray(args)) return JSON.stringify(args ?? null);
  const keys = Object.keys(args).sort();
  const parts = keys.map(key => `${JSON.stringify(key)}:${canonicalArgs(args[key])}`);
  return `{${parts.join(',')}}`;
}

export function digest(value) {
  return createHash('sha256').update(value).digest('hex').slice(0, 16);
}

export class Policy {
  #mode;
  #allow;
  #deny;
  #grants = new Map();
  #grantTtlMs;
  #allowedRoots;
  #now;
  #customTiers;

  constructor({
    mode = 'read-only',
    allow = [],
    deny = [],
    grantTtlMs = 300_000,
    allowedRoots = [],
    customTiers = {},
    now = Date.now,
  } = {}) {
    if (!['read-only', 'standard', 'full'].includes(mode)) {
      throw new Error(`Unknown policy mode: ${mode} (expected read-only | standard | full)`);
    }
    this.#mode = mode;
    this.#allow = new Set(allow);
    this.#deny = new Set(deny);
    this.#grantTtlMs = grantTtlMs;
    this.#allowedRoots = allowedRoots
      .filter(root => typeof root === 'string' && root.trim() !== '')
      .map(root => path.resolve(root));
    this.#customTiers = new Map(
      Object.entries(customTiers).filter(([_, tier]) => [READ, WRITE, HIGH].includes(tier))
    );
    this.#now = now;
  }

  get mode() { return this.#mode; }

  tierOf(name) {
    return this.#customTiers.get(name) || classify(name);
  }

  #isRecognized(name) {
    return this.#customTiers.has(name)
      || Boolean(RISK_TABLE[name])
      || HIGH_PATTERN.test(name)
      || WRITE_PATTERN.test(name);
  }

  /** Tools the plugin may register at all under the current mode. */
  registerable(name) {
    if (this.#deny.has(name)) return false;
    if (this.#allow.has(name)) return true;
    if (!this.#isRecognized(name)) return false;
    const tier = this.tierOf(name);
    if (this.#mode === 'read-only') return tier === READ;
    if (this.#mode === 'standard') return tier !== HIGH;
    return true;
  }

  /**
   * Decide one call. `args` is the raw tool arguments object; `sessionCwd` is
   * the DSH session working directory, used when no explicit allowedRoots are
   * configured (a write outside the session root then needs a grant).
   */
  evaluate(name, args, { sessionCwd } = {}) {
    if (this.#deny.has(name)) {
      return refusal(name, 'TOOL_DENIED', `The user denied ${name} in the dsh-solidworks configuration.`);
    }

    // Defence in depth: Tools not recognized in RISK_TABLE, verb patterns, or customTiers are refused unless explicitly allowed
    if (!this.#isRecognized(name) && !this.#allow.has(name)) {
      return refusal(name, 'TOOL_UNKNOWN', `Tool "${name}" is not recognized in the plugin risk table and is withheld by default.`);
    }

    // Side-effect gate: solidworks_health_check with start_solidworks=true spawns an external CAD process
    // and initiates a COM session, which is not permitted under passive read-only inspection.
    if (this.#mode === 'read-only' && name === 'solidworks_health_check') {
      const startSw = args?.start_solidworks === true || args?.params?.start_solidworks === true;
      if (startSw) {
        return refusal(
          name,
          'POLICY_MODE',
          'solidworks_health_check with start_solidworks=true may launch an external SolidWorks process and is not permitted in "read-only" mode. Pass start_solidworks=false or switch policy mode to standard.',
        );
      }
    }

    const tier = this.tierOf(name);
    const explicitlyAllowed = this.#allow.has(name);
    const modeAllows = this.#mode === 'full'
      || (this.#mode === 'standard' && tier !== HIGH)
      || (this.#mode === 'read-only' && tier === READ);

    if (!modeAllows && !explicitlyAllowed) {
      const hint = tier === HIGH
        ? 'Switch the plugin policy to "full", or allow this single tool in settings, to use it.'
        : 'Switch the plugin policy to "standard" to create or edit documents.';
      return refusal(name, 'POLICY_MODE', `${name} is a ${tier}-risk tool and the plugin runs in "${this.#mode}" mode. ${hint}`);
    }

    const outside = this.#outsideAllowedRoots(name, args, sessionCwd);
    if (outside) {
      return refusal(name, 'PATH_OUTSIDE_ALLOWED_ROOTS', `${name} targets ${outside}, which is outside the allowed roots for this plugin.`);
    }

    const baseDir = (typeof sessionCwd === 'string' && sessionCwd.trim() !== '')
      ? path.resolve(sessionCwd)
      : (this.#allowedRoots[0] ?? null);
    const rewrittenArgs = normalizePathArgs(args, baseDir);

    if (tier === HIGH) {
      const key = this.#grantKey(name, args);
      const grant = this.#grants.get(key);
      if (grant && grant.expires > this.#now()) {
        this.#grants.delete(key);
        return { allowed: true, risk: tier, granted: true, rewrittenArgs };
      }
      return refusal(
        name,
        'CONFIRMATION_REQUIRED',
        `${name} is high-risk (it persists, exports, closes, or solves something). Ask the user, then call solidworks_confirm with exactly these arguments: ${JSON.stringify({ tool: name, args })}`,
      );
    }

    return { allowed: true, risk: tier, granted: false, rewrittenArgs };
  }

  /** Issue a one-shot grant for an exact (tool, args) pair. */
  grant(name, args) {
    if (this.#deny.has(name)) {
      throw new Error(`Refusing to grant denied tool ${name}`);
    }
    const key = this.#grantKey(name, args);
    this.#grants.set(key, { expires: this.#now() + this.#grantTtlMs, tool: name, digest: digest(canonicalArgs(args)) });
    return { tool: name, digest: digest(canonicalArgs(args)), ttlMs: this.#grantTtlMs };
  }

  pendingGrants() { return this.#grants.size; }

  #grantKey(name, args) { return `${name}\u0000${canonicalArgs(args)}`; }

  /**
   * Evaluates path parameters against allowed roots.
   * Path resolution strictly normalizes directory traversal (..)
   * and resolves symlinks/junctions via existing ancestor walk.
   * Enforces fail-closed: if paths exist but no roots/sessionCwd configured, refuses access.
   */
  #outsideAllowedRoots(name, args, sessionCwd) {
    const paths = collectPaths(args);
    if (paths.length === 0) return null;

    const roots = this.#allowedRoots.length > 0
      ? this.#allowedRoots
      : (typeof sessionCwd === 'string' && sessionCwd.trim() !== '' ? [path.resolve(sessionCwd)] : []);

    // Fail-Closed: When paths are referenced, roots cannot be empty.
    if (roots.length === 0) {
      return paths[0];
    }

    const baseDir = (typeof sessionCwd === 'string' && sessionCwd.trim() !== '')
      ? path.resolve(sessionCwd)
      : roots[0];

    for (const candidate of paths) {
      let resolvedCandidate;
      const isAbs = path.isAbsolute(candidate) || /^[a-zA-Z]:[\\/]/.test(candidate) || candidate.startsWith('\\\\');
      if (isAbs) {
        resolvedCandidate = path.resolve(candidate);
      } else {
        if (!baseDir) {
          // Cannot securely anchor relative path without a base directory
          return candidate;
        }
        resolvedCandidate = path.resolve(baseDir, candidate);
      }

      const inside = roots.some(root => isPathInside(resolvedCandidate, root));
      if (!inside) {
        return candidate;
      }
    }
    return null;
  }
}

function refusal(tool, code, reason) {
  return { allowed: false, tool, code, reason };
}

const EXPLICIT_PATH_KEYS = /^(path|filepath|file_path|dir|directory|folder|root|destination|output_dir|output_path|input_path|spec_path|source_model|sourcemodel|expected_document_path)$/i;
const BARE_NAME_KEYS = /^(filename|drawing_filename|basename|doc_type|document_type|unit|format)$/i;

/**
 * Accurately determines if an argument string is intended as a file or directory path.
 * Protects business enums (e.g. target: "document", input: "mm") and bare filenames
 * (e.g. drawing_filename: "drawing.slddrw") from improper path normalization.
 */
export function isPathLike(key, str) {
  if (typeof str !== 'string') return false;
  const trimmed = str.trim();
  if (trimmed.length === 0) return false;

  // If key explicitly designates a bare name (not a directory path)
  if (BARE_NAME_KEYS.test(key)) {
    // Only treat as path if it attempts directory traversal or contains directory slashes
    return trimmed.includes('/') || trimmed.includes('\\') || trimmed.includes('..');
  }

  // Windows absolute (C:\... or C:/...), UNC (\\...), or Unix root (/...)
  if (/^[a-zA-Z]:[\\/]/.test(trimmed) || trimmed.startsWith('\\\\') || trimmed.startsWith('/')) {
    return true;
  }

  // Contains directory separators
  if (trimmed.includes('\\') || trimmed.includes('/')) {
    return true;
  }

  // Explicit path/directory parameter keys
  if (EXPLICIT_PATH_KEYS.test(key) || /(?:^|_)(path|dir|folder|root|destination)(?:$|_)/i.test(key)) {
    return true;
  }

  // Recognized CAD, drawing, or spec extensions
  if (/\.(sldprt|sldasm|slddrw|step|stp|iges|igs|dxf|dwg|json|pdf|stl|csv|txt)$/i.test(trimmed)) {
    if (/(file|model|drawing|spec|target)/i.test(key)) {
      return true;
    }
  }

  return false;
}

/**
 * Deep extraction of path/file parameters from arguments.
 * Examines string values, arrays, and object properties without corrupting business enums.
 */
function collectPaths(value, out = [], depth = 0, currentKey = '') {
  if (depth > 10 || value === null || value === undefined) return out;
  if (typeof value === 'string') {
    if (isPathLike(currentKey, value)) {
      out.push(value.trim());
    }
    return out;
  }
  if (Array.isArray(value)) {
    for (const item of value) collectPaths(item, out, depth + 1, currentKey);
    return out;
  }
  if (typeof value === 'object') {
    for (const [key, item] of Object.entries(value)) {
      collectPaths(item, out, depth + 1, key);
    }
  }
  return out;
}

/**
 * Rewrites relative paths in args into normalized absolute paths anchored at baseDir.
 * Preserves bare filenames and business enums without semantic corruption.
 */
export function normalizePathArgs(value, baseDir, depth = 0, currentKey = '') {
  if (!baseDir || depth > 10 || value === null || value === undefined) return value;
  if (typeof value === 'string') {
    if (!isPathLike(currentKey, value)) {
      return value;
    }
    if (BARE_NAME_KEYS.test(currentKey)) {
      // Single filenames (e.g. drawing_filename) must not be prepended with baseDir
      return value;
    }
    const trimmed = value.trim();
    const isAbs = path.isAbsolute(trimmed) || /^[a-zA-Z]:[\\/]/.test(trimmed) || trimmed.startsWith('\\\\');
    return isAbs ? path.resolve(trimmed) : path.resolve(baseDir, trimmed);
  }
  if (Array.isArray(value)) {
    return value.map(item => normalizePathArgs(item, baseDir, depth + 1, currentKey));
  }
  if (typeof value === 'object') {
    const result = {};
    for (const [key, val] of Object.entries(value)) {
      result[key] = normalizePathArgs(val, baseDir, depth + 1, key);
    }
    return result;
  }
  return value;
}

function hasReservedDeviceName(targetPath) {
  const parts = targetPath.split(/[\\/]/);
  return parts.some(part => WINDOWS_RESERVED_NAMES.test(part.trim()));
}

/**
 * Resolves physical path on disk, walking up existing ancestors to correctly expand
 * symbolic links and directory junctions even if target file/directory does not yet exist.
 * Fails closed (returns null) on permissions, loops, loopback UNC, or DOS device names.
 */
export function realpathWithAncestorWalk(target) {
  if (typeof target !== 'string' || target.trim() === '') return null;
  const trimmed = target.trim();
  if (hasReservedDeviceName(trimmed)) return null;

  // Reject remote UNC paths (\\host\share) immediately to prevent SMB NTLM hash leakage.
  // Also reject local loopback UNC (\\localhost\... or \\127.0.0.1\...) fail-closed.
  if (trimmed.startsWith('\\\\')) {
    const isLocalLongPath = /^\\\\\?\\[a-zA-Z]:[\\/]/i.test(trimmed);
    if (!isLocalLongPath) {
      return null;
    }
  }

  let cur = path.resolve(trimmed);
  const tail = [];
  let steps = 0;
  const maxSteps = 100;

  while (steps++ < maxSteps) {
    try {
      const real = fs.realpathSync.native(cur);
      let res = real;
      for (let i = tail.length - 1; i >= 0; i--) {
        res = path.join(res, tail[i]);
      }
      return res;
    } catch (e) {
      if (e && (e.code === 'ENOENT' || e.code === 'ENOTDIR')) {
        const parent = path.dirname(cur);
        if (parent === cur) return null; // Reached drive root and still not found
        tail.push(path.basename(cur));
        cur = parent;
      } else {
        // EACCES, EPERM, ELOOP (symlink cycle), or invalid path: Fail-Closed
        return null;
      }
    }
  }
  return null;
}

/**
 * Robust containment check defeating directory traversal (..), symlinks/junctions, and case sensitivity.
 */
export function isPathInside(candidatePath, rootPath) {
  try {
    const realCandidate = realpathWithAncestorWalk(candidatePath);
    const realRoot = realpathWithAncestorWalk(rootPath);
    if (!realCandidate || !realRoot) {
      return false;
    }
    const rel = path.relative(realRoot.toLowerCase(), realCandidate.toLowerCase());
    return !rel.startsWith('..') && !path.isAbsolute(rel);
  } catch {
    return false;
  }
}

/** Best-effort human-readable target for audit rows (basename only). */
export function auditTarget(args) {
  const paths = collectPaths(args);
  if (paths.length === 0) return null;
  return paths[0].replace(/\\/g, '/').split('/').pop() ?? null;
}
