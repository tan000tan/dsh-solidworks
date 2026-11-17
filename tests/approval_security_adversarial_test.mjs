/**
 * approval_security_adversarial_test.mjs
 *
 * BUG-0002 全量对抗安全测试：验证彻底消除本地磁盘密钥/CLI自批漏洞后，
 * AI 无法通过任何路径（CLI、solidworks_confirm、重放、篡改参数、跨会话、并发竞态、缺失通道）绕过人类审批。
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { Policy, digest, canonicalArgs } from '../lib/policy.js';
import { apply } from '../lib/index.js';

const ROOT_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const CLI_PATH = path.join(ROOT_DIR, 'bin', 'dsh-solidworks.js');
const sandboxRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-sw-bug0002-adv-'));
const STUB_SERVER = path.join(ROOT_DIR, 'tests', 'stub-server.py');

const argsCli = process.argv.slice(2);
const pyIdx = argsCli.indexOf('--python');
const pythonPath = pyIdx >= 0 ? argsCli[pyIdx + 1] : (process.env.DSH_SOLIDWORKS_PYTHON || null);
const outIdx = argsCli.indexOf('--output');
const outputJson = outIdx >= 0 ? argsCli[outIdx + 1] : null;

const results = {
  suite: 'BUG-0002_APPROVAL_SECURITY_ADVERSARIAL_SUITE',
  timestamp: new Date().toISOString(),
  total_tests: 0,
  passed_tests: 0,
  failed_tests: 0,
  details: [],
};

function record(name, passed, detail) {
  results.total_tests++;
  if (passed) {
    results.passed_tests++;
    console.log(`[PASS] ${name}`);
  } else {
    results.failed_tests++;
    console.error(`[FAIL] ${name} -> ${JSON.stringify(detail)}`);
  }
  results.details.push({ test: name, passed, detail });
}

function runCliExpectFail(cliArgs) {
  try {
    const stdout = execFileSync(process.execPath, [CLI_PATH, ...cliArgs], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
    return { exitCode: 0, json: JSON.parse(stdout || '{}') };
  } catch (err) {
    let parsed = null;
    try { parsed = JSON.parse(err.stdout || '{}'); } catch { parsed = { raw: String(err.stdout || err.stderr || '') }; }
    return { exitCode: err.status ?? 1, json: parsed };
  }
}

try {
  // ---- A. CLI 通道自批与 --yes 绕过测试 -------------------------------------
  for (const [label, cmd] of [
    ['CLI_01_Approve_Subcommand_Removed', ['approve', 'chal_deadbeef', '--json']],
    ['CLI_02_Reject_Subcommand_Removed', ['reject', 'chal_deadbeef', '--json']],
    ['CLI_03_Challenges_Subcommand_Removed', ['challenges', '--json']],
  ]) {
    const res = runCliExpectFail(cmd);
    record(label, res.exitCode === 2 && res.json?.code === 'APPROVAL_CLI_REMOVED', res);
  }

  {
    const res = runCliExpectFail([
      'call', 'solidworks_save_document', '--mode', 'full', '--yes',
      '--json-args', JSON.stringify({ path: 'x.sldprt' }),
      '--json',
    ]);
    record('CLI_04_Call_With_Yes_Fails_Closed', res.exitCode === 3 && res.json?.code === 'APPROVAL_CHANNEL_UNAVAILABLE', res);
  }

  // ---- B. solidworks_confirm 防 AI 自授权测试 -------------------------------
  {
    const registered = new Map();
    const mockCtx = {
      tools: { register: (d) => { registered.set(d.name, d); return () => {}; } },
      agent: { session: { header: { id: 'sess-self', cwd: sandboxRoot } } },
    };
    const stopSelf = await apply(mockCtx, { mode: 'full', allowedRoots: [sandboxRoot] });
    try {
      const confirmTool = registered.get('solidworks_confirm');

      const attempts = [
        ['Confirm_01_Empty_Args', {}],
        ['Confirm_02_ConfirmedByHuman_False', { tool: 'solidworks_save_document', confirmedByHuman: false }],
        ['Confirm_03_ConfirmedByHuman_True', { tool: 'solidworks_save_document', confirmedByHuman: true }],
        ['Confirm_04_Fabricated_Ticket', { challengeId: 'chal_1234', ticket: 'a'.repeat(64), tool: 'solidworks_save_document' }],
      ];
      for (const [label, payload] of attempts) {
        const data = JSON.parse((await confirmTool.execute(payload)).text);
        record(label, data.status === 'refused' && data.code === 'SELF_APPROVAL_PROHIBITED', data);
      }
    } finally {
      await stopSelf?.();
    }
  }

  // ---- C. Policy 内存态 Challenge & Grant 安全不变式 -------------------------
  let simNow = 1_000_000;
  const targetA = path.join(sandboxRoot, 'partA.sldprt');
  const targetB = path.join(sandboxRoot, 'partB.sldprt');
  const argsA = { path: targetA };
  const policy = new Policy({ mode: 'full', allowedRoots: [sandboxRoot], grantTtlMs: 5000, challengeTtlMs: 3000, now: () => simNow });

  record('Policy_01_No_SignChallenge_Method', typeof policy.signChallenge === 'undefined', { hasSign: typeof policy.signChallenge });
  record('Policy_02_No_Disk_Secrets_Or_Challenges',
    !fs.existsSync(path.join(sandboxRoot, '.dsh-approval-secret')) && !fs.existsSync(path.join(sandboxRoot, 'approval-challenges.json')),
    { sandboxRoot },
  );

  {
    const ch = policy.createChallenge('solidworks_save_document', argsA, { sessionId: 's1', sessionCwd: sandboxRoot, callId: 'c1' });
    const resMut = policy.consumeChallengeAndGrant(ch.challengeId, 'solidworks_save_document', { path: targetB }, {
      sessionId: 's1', sessionCwd: sandboxRoot, callId: 'c1', outcome: 'allowed-once',
    });
    record('Policy_03_Arg_Mutation_Rejected', !resMut.ok && resMut.code === 'ARGUMENTS_MUTATED', resMut);

    const resTool = policy.consumeChallengeAndGrant(ch.challengeId, 'solidworks_export_active', argsA, {
      sessionId: 's1', sessionCwd: sandboxRoot, callId: 'c1', outcome: 'allowed-once',
    });
    record('Policy_04_Tool_Mismatch_Rejected', !resTool.ok && resTool.code === 'TOOL_MISMATCH', resTool);

    const resSess = policy.consumeChallengeAndGrant(ch.challengeId, 'solidworks_save_document', argsA, {
      sessionId: 's2', sessionCwd: sandboxRoot, callId: 'c1', outcome: 'allowed-once',
    });
    record('Policy_05_Session_Mismatch_Rejected', !resSess.ok && resSess.code === 'SESSION_MISMATCH', resSess);

    const resCwd = policy.consumeChallengeAndGrant(ch.challengeId, 'solidworks_save_document', argsA, {
      sessionId: 's1', sessionCwd: path.join(sandboxRoot, 'sub'), callId: 'c1', outcome: 'allowed-once',
    });
    record('Policy_06_SessionCwd_Mismatch_Rejected', !resCwd.ok && resCwd.code === 'SESSION_CWD_MISMATCH', resCwd);

    const resCall = policy.consumeChallengeAndGrant(ch.challengeId, 'solidworks_save_document', argsA, {
      sessionId: 's1', sessionCwd: sandboxRoot, callId: 'c2', outcome: 'allowed-once',
    });
    record('Policy_07_CallId_Mismatch_Rejected', !resCall.ok && resCall.code === 'CALL_ID_MISMATCH', resCall);

    const resNonAllow = policy.consumeChallengeAndGrant(ch.challengeId, 'solidworks_save_document', argsA, {
      sessionId: 's1', sessionCwd: sandboxRoot, callId: 'c1', outcome: 'allowed-always',
    });
    record('Policy_08_Strict_AllowedOnce_Only', !resNonAllow.ok && resNonAllow.code === 'APPROVAL_NOT_GRANTED', resNonAllow);

    // Legit consume once, then replay must fail
    const okGrant = policy.consumeChallengeAndGrant(ch.challengeId, 'solidworks_save_document', argsA, {
      sessionId: 's1', sessionCwd: sandboxRoot, callId: 'c1', outcome: 'allowed-once',
    });
    const replayGrant = policy.consumeChallengeAndGrant(ch.challengeId, 'solidworks_save_document', argsA, {
      sessionId: 's1', sessionCwd: sandboxRoot, callId: 'c1', outcome: 'allowed-once',
    });
    record('Policy_09_Single_Use_And_No_Replay', okGrant.ok && !replayGrant.ok && replayGrant.code === 'CHALLENGE_NOT_FOUND', { okGrant, replayGrant });
  }

  {
    const chExp = policy.createChallenge('solidworks_save_document', argsA, { sessionId: 's1', sessionCwd: sandboxRoot, callId: 'c-exp' });
    simNow += 3001;
    const resExp = policy.consumeChallengeAndGrant(chExp.challengeId, 'solidworks_save_document', argsA, {
      sessionId: 's1', sessionCwd: sandboxRoot, callId: 'c-exp', outcome: 'allowed-once',
    });
    record('Policy_10_Expired_Challenge_Rejected', !resExp.ok && resExp.code === 'CHALLENGE_EXPIRED', resExp);
  }

  // ---- D. 真实端到端 ctx.approval 通道门控（无批拒绝 + 并发重放 + 放行）------
  if (pythonPath) {
    // D1: No approval channel -> APPROVAL_CHANNEL_UNAVAILABLE
    const regNoChan = new Map();
    const stop1 = await apply(
      { tools: { register: (d) => { regNoChan.set(d.name, d); return () => {}; } } },
      { mode: 'full', pythonPath, serverScript: STUB_SERVER, serverCwd: path.dirname(STUB_SERVER), allowedRoots: [sandboxRoot] },
    );
    try {
      const r = JSON.parse((await regNoChan.get('stub_export').execute({ output_path: path.join(sandboxRoot, 'o.step') }, {})).text);
      record('Host_01_Missing_Channel_Fails_Closed', r.status === 'refused' && r.code === 'APPROVAL_CHANNEL_UNAVAILABLE', r);
    } finally {
      await stop1?.();
    }

    // D2: Slow approval -> concurrent duplicate callId -> APPROVAL_REPLAY; TTL expire -> CHALLENGE_EXPIRED; rejected/cancelled/allowed-once
    let releaseSlow = null;
    let modeBehavior = 'slow';
    const regHost = new Map();
    const hostCtx = {
      tools: { register: (d) => { regHost.set(d.name, d); return () => {}; } },
      agent: { session: { header: { id: 'sess-e2e', cwd: sandboxRoot } } },
      get: (k) => k === 'approval' ? {
        request: async ({ signal }) => {
          if (modeBehavior === 'slow') {
            return new Promise((resolve) => {
              releaseSlow = resolve;
              signal?.addEventListener('abort', () => resolve('cancelled'), { once: true });
            });
          }
          if (modeBehavior === 'hang-until-abort') {
            return new Promise((resolve) => {
              signal?.addEventListener('abort', () => resolve('cancelled'), { once: true });
            });
          }
          return modeBehavior;
        },
      } : undefined,
    };
    const stop2 = await apply(hostCtx, {
      mode: 'full',
      pythonPath,
      serverScript: STUB_SERVER,
      serverCwd: path.dirname(STUB_SERVER),
      allowedRoots: [sandboxRoot],
      challengeTtlMs: 250,
    });
    try {
      const exp = regHost.get('stub_export');
      // Concurrent replay check with same callId
      modeBehavior = 'slow';
      const p1 = exp.execute({ output_path: path.join(sandboxRoot, 'c.step') }, { callId: 'dup-call-1', agent: { session: { header: { id: 'sess-e2e', cwd: sandboxRoot } } } });
      await new Promise((r) => setTimeout(r, 20));
      const p2 = await exp.execute({ output_path: path.join(sandboxRoot, 'c.step') }, { callId: 'dup-call-1', agent: { session: { header: { id: 'sess-e2e', cwd: sandboxRoot } } } });
      releaseSlow?.('rejected');
      const r1 = JSON.parse((await p1).text);
      const r2 = JSON.parse(p2.text);
      record('Host_02_Concurrent_Same_CallId_Replay_Blocked', r2.code === 'APPROVAL_REPLAY' && r1.code === 'APPROVAL_REJECTED', { r1, r2 });

      // TTL expiration abort check
      modeBehavior = 'hang-until-abort';
      const rTtl = JSON.parse((await exp.execute({ output_path: path.join(sandboxRoot, 'ttl.step') }, { callId: 'ttl-call', agent: { session: { header: { id: 'sess-e2e', cwd: sandboxRoot } } } })).text);
      record('Host_03_TTL_Timeout_Aborts_And_Fails_Closed', rTtl.code === 'CHALLENGE_EXPIRED', rTtl);

      // Cancelled
      modeBehavior = 'cancelled';
      const rCan = JSON.parse((await exp.execute({ output_path: path.join(sandboxRoot, 'can.step') }, { callId: 'can-call', agent: { session: { header: { id: 'sess-e2e', cwd: sandboxRoot } } } })).text);
      record('Host_04_Cancelled_Blocked', rCan.code === 'APPROVAL_CANCELLED', rCan);

      // Allowed-once executes strictly once
      modeBehavior = 'allowed-once';
      const rOk = await exp.execute({ output_path: path.join(sandboxRoot, 'ok.step') }, { callId: 'ok-call', agent: { session: { header: { id: 'sess-e2e', cwd: sandboxRoot } } } });
      record('Host_05_AllowedOnce_Forwards_To_Server', String(rOk.text).includes('unknown tool'), { text: rOk.text });
    } finally {
      await stop2?.();
    }
  }
} finally {
  fs.rmSync(sandboxRoot, { recursive: true, force: true });
}

if (outputJson) {
  fs.mkdirSync(path.dirname(outputJson), { recursive: true });
  fs.writeFileSync(outputJson, JSON.stringify(results, null, 2), 'utf8');
}

console.log(`\nBUG-0002 Adversarial Summary: ${results.passed_tests}/${results.total_tests} passed, ${results.failed_tests} failed`);
process.exit(results.failed_tests === 0 ? 0 : 1);
