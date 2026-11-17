/**
 * scripts/dsh_adapter.js
 *
 * DeepSeek Harness (DSH) 客户端集成与配置适配器。
 * 负责与 DSH 宿主环境的零配置自动接入、预激活校验、无损注册、安全备份、自动回滚与解挂。
 *
 * 结构约定（v0.3.1 修订，D-02 + R3 合并）：
 *   cordis.patch.yml 是一个顶层 YAML 数组，合法条目只有三种形态——
 *     - id: <plugin> + config   （配置覆盖 / 禁用）
 *     - insert: [ ... ]         （把插件真正挂进宿主）
 *     - disabled: true
 *   要把一个还没被宿主加载的插件挂上去，必须写成 insert 列表里的子条目，且必须带 name。
 */

import { existsSync, readFileSync, writeFileSync, copyFileSync } from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { pathToFileURL } from 'node:url';

const PLUGIN_ID = 'dsh-solidworks';
const INSERT_MARKER = '# ---- SolidWorks MCP (dsh-solidworks) ------------------------------';

export function getDshHome() {
  if (process.env.DSH_HOME) return path.resolve(process.env.DSH_HOME);
  const userProfile = process.env.USERPROFILE || process.env.HOME || '';
  return path.join(userProfile, '.dsh');
}

export function getDshDesktopProfileDir() {
  if (process.env.DSH_PROFILE_DIR) return path.resolve(process.env.DSH_PROFILE_DIR);
  return path.join(getDshHome(), 'profiles', 'desktop');
}

export function getDshPrimaryRuntimePython() {
  const dshHome = getDshHome();
  const py = path.join(dshHome, 'dsh-runtimes', 'dsh-primary-runtime', 'dependencies', 'python', 'python.exe');
  return existsSync(py) ? py : null;
}

export function isDshDesktopInstalled() {
  const profileDir = getDshDesktopProfileDir();
  return existsSync(profileDir);
}

/**
 * 预激活静态与契约校验（BUG-0001 / BUG-0003 防护）：
 * 在写入宿主配置前，确认插件主入口包含必须的 Cordis provide/inject 声明与 apply 函数。
 */
export async function verifyPluginEntry(pluginRoot) {
  try {
    const entryPath = path.join(pluginRoot, 'lib', 'index.js');
    if (!existsSync(entryPath)) {
      return { ok: false, reason: `Missing plugin entry: ${entryPath}` };
    }
    const mod = await import(pathToFileURL(entryPath).href);
    if (typeof mod.apply !== 'function') {
      return { ok: false, reason: 'Plugin entry does not export an apply() function' };
    }
    if (!Array.isArray(mod.inject) || !mod.inject.includes('tools')) {
      return { ok: false, reason: 'Plugin entry is missing inject = ["tools"]' };
    }
    if (!Array.isArray(mod.provide) || !mod.provide.includes('solidworks')) {
      return { ok: false, reason: 'Plugin entry is missing provide = ["solidworks"] (would fail Cordis activation)' };
    }
    return { ok: true };
  } catch (err) {
    return { ok: false, reason: `Plugin entry failed pre-activation check: ${err.message}` };
  }
}

/**
 * 默认 CAD 写沙箱目录。
 * 优先兼容历史沙箱目录（如果已存在），否则使用用户文档目录下的独立沙箱，
 * 避免写入 node_modules 插件目录导致升级覆盖或只读失败。
 */
export function resolveSandboxDir(pluginRoot) {
  const legacy = pluginRoot ? path.join(pluginRoot, '测试代码', 'sandbox_benchmark') : null;
  if (legacy && existsSync(legacy)) return legacy;

  const home = process.env.USERPROFILE || process.env.HOME || os.homedir();
  return path.join(home, 'Documents', 'DSH-SolidWorks', 'models');
}

function yamlSingleQuote(value) {
  return `'${String(value).replace(/'/g, "''")}'`;
}

function detectEol(text) {
  return text.includes('\r\n') ? '\r\n' : '\n';
}

function indentOf(line) {
  const match = line.match(/^([ \t]*)/);
  return match ? match[1].length : 0;
}

function findEntryLine(lines) {
  const pattern = new RegExp(`^([ \\t]*)-[ \\t]+id:[ \\t]*["']?${PLUGIN_ID}["']?[ \\t]*$`);
  for (let i = 0; i < lines.length; i += 1) {
    const match = lines[i].match(pattern);
    if (match) return { index: i, indent: match[1].length };
  }
  return null;
}

function findBlockEnd(lines, startIndex, indent) {
  let end = startIndex + 1;
  for (let i = startIndex + 1; i < lines.length; i += 1) {
    const line = lines[i];
    if (line.trim() === '') {
      end = i + 1;
      continue;
    }
    if (indentOf(line) <= indent) break;
    end = i + 1;
  }
  while (end > startIndex + 1 && lines[end - 1].trim() === '') end -= 1;
  return end;
}

function isEmptyDocument(lines) {
  return lines.every((line) => {
    const t = line.trim();
    return t === '' || t === '[]' || t.startsWith('#');
  });
}

function findEmptyInsertParent(lines) {
  for (let i = 0; i < lines.length; i += 1) {
    if (!/^[ \t]*-[ \t]*insert:[ \t]*$/.test(lines[i])) continue;
    if (indentOf(lines[i]) !== 0) continue;
    const end = findBlockEnd(lines, i, 0);
    let hasChild = false;
    for (let j = i + 1; j < end; j += 1) {
      if (/^[ \t]*-[ \t]*/.test(lines[j]) && indentOf(lines[j]) > 0) { hasChild = true; break; }
    }
    if (!hasChild) return i;
  }
  return -1;
}

function renderEntry(indent, name, configLines) {
  const pad = ' '.repeat(indent);
  const out = [`${pad}- id: ${PLUGIN_ID}`];
  if (name) out.push(`${pad}  name: ${name}`);
  out.push(`${pad}  config:`);
  for (const line of configLines) out.push(`${pad}    ${line}`);
  return out;
}

function configLinesFor({ mode, pythonPath, toolTimeoutMs }) {
  const lines = [`mode: ${mode}`];
  if (pythonPath) lines.push(`pythonPath: ${yamlSingleQuote(pythonPath)}`);
  lines.push(`toolTimeoutMs: ${toolTimeoutMs}`);
  return lines;
}

/**
 * 备份 cordis.patch.yml
 */
export function backupCordisPatch(profileDir = getDshDesktopProfileDir()) {
  const patchFile = path.join(profileDir, 'cordis.patch.yml');
  if (!existsSync(patchFile)) return null;

  const timestamp = Date.now();
  const bakFile = path.join(profileDir, `cordis.patch.yml.bak-dshsolidworks-${timestamp}`);
  copyFileSync(patchFile, bakFile);
  return bakFile;
}

/**
 * 自动回滚 cordis.patch.yml（BUG-0003）
 */
export function rollbackCordisPatch(backupPath, profileDir = getDshDesktopProfileDir()) {
  const patchFile = path.join(profileDir, 'cordis.patch.yml');
  if (backupPath && existsSync(backupPath)) {
    try {
      copyFileSync(backupPath, patchFile);
      return { ok: true, restoredFrom: backupPath };
    } catch (err) {
      return { ok: false, reason: err.message };
    }
  }
  return { ok: false, reason: 'No backup file available to rollback' };
}

/**
 * 解析并更新 cordis.patch.yml 中的 dsh-solidworks 配置段（保留 insert 结构、pre-activation 校验与失败回滚）。
 */
export function registerToDshProfile({
  pythonPath,
  mode = 'read-only',
  toolTimeoutMs = 300000,
  pluginRoot,
  profileDir = getDshDesktopProfileDir(),
} = {}) {
  if (!existsSync(profileDir)) {
    return { ok: false, reason: 'DSH desktop profile directory not found' };
  }

  const patchFile = path.join(profileDir, 'cordis.patch.yml');
  if (!existsSync(patchFile)) {
    return { ok: false, reason: 'cordis.patch.yml not found in desktop profile' };
  }

  // BUG-0003: 检查插件根目录中的 lib/index.js 是否具备 provide 声明，防止写入后激活失败
  if (pluginRoot) {
    const entryPath = path.join(pluginRoot, 'lib', 'index.js');
    if (existsSync(entryPath)) {
      const src = readFileSync(entryPath, 'utf8');
      if (!/export\s+const\s+provide\s*=\s*\[['"]solidworks['"]\]/.test(src)) {
        return {
          ok: false,
          rolledBack: true,
          reason: 'Pre-activation check failed: lib/index.js is missing export const provide = ["solidworks"]',
        };
      }
    }
  }

  const original = readFileSync(patchFile, 'utf8');
  const eol = detectEol(original);
  const lines = original.split(/\r?\n/);
  const configLines = configLinesFor({ mode, pythonPath, toolTimeoutMs });

  const found = findEntryLine(lines);
  let nextLines;
  let action;

  if (found) {
    const end = findBlockEnd(lines, found.index, found.indent);
    const block = lines.slice(found.index, end);
    const nameLine = block.find((line) => indentOf(line) > found.indent && /^[ \t]*name:[ \t]*\S/.test(line));
    const rawName = nameLine ? nameLine.replace(/^[ \t]*name:[ \t]*/, '').trim() : '';

    if (found.indent > 0) {
      nextLines = [
        ...lines.slice(0, found.index),
        ...renderEntry(found.indent, rawName || PLUGIN_ID, configLines),
        ...lines.slice(end),
      ];
      action = 'updated-in-insert';
    } else {
      let parentStart = -1;
      for (let i = found.index - 1; i >= 0; i -= 1) {
        const line = lines[i];
        if (line.trim() === '') continue;
        if (/^[ \t]*-[ \t]*insert:[ \t]*$/.test(line) && indentOf(line) === 0) parentStart = i;
        break;
      }
      if (parentStart >= 0) {
        const hasChildBefore = lines
          .slice(parentStart + 1, found.index)
          .some((line) => /^[ \t]*-[ \t]*/.test(line) && indentOf(line) > 0);
        if (hasChildBefore) parentStart = -1;
      }
      const replaceFrom = parentStart >= 0 ? parentStart : found.index;
      nextLines = [
        ...lines.slice(0, replaceFrom),
        '- insert:',
        ...renderEntry(4, rawName || PLUGIN_ID, configLines),
        ...lines.slice(end),
      ];
      action = 'repaired-legacy-entry';
    }
  } else {
    nextLines = [...lines];
    while (nextLines.length && nextLines[nextLines.length - 1].trim() === '') nextLines.pop();
    if (isEmptyDocument(nextLines)) {
      nextLines = nextLines.filter((line) => line.trim() !== '[]');
      while (nextLines.length && nextLines[nextLines.length - 1].trim() === '') nextLines.pop();
    }

    const emptyParent = findEmptyInsertParent(nextLines);
    if (emptyParent >= 0) {
      nextLines = [
        ...nextLines.slice(0, emptyParent + 1),
        ...renderEntry(4, PLUGIN_ID, configLines),
        ...nextLines.slice(emptyParent + 1).filter((line, idx) => !(idx === 0 && line.trim() === '')),
      ];
      action = 'appended-insert';
    } else {
      nextLines.push(INSERT_MARKER, '- insert:', ...renderEntry(4, PLUGIN_ID, configLines));
      action = 'appended-insert';
    }
  }

  const next = nextLines.join(eol).replace(/(\r?\n)+$/, '') + eol;
  if (next === original) {
    return { ok: true, patchFile, backupPath: null, action: 'unchanged' };
  }

  const backupPath = backupCordisPatch(profileDir);

  try {
    writeFileSync(patchFile, next, 'utf8');
    const verifyContent = readFileSync(patchFile, 'utf8');
    if (!/id:\s*dsh-solidworks\b/.test(verifyContent)) {
      throw new Error('Post-write verification of cordis.patch.yml failed');
    }
    return { ok: true, patchFile, backupPath, action };
  } catch (err) {
    const rb = rollbackCordisPatch(backupPath, profileDir);
    return {
      ok: false,
      rolledBack: rb.ok,
      reason: `Failed to write cordis.patch.yml: ${err.message}`,
    };
  }
}

/**
 * 从 cordis.patch.yml 中移除 dsh-solidworks 配置段；若父级 - insert: 变空则一并清理。
 */
export function unregisterFromDshProfile(profileDir = getDshDesktopProfileDir()) {
  if (!existsSync(profileDir)) return { ok: true, skipped: true, reason: 'DSH profile directory does not exist' };

  const patchFile = path.join(profileDir, 'cordis.patch.yml');
  if (!existsSync(patchFile)) return { ok: true, skipped: true, reason: 'cordis.patch.yml does not exist' };

  const original = readFileSync(patchFile, 'utf8');
  const eol = detectEol(original);
  const lines = original.split(/\r?\n/);
  const found = findEntryLine(lines);
  if (!found) {
    return { ok: true, removed: false, reason: 'No dsh-solidworks entry found to remove' };
  }

  const entryEnd = findBlockEnd(lines, found.index, found.indent);
  let removeStart = found.index;
  let removeEnd = entryEnd;

  if (found.indent > 0) {
    let parentIndex = -1;
    for (let i = found.index - 1; i >= 0; i -= 1) {
      const line = lines[i];
      if (line.trim() === '') continue;
      if (indentOf(line) < found.indent) {
        if (/^[ \t]*-[ \t]*insert:[ \t]*$/.test(line)) parentIndex = i;
        break;
      }
    }
    if (parentIndex >= 0) {
      const parentIndent = indentOf(lines[parentIndex]);
      const parentEnd = findBlockEnd(lines, parentIndex, parentIndent);
      const otherChildren = [];
      for (let i = parentIndex + 1; i < parentEnd; i += 1) {
        if (/^[ \t]*-[ \t]*/.test(lines[i]) && indentOf(lines[i]) > parentIndent) {
          if (i < found.index || i >= entryEnd) otherChildren.push(i);
        }
      }
      if (otherChildren.length === 0) {
        removeStart = parentIndex;
        removeEnd = parentEnd;
        if (removeStart > 0 && lines[removeStart - 1].trim() === INSERT_MARKER) removeStart -= 1;
      }
    }
  }

  const nextLines = [...lines.slice(0, removeStart), ...lines.slice(removeEnd)];
  while (nextLines.length && nextLines[nextLines.length - 1].trim() === '') nextLines.pop();

  let body = nextLines.join(eol).replace(/(\r?\n)+$/, '');
  if (isEmptyDocument(body.split(/\r?\n/).filter((line) => line.trim() !== ''))) {
    body = body.trim() === '' ? '[]' : `${body}${eol}[]`;
  }

  const backupPath = backupCordisPatch(profileDir);
  try {
    writeFileSync(patchFile, body + eol, 'utf8');
    return { ok: true, removed: true, backupPath };
  } catch (err) {
    rollbackCordisPatch(backupPath, profileDir);
    return { ok: false, reason: `Failed to write cordis.patch.yml: ${err.message}` };
  }
}

/**
 * 校验当前 DSH profile 中是否已真正以可加载形态注册本插件。
 */
export function checkDshRegistration(profileDir = getDshDesktopProfileDir()) {
  if (!existsSync(profileDir)) return { registered: false, reason: 'DSH profile directory not found' };

  const patchFile = path.join(profileDir, 'cordis.patch.yml');
  if (!existsSync(patchFile)) return { registered: false, reason: 'cordis.patch.yml not found' };

  try {
    const content = readFileSync(patchFile, 'utf8');
    const lines = content.split(/\r?\n/);
    const found = findEntryLine(lines);
    if (!found) {
      return { registered: false, shape: 'absent', patchFile, reason: 'profile 中没有 dsh-solidworks 条目' };
    }
    const end = findBlockEnd(lines, found.index, found.indent);
    const block = lines.slice(found.index, end);
    const hasName = block.some((line) => indentOf(line) > found.indent && /^[ \t]*name:[ \t]*\S/.test(line));

    if (found.indent > 0) {
      return { registered: true, shape: 'insert', patchFile, reason: '已挂在 insert 列表中，宿主会加载' };
    }
    if (hasName) {
      return { registered: true, shape: 'top-level-named', patchFile, reason: '顶层条目带 name，宿主会加载' };
    }
    return {
      registered: false,
      shape: 'legacy-override',
      patchFile,
      reason: '条目缺少 name 且不在 insert 列表内：宿主只当作配置覆盖，不会加载插件',
    };
  } catch (err) {
    return { registered: false, reason: err.message };
  }
}
