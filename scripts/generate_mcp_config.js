#!/usr/bin/env node
/**
 * scripts/generate_mcp_config.js
 *
 * 自动化生成适用于本机的标准 MCP (Model Context Protocol) 接入配置。
 *
 * 行为（v0.3.1 Group D D-03 合并态；后续将在安全闭环中按 RT-SEC-02 核查）：
 *   1. 打印可直接复制的 JSON 配置段；
 *   2. 写入本插件目录下的 dsh-mcp-config.json，不触碰宿主 profile。
 */

import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { resolveSandboxDir } from './dsh_adapter.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.resolve(__dirname, '..');

function getVenvPythonPath() {
  const venvDir = path.join(ROOT_DIR, '.venv');
  const standardExe = process.platform === 'win32'
    ? path.join(venvDir, 'Scripts', 'python.exe')
    : path.join(venvDir, 'bin', 'python');

  if (existsSync(standardExe)) {
    return standardExe;
  }

  const cfgFile = path.join(venvDir, 'pyvenv.cfg');
  if (existsSync(cfgFile)) {
    try {
      const txt = readFileSync(cfgFile, 'utf8');
      const exeMatch = txt.match(/executable\s*=\s*(.+)/);
      if (exeMatch && existsSync(exeMatch[1].trim())) {
        return exeMatch[1].trim();
      }
    } catch {
      // ignore
    }
  }

  return null;
}

function main() {
  const venvPython = getVenvPythonPath();
  const serverPy = path.join(ROOT_DIR, 'vendor', 'solidworks-automation-skill', 'mcp-server', 'server.py');
  const sandboxDir = process.env.DSH_ALLOWED_ROOTS
    ? (() => { try { return JSON.parse(process.env.DSH_ALLOWED_ROOTS)[0]; } catch { return resolveSandboxDir(ROOT_DIR); } })()
    : resolveSandboxDir(ROOT_DIR);

  const hasVenv = Boolean(venvPython);
  const pythonCmd = venvPython || process.env.DSH_SOLIDWORKS_PYTHON || 'python';

  const mcpConfig = {
    mcpServers: {
      'solidworks-cad': {
        command: pythonCmd,
        args: [serverPy],
        env: {
          PYTHONUNBUFFERED: '1',
          PYTHONIOENCODING: 'utf-8',
          DSH_ALLOWED_ROOTS: JSON.stringify([sandboxDir]),
        },
      },
    },
  };

  const jsonStr = JSON.stringify(mcpConfig, null, 2);

  console.log('\n======================================================');
  console.log('   dsh-solidworks-plugin 标准 MCP 配置生成器   ');
  console.log('======================================================\n');

  if (!hasVenv) {
    console.log('\x1b[33m%s\x1b[0m', '⚠ 提示: 当前未检测到已创建的独立虚拟环境 (.venv)！');
    console.log('\x1b[33m%s\x1b[0m', '  建议先执行: npm run setup 完成环境自动化配置。\n');
  } else {
    console.log('\x1b[32m%s\x1b[0m', '✔ 已成功绑定独立虚拟环境: ' + venvPython);
  }

  const writeDirect = process.argv.includes('--write-direct-config');
  const outIdx = process.argv.indexOf('--out');
  const explicitOut = outIdx >= 0 && process.argv[outIdx + 1] ? path.resolve(process.argv[outIdx + 1]) : null;
  const targetPath = explicitOut || path.join(ROOT_DIR, 'dsh-mcp-config.json');

  if (writeDirect || explicitOut) {
    try {
      writeFileSync(targetPath, jsonStr + '\n', 'utf8');
      console.log('\x1b[33m%s\x1b[0m', `⚠ 已按显式请求写入直连配置文件: ${targetPath}`);
      console.log('\x1b[33m%s\x1b[0m', '  安全提醒: 直连 Python MCP 通道将绕过 DSH 插件的 JS 策略审批与审计链路，仅限受信任本地客户端使用。');
    } catch (err) {
      console.log('\x1b[33m%s\x1b[0m', `⚠ 无法写入 ${targetPath}: ${err.message}`);
      console.log('\x1b[33m%s\x1b[0m', '  （目录只读时属正常现象；请直接复制下面的 JSON 手动粘贴。）');
    }
  } else {
    console.log('\x1b[32m%s\x1b[0m', '✔ 安全默认: 未在插件根目录生成 dsh-mcp-config.json（避免形成绕过 JS 策略与审批的直连旁路）。');
    console.log('  如需为独立外部 MCP 客户端生成配置，请显式传入: npm run mcp-config -- --write-direct-config');
  }

  console.log('请复制以下 JSON 配置代码段并粘贴到您的 MCP 客户端配置中');
  console.log('(如 DeepSeek Harness、Claude Desktop 或 Cursor MCP 设置)：\n');

  console.log('\x1b[36m---------------------- [MCP 配置代码段] ----------------------\x1b[0m');
  console.log(jsonStr);
  console.log('\x1b[36m--------------------------------------------------------------\x1b[0m\n');

  console.log('【安全与目录提示】');
  console.log('• 默认安全写操作沙箱目录已绑定为:');
  console.log(`  ${sandboxDir}`);
  console.log('• 若需允许其他工作目录，可在 DSH_ALLOWED_ROOTS 环境变量 JSON 数组中追加。');
  console.log('• DSH 桌面端插件请用应用内的插件面板安装/启用，本文件仅供独立 MCP 客户端使用。\n');

  return 0;
}

process.exit(main());
