/**
 * test_policy_adversarial.mjs
 * 
 * 独立对抗性安全测试：
 * 1. Session TTL 过期拦截 (Expired Grant Refusal)
 * 2. 参数篡改检测 (Digest / Argument Mismatch)
 * 3. 路径穿越拦截 (Directory Traversal .., Windows Reserved Names CON/PRN/NUL, UNC)
 * 4. 保护文件名写入拦截 (Protected Filenames)
 * 5. 未授权高危操作拦截 (Confirmation Required)
 */

import fs from 'node:fs';
import path from 'node:path';
import { Policy, READ, WRITE, HIGH, digest, canonicalArgs, realpathWithAncestorWalk } from '../../lib/policy.js';

const OUTPUT_DIR = path.resolve('temp_evidence_v030/E-Security-and-Safety');
fs.mkdirSync(OUTPUT_DIR, { recursive: true });

const results = {
  timestamp: new Date().toISOString(),
  total_tests: 0,
  passed_tests: 0,
  failed_tests: 0,
  details: []
};

function recordTest(name, passed, detail) {
  results.total_tests++;
  if (passed) {
    results.passed_tests++;
  } else {
    results.failed_tests++;
  }
  results.details.push({ test: name, passed, detail });
  console.log(`[${passed ? 'PASS' : 'FAIL'}] ${name}`);
}

// 模拟时钟
let simulatedNow = 1000000;
const fakeNow = () => simulatedNow;

const rootDir = path.resolve('temp_evidence_v030/sandbox_safe');
fs.mkdirSync(rootDir, { recursive: true });

const policy = new Policy({
  mode: 'full',
  allowedRoots: [rootDir],
  grantTtlMs: 5000,
  now: fakeNow
});

// 1. Session TTL 过期拦截测试
{
  simulatedNow = 1000000;
  const toolName = 'solidworks_save_document';
  const args = { filepath: path.join(rootDir, 'test.sldprt') };
  
  // 发放 5 秒 grant
  const grantInfo = policy.grant(toolName, args);
  
  // 3秒时调用：允许
  simulatedNow += 3000;
  // 重新发放一个单次 grant 测试（因为刚才单次已被消费）
  policy.grant(toolName, args);
  const eval1 = policy.evaluate(toolName, args);
  const pass1 = eval1.allowed === true && eval1.granted === true;
  
  // 再发放一个，时间跳跃 6000 毫秒（此时过期）
  policy.grant(toolName, args);
  simulatedNow += 6000;
  const evalExpired = policy.evaluate(toolName, args);
  const passExpired = evalExpired.allowed === false && evalExpired.code === 'CONFIRMATION_REQUIRED';

  recordTest(
    'TTL_Grant_Expiry_Check',
    pass1 && passExpired,
    {
      grant_ttl_ms: 5000,
      active_at_3s_result: eval1,
      expired_at_6s_result: evalExpired
    }
  );
}

// 2. 参数篡改防御测试 (Argument Tampering)
{
  simulatedNow = 2000000;
  const toolName = 'solidworks_save_document';
  const legitimateArgs = { filepath: path.join(rootDir, 'modelA.sldprt') };
  const tamperedArgs = { filepath: path.join(rootDir, 'modelB_tampered.sldprt') };

  // 为合法参数颁发授权
  policy.grant(toolName, legitimateArgs);

  // 恶意攻击者试图携带该 tool 执行被篡改的参数
  const evalTampered = policy.evaluate(toolName, tamperedArgs);
  const passTampering = evalTampered.allowed === false && evalTampered.code === 'CONFIRMATION_REQUIRED';

  recordTest(
    'Argument_Tampering_Resistance',
    passTampering,
    {
      original_args: legitimateArgs,
      tampered_args: tamperedArgs,
      eval_result: evalTampered
    }
  );
}

// 3. 路径穿越与非法设备名防御测试 (Path Traversal, DOS Names, UNC)
{
  simulatedNow = 3000000;
  const writeTool = 'solidworks_sketch_and_extrude';
  
  // 3.1 试图通过 .. 越界到父目录
  const traversalArgs = { filepath: path.join(rootDir, '../secret/passwords.txt') };
  const evalTraversal = policy.evaluate(writeTool, traversalArgs);
  const passTraversal = evalTraversal.allowed === false && evalTraversal.code === 'PATH_OUTSIDE_ALLOWED_ROOTS';

  // 3.2 尝试 Windows 保留设备名 (CON, PRN, AUX, NUL)
  const conPath = path.join(rootDir, 'CON.sldprt');
  const realpathCon = realpathWithAncestorWalk(conPath);
  const passCon = realpathCon === null;

  // 3.3 尝试 UNC 路径 (防 NTLM 泄漏)
  const uncPath = '\\\\192.168.1.100\\share\\exploit.sldprt';
  const realpathUNC = realpathWithAncestorWalk(uncPath);
  const passUNC = realpathUNC === null;

  recordTest(
    'Path_Traversal_And_Device_DOS_Defense',
    passTraversal && passCon && passUNC,
    {
      traversal_eval: evalTraversal,
      con_device_rejected: passCon,
      unc_path_rejected: passUNC
    }
  );
}

// 4. 保护性零件 (PROTECTED_FILENAMES) 拦截测试
{
  simulatedNow = 4000000;
  const toolName = 'solidworks_fillet';
  const protectedArgs = { filepath: path.join(rootDir, '垫圈.sldprt') };
  const evalProtected = policy.evaluate(toolName, protectedArgs);
  const passProtected = evalProtected.allowed === false && evalProtected.code === 'PROTECTED_FILE_REFUSED';

  recordTest(
    'Protected_Standard_Parts_Refusal',
    passProtected,
    {
      target_file: '垫圈.sldprt',
      eval_result: evalProtected
    }
  );
}

// 5. Read-Only 模式下拦截副作用 (Side-Effect Gate)
{
  const readOnlyPolicy = new Policy({ mode: 'read-only' });
  const healthCheckSpawningSw = readOnlyPolicy.evaluate('solidworks_health_check', { start_solidworks: true });
  const passSpawnRefused = healthCheckSpawningSw.allowed === false && healthCheckSpawningSw.code === 'POLICY_MODE';

  recordTest(
    'ReadOnly_Mode_SideEffect_Gate',
    passSpawnRefused,
    {
      tool: 'solidworks_health_check',
      args: { start_solidworks: true },
      eval_result: healthCheckSpawningSw
    }
  );
}

// 保存最终证据
const outputPath = path.join(OUTPUT_DIR, 'policy_security_adversarial_test.json');
fs.writeFileSync(outputPath, JSON.stringify(results, null, 2), 'utf-8');
console.log(`Saved adversarial test evidence to: ${outputPath}`);

if (results.failed_tests > 0) {
  process.exit(1);
}
