/**
 * scripts/run_clean_environment_sandbox_test.js
 *
 * 第四阶段：干净/隔离环境安装、自配置与生命周期验收脚本。
 * 在独立沙箱目录中，脱离当前工作区的局部状态和开发者环境变量，
 * 验证普通用户获取安装包后的真实安装、自检与卸载体验。
 */

import { existsSync, mkdirSync, rmSync, cpSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import os from 'node:os';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.resolve(__dirname, '..');

// 隔离沙箱根目录
const SANDBOX_ROOT = path.join(os.tmpdir(), 'dsh_solidworks_clean_test_sandbox');
const DIST_DIR = path.join(SANDBOX_ROOT, 'dsh-solidworks');

function runProc(cmd, args, options = {}) {
  return new Promise((resolve) => {
    const cleanEnv = { ...process.env, ...options.cleanEnv };
    delete cleanEnv.DSH_SOLIDWORKS_PYTHON;
    delete cleanEnv.DSH_SOLIDWORKS_SERVER;
    delete cleanEnv.DSH_ALLOWED_ROOTS;
    delete cleanEnv.PYTHONPATH;

    const proc = spawn(cmd, args, {
      cwd: options.cwd || DIST_DIR,
      shell: false,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: cleanEnv,
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

async function main() {
  console.log('\n======================================================');
  console.log('   干净 / 隔离环境真实安装部署与自检测试 (Phase 4)   ');
  console.log('======================================================\n');

  console.log(`[*] 隔离沙箱路径: ${DIST_DIR}`);
  if (existsSync(SANDBOX_ROOT)) {
    rmSync(SANDBOX_ROOT, { recursive: true, force: true });
  }
  mkdirSync(DIST_DIR, { recursive: true });

  // 1. 复制分发白名单文件到隔离目录
  console.log('[1/4] 部署纯净产品分发文件...');
  const pkg = JSON.parse(readFileSync(path.join(ROOT_DIR, 'package.json'), 'utf8'));
  const allowlist = pkg.files || [];

  for (const item of allowlist) {
    const src = path.join(ROOT_DIR, item);
    const dest = path.join(DIST_DIR, item);
    if (existsSync(src)) {
      cpSync(src, dest, { recursive: true });
    }
  }

  // 复制 package.json, dsh-plugin.json, 批处理入口
  for (const extra of ['package.json', 'dsh-plugin.json', 'install.bat', 'doctor.bat', 'upgrade.bat', 'uninstall.bat']) {
    const src = path.join(ROOT_DIR, extra);
    if (existsSync(src)) {
      cpSync(src, path.join(DIST_DIR, extra), { recursive: true });
    }
  }

  console.log('[✔] 纯净分发包已成功构建并部署到隔离目录！');

  // 2. 在完全隔离环境下执行 setup.js
  console.log('\n[2/4] 在无任何开发者环境变量的隔离环境中运行安装向导...');
  const setupRes = await runProc('node', [path.join(DIST_DIR, 'scripts', 'setup.js')]);
  console.log(setupRes.stdout);
  if (setupRes.code !== 0) {
    console.error(`[✖] 隔离环境 setup 执行失败: ${setupRes.stderr}`);
    process.exit(1);
  }
  console.log('[✔] 隔离环境自动化安装配置完成！');

  // 3. 在隔离环境中运行 doctor.js
  console.log('\n[3/4] 在隔离环境中执行健康体检 (doctor)...');
  const doctorRes = await runProc('node', [path.join(DIST_DIR, 'scripts', 'doctor.js')]);
  console.log(doctorRes.stdout);
  if (doctorRes.code !== 0) {
    console.error(`[✖] 隔离环境 doctor 执行失败: ${doctorRes.stderr}`);
    process.exit(1);
  }
  console.log('[✔] 隔离环境健康自检通过 (100% PASS)！');

  // 4. 在隔离环境中执行 uninstall.js
  console.log('\n[4/4] 在隔离环境中验证安全卸载与残留清理...');
  const uninstallRes = await runProc('node', [path.join(DIST_DIR, 'scripts', 'uninstall.js'), '--yes']);
  console.log(uninstallRes.stdout);
  if (uninstallRes.code !== 0) {
    console.error(`[✖] 隔离环境卸载失败: ${uninstallRes.stderr}`);
    process.exit(1);
  }

  // 检查残留
  const venvLeft = existsSync(path.join(DIST_DIR, '.venv'));
  const mcpCfgLeft = existsSync(path.join(DIST_DIR, 'dsh-mcp-config.json'));
  if (venvLeft || mcpCfgLeft) {
    console.error(`[✖] 卸载后发现残留: .venv=${venvLeft}, mcp-config=${mcpCfgLeft}`);
    process.exit(1);
  }
  console.log('[✔] 卸载后零临时残留校验通过！');

  // 清理沙箱
  try {
    rmSync(SANDBOX_ROOT, { recursive: true, force: true });
  } catch {}

  console.log('\n======================================================');
  console.log('  🎉 第四阶段干净/隔离环境安装与生命周期验收全部通过！');
  console.log('======================================================\n');
}

main().catch((err) => {
  console.error('[!] 隔离环境验收异常:', err);
  process.exit(1);
});
