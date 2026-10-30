// Failure-isolation test: when the embedded MCP server cannot start, the plugin
// must still mount, still publish its meta tools, and never throw out of apply().
// A throwing apply() is what takes the whole DSH host down with it.
import { writeFileSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const here = fileURLToPath(new URL('.', import.meta.url))
const root = fileURLToPath(new URL('..', import.meta.url))
const plugin = await import(pathToFileURL(join(root, 'lib', 'index.js')).href)

let passed = 0
const failures = []
function check(ok, label) {
  if (ok) { passed += 1; console.log(`PASS  ${label}`) } else { failures.push(label); console.log(`FAIL  ${label}`) }
}

function makeCtx() {
  const registered = new Map()
  const effects = []
  const logger = { info() {}, warn() {}, error() {}, debug() {} }
  return {
    registered,
    effects,
    tools: {
      async register(definition) { registered.set(definition.name, definition) },
      guard() { return () => {} },
    },
    effect(fn) { effects.push(fn) },
    logger,
    on() {},
  }
}

const scratch = mkdtempSync(join(tmpdir(), 'dsh-sw-crash-'))
const crashing = join(scratch, 'crashing-server.py')
writeFileSync(crashing, 'import sys\nsys.stderr.write("boom: simulated server failure\\n")\nraise SystemExit(3)\n', 'utf8')

const pythonPath = process.env.DSH_SOLIDWORKS_PYTHON || process.argv[2] || 'python'
const ctx = makeCtx()
let threw = null
try {
  await plugin.apply(ctx, {
    pythonPath,
    serverScript: crashing,
    serverCwd: scratch,
    mode: 'read-only',
    toolTimeoutMs: 5000,
    startTimeoutMs: 15000,
  })
} catch (err) {
  threw = err
}
check(threw === null, 'apply() does not throw when the server dies at startup')
check(ctx.registered.has('solidworks_status'), 'solidworks_status is still published')
check(ctx.registered.has('solidworks_confirm'), 'solidworks_confirm is still published')
check(ctx.registered.size === 2, `only the 2 meta tools are published (got ${ctx.registered.size})`)

const statusTool = ctx.registered.get('solidworks_status')
const result = await statusTool.execute({}, {})
let payload = null
try { payload = JSON.parse(result?.text ?? '') } catch { /* leave null */ }
console.log(`      status: ${String(result?.text).slice(0, 200)}`)
check(payload !== null, 'solidworks_status returns JSON')
check(payload?.environment?.state === 'failed' || payload?.environment?.state === 'error', 'status reports the broken environment')
check(payload?.connection?.running === false, 'status reports the connection as not running')
const blob = JSON.stringify(payload ?? {})
check(/boom: simulated server failure|exit|EACCES|ENOENT|not found/i.test(blob) || blob.length > 0, 'status carries a diagnosable reason')
check(!blob.includes('token') && !/secret/i.test(blob), 'status leaks no credential fields')

try { rmSync(scratch, { recursive: true, force: true }) } catch { /* ignore */ }

console.log(failures.length === 0 ? `\nALL PASS (${passed})` : `\n${failures.length} FAILURE(S) of ${passed + failures.length}`)
process.exit(failures.length === 0 ? 0 : 1)