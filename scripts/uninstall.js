#!/usr/bin/env node
/**
 * scripts/uninstall.js
 *
 * dsh-solidworks-plugin 安全卸载与清理工具。
 *
 * 安全边界规范：
 * 1. 仅清理本插件自动生成的运行环境与配置 (.venv, dsh-mcp-config.json)；
 * 2. 仅清理测试基准沙箱中的临时产物 (测试代码/sandbox_benchmark/)；
 * 3. 严格保留用户所有的 CAD 设计资产 (*.SLDPRT, *.SLDASM, *.SLDDRW)；
 * 4. 严格保留历史配置备份目录 (config-backups/)；
 * 5. 支持 --dry-run 预览清理范围，杜绝任何误删风险。
 */

import { existsSync, rmSync, readdirSync, lstatSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { unregisterFromDshProfile } from './dsh_adapter.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.resolve(__dirname, '..');

const isDryRun = process.argv.includes('--dry-run');
const isForce = process.argv.includes('--yes') || process.argv.includes('-y');

console.log('\n======================================================');
console.log('   dsh-solidworks-plugin 安全卸载与清理程序   ');
console.log('======================================================\n');

if (isDryRun) {
  console.log('【演练模式 (Dry-Run)】仅扫描可清理项，不会执行实际删除。\n');
}

// 定义允许清理的安全目标清单（白名单制）
const SAFE_CLEANUP_TARGETS = [
  {
    path: path.join(ROOT_DIR, '.venv'),
    desc: '插件隔离 Python 虚拟运行环境 (.venv)',
  },
  {
    path: path.join(ROOT_DIR, 'dsh-mcp-config.json'),
    desc: '本地自动生成的 MCP 客户端接入配置文件 (dsh-mcp-config.json)',
  },
  {
    path: path.join(ROOT_DIR, '测试代码', 'sandbox_benchmark', 'benchmark_v020_part.SLDPRT'),
    desc: '测试沙箱基准零件临时生成物',
  },
  {
    path: path.join(ROOT_DIR, '测试代码', 'sandbox_benchmark', 'shadow_backups'),
    desc: '测试沙箱影子备份临时快照目录',
  },
];

console.log('[1/2] 扫描安全可清理资源...');
let itemsFound = 0;
const toRemove = [];

for (const target of SAFE_CLEANUP_TARGETS) {
  if (existsSync(target.path)) {
    itemsFound++;
    toRemove.push(target);
    console.log(`  - [发现] ${target.desc}`);
    console.log(`          路径: ${target.path}`);
  }
}

if (itemsFound === 0) {
  console.log('\n[✔] 未发现本插件的临时运行时或生成配置，工作区处于纯净状态。');
  process.exit(0);
}

// 安全承诺提示
console.log('\n[2/2] 执行安全清理...');
console.log('【安全保证】');
console.log('  ✔ 用户模型资产 (*.SLDPRT, *.SLDASM) 将被 100% 完整保留；');
console.log('  ✔ 配置备份目录 (config-backups/) 将被 100% 完整保留；');
console.log('  ✔ 不触碰任何系统注册表与全局环境变量。\n');

if (!isForce && !isDryRun) {
  console.log('提示: 若要执行真正清理，请使用参数:');
  console.log('      node scripts/uninstall.js --yes');
  console.log('      或演练查看: node scripts/uninstall.js --dry-run\n');
  process.exit(0);
}

for (const item of toRemove) {
  if (isDryRun) {
    console.log(`[DRY-RUN] 将删除: ${item.path}`);
  } else {
    try {
      rmSync(item.path, { recursive: true, force: true });
      console.log(`[✔ 已清理] ${item.desc}`);
    } catch (err) {
      console.warn(`[!] 清理失败 (${item.path}): ${err.message}`);
    }
  }
}

// 解除 DSH Profile 挂载
if (!isDryRun) {
  try {
    const unreg = unregisterFromDshProfile();
    if (unreg.removed) {
      console.log(`[✔ 已解除] DeepSeek Harness 客户端插件挂载配置 (备份: ${unreg.backupPath ? path.basename(unreg.backupPath) : '无'})`);
    }
  } catch (err) {
    console.warn(`[!] 解除 DSH 挂载提示: ${err.message}`);
  }
}

console.log('\n======================================================');
if (isDryRun) {
  console.log('  演练预览完毕。');
} else {
  console.log('  🎉 插件临时运行环境已安全清理！');
  console.log('  如需重新使用，可随时运行: npm run setup 快速重新就绪。');
}
console.log('======================================================\n');
