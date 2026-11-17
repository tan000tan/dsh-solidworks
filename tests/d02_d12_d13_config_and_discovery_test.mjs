import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { discover, entryCandidates, PROBE_SOURCE } from '../lib/discover.js';

const PLUGIN_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

test('D-02 / D-13 / D-17: PROBE_SOURCE reports COMDEP and entryCandidates honors DSH_HOME', () => {
  assert.match(PROBE_SOURCE, /COMDEP=/);
  assert.match(PROBE_SOURCE, /comtypes/);
  assert.match(PROBE_SOURCE, /win32com/);

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-sw-d13-'));
  try {
    const customPy = path.join(tmp, 'dsh-runtimes', 'dsh-primary-runtime', 'dependencies', 'python', 'python.exe');
    fs.mkdirSync(path.dirname(customPy), { recursive: true });
    fs.writeFileSync(customPy, 'stub', 'utf8');

    const candidates = entryCandidates({ DSH_HOME: tmp }, PLUGIN_ROOT);
    const paths = candidates.map((c) => path.resolve(c.command));
    assert.ok(paths.includes(path.resolve(customPy)), 'entryCandidates must include DSH_HOME runtime python');
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test('D-17: explicit config.pythonPath emits COMDEP warning when optional comtypes is absent', async () => {
  const candidates = entryCandidates(process.env, PLUGIN_ROOT);
  const dshPy = path.join(
    process.env.USERPROFILE || '',
    '.dsh',
    'dsh-runtimes',
    'dsh-primary-runtime',
    'dependencies',
    'python',
    'python.exe',
  );
  if (!fs.existsSync(dshPy)) {
    return; // Skip if local runtime python does not exist
  }
  const res = await discover({
    pluginRoot: PLUGIN_ROOT,
    config: { pythonPath: dshPy },
    env: process.env,
  });
  assert.equal(res.ok, true);
  assert.equal(typeof res.python.comDeps, 'boolean');
  assert.ok(res.notes.some((n) => n.startsWith('python: ')));
  if (res.python.comDeps === false) {
    assert.ok(res.notes.some((n) => n.includes('comtypes')), 'explicit pythonPath path must warn about missing comtypes');
  }
});
