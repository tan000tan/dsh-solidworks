// tests/audit_outcome.test.js
// RELEASE-SWARM-01 / BUG-009：审计必须按业务状态判定，而不是只看传输层 isError。
import test from 'node:test';
import assert from 'node:assert/strict';
import { businessOutcome } from '../lib/index.js';

const json = (obj) => ({ isError: false, content: [{ type: 'text', text: JSON.stringify(obj) }] });

test('transport error is never success', () => {
  assert.equal(businessOutcome({ isError: true, content: [{ type: 'text', text: '{"status":"ok"}' }] }), false);
});

test('business status ok is success', () => {
  assert.equal(businessOutcome(json({ status: 'ok' })), true);
});

test('business status error is failure even without isError', () => {
  assert.equal(businessOutcome(json({ status: 'error', message: 'DEF-SEC-01' })), false);
});

test('blocked is failure', () => {
  assert.equal(businessOutcome(json({ status: 'blocked' })), false);
});

test('refused is failure', () => {
  assert.equal(businessOutcome(json({ status: 'refused' })), false);
});

test('success:false is failure', () => {
  assert.equal(businessOutcome(json({ success: false })), false);
});

test('plain markdown text keeps transport verdict', () => {
  assert.equal(businessOutcome({ isError: false, content: [{ type: 'text', text: '# result\nfoo' }] }), true);
});

test('empty payload is success', () => {
  assert.equal(businessOutcome({ isError: false, content: [] }), true);
});
