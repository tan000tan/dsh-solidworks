import assert from 'node:assert/strict';
import test from 'node:test';

import { Policy, classify, canonicalArgs, READ, WRITE, HIGH, RISK_TABLE } from '../lib/policy.js';

test('every shipped tool has an explicit risk tier', () => {
  const names = Object.keys(RISK_TABLE);
  assert.ok(names.length >= 60, `expected the full 63-tool table, got ${names.length}`);
  for (const name of names) assert.ok([READ, WRITE, HIGH].includes(RISK_TABLE[name]), name);
});

test('unknown tools are never classified as read', () => {
  assert.equal(classify('solidworks_delete_everything'), HIGH);
  assert.equal(classify('solidworks_add_widget'), WRITE);
  assert.equal(classify('solidworks_something_new'), READ);
});

test('read-only mode publishes reads and withholds writes', () => {
  const policy = new Policy({ mode: 'read-only' });
  assert.equal(policy.registerable('solidworks_mass_properties'), true);
  assert.equal(policy.registerable('solidworks_sketch_and_extrude'), false);
  assert.equal(policy.registerable('solidworks_save_document'), false);

  const denied = policy.evaluate('solidworks_sketch_and_extrude', {});
  assert.equal(denied.allowed, false);
  assert.equal(denied.code, 'POLICY_MODE');
});

test('standard mode allows edits but withholds persistence', () => {
  const policy = new Policy({ mode: 'standard' });
  assert.equal(policy.evaluate('solidworks_sketch_and_extrude', {}).allowed, true);

  // High-risk tools are not published in standard mode at all, so a stray call is
  // refused by mode before any grant is consulted.
  assert.equal(policy.registerable('solidworks_save_document'), false);
  const save = policy.evaluate('solidworks_save_document', { path: 'C:\\work\\a.sldprt' });
  assert.equal(save.allowed, false);
  assert.equal(save.code, 'POLICY_MODE');
});

test('full mode still needs a grant for high-risk calls', () => {
  const policy = new Policy({ mode: 'full' });
  assert.equal(policy.registerable('solidworks_save_document'), true);
  assert.equal(policy.evaluate('solidworks_save_document', { path: 'C:\\work\\a.sldprt' }).code, 'CONFIRMATION_REQUIRED');
});

test('an explicitly allowed high-risk tool escapes the mode ceiling but not the grant', () => {
  const policy = new Policy({ mode: 'read-only', allow: ['solidworks_save_document'] });
  assert.equal(policy.registerable('solidworks_save_document'), true);
  assert.equal(policy.evaluate('solidworks_save_document', { path: 'C:\\work\\a.sldprt' }).code, 'CONFIRMATION_REQUIRED');
  policy.grant('solidworks_save_document', { path: 'C:\\work\\a.sldprt' });
  assert.equal(policy.evaluate('solidworks_save_document', { path: 'C:\\work\\a.sldprt' }).allowed, true);
});

test('high-risk calls need a single-use grant bound to the exact arguments', () => {
  let now = 1_000;
  const policy = new Policy({ mode: 'full', grantTtlMs: 500, now: () => now });

  policy.grant('solidworks_save_document', { path: 'C:\\work\\a.sldprt' });
  assert.equal(policy.evaluate('solidworks_save_document', { path: 'C:\\work\\a.sldprt' }).allowed, true);
  // Consumed: the second identical call needs a fresh grant.
  assert.equal(policy.evaluate('solidworks_save_document', { path: 'C:\\work\\a.sldprt' }).code, 'CONFIRMATION_REQUIRED');

  policy.grant('solidworks_save_document', { path: 'C:\\work\\a.sldprt' });
  assert.equal(policy.evaluate('solidworks_save_document', { path: 'C:\\work\\b.sldprt' }).code, 'CONFIRMATION_REQUIRED');

  now += 10_000;
  policy.grant('solidworks_save_document', { path: 'C:\\work\\a.sldprt' });
  now += 600;
  assert.equal(policy.evaluate('solidworks_save_document', { path: 'C:\\work\\a.sldprt' }).code, 'CONFIRMATION_REQUIRED');
});

test('deny list always wins over mode and allow list', () => {
  const policy = new Policy({ mode: 'full', allow: ['solidworks_export_active'], deny: ['solidworks_export_active'] });
  assert.equal(policy.registerable('solidworks_export_active'), false);
  assert.equal(policy.evaluate('solidworks_export_active', {}).code, 'TOOL_DENIED');
});

test('write calls outside the allowed roots are refused', () => {
  const policy = new Policy({ mode: 'standard', allowedRoots: ['C:\\work'] });
  assert.equal(policy.evaluate('solidworks_open_document', { path: 'C:\\work\\part.sldprt' }).allowed, true);
  assert.equal(policy.evaluate('solidworks_open_document', { path: 'C:\\windows\\system32\\x.sldprt' }).code, 'PATH_OUTSIDE_ALLOWED_ROOTS');
  // Reads are not path-gated: inspection never widens attacker control.
  assert.equal(policy.evaluate('solidworks_inspect_native_geometry', { expected_document_path: 'D:\\elsewhere\\part.sldprt' }).allowed, true);
});

test('session cwd is the default write root when none is configured', () => {
  const policy = new Policy({ mode: 'standard' });
  assert.equal(policy.evaluate('solidworks_open_document', { path: 'C:\\session\\x.sldprt' }, { sessionCwd: 'C:\\session' }).allowed, true);
  assert.equal(policy.evaluate('solidworks_open_document', { path: 'C:\\other\\x.sldprt' }, { sessionCwd: 'C:\\session' }).code, 'PATH_OUTSIDE_ALLOWED_ROOTS');
});

test('canonical args are order independent', () => {
  assert.equal(canonicalArgs({ b: 2, a: 1 }), canonicalArgs({ a: 1, b: 2 }));
  assert.notEqual(canonicalArgs({ a: 1 }), canonicalArgs({ a: '1' }));
});