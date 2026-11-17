import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { apply } from '../lib/index.js';
import { Policy } from '../lib/policy.js';

const pythonExe = process.env.DSH_SOLIDWORKS_PYTHON || null;
const SANDBOX = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-sw-confirm-auth-'));

test('BUG-0002: solidworks_confirm always refuses AI self-authorization and disk approval store is eliminated', async () => {
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
        header: { id: 'test-session-123', cwd: SANDBOX },
      },
    },
  };

  const testTool = 'solidworks_save_document';
  const testArgs = { path: path.join(SANDBOX, 'part1.sldprt') };
  const stop = await apply(mockCtx, { mode: 'full', allowedRoots: [SANDBOX] });
  try {
    const confirmTool = registeredTools.get('solidworks_confirm');
    assert.ok(confirmTool, 'solidworks_confirm must be registered as fail-closed stub');

    for (const payload of [
      { tool: testTool, args: testArgs },
      { tool: testTool, args: testArgs, confirmedByHuman: true },
      { challengeId: 'chal_fake', ticket: '0'.repeat(64), tool: testTool, args: testArgs, reason: 'self-approve' },
    ]) {
      const res = await confirmTool.execute(payload);
      const data = JSON.parse(res.text);
      assert.equal(data.status, 'refused');
      assert.equal(data.code, 'SELF_APPROVAL_PROHIBITED');
    }
  } finally {
    await stop?.();
  }

  // No approval secrets or challenge files should ever exist on disk
  assert.equal(fs.existsSync(path.join(SANDBOX, '.dsh-approval-secret')), false);
  assert.equal(fs.existsSync(path.join(SANDBOX, 'approval-challenges.json')), false);

  // Policy itself keeps single-use binding & never accepts fabricated self-signed tickets
  const policy = new Policy({ mode: 'full', allowedRoots: [SANDBOX] });
  assert.equal(typeof policy.signChallenge, 'undefined');
  const ch = policy.createChallenge(testTool, testArgs, { sessionId: 's1', sessionCwd: SANDBOX, callId: 'c1' });
  const badOutcome = policy.consumeChallengeAndGrant(ch.challengeId, testTool, testArgs, {
    sessionId: 's1', sessionCwd: SANDBOX, callId: 'c1', outcome: 'rejected',
  });
  assert.equal(badOutcome.ok, false);

  const goodOutcome = policy.consumeChallengeAndGrant(ch.challengeId, testTool, testArgs, {
    sessionId: 's1', sessionCwd: SANDBOX, callId: 'c1', outcome: 'allowed-once',
  });
  assert.equal(goodOutcome.ok, true);

  // Replay fails closed
  const replay = policy.consumeChallengeAndGrant(ch.challengeId, testTool, testArgs, {
    sessionId: 's1', sessionCwd: SANDBOX, callId: 'c1', outcome: 'allowed-once',
  });
  assert.equal(replay.ok, false);
  assert.equal(replay.code, 'CHALLENGE_NOT_FOUND');

  fs.rmSync(SANDBOX, { recursive: true, force: true });
});

if (pythonExe) {
  test('BUG-0002: interactive host ctx.approval gates HIGH tools strictly fail-closed', async () => {
    const serverScript = path.resolve(import.meta.dirname, 'stub-server.py');
    let nextOutcome = 'rejected';
    const registered = new Map();
    const ctx = {
      tools: { register: (d) => { registered.set(d.name, d); return () => {}; } },
      get: (k) => (k === 'approval' ? { request: async () => nextOutcome } : undefined),
    };
    const sandbox = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-sw-host-auth-'));
    const stop = await apply(ctx, {
      mode: 'full',
      pythonPath: pythonExe,
      serverScript,
      serverCwd: import.meta.dirname,
      allowedRoots: [sandbox],
      toolTimeoutMs: 15000,
      startTimeoutMs: 15000,
    });
    try {
      const exp = registered.get('stub_export');
      assert.ok(exp);
      nextOutcome = 'rejected';
      const r1 = JSON.parse((await exp.execute({ output_path: path.join(sandbox, 'a.step') }, {})).text);
      assert.equal(r1.code, 'APPROVAL_REJECTED');

      nextOutcome = 'allowed-once';
      const r2 = await exp.execute({ output_path: path.join(sandbox, 'a.step') }, { callId: 'call-1' });
      assert.ok(String(r2.text).includes('unknown tool'));

      // Replay with no host approval -> rejected again (single-use)
      nextOutcome = 'cancelled';
      const r3 = JSON.parse((await exp.execute({ output_path: path.join(sandbox, 'a.step') }, { callId: 'call-2' })).text);
      assert.equal(r3.code, 'APPROVAL_CANCELLED');
    } finally {
      await stop?.();
      fs.rmSync(sandbox, { recursive: true, force: true });
    }
  });
}
