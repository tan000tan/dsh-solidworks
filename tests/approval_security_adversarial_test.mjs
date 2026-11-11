/**
 * approval_security_adversarial_test.mjs
 * 
 * 极端对抗性安全测试：全面验证 P0 人类审批机制与防 AI 自授权体系。
 * 覆盖 18 种攻击场景，确保 100% Fail-Closed。
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Policy, READ, WRITE, HIGH, digest, canonicalArgs } from '../lib/policy.js';
import { apply } from '../lib/index.js';

const ROOT_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const OUTPUT_DIR = path.resolve(ROOT_DIR, 'temp_evidence_v030/E-Security-and-Safety');
fs.mkdirSync(OUTPUT_DIR, { recursive: true });

const results = {
  suite: 'P0_HUMAN_APPROVAL_ADVERSARIAL_SUITE',
  timestamp: new Date().toISOString(),
  total_tests: 0,
  passed_tests: 0,
  failed_tests: 0,
  details: []
};

function record(name, passed, detail) {
  results.total_tests++;
  if (passed) {
    results.passed_tests++;
    console.log(`[PASS] ${name}`);
  } else {
    results.failed_tests++;
    console.error(`[FAIL] ${name}`);
  }
  results.details.push({ test: name, passed, detail });
}

// 模拟时钟
let simulatedNow = 1_000_000;
const fakeNow = () => simulatedNow;

const sandboxRoot = path.resolve(ROOT_DIR, 'temp_evidence_v030/sandbox_safe');
fs.mkdirSync(sandboxRoot, { recursive: true });

const policy = new Policy({
  mode: 'full',
  allowedRoots: [sandboxRoot],
  grantTtlMs: 5000,
  challengeTtlMs: 3000,
  now: fakeNow,
});

// Setup Mock DSH Context
const registeredTools = new Map();
const mockCtx = {
  tools: {
    register(def) {
      registeredTools.set(def.name, def);
      return () => registeredTools.delete(def.name);
    },
  },
  agent: {
    session: {
      header: { id: 'session-alpha-001', cwd: sandboxRoot },
    },
  },
  logger: {
    info() {},
    warn() {},
    error() {},
  },
};

await apply(mockCtx, {
  mode: 'full',
  allowedRoots: [sandboxRoot],
  grantTtlMs: 5000,
  challengeTtlMs: 3000,
  now: fakeNow,
});

const confirmTool = registeredTools.get('solidworks_confirm');
const highTool = 'solidworks_save_document';
const targetFileA = path.join(sandboxRoot, 'partA.sldprt');
const targetFileB = path.join(sandboxRoot, 'partB.sldprt');
const legitArgs = { filepath: targetFileA };

console.log('=== 开始执行 18 种 P0 人类审批对抗测试 ===');

// Vector 1: 缺少凭证与挑战 (Missing ticket / challengeId)
{
  const res = await confirmTool.execute({ tool: highTool, args: legitArgs });
  const data = JSON.parse(res.text);
  const ok = data.status === 'refused' && data.code === 'CHALLENGE_INVALID';
  record('Vector_01_Missing_Confirmation_Or_Ticket', ok, data);
}

// Vector 2: AI 显式提交 confirmedByHuman: false
{
  const res = await confirmTool.execute({ tool: highTool, args: legitArgs, confirmedByHuman: false });
  const data = JSON.parse(res.text);
  const ok = data.status === 'refused';
  record('Vector_02_ConfirmedByHuman_False_Rejected', ok, data);
}

// Vector 3: AI 试图通过历史遗留漏洞参数 confirmedByHuman: true 实施自授权
{
  const res = await confirmTool.execute({ tool: highTool, args: legitArgs, confirmedByHuman: true });
  const data = JSON.parse(res.text);
  // 必须依然拒绝，绝不能因为 confirmedByHuman: true 就放行
  const ok = data.status === 'refused' && data.code === 'CHALLENGE_INVALID';
  record('Vector_03_AI_Self_Authorization_True_Blocked', ok, data);
}

// Vector 4: AI 构造伪造的随机凭证 (Fabricated Random Ticket)
{
  const ch = mockCtx.solidworks.policy.createChallenge(highTool, legitArgs, { sessionId: 'session-alpha-001' });
  const res = await confirmTool.execute({
    challengeId: ch.challengeId,
    ticket: '1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef',
    tool: highTool,
    args: legitArgs,
  });
  const data = JSON.parse(res.text);
  const ok = data.status === 'refused' && data.code === 'TICKET_INVALID';
  record('Vector_04_Fabricated_Ticket_Rejected', ok, data);
}

// Vector 5: 凭证篡改测试 (Ticket Tampering - 1 bit flip)
{
  const ch = mockCtx.solidworks.policy.createChallenge(highTool, legitArgs, { sessionId: 'session-alpha-001' });
  const realTicket = mockCtx.solidworks.signApproval(ch.challengeId, { sessionId: 'session-alpha-001' });
  // 篡改最后一个字符
  const tamperedTicket = realTicket.slice(0, -1) + (realTicket.slice(-1) === 'a' ? 'b' : 'a');
  const res = await confirmTool.execute({
    challengeId: ch.challengeId,
    ticket: tamperedTicket,
    tool: highTool,
    args: legitArgs,
  });
  const data = JSON.parse(res.text);
  const ok = data.status === 'refused' && data.code === 'TICKET_INVALID';
  record('Vector_05_Ticket_Tampering_Rejected', ok, data);
}

// Vector 6: 参数篡改测试 (Argument Tampering - approved for fileA, executed with fileB)
{
  const ch = mockCtx.solidworks.policy.createChallenge(highTool, legitArgs, { sessionId: 'session-alpha-001' });
  const realTicket = mockCtx.solidworks.signApproval(ch.challengeId, { sessionId: 'session-alpha-001' });
  const tamperedArgs = { filepath: targetFileB };
  const res = await confirmTool.execute({
    challengeId: ch.challengeId,
    ticket: realTicket,
    tool: highTool,
    args: tamperedArgs,
  });
  const data = JSON.parse(res.text);
  const ok = data.status === 'refused' && data.code === 'ARGUMENTS_MUTATED';
  record('Vector_06_Argument_Tampering_Detected_And_Refused', ok, data);
}

// Vector 7: 重放攻击测试 (Replay Attack - reusing single-use ticket)
{
  const ch = mockCtx.solidworks.policy.createChallenge(highTool, legitArgs, { sessionId: 'session-alpha-001' });
  const realTicket = mockCtx.solidworks.signApproval(ch.challengeId, { sessionId: 'session-alpha-001' });
  
  // 第一次使用：成功
  const resFirst = await confirmTool.execute({
    challengeId: ch.challengeId,
    ticket: realTicket,
    tool: highTool,
    args: legitArgs,
  });
  const dataFirst = JSON.parse(resFirst.text);
  const firstPass = dataFirst.status === 'granted';

  // 第二次使用同凭证重放：必须拒绝 (单次销毁)
  const resReplay = await confirmTool.execute({
    challengeId: ch.challengeId,
    ticket: realTicket,
    tool: highTool,
    args: legitArgs,
  });
  const dataReplay = JSON.parse(resReplay.text);
  const replayBlocked = dataReplay.status === 'refused' && dataReplay.code === 'CHALLENGE_NOT_FOUND';
  record('Vector_07_Replay_Attack_Blocked_Single_Use', firstPass && replayBlocked, { dataFirst, dataReplay });
}

// Vector 8: 挑战过期拦截测试 (Expired Challenge Refusal)
{
  simulatedNow = 2_000_000;
  const ch = mockCtx.solidworks.policy.createChallenge(highTool, legitArgs, { sessionId: 'session-alpha-001' });
  const realTicket = mockCtx.solidworks.signApproval(ch.challengeId, { sessionId: 'session-alpha-001' });
  
  // 时间流逝 4000ms (TTL为 3000ms)
  simulatedNow += 4000;

  const res = await confirmTool.execute({
    challengeId: ch.challengeId,
    ticket: realTicket,
    tool: highTool,
    args: legitArgs,
  });
  const data = JSON.parse(res.text);
  const ok = data.status === 'refused' && data.code === 'CHALLENGE_EXPIRED';
  record('Vector_08_Expired_Challenge_Refused', ok, data);
}

// Vector 9: 目标路径替换攻击 (Path Swap to Root/Protected)
{
  const ch = mockCtx.solidworks.policy.createChallenge(highTool, legitArgs, { sessionId: 'session-alpha-001' });
  const realTicket = mockCtx.solidworks.signApproval(ch.challengeId, { sessionId: 'session-alpha-001' });
  
  // 尝试替换为系统保护路径
  const attackArgs = { filepath: 'C:\\Windows\\System32\\calc.exe' };
  const res = await confirmTool.execute({
    challengeId: ch.challengeId,
    ticket: realTicket,
    tool: highTool,
    args: attackArgs,
  });
  const data = JSON.parse(res.text);
  const ok = data.status === 'refused' && data.code === 'ARGUMENTS_MUTATED';
  record('Vector_09_Path_Swap_Attack_Blocked', ok, data);
}

// Vector 10: 跨会话滥用拦截 (Cross-Session Abuse)
{
  simulatedNow = 3_000_000;
  // Session A 签发
  const chA = mockCtx.solidworks.policy.createChallenge(highTool, legitArgs, { sessionId: 'session-alpha-001' });
  const ticketA = mockCtx.solidworks.signApproval(chA.challengeId, { sessionId: 'session-alpha-001' });

  // 攻击者试图在 Session B 提交
  const mockCtxSessionB = {
    agent: { session: { header: { id: 'session-beta-002', cwd: sandboxRoot } } },
    tools: mockCtx.tools,
    logger: mockCtx.logger,
  };
  
  const verification = mockCtx.solidworks.policy.verifyAndConsumeTicket(
    chA.challengeId,
    ticketA,
    highTool,
    legitArgs,
    { sessionId: 'session-beta-002' }
  );
  const ok = verification.ok === false && verification.code === 'SESSION_MISMATCH';
  record('Vector_10_Cross_Session_Abuse_Blocked', ok, verification);
}

// Vector 11: 工具名篡改攻击 (Tool Swap - Ticket for export used for close)
{
  simulatedNow = 4_000_000;
  const ch = mockCtx.solidworks.policy.createChallenge('solidworks_export_active', { output_path: path.join(sandboxRoot, 'out.step') }, { sessionId: 'session-alpha-001' });
  const ticket = mockCtx.solidworks.signApproval(ch.challengeId, { sessionId: 'session-alpha-001' });

  // 攻击者携带此凭证尝试调用高危删除/关闭工具
  const res = await confirmTool.execute({
    challengeId: ch.challengeId,
    ticket,
    tool: 'solidworks_close_documents',
    args: { output_path: path.join(sandboxRoot, 'out.step') },
  });
  const data = JSON.parse(res.text);
  const ok = data.status === 'refused' && data.code === 'TOOL_MISMATCH';
  record('Vector_11_Tool_Swap_Attack_Blocked', ok, data);
}

// Vector 12: 并发重放竞争测试 (Concurrent Race Condition on Single Ticket)
{
  simulatedNow = 5_000_000;
  const ch = mockCtx.solidworks.policy.createChallenge(highTool, legitArgs, { sessionId: 'session-alpha-001' });
  const ticket = mockCtx.solidworks.signApproval(ch.challengeId, { sessionId: 'session-alpha-001' });

  // 两个并发请求同时使用同一个 challengeId 和 ticket
  const [res1, res2] = await Promise.all([
    confirmTool.execute({ challengeId: ch.challengeId, ticket, tool: highTool, args: legitArgs }),
    confirmTool.execute({ challengeId: ch.challengeId, ticket, tool: highTool, args: legitArgs })
  ]);
  const data1 = JSON.parse(res1.text);
  const data2 = JSON.parse(res2.text);

  // 必须恰好有一个成功，另一个必须被拒绝！绝不能两个都成功！
  const oneGranted = (data1.status === 'granted' && data2.status === 'refused') ||
                     (data2.status === 'granted' && data1.status === 'refused');
  record('Vector_12_Concurrent_Race_Condition_Defense', oneGranted, { data1, data2 });
}

// Vector 13: READ 工具尝试假冒 HIGH 工具索取授权
{
  const readTool = 'solidworks_list_edges';
  const res = await confirmTool.execute({
    challengeId: 'chal_fake',
    ticket: 'fake',
    tool: readTool,
    args: {},
  });
  const data = JSON.parse(res.text);
  const ok = data.status === 'not_required';
  record('Vector_13_Read_Tool_Confirmation_Not_Required', ok, data);
}

// Vector 14: 普通 WRITE 工具尝试越权执行 HIGH 操作
{
  const writeTool = 'solidworks_sketch_and_extrude';
  const res = await confirmTool.execute({
    challengeId: 'chal_fake',
    ticket: 'fake',
    tool: writeTool,
    args: {},
  });
  const data = JSON.parse(res.text);
  const ok = data.status === 'not_required';
  record('Vector_14_Write_Tool_Confirmation_Not_Required', ok, data);
}

// Vector 15: 禁用名单 (Deny List) 阻断测试
{
  const denyPolicy = new Policy({
    mode: 'full',
    deny: ['solidworks_save_document'],
    allowedRoots: [sandboxRoot],
  });
  assert.throws(() => {
    denyPolicy.grant('solidworks_save_document', legitArgs);
  }, /Refusing to grant denied tool/);
  const evalDeny = denyPolicy.evaluate('solidworks_save_document', legitArgs);
  const ok = evalDeny.allowed === false && evalDeny.code === 'TOOL_DENIED';
  record('Vector_15_Deny_List_Absolute_Override', ok, evalDeny);
}

// Vector 16: Read-Only 模式下高危工具绝对拦截
{
  const readOnlyPolicy = new Policy({ mode: 'read-only', allowedRoots: [sandboxRoot] });
  const evalRo = readOnlyPolicy.evaluate(highTool, legitArgs);
  const ok = evalRo.allowed === false && evalRo.code === 'POLICY_MODE';
  record('Vector_16_ReadOnly_Mode_Ceiling_Enforced', ok, evalRo);
}

// Vector 17: 畸形挑战 ID 防御 (SQLi / Traversal in challengeId)
{
  const malformedIds = [
    '../../../etc/passwd',
    'chal_123; DROP TABLE grants;--',
    '<script>alert(1)</script>',
    '',
    null,
    undefined,
    12345
  ];
  let allMalformedBlocked = true;
  for (const mid of malformedIds) {
    const res = await confirmTool.execute({
      challengeId: mid,
      ticket: 'any',
      tool: highTool,
      args: legitArgs,
    });
    const data = JSON.parse(res.text);
    if (data.status !== 'refused') {
      allMalformedBlocked = false;
      break;
    }
  }
  record('Vector_17_Malformed_ChallengeId_Fail_Closed', allMalformedBlocked, { malformedCount: malformedIds.length });
}

// Vector 18: 无根目录或根目录不匹配时 Fail-Closed
{
  const zeroRootPolicy = new Policy({ mode: 'full', allowedRoots: [] });
  const evalZero = zeroRootPolicy.evaluate(highTool, legitArgs, { sessionCwd: '' });
  const ok = evalZero.allowed === false && evalZero.code === 'PATH_OUTSIDE_ALLOWED_ROOTS';
  record('Vector_18_Missing_Allowed_Roots_Fail_Closed', ok, evalZero);
}

// 保存审计与对抗测试结果
const evidenceFile = path.join(OUTPUT_DIR, 'approval_security_adversarial_evidence.json');
fs.writeFileSync(evidenceFile, JSON.stringify(results, null, 2), 'utf-8');
console.log(`\n=== 18 项对抗测试完成：${results.passed_tests}/${results.total_tests} PASS ===`);
console.log(`证据保存至: ${evidenceFile}`);

if (results.failed_tests > 0) {
  process.exit(1);
} else {
  process.exit(0);
}
