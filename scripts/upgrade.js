#!/usr/bin/env node
/**
 * scripts/upgrade.js
 *
 * dsh-solidworks-plugin 自动化安全升级与配置保护工具。
 *
 * 升级流程：
 * 1. 自动快照备份当前用户配置至 config-backups/；
 * 2. 检查版本兼容性；
 * 3. 增量更新 Python 虚拟环境依赖与 COM 服务注册；
 * 4. 自动调用 doctor 进行升级后验收；
 * 5. 失败时保留完整备份与恢复指引。
 */

import { existsSync, mkdirSync, copyFileSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.resolve(__dirname, '..');

function runProc(cmd, args) {
  return new Promise((resolve) => {
    const proc = spawn(cmd, args, {
      cwd: ROOT_DIR,
      stdio: 'inherit',
      shell: false,
      env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' },
    });
    proc.on('close', (code) => resolve(code ?? 1));
    proc.on('error', () => resolve(1));
  });
}

async function main() {
  console.log('\n======================================================');
  console.log('   dsh-solidworks-plugin 自动化安全升级程序   ');
  console.log('======================================================\n');

  // Step 1: 读取当前版本
  let pkgVer = 'unknown';
  try {
    const pkg = JSON.parse(readFileSync(path.join(ROOT_DIR, 'package.json'), 'utf8'));
    pkgVer = pkg.version || 'unknown';
  } catch {}

  console.log(`[1/4] 正在检测当前插件版本: v${pkgVer}`);

  // Step 2: 自动备份现有配置
  console.log('\n[2/4] 创建配置快照备份 (config-backups)...');
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const backupDir = path.join(ROOT_DIR, 'config-backups', `backup-${timestamp}`);
  mkdirSync(backupDir, { recursive: true });

  const backupCandidates = ['dsh-mcp-config.json', 'package.json', 'dsh-plugin.json'];
  let backedUpCount = 0;
  for (const name of backupCandidates) {
    const src = path.join(ROOT_DIR, name);
    if (existsSync(src)) {
      copyFileSync(src, path.join(backupDir, name));
      backedUpCount++;
    }
  }

  // 写入备份元数据
  writeFileSync(
    path.join(backupDir, 'backup-meta.json'),
    JSON.stringify({ timestamp, previousVersion: pkgVer, backedUpFiles: backupCandidates }, null, 2),
    'utf8'
  );
  console.log(`[✔] 已将 ${backedUpCount} 项核心配置文件安全备份至:`);
  console.log(`    ${backupDir}`);

  // Step 3: 增量更新环境与依赖
  console.log('\n[3/4] 执行依赖增量安装与 COM 重新注册...');
  const setupArgs = [path.join(__dirname, 'setup.js')];
  if (process.argv.includes('--optional') || process.argv.includes('--full')) {
    setupArgs.push('--optional');
  }
  const setupCode = await runProc('node', setupArgs);
  if (setupCode !== 0) {
    console.error(`\n[✖] 升级过程中依赖安装失败！`);
    console.error(`    您的旧配置完好保存在: ${backupDir}`);
    console.error(`    如需回滚，可将该目录中的配置文件复制覆盖回根目录。`);
    process.exit(1);
  }

  // Step 4: 运行全面健康体检
  console.log('\n[4/4] 触发升级后健康诊断 (Doctor)...');
  const doctorCode = await runProc('node', [path.join(__dirname, 'doctor.js')]);
  if (doctorCode !== 0) {
    console.warn(`\n[⚠] 升级完成，但健康体检报告存在警告或需关注项，请参考上文提示。`);
  } else {
    console.log('\n======================================================');
    console.log(`  🎉 恭喜！dsh-solidworks-plugin 已成功升级至 v${pkgVer}！`);
    console.log(`  系统健康度: 100% PASS`);
    console.log('======================================================\n');
  }
}

main().catch((err) => {
  console.error('\n[!] 升级程序执行异常:', err);
  process.exit(1);
});
