import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { embeddedCandidates, tryAutoBootstrap, discover } from '../lib/discover.js';

test('embeddedCandidates discovers .runtime/python/python.exe when present', () => {
  const dummyRoot = 'C:\\dummy_plugin_root';
  const list = embeddedCandidates(dummyRoot);
  assert.ok(Array.isArray(list));
});

test('discover returns friendly Chinese diagnostic when interpreter cannot be found', async () => {
  const res = await discover({
    pluginRoot: process.cwd(),
    config: { pythonPath: 'C:\\non_existent_fake_dir\\python.exe' },
  });
  assert.equal(res.ok, false);
  assert.equal(res.code, 'PYTHON_INVALID');
  assert.ok(res.message.includes('configured pythonPath failed the import check'));
});

test('discover succeeds with valid active python interpreter', async () => {
  const res = await discover({
    pluginRoot: process.cwd(),
    config: {},
    env: { DSH_SOLIDWORKS_PYTHON: 'D:\\SWCAD-MCP\\Python313\\python.exe' }
  });
  assert.equal(res.ok, true);
  assert.ok(res.python.command.toLowerCase().includes('python'));
  assert.ok(res.serverScript.endsWith('server.py'));
});
