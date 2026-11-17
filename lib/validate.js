/**
 * 严格 JSON Schema 参数校验器（BUG-003）。
 * 在任何策略审批、路径处理或 Python MCP 调用之前执行，确保：
 *   1. 拒绝未知参数（顶层与嵌套对象）；
 *   2. 拒绝缺失必填参数；
 *   3. 拒绝错误类型、NaN/Infinity、越界数值、非法枚举、空值/长度超限、非法数组元素。
 */

function decodeJsonPointerToken(token) {
  return token.replace(/~1/g, '/').replace(/~0/g, '~');
}

function resolveJsonPointer(root, ref) {
  if (ref === '#') return root;
  if (!ref.startsWith('#/')) return undefined;
  const parts = ref.slice(2).split('/').map(decodeJsonPointerToken);
  let cur = root;
  for (const part of parts) {
    if (cur === null || typeof cur !== 'object') return undefined;
    if (Array.isArray(cur)) {
      if (!/^\d+$/.test(part)) return undefined;
      const idx = Number(part);
      if (idx < 0 || idx >= cur.length) return undefined;
      cur = cur[idx];
    } else if (Object.prototype.hasOwnProperty.call(cur, part)) {
      cur = cur[part];
    } else {
      return undefined;
    }
  }
  return cur;
}

function resolveRef(node, root, seen = new Set()) {
  if (!node || typeof node !== 'object' || typeof node.$ref !== 'string') {
    return { ok: true, node };
  }
  let current = node;
  let depth = 0;
  const localSeen = new Set(seen);
  while (current && typeof current === 'object' && typeof current.$ref === 'string') {
    const ref = current.$ref;
    if (localSeen.has(ref) || depth >= 32) {
      return { ok: false, code: 'SCHEMA_REF_CYCLE', message: `circular or overly deep $ref "${ref}"` };
    }
    localSeen.add(ref);
    depth += 1;
    const target = resolveJsonPointer(root, ref);
    if (!target || typeof target !== 'object') {
      return { ok: false, code: 'INVALID_SCHEMA_REF', message: `unresolved $ref "${ref}"` };
    }
    const merged = { ...target, ...current };
    delete merged.$ref;
    if (typeof target.$ref === 'string' && current.$ref !== target.$ref) {
      merged.$ref = target.$ref;
    }
    current = merged;
  }
  return { ok: true, node: current, seen: localSeen };
}

function isPlainObject(v) {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}

function matchesType(val, expected) {
  switch (expected) {
    case 'null': return val === null;
    case 'boolean': return typeof val === 'boolean';
    case 'string': return typeof val === 'string';
    case 'number': return typeof val === 'number' && Number.isFinite(val);
    case 'integer': return typeof val === 'number' && Number.isInteger(val);
    case 'array': return Array.isArray(val);
    case 'object': return isPlainObject(val);
    default: return true;
  }
}

function formatError(code, path, message) {
  return { ok: false, code, path, message: `${path}: ${message}` };
}

function deepEqual(a, b) {
  if (Object.is(a, b)) return true;
  if (typeof a !== typeof b || a === null || b === null) return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  if (Array.isArray(a)) {
    return a.length === b.length && a.every((v, i) => deepEqual(v, b[i]));
  }
  if (typeof a === 'object') {
    const ka = Object.keys(a);
    const kb = Object.keys(b);
    return ka.length === kb.length && ka.every((k) => Object.prototype.hasOwnProperty.call(b, k) && deepEqual(a[k], b[k]));
  }
  return false;
}

export function validateSchema(rawNode, value, rootSchema = rawNode, path = '$', refSeen = new Set()) {
  if (!rawNode || typeof rawNode !== 'object') return { ok: true };
  const resolved = resolveRef(rawNode, rootSchema, refSeen);
  if (!resolved.ok) {
    return formatError(resolved.code, path, resolved.message);
  }
  const node = resolved.node;
  const nextRefSeen = resolved.seen ?? refSeen;

  // 优先检查对象未知键（BUG-003），确保任何未知参数必报 UNKNOWN_ARGUMENT
  if (isPlainObject(value)) {
    const props = node.properties && typeof node.properties === 'object' ? node.properties : {};
    const disallowUnknown = node.additionalProperties === false
      || (node.additionalProperties === undefined && node.properties !== undefined);
    if (disallowUnknown) {
      for (const k of Object.keys(value)) {
        if (value[k] !== undefined && !Object.prototype.hasOwnProperty.call(props, k)) {
          return formatError('UNKNOWN_ARGUMENT', `${path}.${k}`, `unknown parameter "${k}"`);
        }
      }
    }
  }

  if (Array.isArray(node.allOf)) {
    for (const sub of node.allOf) {
      const r = validateSchema(sub, value, rootSchema, path, nextRefSeen);
      if (!r.ok) return r;
    }
  }
  if (Array.isArray(node.anyOf)) {
    let lastErr = null;
    let matched = false;
    for (const sub of node.anyOf) {
      const r = validateSchema(sub, value, rootSchema, path, nextRefSeen);
      if (r.ok) { matched = true; break; }
      lastErr = r;
    }
    if (!matched) {
      return formatError(lastErr?.code ?? 'INVALID_ARGUMENTS', path, lastErr?.message ?? 'value does not match anyOf schema');
    }
  }
  if (Array.isArray(node.oneOf)) {
    let hits = 0;
    let lastErr = null;
    for (const sub of node.oneOf) {
      const r = validateSchema(sub, value, rootSchema, path, nextRefSeen);
      if (r.ok) hits += 1;
      else lastErr = r;
    }
    if (hits !== 1) {
      return formatError(lastErr?.code ?? 'INVALID_ARGUMENTS', path, hits === 0 ? (lastErr?.message ?? 'value does not match oneOf schema') : 'value matches multiple oneOf branches');
    }
  }

  if (node.const !== undefined && !deepEqual(value, node.const)) {
    return formatError('INVALID_ARGUMENTS', path, `expected constant ${JSON.stringify(node.const)}`);
  }
  if (Array.isArray(node.enum) && !node.enum.some((e) => deepEqual(value, e))) {
    return formatError('INVALID_ENUM_VALUE', path, `expected one of ${JSON.stringify(node.enum)}`);
  }

  if (node.type !== undefined) {
    const types = Array.isArray(node.type) ? node.type : [node.type];
    if (!types.some((t) => matchesType(value, t))) {
      return formatError('INVALID_ARGUMENT_TYPE', path, `expected type ${types.join('|')}, got ${value === null ? 'null' : Array.isArray(value) ? 'array' : typeof value}`);
    }
  }

  if (typeof value === 'string') {
    if (typeof node.minLength === 'number' && value.length < node.minLength) {
      return formatError('ARGUMENT_OUT_OF_RANGE', path, `string length ${value.length} < minLength ${node.minLength}`);
    }
    if (typeof node.maxLength === 'number' && value.length > node.maxLength) {
      return formatError('ARGUMENT_OUT_OF_RANGE', path, `string length ${value.length} > maxLength ${node.maxLength}`);
    }
    if (typeof node.pattern === 'string') {
      // C-VALIDATE-01: the pattern comes from the server's advertised schema, not
      // from us. `new RegExp("[")` throws, and this function runs before the
      // executor's error boundary, so one malformed upstream pattern turned every
      // call to that tool into an unhandled exception instead of a refusal.
      // A pathological pattern is also a ReDoS vector on attacker-controlled input,
      // so refuse anything absurdly long rather than compiling it.
      if (node.pattern.length > 512) {
        return formatError('INVALID_SCHEMA_PATTERN', path, 'schema pattern is too long to evaluate safely');
      }
      let re;
      try {
        re = new RegExp(node.pattern);
      } catch {
        return formatError('INVALID_SCHEMA_PATTERN', path, `schema pattern ${JSON.stringify(node.pattern)} is not a valid regular expression`);
      }
      if (!re.test(value)) {
        return formatError('INVALID_ARGUMENT_FORMAT', path, `string does not match pattern ${node.pattern}`);
      }
    }
  }

  if (typeof value === 'number') {
    if (typeof node.minimum === 'number' && value < node.minimum) {
      return formatError('ARGUMENT_OUT_OF_RANGE', path, `value ${value} < minimum ${node.minimum}`);
    }
    if (typeof node.maximum === 'number' && value > node.maximum) {
      return formatError('ARGUMENT_OUT_OF_RANGE', path, `value ${value} > maximum ${node.maximum}`);
    }
    if (typeof node.exclusiveMinimum === 'number' && value <= node.exclusiveMinimum) {
      return formatError('ARGUMENT_OUT_OF_RANGE', path, `value ${value} <= exclusiveMinimum ${node.exclusiveMinimum}`);
    }
    if (typeof node.exclusiveMaximum === 'number' && value >= node.exclusiveMaximum) {
      return formatError('ARGUMENT_OUT_OF_RANGE', path, `value ${value} >= exclusiveMaximum ${node.exclusiveMaximum}`);
    }
    if (typeof node.multipleOf === 'number' && node.multipleOf > 0) {
      const ratio = value / node.multipleOf;
      if (Math.abs(ratio - Math.round(ratio)) > 1e-9) {
        return formatError('ARGUMENT_OUT_OF_RANGE', path, `value ${value} is not a multiple of ${node.multipleOf}`);
      }
    }
  }

  if (Array.isArray(value)) {
    if (typeof node.minItems === 'number' && value.length < node.minItems) {
      return formatError('ARGUMENT_OUT_OF_RANGE', path, `array length ${value.length} < minItems ${node.minItems}`);
    }
    if (typeof node.maxItems === 'number' && value.length > node.maxItems) {
      return formatError('ARGUMENT_OUT_OF_RANGE', path, `array length ${value.length} > maxItems ${node.maxItems}`);
    }
    if (node.uniqueItems) {
      for (let i = 0; i < value.length; i++) {
        for (let j = i + 1; j < value.length; j++) {
          if (deepEqual(value[i], value[j])) {
            return formatError('INVALID_ARGUMENTS', path, `duplicate item at index ${j}`);
          }
        }
      }
    }
    if (node.items && typeof node.items === 'object') {
      for (let i = 0; i < value.length; i++) {
        const r = validateSchema(node.items, value[i], rootSchema, `${path}[${i}]`);
        if (!r.ok) return r;
      }
    }
  }

  if (isPlainObject(value)) {
    const props = node.properties && typeof node.properties === 'object' ? node.properties : {};
    const required = Array.isArray(node.required) ? node.required : [];
    for (const reqKey of required) {
      if (!Object.prototype.hasOwnProperty.call(value, reqKey) || value[reqKey] === undefined) {
        return formatError('MISSING_REQUIRED_ARGUMENT', `${path}.${reqKey}`, `missing required parameter "${reqKey}"`);
      }
    }

    const disallowUnknown = node.additionalProperties === false
      || (node.additionalProperties === undefined && node.properties !== undefined);

    for (const [k, v] of Object.entries(value)) {
      if (v === undefined) continue;
      if (Object.prototype.hasOwnProperty.call(props, k)) {
        const r = validateSchema(props[k], v, rootSchema, `${path}.${k}`);
        if (!r.ok) return r;
      } else if (disallowUnknown) {
        return formatError('UNKNOWN_ARGUMENT', `${path}.${k}`, `unknown parameter "${k}"`);
      } else if (node.additionalProperties && typeof node.additionalProperties === 'object') {
        const r = validateSchema(node.additionalProperties, v, rootSchema, `${path}.${k}`);
        if (!r.ok) return r;
      }
    }
  }

  return { ok: true };
}
