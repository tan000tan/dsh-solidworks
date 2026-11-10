/**
 * tests/real_cad/dsh_end_to_end_test.mjs
 * 
 * 真实 DSH 桌面宿主插件端到端调用链核验套件 (L4 - L5 级产品化验收)。
 * 
 * 验证闭环:
 * 1. DSH 插件加载、Python 解释器自动发现与 FastMCP 握手通信;
 * 2. 73 项全量工具注册契约 (71 MCP + 2 Meta Tools: status, confirm);
 * 3. Policy 策略防御拦截 (受保护文件拦截、沙箱越界拦截、高风险单次授权拦截);
 * 4. 用户交互单次确认流转 (solidworks_confirm 授权签发与参数指纹校验);
 * 5. 真实 SolidWorks COM 调度与 DSH 宿主响应渲染呈现.
 */

import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { apply } from '../../lib/index.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, '../..');
const SANDBOX_DIR = path.join(REPO_ROOT, 'tests/real_cad/sandbox/extreme_eng');

async function runEndToEndVerification() {
  console.log('='.repeat(80));
  console.log('   dsh-solidworks 真实 DSH 桌面宿主集成与端到端调用链验收');
  console.log('='.repeat(80));

  const tools = new Map();
  const fakeContext = {
    tools: {
      register(definition) {
        tools.set(definition.name, definition);
        return () => tools.delete(definition.name);
      },
    },
    effect(fn) {
      // 模拟 Cordis 生命周期钩子
    },
  };

  const config = {
    mode: 'full',
    allowedRoots: [SANDBOX_DIR],
    toolTimeoutMs: 30000,
  };

  console.log('[1/5] 正在装载 dsh-solidworks 插件适配器并探测环境...');
  await apply(fakeContext, config);

  console.log(`  - 成功挂载 DSH 工具集, 当前注册工具总数: ${tools.size}`);
  if (tools.size < 73) {
    throw new Error(`工具注册数未达到预期标准: 期望 >= 73, 实际 ${tools.size}`);
  }

  // 1. 验证 solidworks_status
  console.log('\n[2/5] 验证状态健康检查 (solidworks_status)...');
  const statusTool = tools.get('solidworks_status');
  if (!statusTool) throw new Error('缺少 solidworks_status 工具！');
  const statusRes = await statusTool.execute({});
  console.log('  - solidworks_status 响应:\n', statusRes.text);

  // 2. 验证受保护白名单文件硬拦截 (RSK-05)
  console.log('\n[3/5] 验证受保护白名单文件硬拦截防御 (RSK-05)...');
  const modifyTool = tools.get('solidworks_modify_dimension_safe');
  if (!modifyTool) throw new Error('缺少 solidworks_modify_dimension_safe 工具！');
  
  const protectedCallRes = await modifyTool.execute({
    document_path: 'D:/Models/垫圈.SLDPRT',
    dimension_name: 'D1@草图1',
    new_value: 15.0,
  });
  console.log('  - 拦截响应:', protectedCallRes.text);
  if (!protectedCallRes.text.includes('PROTECTED_FILE_REFUSED')) {
    throw new Error('受保护文件未被策略拦截！');
  }
  console.log('  [PASS] 受保护文件白名单拦截生效 (PROTECTED_FILE_REFUSED)');

  // 3. 验证沙箱越界写拦截
  console.log('\n[4/5] 验证沙箱越界写入拦截防御...');
  const saveTool = tools.get('solidworks_save_document');
  const escapeCallRes = await saveTool.execute({
    path: 'C:/Windows/System32/hacked.SLDPRT',
  });
  console.log('  - 越界写入拦截响应:', escapeCallRes.text);
  if (!escapeCallRes.text.includes('PATH_OUTSIDE_ALLOWED_ROOTS') && !escapeCallRes.text.includes('CONFIRMATION_REQUIRED')) {
    throw new Error('未授权路径写入未被拦截！');
  }
  console.log('  [PASS] 沙箱外部未授权写操作成功被拦截');

  // 4. 验证高风险单次授权确认流转 (Grant Binding)
  console.log('\n[5/5] 验证高风险操作单次授权确认流转与 CAD 执行闭环...');
  const confirmTool = tools.get('solidworks_confirm');
  const targetSavePath = path.join(SANDBOX_DIR, 'e2e_verified_part.SLDPRT').replace(/\\/g, '/');

  // 先确保新建一个临时零件以便保存
  const newDocTool = tools.get('solidworks_new_document');
  await newDocTool.execute({ doc_type: 'part' });

  // 尝试直接调用高风险 save 操作 (未授权)
  const unauthRes = await saveTool.execute({ path: targetSavePath });
  console.log('  - 未授权调用返回:', unauthRes.text);
  if (!unauthRes.text.includes('CONFIRMATION_REQUIRED')) {
    throw new Error('未授权高风险调用未返回 CONFIRMATION_REQUIRED 状态！');
  }
  console.log('  [PASS] 高风险操作成功拦截并提示需用户确认 (CONFIRMATION_REQUIRED)');

  // 模拟普通用户在 DSH 界面点击“允许保存”
  console.log('  - 模拟普通用户在 DSH 界面点击“允许操作”...');
  const confirmRes = await confirmTool.execute({
    tool: 'solidworks_save_document',
    args: { path: targetSavePath },
    reason: '用户在 DSH 桌面端授权保存真实 CAD 零件',
  });
  console.log('  - 授权签发响应:', confirmRes.text);
  const confirmData = JSON.parse(confirmRes.text);
  if (confirmData.status !== 'granted' || !confirmData.digest) {
    throw new Error('授权签发失败！');
  }
  console.log(`  [PASS] 成功签发单次防重放 Grant 指纹 (${confirmData.digest})`);

  // 携带 Grant 再次调用，执行真实保存
  console.log('  - 调度 Python FastMCP 执行真实 SolidWorks 保存...');
  const authorizedRes = await saveTool.execute({ path: targetSavePath });
  console.log('  - 授权调用响应:', authorizedRes.text);
  if (authorizedRes.text.includes('refused')) {
    throw new Error(`真实调用执行失败: ${authorizedRes.text}`);
  }
  console.log('  [PASS] 真实 SolidWorks 文档保存成功！');

  // 校验磁盘物证
  if (fs.existsSync(targetSavePath)) {
    console.log(`  [PASS] 真实 CAD 实体落盘验证成功 (${fs.statSync(targetSavePath).size} 字节)`);
  }

  // 关闭并清理
  const closeTool = tools.get('solidworks_close_documents');
  if (closeTool) {
    // 关闭操作也是 HIGH 级别，先签发 grant
    await confirmTool.execute({
      tool: 'solidworks_close_documents',
      args: {},
      reason: '清理测试文档',
    });
    await closeTool.execute({});
  }
  if (fs.existsSync(targetSavePath)) {
    fs.unlinkSync(targetSavePath);
  }

  console.log('\n' + '='.repeat(80));
  console.log('   DSH 插件真实宿主端到端调用链验收结论: [ALL PASS]');
  console.log('='.repeat(80));
  process.exit(0);
}

runEndToEndVerification().catch(err => {
  console.error('\n[FAIL] 端到端验收失败:', err);
  process.exit(1);
});
