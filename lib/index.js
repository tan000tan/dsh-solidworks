/**
 * dsh-solidworks — DSH host plugin that exposes SolidWorks CAD tools.
 *
 * Shape of the plugin: the DSH host loads this module (cordis plugin), it
 * discovers a Python interpreter, starts the bundled SolidWorks MCP server as a
 * child process over stdio, lists its tools, and re-publishes them as DSH tools
 * behind a risk policy. Every call is audited; nothing is auto-approved.
 *
 * Failure philosophy: a broken environment must never take the DSH host down.
 * When discovery or startup fails the plugin logs, publishes a single
 * `solidworks_status` tool that explains exactly what is missing, and returns.
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { discover } from './discover.js';
import { McpClient, McpError } from './mcp.js';
import { Policy, auditTarget, classify, digest, canonicalArgs } from './policy.js';
import { unwrapParams, wrapArgs } from './schema.js';
import { validateSchema } from './validate.js';

export const name = 'dsh-solidworks';

/**
 * Cordis services this plugin consumes.
 */
export const inject = ['tools'];

/**
 * Cordis 4 refuses `ctx.solidworks = ...` unless the plugin declares the same
 * service in `provide`; without it `apply()` throws
 * `cannot set property "solidworks" without provide` and the whole entry fails
 * to activate (BUG-0001).
 */
export const provide = ['solidworks'];

/**
 * D-12: Declare native Schemastery Config when running inside DSH so GUI/schema
 * inspection recognizes plugin settings, while gracefully degrading to undefined
 * in standalone offline environments without @deepseek-ai/schemastery.
 */
let _schemasteryConfig;
try {
  const { default: z } = await import('@deepseek-ai/schemastery');
  if (z && typeof z.object === 'function') {
    _schemasteryConfig = z.object({
      mode: z.union(['read-only', 'standard', 'full']).default('read-only').description('Policy ceiling mode (read-only | standard | full)'),
      allow: z.array(z.string()).default([]).description('Explicitly allowed tool names'),
      deny: z.array(z.string()).default([]).description('Explicitly denied tool names'),
      allowedRoots: z.array(z.string()).default([]).description('Allowed workspace root directories for CAD file access'),
      toolTimeoutMs: z.number().default(300_000).description('Per-tool execution timeout (ms)'),
      startTimeoutMs: z.number().default(60_000).description('MCP subprocess startup timeout (ms)'),
      grantTtlMs: z.number().default(300_000).description('Human approval grant TTL (ms)'),
      challengeTtlMs: z.number().default(120_000).description('Human approval challenge TTL (ms)'),
      maxChallenges: z.number().default(512).description('Maximum in-memory pending approval challenges'),
      pythonPath: z.string().description('Optional explicit Python interpreter path'),
      serverScript: z.string().description('Optional custom SolidWorks MCP server.py path'),
      serverCwd: z.string().description('Optional custom server working directory'),
      toolPrefix: z.string().default('').description('Optional tool name prefix'),
      auditLog: z.string().description('Optional JSONL audit log file path'),
    });
  }
} catch {
  // Standalone Node execution without DSH @deepseek-ai/schemastery installed.
}
export const Config = _schemasteryConfig;

const PLUGIN_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
let pluginVersion = '0.3.1';
try {
  const pkg = JSON.parse(readFileSync(path.join(PLUGIN_ROOT, 'package.json'), 'utf8'));
  if (pkg?.version) pluginVersion = pkg.version;
} catch {
  // fallback to release baseline
}
export const version = pluginVersion;
const PLUGIN_VERSION = pluginVersion;

export const DEFAULTS = Object.freeze({
  mode: 'read-only',
  allow: [],
  deny: [],
  allowedRoots: [],
  grantTtlMs: 300_000,
  challengeTtlMs: 120_000,
  toolTimeoutMs: 300_000,
  startTimeoutMs: 60_000,
  auditLog: null,
  maxChallenges: 512,
  pythonPath: null,
  serverScript: null,
  serverCwd: null,
  toolPrefix: '',
  customTiers: {},
});

function clampTimeout(value, defaultMs, minMs = 1_000, maxMs = 600_000) {
  const num = Number(value);
  if (!Number.isFinite(num)) return defaultMs;
  return Math.max(minMs, Math.min(maxMs, Math.floor(num)));
}

function normaliseConfig(raw) {
  const config = { ...DEFAULTS, ...(raw ?? {}) };
  config.allow = asStringArray(config.allow);
  config.deny = asStringArray(config.deny);
  config.allowedRoots = asStringArray(config.allowedRoots);
  config.customTiers = (raw?.customTiers && typeof raw.customTiers === 'object') ? raw.customTiers : {};
  if (!['read-only', 'standard', 'full'].includes(config.mode)) config.mode = DEFAULTS.mode;
  config.toolTimeoutMs = clampTimeout(config.toolTimeoutMs, DEFAULTS.toolTimeoutMs, 1_000, 600_000);
  config.startTimeoutMs = clampTimeout(config.startTimeoutMs, DEFAULTS.startTimeoutMs, 1_000, 300_000);
  const cap = Number(config.maxChallenges);
  config.maxChallenges = Number.isInteger(cap) && cap > 0 && cap <= 10_000 ? cap : DEFAULTS.maxChallenges;
  return config;
}

function asStringArray(value) {
  if (Array.isArray(value)) return value.filter(item => typeof item === 'string' && item.trim() !== '').map(item => item.trim());
  if (typeof value === 'string' && value.trim() !== '') return value.split(',').map(item => item.trim()).filter(Boolean);
  return [];
}

export const auditState = { written: 0, failures: 0, preservedInMemory: 0, lastError: null };

function syncAuditState(policy) {
  auditState.written = policy.auditState.written;
  auditState.failures = policy.auditState.failures;
  auditState.preservedInMemory = policy.auditState.preservedInMemory;
  auditState.lastError = policy.auditState.lastError;
}

function audit(policy, row) {
  policy.recordAudit(row);
  syncAuditState(policy);
}

const OUTPUT = Object.freeze({
  schema: {
    type: 'object',
    additionalProperties: false,
    properties: { text: { type: 'string' } },
    required: ['text'],
  },
  render: (_args, value) => [{ type: 'text', text: String(value?.text ?? '') }],
});

/**
 * Business-level outcome for auditing.
 *
 * MCP's `isError` only reflects transport failures / uncaught exceptions. Business
 * failures (permission refused, partial success, saved=false) are returned as normal
 * text with `payload.status`. Auditing on `isError` alone therefore records every
 * business failure as success (BUG-009).
 */
export function businessOutcome(result) {
  if (result?.isError) return false;
  const texts = (result?.content ?? [])
    .filter(part => part?.type === 'text' && typeof part.text === 'string')
    .map(part => part.text);
  const text = texts.join('\n').trim();
  if (text === '') return true;
  try {
    const payload = JSON.parse(text);
    if (payload && typeof payload.status === 'string') {
      const status = payload.status.toLowerCase();
      return status === 'ok' || status === 'success' || status === 'completed';
    }
    if (payload && typeof payload.success === 'boolean') return payload.success;
  } catch {
    // Non-JSON payload (Markdown rendering): keep the transport-level verdict.
  }
  return true;
}

function out(payload) {
  return { text: typeof payload === 'string' ? payload : JSON.stringify(payload) };
}

export async function apply(ctx, rawConfig) {
  const config = normaliseConfig(rawConfig);
  const policy = new Policy({
    mode: config.mode,
    allow: config.allow,
    deny: config.deny,
    grantTtlMs: config.grantTtlMs,
    challengeTtlMs: config.challengeTtlMs,
    allowedRoots: config.allowedRoots,
    customTiers: config.customTiers,
    auditLog: config.auditLog,
    maxChallenges: config.maxChallenges,
    now: config.now ?? Date.now,
  });

  let client = null;
  let ready = null;
  let discoveredEnv = null;
  let activeRootsSignature = null;
  let syncLock = Promise.resolve();
  /** Calls currently on the wire against `client` (C-LIFE-02). */
  let inflightCalls = 0;
  let environmentReport = { state: 'pending' };
  let startupError = null;
  let toolCount = 0;
  const inFlightCallIds = new Set();
  const registered = [];
  const disposers = [];
  const toolWrapping = new Map();
  const toolParams = new Map();

  function resolveApprovalService() {
    try {
      const svc = typeof ctx?.get === 'function' ? ctx.get('approval') : ctx?.approval;
      return svc && typeof svc.request === 'function' ? svc : null;
    } catch {
      return null;
    }
  }

  function statusReport() {
    syncAuditState(policy);
    const hasApprovalSvc = Boolean(resolveApprovalService());
    return {
      plugin: { name, version: PLUGIN_VERSION, root: PLUGIN_ROOT },
      policy: {
        mode: policy.mode,
        registeredTools: registered.length,
        pendingGrants: policy.pendingGrants(),
        pendingChallenges: policy.pendingChallenges(),
        approvalChannel: hasApprovalSvc ? 'dsh-user-approval (interactive UI)' : 'unavailable (fail-closed)',
      },
      audit: {
        configured: Boolean(config.auditLog),
        written: auditState.written,
        failures: auditState.failures,
        preservedInMemory: auditState.preservedInMemory,
        lastError: auditState.lastError,
      },
      environment: environmentReport,
      connection: client?.running
        ? { running: true, tools: toolCount }
        : { running: false, error: startupError?.message ?? null, stderr: client?.stderrTail(10) ?? [] },
    };
  }

  const publish = async definition => {
    try {
      const dispose = await Promise.resolve(ctx?.tools?.register?.(definition));
      registered.push(definition.name);
      if (typeof dispose === 'function') disposers.push(dispose);
      return dispose;
    } catch (regErr) {
      const err = regErr instanceof Error ? regErr : new Error(String(regErr));
      err.code = err.code ?? 'TOOL_REGISTRATION_FAILED';
      err._fatalRegistration = true;
      throw err;
    }
  };

  const prefix = config.toolPrefix || '';
  const publicName = raw => `${prefix}${raw}`;

  const cleanup = async () => {
    for (const dispose of disposers.splice(0)) {
      try { dispose(); } catch { /* ignore */ }
    }
    registered.length = 0;
    toolWrapping.clear();
    toolParams.clear();
    inFlightCallIds.clear();
    const activeClient = client;
    client = null;
    await activeClient?.close?.();
  };

  // BUG-001: 先确保 `solidworks` 服务在宿主正确声明且无类型/跨Fiber冲突，再注册工具
  const serviceValue = Object.freeze({
    getPendingChallenge: (challengeId) => policy.getChallenge(challengeId),
    listPendingChallenges: () => policy.listChallenges(),
    status: () => statusReport(),
  });
  if (ctx && typeof ctx === 'object') {
    if (typeof ctx.provide === 'function') {
      const propDef = ctx.reflect?.props?.solidworks;
      if (propDef && propDef.type !== 'service') {
        throw new Error(`property "solidworks" is already declared as ${propDef.type}`);
      }
      const existing = typeof ctx.get === 'function'
        ? ctx.get('solidworks')
        : ctx.reflect?.get?.('solidworks');
      if (existing === undefined) {
        ctx.provide('solidworks', serviceValue);
      }
    } else if (ctx.solidworks === undefined) {
      ctx.solidworks = serviceValue;
    }
  }

  try {
  // ---- meta tools: always available, even when the server is down ---------
  await publish({
    name: publicName('solidworks_status'),
    description: '查看 SolidWorks 插件当前健康状态与连接诊断（包含运行环境、CAD 服务连接状态、安全策略模式与最后一次错误）。当 CAD 建模遇到问题时首选调用本工具排查。\n\n[risk: read]',
    parameters: { type: 'object', properties: {}, additionalProperties: false },
    output: OUTPUT,
    execute: async () => out(statusReport()),
  });

  await publish({
    name: publicName('solidworks_confirm'),
    description: '高危审批状态说明接口（已禁用 AI 自确认）。在 DSH 宿主中调用高危工具时，将直接触发宿主交互式人类审批弹窗 (ctx.approval)；AI 不可通过此工具自我签发或核销授权。\n\n[risk: read]',
    parameters: {
      type: 'object',
      properties: {
        challengeId: { type: 'string', description: '审批挑战标识符（仅用于诊断提示）。' },
        ticket: { type: 'string', description: '已废弃：不再接受命令行或磁盘自签凭证。' },
        tool: { type: 'string', description: '申请审批的工具名称。' },
        args: { type: 'object', description: '参数对象。', additionalProperties: true },
        reason: { type: 'string', description: '操作说明。' },
      },
      required: [],
      additionalProperties: false,
    },
    output: OUTPUT,
    execute: async (args = {}, exec) => {
      const tool = String(args?.tool ?? '').trim() || 'solidworks_confirm';
      const challengeId = String(args?.challengeId ?? '');
      const sessId = resolveSessionId(exec);
      audit(policy, {
        event: 'confirm_rejected',
        tool,
        challengeId: challengeId || null,
        code: 'SELF_APPROVAL_PROHIBITED',
        digest: digest(canonicalArgs(args)),
        message: 'AI self-confirmation via solidworks_confirm is disabled; human approval must come from DSH Host UI (ctx.approval).',
        session: sessId,
      });
      return out({
        status: 'refused',
        code: 'SELF_APPROVAL_PROHIBITED',
        tool: tool || null,
        challengeId: challengeId || null,
        message: '安全防护阻断：已禁用 solidworks_confirm 自确认与磁盘/CLI 伪审批流程。高危操作必须在受信任的 DSH 宿主人类审批界面 (ctx.approval) 逐次由人类点击允许。',
      });
    },
  });

  function resolveSession(exec) {
    return exec?.agent?.session ?? exec?.session ?? null;
  }

  function resolveSessionId(exec) {
    try {
      const sess = resolveSession(exec);
      return sess?.header?.id ?? ctx?.agent?.session?.header?.id ?? null;
    } catch {
      return null;
    }
  }

  async function resolveSessionCwd(exec) {
    const sess = resolveSession(exec);
    try {
      const wdService = typeof ctx?.get === 'function' ? ctx.get('workingDirectory') : ctx?.workingDirectory;
      if (sess && typeof wdService?.get === 'function') {
        const dir = await Promise.resolve(wdService.get(sess));
        if (typeof dir === 'string' && dir.trim() !== '') {
          return path.resolve(dir.trim());
        }
      }
    } catch {
      // ignore and fall back to session header cwd
    }
    try {
      const rawCwd = sess?.header?.cwd ?? ctx?.agent?.session?.header?.cwd ?? null;
      return (typeof rawCwd === 'string' && rawCwd.trim() !== '') ? path.resolve(rawCwd.trim()) : null;
    } catch {
      return null;
    }
  }

  function sessionCwd() {
    try {
      const rawCwd = ctx?.agent?.session?.header?.cwd ?? null;
      return (typeof rawCwd === 'string' && rawCwd.trim() !== '') ? path.resolve(rawCwd.trim()) : null;
    } catch {
      return null;
    }
  }

  async function startClientWithRoots(found, effectiveRoots, defaultCwd) {
    const nextClient = new McpClient({
      command: found.python.command,
      args: [...found.python.args, found.serverScript],
      cwd: found.serverCwd,
      env: {
        PYTHONUTF8: '1',
        PYTHONDONTWRITEBYTECODE: '1',
        // 同步策略模式与禁止在只读模式下启动 SolidWorks 的标志给 Python 服务（BUG-004）。
        DSH_POLICY_MODE: config.mode,
        DSH_ALLOW_LAUNCH_SW: config.mode === 'read-only' ? '0' : '1',
        PYTHONIOENCODING: 'utf-8',
        // BUG-0016: Synchronize effective allowed roots and session CWD with Python.
        // Never fall back silently to host process.cwd() when unknown: use [] -> fail-closed.
        DSH_ALLOWED_ROOTS: JSON.stringify(effectiveRoots),
        DSH_DEFAULT_CWD: defaultCwd || '',
      },
      logger: ctx?.logger,
    });
    await nextClient.initialize({ clientName: name, clientVersion: PLUGIN_VERSION, timeoutMs: config.startTimeoutMs });
    return nextClient;
  }

  async function ensureClientSynced(sessCwd, { excludeSelf = false } = {}) {
    if (!discoveredEnv || !discoveredEnv.ok) return;
    const effectiveRoots = config.allowedRoots.length > 0
      ? config.allowedRoots
      : (sessCwd ? [sessCwd] : []);
    const defaultCwd = sessCwd || config.allowedRoots[0] || '';
    const nextSignature = JSON.stringify({ roots: effectiveRoots, cwd: defaultCwd });
    if (client?.running && nextSignature === activeRootsSignature) return;

    // C-LIFE-02: the MCP client is shared by every DSH session in this host, so a
    // sync triggered by session B must never tear down a call that session A has
    // in flight — that used to surface as "MCP client closed" in the middle of a
    // CAD operation, with unknown side effects on the document. Defer the swap
    // instead: every path in `rewrittenArgs` is already absolute, so serving this
    // call on the current server is correct, and the next idle call re-syncs.
    const busy = Math.max(0, inflightCalls - (excludeSelf ? 1 : 0));
    if (busy > 0) {
      ctx?.logger?.debug?.('dsh-solidworks: deferring server re-sync, a call is in flight on the current client');
      return;
    }

    const prevLock = syncLock;
    let release;
    syncLock = new Promise(resolve => { release = resolve; });
    await prevLock;
    try {
      if (client?.running && nextSignature === activeRootsSignature) return;
      if (Math.max(0, inflightCalls - (excludeSelf ? 1 : 0)) > 0) return;
      const oldClient = client;
      const nextClient = await startClientWithRoots(discoveredEnv, effectiveRoots, defaultCwd);
      client = nextClient;
      activeRootsSignature = nextSignature;
      if (oldClient && oldClient !== nextClient) {
        try { await oldClient.close(); } catch { /* ignore */ }
      }
    } finally {
      release();
    }
  }

  // ---- discovery + server startup ----------------------------------------
  ready = (async () => {
    const found = await discover({ pluginRoot: PLUGIN_ROOT, config, env: process.env, logger: ctx?.logger });
    if (!found.ok) {
      environmentReport = { state: 'error', code: found.code, message: found.message, notes: found.notes };
      startupError = new Error(found.message);
      ctx?.logger?.warn?.(`dsh-solidworks: ${found.message}`);
      return;
    }
    discoveredEnv = found;
    const comDegraded = found.python?.comDeps === false;
    environmentReport = {
      state: 'ok',
      ...(comDegraded ? {
        degraded: true,
        degradedReason: 'Missing optional COM dependency (comtypes); basic pywin32 COM works, Motion typelib tools may degrade.',
      } : {}),
      python: found.python,
      serverScript: found.serverScript,
      serverCwd: found.serverCwd,
      notes: found.notes,
    };

    const bootCwd = sessionCwd();
    const effectiveRoots = config.allowedRoots.length > 0
      ? config.allowedRoots
      : (bootCwd ? [bootCwd] : []);
    const defaultCwd = bootCwd || config.allowedRoots[0] || '';
    activeRootsSignature = JSON.stringify({ roots: effectiveRoots, cwd: defaultCwd });

    try {
      client = await startClientWithRoots(found, effectiveRoots, defaultCwd);
      const tools = await client.listTools({ timeoutMs: config.startTimeoutMs });
      toolCount = tools.length;
      let serverPublished = 0;
      for (const tool of tools) {
        if (!tool?.name) continue;
        if (!policy.registerable(tool.name)) continue;
        const shape = unwrapParams(tool.inputSchema);
        toolWrapping.set(tool.name, shape.wrapped);
        toolParams.set(tool.name, shape.schema);
        await publish({
          name: publicName(tool.name),
          description: describe(tool, policy),
          parameters: normaliseSchema(shape.schema),
          output: OUTPUT,
          timeoutMs: config.toolTimeoutMs,
          execute: makeExecutor(tool.name),
        });
        serverPublished += 1;
      }
      const withheld = tools.length - serverPublished;
      ctx?.logger?.info?.(`dsh-solidworks: ${toolCount} tools from server, ${serverPublished} published under "${policy.mode}" policy${withheld > 0 ? ` (${withheld} withheld)` : ''}`);
    } catch (error) {
      startupError = error;
      environmentReport = { ...environmentReport, state: 'error', code: error.code ?? 'STARTUP_FAILED', message: error.message };
      if (error?._fatalRegistration) {
        ctx?.logger?.error?.(`dsh-solidworks: tool registration failed: ${error.message}`);
        await cleanup();
        throw error;
      }
      ctx?.logger?.warn?.(`dsh-solidworks: server startup failed: ${error.message}`);
      const activeClient = client;
      client = null;
      await activeClient?.close?.();
    }
  })();

  // ---- call path ---------------------------------------------------------
  function makeExecutor(rawName) {
    return async (args = {}, exec) => {
      const signal = exec?.signal;
      const started = Date.now();
      const sess = resolveSession(exec);
      const sessCwd = await resolveSessionCwd(exec);
      const sessId = resolveSessionId(exec);
      const callId = exec?.callId ?? null;
      const argDigest = digest(canonicalArgs(args));

      // BUG-003 / BUG-0023: 在进入策略、路径或 COM 前严格校验 Schema（未知键、必填、类型、范围、嵌套对象）。
      const paramSchema = toolParams.get(rawName);
      const validation = validateSchema(paramSchema, args);
      if (!validation.ok) {
        audit(policy, {
          event: 'refused', tool: rawName, code: validation.code,
          digest: argDigest, session: sessId, challengeId: null,
        });
        return out({
          status: 'refused',
          tool: rawName,
          code: validation.code,
          message: `Invalid parameter(s) for ${rawName} (${validation.message}). The call was not forwarded to the CAD server.`,
        });
      }

      let decision = policy.evaluate(rawName, args, { sessionCwd: sessCwd, sessionId: sessId, callId, skipAudit: true });
      let approvedChallengeId = null;

      if (!decision.allowed && decision.code === 'CONFIRMATION_REQUIRED') {
        const approvalSvc = resolveApprovalService();
        const ch = decision.challenge;
        approvedChallengeId = ch?.challengeId ?? null;

        if (!approvalSvc) {
          if (approvedChallengeId) {
            policy.rejectChallenge(approvedChallengeId, {
              code: 'APPROVAL_CHANNEL_UNAVAILABLE',
              reason: 'No trusted interactive DSH host approval channel (ctx.approval)',
              sessionId: sessId,
            });
          }
          audit(policy, {
            event: 'refused', tool: rawName, code: 'APPROVAL_CHANNEL_UNAVAILABLE',
            digest: argDigest, session: sessId, challengeId: approvedChallengeId,
          });
          return out({
            status: 'refused',
            tool: rawName,
            code: 'APPROVAL_CHANNEL_UNAVAILABLE',
            challengeId: approvedChallengeId,
            message: `${rawName} is high-risk and requires interactive human UI approval (ctx.approval), which is unavailable in this execution environment. Failing closed.`,
          });
        }

        const flightKey = callId ? `${sessId ?? ''}\u0000${callId}` : null;
        if (flightKey && inFlightCallIds.has(flightKey)) {
          audit(policy, {
            event: 'refused', tool: rawName, code: 'APPROVAL_REPLAY',
            digest: argDigest, session: sessId, challengeId: approvedChallengeId,
          });
          return out({
            status: 'refused',
            tool: rawName,
            code: 'APPROVAL_REPLAY',
            message: `Concurrent or replayed approval request detected for callId "${callId}". Failing closed.`,
          });
        }
        if (flightKey) inFlightCallIds.add(flightKey);

        const targetLabel = auditTarget(args) || rawName;
        const ttlAbort = new AbortController();
        const ttlTimer = setTimeout(() => ttlAbort.abort(new Error('CHALLENGE_EXPIRED')), config.challengeTtlMs);
        ttlTimer.unref?.();
        const combinedSignal = signal
          ? AbortSignal.any([signal, ttlAbort.signal])
          : ttlAbort.signal;

        let outcome = 'unavailable';
        try {
          audit(policy, {
            event: 'approval_requested',
            tool: rawName,
            challengeId: approvedChallengeId,
            channel: 'dsh-user-approval',
            target: targetLabel,
            digest: argDigest,
            session: sessId,
            callId,
          });
          outcome = await approvalSvc.request({
            agent: exec?.agent ?? (sess ? { session: sess } : undefined),
            toolName: publicName(rawName),
            callId: callId ?? approvedChallengeId,
            reason: `Allow high-risk CAD operation ${rawName} on ${targetLabel} (digest ${argDigest})`,
            displayReason: {
              en: `Allow high-risk SolidWorks operation "${rawName}" (target: ${targetLabel}, digest: ${argDigest})?`,
              zh: `是否允许执行高危 SolidWorks 操作 "${rawName}"（目标: ${targetLabel}，参数摘要: ${argDigest}）？`,
            },
            signal: combinedSignal,
          });
        } catch {
          outcome = ttlAbort.signal.aborted ? 'expired' : (signal?.aborted ? 'cancelled' : 'unavailable');
        } finally {
          clearTimeout(ttlTimer);
          if (flightKey) inFlightCallIds.delete(flightKey);
        }

        if (ttlAbort.signal.aborted && outcome !== 'allowed-once') {
          policy.rejectChallenge(approvedChallengeId, { code: 'CHALLENGE_EXPIRED', reason: 'Approval timed out', sessionId: sessId });
          audit(policy, {
            event: 'refused', tool: rawName, code: 'CHALLENGE_EXPIRED',
            digest: argDigest, session: sessId, challengeId: approvedChallengeId,
          });
          return out({
            status: 'refused',
            tool: rawName,
            code: 'CHALLENGE_EXPIRED',
            challengeId: approvedChallengeId,
            message: `Approval request for ${rawName} expired before confirmation.`,
          });
        }

        if (outcome !== 'allowed-once') {
          const code = outcome === 'rejected'
            ? 'APPROVAL_REJECTED'
            : (outcome === 'cancelled' ? 'APPROVAL_CANCELLED' : 'APPROVAL_CHANNEL_UNAVAILABLE');
          policy.rejectChallenge(approvedChallengeId, {
            code,
            reason: `Host approval returned "${String(outcome)}"`,
            sessionId: sessId,
          });
          audit(policy, {
            event: 'refused', tool: rawName, code,
            channel: 'dsh-user-approval', outcome: String(outcome),
            digest: argDigest, session: sessId, challengeId: approvedChallengeId,
          });
          return out({
            status: 'refused',
            tool: rawName,
            code,
            challengeId: approvedChallengeId,
            message: `${rawName} was not approved by the human operator (host outcome: ${String(outcome)}).`,
          });
        }

        const currentCwd = await resolveSessionCwd(exec);
        const consumed = policy.consumeChallengeAndGrant(approvedChallengeId, rawName, args, {
          sessionId: resolveSessionId(exec),
          sessionCwd: currentCwd,
          callId,
          channel: 'dsh-user-approval',
          outcome,
        });
        if (!consumed.ok) {
          audit(policy, {
            event: 'refused', tool: rawName, code: consumed.code,
            digest: argDigest, session: sessId, challengeId: approvedChallengeId,
          });
          return out({
            status: 'refused',
            tool: rawName,
            code: consumed.code,
            challengeId: approvedChallengeId,
            message: consumed.message,
          });
        }

        audit(policy, {
          event: 'confirm_granted',
          tool: rawName,
          challengeId: approvedChallengeId,
          channel: 'dsh-user-approval',
          outcome: 'allowed-once',
          digest: consumed.digest,
          scope: consumed.grant.scope,
          session: sessId,
          callId,
        });

        decision = policy.evaluate(rawName, args, { sessionCwd: currentCwd, sessionId: sessId, callId, skipAudit: true });
      }

      if (!decision.allowed) {
        audit(policy, {
          event: 'refused', tool: rawName, code: decision.code,
          digest: argDigest, session: sessId,
          challengeId: decision.challenge?.challengeId ?? approvedChallengeId ?? null,
        });
        return out({
          status: 'refused',
          tool: rawName,
          code: decision.code,
          message: decision.reason,
        });
      }

      // C-EXEC-01: startup, the cross-session re-sync and the wire call share a
      // single error boundary. Before this, a spawn/initialize failure threw out
      // of execute() as a raw McpError and the host saw an unhandled tool
      // exception instead of a structured "unavailable" envelope - the exact
      // failure mode this module promises never to produce.
      inflightCalls += 1;
      try {
        try {
          await ready;
          if (!client && startupError) {
            if (decision.granted) {
              audit(policy, {
                event: 'execution_failed_after_approval',
                tool: rawName,
                risk: decision.risk,
                code: startupError?.code ?? 'SERVER_UNAVAILABLE',
                digest: argDigest,
                session: sessId,
              });
            }
            return out({
              status: 'unavailable',
              tool: rawName,
              code: startupError?.code ?? 'SERVER_UNAVAILABLE',
              message: startupError?.message ?? 'The SolidWorks MCP server is not running. Call solidworks_status for the diagnosis.',
              stderr: client?.stderrTail(10) ?? [],
            });
          }
          await ensureClientSynced(sessCwd, { excludeSelf: true });
          if (!client?.running) {
            if (decision.granted) {
              audit(policy, {
                event: 'execution_failed_after_approval',
                tool: rawName,
                risk: decision.risk,
                code: startupError?.code ?? 'SERVER_UNAVAILABLE',
                digest: argDigest,
                session: sessId,
              });
            }
            return out({
              status: 'unavailable',
              tool: rawName,
              code: startupError?.code ?? 'SERVER_UNAVAILABLE',
              message: startupError?.message ?? 'The SolidWorks MCP server is not running. Call solidworks_status for the diagnosis.',
              stderr: client?.stderrTail(10) ?? [],
            });
          }
        } catch (error) {
          if (error?._fatalRegistration) throw error;
          const code = error instanceof McpError ? error.code : (error?.code ?? 'CLIENT_SYNC_FAILED');
          if (decision.granted) {
            audit(policy, {
              event: 'execution_failed_after_approval',
              tool: rawName,
              risk: decision.risk,
              code,
              digest: argDigest,
              session: sessId,
            });
          }
          return out({
            status: 'unavailable',
            tool: rawName,
            code,
            message: `The SolidWorks MCP server could not be (re)started for this call: ${error?.message ?? String(error)}`,
            stderr: client?.stderrTail(10) ?? [],
          });
        }

        try {
          const effectiveArgs = decision.rewrittenArgs ?? args;
          const wireArgs = wrapArgs(toolWrapping.get(rawName) ?? false, effectiveArgs);
          const result = await client.callTool(rawName, wireArgs, { timeoutMs: config.toolTimeoutMs, signal });
          if (result.isError && decision.granted) {
            audit(policy, {
              event: 'execution_failed_after_approval',
              tool: rawName,
              risk: decision.risk,
              code: 'TOOL_REPORTED_ERROR',
              target: auditTarget(args),
              digest: digest(canonicalArgs(args)),
              ms: Date.now() - started,
              session: sessId,
            });
          } else {
            audit(policy, {
              event: 'call', tool: rawName, risk: decision.risk, ok: businessOutcome(result),
              granted: Boolean(decision.granted),
              target: auditTarget(args), digest: digest(canonicalArgs(args)), ms: Date.now() - started, session: sessId,
            });
          }
          return out(renderResult(result, rawName));
        } catch (error) {
          const code = error instanceof McpError ? error.code : 'TOOL_FAILED';
          audit(policy, {
            event: decision.granted ? 'execution_failed_after_approval' : 'error',
            tool: rawName, risk: decision.risk, code,
            digest: digest(canonicalArgs(args)), ms: Date.now() - started, session: sessId,
          });
          return out({
            status: 'failed', tool: rawName, code, message: error.message,
            sideEffects: 'unknown — the call may have started before the failure; inspect the document before retrying',
            stderr: client?.stderrTail(10) ?? [],
          });
        }
      } finally {
        // C-LIFE-02: held until the wire call settles, so a concurrent
        // cross-session sync can never close a client that still has work on it.
        inflightCalls -= 1;
      }
    };
  }

  // ---- defence in depth: refuse denied tools even if registered elsewhere --
  if (typeof ctx?.tools?.guard === 'function' && typeof ctx?.effect === 'function') {
    ctx.effect(() => ctx.tools.guard(exec => {
      const toolName = String(exec?.name ?? '');
      const withoutNs = toolName.includes('.') ? toolName.split('.').pop() : toolName;
      const bare = prefix && withoutNs.startsWith(prefix) ? withoutNs.slice(prefix.length) : withoutNs;
      if (config.deny.includes(bare)) return `dsh-solidworks: ${bare} is denied by the plugin configuration.`;
      return undefined;
    }), 'dsh-solidworks: deny guard');
  }

  if (typeof ctx?.effect === 'function') {
    ctx.effect(() => cleanup, 'dsh-solidworks: teardown');
  }

  try { await ready; } catch (error) {
    if (error?._fatalRegistration) throw error;
    ctx?.logger?.warn?.(`dsh-solidworks: startup task failed: ${error.message}`);
  }
  return cleanup;
  } catch (error) {
    await cleanup();
    throw error;
  }
}

function describe(tool, policy) {
  const base = String(tool.description ?? '').trim();
  // C-TIER-01: the badge must advertise the tier that will actually be enforced.
  // `customTiers` can escalate a known tool (e.g. treat a read as high-risk), and
  // the static table would then promise "risk: read" for a call that triggers an
  // approval prompt.
  const risk = policy ? policy.tierOf(tool.name) : classify(tool.name);
  const suffix = `[risk: ${risk}]`;
  return base ? `${base}\n\n${suffix}` : `${tool.name} ${suffix}`;
}

function normaliseSchema(schema) {
  if (!schema || typeof schema !== 'object') return { type: 'object', properties: {}, additionalProperties: false };
  const copy = JSON.parse(JSON.stringify(schema));
  if (!copy.type) copy.type = 'object';
  if (!copy.properties || typeof copy.properties !== 'object') copy.properties = {};

  function enforceStrictObjects(node) {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) {
      for (const item of node) enforceStrictObjects(item);
      return;
    }
    if ((node.type === 'object' || node.properties !== undefined) && node.additionalProperties === undefined) {
      node.additionalProperties = false;
    }
    if (node.properties && typeof node.properties === 'object') {
      for (const prop of Object.values(node.properties)) enforceStrictObjects(prop);
    }
    if (node.items && typeof node.items === 'object') enforceStrictObjects(node.items);
    if (node.$defs && typeof node.$defs === 'object') {
      for (const def of Object.values(node.$defs)) enforceStrictObjects(def);
    }
    if (node.definitions && typeof node.definitions === 'object') {
      for (const def of Object.values(node.definitions)) enforceStrictObjects(def);
    }
    for (const branchKey of ['anyOf', 'oneOf', 'allOf']) {
      if (Array.isArray(node[branchKey])) {
        for (const sub of node[branchKey]) enforceStrictObjects(sub);
      }
    }
  }

  enforceStrictObjects(copy);
  return copy;
}

function renderResult(result, rawName) {
  const texts = (result.content ?? [])
    .filter(part => part?.type === 'text' && typeof part.text === 'string')
    .map(part => part.text);
  const text = texts.join('\n').trim();
  if (result.isError) {
    let extra = {};
    if (text.startsWith('{')) {
      try {
        const parsed = JSON.parse(text);
        if (parsed && typeof parsed === 'object' && typeof parsed.error_type === 'string') {
          extra = { error_type: parsed.error_type };
        }
      } catch {}
    }
    return { status: 'error', tool: rawName, message: text || 'The SolidWorks server reported an error with no message.', ...extra };
  }
  if (text === '') {
    return { status: 'ok', tool: rawName, result: result.structured ?? null };
  }
  return text;
}
