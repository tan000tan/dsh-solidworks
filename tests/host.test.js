// End-to-end host-shape test: load the plugin the way the DSH host does
// (import the entry, call apply with a ctx that records registrations) and
// prove it publishes its tools against the REAL vendored MCP server.
//
// This is the test that answers "does the plugin actually work inside DSH?",
// as opposed to mcp.test.js which only exercises the client against a stub.
//
// Run: node tests/host.test.js            (uses the probe to find Python)
//      node tests/host.test.js --python 'D:\path\python.exe'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { dirname, join } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const root = join(here, '..')

const htmlArgs = process.argv.slice(2)
const pyIndex = htmlArgs.indexOf('--python')
const pythonPath = pyIndex >= 0 ? htmlArgs[pyIndex + 1] : null

const failures = []
// Set when the machine has no usable Python, so the exit code can say "environment", not "regression".
let environmentBlocked = false
const check = (value, label) => {
  if (value) console.log(`PASS  ${label}`)
  else { failures.push(label); console.log(`FAIL  ${label}`) }
}

/** Minimal stand-in for the DSH plugin context. */
function makeCtx() {
  const registered = new Map()
  const guards = []
  const logs = []
  return {
    tools: {
      register(definition) {
        if (!definition?.name) throw new Error('register() called without a name')
        if (!definition.parameters) throw new Error(`tool "${definition.name}" has no parameters`)
        if (!definition.output?.schema || typeof definition.output.render !== 'function') {
          throw new Error(`tool "${definition.name}" must declare output { schema, render }`)
        }
        registered.set(definition.name, definition)
        return () => registered.delete(definition.name)
      },
      guard(predicate) { guards.push(predicate); return () => {} },
    },
    logger: {
      info: (...a) => logs.push(['info', ...a]),
      warn: (...a) => logs.push(['warn', ...a]),
      error: (...a) => logs.push(['error', ...a]),
      debug: () => {},
    },
    get: () => undefined,
    on: () => () => {},
    effect: (fn) => { const dispose = fn(); return typeof dispose === 'function' ? dispose : () => {} },
    registered, guards, logs,
  }
}

const ctx = makeCtx()
const { apply, name } = await import(pathToFileURL(join(root, 'lib', 'index.js')).href)

check(typeof name === 'string' && name.length > 0, `entry exports a plugin name (${name})`)
check(typeof apply === 'function', 'entry exports apply()')

const config = { mode: 'read-only', pythonPath, toolTimeoutMs: 120000, startTimeoutMs: 60000 }

let thrown = null
const started = Date.now()
try {
  await apply(ctx, config)
} catch (error) {
  thrown = error
}
const startupMs = Date.now() - started

check(thrown === null, `apply() did not throw${thrown ? `: ${thrown.message}` : ''}`)
check(ctx.logs.length === 0 || !ctx.logs.some(([level]) => level === 'error'), 'apply() logged no errors')
console.log(`      (apply took ${startupMs} ms)`)

const names = [...ctx.registered.keys()].sort()
const mapped = names.filter(n => !n.startsWith('solidworks_') || n === 'solidworks_status' || n === 'solidworks_confirm')
const serverTools = names.filter(n => !['solidworks_status', 'solidworks_confirm'].includes(n))

check(names.includes('solidworks_status'), 'solidworks_status is published')
check(names.includes('solidworks_confirm'), 'solidworks_confirm is published')
check(serverTools.length > 0, `mapped server tools are published (${serverTools.length})`)
console.log(`      registered: ${names.length} tools = 2 meta + ${serverTools.length} server`)

// The read-only mode must not publish write/high tools.
const statusTool = ctx.registered.get('solidworks_status')
check(typeof statusTool.execute === 'function', 'meta tools carry execute()')

let statusValue = null
let statusError = null
try {
  statusValue = await statusTool.execute({}, {})
} catch (error) {
  statusError = error
}
check(statusError === null, `solidworks_status executed${statusError ? `: ${statusError.message}` : ''}`)
if (statusValue) {
  const parsed = JSON.parse(statusValue.text)
  console.log(`      status: mode=${parsed.policy?.mode} env=${parsed.environment?.state} running=${parsed.connection?.running} tools=${parsed.connection?.tools} python=${parsed.environment?.python?.command ?? "-"}`)
  if (parsed.environment?.state === "error") {
    environmentBlocked = true
    console.log(`      environment error: ${parsed.environment.code} — ${parsed.environment.message}`)
    console.log("      (pass --python <path>, or set config.pythonPath; without it only the 2 meta tools register)")
  }
  check(parsed.connection?.running === true, 'status reports the MCP server running')
  check(parsed.connection?.tools >= 60, `status reports the server's full tool count (${parsed.connection?.tools})`)
  check(parsed.policy?.mode === 'read-only', 'status reports the configured policy mode')
  check(parsed.policy?.registeredTools === names.length, 'status reports every registered tool')
}

// A real read-only call through the registered tool, exactly as the model calls it.
const probe = ctx.registered.get('solidworks_health_check')
if (probe) {
  const startedCall = Date.now()
  const value = await probe.execute({}, {})
  const ms = Date.now() - startedCall
  const payload = JSON.parse(value.text)
  console.log(`      solidworks_health_check (${ms} ms): ${JSON.stringify(payload).slice(0, 300)}`)
  check(payload && typeof payload === 'object', 'a mapped tool returns a JSON payload')
} else {
  failures.push('solidworks_health_check was not published')
  console.log('FAIL  solidworks_health_check was not published')
}

// Withholding must be real: a write tool must be absent in read-only mode.
check(!ctx.registered.has('solidworks_save_document'), 'write tools are withheld in read-only mode')

// The deny-list guard must be installed as defence in depth.
check(ctx.guards.length >= 1, 'ctx.tools.guard() is installed')

// --- argument shape --------------------------------------------------------
// Every FastMCP tool takes one `params` object. If the plugin passed that
// through, the DSH form would ask the user for "params" and every call written
// the obvious way would fail with "params: Field required".
const health = ctx.registered.get('solidworks_health_check')
if (health) {
  const props = Object.keys(health.parameters?.properties ?? {})
  check(!props.includes('params'), 'the FastMCP params wrapper is hoisted out of the DSH schema')
  check(props.includes('start_solidworks'), `the hoisted schema keeps the real inputs (${props.length}: ${props.join(', ')})`)
  check(health.parameters?.properties?.params === undefined, 'no leftover params property')
}

// --- the same wrapper, proven on the wire ---------------------------------
// A stub server shaped like FastMCP echoes back the arguments it received, so
// this distinguishes "the plugin wrapped them" from "the plugin sent them flat".
const stubCtx = makeCtx()
let stubThrown = null
try {
  await apply(stubCtx, {
    mode: 'read-only',
    pythonPath,
    serverScript: join(here, 'stub-server.py'),
    serverCwd: here,
    toolTimeoutMs: 20000,
    startTimeoutMs: 30000,
  })
} catch (error) {
  stubThrown = error
}
check(stubThrown === null, `apply() against the stub server did not throw${stubThrown ? `: ${stubThrown.message}` : ''}`)

const wrapped = stubCtx.registered.get('stub_wrapped')
check(wrapped !== undefined, 'a params-wrapped stub tool is published')
if (wrapped) {
  const wrappedProps = Object.keys(wrapped.parameters?.properties ?? {})
  check(!wrappedProps.includes('params') && wrappedProps.includes('width_mm'), `stub schema hoisted (${wrappedProps.join(', ')})`)
  let echoed = null
  try {
    const value = await wrapped.execute({ width_mm: 40, shape: 'box' }, {})
    echoed = value?.text ?? null
  } catch (error) {
    echoed = `threw: ${error.message}`
  }
  console.log(`      stub_wrapped received: ${String(echoed).slice(0, 120)}`)
  let parsed = null
  try { parsed = JSON.parse(echoed) } catch { /* leave null */ }
  check(parsed?.params?.width_mm === 40 && parsed?.params?.shape === 'box', 'arguments go back on the wire wrapped in params')
}

const plainStub = stubCtx.registered.get('stub_plain')
if (plainStub) {
  let echoed = null
  try {
    const value = await plainStub.execute({ id: 'abc' }, {})
    echoed = value?.text ?? null
  } catch (error) {
    echoed = `threw: ${error.message}`
  }
  let parsed = null
  try { parsed = JSON.parse(echoed) } catch { /* leave null */ }
  check(parsed?.id === 'abc' && parsed?.params === undefined, 'a flat-argument tool is not wrapped')
}

// A path argument outside the allowed roots must be refused before any call:
// this is what keeps an export from landing on top of a user's file tree.
const gateCtx = makeCtx()
await apply(gateCtx, {
  mode: 'full',
  pythonPath,
  serverScript: join(here, 'stub-server.py'),
  serverCwd: here,
  allowedRoots: [join(root, 'tests')],
  toolTimeoutMs: 20000,
  startTimeoutMs: 30000,
})
const exporter = gateCtx.registered.get('stub_export')
check(exporter !== undefined, 'a high-risk tool with a path argument is published in full mode')
if (exporter) {
  const refused = await exporter.execute({ output_path: 'C:\\Windows\\Temp\\evil.step' }, {})
  let payload = null
  try { payload = JSON.parse(refused?.text ?? '') } catch { /* leave null */ }
  console.log(`      outside-root call: ${String(refused?.text).slice(0, 140)}`)
  check(payload?.status === 'refused' && payload?.code === 'PATH_OUTSIDE_ALLOWED_ROOTS', 'a write outside allowedRoots is refused before it reaches the server')
  // The same tool inside the roots still needs an explicit confirmation.
  const inside = await exporter.execute({ output_path: join(root, 'tests', 'ok.step') }, {})
  let insidePayload = null
  try { insidePayload = JSON.parse(inside?.text ?? '') } catch { /* leave null */ }
  check(insidePayload?.code === 'CONFIRMATION_REQUIRED', 'a write inside the roots still asks for confirmation')
}

console.log(failures.length === 0 ? '\nALL PASS' : `\n${failures.length} FAILURE(S)`)
// Exit 2 = this machine has no usable Python; exit 1 = a real regression.
process.exit(failures.length === 0 ? 0 : environmentBlocked ? 2 : 1)