import test from 'node:test';
import assert from 'node:assert/strict';
import os from 'node:os';
import path from 'node:path';
import { Policy, HIGH, WRITE, READ } from '../lib/policy.js';

const CONDITIONAL_SAVE_TOOLS = [
  ['solidworks_update_dimension', { dimension_name: 'D1@Sketch1', value_mm: 10 }],
  ['solidworks_create_configuration', { configuration_name: 'CfgA' }],
  ['solidworks_activate_configuration', { configuration_name: 'Default' }],
  ['solidworks_set_custom_properties', { properties: { Material: 'Steel' } }],
];

const INVALID_BOOL_INPUTS = [
  'true',
  'false',
  'True',
  'False',
  'y',
  'Y',
  't',
  'T',
  'yes',
  'no',
  'on',
  'off',
  '1',
  '0',
  1,
  0,
  null,
  [],
  {},
];

test('R1 (AUD-SEC-001): conditional save tools enforce strict JSON boolean and never downgrade invalid save to WRITE', () => {
  const sandbox = os.tmpdir();
  const pStandard = new Policy({ mode: 'standard', allowedRoots: [sandbox] });
  const pFull = new Policy({ mode: 'full', allowedRoots: [sandbox] });

  for (const [tool, base] of CONDITIONAL_SAVE_TOOLS) {
    // Missing or strict false => WRITE (allowed in standard)
    assert.equal(pStandard.tierOf(tool, { params: base }), WRITE);
    assert.equal(pStandard.tierOf(tool, { params: { ...base, save: false } }), WRITE);
    assert.equal(pStandard.evaluate(tool, { params: base }, { sessionCwd: sandbox }).allowed, true);
    assert.equal(pStandard.evaluate(tool, { params: { ...base, save: false } }, { sessionCwd: sandbox }).allowed, true);

    // Strict true => HIGH (blocked in standard, confirmation required in full)
    assert.equal(pStandard.tierOf(tool, { params: { ...base, save: true } }), HIGH);
    const stdTrue = pStandard.evaluate(tool, { params: { ...base, save: true } }, { sessionCwd: sandbox });
    assert.equal(stdTrue.allowed, false);
    assert.equal(stdTrue.code, 'POLICY_MODE');

    const fullTrue = pFull.evaluate(tool, { params: { ...base, save: true } }, { sessionCwd: sandbox });
    assert.equal(fullTrue.allowed, false);
    assert.equal(fullTrue.code, 'CONFIRMATION_REQUIRED');

    // All non-boolean inputs => tierOf stays HIGH (fail-closed) AND evaluate refuses with INVALID_ARGUMENT_TYPE
    for (const bad of INVALID_BOOL_INPUTS) {
      for (const payload of [{ params: { ...base, save: bad } }, { ...base, save: bad }]) {
        assert.equal(pStandard.tierOf(tool, payload), HIGH, `${tool} with save=${JSON.stringify(bad)} must never downgrade to WRITE`);
        const resStd = pStandard.evaluate(tool, payload, { sessionCwd: sandbox });
        assert.equal(resStd.allowed, false);
        assert.equal(resStd.code, 'INVALID_ARGUMENT_TYPE');

        const resFull = pFull.evaluate(tool, payload, { sessionCwd: sandbox });
        assert.equal(resFull.allowed, false);
        assert.equal(resFull.code, 'INVALID_ARGUMENT_TYPE');
      }
    }

    // AUD-MCP-001: Conflicting top-level vs params.save => refused fail-closed
    const conflictRes = pStandard.evaluate(tool, { save: true, params: { ...base, save: false } }, { sessionCwd: sandbox });
    assert.equal(conflictRes.allowed, false);
    assert.equal(conflictRes.code, 'INVALID_ARGUMENTS');
  }
});

test('R1 same-root: solidworks_health_check start_solidworks enforces strict boolean in all modes', () => {
  const sandbox = os.tmpdir();
  const pReadOnly = new Policy({ mode: 'read-only', allowedRoots: [sandbox] });

  assert.equal(pReadOnly.tierOf('solidworks_health_check', { params: {} }), READ);
  assert.equal(pReadOnly.evaluate('solidworks_health_check', { params: { start_solidworks: false } }, { sessionCwd: sandbox }).allowed, true);

  const roTrue = pReadOnly.evaluate('solidworks_health_check', { params: { start_solidworks: true } }, { sessionCwd: sandbox });
  assert.equal(roTrue.allowed, false);
  assert.equal(roTrue.code, 'POLICY_MODE');

  for (const bad of INVALID_BOOL_INPUTS) {
    const res = pReadOnly.evaluate('solidworks_health_check', { params: { start_solidworks: bad } }, { sessionCwd: sandbox });
    assert.equal(res.allowed, false);
    assert.equal(res.code, 'INVALID_ARGUMENT_TYPE');
  }
});

test('AUD-SEC-002: session-scoped grant binds canonicalArgs digest and rejects parameter or target mutation', () => {
  const sandbox = os.tmpdir();
  const p = new Policy({ mode: 'full', allowedRoots: [sandbox] });
  const targetA = path.join(sandbox, 'part_a.step');
  const targetB = path.join(sandbox, 'part_b.step');
  const argsA = { output_path: targetA, overwrite: false };

  p.grant('solidworks_export_active', argsA, { scope: 'session', sessionId: 's1', channel: 'host-ui' });

  // Exact same args repeated in same session => allowed
  assert.equal(p.evaluate('solidworks_export_active', argsA, { sessionId: 's1', callId: 'c1', sessionCwd: sandbox }).allowed, true);
  assert.equal(p.evaluate('solidworks_export_active', { overwrite: false, output_path: targetA }, { sessionId: 's1', callId: 'c2', sessionCwd: sandbox }).allowed, true);

  // Mutated overwrite => refused
  const mutOverwrite = p.evaluate('solidworks_export_active', { output_path: targetA, overwrite: true }, { sessionId: 's1', callId: 'c3', sessionCwd: sandbox });
  assert.equal(mutOverwrite.allowed, false);
  assert.equal(mutOverwrite.code, 'CONFIRMATION_REQUIRED');

  // Mutated target file => refused
  const mutTarget = p.evaluate('solidworks_export_active', { output_path: targetB, overwrite: false }, { sessionId: 's1', callId: 'c4', sessionCwd: sandbox });
  assert.equal(mutTarget.allowed, false);
  assert.equal(mutTarget.code, 'CONFIRMATION_REQUIRED');

  // Different session => refused
  const diffSession = p.evaluate('solidworks_export_active', argsA, { sessionId: 's2', callId: 'c5', sessionCwd: sandbox });
  assert.equal(diffSession.allowed, false);
  assert.equal(diffSession.code, 'CONFIRMATION_REQUIRED');
});
