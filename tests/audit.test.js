// Audit-trail test: the plugin claims every accepted, refused and failed CAD call
// leaves one JSONL line with a content digest and no arguments or credentials.
// That claim is what lets a user answer "what did the model actually do to my
// document?", so it is checked end to end against a stub server instead of being
// taken from the source.
//
// Run: node tests/audit.test.js --python 'D:\path\python.exe'
// Exit: 0 pass, 1 regression, 2 environment (no usable Python)
import { existsSync, mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const root = join(here, '..')

const argv = process.argv.slice(2)
const pyIndex = argv.indexOf('--python')
const pythonPath = pyIndex >= 0 ? argv[pyIndex + 1] : (process.env.DSH_SOLIDWORKS_PYTHON || null)
if (!pythonPath) {
  console.error('usage: node tests/audit.test.js --python <python.exe>\n       (or set DSH_SOLIDWORKS_PYTHON)')
  process.exit(2)
}

const failures = []
const check = (value, label) => {
  if (value) console.log(`PASS  ${label}`)
  else { failures.push(label); console.log(`FAIL  ${label}`) }
}

/** Minimal stand-in for the DSH plugin context (same contract host.test.js uses). */
function makeCtx() {
  const registered = new Map()
  return {
    tools: {
      register(definition) {
        if (!definition?.name) throw new Error('register() called without a name')
        if (!definition.output?.schema || typeof definition.output.render !== 'function') {
          throw new Error(`tool "${definition.name}" must declare output { schema, render }`)
        }
        registered.set(definition.name, definition)
        return () => registered.delete(definition.name)
      },
      guard() { return () => {} },
    },
    logger: { info() {}, warn() {}, error() {}, debug() {} },
    get: () => undefined,
    on: () => () => {},
    effect: (fn) => { const dispose = fn(); return typeof dispose === 'function' ? dispose : () => {} },
    registered,
  }
}

const tmp = mkdtempSync(join(tmpdir(), 'dsh-sw-audit-'))
const auditLog = join(tmp, 'logs', 'audit.jsonl')
const readRows = () => readFileSync(auditLog, 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line))
const text = (value) => String(value?.text ?? '')

const { apply } = await import(pathToFileURL(join(root, 'lib', 'index.js')).href)
const base = {
  pythonPath,
  serverScript: join(here, 'stub-server.py'),
  serverCwd: here,
  auditLog,
  toolTimeoutMs: 20000,
  startTimeoutMs: 20000,
}

// ---- instance A: read-only, one read tool called twice ---------------------
const ctxA = makeCtx()
const stopA = await apply(ctxA, { ...base, mode: 'read-only' })

check(ctxA.registered.has('stub_wrapped'), 'read-only mode publishes the read-shaped stub tool')
check(!ctxA.registered.has('stub_export'), 'read-only mode withholds the write-shaped stub tool')

const wrapped = ctxA.registered.get('stub_wrapped')
const first = await wrapped.execute({ width_mm: 120 }, {})
check(text(first).includes('"width_mm": 120'), 'the call reaches the server with the arguments re-wrapped')
await wrapped.execute({ width_mm: 120 }, {})
await stopA?.()

// ---- instance B: full mode + path gate + confirm + server error ------------
const ctxB = makeCtx()
const outside = join(tmpdir(), 'dsh-sw-audit-elsewhere', 'part.step')
const inside = join(tmp, 'out', 'part.step')
const stopB = await apply(ctxB, { ...base, mode: 'full', allowedRoots: [tmp] })

check(ctxB.registered.has('stub_export'), 'full mode publishes the write-shaped stub tool')

const exportTool = ctxB.registered.get('stub_export')
const blocked = await exportTool.execute({ output_path: outside }, {})
check(text(blocked).includes('PATH_OUTSIDE_ALLOWED_ROOTS'), 'a write outside allowedRoots is refused before reaching the server')

const needsConfirm = await exportTool.execute({ output_path: inside }, {})
check(text(needsConfirm).includes('CONFIRMATION_REQUIRED'), 'a write inside allowedRoots still needs explicit confirmation')

const confirm = ctxB.registered.get('solidworks_confirm')
await confirm.execute({ tool: 'stub_export', args: { output_path: inside }, reason: 'test approval' }, {})
const afterGrant = await exportTool.execute({ output_path: inside }, {})
check(text(afterGrant).includes('unknown tool'), 'after the grant the call is actually sent (the stub answers with an error)')
await stopB?.()

// ---- the trail itself ------------------------------------------------------
check(existsSync(auditLog), 'the audit log file was created at the configured path')
const rows = readRows()
check(rows.length >= 5, `the log holds one line per event (got ${rows.length})`)

const events = new Set(rows.map((row) => row.event))
for (const expected of ['call', 'refused', 'confirm', 'error']) {
  check(events.has(expected), `the log records a "${expected}" event`)
}

check(rows.every((row) => typeof row.ts === 'string' && !Number.isNaN(Date.parse(row.ts))), 'every row carries an ISO timestamp')
check(rows.every((row) => typeof row.tool === 'string' && row.tool.length > 0), 'every row names the tool')

const audited = rows.filter((row) => row.event !== 'confirm')
check(audited.every((row) => /^[0-9a-f]{16}$/.test(String(row.digest))), 'every executed or refused call carries a 16-hex argument digest')

const callDigests = rows.filter((row) => row.event === 'call').map((row) => row.digest)
check(callDigests.length >= 2 && new Set(callDigests).size === 1, 'identical arguments produce an identical digest (no salt churn)')

check(rows.some((row) => row.code === 'PATH_OUTSIDE_ALLOWED_ROOTS'), 'the refusal reason is recorded, not just the fact of refusal')
check(rows.some((row) => row.code === 'CONFIRMATION_REQUIRED'), 'the confirmation requirement is recorded')

const raw = readFileSync(auditLog, 'utf8')
check(!raw.includes('width_mm'), 'argument names are never written to the log (only their digest)')
check(!raw.includes(tmp) && !raw.includes(tmpdir().replace(/\\/g, '\\\\')), 'no absolute path is written to the log')
check(!/token|password|secret|api[_-]?key/i.test(raw), 'no credential-shaped key appears in the log')

const targets = rows.filter((row) => row.target).map((row) => row.target)
check(targets.every((target) => !target.includes('/') && !target.includes('\\')), 'recorded targets are bare file names, not paths')

// The digest and the target name are produced by pure helpers, so their contract
// is checked directly as well: the log above only has a path-bearing row when a
// write actually reaches the server, which the stub deliberately refuses to do.
const { auditTarget, digest, canonicalArgs } = await import(pathToFileURL(join(root, 'lib', 'policy.js')).href)
check(auditTarget({ output_path: 'C:/Users/someone/Desktop/part.STEP' }) === 'part.STEP', 'auditTarget() keeps only the file name')
check(auditTarget({ width_mm: 10 }) === null, 'auditTarget() returns null when the arguments name no path')
check(/^[0-9a-f]{16}$/.test(digest(canonicalArgs({ b: 1, a: 2 }))), 'digest() is a fixed-width hex string')
check(digest(canonicalArgs({ a: 2, b: 1 })) === digest(canonicalArgs({ b: 1, a: 2 })), 'canonicalArgs() makes key order irrelevant')

rmSync(tmp, { recursive: true, force: true })

console.log(`\n${failures.length === 0 ? 'OK' : 'FAILED'}: ${failures.length} failure(s)`)
if (failures.length > 0) {
  for (const failure of failures) console.log(`  - ${failure}`)
  process.exit(1)
}
process.exit(0)