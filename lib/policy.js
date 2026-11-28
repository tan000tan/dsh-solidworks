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

import { createHash, randomBytes } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

export const READ = 'read';
export const WRITE = 'write';
export const HIGH = 'high';

/**
 * Explicit classification for every tool the bundled server actually offers.
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
  solidworks_compile_feature_graph: READ,
  solidworks_identify_dimensions: READ,
  solidworks_inspect_dimension_impact: READ,
  solidworks_plan_multi_schemes: READ,
  solidworks_optimize_feature_tree: READ,
  solidworks_inspect_cad_quality: READ,

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
  solidworks_execute_feature_graph: HIGH,
  solidworks_modify_dimension_safe: HIGH,
});

const HIGH_PATTERN = /(?:^|_)(save|export|close|delete|pack|remove|recover|write|install|uninstall)(?:_|$)/i;
const WRITE_PATTERN = /(?:^|_)(add|create|set|update|activate|combine|revolve|fillet|chamfer|shell|pattern|mirror|sketch|build|generate|open|connect|insert|apply|prepare)(?:_|$)/i;
const WINDOWS_RESERVED_NAMES = /^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$/i;

export const PROTECTED_FILENAMES = Object.freeze([
  '垫圈.sldprt',
  '螺母 gb_t 6170 m10.sldprt',
  'cordis.patch.yml',
  'cordis.yml',
  'dsh-mcp-config.json',
  '.dsh-approval-secret',
  'approval-challenges.json',
  '.env',
]);

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
  if (args === null || typeof args !== 'object') return JSON.stringify(args ?? null);
  // Arrays keep their order (it is semantic), but their elements are
  // canonicalised recursively so that key order inside an element object can
  // never change the digest (BUG-0010).
  if (Array.isArray(args)) return `[${args.map(item => canonicalArgs(item)).join(',')}]`;
  const keys = Object.keys(args).sort();
  const parts = keys.map(key => `${JSON.stringify(key)}:${canonicalArgs(args[key])}`);
  return `{${parts.join(',')}}`;
}

const TIER_RANK = Object.freeze({ [READ]: 0, [WRITE]: 1, [HIGH]: 2 });
const MAX_TTL_MS = 24 * 60 * 60 * 1000; // 24h ceiling for challenge/grant TTLs
const MAX_ARG_DEPTH = 32;
const MAX_PAYLOAD_BYTES = 1024 * 1024; // 1 MiB
const MAX_AUDIT_MEMORY = 1000;

function assertTtl(name, value) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0 || value > MAX_TTL_MS) {
    throw new Error(
      `Invalid ${name}: ${JSON.stringify(value)} (expected a finite number of milliseconds in (0, ${MAX_TTL_MS}])`,
    );
  }
  return Math.floor(value);
}

export function digest(value) {
  return createHash('sha256').update(value).digest('hex').slice(0, 16);
}

function checkDepth(value, depth = 0) {
  if (depth > MAX_ARG_DEPTH) return false;
  if (value === null || typeof value !== 'object') return true;
  if (Array.isArray(value)) {
    for (const item of value) {
      if (!checkDepth(item, depth + 1)) return false;
    }
    return true;
  }
  for (const val of Object.values(value)) {
    if (!checkDepth(val, depth + 1)) return false;
  }
  return true;
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
  #challenges = new Map();
  #rejectedChallenges = new Map();
  #challengeTtlMs;
  #maxChallenges = 512;
  #auditLog = null;
  #auditTrail = [];

  approvalMode = 'balanced';
  auditState = { written: 0, failures: 0, preservedInMemory: 0, lastError: null };

  constructor({
    mode = 'read-only',
    approvalMode = 'balanced',
    allow = [],
    deny = [],
    grantTtlMs = 300_000,
    challengeTtlMs = 120_000,
    allowedRoots = [],
    customTiers = {},
    maxChallenges = 512,
    auditLog = null,
    now = Date.now,
  } = {}) {
    if (!['read-only', 'standard', 'full'].includes(mode)) {
      throw new Error(`Unknown policy mode: ${mode} (expected read-only | standard | full)`);
    }
    if (!Array.isArray(allowedRoots)) {
      throw new TypeError('allowedRoots must be an array of directory paths');
    }
    this.#mode = mode;
    this.approvalMode = ['strict', 'balanced', 'autonomous'].includes(approvalMode) ? approvalMode : 'balanced';
    this.#allow = new Set(Array.isArray(allow) ? allow.filter(x => typeof x === 'string' && x.trim() !== '') : []);
    this.#deny = new Set(Array.isArray(deny) ? deny.filter(x => typeof x === 'string' && x.trim() !== '') : []);
    // BUG-0008: validate TTLs at construction time; invalid values fail closed.
    this.#grantTtlMs = assertTtl('grantTtlMs', grantTtlMs);
    this.#challengeTtlMs = assertTtl('challengeTtlMs', challengeTtlMs);
    this.#allowedRoots = allowedRoots
      .filter(root => typeof root === 'string' && root.trim() !== '')
      .map(root => path.resolve(root));
    // BUG-0006: escalation is allowed; downgrading a known tool is refused,
    // and unknown tools may never be declared READ.
    const tiers = new Map();
    if (customTiers && typeof customTiers === 'object') {
      for (const [toolName, tier] of Object.entries(customTiers)) {
        if (toolName === '__proto__' || toolName === 'constructor' || toolName === 'prototype') continue;
        if (![READ, WRITE, HIGH].includes(tier)) continue;
        const known = RISK_TABLE[toolName];
        if (known) {
          if (TIER_RANK[tier] < TIER_RANK[known]) continue;
        } else if (tier === READ) {
          continue;
        }
        tiers.set(toolName, tier);
      }
    }
    this.#customTiers = tiers;
    const cap = Number(maxChallenges);
    this.#maxChallenges = Number.isInteger(cap) && cap > 0 ? cap : 512;
    this.#auditLog = typeof auditLog === 'string' && auditLog.trim() !== '' ? auditLog : null;
    this.#now = now;
  }

  /**
   * BUG-0022 & AUDIT-N-03: Record an audit entry both to disk (if auditLog is
   * configured) and to the in-memory ring buffer so an unwritable auditLog path
   * never silently erases the audit trail.
   */
  recordAudit(row) {
    const entry = { ts: new Date(this.#now()).toISOString(), ...row };
    this.#auditTrail.push(entry);
    if (this.#auditTrail.length > MAX_AUDIT_MEMORY) {
      this.#auditTrail.shift();
    }
    if (!this.#auditLog) return;
    try {
      fs.mkdirSync(path.dirname(this.#auditLog), { recursive: true });
      fs.appendFileSync(this.#auditLog, `${JSON.stringify(entry)}\n`, 'utf8');
      this.auditState.written += 1;
    } catch (error) {
      this.auditState.failures += 1;
      this.auditState.preservedInMemory += 1;
      this.auditState.lastError = String(error?.message ?? error);
      if (this.auditState.failures === 1) {
        // eslint-disable-next-line no-console
        console.error(`[dsh-solidworks] audit log unavailable (${this.#auditLog}): ${this.auditState.lastError}`);
      }
    }
  }

  auditTrail(limit = 100) {
    return this.#auditTrail.slice(-limit);
  }

  get mode() { return this.#mode; }
  get allowedRoots() { return [...this.#allowedRoots]; }

  tierOf(name, args = null) {
    const base = this.#customTiers.get(name) || classify(name);
    if (base === HIGH || !args || typeof args !== 'object') {
      return base;
    }
    if (name === 'solidworks_create_basic_part' || name === 'design_spec_build') {
      for (const field of ['output_path', 'save_path']) {
        const info = extractOptionalStringField(args, field);
        if (info.present) {
          if (info.conflict || !info.valid) return HIGH;
          if (typeof info.value === 'string' && info.value.trim() !== '') return HIGH;
        }
      }
    }
    if (
      name === 'solidworks_update_dimension'
      || name === 'solidworks_create_configuration'
      || name === 'solidworks_activate_configuration'
      || name === 'solidworks_set_custom_properties'
    ) {
      const saveInfo = extractStrictBoolField(args, 'save');
      if (saveInfo.present && (saveInfo.conflict || !saveInfo.valid || saveInfo.value === true)) {
        return HIGH;
      }
    }
    return base;
  }

  #isRecognized(name) {
    return this.#customTiers.has(name)
      || Boolean(RISK_TABLE[name])
      || HIGH_PATTERN.test(name)
      || WRITE_PATTERN.test(name);
  }

  /** Tools the plugin may register at all under the current mode. */
  registerable(name, args = undefined) {
    if (this.#deny.has(name)) return false;
    if (this.#allow.has(name)) return true;
    if (!this.#isRecognized(name)) return false;
    const tier = this.tierOf(name, args);
    if (this.#mode === 'read-only') return tier === READ;
    if (this.#mode === 'standard') return tier !== HIGH;
    return true;
  }

  /**
   * Decide one call. `args` is the raw tool arguments object; `sessionCwd` is
   * the DSH session working directory, used when no explicit allowedRoots are
   * configured (a write outside the session root then needs a grant).
   */
  evaluate(name, args, { sessionCwd, sessionId = null, callId = null, skipAudit = false } = {}) {
    const finalize = (result) => {
      if (!skipAudit && this.#auditLog) {
        this.recordAudit({
          event: result.allowed ? 'policy_allowed' : 'policy_refused',
          tool: name,
          code: result.code ?? null,
          risk: result.risk ?? this.tierOf(name, args),
          session: sessionId,
          challengeId: result.challenge?.challengeId ?? null,
        });
      }
      return result;
    };

    if (this.#deny.has(name)) {
      return finalize(refusal(name, 'TOOL_DENIED', `The user denied ${name} in the dsh-solidworks configuration.`));
    }

    if (!this.#isRecognized(name) && !this.#allow.has(name)) {
      return finalize(refusal(name, 'TOOL_UNKNOWN', `Tool "${name}" is not recognized in the plugin risk table and is withheld by default.`));
    }

    if (!checkDepth(args)) {
      return finalize(refusal(name, 'ARGUMENT_DEPTH_EXCEEDED', `Arguments for ${name} exceed maximum nesting depth (${MAX_ARG_DEPTH}).`));
    }

    try {
      const serialized = JSON.stringify(args ?? {});
      if (Buffer.byteLength(serialized, 'utf8') > MAX_PAYLOAD_BYTES) {
        return finalize(refusal(name, 'PAYLOAD_TOO_LARGE', `Arguments for ${name} exceed maximum payload size (${MAX_PAYLOAD_BYTES} bytes).`));
      }
    } catch {
      return finalize(refusal(name, 'INVALID_ARGUMENTS', `Arguments for ${name} cannot be serialized.`));
    }

    // Strict type & conflict validation for conditional-HIGH / side-effect parameters (AUD-SEC-001 / AUD-MCP-001)
    if (
      name === 'solidworks_update_dimension'
      || name === 'solidworks_create_configuration'
      || name === 'solidworks_activate_configuration'
      || name === 'solidworks_set_custom_properties'
    ) {
      const saveInfo = extractStrictBoolField(args, 'save');
      if (saveInfo.conflict) {
        return finalize(refusal(name, 'INVALID_ARGUMENTS', `Conflicting "save" values for ${name} between top-level arguments and params.`));
      }
      if (saveInfo.present && !saveInfo.valid) {
        return finalize(refusal(
          name,
          'INVALID_ARGUMENT_TYPE',
          `Parameter "save" for ${name} must be a strict JSON boolean (true or false), got ${describeType(saveInfo.value)}.`,
        ));
      }
    }

    if (name === 'solidworks_create_basic_part' || name === 'design_spec_build') {
      for (const field of ['output_path', 'save_path']) {
        const info = extractOptionalStringField(args, field);
        if (info.conflict) {
          return finalize(refusal(name, 'INVALID_ARGUMENTS', `Conflicting "${field}" values for ${name} between top-level arguments and params.`));
        }
        if (info.present && !info.valid) {
          return finalize(refusal(
            name,
            'INVALID_ARGUMENT_TYPE',
            `Parameter "${field}" for ${name} must be a string or null, got ${describeType(info.value)}.`,
          ));
        }
      }
    }

    // Side-effect gate: solidworks_health_check with start_solidworks=true spawns an external CAD process
    if (name === 'solidworks_health_check') {
      const startInfo = extractStrictBoolField(args, 'start_solidworks');
      if (startInfo.conflict) {
        return finalize(refusal(name, 'INVALID_ARGUMENTS', 'Conflicting "start_solidworks" values between top-level arguments and params.'));
      }
      if (startInfo.present && !startInfo.valid) {
        return finalize(refusal(
          name,
          'INVALID_ARGUMENT_TYPE',
          `Parameter "start_solidworks" for solidworks_health_check must be a strict JSON boolean (true or false), got ${describeType(startInfo.value)}.`,
        ));
      }
      if (this.#mode === 'read-only' && startInfo.value === true) {
        return finalize(refusal(
          name,
          'POLICY_MODE',
          'solidworks_health_check with start_solidworks=true may launch an external SolidWorks process and is not permitted in "read-only" mode. Pass start_solidworks=false or switch policy mode to standard.',
        ));
      }
    }

    const tier = this.tierOf(name, args);
    const explicitlyAllowed = this.#allow.has(name);
    const modeAllows = this.#mode === 'full'
      || (this.#mode === 'standard' && tier !== HIGH)
      || (this.#mode === 'read-only' && tier === READ);

    if (!modeAllows && !explicitlyAllowed) {
      const hint = tier === HIGH
        ? 'Switch the plugin policy to "full", or allow this single tool in settings, to use it.'
        : 'Switch the plugin policy to "standard" to create or edit documents.';
      return finalize(refusal(name, 'POLICY_MODE', `${name} is a ${tier}-risk tool and the plugin runs in "${this.#mode}" mode. ${hint}`));
    }

    if (tier !== READ) {
      const paths = collectPaths(args);
      for (const p of paths) {
        const base = path.basename(String(p)).toLowerCase();
        if (PROTECTED_FILENAMES.includes(base) || base.startsWith('.env')) {
          return finalize(refusal(name, 'PROTECTED_FILE_REFUSED', `Target "${base}" is a permanently protected file and cannot be modified.`));
        }
      }
    }
    const outside = this.#outsideAllowedRoots(name, args, sessionCwd);
    if (outside !== null) {
      return finalize(refusal(name, 'PATH_OUTSIDE_ALLOWED_ROOTS', `${name} targets ${outside || '<empty>'}, which is outside the allowed roots for this plugin.`));
    }

    const baseDir = (typeof sessionCwd === 'string' && sessionCwd.trim() !== '')
      ? path.resolve(sessionCwd)
      : (this.#allowedRoots[0] ?? null);
    const rewrittenArgs = normalizePathArgs(args, baseDir);

    if (tier === HIGH) {
      const key = this.#grantKey(name, args);
      const sessionKey = this.#sessionGrantKey(name, args, sessionId);
      const now = this.#now();
      // C-GRANT-01: judge each candidate grant on its own merits. The previous
      // `get(key) || get(sessionKey)` short-circuited on a *truthy* record, so an
      // expired single-use grant masked a still-valid session-scope grant and the
      // operator got an approval prompt for work they had already approved. It
      // also leaked every expired record, because only the consumed key was ever
      // deleted.
      let matched = null;
      for (const candidateKey of [key, sessionKey]) {
        const candidate = this.#grants.get(candidateKey);
        if (!candidate) continue;
        if (candidate.expires <= now) {
          this.#grants.delete(candidateKey);
          continue;
        }
        if (matched) continue;
        const sameSession = (candidate.sessionId ?? null) === (sessionId ?? null);
        const sameCall = candidate.callId === null || candidate.callId === (callId ?? null);
        if (sameSession && sameCall) matched = { entry: candidate, key: candidateKey };
      }
      if (matched) {
        if (!matched.entry.isSessionScope) {
          this.#grants.delete(matched.key);
        }
        return finalize({ allowed: true, risk: tier, granted: true, rewrittenArgs });
      }
      const ch = this.createChallenge(name, args, { sessionId, sessionCwd, callId });
      return finalize(refusal(
        name,
        'CONFIRMATION_REQUIRED',
        `${name} is high-risk (persists, exports, deletes, closes, or solves). Interactive human approval via the DSH Host approval prompt is required (Challenge ID: ${ch.challengeId}).`,
        { challenge: ch, canonicalArgs: ch.canonical, digest: ch.digest, targetFiles: ch.targetFiles, expiresAt: ch.expiresAt },
      ));
    }

    return finalize({ allowed: true, risk: tier, granted: false, rewrittenArgs });
  }

  /**
   * Create a strictly in-memory ephemeral challenge for an ungranted HIGH-risk call.
   * No secrets or challenges are persisted to disk.
   */
  createChallenge(name, args, { sessionId = null, sessionCwd = null, callId = null, scope = 'single' } = {}) {
    const now = this.#now();
    for (const [id, existing] of this.#challenges) {
      if (existing.expiresAt <= now) this.#challenges.delete(id);
    }
    while (this.#challenges.size >= this.#maxChallenges) {
      const oldest = this.#challenges.keys().next();
      if (oldest.done) break;
      this.#challenges.delete(oldest.value);
    }
    const challengeId = 'chal_' + randomBytes(16).toString('hex');
    const canonical = canonicalArgs(args);
    const d = digest(canonical);
    const targetFiles = collectPaths(args);
    const expiresAt = now + this.#challengeTtlMs;
    const challenge = {
      challengeId,
      tool: name,
      args,
      canonical,
      digest: d,
      targetFiles,
      sessionId: sessionId ?? null,
      sessionCwd: sessionCwd ?? null,
      callId: callId ?? null,
      scope,
      status: 'pending',
      createdAt: now,
      expiresAt,
    };
    this.#challenges.set(challengeId, challenge);
    return {
      challengeId,
      tool: name,
      canonical,
      digest: d,
      targetFiles,
      sessionId: sessionId ?? null,
      callId: callId ?? null,
      scope,
      expiresAt,
      riskLevel: HIGH,
      instruction: 'Human interactive approval via DSH Host UI (ctx.approval) is required. AI self-authorization and CLI bypasses are disabled.',
    };
  }

  /** Retrieve an active in-memory challenge, purging expired entries fail-closed. */
  getChallenge(challengeId) {
    if (!challengeId || typeof challengeId !== 'string') return null;
    if (this.#rejectedChallenges.has(challengeId)) return null;
    const ch = this.#challenges.get(challengeId);
    if (!ch) return null;
    if (ch.expiresAt <= this.#now()) {
      this.#challenges.delete(challengeId);
      return null;
    }
    return {
      challengeId: ch.challengeId,
      tool: ch.tool,
      args: ch.args,
      canonical: ch.canonical,
      digest: ch.digest,
      targetFiles: ch.targetFiles,
      sessionId: ch.sessionId,
      sessionCwd: ch.sessionCwd ?? null,
      callId: ch.callId ?? null,
      scope: ch.scope,
      status: ch.status ?? 'pending',
      createdAt: ch.createdAt,
      expiresAt: ch.expiresAt,
      riskLevel: HIGH,
    };
  }

  /** List all non-expired pending challenges (safe read-only metadata view). */
  listChallenges() {
    const now = this.#now();
    const out = [];
    for (const [id, ch] of this.#challenges.entries()) {
      if (ch.expiresAt <= now) {
        this.#challenges.delete(id);
        continue;
      }
      if (!this.#rejectedChallenges.has(id)) {
        out.push(this.getChallenge(id));
      }
    }
    return out;
  }

  /**
   * Explicitly mark a pending challenge as rejected/cancelled/unavailable (fail-closed).
   */
  rejectChallenge(challengeId, { reason = 'Rejected by human operator', sessionId = null, code = 'APPROVAL_REJECTED' } = {}) {
    if (!challengeId || typeof challengeId !== 'string') {
      return { ok: false, code: 'CHALLENGE_INVALID', message: 'Missing or invalid challengeId.' };
    }
    const ch = this.#challenges.get(challengeId);
    if (!ch) {
      if (this.#rejectedChallenges.has(challengeId)) {
        return { ok: true, status: 'rejected', challengeId, reason: this.#rejectedChallenges.get(challengeId).reason };
      }
      return { ok: false, code: 'CHALLENGE_NOT_FOUND', message: 'Challenge ID not found or already expired.' };
    }
    this.#challenges.delete(challengeId);
    const rejection = {
      challengeId,
      tool: ch.tool,
      digest: ch.digest,
      sessionId: ch.sessionId ?? sessionId ?? null,
      callId: ch.callId ?? null,
      code,
      reason: reason || 'Rejected by human operator',
      rejectedAt: this.#now(),
    };
    this.#rejectedChallenges.set(challengeId, rejection);
    if (this.#auditLog) {
      this.recordAudit({
        event: 'challenge_rejected',
        tool: ch.tool,
        challengeId,
        digest: ch.digest,
        code,
        reason: rejection.reason,
        session: rejection.sessionId,
      });
    }
    return { ok: true, status: 'rejected', ...rejection };
  }

  /**
   * Atomically verify and consume an in-memory challenge ONLY after the trusted DSH
   * host human-UI approval channel returns `'allowed-once'`.
   * Fail-closed on expired, rejected, mismatched tool/args/session/callId, or replay.
   */
  consumeChallengeAndGrant(
    challengeId,
    tool,
    args,
    { sessionId = null, sessionCwd = null, callId = null, channel = 'dsh-user-approval', outcome = null } = {},
  ) {
    if (outcome !== 'allowed-once') {
      return { ok: false, code: 'APPROVAL_NOT_GRANTED', message: `Host approval outcome was "${String(outcome)}".` };
    }
    if (!challengeId || typeof challengeId !== 'string') {
      return { ok: false, code: 'CHALLENGE_INVALID', message: 'Missing or invalid challengeId.' };
    }
    if (this.#rejectedChallenges.has(challengeId)) {
      const rej = this.#rejectedChallenges.get(challengeId);
      return {
        ok: false,
        code: rej.code || 'APPROVAL_REJECTED',
        message: `Challenge ${challengeId} was rejected/cancelled (${rej.reason}).`,
      };
    }
    const ch = this.#challenges.get(challengeId);
    if (!ch) {
      return { ok: false, code: 'CHALLENGE_NOT_FOUND', message: 'Challenge ID not found, expired, or already consumed.' };
    }
    if (ch.expiresAt <= this.#now()) {
      this.#challenges.delete(challengeId);
      return { ok: false, code: 'CHALLENGE_EXPIRED', message: 'Challenge has expired. A fresh approval is required.' };
    }
    if (ch.tool !== tool) {
      return { ok: false, code: 'TOOL_MISMATCH', message: `Challenge was issued for tool "${ch.tool}", but received "${tool}".` };
    }
    const d = digest(canonicalArgs(args));
    if (d !== ch.digest) {
      return { ok: false, code: 'ARGUMENTS_MUTATED', message: 'Arguments do not match the parameters approved in this challenge.' };
    }
    if ((ch.sessionId ?? null) !== (sessionId ?? null)) {
      return { ok: false, code: 'SESSION_MISMATCH', message: 'Challenge was issued in a different session context.' };
    }
    if ((ch.sessionCwd ?? null) !== (sessionCwd ?? null)) {
      return { ok: false, code: 'SESSION_CWD_MISMATCH', message: 'Session working directory changed while waiting for approval.' };
    }
    if ((ch.callId ?? null) !== (callId ?? null)) {
      return { ok: false, code: 'CALL_ID_MISMATCH', message: 'Approval callId mismatch.' };
    }

    // Consume immediately so concurrent or replayed attempts cannot reuse it.
    this.#challenges.delete(challengeId);
    const grant = this.grant(tool, args, { scope: 'single', sessionId, callId, channel });
    return { ok: true, grant, digest: d };
  }

  /** Issue a strictly bound in-memory grant for an exact (tool, args, sessionId, callId). */
  grant(name, args, { scope = 'single', sessionId = null, callId = null, channel = 'host-ui' } = {}) {
    if (this.#deny.has(name)) {
      throw new Error(`Refusing to grant denied tool ${name}`);
    }
    const isSessionScope = scope === 'session';
    const key = isSessionScope ? this.#sessionGrantKey(name, args, sessionId) : this.#grantKey(name, args);
    const d = digest(canonicalArgs(args));
    this.#grants.set(key, {
      expires: this.#now() + this.#grantTtlMs,
      tool: name,
      digest: d,
      sessionId: sessionId ?? null,
      callId: callId ?? null,
      channel,
      isSessionScope,
    });
    return { tool: name, digest: d, ttlMs: this.#grantTtlMs, scope: isSessionScope ? 'session' : 'single', channel };
  }

  pendingGrants() { return this.#grants.size; }
  pendingChallenges() { return this.#challenges.size; }

  #grantKey(name, args) { return `${name}\u0000${canonicalArgs(args)}`; }
  #sessionGrantKey(name, args, sessionId = null) { return `${name}\u0000*SESSION*\u0000${sessionId ?? ''}\u0000${canonicalArgs(args)}`; }

  /**
   * Evaluates path parameters against allowed roots.
   * Enforces fail-closed: if paths exist but no roots/sessionCwd configured, refuses access.
   */
  #outsideAllowedRoots(name, args, sessionCwd) {
    const paths = collectPaths(args);
    if (paths.length === 0) return null;

    const roots = this.#allowedRoots.length > 0
      ? this.#allowedRoots
      : (typeof sessionCwd === 'string' && sessionCwd.trim() !== '' ? [path.resolve(sessionCwd)] : []);

    if (roots.length === 0) {
      return paths[0];
    }

    const baseDir = (typeof sessionCwd === 'string' && sessionCwd.trim() !== '')
      ? path.resolve(sessionCwd)
      : roots[0];

    for (const candidate of paths) {
      if (hasForbiddenPathSyntax(candidate)) {
        return candidate || '<empty>';
      }
      let resolvedCandidate;
      const isAbs = path.isAbsolute(candidate) || /^[a-zA-Z]:[\\/]/.test(candidate) || candidate.startsWith('\\\\');
      if (isAbs) {
        resolvedCandidate = path.resolve(candidate);
      } else {
        if (!baseDir) {
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

function describeType(val) {
  if (val === null) return 'null';
  if (Array.isArray(val)) return 'array';
  return typeof val;
}

function extractStrictBoolField(args, fieldName) {
  if (!args || typeof args !== 'object') {
    return { present: false, conflict: false, valid: true, value: undefined };
  }
  const hasTop = Object.prototype.hasOwnProperty.call(args, fieldName) && args[fieldName] !== undefined;
  const hasParamsObj = args.params && typeof args.params === 'object' && !Array.isArray(args.params);
  const hasNested = Boolean(hasParamsObj && Object.prototype.hasOwnProperty.call(args.params, fieldName) && args.params[fieldName] !== undefined);
  if (!hasTop && !hasNested) {
    return { present: false, conflict: false, valid: true, value: undefined };
  }
  if (hasTop && hasNested && !Object.is(args[fieldName], args.params[fieldName])) {
    return { present: true, conflict: true, valid: false, value: undefined };
  }
  const value = hasNested ? args.params[fieldName] : args[fieldName];
  return {
    present: true,
    conflict: false,
    valid: typeof value === 'boolean',
    value,
  };
}

function extractOptionalStringField(args, fieldName) {
  if (!args || typeof args !== 'object') {
    return { present: false, conflict: false, valid: true, value: undefined };
  }
  const hasTop = Object.prototype.hasOwnProperty.call(args, fieldName) && args[fieldName] !== undefined;
  const hasParamsObj = args.params && typeof args.params === 'object' && !Array.isArray(args.params);
  const hasNested = Boolean(hasParamsObj && Object.prototype.hasOwnProperty.call(args.params, fieldName) && args.params[fieldName] !== undefined);
  if (!hasTop && !hasNested) {
    return { present: false, conflict: false, valid: true, value: undefined };
  }
  if (hasTop && hasNested && !Object.is(args[fieldName], args.params[fieldName])) {
    return { present: true, conflict: true, valid: false, value: undefined };
  }
  const value = hasNested ? args.params[fieldName] : args[fieldName];
  return {
    present: true,
    conflict: false,
    valid: value === null || typeof value === 'string',
    value,
  };
}

function refusal(tool, code, reason, extra = {}) {
  return { allowed: false, tool, code, reason, ...extra };
}

const EXPLICIT_PATH_KEYS = /^(path|filepath|file_path|dir|directory|folder|root|destination|output_dir|output_path|input_path|spec_path|source_path|step_path|replacement_path|source_model|sourcemodel|expected_document_path|brep_evidence_path|profile_paths|file_paths|pdf_path|drawing_path|document_path|template_path|assembly_path|backup_dir|log_path|scene_path|save_path|drawing_template|template_candidates|templatecandidates|target_folder|targetfolder)$/i;
const BARE_NAME_KEYS = /^(filename|drawing_filename|basename|doc_type|document_type|unit|format)$/i;

/**
 * Checks whether a path string contains forbidden syntax that must be rejected
 * identically in both JS and Python layers:
 * - NUL bytes (\0)
 * - file:// URIs
 * - Drive-relative paths without slash (e.g. C:../evil or C:a.sldprt)
 * - NTFS Alternate Data Streams (:ads, any colon after optional \\?\ and drive letter)
 * - Remote/loopback/pipe UNC paths (anything starting with \\ except \\?\<Drive>:\)
 * - Windows reserved DOS device names (CON, PRN, AUX, NUL, COM1..9, LPT1..9)
 */
export function hasForbiddenPathSyntax(raw) {
  if (typeof raw !== 'string') return true;
  const trimmed = raw.trim();
  if (trimmed === '' || trimmed.includes('\0')) return true;
  if (/^file:/i.test(trimmed)) return true;
  // BUG-0016: reject environment variable expansion & tilde home shortcuts so Python/OS cannot redirect paths after validation.
  if (/%[A-Za-z0-9_().-]+%/.test(trimmed)) return true;
  if (/\$[A-Za-z_][A-Za-z0-9_]*|\$\{[^}]+\}/.test(trimmed)) return true;
  if (/^~(?:$|[\\/]|[A-Za-z0-9_.-]+[\\/])/.test(trimmed)) return true;
  if (/^[a-zA-Z]:(?![\\/])/.test(trimmed)) return true;
  if (trimmed.startsWith('\\\\')) {
    if (!/^\\\\\?\\[a-zA-Z]:[\\/]/i.test(trimmed)) {
      return true;
    }
  }
  let rest = trimmed.replace(/^\\\\\?\\/, '');
  rest = rest.replace(/^[a-zA-Z]:[\\/]?/, '');
  if (rest.includes(':')) return true;
  if (hasReservedDeviceName(rest)) return true;
  return false;
}

export function isPathLike(key, str) {
  if (typeof str !== 'string') return false;
  const trimmed = str.trim();
  if (trimmed.length === 0) return false;

  if (BARE_NAME_KEYS.test(key)) {
    return trimmed.includes('/')
      || trimmed.includes('\\')
      || trimmed.includes('..')
      || trimmed.includes(':')
      || WINDOWS_RESERVED_NAMES.test(trimmed)
      || hasForbiddenPathSyntax(trimmed);
  }

  if (/^file:/i.test(trimmed) || /^[a-zA-Z]:/.test(trimmed) || trimmed.startsWith('\\\\') || trimmed.startsWith('/')) {
    return true;
  }

  if (trimmed.includes('\\') || trimmed.includes('/')) {
    return true;
  }

  if (
    EXPLICIT_PATH_KEYS.test(key)
    || /(?:^|_)(path|dir|folder|root|destination)(?:$|_)/i.test(key)
    || /(?:Path|Dir|Directory|Folder|Root|Model|Template|File|Candidates)$/.test(key)
  ) {
    return true;
  }

  if (/\.(sldprt|sldasm|slddrw|step|stp|iges|igs|dxf|dwg|json|pdf|stl|csv|txt)(:.*)?$/i.test(trimmed)) {
    if (/(file|model|drawing|spec|target|path|doc)/i.test(key)) {
      return true;
    }
  }

  return false;
}

function collectPaths(value, out = [], depth = 0, currentKey = '') {
  if (depth > MAX_ARG_DEPTH || value === null || value === undefined) return out;
  if (typeof value === 'string') {
    if (value.trim() === '' && currentKey && EXPLICIT_PATH_KEYS.test(currentKey)) {
      out.push('');
      return out;
    }
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

export function normalizePathArgs(value, baseDir, depth = 0, currentKey = '') {
  if (!baseDir || depth > MAX_ARG_DEPTH || value === null || value === undefined) return value;
  if (typeof value === 'string') {
    if (!isPathLike(currentKey, value)) {
      return value;
    }
    if (BARE_NAME_KEYS.test(currentKey)) {
      return value;
    }
    const trimmed = value.trim();
    if (hasForbiddenPathSyntax(trimmed)) {
      return trimmed;
    }
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

export function realpathWithAncestorWalk(target) {
  if (typeof target !== 'string' || target.trim() === '') return null;
  const trimmed = target.trim();
  if (hasForbiddenPathSyntax(trimmed)) return null;

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
        if (parent === cur) return null;
        tail.push(path.basename(cur));
        cur = parent;
      } else {
        return null;
      }
    }
  }
  return null;
}

function stripWinLongPrefix(p) {
  if (typeof p !== 'string') return p;
  if (/^\\\\\?\\[a-zA-Z]:[\\/]/.test(p)) return p.slice(4);
  return p;
}

export function isPathInside(candidatePath, rootPath) {
  try {
    const rawCandidate = realpathWithAncestorWalk(candidatePath);
    const rawRoot = realpathWithAncestorWalk(rootPath);
    if (!rawCandidate || !rawRoot) {
      return false;
    }
    const realCandidate = stripWinLongPrefix(rawCandidate);
    const realRoot = stripWinLongPrefix(rawRoot);
    const rel = path.relative(realRoot.toLowerCase(), realCandidate.toLowerCase());
    return !rel.startsWith('..') && !path.isAbsolute(rel);
  } catch {
    return false;
  }
}

export function auditTarget(args) {
  const paths = collectPaths(args);
  if (paths.length === 0) return null;
  return paths[0].replace(/\\/g, '/').split('/').pop() ?? null;
}
