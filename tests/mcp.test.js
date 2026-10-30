import assert from 'node:assert/strict';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { McpClient, McpError } from '../lib/mcp.js';
import { probePython, discover } from '../lib/discover.js';

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
    assert.deepEqual(tools.map(tool => tool.name), ['stub_read', 'stub_save', 'stub_slow']);
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