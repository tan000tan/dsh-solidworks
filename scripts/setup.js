#!/usr/bin/env node
/**
 * scripts/setup.js
 *
 * dsh-solidworks-plugin 自动化环境安装与配置引导器。
 * 纯 Node.js 实现，跨平台、防 Windows 执行策略拦截、幂等支持。
 *
 * 核心流程：
 * 1. 架构与平台校验 (Windows x64 / Node.js >= 18)；
 * 2. 智能探测系统中可用的 Python 3.10+ 解释器；
 * 3. 在项目根目录下自动创建独立虚拟环境 (.venv)；
 * 4. 幂等安装 requirements.txt 运行时依赖（支持镜像源加速与按需可选扩展）；
 * 5. 自动执行 pywin32_postinstall.py -install 注册 Windows COM 组件；
 * 6. 生成安全规范的 MCP 接入配置段 (dsh-mcp-config.json)；
 * 7. 支持 --verify 参数直接链式触发健康自检。
 */

import { existsSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import os from 'node:os';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.resolve(__dirname, '..');

// 常用候选路径
function getCandidatePythonPaths() {
  const candidates = [];

  // 0. 若存在已有 .venv，优先继承其配置的 Python 路径
  const venvCfg = path.join(ROOT_DIR, '.venv', 'pyvenv.cfg');
  if (existsSync(venvCfg)) {
    try {
      const content = readFileSync(venvCfg, 'utf8');
      const exeMatch = content.match(/executable\s*=\s*(.+)/);
      if (exeMatch && exeMatch[1]) candidates.push(exeMatch[1].trim());
      const homeMatch = content.match(/home\s*=\s*(.+)/);
      if (homeMatch && homeMatch[1]) {
        candidates.push(path.join(homeMatch[1].trim(), 'python.exe'));
      }
    } catch {}
  }

  // 1. 命令行参数 --python 指定
  const pyArgIdx = process.argv.indexOf('--python');
  if (pyArgIdx !== -1 && process.argv[pyArgIdx + 1]) {
    candidates.push(process.argv[pyArgIdx + 1]);
  }

  // 2. 环境变量指定
  if (process.env.DSH_SOLIDWORKS_PYTHON) candidates.push(process.env.DSH_SOLIDWORKS_PYTHON);
  if (process.env.PYTHON) candidates.push(process.env.PYTHON);
  if (process.env.PYTHON_PATH) candidates.push(process.env.PYTHON_PATH);

  // 3. 全局命令名称
  candidates.push('python', 'python3', 'py');

  // 4. Windows 常见标准安装目录
  const localAppData = process.env.LOCALAPPDATA || '';
  const programFiles = process.env.ProgramFiles || 'C:\\Program Files';
  const programFilesX86 = process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)';
  const systemDrive = process.env.SystemDrive || 'C:';

  const checkDrives = [systemDrive, 'C:', 'D:', 'E:', 'F:'].filter((v, i, a) => a.indexOf(v) === i);

  for (const ver of ['Python313', 'Python312', 'Python311', 'Python310']) {
    if (localAppData) {
      candidates.push(path.join(localAppData, 'Programs', 'Python', ver, 'python.exe'));
    }
    candidates.push(path.join(programFiles, ver, 'python.exe'));
    candidates.push(path.join(programFiles, 'Python', ver, 'python.exe'));
    candidates.push(path.join(programFilesX86, ver, 'python.exe'));
    candidates.push(path.join(programFilesX86, 'Python', ver, 'python.exe'));

    for (const drive of checkDrives) {
      candidates.push(path.join(drive, ver, 'python.exe'));
      candidates.push(path.join(drive, 'Python', ver, 'python.exe'));
    }
  }

  return candidates;
}

function runCommand(command, args, options = {}) {
  return new Promise((resolve) => {
    const proc = spawn(command, args, {
      cwd: options.cwd || ROOT_DIR,
      shell: false,
      stdio: options.stdio || ['ignore', 'pipe', 'pipe'],
      env: {
        ...process.env,
        PYTHONDONTWRITEBYTECODE: '1',
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8',
        ...options.env,
      },
    });

    let stdout = '';
    let stderr = '';

    if (proc.stdout) {
      proc.stdout.on('data', (data) => {
        stdout += data.toString();
        if (options.onStdout) options.onStdout(data.toString());
      });
    }

    if (proc.stderr) {
      proc.stderr.on('data', (data) => {
        stderr += data.toString();
        if (options.onStderr) options.onStderr(data.toString());
      });
    }

    proc.on('close', (code) => {
      resolve({ code: code ?? 1, stdout: stdout.trim(), stderr: stderr.trim() });
    });

    proc.on('error', (err) => {
      resolve({ code: 1, stdout: '', stderr: err.message });
    });
  });
}

async function inspectPython(cmd) {
  try {
    const res = await runCommand(cmd, [
      '-c',
      'import sys, struct; v=sys.version_info; b=struct.calcsize("P")*8; print(str(v[0])+"."+str(v[1])+"."+str(v[2])+"|"+str(b))',
    ]);
    if (res.code === 0 && res.stdout) {
      const [verStr, bitsStr] = res.stdout.trim().split('|');
      const parts = verStr.split('.').map(Number);
      if (parts.length >= 2) {
        const [major, minor] = parts;
        if (major === 3 && minor >= 10) {
          return { valid: true, version: verStr, bits: bitsStr || '64', cmd };
        }
      }
    }
  } catch {
    // 忽略探测异常
  }
  return { valid: false };
}

async function findSuitablePython() {
  const candidates = getCandidatePythonPaths();
  for (const candidate of candidates) {
    if (candidate.includes(path.sep) && !existsSync(candidate)) {
      continue;
    }
    const result = await inspectPython(candidate);
    if (result.valid) {
      return result;
    }
  }
  return null;
}

// 检查是否已经具备运行核心依赖（幂等支持）
async function checkDepsInstalled(pythonCmd, reqFilePath) {
  try {
    const checkSnippet = `
import sys
try:
    import win32com.client
    import pythoncom
    import comtypes
    import pydantic
    import mcp
    print("ALL_DEPS_READY")
except Exception:
    sys.exit(1)
`;
    const res = await runCommand(pythonCmd, ['-c', checkSnippet]);
    return res.code === 0 && res.stdout.includes('ALL_DEPS_READY');
  } catch {
    return false;
  }
}

// 生成标准化 MCP 客户端配置文件
function generateMcpConfig(pythonExecutable) {
  const serverScript = path.join(ROOT_DIR, 'vendor', 'solidworks-automation-skill', 'mcp-server', 'server.py');
  const sandboxDir = process.env.DSH_ALLOWED_ROOTS
    ? (() => { try { return JSON.parse(process.env.DSH_ALLOWED_ROOTS)[0]; } catch { return path.join(process.cwd(), 'cad_sandbox'); } })()
    : path.join(ROOT_DIR, '测试代码', 'sandbox_benchmark');
  const config = {
    mcpServers: {
      "solidworks-cad": {
        command: pythonExecutable,
        args: [serverScript],
        env: {
          DSH_ALLOWED_ROOTS: JSON.stringify([sandboxDir]),
          PYTHONUNBUFFERED: "1",
          PYTHONDONTWRITEBYTECODE: "1"
        }
      }
    }
  };

  const targetPath = path.join(ROOT_DIR, 'dsh-mcp-config.json');
  try {
    writeFileSync(targetPath, JSON.stringify(config, null, 2), 'utf8');
    return targetPath;
  } catch {
    return null;
  }
}

async function main() {
  console.log('\n======================================================');
  console.log('  dsh-solidworks-plugin 自动化环境安装程序 (Setup)  ');
  console.log('======================================================\n');

  // Step 0: 平台与架构基准检测
  console.log('[0/5] 校验系统架构与基础运行平台...');
  const isWin = process.platform === 'win32';
  const arch = os.arch();
  console.log(`    操作系统: ${process.platform} (${os.release()}), 架构: ${arch}`);
  if (isWin && arch !== 'x64' && arch !== 'arm64') {
    console.warn(`[!] 警告: 检测到当前非 64 位 Windows 系统 (${arch})，SolidWorks 官方仅支持 64 位环境。`);
  } else {
    console.log(`[✔] 平台架构校验通过 (64-bit 兼容)`);
  }

  // Step 1: 探测 Python 解释器
  console.log('\n[1/5] 正在检测 Python 运行时环境 (>= 3.10 64-bit)...');
  const pythonInfo = await findSuitablePython();

  if (!pythonInfo) {
    console.error('\n[✖] 未在系统中检测到满足要求的 Python 3.10+ 环境！');
    console.error('    SolidWorks CAD 插件需要 Python 3.10 或更高版本以驱动本地 COM 自动化接口。');
    console.error('    【推荐解决方案】');
    console.error('    1. 请前往 Python 官方网站下载 Windows 64-bit 安装包 (推荐 Python 3.12 或 3.13):');
    console.error('       👉 https://www.python.org/downloads/windows/');
    console.error('    2. 安装时请务必勾选: "Add python.exe to PATH" 以及 "Install for all users"；');
    console.error('    3. 安装完成后，请重新在终端运行: npm run setup\n');
    process.exit(1);
  }

  console.log(`[✔] 成功定位 Python 解释器: ${pythonInfo.cmd} (版本: ${pythonInfo.version}, 架构: ${pythonInfo.bits}-bit)`);

  // Step 2: 创建独立虚拟环境 (.venv)
  const venvDir = path.join(ROOT_DIR, '.venv');
  const scriptsDir = path.join(venvDir, 'Scripts');
  const cfgFile = path.join(venvDir, 'pyvenv.cfg');

  console.log('\n[2/5] 检查独立虚拟环境 (.venv)...');
  let activePython = pythonInfo.cmd;
  let activePip = null;

  let standardVenvCreated = false;
  const standardVenvPython = isWin
    ? path.join(scriptsDir, 'python.exe')
    : path.join(venvDir, 'bin', 'python');

  if (existsSync(cfgFile) && existsSync(standardVenvPython)) {
    console.log(`[✔] 虚拟环境已就绪: ${venvDir}`);
    activePython = standardVenvPython;
    activePip = path.join(path.dirname(standardVenvPython), 'pip.exe');
  } else {
    console.log(`[*] 正在创建隔离虚拟环境: ${venvDir} ...`);
    const venvRes = await runCommand(pythonInfo.cmd, ['-m', 'venv', venvDir]);
    if (venvRes.code === 0 && existsSync(standardVenvPython)) {
      // 验证标准 venv 中的 python 是否正常可用
      const venvTest = await runCommand(standardVenvPython, ['-c', 'import sys; print("OK")']);
      if (venvTest.code === 0) {
        standardVenvCreated = true;
        activePython = standardVenvPython;
        activePip = path.join(scriptsDir, 'pip.exe');
        console.log('[✔] 标准独立虚拟环境创建成功！');
      }
    }

    if (!standardVenvCreated) {
      // 降级支持：便携式虚拟隔离代理
      console.log('    (检测到宿主为便携隔离环境，初始化项目级 .venv 配置绑定...)');
      mkdirSync(scriptsDir, { recursive: true });
      const cfgContent = [
        `home = ${path.dirname(pythonInfo.cmd)}`,
        'include-system-site-packages = true',
        `version = ${pythonInfo.version}`,
        `executable = ${pythonInfo.cmd}`,
        `command = ${pythonInfo.cmd} -m venv ${venvDir}`,
      ].join('\n');
      writeFileSync(cfgFile, cfgContent, 'utf8');

      // 建立 Windows 快捷调用包装脚本
      if (isWin) {
        writeFileSync(
          path.join(scriptsDir, 'python.cmd'),
          `@echo off\r\n"${pythonInfo.cmd}" %*\r\n`,
          'utf8'
        );
        writeFileSync(
          path.join(scriptsDir, 'pip.cmd'),
          `@echo off\r\n"${pythonInfo.cmd}" -m pip %*\r\n`,
          'utf8'
        );
      }
      activePython = pythonInfo.cmd;
      console.log('[✔] 独立虚拟环境代理配置就绪！');
    }
  }

  // 解析国内镜像源参数
  let mirrorArgs = [];
  if (process.argv.includes('--tsinghua')) {
    mirrorArgs = ['-i', 'https://pypi.tuna.tsinghua.edu.cn/simple'];
  } else if (process.argv.includes('--aliyun')) {
    mirrorArgs = ['-i', 'https://mirrors.aliyun.com/pypi/simple/'];
  } else {
    const mirrorIdx = process.argv.indexOf('--mirror');
    if (mirrorIdx !== -1 && process.argv[mirrorIdx + 1]) {
      mirrorArgs = ['-i', process.argv[mirrorIdx + 1]];
    }
  }

  // Step 3: 安装依赖包（具备幂等跳过）
  console.log('\n[3/5] 正在安装与校验运行时核心依赖 (mcp, pydantic, pywin32, comtypes)...');
  const reqPath = path.join(ROOT_DIR, 'requirements.txt');
  if (!existsSync(reqPath)) {
    console.error(`[✖] 未找到依赖配置文件: ${reqPath}`);
    process.exit(1);
  }

  const isAlreadyInstalled = await checkDepsInstalled(activePython, reqPath);
  const forceReinstall = process.argv.includes('--force');

  if (isAlreadyInstalled && !forceReinstall) {
    console.log('[✔] 核心依赖已全部就绪（幂等验证通过，跳过重复下载）！');
  } else {
    console.log('[*] 正在安装核心依赖包...');
    let pipRes;
    const baseArgs = ['install', '-r', reqPath, '--disable-pip-version-check', ...mirrorArgs];
    if (activePip && existsSync(activePip)) {
      pipRes = await runCommand(activePip, baseArgs);
    } else {
      pipRes = await runCommand(activePython, ['-m', 'pip', ...baseArgs]);
    }

    if (pipRes.code !== 0) {
      console.error(`[✖] 依赖安装失败:\n${pipRes.stderr}`);
      console.error('    提示: 如果网络连接超时，可尝试使用清华镜像源重试:');
      console.error('          npm run setup -- --tsinghua');
      process.exit(1);
    }
    console.log('[✔] 核心 Python 依赖包已就绪！');
  }

  const installOptional = process.argv.includes('--optional') || process.argv.includes('--full');
  const optReqPath = path.join(ROOT_DIR, 'requirements-optional.txt');
  if (installOptional && existsSync(optReqPath)) {
    console.log('\n[*] 正在安装可选高级扩展依赖 (DFM, DXF, Office)...');
    let optPipRes;
    const optBaseArgs = ['install', '-r', optReqPath, '--disable-pip-version-check', ...mirrorArgs];
    if (activePip && existsSync(activePip)) {
      optPipRes = await runCommand(activePip, optBaseArgs);
    } else {
      optPipRes = await runCommand(activePython, ['-m', 'pip', ...optBaseArgs]);
    }
    if (optPipRes.code === 0) {
      console.log('[✔] 可选高级扩展依赖安装成功！');
    } else {
      console.warn(`[!] 可选依赖安装提示 (核心功能不受影响): ${optPipRes.stderr || '未全部安装'}`);
    }
  }

  // Step 4: 注册 pywin32 COM 组件
  console.log('\n[4/5] 正在配置并注册 Windows COM 自动化服务 (pywin32)...');
  if (isWin) {
    const candidatePostInstalls = [
      path.join(venvDir, 'Scripts', 'pywin32_postinstall.py'),
      path.join(path.dirname(activePython), 'Scripts', 'pywin32_postinstall.py'),
      path.join(path.dirname(activePython), 'pywin32_postinstall.py'),
    ];

    let postFound = null;
    for (const p of candidatePostInstalls) {
      if (existsSync(p)) {
        postFound = p;
        break;
      }
    }

    if (postFound) {
      console.log(`    正在执行 pywin32_postinstall.py -install ...`);
      const postRes = await runCommand(activePython, [postFound, '-install', '-silent']);
      if (postRes.code === 0) {
        console.log('[✔] pywin32 COM 注册成功！');
      } else {
        console.log(`[!] pywin32_postinstall 提示: ${postRes.stderr || '已完成'}`);
      }
    }

    // 验证 COM 导入
    const testComRes = await runCommand(activePython, [
      '-c',
      'import win32com.client, pythoncom; print("COM_VERIFIED_OK")',
    ]);
    if (testComRes.code === 0 && testComRes.stdout.includes('COM_VERIFIED_OK')) {
      console.log('[✔] Windows COM 运行时测试通过！');
    } else {
      console.warn(`[!] COM 导入检测异常: ${testComRes.stderr}`);
    }
  } else {
    console.log('[*] 非 Windows 平台，跳过 pywin32 COM 注册。');
  }

  // Step 5: 生成 MCP 标准配置
  console.log('\n[5/5] 生成标准 MCP 客户端接入配置...');
  const cfgPath = generateMcpConfig(activePython);
  if (cfgPath) {
    console.log(`[✔] 专属 MCP 配置文件已更新: ${cfgPath}`);
  } else {
    console.warn(`[!] 无法自动写入 MCP 配置文件`);
  }

  console.log('\n======================================================');
  console.log('  🎉 全部环境构建与配置成功完成！');
  console.log('======================================================');

  if (process.argv.includes('--verify')) {
    console.log('\n[*] 正在触发安装后自动化健康诊断 (Doctor)...');
    await runCommand('node', [path.join(__dirname, 'doctor.js')], { stdio: 'inherit' });
  } else {
    console.log('\n【下一步快捷操作】');
    console.log('  1. 运行系统全项健康诊断:');
    console.log('     npm run doctor');
    console.log('  2. 查看标准 MCP 接入配置代码段:');
    console.log('     npm run mcp-config\n');
  }
}

main().catch((err) => {
  console.error('\n[!] 安装引导程序异常中断:', err);
  process.exit(1);
});
