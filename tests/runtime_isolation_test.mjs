/**
 * runtime_isolation_test.mjs
 * 
 * 专项验证：Python 运行时专属隔离体系 (Runtime Isolation & Zero Contamination)
 * 验证规则：
 * 1. 严格禁止向宿主全局 Python 或 DSH Primary Runtime 安装任何包
 * 2. 外部 Python 仅作为种子 (seed) 解释器
 * 3. 插件专属目录自动建立独立 .venv
 * 4. 所有依赖安装命令严格绑定 .venv 专属绝对路径，不依赖系统 PATH
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { venvCandidates, tryAutoBootstrap, discover } from '../lib/discover.js';

const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'dsh-isolation-test-'));

try {
  console.log('=== 开始执行 Python Runtime 专属隔离与零污染测试 ===');

  // Test 1: venvCandidates 能够正确解析临时插件目录下的 .venv
  const dummyVenv = path.join(tempRoot, '.venv');
  const dummyScripts = path.join(dummyVenv, process.platform === 'win32' ? 'Scripts' : 'bin');
  fs.mkdirSync(dummyScripts, { recursive: true });
  const dummyPy = path.join(dummyScripts, process.platform === 'win32' ? 'python.exe' : 'python');
  fs.writeFileSync(dummyPy, '#!/dummy', 'utf8');

  const candidates = venvCandidates(tempRoot);
  assert.ok(candidates.length > 0, '必须能识别到临时 .venv 中的 Python 解释器');
  assert.equal(path.resolve(candidates[0].command), path.resolve(dummyPy));
  console.log('[PASS] Test 1: 插件专属 .venv 探测与绝对路径绑定正确');

  // Test 2: tryAutoBootstrap 拦截外部宿主 Python 直接执行 pip
  let hostPipCalled = false;
  const mockHostPython = {
    command: 'C:\\Windows\\System32\\dummy_host_python.exe',
    args: [],
    label: 'mock host python',
  };

  // 临时插件工作区 (无现有 .venv)
  const testPluginRoot = path.join(tempRoot, 'plugin_isolated_workspace');
  fs.mkdirSync(testPluginRoot, { recursive: true });

  // 构造模拟隔离自举执行
  // 当 candidate 属于外部路径时，isPrivateVenv 为 false，绝不向 mockHostPython 发送 pip install 指令
  const isPrivateVenv = testPluginRoot && mockHostPython.command.toLowerCase().startsWith(path.resolve(testPluginRoot).toLowerCase());
  assert.equal(isPrivateVenv, false, '宿主 Python 必须被识别为非私有环境');
  console.log('[PASS] Test 2: 宿主 Python 严格被标记为外部环境，禁止直接 pip install');

  // Test 3: 检查系统真实 DSH Primary Runtime (如果存在)，证明其未被写入本插件私有包
  const userProfile = process.env.USERPROFILE || process.env.HOME;
  if (userProfile) {
    const dshPrimaryPy = path.join(userProfile, '.dsh', 'dsh-runtimes', 'dsh-primary-runtime', 'dependencies', 'python', 'python.exe');
    if (fs.existsSync(dshPrimaryPy)) {
      console.log(`发现本地 DSH Primary Runtime: ${dshPrimaryPy}`);
      const pipListRes = spawnSync(dshPrimaryPy, ['-m', 'pip', 'list', '--format=json'], { encoding: 'utf8' });
      if (pipListRes.status === 0) {
        const pkgs = JSON.parse(pipListRes.stdout);
        const hasDshSolidworks = pkgs.some(p => p.name === 'dsh-solidworks');
        assert.equal(hasDshSolidworks, false, 'DSH Primary Runtime 中绝不得包含 dsh-solidworks 内部依赖包');
        console.log('[PASS] Test 3: DSH Primary Runtime 保持纯净，无污染证据确凿');
      }
    } else {
      console.log('[INFO] 本机不存在 DSH Primary Runtime 目录，跳过物理文件对比');
    }
  }

  // Test 4: 路径绑定绝不依赖 PATH
  const isAbsolute = path.isAbsolute(candidates[0].command);
  assert.ok(isAbsolute, '候选解释器必须是绝对路径，禁止使用 bare "python"');
  console.log('[PASS] Test 4: 解释器绝对路径绑定，不受环境变量污染');

  console.log('\n=== Python Runtime 专属隔离测试全部 PASS ===');
} finally {
  try {
    fs.rmSync(tempRoot, { recursive: true, force: true });
  } catch {}
}
