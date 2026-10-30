// The real write loop, ready to run the moment the user authorises SolidWorks.
//
// It creates a NEW part (a Ø50 × 10 mm cylinder), reads its volume back, exports
// one STEP file into a scratch directory, and closes the document WITHOUT
// saving — so it cannot modify any document the user already has open.
//
// Run ONLY with authorisation to start SolidWorks:
//   node tests/write-loop.mjs --python "D:\SWCAD-MCP\Python313\python.exe" --authorised
//
// Exit: 0 pass, 1 regression, 2 precondition (no SolidWorks / not authorised).
//
// What the run proves, in the order it proves it:
//   1. the plugin loads the vendored server inside the host shape;
//   2. a read-only call still works (health_check);
//   3. a write call is REFUSED until it is confirmed  -> step 6/8;
//   4. after `solidworks_confirm` with byte-identical arguments it is allowed;
//   5. the geometry really exists (mass_properties volume > 0), i.e. the write
//      did something, not just returned ok;
//   6. the export lands on disk inside allowedRoots;
//   7. every step leaves an audit row.
import { existsSync, mkdirSync, readFileSync, statSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const root = join(here, '..')

const argv = process.argv.slice(2)
const pyIndex = argv.indexOf('--python')
const pythonPath = pyIndex >= 0 ? argv[pyIndex + 1] : null
const authorised = argv.includes('--authorised')

if (!pythonPath) {
  console.error('usage: node tests/write-loop.mjs --python <python.exe> --authorised')
  process.exit(2)
}
if (!authorised) {
  console.error('refusing to start SolidWorks without --authorised.\n' +
    'This script launches SolidWorks, creates a new part, exports one STEP file and closes\n' +
    'the document without saving. Re-run with --authorised once the user has approved it.')
  process.exit(2)
}

const failures = []
const check = (value, label) => {
  if (value) console.log(`PASS  ${label}`)
  else { failures.push(label); console.log(`FAIL  ${label}`) }
}

const outDir = join(tmpdir(), `dsh-sw-write-loop-${Date.now()}`)
mkdirSync(outDir, { recursive: true })
const auditLog = join(outDir, 'audit.jsonl')

function makeCtx() {
  const registered = new Map()
  return {
    tools: {
      register(definition) {
        if (!definition.output?.schema || typeof definition.output.render !== 'function') {
          throw new Error(`tool "${definition.name}" must declare output { schema, render }`)
        }
        registered.set(definition.name, definition)
        return () => registered.delete(definition.name)
      },
      guard() { return () => {} },
    },
    logger: { info() {}, warn(...a) { console.log('  [warn]', ...a) }, error() {}, debug() {} },
    get: () => undefined,
    on: () => () => {},
    effect: (fn) => { const dispose = fn(); return typeof dispose === 'function' ? dispose : () => {} },
    registered,
  }
}

const ctx = makeCtx()
const { apply } = await import(pathToFileURL(join(root, 'lib', 'index.js')).href)
const stop = await apply(ctx, {
  mode: 'full',
  allowedRoots: [outDir],
  auditLog,
  pythonPath,
  toolTimeoutMs: 180000,
  startTimeoutMs: 120000,
})

const tool = (name) => {
  const found = ctx.registered.get(name)
  if (!found) throw new Error(`tool ${name} was not published — the write loop cannot run`)
  return found
}
const text = (value) => String(value?.text ?? '')
const json = (value) => { try { return JSON.parse(text(value)) } catch { return null } }

/** Run one call and return { raw, body }. */
async function run(name, args = {}) {
  const raw = await tool(name).execute(args, {})
  return { raw, body: json(raw) }
}

/** A high-risk call: it must be refused first, then allowed after a grant. */
async function guarded(name, args) {
  const before = await run(name, args)
  check(text(before.raw).includes('CONFIRMATION_REQUIRED'), `${name} is refused before confirmation`)
  const granted = await run('solidworks_confirm', { tool: name, args, reason: 'write-loop test: user authorised this run' })
  check(text(granted.raw).includes('granted') || text(granted.raw).includes('"status":"granted"'), `${name} confirmation is granted`)
  const after = await run(name, args)
  return after
}

// ---- 1. precondition --------------------------------------------------------
const health = await run('solidworks_health_check', {})
const healthBody = health.body?.checks ?? health.body
check(Boolean(healthBody), 'health_check returns a JSON body')
if (!healthBody?.solidworks_detected) {
  console.error('\nSolidWorks is not installed on this machine — nothing to verify.')
  await stop?.()
  process.exit(2)
}
check(Array.isArray(healthBody.missing_com_dependencies) && healthBody.missing_com_dependencies.length === 0,
  'no missing COM dependency')

// ---- 2. connect + new part -------------------------------------------------
const connected = await run('solidworks_connect', { visible: true, wait_seconds: 10 })
check(!text(connected.raw).includes('"status":"failed"'), 'connect returns without a failure status')

const fresh = await run('solidworks_new_document', { doc_type: 'part' })
check(!text(fresh.raw).includes('"status":"failed"'), 'new part document is created')

// ---- 3. geometry -----------------------------------------------------------
const build = await run('solidworks_sketch_and_extrude', {
  plane_name: 'Front Plane',
  shape: 'circle',
  center_x_mm: 0,
  center_y_mm: 0,
  radius_mm: 25,
  depth_mm: 10,
  feature_name: 'MCP_WriteLoop_Cylinder',
})
check(!text(build.raw).includes('"status":"failed"'), 'sketch + boss-extrude returns without a failure status')

const mass = await run('solidworks_mass_properties', {})
const volume = Number(mass.body?.volume_mm3 ?? mass.body?.volume ?? NaN)
// A Ø50 × 10 cylinder is ~19,635 mm³; anything above 1,000 proves real geometry.
check(Number.isFinite(volume) && volume > 1000, `mass properties reports real volume (${volume} mm³)`)

// ---- 4. export (high risk) --------------------------------------------------
const stepPath = join(outDir, 'write-loop.step')
const exported = await guarded('solidworks_export_active', { output_path: stepPath, export_format: 'step' })
check(!text(exported.raw).includes('"status":"failed"'), 'export runs after the confirmation')
check(existsSync(stepPath) && statSync(stepPath).size > 1000, 'the STEP file exists and is not empty')

// ---- 5. close without saving (high risk) ------------------------------------
const closed = await guarded('solidworks_close_documents', { close_all: false, save_changes: false })
check(!text(closed.raw).includes('"status":"failed"'), 'the document closes after the confirmation')

// ---- 6. audit trail ---------------------------------------------------------
const rows = existsSync(auditLog) ? readFileSync(auditLog, 'utf8').split('\n').filter(Boolean).map((line) => JSON.parse(line)) : []
check(rows.some((row) => row.event === 'confirm'), 'the audit log records the confirmation')
check(rows.filter((row) => row.event === 'call').length >= 5, 'the audit log records each executed call')
check(rows.some((row) => row.event === 'refused'), 'the audit log records the refusals that happened before the grants')
check(!readFileSync(auditLog, 'utf8').includes(outDir), 'the audit log does not contain absolute paths')

await stop?.()

console.log(`\nArtifacts: ${outDir}`)
console.log(failures.length === 0 ? 'WRITE LOOP OK' : `WRITE LOOP FAILED: ${failures.length} failure(s)`)
process.exit(failures.length === 0 ? 0 : 1)