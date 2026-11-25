import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import {
  getDshHome,
  getDshDesktopProfileDir,
  resolveSandboxDir,
  verifyPluginEntry,
  isInstalledAsDshBundle,
  registerToDshProfile,
  unregisterFromDshProfile,
  checkDshRegistration,
} from '../scripts/dsh_adapter.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');

test('DSH_HOME / DSH_PROFILE_DIR env isolation overrides host paths', () => {
  const prevHome = process.env.DSH_HOME;
  const prevProf = process.env.DSH_PROFILE_DIR;
  try {
    const tmpHome = path.join(os.tmpdir(), 'dsh-env-test-home');
    process.env.DSH_HOME = tmpHome;
    delete process.env.DSH_PROFILE_DIR;
    assert.equal(getDshHome(), path.resolve(tmpHome));
    assert.equal(getDshDesktopProfileDir(), path.join(path.resolve(tmpHome), 'profiles', 'desktop'));

    const customProf = path.join(os.tmpdir(), 'dsh-env-custom-prof');
    process.env.DSH_PROFILE_DIR = customProf;
    assert.equal(getDshDesktopProfileDir(), path.resolve(customProf));
  } finally {
    if (prevHome === undefined) delete process.env.DSH_HOME; else process.env.DSH_HOME = prevHome;
    if (prevProf === undefined) delete process.env.DSH_PROFILE_DIR; else process.env.DSH_PROFILE_DIR = prevProf;
  }
});

test('cordis.patch.yml register / idempotency / legacy-repair / unregister preserves sibling entries', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-adapter-yml-'));
  const profileDir = path.join(tmp, 'profiles', 'desktop');
  fs.mkdirSync(profileDir, { recursive: true });
  const patchFile = path.join(profileDir, 'cordis.patch.yml');

  try {
    // 1. Start from empty []
    fs.writeFileSync(patchFile, '[]\n', 'utf8');
    const r1 = registerToDshProfile({
      pythonPath: 'C:\\Tools\\Python\\python.exe',
      mode: 'read-only',
      toolTimeoutMs: 300000,
      pluginRoot: ROOT,
      profileDir,
    });
    assert.equal(r1.ok, true);
    assert.equal(r1.action, 'appended-insert');
    const yml1 = fs.readFileSync(patchFile, 'utf8');
    assert.ok(yml1.includes('- insert:'), 'must register inside - insert:');
    assert.ok(yml1.includes("pythonPath: 'C:\\Tools\\Python\\python.exe'"), 'single-quoted YAML path must not double backslashes');
    assert.ok(!yml1.includes('C:\\\\Tools'), 'must never emit doubled backslashes in YAML single quotes');
    assert.deepEqual(checkDshRegistration(profileDir).shape, 'insert');
    assert.equal(checkDshRegistration(profileDir).registered, true);

    // 2. Idempotent re-run
    const r2 = registerToDshProfile({
      pythonPath: 'C:\\Tools\\Python\\python.exe',
      mode: 'read-only',
      toolTimeoutMs: 300000,
      pluginRoot: ROOT,
      profileDir,
    });
    assert.equal(r2.ok, true);
    assert.equal(r2.action, 'unchanged');

    // 3. Unregister removes insert shell and restores []
    const u1 = unregisterFromDshProfile(profileDir);
    assert.equal(u1.ok, true);
    assert.equal(u1.removed, true);
    assert.equal(fs.readFileSync(patchFile, 'utf8').trim(), '[]');

    // 4. Legacy override detection and repair
    fs.writeFileSync(patchFile, '- insert:\n\n- id: dsh-solidworks\n  config:\n    mode: read-only\n', 'utf8');
    const cLegacy = checkDshRegistration(profileDir);
    assert.equal(cLegacy.registered, false);
    assert.equal(cLegacy.shape, 'legacy-override');

    const rRepair = registerToDshProfile({
      pythonPath: 'D:\\py\\python.exe',
      mode: 'full',
      pluginRoot: ROOT,
      profileDir,
    });
    assert.equal(rRepair.ok, true);
    assert.equal(rRepair.action, 'repaired-legacy-entry');
    assert.equal(checkDshRegistration(profileDir).registered, true);

    // 5. Sibling child inside - insert: must survive unregister
    fs.writeFileSync(
      patchFile,
      [
        '- insert:',
        '    - id: other-plugin',
        '      name: other-plugin',
        '    - id: dsh-solidworks',
        '      name: dsh-solidworks',
        '      config:',
        '        mode: read-only',
        '',
      ].join('\n'),
      'utf8',
    );
    const uSibling = unregisterFromDshProfile(profileDir);
    assert.equal(uSibling.ok, true);
    assert.equal(uSibling.removed, true);
    const afterSibling = fs.readFileSync(patchFile, 'utf8');
    assert.ok(afterSibling.includes('- insert:') && afterSibling.includes('other-plugin'));
    assert.ok(!afterSibling.includes('dsh-solidworks'));
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test('re-register preserves user security keys (auditLog / allow / customTiers) instead of dropping them', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-adapter-merge-'));
  const profileDir = path.join(tmp, 'profiles', 'desktop');
  fs.mkdirSync(profileDir, { recursive: true });
  const patchFile = path.join(profileDir, 'cordis.patch.yml');
  try {
    fs.writeFileSync(
      patchFile,
      [
        '- insert:',
        '    - id: dsh-solidworks',
        '      name: dsh-solidworks',
        '      config:',
        '        mode: read-only',
        "        pythonPath: 'D:\\old\\python.exe'",
        '        toolTimeoutMs: 300000',
        "        auditLog: 'D:\\logs\\sw-audit.log'",
        '        allow:',
        '          - solidworks_save_document',
        '        customTiers:',
        '          solidworks_mass_properties: read',
        '',
      ].join('\n'),
      'utf8',
    );

    const r = registerToDshProfile({
      pythonPath: 'C:\\New\\python.exe',
      mode: 'standard',
      toolTimeoutMs: 120000,
      pluginRoot: ROOT,
      profileDir,
    });
    assert.equal(r.ok, true);
    assert.equal(r.action, 'updated-in-insert');
    const yml = fs.readFileSync(patchFile, 'utf8');
    assert.ok(yml.includes("pythonPath: 'C:\\New\\python.exe'"), 'managed pythonPath must be updated');
    assert.ok(!yml.includes('D:\\old\\python.exe'), 'stale pythonPath must be replaced');
    assert.ok(yml.includes('mode: standard'), 'managed mode must be updated');
    assert.ok(yml.includes('toolTimeoutMs: 120000'), 'managed toolTimeoutMs must be updated');
    assert.ok(yml.includes("auditLog: 'D:\\logs\\sw-audit.log'"), 'user auditLog must survive re-register');
    assert.ok(yml.includes('solidworks_save_document'), 'user allow list must survive re-register');
    assert.ok(yml.includes('customTiers:') && yml.includes('solidworks_mass_properties: read'), 'user customTiers must survive re-register');

    const again = registerToDshProfile({
      pythonPath: 'C:\\New\\python.exe',
      mode: 'standard',
      toolTimeoutMs: 120000,
      pluginRoot: ROOT,
      profileDir,
    });
    assert.equal(again.action, 'unchanged', 'merged re-register must stay idempotent');
    assert.ok(fs.readFileSync(patchFile, 'utf8').includes("auditLog: 'D:\\logs\\sw-audit.log'"));
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test('uninstall.js unregisters cordis.patch.yml even when zero local runtime items exist', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-uninstall-iso-'));
  const profileDir = path.join(tmp, 'dsh_home', 'profiles', 'desktop');
  fs.mkdirSync(profileDir, { recursive: true });
  const patchFile = path.join(profileDir, 'cordis.patch.yml');
  try {
    fs.writeFileSync(patchFile, '[]\n', 'utf8');
    registerToDshProfile({ mode: 'read-only', pluginRoot: ROOT, profileDir });
    assert.equal(checkDshRegistration(profileDir).registered, true);

    // Run in dry-run check first? No, test isolated sandbox profile unregister with --yes when no .venv exists in a temp copy or check behavior:
    // Wait: avoid deleting ROOT's own files! Instead test with --dry-run (safe) or test uninstall against isolated plugin copy!
    const isoPlugin = path.join(tmp, 'iso-plugin');
    fs.mkdirSync(path.join(isoPlugin, 'scripts'), { recursive: true });
    fs.mkdirSync(path.join(isoPlugin, 'lib'), { recursive: true });
    fs.copyFileSync(path.join(ROOT, 'scripts', 'uninstall.js'), path.join(isoPlugin, 'scripts', 'uninstall.js'));
    fs.copyFileSync(path.join(ROOT, 'scripts', 'dsh_adapter.js'), path.join(isoPlugin, 'scripts', 'dsh_adapter.js'));

    const res = spawnSync(process.execPath, [path.join(isoPlugin, 'scripts', 'uninstall.js'), '--yes'], {
      cwd: isoPlugin,
      // DSH_PROFILE_DIR from the host shell would otherwise point the child at the real desktop
      // profile; always pin it to the isolated temp profile (test must never touch user config).
      env: {
        ...process.env,
        DSH_HOME: path.join(tmp, 'dsh_home'),
        DSH_PROFILE_DIR: profileDir,
      },
      encoding: 'utf8',
    });
    assert.equal(res.status, 0, res.stderr || res.stdout);
    assert.equal(checkDshRegistration(profileDir).registered, false, 'uninstall must unregister profile even when 0 temp files existed');
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test('verifyPluginEntry validates canonical src/lib/index.js and resolveSandboxDir avoids node_modules by default', async () => {
  const okRes = await verifyPluginEntry(ROOT);
  assert.equal(okRes.ok, true, okRes.reason);

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-sandbox-res-'));
  try {
    const resolved = resolveSandboxDir(tmp);
    assert.ok(resolved.endsWith(path.join('Documents', 'DSH-SolidWorks', 'models')), `unexpected default sandbox: ${resolved}`);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test('isInstalledAsDshBundle skips writing duplicate cordis.patch.yml entries in DSH bundle mode', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-bundle-guard-'));
  const profileDir = path.join(tmp, 'profiles', 'desktop');
  const bundlePluginDir = path.join(profileDir, 'node_modules', 'dsh-solidworks');
  fs.mkdirSync(bundlePluginDir, { recursive: true });
  const patchFile = path.join(profileDir, 'cordis.patch.yml');
  const pkgFile = path.join(profileDir, 'package.json');

  try {
    fs.writeFileSync(patchFile, '[]\n', 'utf8');
    fs.writeFileSync(
      pkgFile,
      JSON.stringify({
        name: 'desktop-profile',
        dependencies: { 'dsh-solidworks': 'file:dsh-solidworks-0.3.3.tgz' },
        dsh: { profile: { bundles: ['dsh-solidworks'] } },
      }, null, 2),
      'utf8',
    );

    const b1 = isInstalledAsDshBundle(bundlePluginDir, profileDir);
    assert.equal(b1.isBundle, true);

    const bOutside = isInstalledAsDshBundle(ROOT, profileDir);
    assert.equal(bOutside.isBundle, false);

    const res = registerToDshProfile({
      pythonPath: 'C:\\Tools\\Python\\python.exe',
      mode: 'read-only',
      pluginRoot: bundlePluginDir,
      profileDir,
    });
    assert.equal(res.ok, true);
    assert.equal(res.skipped, true);
    assert.equal(res.action, 'skipped-bundle-mode');
    assert.equal(fs.readFileSync(patchFile, 'utf8'), '[]\n', 'cordis.patch.yml must remain untouched in bundle mode');
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});
