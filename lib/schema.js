/**
 * Argument-shape adaptation between DSH and the SolidWorks MCP server.
 *
 * FastMCP serialises each tool as
 *
 *   { type: 'object', properties: { params: { $ref: '#/$defs/XInput' } },
 *     required: ['params'], $defs: { XInput: { ... } } }
 *
 * so the raw schema a DSH user would see has exactly one input, `params`,
 * and every call has to be written `{ params: { width_mm: 40 } }`. That is a
 * leak of the server's internals into the tool surface: an agent (or a person
 * filling in the form) has no reason to know about the wrapper, and a call
 * written the obvious way fails with "params: Field required".
 *
 * `unwrapParams` moves the inner object up so the DSH tool looks like
 * `{ width_mm, height_mm, ... }`, and `wrapArgs` puts it back on the wire.
 */

const REF_PREFIX = '#/$defs/';

/**
 * @param {unknown} schema the tool's inputSchema as reported by the server
 * @returns {{ schema: unknown, wrapped: boolean }}
 */
export function unwrapParams(schema) {
  const unchanged = { schema, wrapped: false };
  if (!schema || typeof schema !== 'object') return unchanged;

  const properties = schema.properties;
  if (!properties || typeof properties !== 'object') return unchanged;

  const keys = Object.keys(properties);
  if (keys.length !== 1 || keys[0] !== 'params') return unchanged;

  const required = Array.isArray(schema.required) ? schema.required : [];
  if (required.length > 0 && !required.includes('params')) return unchanged;

  const inner = resolveRef(properties.params, schema);
  if (!inner || typeof inner !== 'object') return unchanged;

  const copy = JSON.parse(JSON.stringify(inner));
  // Inner `$ref`s still point at `#/$defs/...`, so the definitions have to travel
  // with the extracted object or they dangle.
  const defs = { ...(schema.$defs ?? {}), ...(copy.$defs ?? {}) };
  if (Object.keys(defs).length > 0) copy.$defs = defs;
  if (!copy.type) copy.type = 'object';
  return { schema: copy, wrapped: true };
}

/** Put the wrapper back on the wire, tolerating a caller that already nested. */
export function wrapArgs(wrapped, args) {
  const value = args && typeof args === 'object' ? args : {};
  if (!wrapped) return value;
  const keys = Object.keys(value);
  if (keys.length === 1 && keys[0] === 'params' && value.params && typeof value.params === 'object') return value;
  return { params: value };
}

function resolveRef(node, root) {
  if (!node || typeof node !== 'object' || typeof node.$ref !== 'string') return node;
  if (!node.$ref.startsWith(REF_PREFIX)) return node;
  const name = node.$ref.slice(REF_PREFIX.length);
  const target = root.$defs?.[name];
  if (!target || typeof target !== 'object') return node;
  const merged = { ...target };
  // A wrapper can carry a description/default of its own; the inner model wins
  // on structure and these two are the only annotations worth keeping.
  if (node.description !== undefined) merged.description = node.description;
  if (node.default !== undefined) merged.default = node.default;
  return merged;
}