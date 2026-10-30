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

console.log(failures.length === 0 ? '\nALL PASS' : `\n${failures.length} FAILURE(S)`);
process.exit(failures.length === 0 ? 0 : 1);