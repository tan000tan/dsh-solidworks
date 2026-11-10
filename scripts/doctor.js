#!/usr/bin/env node
/**
 * scripts/doctor.js
 *
 * dsh-solidworks-plugin 全生命周期健康诊断系统 (Doctor)。
 * 纯 Node.js 驱动，支持 8 大核心维度自动化探测：
 * 1. OS_PLATFORM_ARCH       操作系统平台与 Node.js 运行时合规性
 * 2. PYTHON_RUNTIME         Python 解释器版本与虚拟环境合法性
 * 3. COM_DEPENDENCIES       Windows COM 底层接口与 pywin32 注册状态
 * 4. OPTIONAL_EXTENSIONS    DFM / DXF / Office 制造扩展依赖按需状态
 * 5. SOLIDWORKS_REGISTRY    SolidWorks 本地安装、ProgID 与主程序探测
 * 6. STA_DESKTOP_PERM       Windows Default 桌面访问与 STA 调度线程权限
 * 7. SANDBOX_ROOTS_VALIDITY 读写沙箱物理目录存在性与读写权限
 * 8. LIVE_COM_ECHO          SolidWorks 进程与 COM 接口在线回响探测
 */

import { existsSync, mkdirSync, accessSync, constants, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import os from 'node:os';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.resolve(__dirname, '..');

const C = {
  reset: '\x1b[0m',
  bold: '\x1b[1m',
  green: '\x1b[32m',
  red: '\x1b[31m',
  yellow: '\x1b[33m',
  cyan: '\x1b[36m',
  gray: '\x1b[90m',
};

function runPythonSnippet(pythonCmd, snippet, extraEnv = {}) {
  return new Promise((resolve) => {
    const proc = spawn(pythonCmd, ['-B', '-c', snippet], {
      cwd: ROOT_DIR,
      shell: false,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: {
        ...process.env,
        PYTHONDONTWRITEBYTECODE: '1',
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8',
        ...extraEnv,
      },
    });

    let stdout = '';
    let stderr = '';

    proc.stdout.on('data', (d) => { stdout += d.toString(); });
    proc.stderr.on('data', (d) => { stderr += d.toString(); });

    proc.on('close', (code) => {
      resolve({ code: code ?? 1, stdout: stdout.trim(), stderr: stderr.trim() });
    });

    proc.on('error', (err) => {
      resolve({ code: 1, stdout: '', stderr: err.message });
    });
  });
}

async function getUsablePython() {
  const venvDir = path.join(ROOT_DIR, '.venv');
  const venvPython = process.platform === 'win32'
    ? path.join(venvDir, 'Scripts', 'python.exe')
    : path.join(venvDir, 'bin', 'python');

  if (existsSync(venvPython)) {
    return { cmd: venvPython, isVenv: true };
  }

  const cfgFile = path.join(venvDir, 'pyvenv.cfg');
  if (existsSync(cfgFile)) {
    try {
      const txt = readFileSync(cfgFile, 'utf8');
      const exeMatch = txt.match(/executable\s*=\s*(.+)/);
      if (exeMatch && existsSync(exeMatch[1].trim())) {
        return { cmd: exeMatch[1].trim(), isVenv: true };
      }
      const homeMatch = txt.match(/home\s*=\s*(.+)/);
      if (homeMatch) {
        const homePy = path.join(homeMatch[1].trim(), 'python.exe');
        if (existsSync(homePy)) {
          return { cmd: homePy, isVenv: true };
        }
      }
    } catch {
      // ignore
    }
  }

  // 检查常用路径与环境变量
  const candidates = [];
  if (process.env.DSH_SOLIDWORKS_PYTHON) candidates.push(process.env.DSH_SOLIDWORKS_PYTHON);
  if (process.env.PYTHON) candidates.push(process.env.PYTHON);
  if (process.env.PYTHON_PATH) candidates.push(process.env.PYTHON_PATH);
  candidates.push('python', 'python3', 'py');

  const localAppData = process.env.LOCALAPPDATA || '';
  const programFiles = process.env.ProgramFiles || 'C:\\Program Files';
  const systemDrive = process.env.SystemDrive || 'C:';
  const checkDrives = [systemDrive, 'C:', 'D:', 'E:', 'F:'].filter((v, i, a) => a.indexOf(v) === i);

  for (const ver of ['Python313', 'Python312', 'Python311', 'Python310']) {
    if (localAppData) {
      candidates.push(path.join(localAppData, 'Programs', 'Python', ver, 'python.exe'));
    }
    candidates.push(path.join(programFiles, ver, 'python.exe'));
    candidates.push(path.join(programFiles, 'Python', ver, 'python.exe'));
    for (const drive of checkDrives) {
      candidates.push(path.join(drive, ver, 'python.exe'));
      candidates.push(path.join(drive, 'Python', ver, 'python.exe'));
    }
  }

  for (const c of candidates) {
    if (c.includes(path.sep) && !existsSync(c)) {
      continue;
    }
    try {
      const res = await runPythonSnippet(c, 'import sys; print("OK")');
      if (res.code === 0 && res.stdout.includes('OK')) {
        return { cmd: c, isVenv: false };
      }
    } catch {
      // ignore
    }
  }

  return null;
}

async function main() {
  console.log('\n======================================================');
  console.log('   dsh-solidworks-plugin 系统全项健康诊断 (Doctor)   ');
  console.log('======================================================\n');

  const report = [];
  let failCount = 0;
  let warnCount = 0;

  function record(name, level, summary, details = null, howToFix = null) {
    // level: 'PASS' | 'WARN' | 'FAIL'
    if (level === 'FAIL') failCount++;
    if (level === 'WARN') warnCount++;
    report.push({ name, level, summary, details, howToFix });

    let mark = `${C.green}✔ PASS${C.reset}`;
    if (level === 'WARN') mark = `${C.yellow}⚠ WARN${C.reset}`;
    if (level === 'FAIL') mark = `${C.red}✖ FAIL${C.reset}`;

    console.log(`[${mark}] ${C.bold}${name}${C.reset}: ${summary}`);
    if (details) {
      console.log(`       ${C.gray}${details}${C.reset}`);
    }
    if (level !== 'PASS' && howToFix) {
      console.log(`       ${C.cyan}👉 修复建议 (Recommendation): ${howToFix}${C.reset}`);
    }
  }

  // ---------------------------------------------------------
  // 1. OS_PLATFORM_ARCH
  // ---------------------------------------------------------
  const isWin = process.platform === 'win32';
  const arch = os.arch();
  const nodeVer = process.version;
  const nodeMajor = parseInt(nodeVer.slice(1).split('.')[0], 10);

  if (isWin && arch === 'x64' && nodeMajor >= 18) {
    record('OS_PLATFORM_ARCH', 'PASS', `Windows x64 与 Node.js ${nodeVer} 环境合规`, `系统: Windows ${os.release()} (${arch}), Node: ${nodeVer}`);
  } else if (!isWin) {
    record('OS_PLATFORM_ARCH', 'WARN', `非 Windows 操作系统 (${process.platform})`, 'SolidWorks 桌面版仅运行于 Windows，非 Windows 仅可进行离线规则审计与 Mock 调试');
  } else if (arch !== 'x64') {
    record('OS_PLATFORM_ARCH', 'FAIL', `不支持的架构: ${arch}`, 'SolidWorks COM 自动化驱动需要 64 位 x64 环境', '请在 64 位 Windows 机器上运行本插件。');
  } else {
    record('OS_PLATFORM_ARCH', 'WARN', `Node.js 版本较低 (${nodeVer})`, '推荐 Node.js >= 18.0.0 以获得完整的 AbortSignal 和异步事件支持', '建议升级 Node.js 至 LTS 版本。');
  }

  // ---------------------------------------------------------
  // 2. PYTHON_RUNTIME
  // ---------------------------------------------------------
  const py = await getUsablePython();
  if (!py) {
    record(
      'PYTHON_RUNTIME',
      'FAIL',
      '未检测到可用的 Python 运行时',
      '在 .venv 及系统 PATH 中均未找到 Python 3.10+ 解释器',
      '请在终端运行 "npm run setup" 自动构建独立虚拟环境；或手动安装 64位 Python 3.10+。'
    );
  } else {
    const verRes = await runPythonSnippet(
      py.cmd,
      'import sys; v=sys.version_info; print(f"{v.major}.{v.minor}.{v.micro}")'
    );
    const verStr = verRes.stdout || 'unknown';
    const parts = verStr.split('.').map(Number);
    const isValidVer = parts[0] === 3 && parts[1] >= 10;

    if (isValidVer) {
      record(
        'PYTHON_RUNTIME',
        'PASS',
        `Python ${verStr} (${py.isVenv ? '独立虚拟环境 .venv' : '宿主环境'})`,
        `路径: ${py.cmd}`
      );
    } else {
      record(
        'PYTHON_RUNTIME',
        'FAIL',
        `Python 版本不满足要求 (${verStr})`,
        `必须为 Python 3.10 或更高版本`,
        '请下载安装 Python 3.12 或 3.13: https://www.python.org/downloads/windows/'
      );
    }
  }

  // ---------------------------------------------------------
  // 3. COM_DEPENDENCIES
  // ---------------------------------------------------------
  if (!py) {
    record('COM_DEPENDENCIES', 'FAIL', '跳过 (依赖 Python 解释器)', null, '修复 PYTHON_RUNTIME 后重新运行。');
  } else {
    const comRes = await runPythonSnippet(
      py.cmd,
      `
import sys
try:
    import win32com.client
    import pythoncom
    import comtypes
    import pydantic
    import mcp
    print("ALL_COM_DEPS_READY")
except Exception as e:
    print(f"ERR:{e}")
`
    );
    if (comRes.code === 0 && comRes.stdout.includes('ALL_COM_DEPS_READY')) {
      record('COM_DEPENDENCIES', 'PASS', 'Windows COM 与 MCP 核心依赖已全部就绪', 'win32com, pythoncom, comtypes, pydantic, mcp 校验通过');
    } else {
      record(
        'COM_DEPENDENCIES',
        'FAIL',
        '缺少 COM 或 MCP 必要依赖',
        comRes.stdout || comRes.stderr,
        '请在终端运行: npm run setup 进行自动化补全与 COM 注册。'
      );
    }

    // 可选扩展依赖探测 (DFM, DXF, 制造分析)
    const optRes = await runPythonSnippet(
      py.cmd,
      `
modules = ['ezdxf', 'numpy', 'PIL', 'openpyxl', 'docx', 'pptx']
present = []
missing = []
for m in modules:
    try:
        __import__(m)
        present.append(m)
    except ImportError:
        missing.append(m)
print(f"PRESENT:{','.join(present)}|MISSING:{','.join(missing)}")
`
    );
    if (optRes.code === 0 && optRes.stdout.includes('PRESENT:')) {
      const match = optRes.stdout.match(/PRESENT:(.*?)\|MISSING:(.*)/);
      const missingList = match && match[2] ? match[2].split(',').filter(Boolean) : [];
      if (missingList.length === 0) {
        record('OPTIONAL_EXTENSIONS', 'PASS', '高级扩展依赖已全部就绪', 'DFM、DXF、Office 报表族扩展可用');
      } else {
        record(
          'OPTIONAL_EXTENSIONS',
          'PASS',
          `核心不受影响；按需扩展包未安装 (${missingList.join(', ')})`,
          '提示：如需使用 DFM 制造报表或 DXF 轮廓解析，可运行 "npm run setup -- --optional"',
          null
        );
      }
    }
  }

  // ---------------------------------------------------------
  // 4. SOLIDWORKS_REGISTRY
  // ---------------------------------------------------------
  if (!py) {
    record('SOLIDWORKS_REGISTRY', 'FAIL', '跳过 (依赖 Python 解释器)');
  } else {
    const swRegRes = await runPythonSnippet(
      py.cmd,
      `
import sys, json
sys.path.insert(0, "vendor/solidworks-automation-skill/scripts")
try:
    from sw_preflight import discover_installation
    info = discover_installation("solidworks")
    print("SW_INFO:" + json.dumps(info))
except Exception as e:
    print(f"ERR:{e}")
`
    );
    let swInfo = null;
    if (swRegRes.stdout.includes('SW_INFO:')) {
      try {
        const line = swRegRes.stdout.split('SW_INFO:')[1].trim();
        swInfo = JSON.parse(line);
      } catch {
        // ignore
      }
    }

    if (swInfo && swInfo.installed) {
      record(
        'SOLIDWORKS_REGISTRY',
        'PASS',
        `已检测到 ${swInfo.displayName || 'SolidWorks'}`,
        `程序路径: ${swInfo.executable} (COM 已注册: ${swInfo.registered})`
      );
    } else {
      record(
        'SOLIDWORKS_REGISTRY',
        'FAIL',
        '系统未检测到 SolidWorks 安装或 COM 注册表缺失',
        swRegRes.stderr || '注册表中未找到 SldWorks.Application 键值',
        '请确认本地已安装 SolidWorks 桌面版，并至少启动过一次以完成 Windows COM 注册。'
      );
    }
  }

  // ---------------------------------------------------------
  // 5. STA_DESKTOP_PERM
  // ---------------------------------------------------------
  if (!py) {
    record('STA_DESKTOP_PERM', 'FAIL', '跳过 (依赖 Python 解释器)');
  } else {
    const staRes = await runPythonSnippet(
      py.cmd,
      `
import sys
sys.path.insert(0, "vendor/solidworks-automation-skill/scripts")
try:
    from sw_connect import get_sta_worker
    worker = get_sta_worker()
    ans = worker.execute(lambda: 42 * 2)
    if ans == 84:
        print("STA_WORKER_OK")
except Exception as e:
    print(f"ERR:{e}")
`
    );
    if (staRes.code === 0 && staRes.stdout.includes('STA_WORKER_OK')) {
      record('STA_DESKTOP_PERM', 'PASS', 'Windows Default 桌面访问与 STA 工作线程权限正常', '跨线程 STA 消息队列调度与安全重入锁校验通过');
    } else {
      record(
        'STA_DESKTOP_PERM',
        'FAIL',
        'STA 桌面工作线程调度异常',
        staRes.stderr || staRes.stdout,
        '请确认当前处于 Windows 交互式图形桌面会话，避免在非交互式系统服务或远程无头会话中运行。'
      );
    }
  }

  // ---------------------------------------------------------
  // 6. SANDBOX_ROOTS_VALIDITY
  // ---------------------------------------------------------
  const defaultSandbox = process.env.DSH_ALLOWED_ROOTS
    ? (() => { try { return JSON.parse(process.env.DSH_ALLOWED_ROOTS)[0]; } catch { return path.join(process.cwd(), 'cad_sandbox'); } })()
    : path.join(ROOT_DIR, '测试代码', 'sandbox_benchmark');
  let sandboxOk = false;
  let sandboxMsg = '';
  try {
    if (!existsSync(defaultSandbox)) {
      mkdirSync(defaultSandbox, { recursive: true });
    }
    accessSync(defaultSandbox, constants.R_OK | constants.W_OK);
    sandboxOk = true;
    sandboxMsg = `物理沙箱已就绪且可读写: ${defaultSandbox}`;
  } catch (err) {
    sandboxMsg = `沙箱路径不可写: ${err.message}`;
  }

  if (sandboxOk) {
    record('SANDBOX_ROOTS_VALIDITY', 'PASS', '工作区读写沙箱物理目录校验通过', sandboxMsg);
  } else {
    record(
      'SANDBOX_ROOTS_VALIDITY',
      'FAIL',
      '读写沙箱目录不可用',
      sandboxMsg,
      `请检查目录权限或赋予当前用户对 ${defaultSandbox} 的完全读写控制。`
    );
  }

  // ---------------------------------------------------------
  // 7. MCP_CONFIG_VALIDITY
  // ---------------------------------------------------------
  const mcpConfigFile = path.join(ROOT_DIR, 'dsh-mcp-config.json');
  if (existsSync(mcpConfigFile)) {
    try {
      const cfgObj = JSON.parse(readFileSync(mcpConfigFile, 'utf8'));
      if (cfgObj.mcpServers && cfgObj.mcpServers['solidworks-cad']) {
        record('MCP_CONFIG_VALIDITY', 'PASS', 'MCP 客户端配置文件格式合规', `文件: ${mcpConfigFile}`);
      } else {
        record('MCP_CONFIG_VALIDITY', 'WARN', 'MCP 配置文件存在但结构不完整', '缺少 solidworks-cad 服务定义', '运行 npm run mcp-config 重新生成。');
      }
    } catch (e) {
      record('MCP_CONFIG_VALIDITY', 'WARN', 'MCP 配置文件 JSON 语法损坏', e.message, '运行 npm run mcp-config 重新生成。');
    }
  } else {
    record('MCP_CONFIG_VALIDITY', 'WARN', '未生成 dsh-mcp-config.json', '尚无开箱即用的配置文件', '建议运行 npm run setup 或 npm run mcp-config 自动生成。');
  }

  // ---------------------------------------------------------
  // 8. LIVE_COM_ECHO
  // ---------------------------------------------------------
  if (!py) {
    record('LIVE_COM_ECHO', 'FAIL', '跳过 (依赖 Python 解释器)');
  } else {
    const echoRes = await runPythonSnippet(
      py.cmd,
      `
import sys, json
sys.path.insert(0, "vendor/solidworks-automation-skill/scripts")
try:
    from sw_connect import solidworks_processes, connect_solidworks, get_com_member
    procs = solidworks_processes()
    if not procs:
        print("ECHO:STANDBY")
    else:
        sw, model = connect_solidworks(wait_seconds=5, visible=False)
        rev = get_com_member(sw, "RevisionNumber")
        print(f"ECHO:RUNNING:{rev}")
except Exception as e:
    print(f"ERR:{e}")
`
    );

    if (echoRes.stdout.includes('ECHO:RUNNING:')) {
      const rev = echoRes.stdout.split('ECHO:RUNNING:')[1].trim();
      record('LIVE_COM_ECHO', 'PASS', `SolidWorks 正在运行，COM 实时心跳响应正常`, `当前版本修订号: ${rev}`);
    } else if (echoRes.stdout.includes('ECHO:STANDBY')) {
      record('LIVE_COM_ECHO', 'PASS', 'SolidWorks 当前处于待机状态 (Standby - 就绪)', '后台无运行中进程，首次 MCP 工具调用时将自动静默拉起');
    } else {
      record(
        'LIVE_COM_ECHO',
        'WARN',
        'COM 心跳探测响应超时或未就绪',
        echoRes.stdout || echoRes.stderr,
        '若 SolidWorks 窗口弹出对话框阻塞，请手动处理；首次调用时亦会自动重试。'
      );
    }
  }

  // ---------------------------------------------------------
  // 总结输出
  // ---------------------------------------------------------
  console.log('\n======================================================');
  if (failCount === 0) {
    const warnSuffix = warnCount > 0 ? ` (存在 ${warnCount} 项轻量提醒)` : '！系统状态极佳！';
    console.log(`  ${C.green}🎉 系统健康诊断完成: 0 项阻塞错误${warnSuffix}${C.reset}`);
    console.log('======================================================\n');
    console.log('【提示】随时运行 "npm run mcp-config" 即可获取本机专属 MCP 客户端接入配置。');
  } else {
    console.log(`  ${C.red}✖ 检测到 ${failCount} 项阻塞故障，请参考上述建议进行修复。${C.reset}`);
    console.log('======================================================\n');
    process.exit(1);
  }
}

main().catch((err) => {
  console.error('\n[!] Doctor 诊断工具执行异常:', err);
  process.exit(1);
});
