#!/usr/bin/env node
/**
 * dsh-solidworks CLI — the operator-facing half of the plugin.
 *
 *   dsh-solidworks doctor      diagnose interpreter / server / policy (no SolidWorks needed)
 *   dsh-solidworks list-tools  connect, list the server tool surface, show what the policy publishes
 *   dsh-solidworks selftest    connect and call solidworks_health_check (touches SolidWorks read-only)
 *   dsh-solidworks call <tool> run ONE tool through the same policy gate the plugin uses
 *
 * `call` exists so a user (or a bug report) can reproduce a single tool call
 * without the GUI, and so the policy gate can be exercised end to end:
 *
 *   dsh-solidworks call solidworks_mass_properties
 *   dsh-solidworks call solidworks_create_basic_part --json-args '{"depth_mm":50}' --mode standard
 *   dsh-solidworks call solidworks_export_active --json-args '{"output_path":"D:\\out\\x.step","export_format":"step"}' --mode full --yes
 *
 * It goes through Policy.evaluate exactly like the plugin does, so a refusal
 * here is the same refusal DSH would report.
 *
 * Every command prints machine-readable JSON with --json, and never modifies a
 * CAD document.
 */

import os from 'node:os';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { readFileSync } from 'node:fs';

import { discover } from '../lib/discover.js';
import { McpClient } from '../lib/mcp.js';
import { Policy } from '../lib/policy.js';
import { unwrapParams, wrapArgs } from '../lib/schema.js';

const PLUGIN_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const VERSION = '0.1.0';

const argv = process.argv.slice(2);
const command = argv.find(arg => !arg.startsWith('-')) ?? 'doctor';
const flags = new Set(argv.filter(arg => arg.startsWith('-')));
const json = flags.has('--json');
const modeArg = valueOf('--mode');
const serverArg = valueOf('--server');
const pythonArg = valueOf('--python');

function valueOf(flag) {
  const index = argv.indexOf(flag);
  return index >= 0 ? argv[index + 1] : undefined;
}

function out(payload, human) {
  if (json) console.log(JSON.stringify(payload, null, 2));
  else console.log(human ?? JSON.stringify(payload, null, 2));
}

async function main() {
  switch (command) {
    case 'doctor': return doctor();
    case 'list-tools': return listTools();
    case 'selftest': return selftest();
    case 'call': return callTool();
    case 'version': out({ name: 'dsh-solidworks', version: VERSION, pluginRoot: PLUGIN_ROOT }); return 0;
    default:
      console.error(`unknown command: ${command}\nusage: dsh-solidworks [doctor|list-tools|selftest|call <tool>|version] [--json] [--mode read-only|standard|full]`);
      return 2;
  }
}

async function doctor() {
  const config = { pythonPath: pythonArg ?? null, serverScript: serverArg ?? null };
  const found = await discover({ pluginRoot: PLUGIN_ROOT, config, env: process.env });
  const solidworks = await solidworksInstallation();
  const report = {
    plugin: { name: 'dsh-solidworks', version: VERSION, root: PLUGIN_ROOT },
    host: { platform: process.platform, arch: process.arch, node: process.versions.node, os: `${os.type()} ${os.release()}` },
    python: found.ok ? found.python : { state: 'error', message: found.message },
    server: found.ok ? { script: found.serverScript, cwd: found.serverCwd } : { state: 'error' },
    solidworks,
    ready: found.ok && solidworks.installed,
    nextSteps: nextSteps(found, solidworks),
  };
  const human = [
    `dsh-solidworks ${VERSION} (${process.platform}/${process.arch}, node ${process.versions.node})`,
    `python : ${found.ok ? `${found.python.command} (${found.python.version})` : `NOT USABLE — ${found.message}`}`,
    `server : ${found.ok ? found.serverScript : 'not resolved'}`,
    `SolidWorks: ${solidworks.installed ? `installed${solidworks.version ? ` ${solidworks.version}` : ''}` : 'NOT DETECTED'}`,
    `ready  : ${report.ready ? 'yes' : 'no'}`,
    ...report.nextSteps.map(step => `  -> ${step}`),
  ].join('\n');
  out(report, human);
  return report.ready ? 0 : 1;
}

async function listTools() {
  const mode = modeArg ?? 'read-only';
  const found = await discover({ pluginRoot: PLUGIN_ROOT, config: { pythonPath: pythonArg ?? null, serverScript: serverArg ?? null }, env: process.env });
  if (!found.ok) {
    out({ ok: false, code: found.code, message: found.message }, `cannot start: ${found.message}`);
    return 1;
  }
  const client = new McpClient({
    command: found.python.command,
    args: [...found.python.args, found.serverScript],
    cwd: found.serverCwd,
    env: { PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8', PYTHONDONTWRITEBYTECODE: '1' },
  });
  let init;
  let tools;
  try {
    init = await client.initialize({ clientName: 'dsh-solidworks-cli', clientVersion: VERSION, timeoutMs: 60_000 });
    tools = await client.listTools({ timeoutMs: 60_000 });
  } catch (error) {
    const stderr = client.stderrTail(30);
    out({ ok: false, code: error.code ?? 'STARTUP_FAILED', message: error.message, stderr }, [
      `cannot start the server: ${error.message}`,
      ...stderr.map(line => `  ${line}`),
    ].join('\n'));
    return 1;
  } finally {
    await client.close();
  }

  const policy = new Policy({ mode });
  const published = tools.filter(tool => policy.registerable(tool.name));
  const withheld = tools.filter(tool => !policy.registerable(tool.name));
  const payload = {
    ok: true,
    protocolVersion: init?.protocolVersion ?? null,
    server: init?.serverInfo ?? null,
    mode,
    total: tools.length,
    published: published.map(tool => ({ name: tool.name, risk: policy.tierOf(tool.name) })),
    withheld: withheld.map(tool => ({ name: tool.name, risk: policy.tierOf(tool.name) })),
  };
  out(payload, [
    `server ${payload.server?.name ?? '?'} ${payload.server?.version ?? ''} (protocol ${payload.protocolVersion})`,
    `mode ${mode}: ${published.length} published / ${withheld.length} withheld of ${tools.length}`,
    ...withheld.map(tool => `  withheld [${policy.tierOf(tool.name)}] ${tool.name}`),
  ].join('\n'));
  return 0;
}

async function selftest() {
  const found = await discover({ pluginRoot: PLUGIN_ROOT, config: { pythonPath: pythonArg ?? null, serverScript: serverArg ?? null }, env: process.env });
  if (!found.ok) {
    out({ ok: false, code: found.code, message: found.message }, `cannot start: ${found.message}`);
    return 1;
  }
  const client = new McpClient({
    command: found.python.command,
    args: [...found.python.args, found.serverScript],
    cwd: found.serverCwd,
    env: { PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8', PYTHONDONTWRITEBYTECODE: '1' },
    timeoutMs: 120_000,
  });
  try {
    await client.initialize({ clientName: 'dsh-solidworks-cli', clientVersion: VERSION });
    const result = await client.callTool('solidworks_health_check', {}, { timeoutMs: 120_000 });
    const text = result.content.filter(part => part?.type === 'text').map(part => part.text).join('\n');
    out({ ok: !result.isError, isError: result.isError, text }, text);
    return result.isError ? 1 : 0;
  } finally {
    await client.close();
  }
}

async function callTool() {
  const toolName = argv[argv.indexOf('call') + 1];
  if (!toolName || toolName.startsWith('-')) {
    console.error(`usage: dsh-solidworks call <tool> [--json-args '{"k":v}'] [--mode read-only|standard|full] [--root <dir>] [--allow <tool>] [--yes]`);
    return 2;
  }

  let args = {};
  const rawArgs = valueOf('--json-args');
  if (rawArgs !== undefined) {
    try {
      // `--json-args @args.json` reads the object from a file: on Windows the
      // shell mangles quotes and backslashes long before node sees them, and a
      // path like "C:\out\x.step" is the normal case for export tools.
      const text = rawArgs.startsWith('@') ? readFileSync(rawArgs.slice(1), 'utf8') : rawArgs;
      // Windows editors (and PowerShell 5.1's Set-Content) like to prefix a BOM.
      args = JSON.parse(text.replace(/^\uFEFF/, ''));
    } catch (error) {
      console.error(`--json-args could not be parsed: ${error.message}`);
      return 2;
    }
  }

  const mode = modeArg ?? 'standard';
  const rootArg = valueOf('--root');
  const allowArg = valueOf('--allow');
  const policy = new Policy({
    mode,
    allow: allowArg ? [allowArg] : [],
    allowedRoots: rootArg ? [rootArg] : [process.cwd()],
  });

  // Same two gates the plugin applies: publication, then per-call evaluation.
  if (!policy.registerable(toolName)) {
    const tier = policy.tierOf(toolName);
    const message = tier === 'high'
      ? `${toolName} is high-risk: run with --mode full (and --yes) or allow it explicitly.`
      : `${toolName} is a ${tier}-risk tool and mode "${mode}" does not publish it; use --mode standard or --allow ${toolName}.`;
    out({ ok: false, status: 'refused', code: 'NOT_PUBLISHED', tool: toolName, risk: tier, message }, message);
    return 3;
  }

  let decision = policy.evaluate(toolName, args, { sessionCwd: process.cwd() });
  if (!decision.allowed && decision.code === 'CONFIRMATION_REQUIRED' && flags.has('--yes')) {
    policy.grant(toolName, args);
    decision = policy.evaluate(toolName, args, { sessionCwd: process.cwd() });
  }
  if (!decision.allowed) {
    out({ ok: false, status: 'refused', code: decision.code, tool: toolName, risk: decision.risk, reason: decision.reason, message: decision.message ?? decision.reason, args, roots: policy.allowedRoots ?? null }, decision.reason ?? decision.message);
    return 3;
  }

  const found = await discover({ pluginRoot: PLUGIN_ROOT, config: { pythonPath: pythonArg ?? null, serverScript: serverArg ?? null }, env: process.env });
  if (!found.ok) {
    out({ ok: false, code: found.code, message: found.message }, `cannot start: ${found.message}`);
    return 1;
  }

  const client = new McpClient({
    command: found.python.command,
    args: [...found.python.args, found.serverScript],
    cwd: found.serverCwd,
    env: { PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8', PYTHONDONTWRITEBYTECODE: '1' },
    timeoutMs: 300_000,
  });
  try {
    await client.initialize({ clientName: 'dsh-solidworks-cli', clientVersion: VERSION });
    const tools = await client.listTools({ timeoutMs: 60_000 });
    const tool = tools.find(candidate => candidate.name === toolName);
    if (!tool) {
      out({ ok: false, code: 'UNKNOWN_TOOL', tool: toolName, message: `the server does not expose ${toolName}` }, `unknown tool: ${toolName}`);
      return 4;
    }
    // Same wire shape the plugin uses: FastMCP tools take a single `params` object.
    const wireArgs = wrapArgs(unwrapParams(tool.inputSchema).wrapped, args);
    const started = Date.now();
    const result = await client.callTool(toolName, wireArgs, { timeoutMs: 300_000 });
    const text = (result.content ?? []).filter(part => part?.type === 'text').map(part => part.text).join('\n');
    const elapsedMs = Date.now() - started;
    out(
      { ok: !result.isError, status: result.isError ? 'failed' : 'ok', tool: toolName, risk: decision.risk, granted: decision.granted ?? false, elapsedMs, isError: !!result.isError, text },
      `${toolName} [${decision.risk}] ${result.isError ? 'FAILED' : 'ok'} in ${elapsedMs} ms\n${text}`,
    );
    return result.isError ? 1 : 0;
  } catch (error) {
    const stderr = client.stderrTail(20);
    out({ ok: false, status: 'failed', tool: toolName, code: error.code ?? 'CALL_FAILED', message: error.message, stderr }, `call failed: ${error.message}`);
    return 1;
  } finally {
    await client.close();
  }
}

async function solidworksInstallation() {
  if (process.platform !== 'win32') return { installed: false, reason: 'SolidWorks only runs on Windows' };
  const keys = [
    'HKLM\\SOFTWARE\\SolidWorks',
    'HKLM\\SOFTWARE\\WOW6432Node\\SolidWorks',
  ];
  for (const key of keys) {
    const value = await regQuery(key);
    if (value) return { installed: true, registryKey: key, version: value };
  }
  return { installed: false, reason: 'no SolidWorks registry key under HKLM\\SOFTWARE' };
}

function regQuery(key) {
  return new Promise(resolve => {
    execFile('reg.exe', ['query', key], { windowsHide: true, timeout: 10_000 }, (error, stdout) => {
      if (error) return resolve(null);
      const match = /SolidWorks\s+(\d{4})/i.exec(stdout) ?? /\\(\d{4})\\/.exec(stdout);
      resolve(match ? match[1] : 'present');
    });
  });
}

function nextSteps(found, solidworks) {
  const steps = [];
  if (!found.ok) {
    if (found.code === 'PYTHON_NOT_FOUND' || found.code === 'PYTHON_INVALID') {
      steps.push('Install Python 3.10+ (python.org, 64-bit) and run: <python> -m pip install "mcp>=1.2" httpx pydantic ezdxf');
      steps.push('Then re-run: dsh-solidworks doctor --python "C:\\path\\to\\python.exe"');
    } else if (found.code === 'SERVER_SCRIPT_MISSING') {
      steps.push('The bundled server is missing from this install; reinstall the plugin or set serverScript to <solidworks-automation-skill>\\mcp-server\\server.py');
    } else {
      steps.push(found.message);
    }
  }
  if (!solidworks.installed) steps.push('Install or repair SolidWorks 2023-2026, then start it once so COM registration completes.');
  if (steps.length === 0) steps.push('Ready: enable mode "standard" in plugin settings to start modelling, or run dsh-solidworks selftest.');
  return steps;
}

main().then(code => process.exit(code)).catch(error => {
  console.error(json ? JSON.stringify({ ok: false, error: error.message }) : `dsh-solidworks failed: ${error.message}`);
  process.exit(1);
});