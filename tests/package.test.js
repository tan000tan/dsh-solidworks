// Packaging integrity: catches the mistakes that only show up after publish —
// a manifest pointing at a missing file, a shipped file list that drops a runtime
// dependency, a tool table that drifted from the manifest, or a cache directory
// leaking into the tarball. No host, no Python, no spawn: pure file inspection.
import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { DEFAULTS } from '../lib/index.js';
import { RISK_TABLE } from '../lib/policy.js';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (rel) => readFileSync(join(ROOT, rel), 'utf8');
const json = (rel) => JSON.parse(read(rel));
const has = (rel) => existsSync(join(ROOT, rel));

const pkg = json('package.json');
const manifest = json('dsh-plugin.json');

/** Meta tools published by the plugin itself; everything else comes from the MCP server. */
const META_TOOLS = ['solidworks_status', 'solidworks_confirm'];

function walk(dir, out = []) {
  for (const entry of readdirSync(join(ROOT, dir), { withFileTypes: true })) {
    const rel = `${dir}/${entry.name}`;
    if (entry.isDirectory()) walk(rel, out);
    else out.push(rel);
  }
  return out;
}

test('package.json declares the identity and the bundle patch the host needs', () => {
  assert.equal(pkg.name, 'dsh-solidworks');
  assert.match(pkg.version, /^\d+\.\d+\.\d+/);
  assert.equal(pkg.type, 'module');
  assert.equal(pkg.license, 'AGPL-3.0-only');
  assert.equal(pkg.dsh.bundle.patch, './cordis.patch.yml');
  assert.ok(has('cordis.patch.yml'), 'dsh.bundle.patch must exist on disk');
  assert.ok(has(pkg.main), `main entry ${pkg.main} must exist`);
  assert.ok(has(pkg.exports['.']), 'exports["."] must exist');
  assert.ok(has(Object.values(pkg.bin)[0]), 'bin entry must exist');
  assert.ok(!pkg.scripts || !Object.keys(pkg.scripts).some((s) => /^(pre|post)?install$/.test(s)),
    'a market-installed plugin must not run install scripts');
});

test('the files allowlist ships every runtime dependency and nothing missing', () => {
  const files = pkg.files ?? [];
  assert.ok(files.length > 0, 'files allowlist must exist');

  // Runtime surface a user install needs.
  const required = [
    'lib', 'bin', 'vendor', 'docs', 'cordis.patch.yml', 'dsh-plugin.json',
    'LICENSE', 'NOTICE', 'README.md', 'README.zh.md', 'PROVENANCE.md',
  ];
  for (const entry of required) {
    assert.ok(files.includes(entry), `files must ship ${entry}`);
    assert.ok(has(entry), `${entry} is listed in files but missing on disk`);
  }

  // Anything the manifest or the entry point references must be inside the allowlist.
  const covered = (rel) => files.some((f) => rel === f || rel.startsWith(`${f}/`));
  for (const rel of [manifest.facets.host.entry, manifest.contributes['x-display'][0].icon,
    ...manifest.contributes['x-display'][0].locales, 'cordis.patch.yml', 'dsh-plugin.json']) {
    assert.ok(covered(rel.replace(/^\.\//, '')), `manifest references ${rel}, which files does not ship`);
  }
});

test('cordis.patch.yml inserts this plugin with only known config keys', () => {
  const yml = read('cordis.patch.yml');
  assert.match(yml, /insert:/);
  assert.match(yml, new RegExp(`id:\\s*${pkg.name}`));
  assert.match(yml, new RegExp(`name:\\s*${pkg.name}`));

  const known = new Set(Object.keys(DEFAULTS));
  const lines = yml.split(/\r?\n/);
  const anchor = lines.findIndex((line) => /^(\s*)config:\s*$/.test(line));
  assert.ok(anchor >= 0, 'the insert must carry a config: block');
  const indent = lines[anchor].match(/^(\s*)/)[1].length;

  const keys = [];
  for (const line of lines.slice(anchor + 1)) {
    const match = line.match(/^(\s*)([a-zA-Z][\w]*):/);
    if (!match) continue;
    if (match[1].length <= indent) break;
    if (match[1].length === indent + 2) keys.push(match[2]);
  }
  assert.ok(keys.length > 0, 'the config block must set at least one key');
  for (const key of keys) {
    assert.ok(known.has(key), `cordis.patch.yml sets "${key}", which apply() does not read`);
  }
  assert.ok(keys.includes('mode'), 'the shipped default must pin a policy mode');
});

test('manifest agrees with package.json and points at files that exist', () => {
  assert.equal(manifest.name, pkg.name);
  assert.equal(manifest.version, pkg.version);
  assert.equal(manifest.license, pkg.license);
  assert.equal(manifest.facets.host.entry, pkg.main);
  assert.equal(manifest.facets.host.apiVersion, 'v1alpha1');

  const display = manifest.contributes['x-display'][0];
  assert.ok(has(display.icon.replace(/^\.\//, '')), 'display icon must exist');
  assert.ok(statSync(join(ROOT, display.icon.replace(/^\.\//, ''))).size > 1024, 'icon must not be a stub');
  for (const locale of display.locales) {
    const table = json(locale);
    assert.ok(typeof table.title === 'string' && table.title.length > 0, `${locale} needs a title`);
    assert.ok(typeof table.description === 'string' && table.description.length > 20, `${locale} needs a description`);
  }

  const permissions = manifest.permissions.map((p) => p.scope).sort();
  assert.deepEqual(permissions, ['dsh-home', 'filesystem-read', 'subprocess']);
});

test('manifest tool list matches the risk table exactly', () => {
  const declared = manifest.contributes['x-tool-namespaces'][0].tools;
  assert.equal(new Set(declared).size, declared.length, 'manifest tool list must not repeat a tool');

  const table = Object.keys(RISK_TABLE);
  const expected = [...META_TOOLS, ...table].sort();
  assert.deepEqual([...declared].sort(), expected,
    'x-tool-namespaces.tools must equal meta tools + every RISK_TABLE entry');

  const counts = { read: 0, write: 0, high: 0 };
  for (const tier of Object.values(RISK_TABLE)) counts[tier] += 1;
  assert.deepEqual(counts, { read: 16, write: 26, high: 24 });
});

test('licence and notice travel with the package', () => {
  const licence = read('LICENSE');
  assert.match(licence, /GNU AFFERO GENERAL PUBLIC LICENSE/);
  assert.match(licence, /Version 3/);

  const notice = read('NOTICE');
  assert.match(notice, /MIT/);
  assert.match(notice, /solidworks-automation-skill/);
  assert.match(read('PROVENANCE.md'), /d8b9547/, 'provenance must pin the upstream commit');

  const vendorLicence = read('vendor/solidworks-automation-skill/LICENSE');
  assert.match(vendorLicence, /MIT License/);
  assert.match(vendorLicence, /Copyright \(c\) 2026 SolidWorks Automation Skill Contributors/);
});

test('the vendored engine is complete and carries no build junk', () => {
  const anchors = [
    'vendor/solidworks-automation-skill/mcp-server/server.py',
    'vendor/solidworks-automation-skill/apps/desktop/cad_workbench/artifact_ledger.py',
    'vendor/solidworks-automation-skill/capabilities.yaml',
    'vendor/solidworks-automation-skill/manifest.json',
  ];
  for (const rel of anchors) assert.ok(has(rel), `${rel} is part of the server import graph`);

  assert.ok(readdirSync(join(ROOT, 'vendor/solidworks-automation-skill/scripts')).length > 50,
    'scripts/ must be vendored');
  assert.ok(has('vendor/solidworks-automation-skill/subskills'), 'subskills/ must be vendored');

  const junk = walk('vendor').filter((rel) =>
    rel.includes('__pycache__') || rel.endsWith('.pyc') || rel.includes('/.git/') || rel.startsWith('vendor/.git'));
  assert.deepEqual(junk, [], 'the tarball must not carry bytecode caches or a nested repository');
});

test('user-facing docs exist and state the tool count the code actually ships', () => {
  const total = Object.keys(RISK_TABLE).length;
  for (const rel of ['README.md', 'README.zh.md', 'docs/verification.md', 'docs/market-submission.md']) {
    assert.ok(has(rel), `${rel} must ship`);
    assert.ok(statSync(join(ROOT, rel)).size > 2000, `${rel} looks like a stub`);
  }
  assert.ok(read('docs/verification.md').includes(String(total)), 'verification.md must quote the real tool count');

  // Every suite on disk must be described in the evidence log, and the two docs must
  // agree on the total, so adding a suite cannot silently leave the docs behind.
  const verification = read('docs/verification.md');
  const suites = readdirSync(join(ROOT, 'tests')).filter((file) => file.endsWith('.test.js')).sort();
  assert.ok(suites.length >= 7, `expected the seven suites on disk, found ${suites.length}`);
  for (const suite of suites) {
    assert.ok(verification.includes(suite), `docs/verification.md must describe the ${suite} suite`);
  }

  const totalFrom = (text, pattern) => {
    const match = text.match(pattern);
    return match ? Number(match[1]) : null;
  };
  const verificationTotal = totalFrom(verification, /合计\s*\*\*(\d+)\s*项断言\*\*/);
  const readmeTotal = totalFrom(read('README.md'), /(\d+)\s+assertions across/);
  assert.ok(Number.isInteger(verificationTotal), 'verification.md must state the total assertion count');
  assert.equal(readmeTotal, verificationTotal, `README.md (${readmeTotal}) and verification.md (${verificationTotal}) disagree on the assertion count`);

  // Documentation must describe the shipped default, not an older plan.
  assert.match(read('cordis.patch.yml'), /mode:\s*read-only/);
  assert.match(read('README.zh.md'), /read-only/);
});

test('shipped docs do not leak this build machine', () => {
  const leaked = ['D:\\Agent工作区', 'C:\\Users\\Khalil', 'D:\\SWCAD-MCP'];
  // verification.md and PROVENANCE.md are deliberately machine-specific evidence logs.
  const machineReports = new Set(['docs/verification.md', 'PROVENANCE.md']);
  for (const rel of ['README.md', 'README.zh.md', 'docs/market-submission.md', 'package.json', 'dsh-plugin.json']) {
    const text = read(rel);
    for (const needle of leaked) {
      assert.ok(!text.includes(needle), `${rel} leaks a path from the build machine: ${needle}`);
    }
  }
  assert.ok(machineReports.size === 2);
});

test('the vendor tree matches the paths the plugin resolves at runtime', () => {
  assert.equal(DEFAULTS.serverScript, null, 'the default server script is resolved by discover.js');
  const discover = read('lib/discover.js');
  for (const token of ["'vendor'", "'solidworks-automation-skill'", "'mcp-server'", "'server.py'"]) {
    assert.ok(discover.includes(token), `discover.js must resolve the vendored server (missing ${token})`);
  }
  assert.ok(!discover.includes('mcp-server-solidworks-main'), 'discover.js must not point at the old tree');
});

test('the evidence log is internally consistent', () => {
  const doc = read('docs/verification.md');
  const ids = [...doc.matchAll(/^\|\s*E(\d+)\s*\|/gm)].map((m) => Number(m[1]));
  assert.ok(ids.length >= 15, `expected E1..E17, found ${ids.length} rows`);
  assert.deepEqual(ids, ids.map((_, i) => i + 1), 'evidence ids must run E1..En without gaps');

  // Every command the log quotes must exist in the package.
  for (const [, script] of doc.matchAll(/node (tests\/[\w.-]+|bin\/[\w.-]+)/g)) {
    assert.ok(has(script), `verification.md runs ${script}, which is not shipped`);
  }
});

test('NOTICE states the file count the vendor tree actually has', () => {
  const countFiles = (dir) => readdirSync(join(ROOT, dir), { withFileTypes: true })
    .reduce((n, e) => n + (e.isDirectory() ? countFiles(join(dir, e.name)) : 1), 0);

  const actual = countFiles('vendor/solidworks-automation-skill');
  const said = Number(read('NOTICE').match(/Files\s*:\s*(\d+)/)?.[1]);
  assert.ok(Number.isFinite(said), 'NOTICE must state "Files : <n>" for the vendored tree');
  assert.strictEqual(said, actual, `NOTICE says ${said} vendored files, tree has ${actual}`);
});