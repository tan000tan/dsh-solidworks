/**
 * verify_installation_productization.mjs
 * 
 * 验证零配置安装、环境自适应发现与卸载安全生命周期：
 * 1. 运行态环境探测与自适应发现测试 (discover)
 * 2. 模拟无 Python 环境下的优雅降级与中文引导诊断
 * 3. 卸载安全白名单与 Dry-Run 验证 (严格保证不误伤用户 CAD 资产)
 */

import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { discover, probePython, entryCandidates } from '../../lib/discover.js';

const ROOT_DIR = path.resolve('.');
const OUTPUT_DIR = path.resolve('temp_evidence_v030/C-Installation-and-Environment');
fs.mkdirSync(OUTPUT_DIR, { recursive: true });

const results = {
  timestamp: new Date().toISOString(),
  product_name: "dsh-solidworks",
  version: "0.3.0",
  tests: [],
  summary: { total: 0, passed: 0, failed: 0 }
};

function recordTest(name, passed, detail) {
  results.summary.total++;
  if (passed) {
    results.summary.passed++;
    console.log(`[PASS] ${name}`);
  } else {
    results.summary.failed++;
    console.log(`[FAIL] ${name}`);
  }
  results.tests.push({ name, passed, detail });
}

// 1. 现有生产环境下的自动发现
console.log('=== 1. 测试真实生产环境自适应发现 ===');
const realDiscover = await discover({ pluginRoot: ROOT_DIR });
const passRealDiscover = realDiscover.ok === true && 
                         Boolean(realDiscover.python?.command) && 
                         Boolean(realDiscover.serverScript);

recordTest(
  'Runtime_Environment_Discovery',
  passRealDiscover,
  {
    ok: realDiscover.ok,
    python: realDiscover.python,
    serverScript: realDiscover.serverScript,
    notes: realDiscover.notes
  }
);

// 2. 模拟缺失 Python 时的优雅降级与中文引导
console.log('\n=== 2. 测试缺失 Python 时的优雅诊断提示 ===');
const fakeEnv = {
  PATH: '',
  LOCALAPPDATA: 'C:\\NonExistent_Fake_Path',
  PROGRAMFILES: 'C:\\NonExistent_Fake_Path'
};
const missingPyDiscover = await discover({
  pluginRoot: ROOT_DIR,
  config: { pythonPath: 'C:\\FakeNonExistentPython\\python.exe' },
  env: fakeEnv
});

const passFriendlyError = missingPyDiscover.ok === false &&
                          missingPyDiscover.code === 'PYTHON_INVALID' &&
                          missingPyDiscover.message.includes('configured pythonPath failed');

recordTest(
  'Missing_Python_Graceful_Guidance',
  passFriendlyError,
  {
    ok: missingPyDiscover.ok,
    code: missingPyDiscover.code,
    message: missingPyDiscover.message
  }
);

// 3. 卸载安全白名单与 Dry-Run 验证
console.log('\n=== 3. 卸载程序 Dry-Run 与安全白名单验证 ===');
const uninstallScript = path.join(ROOT_DIR, 'scripts', 'uninstall.js');
const dryRunResult = spawnSync(process.execPath, [uninstallScript, '--dry-run'], {
  encoding: 'utf8',
  timeout: 10000
});

const stdout = dryRunResult.stdout || '';
const hasDryRunBanner = stdout.includes('【演练模式 (Dry-Run)】');
const hasSafetyAssurance = stdout.includes('用户模型资产 (*.SLDPRT, *.SLDASM) 将被 100% 完整保留');
const noUserCadDeleted = !stdout.includes('Deleting user CAD files') && dryRunResult.status === 0;

recordTest(
  'Uninstall_DryRun_Safety_Assurance',
  hasDryRunBanner && hasSafetyAssurance && noUserCadDeleted,
  {
    exit_code: dryRunResult.status,
    has_banner: hasDryRunBanner,
    has_safety_pledge: hasSafetyAssurance,
    stdout_preview: stdout.slice(0, 500)
  }
);

// 4. 离线打包资产完整性检查
console.log('\n=== 4. 离线打包资产与依赖自洽性检查 ===');
const requiredFiles = [
  'vendor/solidworks-automation-skill/mcp-server/server.py',
  'vendor/solidworks-automation-skill/scripts/sw_compat.py',
  'vendor/solidworks-automation-skill/scripts/sw_part.py',
  'vendor/solidworks-automation-skill/scripts/sw_connect.py',
  'vendor/solidworks-automation-skill/scripts/sw_export.py',
  'lib/index.js',
  'lib/policy.js',
  'lib/discover.js',
  'package.json',
  'dsh-plugin.json'
];

const fileChecks = requiredFiles.map(rel => {
  const p = path.join(ROOT_DIR, rel);
  return { file: rel, exists: fs.existsSync(p) };
});
const allFilesExist = fileChecks.every(f => f.exists);

recordTest(
  'Bundled_Assets_Integrity_Check',
  allFilesExist,
  { file_checks: fileChecks }
);

// 写入证据文件
const outPath = path.join(OUTPUT_DIR, 'installation_and_lifecycle_verification.json');
fs.writeFileSync(outPath, JSON.stringify(results, null, 2), 'utf8');
console.log(`\n已保存安装与产品化证据至: ${outPath}`);

if (results.summary.failed > 0) {
  process.exit(1);
}
