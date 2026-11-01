import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {
  Policy,
  classify,
  canonicalArgs,
  READ,
  WRITE,
  HIGH,
  RISK_TABLE,
  isPathInside,
  realpathWithAncestorWalk,
} from '../lib/policy.js';

test('every shipped tool has an explicit risk tier', () => {
  const names = Object.keys(RISK_TABLE);
  assert.ok(names.length >= 60, `expected the full 66-tool table, got ${names.length}`);
  for (const name of names) assert.ok([READ, WRITE, HIGH].includes(RISK_TABLE[name]), name);
});

test('unknown tools are never classified as read (default to HIGH)', () => {
  assert.equal(classify('solidworks_delete_everything'), HIGH);
  assert.equal(classify('solidworks_add_widget'), WRITE);
  // Unknown tools without keywords default to HIGH, never READ
  assert.equal(classify('solidworks_something_new'), HIGH);
  assert.equal(classify('arbitrary_unknown_function'), HIGH);
  // Unknown casing variant without recognized verbs defaults to HIGH
  assert.equal(classify('SolidWorks_Custom_Inspection'), HIGH);
  // Casing variant with write verb is classified as WRITE, never READ
  assert.notEqual(classify('SolidWorks_Sketch_And_Extrude'), READ);
  // Fake stub_ prefix attempts never default to READ
  assert.equal(classify('stub_delete_database'), HIGH);
  assert.equal(classify('stub_arbitrary_name'), HIGH);
  assert.equal(classify('stub_fake_reader'), HIGH);
  assert.equal(classify('solidworks_mass_properties_v2'), HIGH);
});

test('unknown tools are refused by evaluate unless explicitly allowed', () => {
  const policy = new Policy({ mode: 'full' });
  const result = policy.evaluate('unrecognized_tool_xyz', {});
  assert.equal(result.allowed, false);
  assert.equal(result.code, 'TOOL_UNKNOWN');

  // Fake stub_ prefix tool is also rejected as TOOL_UNKNOWN
  const stubFake = policy.evaluate('stub_fake_tool', {});
  assert.equal(stubFake.allowed, false);
  assert.equal(stubFake.code, 'TOOL_UNKNOWN');

  // And registerable() rejects it across all modes
  assert.equal(policy.registerable('stub_fake_tool'), false);
  const readPolicy = new Policy({ mode: 'read-only' });
  assert.equal(readPolicy.registerable('stub_fake_tool'), false);
});

test('explicit customTiers allow explicit test binding without ambient prefix privileges', () => {
  const policy = new Policy({
    mode: 'read-only',
    customTiers: { explicit_test_tool: READ },
  });
  assert.equal(policy.registerable('explicit_test_tool'), true);
  assert.equal(policy.evaluate('explicit_test_tool', {}).allowed, true);

  // Unlisted stub tool remains rejected
  assert.equal(policy.registerable('stub_unlisted'), false);
});

test('solidworks_health_check start_solidworks=true side-effect is gated by policy mode', () => {
  const readPolicy = new Policy({ mode: 'read-only' });
  // Default (start_solidworks false or omitted) is purely read-only inspection
  assert.equal(readPolicy.evaluate('solidworks_health_check', {}).allowed, true);
  assert.equal(readPolicy.evaluate('solidworks_health_check', { start_solidworks: false }).allowed, true);

  // start_solidworks=true spawns a heavy process, blocked in read-only mode
  const blockedFlat = readPolicy.evaluate('solidworks_health_check', { start_solidworks: true });
  assert.equal(blockedFlat.allowed, false);
  assert.equal(blockedFlat.code, 'POLICY_MODE');
  assert.ok(blockedFlat.reason.includes('start_solidworks=true'));

  // Nested in FastMCP params object is also caught
  const blockedNested = readPolicy.evaluate('solidworks_health_check', { params: { start_solidworks: true } });
  assert.equal(blockedNested.allowed, false);
  assert.equal(blockedNested.code, 'POLICY_MODE');

  // Allowed in standard and full modes
  const stdPolicy = new Policy({ mode: 'standard' });
  assert.equal(stdPolicy.evaluate('solidworks_health_check', { start_solidworks: true }).allowed, true);
});

test('read-only mode publishes reads and withholds writes and high-risk tools', () => {
  const policy = new Policy({ mode: 'read-only' });
  assert.equal(policy.registerable('solidworks_mass_properties'), true);
  assert.equal(policy.registerable('solidworks_sketch_and_extrude'), false);
  assert.equal(policy.registerable('solidworks_save_document'), false);
  assert.equal(policy.registerable('unknown_tool'), false);

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
  const policy = new Policy({ mode: 'full', allowedRoots: ['C:\\work'] });
  assert.equal(policy.registerable('solidworks_save_document'), true);
  assert.equal(policy.evaluate('solidworks_save_document', { path: 'C:\\work\\a.sldprt' }).code, 'CONFIRMATION_REQUIRED');
});

test('an explicitly allowed high-risk tool escapes the mode ceiling but not the grant', () => {
  const policy = new Policy({ mode: 'read-only', allow: ['solidworks_save_document'], allowedRoots: ['C:\\work'] });
  assert.equal(policy.registerable('solidworks_save_document'), true);
  assert.equal(policy.evaluate('solidworks_save_document', { path: 'C:\\work\\a.sldprt' }).code, 'CONFIRMATION_REQUIRED');
  policy.grant('solidworks_save_document', { path: 'C:\\work\\a.sldprt' });
  assert.equal(policy.evaluate('solidworks_save_document', { path: 'C:\\work\\a.sldprt' }).allowed, true);
});

test('high-risk calls need a single-use grant bound to the exact arguments', () => {
  let now = 1_000;
  const policy = new Policy({ mode: 'full', grantTtlMs: 500, allowedRoots: ['C:\\work'], now: () => now });

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
  const policy = new Policy({ mode: 'full', allow: ['solidworks_export_active'], deny: ['solidworks_export_active'], allowedRoots: ['C:\\work'] });
  assert.equal(policy.registerable('solidworks_export_active'), false);
  assert.equal(policy.evaluate('solidworks_export_active', {}).code, 'TOOL_DENIED');
});

test('write calls outside the allowed roots are refused', () => {
  const policy = new Policy({ mode: 'standard', allowedRoots: ['C:\\work'] });
  assert.equal(policy.evaluate('solidworks_open_document', { path: 'C:\\work\\part.sldprt' }).allowed, true);
  assert.equal(policy.evaluate('solidworks_open_document', { path: 'C:\\windows\\system32\\x.sldprt' }).code, 'PATH_OUTSIDE_ALLOWED_ROOTS');
  // READ tools with paths outside allowed roots are now strictly gated (Fail-Closed)
  assert.equal(policy.evaluate('solidworks_inspect_native_geometry', { expected_document_path: 'D:\\elsewhere\\part.sldprt' }).code, 'PATH_OUTSIDE_ALLOWED_ROOTS');
  assert.equal(policy.evaluate('solidworks_inspect_native_geometry', { expected_document_path: 'C:\\work\\part.sldprt' }).allowed, true);
});

test('path traversal attempts using .. are caught and blocked', () => {
  const policy = new Policy({ mode: 'standard', allowedRoots: ['C:\\work'] });
  // Traversal trying to escape C:\work to C:\windows
  const escape = policy.evaluate('solidworks_open_document', { path: 'C:\\work\\..\\windows\\system32\\calc.exe' });
  assert.equal(escape.allowed, false);
  assert.equal(escape.code, 'PATH_OUTSIDE_ALLOWED_ROOTS');

  // Prefix collision test: C:\workspace must not match C:\work
  const prefixCollision = policy.evaluate('solidworks_open_document', { path: 'C:\\workspace\\model.sldprt' });
  assert.equal(prefixCollision.allowed, false);
  assert.equal(prefixCollision.code, 'PATH_OUTSIDE_ALLOWED_ROOTS');
});

test('relative paths are resolved against session cwd or allowed roots', () => {
  const policy = new Policy({ mode: 'standard', allowedRoots: ['C:\\work'] });
  // Valid relative path inside C:\work
  assert.equal(policy.evaluate('solidworks_open_document', { path: 'part.sldprt' }).allowed, true);
  assert.equal(policy.evaluate('solidworks_open_document', { path: '.\\sub\\part.sldprt' }).allowed, true);

  // Relative traversal escaping C:\work
  const escape = policy.evaluate('solidworks_open_document', { path: '..\\other\\part.sldprt' });
  assert.equal(escape.allowed, false);
  assert.equal(escape.code, 'PATH_OUTSIDE_ALLOWED_ROOTS');
});

test('session cwd is the default write root when none is configured', () => {
  const policy = new Policy({ mode: 'standard' });
  assert.equal(policy.evaluate('solidworks_open_document', { path: 'C:\\session\\x.sldprt' }, { sessionCwd: 'C:\\session' }).allowed, true);
  assert.equal(policy.evaluate('solidworks_open_document', { path: 'C:\\other\\x.sldprt' }, { sessionCwd: 'C:\\session' }).code, 'PATH_OUTSIDE_ALLOWED_ROOTS');
});

test('physical realpath with ancestor walk resolves uncreated targets correctly', () => {
  const resolved = realpathWithAncestorWalk('C:\\Users\\tester\\sub_uncreated_dir\\target.sldprt');
  assert.ok(resolved.toLowerCase().includes('sub_uncreated_dir'));
  assert.ok(resolved.toLowerCase().endsWith('target.sldprt'));

  // Cross drive isolation check
  assert.equal(isPathInside('D:\\other\\file.sldprt', 'C:\\work'), false);
});

test('DOS reserved device names and loopback UNC are refused (fail-closed)', () => {
  const policy = new Policy({ mode: 'standard', allowedRoots: ['C:\\work'] });
  assert.equal(policy.evaluate('solidworks_open_document', { path: 'C:\\work\\CON.sldprt' }).code, 'PATH_OUTSIDE_ALLOWED_ROOTS');
  assert.equal(policy.evaluate('solidworks_open_document', { path: 'C:\\work\\NUL' }).code, 'PATH_OUTSIDE_ALLOWED_ROOTS');
  assert.equal(policy.evaluate('solidworks_open_document', { path: '\\\\127.0.0.1\\c$\\work\\file.sldprt' }).code, 'PATH_OUTSIDE_ALLOWED_ROOTS');
});

test('canonical args are order independent', () => {
  assert.equal(canonicalArgs({ b: 2, a: 1 }), canonicalArgs({ a: 1, b: 2 }));
  assert.notEqual(canonicalArgs({ a: 1 }), canonicalArgs({ a: '1' }));
});

test('Windows Junction pointing outside allowedRoots is blocked by physical realpath', () => {
  const tmpBase = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-sw-fs-'));
  const sandbox = path.join(tmpBase, 'sandbox');
  const secretOutside = path.join(tmpBase, 'secret_outside');
  fs.mkdirSync(sandbox);
  fs.mkdirSync(secretOutside);

  const junctionPath = path.join(sandbox, 'junction_to_secret');
  try {
    fs.symlinkSync(secretOutside, junctionPath, 'junction');

    const targetInsideJunction = path.join(junctionPath, 'leak.sldprt');
    const isContained = isPathInside(targetInsideJunction, sandbox);
    assert.equal(isContained, false, 'Junction escaping sandbox must be detected as outside');

    const policy = new Policy({ mode: 'standard', allowedRoots: [sandbox] });
    const decision = policy.evaluate('solidworks_open_document', { path: targetInsideJunction });
    assert.equal(decision.allowed, false);
    assert.equal(decision.code, 'PATH_OUTSIDE_ALLOWED_ROOTS');
  } finally {
    try { fs.unlinkSync(junctionPath); } catch {}
    try { fs.rmdirSync(sandbox); } catch {}
    try { fs.rmdirSync(secretOutside); } catch {}
    try { fs.rmdirSync(tmpBase); } catch {}
  }
});

test('Windows Junction pointing inside allowedRoots allows uncreated files', () => {
  const tmpBase = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-sw-fs-'));
  const sandbox = path.join(tmpBase, 'sandbox');
  const realSub = path.join(sandbox, 'real_sub');
  fs.mkdirSync(sandbox);
  fs.mkdirSync(realSub);

  const junctionPath = path.join(sandbox, 'internal_junction');
  try {
    fs.symlinkSync(realSub, junctionPath, 'junction');

    const uncreatedTarget = path.join(junctionPath, 'new_model.sldprt');
    const isContained = isPathInside(uncreatedTarget, sandbox);
    assert.equal(isContained, true, 'Internal junction target must be recognized as inside sandbox');

    const policy = new Policy({ mode: 'standard', allowedRoots: [sandbox] });
    const decision = policy.evaluate('solidworks_create_basic_part', { output_path: uncreatedTarget });
    assert.equal(decision.allowed, true);
  } finally {
    try { fs.unlinkSync(junctionPath); } catch {}
    try { fs.rmdirSync(realSub); } catch {}
    try { fs.rmdirSync(sandbox); } catch {}
    try { fs.rmdirSync(tmpBase); } catch {}
  }
});

test('Multi-layer parameter extraction catches nested objects and arrays of paths', () => {
  const fullPolicy = new Policy({ mode: 'full', allowedRoots: ['C:\\work'] });
  // One file outside allowed roots in array
  const batchEscaping = fullPolicy.evaluate('solidworks_batch_export_files', {
    file_paths: ['C:\\work\\p1.sldprt', 'D:\\other\\p2.sldprt'],
    output_dir: 'C:\\work\\out',
  });
  assert.equal(batchEscaping.allowed, false);
  assert.equal(batchEscaping.code, 'PATH_OUTSIDE_ALLOWED_ROOTS');

  // Deeply nested custom spec_path parameter
  const nestedEscaping = fullPolicy.evaluate('design_spec_build', {
    nested: { spec_path: 'C:\\Windows\\System32\\calc.exe' },
  });
  assert.equal(nestedEscaping.allowed, false);
  assert.equal(nestedEscaping.code, 'PATH_OUTSIDE_ALLOWED_ROOTS');
});

test('calls with paths fail closed when allowedRoots and sessionCwd are missing', () => {
  const policy = new Policy({ mode: 'full' });
  const result = policy.evaluate('solidworks_open_document', { path: 'C:\\work\\part.sldprt' });
  assert.equal(result.allowed, false);
  assert.equal(result.code, 'PATH_OUTSIDE_ALLOWED_ROOTS');
});

test('read tool design_spec_validate cannot probe paths outside allowedRoots', () => {
  const policy = new Policy({ mode: 'read-only', allowedRoots: ['C:\\work'] });
  const result = policy.evaluate('design_spec_validate', { specPath: 'C:\\Windows\\System32\\config\\SAM' });
  assert.equal(result.allowed, false);
  assert.equal(result.code, 'PATH_OUTSIDE_ALLOWED_ROOTS');
});

test('evaluate returns normalized rewrittenArgs for relative paths', () => {
  const policy = new Policy({ mode: 'standard', allowedRoots: ['C:\\work'] });
  const result = policy.evaluate('solidworks_open_document', { path: 'part.sldprt' });
  assert.equal(result.allowed, true);
  assert.ok(result.rewrittenArgs);
  assert.equal(result.rewrittenArgs.path, path.resolve('C:\\work', 'part.sldprt'));
});

test('normalizePathArgs preserves bare filenames and business enums without path rewriting', () => {
  const policy = new Policy({ mode: 'standard', allowedRoots: ['C:\\work'] });
  const result = policy.evaluate('solidworks_create_drawing', {
    part_path: 'part.sldprt',
    drawing_filename: 'drawing.slddrw',
    template_type: 'A4',
    target: 'document',
    input: 'mm',
  });
  assert.equal(result.allowed, true);
  assert.ok(result.rewrittenArgs);
  // Real path is resolved to absolute
  assert.equal(result.rewrittenArgs.part_path, path.resolve('C:\\work', 'part.sldprt'));
  // Bare filename is preserved intact (NOT prepended with directory)
  assert.equal(result.rewrittenArgs.drawing_filename, 'drawing.slddrw');
  // Business enums are preserved intact
  assert.equal(result.rewrittenArgs.template_type, 'A4');
  assert.equal(result.rewrittenArgs.target, 'document');
  assert.equal(result.rewrittenArgs.input, 'mm');
});

test('bare filename with traversal attempts is blocked outside allowedRoots', () => {
  const policy = new Policy({ mode: 'standard', allowedRoots: ['C:\\work'] });
  const result = policy.evaluate('solidworks_create_drawing', {
    part_path: 'C:\\work\\part.sldprt',
    drawing_filename: '..\\secret\\leak.slddrw',
  });
  assert.equal(result.allowed, false);
  assert.equal(result.code, 'PATH_OUTSIDE_ALLOWED_ROOTS');
});

test('remote UNC paths are rejected fail-closed to prevent SMB NTLM hash leakage', () => {
  const policy = new Policy({ mode: 'standard', allowedRoots: ['C:\\work'] });
  const result = policy.evaluate('solidworks_open_document', {
    path: '\\\\evil.attacker.com\\share\\part.sldprt',
  });
  assert.equal(result.allowed, false);
  assert.equal(result.code, 'PATH_OUTSIDE_ALLOWED_ROOTS');
});
