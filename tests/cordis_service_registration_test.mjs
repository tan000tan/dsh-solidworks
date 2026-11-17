import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import * as plugin from '../lib/index.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));

function makeStrictCordisContext({ presetProp = null, existingService = undefined } = {}) {
  const services = new Map();
  if (existingService !== undefined) services.set('solidworks', existingService);
  const tools = new Map();
  const disposables = [];
  const props = {};
  if (presetProp) props.solidworks = presetProp;

  const ctx = {
    reflect: {
      props,
      get(name) {
        return services.get(name);
      },
    },
    get(name) {
      return services.get(name);
    },
    provide(name, value) {
      if (!plugin.provide.includes(name)) {
        throw new Error(`cannot provide undeclared service "${name}"`);
      }
      props[name] = { type: 'service' };
      services.set(name, value);
    },
    tools: {
      register(def) {
        tools.set(def.name, def);
        return () => tools.delete(def.name);
      },
    },
    logger() {
      return { info() {}, warn() {}, error() {}, debug() {} };
    },
    on(event, fn) {
      if (event === 'dispose') disposables.push(fn);
      return () => {};
    },
    effect(fn) {
      const res = fn();
      if (typeof res === 'function') disposables.push(res);
      return () => {};
    },
  };

  Object.defineProperty(ctx, 'solidworks', {
    enumerable: true,
    configurable: true,
    get() {
      return services.get('solidworks');
    },
    set() {
      throw new Error('direct ctx.solidworks assignment blocked in strict Cordis mode');
    },
  });

  return { ctx, tools, services, disposables };
}

test('Cordis export contract & frozen service surface activation', async () => {
  assert.equal(plugin.name, 'dsh-solidworks');
  assert.ok(Array.isArray(plugin.inject) && plugin.inject.includes('tools'), 'inject must include tools');
  assert.ok(Array.isArray(plugin.provide) && plugin.provide.includes('solidworks'), 'provide must include solidworks');
  assert.equal(typeof plugin.apply, 'function');

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-cordis-reg-'));
  const { ctx, tools, services, disposables } = makeStrictCordisContext();
  let cleanup;
  try {
    cleanup = await plugin.apply(ctx, {
      mode: 'full',
      allowedRoots: [tmp],
      auditLog: path.join(tmp, 'audit.jsonl'),
      // Isolate test completely from host Python / .dsh runtimes:
      // Cordis service registration & meta tools must succeed even before Python backend connects.
      pythonPath: path.join(tmp, 'nonexistent-python.exe'),
      startTimeoutMs: 5_000,
    });

    const svc = services.get('solidworks');
    assert.ok(svc && Object.isFrozen(svc), 'provided solidworks service must be frozen');
    assert.equal(typeof svc.getPendingChallenge, 'function');
    assert.equal(typeof svc.listPendingChallenges, 'function');
    assert.equal(typeof svc.status, 'function');
    assert.deepEqual(svc.listPendingChallenges(), []);
    assert.equal(svc.getPendingChallenge('nonexistent'), null);

    const status = svc.status();
    assert.equal(status.plugin?.name, 'dsh-solidworks');
    assert.equal(status.policy?.mode, 'full');
    assert.equal(tools.has('solidworks_status'), true);
    assert.equal(tools.has('solidworks_confirm'), true);
  } finally {
    await cleanup?.();
    for (const fn of disposables) await fn();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test('Cordis cross-Fiber non-service property conflict raises explicit error', async () => {
  const { ctx } = makeStrictCordisContext({ presetProp: { type: 'alias' } });
  await assert.rejects(
    () => plugin.apply(ctx, { mode: 'read-only' }),
    /property "solidworks" is already declared as alias/,
  );
});

test('Cordis skips duplicate provide when service already registered', async () => {
  const sentinel = Object.freeze({ existing: true });
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-cordis-dup-'));
  const { ctx, services, disposables } = makeStrictCordisContext({ existingService: sentinel });
  let cleanup;
  try {
    cleanup = await plugin.apply(ctx, {
      mode: 'read-only',
      allowedRoots: [tmp],
      auditLog: path.join(tmp, 'audit.jsonl'),
      pythonPath: path.join(tmp, 'nonexistent-python.exe'),
      startTimeoutMs: 5_000,
    });
    assert.equal(services.get('solidworks'), sentinel, 'existing service must remain untouched');
  } finally {
    await cleanup?.();
    for (const fn of disposables) await fn();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});
