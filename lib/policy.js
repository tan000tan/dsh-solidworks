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

/** Classify a tool the table does not know about (defensive: unknown ≠ safe). */
export function classify(name) {
  const known = RISK_TABLE[name];
  if (known) return known;
  if (HIGH_PATTERN.test(name)) return HIGH;
  if (WRITE_PATTERN.test(name)) return WRITE;
  return READ;
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

  constructor({ mode = 'read-only', allow = [], deny = [], grantTtlMs = 300_000, allowedRoots = [], now = Date.now } = {}) {
    if (!['read-only', 'standard', 'full'].includes(mode)) {
      throw new Error(`Unknown policy mode: ${mode} (expected read-only | standard | full)`);
    }
    this.#mode = mode;
    this.#allow = new Set(allow);
    this.#deny = new Set(deny);
    this.#grantTtlMs = grantTtlMs;
    this.#allowedRoots = allowedRoots.filter(root => typeof root === 'string' && root.trim() !== '');
    this.#now = now;
  }

  get mode() { return this.#mode; }

  tierOf(name) { return classify(name); }

  /** Tools the plugin may register at all under the current mode. */
  registerable(name) {
    if (this.#deny.has(name)) return false;
    if (this.#allow.has(name)) return true;
    const tier = classify(name);
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
    const tier = classify(name);
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

    if (tier === HIGH) {
      const key = this.#grantKey(name, args);
      const grant = this.#grants.get(key);
      if (grant && grant.expires > this.#now()) {
        this.#grants.delete(key);
        return { allowed: true, risk: tier, granted: true };
      }
      return refusal(
        name,
        'CONFIRMATION_REQUIRED',
        `${name} is high-risk (it persists, exports, closes, or solves something). Ask the user, then call solidworks_confirm with exactly these arguments: ${JSON.stringify({ tool: name, args })}`,
      );
    }

    return { allowed: true, risk: tier, granted: false };
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

  /** Only path-looking string arguments are checked; nothing else is inferred. */
  #outsideAllowedRoots(name, args, sessionCwd) {
    if (classify(name) === READ) return null;
    const roots = this.#allowedRoots.length > 0 ? this.#allowedRoots : (typeof sessionCwd === 'string' && sessionCwd ? [sessionCwd] : []);
    if (roots.length === 0) return null;
    const paths = collectPaths(args);
    for (const candidate of paths) {
      if (!isInsideAny(candidate, roots)) return candidate;
    }
    return null;
  }
}

function refusal(tool, code, reason) {
  return { allowed: false, tool, code, reason };
}

function collectPaths(value, out = [], depth = 0) {
  if (depth > 4 || value === null || value === undefined) return out;
  if (typeof value === 'string') {
    if (/^[a-zA-Z]:[\\/]/.test(value) || value.startsWith('\\\\') || value.startsWith('/')) out.push(value);
    return out;
  }
  if (Array.isArray(value)) {
    for (const item of value) collectPaths(item, out, depth + 1);
    return out;
  }
  if (typeof value === 'object') {
    for (const item of Object.values(value)) collectPaths(item, out, depth + 1);
  }
  return out;
}

function isInsideAny(candidate, roots) {
  const normalise = value => value.replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase();
  const target = normalise(candidate);
  return roots.some(root => {
    const base = normalise(root);
    return target === base || target.startsWith(`${base}/`);
  });
}

/** Best-effort human-readable target for audit rows (basename only). */
export function auditTarget(args) {
  const paths = collectPaths(args);
  if (paths.length === 0) return null;
  return paths[0].replace(/\\/g, '/').split('/').pop() ?? null;
}