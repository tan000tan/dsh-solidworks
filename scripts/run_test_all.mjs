#!/usr/bin/env node
/**
 * 统一测试运行器（B2 / N-04 修复）：
 * - 按顺序运行全部 7 个核心测试套件（4 个离线套件 + 3 个 Python 联动套件）；
 * - 自动探测可用 Python 解释器（支持 --python / DSH_SOLIDWORKS_PYTHON / discover.js 探测）；
 * - 明确区分 PASS / FAIL / BLOCKED / SKIPPED，绝不静默跳过或误报通过；
 * - 输出每个套件的精确断言数、耗时与退出码，支持 --json <path> 导出机器清单。
 */
import { spawnSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..');

const argv = process.argv.slice(2);
const pyIdx = argv.indexOf('--python');
let pythonPath = pyIdx >= 0 ? argv[pyIdx + 1] : (process.env.DSH_SOLIDWORKS_PYTHON || null);
const jsonIdx = argv.indexOf('--json');
const jsonOut = jsonIdx >= 0 ? argv[jsonIdx + 1] : null;

if (!pythonPath) {
  const { entryCandidates, probePython } = await import(pathToFileURL(join(ROOT, 'lib', 'discover.js')).href);
  for (const candidate of entryCandidates(process.env, ROOT)) {
    const res = await probePython(candidate);
    if (res.ok) {
      pythonPath = res.command;
      break;
    }
  }
}

const SUITES = [
  { id: 'policy', file: 'tests/policy.test.js', needsPython: false },
  { id: 'mcp', file: 'tests/mcp.test.js', needsPython: false },
  { id: 'schema', file: 'tests/schema.test.js', needsPython: false },
  { id: 'package', file: 'tests/package.test.js', needsPython: false },
  { id: 'audit', file: 'tests/audit.test.js', needsPython: true, passPythonFlag: true },
  { id: 'host', file: 'tests/host.test.js', needsPython: true, passPythonFlag: true },
  { id: 'crash', file: 'tests/crash.test.js', needsPython: true, passPythonEnv: true },
  // RELEASE-SWARM-01：审计业务状态（BUG-009）与 Python 侧回归（BUG-001/002/015/016/017/018）
  { id: 'audit-outcome', file: 'tests/audit_outcome.test.js', needsPython: false },
  { id: 'release-swarm', file: 'tests/release_swarm_regression_test.py', needsPython: true, runtime: 'python' },
  // Round 2 canonical baseline additions (Group A Cordis service + Group D/R3 adapter scripts)
  { id: 'cordis-service', file: 'tests/cordis_service_registration_test.mjs', needsPython: false },
  { id: 'dsh-adapter', file: 'tests/dsh_adapter_scripts.test.js', needsPython: false },
  // Round 2 Deep Closure (R1 / R5 / AUD-TEST-003): include previously excluded security & productization suites
  { id: 'approval-adversarial', file: 'tests/approval_security_adversarial_test.mjs', needsPython: false, passPythonEnv: true },
  { id: 'phase5-approval', file: 'tests/phase5_security_approval_test.js', needsPython: false },
  { id: 'r1-r5-security-matrix', file: 'tests/r1_r5_security_matrix_test.mjs', needsPython: false },
  { id: 'confirm-human-auth', file: 'tests/confirm_human_authorization_test.js', needsPython: false, passPythonEnv: true },
  { id: 'cordis-activation', file: 'tests/cordis_activation_test.mjs', needsPython: false },
  { id: 'runtime-isolation', file: 'tests/runtime_isolation_test.mjs', needsPython: false },
  { id: 'phase3-productization', file: 'tests/phase3_productization_test.js', needsPython: false },
  { id: 'd02-d12-d13-discovery', file: 'tests/d02_d12_d13_config_and_discovery_test.mjs', needsPython: false },
  // Full Python test aggregator (discovers all tests/*_test.py strictly; fails on any FAIL/EMPTY/SKIPPED)
  { id: 'python-all', file: 'scripts/run_all_python_tests.py', needsPython: true, runtime: 'python' },
];

function parseStats(output, exitCode) {
  // node:test summary (supports both TAP "# tests N" and Node 24 spec "ℹ tests N")
  const tapPass = output.match(/^(?:#|ℹ)\s+pass\s+(\d+)/m);
  const tapFail = output.match(/^(?:#|ℹ)\s+fail\s+(\d+)/m);
  const tapTests = output.match(/^(?:#|ℹ)\s+tests\s+(\d+)/m);
  if (tapTests && tapPass) {
    const passed = Number(tapPass[1]);
    const failed = tapFail ? Number(tapFail[1]) : 0;
    return { tests: Number(tapTests[1]), passed, failed };
  }
  // Custom check() format: "PASS  ..." / "FAIL  ..."
  const passLines = (output.match(/^PASS\s+/gm) || []).length;
  const failLines = (output.match(/^FAIL\s+/gm) || []).length;
  if (passLines > 0 || failLines > 0) {
    return { tests: passLines + failLines, passed: passLines, failed: failLines };
  }
  // "ALL PASS (N)" fallback
  const allPassN = output.match(/ALL PASS\s*\((\d+)\)/);
  if (allPassN) {
    const n = Number(allPassN[1]);
    return { tests: n, passed: n, failed: 0 };
  }
  // unittest format: "Ran 6 tests in 0.03s" + "OK"/"FAILED (failures=N)"
  const uniRan = output.match(/^Ran (\d+) tests?/m);
  if (uniRan) {
    const failed = output.match(/^FAILED \(([^)]*)\)/m);
    const n = Number(uniRan[1]);
    if (failed) {
      const f = /failures=(\d+)/.exec(failed[1]);
      const e = /errors=(\d+)/.exec(failed[1]);
      const bad = (f ? Number(f[1]) : 0) + (e ? Number(e[1]) : 0);
      return { tests: n, passed: Math.max(0, n - bad), failed: bad || 1 };
    }
    return { tests: n, passed: n, failed: 0 };
  }
  return { tests: exitCode === 0 ? 1 : 0, passed: exitCode === 0 ? 1 : 0, failed: exitCode === 0 ? 0 : 1 };
}

const results = [];
let hasFailure = false;
let hasBlocked = false;

console.log(`dsh-solidworks test:all runner`);
console.log(`Root: ${ROOT}`);
console.log(`Python: ${pythonPath || '(none detected)'}\n`);

for (const suite of SUITES) {
  const args = [join(ROOT, suite.file)];
  const env = { ...process.env, PYTHONDONTWRITEBYTECODE: '1' };
  if (suite.needsPython && !pythonPath) {
    console.log(`[BLOCKED] ${suite.id} (${suite.file}): no usable Python interpreter with mcp package`);
    results.push({
      id: suite.id,
      file: suite.file,
      status: 'BLOCKED',
      exitCode: 2,
      durationMs: 0,
      tests: 0,
      passed: 0,
      failed: 0,
      reason: 'no usable Python interpreter detected',
    });
    hasBlocked = true;
    continue;
  }
  if (suite.passPythonFlag && pythonPath) {
    args.push('--python', pythonPath);
  }
  if (suite.passPythonEnv && pythonPath) {
    env.DSH_SOLIDWORKS_PYTHON = pythonPath;
  }

  const t0 = Date.now();
  const isPythonSuite = suite.runtime === 'python';
  const spawnCmd = isPythonSuite ? pythonPath : process.execPath;
  const spawnArgs = isPythonSuite ? [join(ROOT, suite.file)] : args;
  const proc = spawnSync(spawnCmd, spawnArgs, {
    cwd: ROOT,
    env,
    encoding: 'utf8',
    windowsHide: true,
    timeout: 120_000,
  });
  const durationMs = Date.now() - t0;
  const combined = `${proc.stdout || ''}\n${proc.stderr || ''}`;
  const exitCode = proc.status ?? 1;
  const stats = parseStats(combined, exitCode);

  let status = 'PASS';
  if (exitCode === 2 || /^SKIPPED:/m.test(combined)) {
    status = 'BLOCKED';
    hasBlocked = true;
  } else if (exitCode !== 0 || stats.failed > 0) {
    status = 'FAIL';
    hasFailure = true;
  }

  console.log(`[${status}] ${suite.id} (${suite.file}) -> tests=${stats.tests}, pass=${stats.passed}, fail=${stats.failed}, exit=${exitCode}, ${durationMs}ms`);
  if (status !== 'PASS') {
    const tail = combined.trim().split(/\r?\n/).slice(-12).join('\n');
    console.log(tail);
  }

  results.push({
    id: suite.id,
    file: suite.file,
    status,
    exitCode,
    durationMs,
    ...stats,
  });
}

const totalTests = results.reduce((s, r) => s + r.tests, 0);
const totalPassed = results.reduce((s, r) => s + r.passed, 0);
const totalFailed = results.reduce((s, r) => s + r.failed, 0);
const summary = {
  generatedAt: new Date().toISOString(),
  python: pythonPath,
  suites: results.length,
  passedSuites: results.filter((r) => r.status === 'PASS').length,
  failedSuites: results.filter((r) => r.status === 'FAIL').length,
  blockedSuites: results.filter((r) => r.status === 'BLOCKED').length,
  totalAssertions: totalTests,
  totalPassed,
  totalFailed,
  verdict: hasFailure ? 'FAIL' : hasBlocked ? 'BLOCKED' : 'PASS',
  results,
};

console.log(`\nSummary: ${summary.verdict} | suites=${summary.passedSuites}/${summary.suites} PASS, blocked=${summary.blockedSuites}, failed=${summary.failedSuites} | assertions=${totalPassed}/${totalTests}`);

if (jsonOut) {
  writeFileSync(jsonOut, JSON.stringify(summary, null, 2), 'utf8');
}

if (hasFailure) process.exit(1);
if (hasBlocked) process.exit(2);
process.exit(0);
