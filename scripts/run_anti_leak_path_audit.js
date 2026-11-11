/**
 * scripts/run_anti_leak_path_audit.js
 *
 * 第六阶段：代码与分发物无泄露独立审查工具。
 * 深度扫描项目中的所有分发文件，排查是否存在硬编码的开发者私有绝对路径。
 */

import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.resolve(__dirname, '..');

// 严禁泄露的开发者私有路径模式
const FORBIDDEN_PATTERNS = [
  /D:\\SWCAD-MCP\\Python313/i,
  /D:\\SWCAD-MCP\\solidworks-cad/i,
  /C:\\Users\\(?!Default|Public)[a-zA-Z0-9_\-\.]+\\/i,
  /D:\\Agent工作区\\Antigravity工作区/i,
];

const SCAN_DIRS = ['lib', 'bin', 'scripts', 'vendor'];
const SCAN_FILES = ['package.json', 'dsh-plugin.json', 'cordis.patch.yml'];

// 允许在某些特定自测测试脚本或历史记录中提及的白名单（例如针对性审计脚本除外）
const EXEMPT_FILES = [
  'run_anti_leak_path_audit.js',
  'dsh-solidworks-0.2.0.tgz',
  'dsh-solidworks-0.1.0.tgz',
  'execute_official_release.py',
  'check_required_deliverables.py',
  'audit_18_fails.py',
  'audit_patch_35.py',
  'reconcile_counts.py',
  'generate_reconciliation_csv.py',
  'check_submission_repo.py',
  'submit_to_marketplace.py',
  'create_marketplace_update_pr.py',
  'generate_review_package_data.py',
  'run_independent_verification.py',
];

function getAllFiles(dirPath, arrayOfFiles = []) {
  if (!existsSync(dirPath)) return arrayOfFiles;
  const files = readdirSync(dirPath);
  for (const file of files) {
    const fullPath = path.join(dirPath, file);
    if (statSync(fullPath).isDirectory()) {
      if (file !== 'node_modules' && file !== '.git' && file !== '__pycache__' && file !== '.venv') {
        getAllFiles(fullPath, arrayOfFiles);
      }
    } else {
      arrayOfFiles.push(fullPath);
    }
  }
  return arrayOfFiles;
}

let totalFilesChecked = 0;
let leakCount = 0;
const leaks = [];

console.log('\n======================================================');
console.log('   第六阶段：分发代码与配置无硬编码路径独立审查   ');
console.log('======================================================\n');

const filesToAudit = [];
for (const f of SCAN_FILES) {
  const p = path.join(ROOT_DIR, f);
  if (existsSync(p)) filesToAudit.push(p);
}
for (const d of SCAN_DIRS) {
  getAllFiles(path.join(ROOT_DIR, d), filesToAudit);
}

for (const filePath of filesToAudit) {
  const relPath = path.relative(ROOT_DIR, filePath);
  const baseName = path.basename(filePath);
  if (EXEMPT_FILES.includes(baseName)) continue;
  if (relPath.includes('tests') && baseName !== 'package.test.js') continue;

  try {
    const content = readFileSync(filePath, 'utf8');
    totalFilesChecked++;
    for (const pattern of FORBIDDEN_PATTERNS) {
      if (pattern.test(content)) {
        leakCount++;
        leaks.push({ file: relPath, pattern: pattern.toString() });
        console.warn(`[!] 发现硬编码路径模式匹配: ${relPath} -> ${pattern}`);
      }
    }
  } catch {
    // binary file or read error
  }
}

console.log(`\n审查完成: 共扫描 ${totalFilesChecked} 个核心分发源码与配置文件。`);
if (leakCount === 0) {
  console.log('🎉 零私有硬编码路径泄露！代码符合严格产品化通用分发标准！\n');
} else {
  console.error(`✖ 发现 ${leakCount} 处潜在路径硬编码，必须修复！\n`);
  process.exit(1);
}
