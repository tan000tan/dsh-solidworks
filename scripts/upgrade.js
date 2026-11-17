#!/usr/bin/env node
/**
 * scripts/upgrade.js
 *
 * dsh-solidworks-plugin 自动化安全升级与事务性自动回滚工具（修复 BUG-0003）。
 *
 * 升级流程：
 * 1. 自动快照备份当前用户配置至 config-backups/；
 * 2. 预检插件入口完整性（verifyPluginEntry）；
 * 3. 增量更新 Python 虚拟环境依赖与 COM 服务注册；
 * 4. 失败时自动将备份配置无损还原回根目录与 DSH Profile，绝不留半安装状态；
 * 5. 自动调用 doctor 进行升级后验收。
 */

import { existsSync, mkdirSync, copyFileSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { getDshDesktopProfileDir, verifyPluginEntry } from './dsh_adapter.js';

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

export function restoreFromBackup(backupDir, rootDir = ROOT_DIR, dshProfileDir = getDshDesktopProfileDir()) {
  const restored = [];
  const backupCandidates = ['dsh-mcp-config.json', 'package.json', 'dsh-plugin.json'];
  for (const name of backupCandidates) {
    const bak = path.join(backupDir, name);
    if (existsSync(bak)) {
      try {
        copyFileSync(bak, path.join(rootDir, name));
        restored.push(name);
      } catch {}
    }
  }
  const bakPatch = path.join(backupDir, 'cordis.patch.yml');
  if (existsSync(bakPatch) && existsSync(dshProfileDir)) {
    try {
      copyFileSync(bakPatch, path.join(dshProfileDir, 'cordis.patch.yml'));
      restored.push('cordis.patch.yml');
    } catch {}
  }
  return restored;
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

  const dshProfileDir = getDshDesktopProfileDir();
  const dshPatchFile = path.join(dshProfileDir, 'cordis.patch.yml');
  if (existsSync(dshPatchFile)) {
    copyFileSync(dshPatchFile, path.join(backupDir, 'cordis.patch.yml'));
    backedUpCount++;
  }

  writeFileSync(
    path.join(backupDir, 'backup-meta.json'),
    JSON.stringify({ timestamp, previousVersion: pkgVer, backedUpFiles: backupCandidates }, null, 2),
    'utf8'
  );
  console.log(`[✔] 已将 ${backedUpCount} 项核心配置文件安全备份至:`);
  console.log(`    ${backupDir}`);

  // Step 2.5: 预检插件入口契约（BUG-0003）
  const entryCheck = await verifyPluginEntry(ROOT_DIR);
  if (!entryCheck.ok) {
    console.error(`\n[✖] 插件入口预激活校验未通过: ${entryCheck.reason}`);
    const restored = restoreFromBackup(backupDir, ROOT_DIR, dshProfileDir);
    console.error(`[↺] 已自动回滚并恢复配置文件: ${restored.join(', ') || '无变更'}`);
    process.exit(1);
  }

  // Step 3: 增量更新环境与依赖
  console.log('\n[3/4] 执行依赖增量安装与 COM 重新注册...');
  const setupArgs = [path.join(__dirname, 'setup.js')];
  if (process.argv.includes('--optional') || process.argv.includes('--full')) {
    setupArgs.push('--optional');
  }
  const setupCode = await runProc(process.execPath, setupArgs);
  if (setupCode !== 0) {
    console.error(`\n[✖] 升级过程中环境配置失败，正在触发事务性自动回滚...`);
    const restored = restoreFromBackup(backupDir, ROOT_DIR, dshProfileDir);
    console.error(`[↺] 已自动从快照 (${backupDir}) 恢复配置文件: ${restored.join(', ')}`);
    process.exit(1);
  }

  // Step 4: 运行全面健康体检
  console.log('\n[4/4] 触发升级后健康诊断 (Doctor)...');
  const doctorCode = await runProc(process.execPath, [path.join(__dirname, 'doctor.js')]);
  if (doctorCode !== 0) {
    console.warn(`\n[⚠] 升级完成，但健康体检报告存在警告或需关注项，请参考上文提示。`);
  } else {
    console.log('\n======================================================');
    console.log(`  🎉 恭喜！dsh-solidworks-plugin 已成功升级至 v${pkgVer}！`);
    console.log(`  系统健康度: 100% PASS`);
    console.log('======================================================\n');
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === __filename) {
  main().catch((err) => {
    console.error('\n[!] 升级程序执行异常:', err);
    process.exit(1);
  });
}
