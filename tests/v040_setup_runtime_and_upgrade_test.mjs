import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';

import { restoreFromBackup } from '../scripts/upgrade.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const plugin = await import(pathToFileURL(path.join(ROOT, 'lib', 'index.js')).href);

function makeMockCtx({ approvalOutcome = 'allowed-once', hasApprovalSvc = true } = {}) {
  const registered = new Map();
  const requestedApprovals = [];
  const approval = hasApprovalSvc ? {
    async request(params) {
      requestedApprovals.push(params);
      return approvalOutcome;
    },
  } : null;

  return {
    registered,
    requestedApprovals,
    approval,
    get(name) {
      if (name === 'approval') return approval;
      return undefined;
    },
    tools: {
      async register(definition) {
        registered.set(definition.name, definition);
        return () => registered.delete(definition.name);
      },
      guard() { return () => {}; },
    },
    logger: { info() {}, warn() {}, error() {}, debug() {} },
  };
}

test('P0-1: solidworks_setup_runtime fails closed when ctx.approval is unavailable', async () => {
  const ctx = makeMockCtx({ hasApprovalSvc: false });
  const cleanup = await plugin.apply(ctx, { mode: 'read-only' });
  try {
    const setupTool = ctx.registered.get('solidworks_setup_runtime');
    assert.ok(setupTool, 'solidworks_setup_runtime must be published as a host meta-tool');

    const res = await setupTool.execute({});
    const payload = JSON.parse(res.text);
    assert.equal(payload.status, 'refused');
    assert.equal(payload.code, 'APPROVAL_CHANNEL_UNAVAILABLE');
    assert.ok(payload.fallbackCommand.includes('npm run setup'));
  } finally {
    await cleanup?.();
  }
});

test('P0-1: solidworks_setup_runtime fails closed when operator rejects approval', async () => {
  const ctx = makeMockCtx({ approvalOutcome: 'rejected' });
  const cleanup = await plugin.apply(ctx, { mode: 'read-only' });
  try {
    const setupTool = ctx.registered.get('solidworks_setup_runtime');
    const res = await setupTool.execute({});
    const payload = JSON.parse(res.text);
    assert.equal(payload.status, 'refused');
    assert.equal(payload.code, 'APPROVAL_REJECTED');
    assert.equal(ctx.requestedApprovals.length, 1);
    assert.ok(payload.fallbackCommand.includes('npm run setup'));
  } finally {
    await cleanup?.();
  }
});

test('P0-1: upgrade.js restoreFromBackup logs copy errors instead of swallowing them', () => {
  const tmpBackup = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-upg-bak-'));
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-upg-root-'));
  try {
    fs.writeFileSync(path.join(tmpBackup, 'package.json'), '{"name":"bak"}', 'utf8');
    // Create package.json as directory in root to trigger copyFileSync failure
    fs.mkdirSync(path.join(tmpRoot, 'package.json'));

    const restored = restoreFromBackup(tmpBackup, tmpRoot, path.join(tmpRoot, 'profiles'));
    assert.ok(!restored.includes('package.json'), 'package.json copy failed so it should not be listed as restored');
  } finally {
    fs.rmSync(tmpBackup, { recursive: true, force: true });
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});
