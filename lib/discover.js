/**
 * Environment discovery: which Python, and which SolidWorks MCP server script.
 *
 * Discovery is explicit and verifiable. A candidate only wins after it proves
 * it can `import mcp` and print a version — the Windows Store alias stub
 * (`WindowsApps\python.exe`) looks like a real interpreter on PATH but cannot
 * import anything, so "found python.exe" is never treated as success.
 */

import { spawn, spawnSync } from 'node:child_process';
import { existsSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';

export const PROBE_SOURCE = "import mcp,sys;print('OK',sys.version.split()[0],mcp.__file__)";

const PROBE_TIMEOUT_MS = 20_000;

// Import check, run with the same -c as the probe; kept separate so a failure
// message can name the missing module.
export function probePython(candidate, { timeoutMs = PROBE_TIMEOUT_MS } = {}) {
  return new Promise(resolve => {
    let settled = false;
    const finish = value => { if (!settled) { settled = true; resolve(value); } };
    let child;
    try {
      child = spawn(candidate.command, [...(candidate.args ?? []), '-c', PROBE_SOURCE], {
        stdio: ['ignore', 'pipe', 'pipe'],
        windowsHide: true,
      });
    } catch (error) {
      finish({ ok: false, reason: `cannot execute: ${error.message}` });
      return;
    }
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => {
      try { child.kill(); } catch { /* ignore */ }
      finish({ ok: false, reason: `probe timed out after ${timeoutMs}ms` });
    }, timeoutMs);
    timer.unref?.();
    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');
    child.stdout.on('data', chunk => { stdout += chunk; });
    child.stderr.on('data', chunk => { stderr += chunk; });
    child.on('error', error => { clearTimeout(timer); finish({ ok: false, reason: `cannot execute: ${error.message}` }); });
    child.on('exit', code => {
      clearTimeout(timer);
      const text = stdout.trim();
      if (code === 0 && text.startsWith('OK ')) {
        const [, version, modulePath] = text.split(' ');
        finish({ ok: true, version, modulePath, command: candidate.command, args: candidate.args ?? [] });
        return;
      }
      const detail = (stderr.trim() || stdout.trim() || '').slice(0, 400);
      finish({
        ok: false,
        reason: code === 9009
          ? 'not a real interpreter (Windows Store alias stub?)'
          : `exit ${code}${detail ? `: ${detail}` : ''}`,
      });
    });
  });
}

function pythonCandidates(env) {
  const list = [];
  const push = (command, args = [], label = command) => {
    if (command) list.push({ command, args, label });
  };
  push('py', ['-3'], 'py -3');
  push('python', [], 'python (PATH)');
  push('python3', [], 'python3 (PATH)');

  const roots = [env.LOCALAPPDATA && path.join(env.LOCALAPPDATA, 'Programs', 'Python'), 'C:\\', env.PROGRAMFILES && path.join(env.PROGRAMFILES, 'Python')].filter(Boolean);
  for (const root of roots) {
    if (!existsSync(root)) continue;
    let entries = [];
    try { entries = readdirSync(root); } catch { continue; }
    for (const entry of entries.filter(name => /^Python3\d+$/i.test(name)).sort().reverse()) {
      const exe = path.join(root, entry, 'python.exe');
      if (existsSync(exe)) push(exe, [], exe);
    }
  }
  return list;
}

/**
 * Interpreters registered with the Windows `py` launcher, in launcher order.
 * `py -0p` prints lines like ` -V:3.13 *        D:\Python313\python.exe`, which
 * covers per-user installs that are not on PATH — the common case on machines
 * where Python was installed "for me only".
 */
function launcherCandidates() {
  const found = [];
  try {
    const result = spawnSync('py', ['-0p'], { encoding: 'utf8', timeout: 5_000, windowsHide: true });
    if (result.status !== 0 || !result.stdout) return found;
    for (const line of result.stdout.split(/\r?\n/)) {
      const start = line.search(/[A-Za-z]:\\/);
      if (start < 0) continue;
      const candidate = line.slice(start).trim();
      if (candidate.toLowerCase().endsWith('python.exe')) {
        found.push({ command: candidate, args: [], label: `py launcher: ${candidate}` });
      }
    }
  } catch {
    // No launcher on this machine; the PATH and well-known-root probes cover it.
  }
  return found;
}

/** Every interpreter candidate, most specific first. */
function entryCandidates(env) {
  const list = [];
  if (env.DSH_SOLIDWORKS_PYTHON) {
    list.push({ command: env.DSH_SOLIDWORKS_PYTHON, args: [], label: 'DSH_SOLIDWORKS_PYTHON' });
  }
  list.push(...launcherCandidates(), ...pythonCandidates(env));
  const seen = new Set();
  return list.filter(candidate => {
    const key = `${candidate.command}\u0000${candidate.args.join(' ')}`.toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/**
 * Resolve the interpreter and the server script.
 * @returns {Promise<{ok: true, python: object, serverScript: string, serverCwd: string, notes: string[]}
 *   | {ok: false, code: string, message: string, notes: string[]}>}
 */
export async function discover({ pluginRoot, config = {}, env = process.env, logger } = {}) {
  const notes = [];
  if (!pluginRoot) throw new Error('discover() needs pluginRoot');

  // ---- interpreter ------------------------------------------------------
  let python = null;
  if (config.pythonPath) {
    const candidate = { command: config.pythonPath, args: [], label: 'config.pythonPath' };
    const result = await probePython(candidate);
    if (result.ok) python = result;
    else return { ok: false, code: 'PYTHON_INVALID', message: `configured pythonPath failed the import check (${result.reason})`, notes };
  } else {
    const failures = [];
    for (const candidate of entryCandidates(env)) {
      const result = await probePython(candidate);
      if (result.ok) {
        python = { ...result, label: candidate.label };
        notes.push(`python: ${candidate.label} -> ${result.command} ${result.args.join(' ')} (${result.version})`);
        break;
      }
      failures.push(`${candidate.label}: ${result.reason}`);
    }
    if (!python) {
      return {
        ok: false,
        code: 'PYTHON_NOT_FOUND',
        message: `no Python with the "mcp" package was found. Tried: ${failures.join('; ')}`,
        notes,
      };
    }
  }

  // ---- server script ----------------------------------------------------
  const bundled = path.join(pluginRoot, 'vendor', 'solidworks-automation-skill', 'mcp-server', 'server.py');
  const serverScript = config.serverScript || env.DSH_SOLIDWORKS_SERVER || bundled;
  if (!existsSync(serverScript) || !statSync(serverScript).isFile()) {
    return {
      ok: false,
      code: 'SERVER_SCRIPT_MISSING',
      message: `SolidWorks MCP server script not found at ${serverScript}. Set the "serverScript" setting to the mcp-server/server.py of solidworks-automation-skill.`,
      notes,
    };
  }
  const serverCwd = config.serverCwd || path.dirname(path.dirname(serverScript));
  if (!existsSync(serverCwd)) {
    return { ok: false, code: 'SERVER_CWD_MISSING', message: `server working directory not found: ${serverCwd}`, notes };
  }
  logger?.debug?.(`dsh-solidworks: discover ok python=${python.command} server=${serverScript} cwd=${serverCwd}`);
  return { ok: true, python: { command: python.command, args: python.args, version: python.version }, serverScript, serverCwd, notes };
}