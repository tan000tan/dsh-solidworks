import assert from 'node:assert/strict';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs';
import os from 'node:os';

import { spawnSync } from 'node:child_process';

import { McpClient, McpError } from '../lib/mcp.js';
import { probePython, discover, venvCandidates, entryCandidates } from '../lib/discover.js';
import { version as libVersion } from '../lib/index.js';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STUB = path.join(HERE, 'stub-server.mjs');

function client() {
  return new McpClient({ command: process.execPath, args: [STUB], cwd: HERE });
}

test('initialize + tools/list round-trip', async () => {
  const mcp = client();
  try {
    const init = await mcp.initialize({ clientName: 'test', clientVersion: '0.0.0', timeoutMs: 10_000 });
    assert.equal(init.protocolVersion, '2025-06-18');
    assert.equal(init.serverInfo.name, 'stub');
    const tools = await mcp.listTools({ timeoutMs: 10_000 });
    assert.deepEqual(tools.map(tool => tool.name), ['stub_read', 'stub_save', 'stub_slow', 'stub_crash']);
    assert.deepEqual(tools[0].inputSchema.required, ['id']);
  } finally {
    await mcp.close();
  }
});

test('tools/call returns text for success and isError for failure', async () => {
  const mcp = client();
  try {
    await mcp.initialize({ timeoutMs: 10_000 });
    const ok = await mcp.callTool('stub_read', { id: '42' }, { timeoutMs: 10_000 });
    assert.equal(ok.isError, false);
    assert.equal(ok.content[0].text, 'read 42');

    const failed = await mcp.callTool('stub_save', { path: 'C:\\x.sldprt' }, { timeoutMs: 10_000 });
    assert.equal(failed.isError, true);
    assert.equal(failed.content[0].text, 'save refused by stub');
  } finally {
    await mcp.close();
  }
});

test('json-rpc errors surface as McpError with the server code', async () => {
  const mcp = client();
  try {
    await mcp.initialize({ timeoutMs: 10_000 });
    await assert.rejects(
      () => mcp.callTool('no_such_tool', {}, { timeoutMs: 10_000 }),
      error => error instanceof McpError && error.code === -32602,
    );
  } finally {
    await mcp.close();
  }
});

test('a hung call times out instead of hanging the host', async () => {
  const mcp = client();
  try {
    await mcp.initialize({ timeoutMs: 10_000 });
    await assert.rejects(
      () => mcp.callTool('stub_slow', {}, { timeoutMs: 300 }),
      error => error instanceof McpError && error.code === 'TIMEOUT',
    );
  } finally {
    await mcp.close();
  }
});

test('abort signal cancels an in-flight call', async () => {
  const mcp = client();
  try {
    await mcp.initialize({ timeoutMs: 10_000 });
    const controller = new AbortController();
    const pending = mcp.callTool('stub_slow', {}, { timeoutMs: 30_000, signal: controller.signal });
    setTimeout(() => controller.abort(), 150);
    await assert.rejects(pending, error => error instanceof McpError && error.code === 'CANCELLED');
  } finally {
    await mcp.close();
  }
});

test('close is idempotent and rejects later calls', async () => {
  const mcp = client();
  await mcp.initialize({ timeoutMs: 10_000 });
  await mcp.close();
  await mcp.close();
  assert.equal(mcp.running, false);
  await assert.rejects(() => mcp.callTool('stub_read', { id: '1' }), error => error instanceof McpError);
});

test('probe rejects a command that cannot run', async () => {
  const result = await probePython({ command: path.join(HERE, 'definitely-not-python.exe'), args: [] }, { timeoutMs: 5_000 });
  assert.equal(result.ok, false);
  assert.match(result.reason, /cannot execute/);
});

test('discover reports a readable error when the server script is missing', async () => {
  const root = path.join(HERE, 'no-such-plugin-root');
  const found = await discover({ pluginRoot: root, config: { pythonPath: process.execPath }, env: process.env });
  // The interpreter is wrong on purpose, so either check may fire first; both must
  // produce a code instead of throwing.
  assert.equal(found.ok, false);
  assert.ok(['PYTHON_INVALID', 'SERVER_SCRIPT_MISSING'].includes(found.code), found.code);
  assert.ok(found.message.length > 0);
});

test('DEF-03: package.json, dsh-plugin.json, and lib/index.js report identical version', () => {
  const pkg = JSON.parse(fs.readFileSync(path.join(HERE, '..', 'package.json'), 'utf8'));
  const manifest = JSON.parse(fs.readFileSync(path.join(HERE, '..', 'dsh-plugin.json'), 'utf8'));
  const binScript = fs.readFileSync(path.join(HERE, '..', 'bin', 'dsh-solidworks.js'), 'utf8');
  assert.equal(pkg.version, manifest.version, 'package.json and manifest version must match');
  assert.equal(libVersion, pkg.version, 'lib/index.js export version must match package.json');
  assert.notEqual(libVersion, '0.1.0', 'lib/index.js must not report 0.1.0');
  assert.ok(binScript.includes('pkg.version'), 'bin/dsh-solidworks.js must read pkg.version');
});

test('DEF-01: discovers project .venv when present in plugin root', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-test-hasvenv-'));
  try {
    const venvBin = process.platform === 'win32'
      ? path.join(tempDir, '.venv', 'Scripts', 'python.exe')
      : path.join(tempDir, '.venv', 'bin', 'python');
    fs.mkdirSync(path.dirname(venvBin), { recursive: true });
    fs.writeFileSync(venvBin, '');
    const candidates = venvCandidates(tempDir);
    assert.ok(candidates.length > 0, 'venvCandidates must find candidate in ROOT/.venv');
    assert.match(candidates[0].label, /local \.venv|pyvenv\.cfg/);
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
});

test('DEF-01: priority order is config.pythonPath > DSH_SOLIDWORKS_PYTHON > .venv > py launcher > PATH', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-test-prio-'));
  try {
    const venvBin = process.platform === 'win32'
      ? path.join(tempDir, '.venv', 'Scripts', 'python.exe')
      : path.join(tempDir, '.venv', 'bin', 'python');
    fs.mkdirSync(path.dirname(venvBin), { recursive: true });
    fs.writeFileSync(venvBin, '');
    const fakeEnv = { DSH_SOLIDWORKS_PYTHON: 'C:\\fake\\env\\python.exe' };
    const candidates = entryCandidates(fakeEnv, tempDir);
    assert.ok(candidates.length >= 2);
    assert.equal(candidates[0].command, 'C:\\fake\\env\\python.exe', 'DSH_SOLIDWORKS_PYTHON must take precedence');
    assert.ok(candidates[1].label.includes('.venv') || candidates[1].label.includes('pyvenv'), 'Second priority must be local .venv');
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
});

test('DEF-01: non-existent venv falls through cleanly to PATH candidates without crashing', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-test-novenv-'));
  try {
    const candidates = venvCandidates(tempDir);
    assert.deepEqual(candidates, [], 'empty dir must yield 0 venv candidates');
    const all = entryCandidates({}, tempDir);
    assert.ok(all.length > 0, 'must fall through to PATH/launcher candidates');
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
});

test('DEF-04: solidworks_pack_and_go is registered with exact tool name in manifest and server', () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(HERE, '..', 'dsh-plugin.json'), 'utf8'));
  const declaredTools = manifest.contributes['x-tool-namespaces'][0].tools;
  assert.ok(declaredTools.includes('solidworks_pack_and_go'), 'manifest must include solidworks_pack_and_go');
  assert.ok(!declaredTools.includes('solidworks_pack_and_go_tool'), 'manifest must not have _tool suffix');

  const serverSrc = fs.readFileSync(path.join(HERE, '..', 'vendor', 'solidworks-automation-skill', 'mcp-server', 'server.py'), 'utf8');
  assert.match(serverSrc, /@mcp\.tool\(\s*name="solidworks_pack_and_go"/, 'server.py must register with wire name solidworks_pack_and_go');
});
// --- Group C regressions: client lifecycle ----------------------------------

test('C-03: a restart does not reuse the dead child\'s partial stdout frame', async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-test-c03-'));
  try {
    // This stub answers initialize/tools/list, but on tools/call it emits a
    // truncated frame and dies — leaving bytes behind in the client's buffer.
    const dying = path.join(tmp, 'dying.mjs');
    fs.writeFileSync(dying, `
      import process from 'node:process';
      const send = m => process.stdout.write(JSON.stringify(m) + '\\n');
      process.stdin.setEncoding('utf8');
      process.stdin.on('data', chunk => {
        for (const line of chunk.split('\\n').filter(Boolean)) {
          const m = JSON.parse(line);
          if (m.id === undefined) continue;
          if (m.method === 'initialize') {
            send({ jsonrpc: '2.0', id: m.id, result: { protocolVersion: '2025-06-18', capabilities: {}, serverInfo: { name: 'dying', version: '1' } } });
          } else if (m.method === 'tools/list') {
            send({ jsonrpc: '2.0', id: m.id, result: { tools: [{ name: 'stub_read', description: 'x', inputSchema: { type: 'object', properties: {} } }] } });
          } else if (m.method === 'tools/call') {
            process.stdout.write('{"jsonrpc":"2.0","id":99,"res');
            process.exit(3);
          }
        }
      });
    `);
    const mcp = new McpClient({ command: process.execPath, args: [dying], cwd: tmp });
    await mcp.initialize({ timeoutMs: 8000 });
    await mcp.callTool('stub_read', { id: '1' }, { timeoutMs: 3000 }).catch(() => {});
    await new Promise(resolve => setTimeout(resolve, 150));

    // The auto-restart in callTool must re-initialize against a *clean* buffer.
    // With the old buffer reuse, the initialize reply was glued onto the dead
    // child's partial frame, was unparsable, and burned the whole timeout.
    const started = Date.now();
    let code = null;
    try { await mcp.callTool('stub_read', { id: '2' }, { timeoutMs: 4000 }); }
    catch (error) { code = error.code; }
    const elapsed = Date.now() - started;
    assert.ok(elapsed < 3000, `the restart must not burn the full timeout on a polluted buffer (${elapsed}ms)`);
    assert.ok(!mcp.stderrTail(50).some(line => line.includes('unparsable stdout line')),
      'no frame from the dead child may be glued onto the new child\'s reply');
    await mcp.close().catch(() => {});
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test('C-04: a timed-out tools/call sends notifications/cancelled to the server', async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-test-c04-'));
  try {
    // A stub that logs every inbound line, and answers one tool late.
    const log = path.join(tmp, 'inbound.jsonl');
    const logging = path.join(tmp, 'logging.mjs');
    fs.writeFileSync(logging, `
      import fs from 'node:fs';
      const LOG = ${JSON.stringify(log)};
      const send = m => process.stdout.write(JSON.stringify(m) + '\\n');
      process.stdin.setEncoding('utf8');
      let buffer = '';
      process.stdin.on('data', chunk => {
        buffer += chunk;
        let index;
        while ((index = buffer.indexOf('\\n')) >= 0) {
          const line = buffer.slice(0, index);
          buffer = buffer.slice(index + 1);
          if (!line.trim()) continue;
          fs.appendFileSync(LOG, line + '\\n');
          const m = JSON.parse(line);
          if (m.id === undefined) continue;
          if (m.method === 'initialize') {
            send({ jsonrpc: '2.0', id: m.id, result: { protocolVersion: '2025-06-18', capabilities: {}, serverInfo: { name: 'log', version: '1' } } });
          } else if (m.method === 'tools/call' && m.params?.name === 'stub_slow') {
            setTimeout(() => send({ jsonrpc: '2.0', id: m.id, result: { content: [{ type: 'text', text: 'late' }] } }), 900);
          } else {
            send({ jsonrpc: '2.0', id: m.id, result: { content: [{ type: 'text', text: 'ok' }] } });
          }
        }
      });
    `);
    const mcp = new McpClient({ command: process.execPath, args: [logging], cwd: tmp });
    await mcp.initialize({ timeoutMs: 8000 });
    // Without the cancellation, the CAD side keeps executing a long solve after
    // the client has already given up, and the late result is dropped.
    await assert.rejects(mcp.callTool('stub_slow', {}, { timeoutMs: 250 }), error => error.code === 'TIMEOUT');
    await new Promise(resolve => setTimeout(resolve, 800));
    const inbound = fs.readFileSync(log, 'utf8').split('\n').filter(Boolean);
    assert.ok(inbound.some(line => line.includes('notifications/cancelled')),
      'the client must tell the server to stop when it gives up waiting');
    await mcp.close().catch(() => {});
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

// --- Group C regression: CLI argument parsing --------------------------------

test('C-CLI-01: value-flags before the command do not hijack command resolution', () => {
  const bin = path.join(HERE, '..', 'bin', 'dsh-solidworks.js');
  // "the first token that does not start with -" made `--mode full list-tools`
  // resolve to the command "full", and `--python <path> doctor` to the command
  // <path>. Both documented invocation orders failed with "unknown command".
  const run = args => spawnSync(process.execPath, [bin, ...args], { encoding: 'utf8', timeout: 60_000 });

  const modeFirst = run(['--mode', 'full', 'version']);
  assert.equal(modeFirst.status, 0, `--mode full version must resolve to the version command (stderr: ${modeFirst.stderr?.slice(0, 200)})`);
  assert.ok(modeFirst.stdout.includes('"version"'), 'the version command prints the version JSON');

  const pythonFirst = run(['--python', 'C:/nonexistent/python.exe', 'version']);
  assert.equal(pythonFirst.status, 0, `--python <path> version must resolve to the version command (stderr: ${pythonFirst.stderr?.slice(0, 200)})`);

  const bare = run(['version']);
  assert.equal(bare.status, 0, 'the bare command still works');
});

// --- Group A regression: server crash recovery -------------------------------

test('a crashed server is transparently respawned by the next call', async () => {
  const mcp = client();
  try {
    await mcp.initialize({ timeoutMs: 10_000 });
    // Kill the server mid-session: the pending call must fail with SERVER_EXITED.
    await assert.rejects(
      () => mcp.callTool('stub_crash', {}, { timeoutMs: 10_000 }),
      error => error instanceof McpError && error.code === 'SERVER_EXITED',
    );
    assert.equal(mcp.running, false);
    // The next call must transparently respawn the server and succeed — the
    // recovery branch is reachable, not dead code that only logs a failure.
    const ok = await mcp.callTool('stub_read', { id: 'after-crash' }, { timeoutMs: 15_000 });
    assert.equal(ok.isError, false);
    assert.equal(ok.content[0].text, 'read after-crash');
    assert.equal(mcp.running, true);
  } finally {
    await mcp.close();
  }
});
