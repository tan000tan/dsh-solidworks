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
 *   dsh-solidworks call solidworks_export_active --json-args '{"output_path":"part.step","export_format":"step"}' --mode full
 *
 * It goes through Policy.evaluate exactly like the plugin does, so a refusal
 * here is the same refusal DSH would report.
 *
 * Every command prints machine-readable JSON with --json, and never modifies a
 * CAD document.
 */

import os from 'node:os';
import path from 'node:path';
import { execFile, spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { existsSync, readFileSync } from 'node:fs';

import { discover, formatSetupCommand } from '../lib/discover.js';
import { McpClient } from '../lib/mcp.js';
import { Policy } from '../lib/policy.js';
import { unwrapParams, wrapArgs } from '../lib/schema.js';
import { getDshDesktopProfileDir } from '../scripts/dsh_adapter.js';

const PLUGIN_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const pkg = JSON.parse(readFileSync(path.join(PLUGIN_ROOT, 'package.json'), 'utf8'));
const VERSION = pkg.version;

const argv = process.argv.slice(2);

/** Flags that consume the following token as their value (C-CLI-01). */
const VALUE_FLAGS = new Set(['--mode', '--server', '--python', '--json-args', '--root', '--allow', '--profile']);

/**
 * The command is the first token that is neither a flag nor a flag's value.
 * Taking "the first token that does not start with -" made `--mode full
 * list-tools` resolve to the command "full" and fail with "unknown command",
 * even though it is a documented invocation order.
 */
function findCommandIndex(tokens) {
  for (let i = 0; i < tokens.length; i += 1) {
    const token = tokens[i];
    if (token.startsWith('-')) {
      if (VALUE_FLAGS.has(token)) i += 1;
      continue;
    }
    return i;
  }
  return -1;
}

const commandIndex = findCommandIndex(argv);
const command = commandIndex >= 0 ? argv[commandIndex] : 'doctor';
const flags = new Set(argv.filter(arg => arg.startsWith('-')));
const json = flags.has('--json');
const modeArg = valueOf('--mode');
const serverArg = valueOf('--server');
const pythonArg = valueOf('--python');
const profileArg = valueOf('--profile');
const useProfile = flags.has('--profile') || Boolean(profileArg);

/**
 * Read what the DSH desktop profile actually configures for this plugin.
 * `doctor` used to ignore the profile completely, so a dangling `pythonPath`
 * (or a narrowed `mode`) produced "ready: yes" while the host itself refused to
 * load the plugin. This makes the check honest: the same config the host reads.
 */
function readProfileConfig() {
  const dir = profileArg ? path.resolve(profileArg) : getDshDesktopProfileDir();
  const patchFile = path.join(dir, 'cordis.patch.yml');
  const result = {
    profileDir: dir,
    patchFile,
    installedAsBundle: false,
    dependencySpec: null,
    patchEntry: false,
    mode: null,
    pythonPath: null,
    toolTimeoutMs: null,
    issues: [],
  };

  // A plugin installed through DSH (market panel or `dsh plugin add`) is a *bundle*:
  // it appears in package.json dependencies + dsh.profile.bundles and DSH applies the
  // package's own dsh.bundle.patch. That is the normal path and needs no patch entry.
  const pkgFile = path.join(dir, 'package.json');
  if (existsSync(pkgFile)) {
    try {
      const profilePkg = JSON.parse(readFileSync(pkgFile, 'utf8'));
      result.dependencySpec = profilePkg.dependencies?.['dsh-solidworks'] ?? null;
      result.installedAsBundle = Boolean(profilePkg.dsh?.profile?.bundles?.includes('dsh-solidworks'));
    } catch (err) {
      result.issues.push(`profile package.json is not valid JSON: ${err.message}`);
    }
  }

  if (!existsSync(patchFile)) {
    if (!result.installedAsBundle) result.issues.push(`Neither a profile bundle nor a cordis.patch.yml entry found in ${dir}.`);
    return result;
  }
  const lines = readFileSync(patchFile, 'utf8').split(/\r?\n/);
  const indentOf = (line) => line.length - line.trimStart().length;
  const start = lines.findIndex((line) => /^[ \t]*-[ \t]*id:[ \t]*dsh-solidworks[ \t]*$/.test(line));
  if (start < 0) {
    if (!result.installedAsBundle) result.issues.push('cordis.patch.yml has no "dsh-solidworks" entry and the plugin is not a profile bundle.');
    return result;
  }
  result.patchEntry = true;
  const baseIndent = indentOf(lines[start]);
  for (let i = start + 1; i < lines.length; i += 1) {
    const line = lines[i];
    if (line.trim() === '') continue;
    if (indentOf(line) <= baseIndent) break;
    const m = line.trim().match(/^(mode|pythonPath|toolTimeoutMs):[ \t]*(.+)$/);
    if (!m) continue;
    const raw = m[2].trim().replace(/^'(.*)'$/, '$1').replace(/^"(.*)"$/, '$1');
    if (m[1] === 'toolTimeoutMs') result.toolTimeoutMs = Number(raw);
    else result[m[1]] = raw;
  }
  if (result.pythonPath && !existsSync(result.pythonPath)) {
    result.issues.push(`configured pythonPath does not exist: ${result.pythonPath} — the host will fail to load the plugin with PYTHON_INVALID.`);
  }
  return result;
}

function valueOf(flag) {
  const index = argv.indexOf(flag);
  if (index < 0) return undefined;
  const next = argv[index + 1];
  return next === undefined || next.startsWith('-') ? undefined : next;
}

function out(payload, human) {
  if (json) console.log(JSON.stringify(payload, null, 2));
  else console.log(human ?? JSON.stringify(payload, null, 2));
}

async function runScript(scriptName) {
  const scriptPath = path.join(PLUGIN_ROOT, 'scripts', scriptName);
  // Forward everything except the command token itself, by position: filtering by
  // value would also delete a *flag value* that happens to equal the command.
  const forwarded = argv.filter((_, index) => index !== commandIndex);
  const child = spawn(process.execPath, [scriptPath, ...forwarded], {
    cwd: PLUGIN_ROOT,
    stdio: 'inherit',
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' },
  });
  return new Promise((resolve) => {
    child.on('close', (code) => resolve(code ?? 0));
    child.on('error', (err) => {
      console.error(`cannot execute ${scriptName}: ${err.message}`);
      resolve(1);
    });
  });
}

async function main() {
  switch (command) {
    case 'setup': return runScript('setup.js');
    case 'doctor': return doctor();
    case 'mcp-config': return runScript('generate_mcp_config.js');
    case 'upgrade': return runScript('upgrade.js');
    case 'uninstall': return runScript('uninstall.js');
    case 'list-tools': return listTools();
    case 'selftest': return selftest();
    case 'call': return callTool();
    case 'challenges':
    case 'approve':
    case 'reject':
      out({
        ok: false,
        status: 'refused',
        code: 'APPROVAL_CLI_REMOVED',
        command,
        message: `CLI command "${command}" was removed (BUG-0002). Human approval for high-risk operations is enforced interactively via DSH Host UI (ctx.approval) and cannot be executed from a shell.`,
      }, `Refused: "${command}" CLI approval bypass was removed. High-risk operations must be approved interactively in the DSH Host UI.`);
      return 2;
    case 'version': out({ name: 'dsh-solidworks', version: VERSION, pluginRoot: PLUGIN_ROOT }); return 0;
    default:
      console.error(`unknown command: ${command}\nusage: dsh-solidworks [setup|doctor|mcp-config|list-tools|selftest|call <tool>|version|upgrade|uninstall] [--json] [--mode read-only|standard|full]`);
      return 2;
  }
}

async function doctor() {
  const profile = useProfile ? readProfileConfig() : null;
  const effectivePython = pythonArg ?? profile?.pythonPath ?? null;
  const config = { pythonPath: effectivePython, serverScript: serverArg ?? null };
  const found = await discover({ pluginRoot: PLUGIN_ROOT, config, env: process.env });
  const solidworks = await solidworksInstallation();
  const comDeps = Boolean(found.ok && found.python?.comDeps);
  const coreReady = Boolean(found.ok && solidworks.installed);
  const readiness = {
    core: coreReady,
    full: coreReady && comDeps,
    missing: [],
  };
  if (coreReady && !comDeps) {
    readiness.missing.push('comtypes (optional COM dependency) — advanced geometry/surface tools may fail without it; run: npm run setup -- --optional');
  }
  if (profile) {
    for (const issue of profile.issues) readiness.missing.push(issue);
  }
  const effectiveConfig = {
    source: pythonArg ? 'cli --python' : profile?.pythonPath ? 'DSH profile pythonPath' : 'auto-discovery',
    pythonPath: effectivePython,
    mode: profile?.mode ?? null,
    toolTimeoutMs: profile?.toolTimeoutMs ?? null,
  };
  const report = {
    plugin: { name: 'dsh-solidworks', version: VERSION, root: PLUGIN_ROOT },
    host: { platform: process.platform, arch: process.arch, node: process.versions.node, os: `${os.type()} ${os.release()}` },
    python: found.ok ? found.python : { state: 'error', message: found.message },
    server: found.ok ? { script: found.serverScript, cwd: found.serverCwd } : { state: 'error' },
    solidworks,
    profile,
    effectiveConfig,
    readiness,
    ready: coreReady,
    readyFull: readiness.full,
    nextSteps: nextSteps(found, solidworks, readiness, profile),
  };
  const human = [
    `dsh-solidworks ${VERSION} (${process.platform}/${process.arch}, node ${process.versions.node})`,
    `python : ${found.ok ? `${found.python.command} (${found.python.version})` : `NOT USABLE — ${found.message}`}`,
    `         config source: ${effectiveConfig.source}${effectiveConfig.mode ? `, mode: ${effectiveConfig.mode}` : ''}`,
    `server : ${found.ok ? found.serverScript : 'not resolved'}`,
    `SolidWorks: ${solidworks.installed ? `installed${solidworks.version ? ` ${solidworks.version}` : ''}` : 'NOT DETECTED'}`,
    `ready  : ${report.ready ? 'yes' : 'no'} (core) / ${report.readyFull ? 'yes' : 'no'} (full: COM dependencies present)`,
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
    env: {
      PYTHONUTF8: '1',
      PYTHONIOENCODING: 'utf-8',
      PYTHONDONTWRITEBYTECODE: '1',
      DSH_POLICY_MODE: mode,
      DSH_ALLOW_LAUNCH_SW: '0',
    },
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
  const conditionalHighTools = new Set([
    'solidworks_create_basic_part',
    'design_spec_build',
    'solidworks_update_dimension',
    'solidworks_create_configuration',
    'solidworks_activate_configuration',
    'solidworks_set_custom_properties',
  ]);
  const payload = {
    ok: true,
    protocolVersion: init?.protocolVersion ?? null,
    server: init?.serverInfo ?? null,
    mode,
    total: tools.length,
    published: published.map(tool => ({
      name: tool.name,
      risk: policy.tierOf(tool.name),
      ...(conditionalHighTools.has(tool.name) ? { conditionalRisk: 'high (elevates to high when persisting to disk or saving)' } : {}),
    })),
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
    env: {
      PYTHONUTF8: '1',
      PYTHONIOENCODING: 'utf-8',
      PYTHONDONTWRITEBYTECODE: '1',
      DSH_POLICY_MODE: 'read-only',
      DSH_ALLOW_LAUNCH_SW: '0',
    },
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
  const toolName = commandIndex >= 0 ? argv[commandIndex + 1] : undefined;
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

  const decision = policy.evaluate(toolName, args, { sessionCwd: process.cwd() });
  if (!decision.allowed) {
    const code = decision.code === 'CONFIRMATION_REQUIRED' ? 'APPROVAL_CHANNEL_UNAVAILABLE' : decision.code;
    const msg = decision.code === 'CONFIRMATION_REQUIRED'
      ? `${toolName} is high-risk and requires interactive DSH Host UI human approval (ctx.approval). CLI "--yes" bypass is disabled (failing closed).`
      : (decision.message ?? decision.reason);
    out({ ok: false, status: 'refused', code, tool: toolName, risk: decision.risk, reason: msg, message: msg, args, roots: policy.allowedRoots ?? null }, msg);
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
    env: {
      PYTHONUTF8: '1',
      PYTHONIOENCODING: 'utf-8',
      PYTHONDONTWRITEBYTECODE: '1',
      DSH_POLICY_MODE: mode,
      DSH_ALLOW_LAUNCH_SW: mode === 'read-only' ? '0' : '1',
      DSH_ALLOWED_ROOTS: JSON.stringify(policy.allowedRoots ?? []),
      DSH_DEFAULT_CWD: process.cwd(),
    },
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

function nextSteps(found, solidworks, readiness = null, profile = null) {
  const steps = [];
  if (!found.ok) {
    if (found.code === 'PYTHON_NOT_FOUND' || found.code === 'PYTHON_INVALID') {
      const setupCmd = formatSetupCommand(PLUGIN_ROOT);
      steps.push(`请运行一键初始化命令创建插件隔离 .venv 并安装 mcp/pywin32（不修改系统 Python）/ Run one-line isolated setup: ${setupCmd}`);
      steps.push('或手动指定已安装依赖的 64 位 Python 3.10+ / Or specify an existing interpreter: dsh-solidworks doctor --python "C:\\path\\to\\python.exe"');
      if (profile?.pythonPath) {
        steps.push(`The DSH profile pins pythonPath to ${profile.pythonPath}; fix or remove that pin in cordis.patch.yml, or point it at a working interpreter.`);
      }
    } else if (found.code === 'SERVER_SCRIPT_MISSING') {
      steps.push('The bundled server is missing from this install; reinstall the plugin or set serverScript to <solidworks-automation-skill>\\mcp-server\\server.py');
    } else {
      steps.push(found.message);
    }
  }
  if (!solidworks.installed) steps.push('Install or repair SolidWorks 2023-2026, then start it once so COM registration completes.');
  if (readiness) {
    for (const missing of readiness.missing) steps.push(missing);
  }
  if (steps.length === 0) steps.push('Ready: enable mode "standard" in plugin settings to start modelling, or run dsh-solidworks selftest.');
  return steps;
}

main().then(code => process.exit(code)).catch(error => {
  console.error(json ? JSON.stringify({ ok: false, error: error.message }) : `dsh-solidworks failed: ${error.message}`);
  process.exit(1);
});