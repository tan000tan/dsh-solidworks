/**
 * scripts/dsh_adapter.js
 *
 * DeepSeek Harness (DSH) 客户端集成与配置适配器。
 * 负责与 DSH 宿主环境的零配置自动接入、无损注册、安全备份、回滚与解挂。
 */

import { existsSync, readFileSync, writeFileSync, copyFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import os from 'node:os';

export function getDshHome() {
  const userProfile = process.env.USERPROFILE || process.env.HOME || '';
  return path.join(userProfile, '.dsh');
}

export function getDshDesktopProfileDir() {
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
 * 解析并更新 cordis.patch.yml 中的 dsh-solidworks 配置段
 */
export function registerToDshProfile({
  pythonPath,
  mode = 'read-only',
  toolTimeoutMs = 300000,
  pluginRoot,
} = {}) {
  const profileDir = getDshDesktopProfileDir();
  if (!existsSync(profileDir)) {
    return { ok: false, reason: 'DSH desktop profile directory not found' };
  }

  const patchFile = path.join(profileDir, 'cordis.patch.yml');
  if (!existsSync(patchFile)) {
    return { ok: false, reason: 'cordis.patch.yml not found in desktop profile' };
  }

  // 先备份
  const backupPath = backupCordisPatch(profileDir);

  let content = readFileSync(patchFile, 'utf8');

  // 构建我们要注入的规范配置块
  const escapedPyPath = pythonPath ? pythonPath.replace(/\\/g, '\\\\') : '';
  const pluginBlock = [
    '# ---- SolidWorks MCP (dsh-solidworks) ------------------------------',
    '- id: dsh-solidworks',
    '  config:',
    `    mode: ${mode}`,
    ...(pythonPath ? [`    pythonPath: '${escapedPyPath}'`] : []),
    `    toolTimeoutMs: ${toolTimeoutMs}`,
  ].join('\r\n');

  // 如果已经包含 - id: dsh-solidworks，进行安全替换或更新
  const idRegex = /([ \t]*-[ \t]*id:[ \t]*dsh-solidworks\b[\s\S]*?)(?=\r?\n[ \t]*-[ \t]*id:|\r?\n\[\]|\r?\n# ----|\s*$)/;
  if (idRegex.test(content)) {
    content = content.replace(idRegex, `- id: dsh-solidworks\r\n  config:\r\n    mode: ${mode}\r\n${pythonPath ? `    pythonPath: '${escapedPyPath}'\r\n` : ''}    toolTimeoutMs: ${toolTimeoutMs}`);
  } else {
    // 插入到末尾
    if (!content.endsWith('\n')) content += '\r\n';
    content += '\r\n' + pluginBlock + '\r\n';
  }

  try {
    writeFileSync(patchFile, content, 'utf8');
    return { ok: true, patchFile, backupPath };
  } catch (err) {
    // 回滚备份
    if (backupPath && existsSync(backupPath)) {
      try { copyFileSync(backupPath, patchFile); } catch {}
    }
    return { ok: false, reason: `Failed to write cordis.patch.yml: ${err.message}` };
  }
}

/**
 * 从 cordis.patch.yml 中移除 dsh-solidworks 配置段
 */
export function unregisterFromDshProfile() {
  const profileDir = getDshDesktopProfileDir();
  if (!existsSync(profileDir)) return { ok: true, skipped: true, reason: 'DSH profile directory does not exist' };

  const patchFile = path.join(profileDir, 'cordis.patch.yml');
  if (!existsSync(patchFile)) return { ok: true, skipped: true, reason: 'cordis.patch.yml does not exist' };

  const backupPath = backupCordisPatch(profileDir);
  let content = readFileSync(patchFile, 'utf8');

  // 匹配并删除 dsh-solidworks 节点
  const blockRegex = /(?:# ---- SolidWorks MCP \(dsh-solidworks\) -+[\r\n]+)?([ \t]*-[ \t]*id:[ \t]*dsh-solidworks\b[\s\S]*?)(?=\r?\n[ \t]*-[ \t]*id:|\r?\n\[\]|\r?\n# ----|\s*$)/;
  if (blockRegex.test(content)) {
    content = content.replace(blockRegex, '');
    writeFileSync(patchFile, content.trim() + '\r\n', 'utf8');
    return { ok: true, removed: true, backupPath };
  }

  return { ok: true, removed: false, reason: 'No dsh-solidworks entry found to remove' };
}

/**
 * 校验当前 DSH profile 中是否已正确注册本插件
 */
export function checkDshRegistration() {
  const profileDir = getDshDesktopProfileDir();
  if (!existsSync(profileDir)) return { registered: false, reason: 'DSH profile directory not found' };

  const patchFile = path.join(profileDir, 'cordis.patch.yml');
  if (!existsSync(patchFile)) return { registered: false, reason: 'cordis.patch.yml not found' };

  try {
    const content = readFileSync(patchFile, 'utf8');
    const hasSolidworks = /id:\s*dsh-solidworks\b/.test(content);
    return { registered: hasSolidworks, patchFile };
  } catch (err) {
    return { registered: false, reason: err.message };
  }
}
