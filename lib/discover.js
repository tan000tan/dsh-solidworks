/**
 * Environment discovery: which Python, and which SolidWorks MCP server script.
 */

import { spawn, spawnSync } from 'node:child_process';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';

export const PROBE_SOURCE = [
  'import importlib,importlib.util,sys',
  'import mcp,pydantic,jsonschema',
  "has_fastmcp=any(importlib.util.find_spec(m) is not None for m in ('mcp.server.fastmcp','mcp.server.mcpserver'))",
  "assert has_fastmcp,'missing mcp FastMCP/MCPServer'",
  "(sys.platform!='win32' or (importlib.import_module('win32com.client'),importlib.import_module('pythoncom')))",
  "comdep='1' if (sys.platform!='win32' or (importlib.util.find_spec('comtypes') and importlib.util.find_spec('win32com'))) else '0'",
  "print('OK',sys.version.split()[0],mcp.__file__,'COMDEP='+comdep)",
].join(';');

const PROBE_TIMEOUT_MS = 20_000;

export function probePython(candidate, { timeoutMs = PROBE_TIMEOUT_MS } = {}) {
  const cmdStr = String(candidate?.command ?? '');
  if (cmdStr.toLowerCase().includes('windowsapps')) {
    return Promise.resolve({
      ok: false,
      code: 'WINDOWS_STORE_ALIAS',
      reason: 'not a real interpreter (Windows Store alias stub in WindowsApps)',
    });
  }
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
        const [, version, modulePath, comdepToken] = text.split(' ');
        const comDeps = comdepToken ? comdepToken === 'COMDEP=1' : true;
        finish({ ok: true, version, modulePath, comDeps, command: candidate.command, args: candidate.args ?? [] });
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
    // ignore
  }
  return found;
}

export function venvCandidates(pluginRoot) {
  if (!pluginRoot) return [];
  const list = [];
  const venvDir = path.join(pluginRoot, '.venv');
  const venvPython = process.platform === 'win32'
    ? path.join(venvDir, 'Scripts', 'python.exe')
    : path.join(venvDir, 'bin', 'python');

  if (existsSync(venvPython)) {
    list.push({ command: venvPython, args: [], label: `local .venv: ${venvPython}` });
  }

  const cfgFile = path.join(venvDir, 'pyvenv.cfg');
  if (existsSync(cfgFile)) {
    try {
      const txt = readFileSync(cfgFile, 'utf8');
      const exeMatch = txt.match(/executable\s*=\s*(.+)/);
      if (exeMatch) {
        const exe = exeMatch[1].trim();
        if (existsSync(exe)) {
          list.push({ command: exe, args: [], label: `pyvenv.cfg executable: ${exe}` });
        }
      }
      const homeMatch = txt.match(/home\s*=\s*(.+)/);
      if (homeMatch) {
        const homePy = path.join(homeMatch[1].trim(), process.platform === 'win32' ? 'python.exe' : 'python');
        if (existsSync(homePy)) {
          list.push({ command: homePy, args: [], label: `pyvenv.cfg home: ${homePy}` });
        }
      }
    } catch {
      // ignore read error
    }
  }
  return list;
}

export function embeddedCandidates(pluginRoot) {
  if (!pluginRoot) return [];
  const list = [];
  const embeddedPy = path.join(pluginRoot, '.runtime', 'python', 'python.exe');
  if (existsSync(embeddedPy)) {
    list.push({ command: embeddedPy, args: [], label: `embedded runtime: ${embeddedPy}` });
  }
  return list;
}

export function tryAutoBootstrap(candidate, { pluginRoot, logger, timeoutMs = 120_000 } = {}) {
  const isPrivateVenv = pluginRoot && candidate.command.toLowerCase().startsWith(path.resolve(pluginRoot).toLowerCase());

  if (isPrivateVenv) {
    try {
      logger?.info?.(`dsh-solidworks: 正在为插件专属虚拟环境 (${candidate.label}) 补齐核心依赖 (mcp, pywin32)...`);
      const pipArgs = [
        ...(candidate.args ?? []),
        '-m', 'pip', 'install', '--quiet',
        'mcp>=1.27,<2', 'pydantic>=2.0', 'pywin32>=305', 'comtypes>=1.2.0', 'jsonschema>=4.20,<5',
        '-i', 'https://pypi.tuna.tsinghua.edu.cn/simple',
        '--extra-index-url', 'https://pypi.org/simple',
      ];
      const res = spawnSync(candidate.command, pipArgs, {
        timeout: timeoutMs,
        windowsHide: true,
        encoding: 'utf8',
      });
      if (res.status === 0) {
        logger?.info?.(`dsh-solidworks: 依赖自动安装成功 (${candidate.label})`);
        return true;
      }
    } catch (err) {
      logger?.debug?.(`dsh-solidworks: 专属虚拟环境自举安装跳过: ${err.message}`);
    }
    return false;
  }

  if (pluginRoot && existsSync(pluginRoot)) {
    try {
      const venvDir = path.join(pluginRoot, '.venv');
      logger?.info?.(`dsh-solidworks: 探测到宿主可用种子 Python (${candidate.label})，正在自动创建插件隔离专属环境 (.venv)...`);

      const venvPy = process.platform === 'win32'
        ? path.join(venvDir, 'Scripts', 'python.exe')
        : path.join(venvDir, 'bin', 'python');

      if (!existsSync(venvPy)) {
        const venvRes = spawnSync(candidate.command, [...(candidate.args ?? []), '-m', 'venv', venvDir], {
          timeout: timeoutMs,
          windowsHide: true,
          encoding: 'utf8',
        });
        if (venvRes.status !== 0 || !existsSync(venvPy)) {
          logger?.debug?.(`dsh-solidworks: 创建隔离虚拟环境未成功: ${venvRes.stderr || venvRes.stdout}`);
          return false;
        }
      }

      logger?.info?.(`dsh-solidworks: 正在为插件隔离环境配置核心依赖 (mcp, pywin32)...`);
      const pipArgs = [
        '-m', 'pip', 'install', '--quiet',
        'mcp>=1.27,<2', 'pydantic>=2.0', 'pywin32>=305', 'comtypes>=1.2.0', 'jsonschema>=4.20,<5',
        '-i', 'https://pypi.tuna.tsinghua.edu.cn/simple',
        '--extra-index-url', 'https://pypi.org/simple',
      ];
      const pipRes = spawnSync(venvPy, pipArgs, {
        timeout: timeoutMs,
        windowsHide: true,
        encoding: 'utf8',
      });
      if (pipRes.status === 0) {
        logger?.info?.(`dsh-solidworks: 插件专属隔离运行环境初始化成功！`);
        return { createdVenvPy: venvPy };
      }
    } catch (err) {
      logger?.debug?.(`dsh-solidworks: 隔离环境自举失败: ${err.message}`);
    }
  }
  return false;
}

export function dshRuntimeCandidates(env = process.env) {
  const list = [];
  const roots = [];
  if (env.DSH_HOME && String(env.DSH_HOME).trim() !== '') {
    roots.push(String(env.DSH_HOME).trim());
  }
  const userProfile = env.USERPROFILE || env.HOME;
  if (userProfile) {
    roots.push(path.join(userProfile, '.dsh'));
  }
  const seen = new Set();
  for (const base of roots) {
    for (const rel of [
      path.join('dsh-runtimes', 'dsh-primary-runtime', 'dependencies', 'python', 'python.exe'),
      path.join('runtime', 'python', 'python.exe'),
    ]) {
      const dshPy = path.join(base, rel);
      const norm = dshPy.toLowerCase();
      if (seen.has(norm)) continue;
      seen.add(norm);
      if (existsSync(dshPy)) {
        list.push({ command: dshPy, args: [], label: `dsh runtime: ${dshPy}` });
      }
    }
  }
  return list;
}

export function entryCandidates(env, pluginRoot = null) {
  const list = [];
  if (env.DSH_SOLIDWORKS_PYTHON) {
    list.push({ command: env.DSH_SOLIDWORKS_PYTHON, args: [], label: 'DSH_SOLIDWORKS_PYTHON' });
  }
  list.push(...embeddedCandidates(pluginRoot), ...venvCandidates(pluginRoot), ...dshRuntimeCandidates(env), ...launcherCandidates(), ...pythonCandidates(env));
  const seen = new Set();
  return list.filter(candidate => {
    const key = `${candidate.command}\u0000${candidate.args.join(' ')}`.toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function formatSetupCommand(pluginRoot) {
  const resolvedRoot = path.resolve(pluginRoot);
  return process.platform === 'win32'
    ? `cd /d "${resolvedRoot}" && npm run setup`
    : `cd "${resolvedRoot}" && npm run setup`;
}

export async function discover({ pluginRoot, config = {}, env = process.env, logger, _probePython = probePython } = {}) {
  const notes = [];
  if (!pluginRoot) throw new Error('discover() needs pluginRoot');

  const setupCmd = formatSetupCommand(pluginRoot);
  let python = null;
  if (config.pythonPath) {
    const candidate = { command: config.pythonPath, args: [], label: 'config.pythonPath' };
    const result = await _probePython(candidate);
    if (result.ok) python = result;
    else {
      return {
        ok: false,
        code: 'PYTHON_INVALID',
        message: `configured pythonPath failed the import check (${result.reason}). 若当前 Python 缺少 mcp/pywin32 依赖（或 DSH 内置 Python 已重置），请复制运行一键初始化命令创建插件隔离环境 / Run one-line setup to create an isolated .venv: ${setupCmd}`,
        notes,
      };
    }
  } else {
    const failures = [];
    let bootstrapAttempted = false;
    for (const candidate of entryCandidates(env, pluginRoot)) {
      let result = await _probePython(candidate);
      const allowAutoBootstrap = Boolean(config.autoBootstrap) || env.DSH_SOLIDWORKS_AUTO_BOOTSTRAP === '1';
      if (allowAutoBootstrap && !result.ok && result.reason && result.reason.includes('No module named')) {
        bootstrapAttempted = true;
        const bootstrapResult = tryAutoBootstrap(candidate, { pluginRoot, logger });
        if (bootstrapResult) {
          if (typeof bootstrapResult === 'object' && bootstrapResult.createdVenvPy) {
            const venvCandidate = { command: bootstrapResult.createdVenvPy, args: [], label: `isolated .venv: ${bootstrapResult.createdVenvPy}` };
            const venvProbe = await _probePython(venvCandidate);
            if (venvProbe.ok) {
              result = venvProbe;
              candidate.label = venvCandidate.label;
              candidate.command = venvCandidate.command;
              candidate.args = venvCandidate.args;
            }
          } else {
            result = await _probePython(candidate);
          }
        }
      }
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
        message: `未找到包含 'mcp' 与 'pywin32' 核心依赖的可用 Python 环境 (No Python environment with 'mcp' and 'pywin32' was found)。已排查候选: ${failures.join('; ')}。${bootstrapAttempted ? '已尝试自动自举修复但未完成，请检查本地网络' : `加载期默认禁止静默联网安装依赖；请复制运行一键初始化命令创建隔离运行环境（不影响系统 Python）/ Run this one-line command to set up an isolated .venv: ${setupCmd} ，或在 DSH 插件设置中手动指定已安装依赖的 pythonPath`}。`,
        notes,
      };
    }
  }

  notes.push(`python: ${python.command} ${python.args.join(' ')} [${python.version}]`);
  if (python.comDeps === false) {
    notes.push('警告：当前 Python 环境缺少可选 COM 依赖 (comtypes)；基础 pywin32 COM 可用，但 Motion 算例与类型库功能将受限（pip install "comtypes>=1.2.0"）。');
  }

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
  return { ok: true, python: { command: python.command, args: python.args, version: python.version, comDeps: python.comDeps !== false }, serverScript, serverCwd, notes };
}
