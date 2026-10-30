#!/usr/bin/env node
/**
 * Read-only probe: start the vendored SolidWorks MCP server, list its tools, and
 * cross-check the result against the plugin's risk table.
 *
 * This is a development diagnostic, not a shipped command. It never calls a tool
 * that could touch a document.
 *
 *   node tests/probe-server.mjs [--python <path>] [--mode read-only|standard|full]
 */
import { fileURLToPath } from 'node:url';
import path from 'node:path';

import { RISK_TABLE, Policy } from '../lib/policy.js';
import { unwrapParams } from '../lib/schema.js';
import { discover } from '../lib/discover.js';
import { McpClient } from '../lib/mcp.js';

const PLUGIN_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function arg(name, fallback = null) {
  const index = process.argv.indexOf(`--${name}`);
  return index === -1 ? fallback : process.argv[index + 1];
}

const pythonPath = arg('python');
const mode = arg('mode', 'read-only');

const found = await discover({
  pluginRoot: PLUGIN_ROOT,
  config: { pythonPath, serverScript: null },
  env: process.env,
});
if (!found.ok) {
  console.error(`discover failed: ${found.code} ${found.message}`);
  process.exit(2);
}

const client = new McpClient({
  command: found.python.command,
  args: [...found.python.args, found.serverScript],
  cwd: found.serverCwd,
  env: { PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8' },
});

let init;
let tools;
try {
  init = await client.initialize({ clientName: 'dsh-solidworks-probe', clientVersion: '0.1.0', timeoutMs: 90_000 });
  tools = await client.listTools({ timeoutMs: 90_000 });
} catch (error) {
  console.error(`handshake failed: ${error.code ?? '?'} ${error.message}`);
  for (const line of client.stderrTail(20)) console.error(`  ${line}`);
  process.exit(1);
} finally {
  await client.close();
}

const policy = new Policy({ mode, allowedRoots: [] });
const names = tools.map(tool => tool.name);
const byTier = {};
for (const tool of tools) {
  const tier = policy.tierOf(tool.name);
  byTier[tier] = (byTier[tier] ?? 0) + 1;
}
const unknown = names.filter(name => !(name in RISK_TABLE));
const stale = Object.keys(RISK_TABLE).filter(name => !names.includes(name));
const published = names.filter(name => policy.registerable(name));
const withheld = names.filter(name => !policy.registerable(name));

// Every FastMCP tool takes one `params` object; the plugin hoists it for the DSH
// surface. A tool that suddenly grows a different shape still works (the plugin
// passes it through untouched) but the argument form users see changes, so say so.
const wrapped = tools.filter(tool => unwrapParams(tool.inputSchema).wrapped).length;
const empty = tools.filter(tool => {
  const schema = unwrapParams(tool.inputSchema).schema;
  return !schema?.properties || Object.keys(schema.properties).length === 0;
});

console.log(`server      ${init.serverInfo?.name} ${init.serverInfo?.version} (protocol ${init.protocolVersion})`);
console.log(`python      ${found.python.version} at ${found.python.command}`);
console.log(`tools       ${tools.length} total, tiers ${JSON.stringify(byTier)}`);
console.log(`table       ${Object.keys(RISK_TABLE).length} entries`);
console.log(`mode ${mode}: ${published.length} published / ${withheld.length} withheld`);
if (unknown.length) console.log(`NOT IN TABLE (classified by pattern): ${unknown.join(', ')}`);
if (stale.length) console.log(`STALE TABLE ENTRIES (server no longer offers them): ${stale.join(', ')}`);
if (withheld.length) console.log(`withheld: ${withheld.join(', ')}`);

// A tool the server offers but the table forgets is a policy hole only if the
// fallback guesses "read"; print the guess so a human can confirm it.
for (const name of unknown) {
  console.log(`  ${name} -> ${policy.tierOf(name)} (heuristic)`);
}

process.exit(unknown.length || stale.length ? 3 : 0);