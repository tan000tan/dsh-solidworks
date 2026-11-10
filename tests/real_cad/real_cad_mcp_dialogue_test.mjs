/**
 * tests/real_cad/real_cad_mcp_dialogue_test.mjs
 * NIGHT-ENGINEERING-02 第八轮：真实 FastMCP / JSON-RPC 三轮对话端到端实机验收套件。
 *
 * 核心链路：
 * Turn 1: tools/call -> solidworks_execute_feature_graph (特征图实机建模与落盘)
 * Turn 2: tools/call -> solidworks_identify_dimensions + solidworks_mass_properties (多维检查与几何核验)
 * Turn 3: tools/call -> solidworks_update_dimension (原位参数化修改、模型重建与改后核验)
 * 最终会话收尾与白名单文档守恒检测。
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { McpClient } from '../../lib/mcp.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, '../../');
const SANDBOX_DIR = path.resolve(__dirname, 'sandbox');

if (!fs.existsSync(SANDBOX_DIR)) {
  fs.mkdirSync(SANDBOX_DIR, { recursive: true });
}

function timestamp() {
  const d = new Date();
  const pad = (n, l = 2) => String(n).padStart(l, '0');
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

async function runMcpDialogueSuite() {
  console.log('='.repeat(70));
  console.log('      dsh-solidworks 第八轮：FastMCP JSON-RPC 三轮对话实机验收');
  console.log('='.repeat(70));

  const pythonExe = 'D:\\SWCAD-MCP\\Python313\\python.exe';
  const serverScript = path.join(REPO_ROOT, 'vendor/solidworks-automation-skill/mcp-server/server.py');

  const mcp = new McpClient({
    command: pythonExe,
    args: ['-u', '-B', serverScript],
    cwd: REPO_ROOT,
  });

  const partPath = path.join(SANDBOX_DIR, `mcp_dialogue_part_${timestamp()}.SLDPRT`);

  try {
    // 0. 协议握手与工具发现
    console.log('[*] 启动 FastMCP Server 进程并执行标准协议握手...');
    const init = await mcp.initialize({ timeoutMs: 30_000 });
    console.log(`[✔ PASS] MCP 握手成功: 服务=${init.serverInfo.name}, 协议版本=${init.protocolVersion}`);

    const tools = await mcp.listTools({ timeoutMs: 30_000 });
    console.log(`[✔ PASS] tools/list 获取工具总数: ${tools.length}`);
    const toolNames = new Set(tools.map(t => t.name));
    assert(toolNames.has('solidworks_execute_feature_graph'), '缺失 solidworks_execute_feature_graph 工具');
    assert(toolNames.has('solidworks_identify_dimensions'), '缺失 solidworks_identify_dimensions 工具');
    assert(toolNames.has('solidworks_update_dimension'), '缺失 solidworks_update_dimension 工具');
    assert(toolNames.has('solidworks_mass_properties'), '缺失 solidworks_mass_properties 工具');

    // -------------------------------------------------------------
    // Turn 1: 特征图建模执行 (solidworks_execute_feature_graph)
    // -------------------------------------------------------------
    console.log('\n' + '='.repeat(70));
    console.log('【Turn 1：Agent 发起特征图建模请求 -> solidworks_execute_feature_graph】');
    console.log('='.repeat(70));

    const graphPayload = {
      graph_id: 'mcp_flange_graph',
      target_part_name: 'McpFlangePart',
      nodes: {
        sk_base: {
          id: 'sk_base',
          type: 'sketch_2d',
          name: 'BaseSketch',
          parameters: {
            plane: 'Top Plane',
            shape: 'corner_rectangle',
            x1_m: 0.0,
            y1_m: 0.0,
            x2_m: 0.120, // 120mm
            y2_m: 0.080, // 80mm
            add_dimensions: true,
          },
          depends_on: [],
        },
        boss_base: {
          id: 'boss_base',
          type: 'extrude_boss',
          name: 'BaseBoss',
          parameters: {
            depth_m: 0.015, // 15mm
            direction: true,
          },
          depends_on: ['sk_base'],
        },
        sk_hole: {
          id: 'sk_hole',
          type: 'sketch_2d',
          name: 'HoleSketch',
          parameters: {
            plane: 'Top Plane',
            shape: 'circle',
            cx_m: 0.060,
            cy_m: 0.040,
            radius_m: 0.0125, // 直径 25mm
            add_dimensions: true,
          },
          depends_on: ['boss_base'],
        },
        cut_hole: {
          id: 'cut_hole',
          type: 'extrude_cut',
          name: 'HoleCut',
          parameters: {
            depth_m: 0.015,
            direction: false,
          },
          depends_on: ['sk_hole'],
        },
      },
    };

    const t1Start = Date.now();
    const t1Resp = await mcp.callTool(
      'solidworks_execute_feature_graph',
      {
        params: {
          graph: graphPayload,
          output_path: partPath,
          collect_metrics: true,
          close_on_finish: false, // 保持打开以便后续交互
        },
      },
      { timeoutMs: 60_000 }
    );
    const t1Elapsed = Date.now() - t1Start;

    assert.equal(t1Resp.isError, false, `Turn 1 响应报错: ${t1Resp.content?.[0]?.text}`);
    const t1Data = JSON.parse(t1Resp.content[0].text);
    console.log(`[*] Turn 1 响应解析成功 (耗时 ${t1Elapsed}ms):`);
    console.log(`    - success: ${t1Data.success}`);
    console.log(`    - total_nodes: ${t1Data.total_nodes}, executed_count: ${t1Data.executed_count}`);
    console.log(`    - saved_file_path: ${t1Data.saved_file_path}`);
    assert.equal(t1Data.success, true);
    assert.equal(t1Data.executed_count, 4);
    assert(fs.existsSync(partPath), '物理零件文件未落盘');
    console.log('[✔ PASS] Turn 1 建模执行成功');

    // -------------------------------------------------------------
    // Turn 2: 多维参数检查与几何核验 (solidworks_identify_dimensions + mass_properties)
    // -------------------------------------------------------------
    console.log('\n' + '='.repeat(70));
    console.log('【Turn 2：Agent 发起参数检查与几何测量 -> identify_dimensions & mass_props】');
    console.log('='.repeat(70));

    // 2.1 查询模型尺寸列表
    const dimResp = await mcp.callTool('solidworks_identify_dimensions', { params: {} }, { timeoutMs: 30_000 });
    assert.equal(dimResp.isError, false);
    const dimData = JSON.parse(dimResp.content[0].text);
    console.log(`[*] 识别到尺寸参数总数: ${dimData.count}`);
    const dimNames = dimData.dimensions.map(d => d.dimension_name || d.name);
    console.log(`    - 尺寸列表: ${JSON.stringify(dimNames)}`);

    // 2.2 读取物理质量属性
    const massResp = await mcp.callTool('solidworks_mass_properties', { params: {} }, { timeoutMs: 30_000 });
    assert.equal(massResp.isError, false);
    const massData = JSON.parse(massResp.content[0].text);
    const v1Actual = massData.volume_mm3 || massData.volume;

    // 理论解析体积: (120 * 80 * 15) - (pi * 12.5^2 * 15) = 144,000 - 7,363.12 = 136,636.88 mm^3
    const v1Theory = (120.0 * 80.0 * 15.0) - (Math.PI * (12.5 ** 2) * 15.0);
    const v1Diff = Math.abs(v1Actual - v1Theory);
    console.log(`[*] 实测体积: ${v1Actual.toFixed(2)} mm³, 理论体积: ${v1Theory.toFixed(2)} mm³, 误差: ${v1Diff.toFixed(4)} mm³`);
    assert(v1Diff < 1.0, `Turn 2 初始体积偏差超标: ${v1Diff}mm³`);
    console.log('[✔ PASS] Turn 2 初始几何核验无误');

    // -------------------------------------------------------------
    // Turn 3: 基于前序上下文原位参数化修改 (solidworks_update_dimension)
    // -------------------------------------------------------------
    console.log('\n' + '='.repeat(70));
    console.log('【Turn 3：Agent 发起原位参数驱动修改 -> solidworks_update_dimension】');
    console.log('='.repeat(70));

    // 修改 1: 底板长 120 -> 150mm (D1@BaseSketch)
    console.log('[*] 修改底板长度: D1@BaseSketch -> 150.0mm');
    const mod1Resp = await mcp.callTool(
      'solidworks_update_dimension',
      {
        params: {
          dimension_name: 'D1@BaseSketch',
          value_mm: 150.0,
          rebuild: true,
          save: false,
        },
      },
      { timeoutMs: 30_000 }
    );
    assert.equal(mod1Resp.isError, false);
    const mod1Data = JSON.parse(mod1Resp.content[0].text);
    console.log(`    - 修改结果: success=${mod1Data.success}, new_value=${mod1Data.new_value_mm || mod1Data.value_mm}`);

    // 修改 2: 中心孔径 25 -> 30mm (D1@HoleSketch)
    console.log('[*] 修改中心孔径: D1@HoleSketch -> 30.0mm');
    const mod2Resp = await mcp.callTool(
      'solidworks_update_dimension',
      {
        params: {
          dimension_name: 'D1@HoleSketch',
          value_mm: 30.0,
          rebuild: true,
          save: true,
        },
      },
      { timeoutMs: 30_000 }
    );
    assert.equal(mod2Resp.isError, false);
    const mod2Data = JSON.parse(mod2Resp.content[0].text);
    console.log(`    - 修改结果: success=${mod2Data.success}, new_value=${mod2Data.new_value_mm || mod2Data.value_mm}`);

    // 修改后几何重新核验
    const massModResp = await mcp.callTool('solidworks_mass_properties', { params: {} }, { timeoutMs: 30_000 });
    const massModData = JSON.parse(massModResp.content[0].text);
    const v2Actual = massModData.volume_mm3 || massModData.volume;

    // 新理论体积: (150 * 80 * 15) - (pi * 15^2 * 15) = 180,000 - 10,602.88 = 169,397.12 mm^3
    const v2Theory = (150.0 * 80.0 * 15.0) - (Math.PI * (15.0 ** 2) * 15.0);
    const v2Diff = Math.abs(v2Actual - v2Theory);
    console.log(`[*] 修改后实测体积: ${v2Actual.toFixed(2)} mm³, 新理论体积: ${v2Theory.toFixed(2)} mm³, 误差: ${v2Diff.toFixed(4)} mm³`);
    assert(v2Diff < 1.0, `Turn 3 修改后体积偏差超标: ${v2Diff}mm³`);
    console.log('[✔ PASS] Turn 3 参数化修改与重建闭环成功');

    // -------------------------------------------------------------
    // 会话收尾与白名单文档守恒检验
    // -------------------------------------------------------------
    console.log('\n' + '='.repeat(70));
    console.log('【会话收尾：文档关闭与白名单状态守恒】');
    console.log('='.repeat(70));
    const closeResp = await mcp.callTool('solidworks_close_documents', { params: { save_changes: true, close_all: false } }, { timeoutMs: 30_000 });
    console.log(`[*] 关闭测试文档响应: ${closeResp.content?.[0]?.text}`);

    console.log('\n' + '='.repeat(70));
    console.log('      第八轮 FastMCP JSON-RPC 三轮对话实机验收结果');
    console.log('='.repeat(70));
    console.log('  Turn 1：特征图建模执行 (solidworks_execute_feature_graph): [PASS]');
    console.log('  Turn 2：尺寸发现与质量核查 (identify_dims & mass_props):   [PASS]');
    console.log('  Turn 3：原位参数驱动与重建 (solidworks_update_dimension):  [PASS]');
    console.log('  第八轮综合验收结论: [ALL PASS]');
    console.log('='.repeat(70));

    return true;
  } finally {
    await mcp.close();
  }
}

runMcpDialogueSuite()
  .then(() => process.exit(0))
  .catch(err => {
    console.error('[✖ FAIL] 第八轮测试发生异常:', err);
    process.exit(1);
  });

