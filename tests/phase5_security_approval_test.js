import test from 'node:test';
import assert from 'node:assert/strict';
import { Policy, HIGH, WRITE, READ } from '../lib/policy.js';

test('Policy approvalMode defaults to balanced and supports custom modes', () => {
  const p1 = new Policy({ mode: 'full' });
  assert.equal(p1.approvalMode, 'balanced');

  const p2 = new Policy({ mode: 'full', approvalMode: 'strict' });
  assert.equal(p2.approvalMode, 'strict');
});

test('Session-scoped grant allows multiple invocations during TTL', () => {
  const p = new Policy({ mode: 'full' });
  const tool = 'solidworks_save_document';
  const args = { path: 'test_model.sldprt' };

  // 1. Initial evaluate requires confirmation
  const res1 = p.evaluate(tool, args, { sessionCwd: 'D:\\sandbox' });
  assert.equal(res1.allowed, false);
  assert.equal(res1.code, 'CONFIRMATION_REQUIRED');

  // 2. Grant session-scoped approval
  const grantRes = p.grant(tool, args, { scope: 'session' });
  assert.equal(grantRes.scope, 'session');

  // 3. First invocation allowed
  const res2 = p.evaluate(tool, args, { sessionCwd: 'D:\\sandbox' });
  assert.equal(res2.allowed, true);
  assert.equal(res2.granted, true);

  // 4. Second invocation still allowed (session scope not consumed)
  const res3 = p.evaluate(tool, { ...args, extra: 1 }, { sessionCwd: 'D:\\sandbox' });
  assert.equal(res3.allowed, true);
  assert.equal(res3.granted, true);
});

test('Single-use grant is consumed immediately upon first evaluation', () => {
  const p = new Policy({ mode: 'full' });
  const tool = 'solidworks_save_document';
  const args = { path: 'single_test.sldprt' };

  // Grant single-use
  p.grant(tool, args, { scope: 'single' });

  // First call succeeds
  const res1 = p.evaluate(tool, args, { sessionCwd: 'D:\\sandbox' });
  assert.equal(res1.allowed, true);

  // Second call must fail
  const res2 = p.evaluate(tool, args, { sessionCwd: 'D:\\sandbox' });
  assert.equal(res2.allowed, false);
  assert.equal(res2.code, 'CONFIRMATION_REQUIRED');
});
