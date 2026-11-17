/**
 * Argument-shape adaptation between DSH and the SolidWorks MCP server.
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
  if (node.description !== undefined) merged.description = node.description;
  if (node.default !== undefined) merged.default = node.default;
  return merged;
}

/**
 * 紧凑精简 Schema，保留核心参数类型、必填约束和 `$defs` 引用完整性（修复 BUG-0015）。
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
      for (const def of Object.values(node.$defs)) stripExcess(def);
    }
  }

  stripExcess(copy);
  return copy;
}
