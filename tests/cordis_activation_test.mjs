// 回归测试：插件必须能在真实 Cordis 4 Context 中激活（BUG-0001 复发防护）。
// 未找到 Cordis 时（非 DSH 环境）跳过并明确标记 SKIPPED，不算通过。
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import path from 'node:path';
import os from 'node:os';

const cordisPath = process.env.DSH_CORDIS_PATH
  || path.join(process.env.APPDATA || '', 'npm', 'node_modules', '@deepseek-ai', 'dsh', 'node_modules', '@deepseek-ai', 'cordis', 'lib', 'index.js');
if (!existsSync(cordisPath)) { console.log('SKIPPED: Cordis not found (' + cordisPath + ')'); process.exit(0); }

const { Context } = await import(pathToFileURL(cordisPath).href);
const plugin = await import(pathToFileURL(path.resolve(import.meta.dirname, '..', 'lib', 'index.js')).href);

const ctx = new Context();
ctx.provide('tools');
ctx.set('tools', { register() { return () => {}; }, unregister() {}, add() { return () => {}; } });
const errors = [];
ctx.on('internal/error', (e) => errors.push(e));
ctx.plugin(plugin, { mode: 'read-only', pythonPath: path.join(os.tmpdir(), 'no-such-python.exe'), allowedRoots: [] });
await new Promise((r) => setTimeout(r, 1500));
assert.ok(ctx.solidworks, 'ctx.solidworks must be provided after activation');
assert.equal(typeof ctx.solidworks.status, 'function');
assert.equal(errors.length, 0, 'no activation error: ' + errors.map(String).join('; '));
console.log('PASS: cordis activation');
process.exit(0);