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

/**
 * 紧凑精简 Schema，移除重复冗余标注，保留核心参数类型和必填约束，大幅降低大模型 Token 开销。
 */
export function compactToolSchema(schema) {
  if (!schema || typeof schema !== 'object') return schema;
  const copy = JSON.parse(JSON.stringify(schema));
  
  function stripExcess(node) {
    if (!node || typeof node !== 'object') return;
    if (typeof node.title === 'string') delete node.title;
    if (typeof node.description === 'string' && node.description.length > 80) {
      node.description = node.description.split(/[\n\r.]/)[0].trim().slice(0, 80);
    }
    if (node.properties && typeof node.properties === 'object') {
      for (const prop of Object.values(node.properties)) {
        stripExcess(prop);
      }
    }
    if (node.items && typeof node.items === 'object') {
      stripExcess(node.items);
    }
    if (node.$defs && typeof node.$defs === 'object') {
      delete node.$defs;
    }
  }

  stripExcess(copy);
  return copy;
}