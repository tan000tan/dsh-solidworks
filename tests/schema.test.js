/**
 * FastMCP wraps every tool's arguments in a single `params` object. The plugin
 * unwraps it for the DSH tool surface and re-wraps on the wire; if that ever
 * gets asymmetrical, every write tool fails with "params: Field required", so
 * these cases are worth pinning down.
 */
import { unwrapParams, wrapArgs } from '../lib/schema.js';

const failures = [];
const check = (condition, label, detail) => {
  if (condition) console.log(`PASS  ${label}`);
  else { failures.push(label); console.log(`FAIL  ${label}${detail ? ` — ${detail}` : ''}`); }
};

// --- the real shape FastMCP emits -----------------------------------------
const fastmcp = {
  type: 'object',
  properties: { params: { $ref: '#/$defs/SolidWorksCreateBasicPartInput' } },
  required: ['params'],
  $defs: {
    BasicPartShape: { type: 'string', enum: ['cylinder', 'box'], title: 'BasicPartShape' },
    SolidWorksCreateBasicPartInput: {
      type: 'object',
      additionalProperties: false,
      properties: {
        shape: { $ref: '#/$defs/BasicPartShape', default: 'cylinder' },
        width_mm: { type: 'number', default: 80, exclusiveMinimum: 0 },
      },
      required: [],
    },
  },
};

const unwrapped = unwrapParams(fastmcp);
check(unwrapped.wrapped === true, 'detects the params wrapper');
check(Object.keys(unwrapped.schema.properties).join(',') === 'shape,width_mm', 'hoists the inner properties', Object.keys(unwrapped.schema.properties ?? {}).join(','));
check(unwrapped.schema.properties.shape.$ref === '#/$defs/BasicPartShape', 'keeps inner $ref intact');
check(unwrapped.schema.$defs?.BasicPartShape?.enum?.length === 2, 'carries $defs so the inner $ref still resolves');
check(unwrapped.schema.type === 'object', 'defaults type to object');
check(unwrapped.schema.properties.params === undefined, 'leaves no params property behind');

// --- idempotence / pass-through -------------------------------------------
const plain = { type: 'object', properties: { a: { type: 'string' } } };
const plainResult = unwrapParams(plain);
check(plainResult.wrapped === false, 'a normal schema is not touched');
check(plainResult.schema === plain, 'returns the same object when it does not unwrap');

const twoKeys = { type: 'object', properties: { params: { type: 'object' }, other: { type: 'string' } }, required: ['params'] };
check(unwrapParams(twoKeys).wrapped === false, 'refuses to unwrap when params is not the only input');

const optionalParams = { type: 'object', properties: { params: { type: 'object', properties: { x: { type: 'number' } } } }, required: ['somethingElse'] };
check(unwrapParams(optionalParams).wrapped === false, 'refuses when required names another key');

const inlineParams = { type: 'object', properties: { params: { type: 'object', properties: { depth_mm: { type: 'number' } } } }, required: ['params'] };
const inlined = unwrapParams(inlineParams);
check(inlined.wrapped === true && inlined.schema.properties.depth_mm?.type === 'number', 'unwraps an inline (non-$ref) params object');

// --- wrapping on the wire -------------------------------------------------
check(JSON.stringify(wrapArgs(true, { width_mm: 40 })) === '{"params":{"width_mm":40}}', 'wraps a flat argument object');
check(JSON.stringify(wrapArgs(true, { params: { width_mm: 40 } })) === '{"params":{"width_mm":40}}', 'does not double-wrap an already nested call');
check(JSON.stringify(wrapArgs(false, { a: 1 })) === '{"a":1}', 'leaves arguments alone when the tool is not wrapped');
check(JSON.stringify(wrapArgs(true, undefined)) === '{"params":{}}', 'sends an empty params object instead of null');
check(JSON.stringify(wrapArgs(true, { params: 5 })) === '{"params":{"params":5}}', 'nests a non-object params value rather than losing it');

import { validateSchema } from '../lib/validate.js';

// --- strict JSON Schema & $ref (G-08) --------------------------------------
const defsSchema = {
  type: 'object',
  definitions: {
    Point: {
      type: 'object',
      properties: { x: { type: 'number' }, y: { type: 'number' } },
      required: ['x', 'y'],
      additionalProperties: false,
    },
    'a/b~c': { type: 'string', minLength: 1 },
  },
  properties: {
    origin: { $ref: '#/definitions/Point' },
    tag: { $ref: '#/definitions/a~1b~0c' },
  },
  required: ['origin'],
  additionalProperties: false,
};
check(validateSchema(defsSchema, { origin: { x: 1, y: 2 }, tag: 'ok' }).ok === true, 'G-08: accepts valid #/definitions and escaped ~0/~1 $ref');
check(validateSchema(defsSchema, { origin: { x: 1, y: 2, z: 3 } }).code === 'UNKNOWN_ARGUMENT', 'G-08: rejects unknown key inside #/definitions $ref');
check(validateSchema(defsSchema, { origin: { x: 1, y: 2 }, tag: '' }).code === 'ARGUMENT_OUT_OF_RANGE', 'G-08: enforces minLength via escaped JSON Pointer $ref');

const rootRefSchema = {
  type: 'object',
  properties: {
    name: { type: 'string' },
    child: { $ref: '#' },
  },
  required: ['name'],
  additionalProperties: false,
};
check(validateSchema(rootRefSchema, { name: 'root', child: { name: 'leaf' } }).ok === true, 'G-08: accepts recursive root # $ref');
check(validateSchema(rootRefSchema, { name: 'root', child: { name: 'leaf', extra: 1 } }).code === 'UNKNOWN_ARGUMENT', 'G-08: rejects unknown key in recursive root # $ref');

const cycleSchema = {
  $defs: {
    A: { $ref: '#/$defs/B' },
    B: { $ref: '#/$defs/A' },
  },
  $ref: '#/$defs/A',
};
check(validateSchema(cycleSchema, { any: 1 }).code === 'SCHEMA_REF_CYCLE', 'G-08: rejects circular $ref fail-closed');

const missingRefSchema = {
  type: 'object',
  properties: { x: { $ref: '#/definitions/DoesNotExist' } },
  additionalProperties: false,
};
check(validateSchema(missingRefSchema, { x: 1 }).code === 'INVALID_SCHEMA_REF', 'G-08: rejects unresolved $ref fail-closed');

// --- Group C regression (C-08) ----------------------------------------------
// The pattern comes from the server's advertised schema, not from us. One
// malformed upstream pattern used to throw a raw SyntaxError out of
// validateSchema, which runs *before* the executor's error boundary — every
// call to that tool crashed the tool instead of being refused cleanly.
const badPatternSchema = {
  type: 'object',
  properties: { code: { type: 'string', pattern: '[' } },
  additionalProperties: false,
};
{
  let threw = null;
  let verdict = null;
  try { verdict = validateSchema(badPatternSchema, { code: 'a' }); } catch (error) { threw = error; }
  check(threw === null, 'C-08: a malformed schema pattern does not throw out of validateSchema');
  check(verdict?.code === 'INVALID_SCHEMA_PATTERN', 'C-08: a malformed schema pattern is refused with a structured code');
}
{
  // A pathological (too long) pattern must be refused without compiling it —
  // it would otherwise be a ReDoS vector on user-controlled strings.
  const longPattern = { type: 'object', properties: { s: { type: 'string', pattern: 'a'.repeat(600) } }, additionalProperties: false };
  check(validateSchema(longPattern, { s: 'aaa' }).code === 'INVALID_SCHEMA_PATTERN', 'C-08: an over-long schema pattern is refused before compiling');
}

console.log(failures.length === 0 ? '\nALL PASS' : `\n${failures.length} FAILURE(S)`);
process.exit(failures.length === 0 ? 0 : 1);