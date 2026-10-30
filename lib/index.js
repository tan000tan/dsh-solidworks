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

import { appendFileSync, mkdirSync } from 'node:fs';
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
const PLUGIN_VERSION = '0.1.0';

export const DEFAULTS = Object.freeze({
  mode: 'read-only',
  allow: [],
  deny: [],
  allowedRoots: [],
  grantTtlMs: 300_000,
  toolTimeoutMs: 300_000,
  startTimeoutMs: 60_000,
  auditLog: null,
  pythonPath: null,
  serverScript: null,
  serverCwd: null,
  toolPrefix: '',
});

function normaliseConfig(raw) {
  const config = { ...DEFAULTS, ...(raw ?? {}) };
  config.allow = asStringArray(config.allow);
  config.deny = asStringArray(config.deny);
  config.allowedRoots = asStringArray(config.allowedRoots);
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
    allowedRoots: config.allowedRoots,
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
    description: 'Report whether the SolidWorks plugin can reach SolidWorks: interpreter, server script, policy mode, and the last startup error. Use this first when a CAD tool fails.',
    parameters: { type: 'object', properties: {}, additionalProperties: false },
    output: OUTPUT,
    execute: async () => out(statusReport()),
  });

  publish({
    name: publicName('solidworks_confirm'),
    description: 'Record explicit user approval for one high-risk SolidWorks call. Pass the exact tool name and arguments you are about to use; the approval is single-use and expires.',
    parameters: {
      type: 'object',
      properties: {
        tool: { type: 'string', description: 'Exact tool name being approved.' },
        args: { type: 'object', description: 'Exact arguments object that will be passed to that tool.', additionalProperties: true },
        reason: { type: 'string', description: 'One line quoting what the user approved.' },
      },
      required: ['tool', 'args'],
      additionalProperties: false,
    },
    output: OUTPUT,
    execute: async (args = {}) => {
      const tool = String(args.tool ?? '');
      if (policy.tierOf(tool) !== 'high') {
        return out({ status: 'not_required', tool, message: `${tool} is not a high-risk tool; call it directly.` });
      }
      if (!policy.registerable(tool)) {
        return out({ status: 'refused', code: 'POLICY_MODE', message: `${tool} is disabled by the plugin policy (mode=${policy.mode}).` });
      }
      const grant = policy.grant(tool, args.args ?? {});
      audit(config, { ts: new Date().toISOString(), event: 'confirm', tool, digest: grant.digest, reason: args.reason ?? null, session: currentSessionId() });
      return out({ status: 'granted', tool, digest: grant.digest, ttlMs: grant.ttlMs, next: `Call ${tool} with exactly the same arguments now.` });
    },
  });

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
      env: { PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8', PYTHONDONTWRITEBYTECODE: '1' },
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
      const decision = policy.evaluate(rawName, args, { sessionCwd: exec?.session?.header?.cwd ?? sessionCwd() });
      if (!decision.allowed) {
        audit(config, {
          ts: new Date().toISOString(), event: 'refused', tool: rawName, code: decision.code,
          digest: digest(canonicalArgs(args)), session: currentSessionId(),
        });
        return out({ status: 'refused', tool: rawName, code: decision.code, message: decision.reason });
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
        // solidworks_confirm hashes); the wrapper goes back on for the wire.
        const wireArgs = wrapArgs(toolWrapping.get(rawName) ?? false, args);
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
  if (typeof ctx?.tools?.guard === 'function') {
    ctx.effect(() => ctx.tools.guard(exec => {
      const toolName = String(exec?.name ?? '');
      const bare = prefix && toolName.startsWith(prefix) ? toolName.slice(prefix.length) : toolName;
      if (config.deny.includes(bare)) return `dsh-solidworks: ${bare} is denied by the plugin configuration.`;
      return undefined;
    }), 'dsh-solidworks: deny guard');
  }

  ctx.effect(() => async () => {
    for (const dispose of disposers.splice(0)) {
      try { dispose(); } catch { /* ignore */ }
    }
    await client?.close?.();
  }, 'dsh-solidworks: teardown');

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