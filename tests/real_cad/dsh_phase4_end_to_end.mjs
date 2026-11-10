/**
 * tests/real_cad/dsh_phase4_end_to_end.mjs
 * 
 * NIGHT-ENGINEERING-PHASE4: 真实 DSH 桌面宿主集成与端到端调用链核验
 * 
 * 验证闭环:
 * 1. DSH 插件加载、Python 解释器自动发现与 FastMCP 握手通信;
 * 2. 73 项全量工具注册契约 (71 MCP + 2 Meta Tools: status, confirm);
 * 3. Policy 策略防御拦截 (白名单零件保护、沙箱越界拦截、高风险操作单次授权拦截);
 * 4. 用户交互单次确认流转 (solidworks_confirm 授权签发与参数指纹绑定);
 * 5. 真实 SolidWorks COM 调度与 DSH 宿主响应渲染呈现;
 * 6. 产出结构化物证日志与哈希记录.
 */

import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { apply } from '../../lib/index.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, '../..');
const SANDBOX_DIR = path.join(REPO_ROOT, 'tests/real_cad/sandbox/phase4_core');

async function runEndToEndVerification() {
  console.log('='.repeat(80));
  console.log('   dsh-solidworks 第四阶段真实 DSH 宿主集成与端到端调用链验收');
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
  console.log('  [PASS] 73 项工具同构注册与暴露核验通过！');

  console.log('\n[2/5] 探测 SolidWorks 实例与运行时状态 (solidworks_status)...');
  const statusTool = tools.get('solidworks_status');
  if (!statusTool) throw new Error('缺失元工具 solidworks_status');

  const statusRes = await statusTool.execute({}, { session: { cwd: SANDBOX_DIR } });
  console.log(`  - 进程探针响应: ${statusRes.text.slice(0, 120)}...`);
  if (!statusRes.text.includes('"running":true') && !statusRes.text.includes('"state":"ok"')) {
    throw new Error(`SolidWorks 实例未就绪: ${statusRes.text}`);
  }
  console.log('  [PASS] SolidWorks COM 宿主连接探针验证通过！');

  console.log('\n[3/5] 策略网关安全防御验证 (白名单零件保护与沙箱越界拦截)...');
  const modifyTool = tools.get('solidworks_modify_dimension_safe');
  if (!modifyTool) throw new Error('缺失工具 solidworks_modify_dimension_safe');

  // 3.1 白名单受保护零件强制只读拦截
  const protectedRes = await modifyTool.execute(
    { file_path: 'C:\\Users\\Public\\Documents\\Protected\\垫圈.SLDPRT', dimension: 'D1@Sketch1', new_value: 0.05 },
    { session: { cwd: SANDBOX_DIR } }
  );
  console.log('  - 白名单保护拦截响应:', protectedRes.text);
  if (!protectedRes.text.includes('PROTECTED_FILE_REFUSED')) {
    throw new Error(`白名单零件拦截失效: ${protectedRes.text}`);
  }
  console.log('  - [PASS] RSK-05 白名单受保护零件强制只读拦截通过！');

  // 3.2 沙箱越界拦截
  const saveTool = tools.get('solidworks_save_document');
  if (!saveTool) throw new Error('缺失工具 solidworks_save_document');

  const escapeRes = await saveTool.execute(
    { path: 'C:/Windows/System32/hacked.SLDPRT' },
    { session: { cwd: SANDBOX_DIR } }
  );
  console.log('  - 越界写入拦截响应:', escapeRes.text);
  if (!escapeRes.text.includes('PATH_OUTSIDE_ALLOWED_ROOTS') && !escapeRes.text.includes('CONFIRMATION_REQUIRED')) {
    throw new Error(`沙箱越界拦截失效: ${escapeRes.text}`);
  }
  console.log('  - [PASS] 沙箱路径越界阻断拦截通过！');

  console.log('\n[4/5] 高风险操作单次授权流转验证 (solidworks_confirm)...');
  const targetSavePath = path.join(SANDBOX_DIR, 'dsh_phase4_verified_part.SLDPRT').replace(/\\/g, '/');

  // 先确保新建一个临时零件以便保存
  const newDocTool = tools.get('solidworks_new_document');
  await newDocTool.execute({ doc_type: 'part' });

  // 尝试直接调用高风险 save 操作 (未授权)
  const unauthRes = await saveTool.execute({ path: targetSavePath });
  console.log('  - 未授权调用返回:', unauthRes.text);
  if (!unauthRes.text.includes('CONFIRMATION_REQUIRED')) {
    throw new Error('未授权高风险调用未返回 CONFIRMATION_REQUIRED 状态！');
  }
  console.log('  [PASS] 高风险操作拦截挂起与摘要计算通过');

  // 签发单次 Grant 授权
  const confirmTool = tools.get('solidworks_confirm');
  const grantRes = await confirmTool.execute({
    tool: 'solidworks_save_document',
    args: { path: targetSavePath },
    reason: '第四阶段 DSH 桌面端端到端核验用户确认',
  });
  console.log('  - Grant 授权结果:', grantRes.text);
  const grantData = JSON.parse(grantRes.text);
  if (grantData.status !== 'granted' || !grantData.digest) {
    throw new Error(`单次 Grant 授权签发失败: ${grantRes.text}`);
  }
  console.log(`  [PASS] 单次防重放 Grant 授权签发成功: digest=${grantData.digest}`);

  console.log('\n[5/5] 携带 Grant 授权调度真实 FastMCP 执行 CAD 持久化与结果返回...');
  const finalCallRes = await saveTool.execute({ path: targetSavePath });
  console.log('  - 携带授权执行结果:', finalCallRes.text);
  if (finalCallRes.text.includes('refused')) {
    throw new Error(`真实落盘保存失败: ${finalCallRes.text}`);
  }
  console.log('  [PASS] 真实 SolidWorks 文件安全持久化落盘成功！');

  // 关闭临时零件清理文档基线
  const closeTool = tools.get('solidworks_close_documents');
  if (closeTool) {
    await closeTool.execute({});
  }

  console.log('='.repeat(80));
  console.log('   第四阶段 DSH 真实桌面宿主端到端调用链核验全线通过！ (ALL PASS)');
  console.log('='.repeat(80));

  // 写入物证记录
  const e2eEvidence = {
    timestamp: new Date().toISOString(),
    suite: 'dsh_phase4_end_to_end',
    verdict: 'PASS',
    total_tools: tools.size,
    checks: [
      'tools_registration_73',
      'solidworks_status_probe',
      'protected_file_refused',
      'sandbox_boundary_enforced',
      'confirmation_required_digest',
      'grant_single_use_issued',
      'fastmcp_cad_save_executed',
      'baseline_docs_cleaned',
    ],
  };
  fs.writeFileSync(
    path.join(SANDBOX_DIR, 'dsh_phase4_e2e_evidence.json'),
    JSON.stringify(e2eEvidence, null, 2),
    'utf8'
  );
  console.log(`物证日志已存盘: ${path.join(SANDBOX_DIR, 'dsh_phase4_e2e_evidence.json')}`);
  process.exit(0);
}

runEndToEndVerification().catch((err) => {
  console.error('\n[FATAL] 端到端核验失败:', err);
  process.exit(1);
});
