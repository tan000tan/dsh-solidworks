#!/usr/bin/env node
/**
 * scripts/generate_mcp_config.js
 *
 * 自动化生成适用于本机的标准 MCP (Model Context Protocol) 接入配置。
 * 遵循安全越权红线：仅在终端生成高亮格式展示供用户复制，绝不擅自越权篡改用户配置文件。
 */

import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import os from 'node:os';

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
    ? (() => { try { return JSON.parse(process.env.DSH_ALLOWED_ROOTS)[0]; } catch { return path.join(process.cwd(), 'cad_sandbox'); } })()
    : (existsSync(path.join(ROOT_DIR, '测试代码', 'sandbox_benchmark'))
        ? path.join(ROOT_DIR, '测试代码', 'sandbox_benchmark')
        : path.join(process.cwd(), 'cad_sandbox'));

  const hasVenv = Boolean(venvPython);
  const pythonCmd = venvPython || process.env.DSH_SOLIDWORKS_PYTHON || 'python';

  const mcpConfig = {
    mcpServers: {
      solidworks: {
        command: pythonCmd,
        args: [serverPy],
        env: {
          PYTHONUNBUFFERED: "1",
          PYTHONIOENCODING: "utf-8",
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

  console.log('请复制以下 JSON 配置代码段并粘贴到您的 MCP 客户端配置中');
  console.log('(如 DeepSeek Harness、Claude Desktop 或 Cursor MCP 设置)：\n');

  console.log('\x1b[36m---------------------- [MCP 配置代码段] ----------------------\x1b[0m');
  console.log(jsonStr);
  console.log('\x1b[36m--------------------------------------------------------------\x1b[0m\n');

  console.log('【安全与目录提示】');
  console.log(`• 默认安全写操作沙箱目录已绑定为:`);
  console.log(`  ${sandboxDir}`);
  console.log(`• 若需允许其他工作目录，可在 DSH_ALLOWED_ROOTS 环境变量 JSON 数组中追加。\n`);
}

main();
