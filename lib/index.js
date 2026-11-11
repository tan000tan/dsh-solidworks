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

import { appendFileSync, mkdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { discover } from './discover.js';
import { McpClient, McpError } from './mcp.js';
import { Policy, auditTarget, classify, digest, canonicalArgs } from './policy.js';
import { unwrapParams, wrapArgs } from './schema.js';

export const name = 'dsh-solidworks';

/**
 * Cordis services this plugin consumes. The host refuses `ctx.tools` until the
 * declaration exists — without it `apply()` throws and the whole entry fails to
 * activate (verified against dsh 0.1.7-rc.2).
 */
export const inject = ['tools'];

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
  pythonPath: null,
  serverScript: null,
  serverCwd: null,
  toolPrefix: '',
  customTiers: {},
});

function normaliseConfig(raw) {
  const config = { ...DEFAULTS, ...(raw ?? {}) };
  config.allow = asStringArray(config.allow);
  config.deny = asStringArray(config.deny);
  config.allowedRoots = asStringArray(config.allowedRoots);
  config.customTiers = (raw?.customTiers && typeof raw.customTiers === 'object') ? raw.customTiers : {};
  if (!['read-only', 'standard', 'full'].includes(config.mode)) config.mode = DEFAULTS.mode;
  return config;
}

function asStringArray(value) {
  if (Array.isArray(value)) return value.filter(item => typeof item === 'string' && item.trim() !== '').map(item => item.trim());
  if (typeof value === 'string' && value.trim() !== '') return value.split(',').map(item => item.trim()).filter(Boolean);
  return [];
}

function audit(config, row) {
  if (!config.auditLog) return;
  try {
    mkdirSync(path.dirname(config.auditLog), { recursive: true });
    appendFileSync(config.auditLog, `${JSON.stringify(row)}\n`, 'utf8');
  } catch {
    // Auditing must never break a tool call; the failure is visible via doctor.
  }
}

/**
 * Registry-ready output contract required by `ctx.tools.register()`: every tool
 * must declare `output: { schema, render }` or registration throws
 * (`tool "x" must declare output { schema, render, presentationMeta? }`,
 * verified against dsh 0.1.7-rc.2). The schema is object-rooted and every
 * payload is delivered as `{ text }` so the same rendering works for the meta
 * tools and the mapped MCP tools.
 */
const OUTPUT = Object.freeze({
  schema: {
    type: 'object',
    additionalProperties: false,
    properties: { text: { type: 'string' } },
    required: ['text'],
  },
  render: (_args, value) => [{ type: 'text', text: String(value?.text ?? '') }],
});

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
    secretKey: config.secretKey,
    now: config.now ?? Date.now,
  });

  let client = null;
  let ready = null;
  const registered = [];
  const disposers = [];

  const publish = definition => {
    const dispose = ctx?.tools?.register?.(definition);
    registered.push(definition.name);
    if (typeof dispose === 'function') disposers.push(dispose);
    return dispose;
  };

  const prefix = config.toolPrefix || '';
  const publicName = raw => `${prefix}${raw}`;

  // ---- meta tools: always available, even when the server is down ---------
  publish({
    name: publicName('solidworks_status'),
    description: '查看 SolidWorks 插件当前健康状态与连接诊断（包含运行环境、CAD 服务连接状态、安全策略模式与最后一次错误）。当 CAD 建模遇到问题时首选调用本工具排查。',
    parameters: { type: 'object', properties: {}, additionalProperties: false },
    output: OUTPUT,
    execute: async () => out(statusReport()),
  });

  publish({
    name: publicName('solidworks_confirm'),
    description: '提交由本地人类明确审批签发的加密授权凭证 (HMAC-SHA256 Ticket)。凭证必须与具体操作、参数和挑战 ID 严格绑定。未提供有效凭证时拒绝执行，杜绝 AI 自行授权。',
    parameters: {
      type: 'object',
      properties: {
        challengeId: { type: 'string', description: '高危操作触发时返回的审批挑战标识符 (Challenge ID)。' },
        ticket: { type: 'string', description: '经由本地可信通道/人类明确授权签发的加密验签凭证 (HMAC-SHA256 Ticket)。' },
        tool: { type: 'string', description: '申请授权的完整工具名称。' },
        args: { type: 'object', description: '将要传递给该工具的精确参数对象。', additionalProperties: true },
        reason: { type: 'string', description: '简明说明申请授权的原因（如：保存底板模型、导出装配体工程图等）。' },
      },
      required: ['challengeId', 'ticket', 'tool', 'args'],
      additionalProperties: false,
    },
    output: OUTPUT,
    execute: async (args = {}) => {
      const tool = String(args.tool ?? '');
      const challengeId = String(args.challengeId ?? '');
      const ticket = String(args.ticket ?? '');
      const callArgs = args.args ?? {};

      if (policy.tierOf(tool) !== 'high') {
        return out({ status: 'not_required', tool, message: `${tool} 是普通操作，无需申请高危授权，可直接调用。` });
      }
      if (!policy.registerable(tool)) {
        return out({ status: 'refused', code: 'POLICY_MODE', message: `工具 ${tool} 在当前策略模式 (${policy.mode}) 下已被禁用。` });
      }

      const verification = policy.verifyAndConsumeTicket(challengeId, ticket, tool, callArgs, {
        sessionId: currentSessionId(),
      });

      if (!verification.ok) {
        audit(config, {
          ts: new Date().toISOString(),
          event: 'confirm_rejected',
          tool,
          challengeId,
          code: verification.code,
          message: verification.message,
          session: currentSessionId(),
        });
        return out({
          status: 'refused',
          code: verification.code,
          tool,
          challengeId,
          message: `安全防护阻断：${verification.message}`,
        });
      }

      const grant = verification.grant;
      audit(config, {
        ts: new Date().toISOString(),
        event: 'confirm_granted',
        tool,
        challengeId,
        digest: grant.digest,
        scope: grant.scope,
        reason: args.reason ?? null,
        session: currentSessionId(),
      });

      return out({
        status: 'granted',
        tool,
        challengeId,
        digest: grant.digest,
        scope: grant.scope,
        ttlMs: grant.ttlMs,
        next: `已验证可信人类授权凭证，操作授权生效。现在可以使用该精确参数执行 ${tool} 了。`,
      });
    },
  });

  if (ctx && typeof ctx === 'object') {
    ctx.solidworks = {
      getPendingChallenge: (challengeId) => policy.getChallenge(challengeId),
      signApproval: (challengeId, opts) => policy.signChallenge(challengeId, opts),
      policy,
    };
  }

  function currentSessionId() {
    try { return ctx?.agent?.session?.header?.id ?? null; } catch { return null; }
  }

  function sessionCwd() {
    try { return ctx?.agent?.session?.header?.cwd ?? null; } catch { return null; }
  }

  function statusReport() {
    return {
      plugin: { name, version: PLUGIN_VERSION, root: PLUGIN_ROOT },
      policy: { mode: policy.mode, registeredTools: registered.length, pendingGrants: policy.pendingGrants() },
      environment: environmentReport,
      connection: client?.running
        ? { running: true, tools: toolCount }
        : { running: false, error: startupError?.message ?? null, stderr: client?.stderrTail(10) ?? [] },
    };
  }

  let environmentReport = { state: 'pending' };
  let startupError = null;
  let toolCount = 0;
  /** server tool name -> does the server expect a { params: {...} } wrapper? */
  const toolWrapping = new Map();

  // ---- discovery + server startup ----------------------------------------
  ready = (async () => {
    const found = await discover({ pluginRoot: PLUGIN_ROOT, config, env: process.env, logger: ctx?.logger });
    if (!found.ok) {
      environmentReport = { state: 'error', code: found.code, message: found.message, notes: found.notes };
      startupError = new Error(found.message);
      ctx?.logger?.warn?.(`dsh-solidworks: ${found.message}`);
      return;
    }
    environmentReport = {
      state: 'ok',
      python: found.python,
      serverScript: found.serverScript,
      serverCwd: found.serverCwd,
      notes: found.notes,
    };

    client = new McpClient({
      command: found.python.command,
      args: [...found.python.args, found.serverScript],
      cwd: found.serverCwd,
      env: {
        PYTHONUTF8: '1',
        PYTHONIOENCODING: 'utf-8',
        PYTHONDONTWRITEBYTECODE: '1',
        DSH_ALLOWED_ROOTS: JSON.stringify(config.allowedRoots || []),
      },
      logger: ctx?.logger,
    });

    try {
      await client.initialize({ clientName: name, clientVersion: PLUGIN_VERSION, timeoutMs: config.startTimeoutMs });
      const tools = await client.listTools({ timeoutMs: config.startTimeoutMs });
      toolCount = tools.length;
      let serverPublished = 0;
      for (const tool of tools) {
        if (!tool?.name) continue;
        if (!policy.registerable(tool.name)) continue;
        const shape = unwrapParams(tool.inputSchema);
        toolWrapping.set(tool.name, shape.wrapped);
        publish({
          name: publicName(tool.name),
          description: describe(tool),
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
      ctx?.logger?.warn?.(`dsh-solidworks: server startup failed: ${error.message}`);
      await client?.close?.();
    }
  })();

  // ---- call path ---------------------------------------------------------
  function makeExecutor(rawName) {
    return async (args = {}, exec) => {
      const signal = exec?.signal;
      const started = Date.now();
      const sessCwd = exec?.session?.header?.cwd ?? sessionCwd();
      const sessId = exec?.session?.header?.id ?? currentSessionId();
      const decision = policy.evaluate(rawName, args, { sessionCwd: sessCwd, sessionId: sessId });
      if (!decision.allowed) {
        audit(config, {
          ts: new Date().toISOString(), event: 'refused', tool: rawName, code: decision.code,
          digest: digest(canonicalArgs(args)), session: sessId,
          challengeId: decision.challenge?.challengeId ?? null,
        });
        return out({
          status: 'refused',
          tool: rawName,
          code: decision.code,
          message: decision.reason,
          challenge: decision.challenge ?? null,
        });
      }
      await ready;
      if (!client?.running) {
        return out({
          status: 'unavailable',
          tool: rawName,
          code: startupError?.code ?? 'SERVER_UNAVAILABLE',
          message: startupError?.message ?? 'The SolidWorks MCP server is not running. Call solidworks_status for the diagnosis.',
          stderr: client?.stderrTail(10) ?? [],
        });
      }
      try {
        // The policy sees the arguments the user actually wrote (that is what
        // solidworks_confirm hashes); normalized rewritten arguments go to the wire.
        const effectiveArgs = decision.rewrittenArgs ?? args;
        const wireArgs = wrapArgs(toolWrapping.get(rawName) ?? false, effectiveArgs);
        const result = await client.callTool(rawName, wireArgs, { timeoutMs: config.toolTimeoutMs, signal });
        audit(config, {
          ts: new Date().toISOString(), event: 'call', tool: rawName, risk: decision.risk, ok: !result.isError,
          target: auditTarget(args), digest: digest(canonicalArgs(args)), ms: Date.now() - started, session: currentSessionId(),
        });
        return out(renderResult(result, rawName));
      } catch (error) {
        const code = error instanceof McpError ? error.code : 'TOOL_FAILED';
        audit(config, {
          ts: new Date().toISOString(), event: 'error', tool: rawName, risk: decision.risk, code,
          digest: digest(canonicalArgs(args)), ms: Date.now() - started, session: currentSessionId(),
        });
        return out({
          status: 'failed', tool: rawName, code, message: error.message,
          sideEffects: 'unknown — the call may have started before the failure; inspect the document before retrying',
          stderr: client?.stderrTail(10) ?? [],
        });
      }
    };
  }

  // ---- defence in depth: refuse denied tools even if registered elsewhere --
  if (typeof ctx?.tools?.guard === 'function' && typeof ctx?.effect === 'function') {
    ctx.effect(() => ctx.tools.guard(exec => {
      const toolName = String(exec?.name ?? '');
      const bare = prefix && toolName.startsWith(prefix) ? toolName.slice(prefix.length) : toolName;
      if (config.deny.includes(bare)) return `dsh-solidworks: ${bare} is denied by the plugin configuration.`;
      return undefined;
    }), 'dsh-solidworks: deny guard');
  }

  if (typeof ctx?.effect === 'function') {
    ctx.effect(() => async () => {
      for (const dispose of disposers.splice(0)) {
        try { dispose(); } catch { /* ignore */ }
      }
      await client?.close?.();
    }, 'dsh-solidworks: teardown');
  }

  // Await startup so a `dsh plugin` install check sees the real tool surface.
  // The catch keeps a bad environment from failing the whole host.
  try { await ready; } catch (error) { ctx?.logger?.warn?.(`dsh-solidworks: startup task failed: ${error.message}`); }
  return () => client?.close?.();
}

function describe(tool) {
  const base = String(tool.description ?? '').trim();
  const risk = classify(tool.name);
  const suffix = `[risk: ${risk}]`;
  return base ? `${base}\n\n${suffix}` : `${tool.name} ${suffix}`;
}

function normaliseSchema(schema) {
  if (!schema || typeof schema !== 'object') return { type: 'object', properties: {}, additionalProperties: false };
  const copy = JSON.parse(JSON.stringify(schema));
  if (!copy.type) copy.type = 'object';
  if (!copy.properties || typeof copy.properties !== 'object') copy.properties = {};
  if (copy.additionalProperties === undefined) copy.additionalProperties = false;
  return copy;
}

function renderResult(result, rawName) {
  const texts = (result.content ?? [])
    .filter(part => part?.type === 'text' && typeof part.text === 'string')
    .map(part => part.text);
  const text = texts.join('\n').trim();
  if (result.isError) {
    return { status: 'error', tool: rawName, message: text || 'The SolidWorks server reported an error with no message.' };
  }
  if (text === '') {
    return { status: 'ok', tool: rawName, result: result.structured ?? null };
  }
  return text;
}