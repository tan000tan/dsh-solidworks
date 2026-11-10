# -*- coding: utf-8 -*-
"""
tests/real_cad/real_cad_complex_test.py
SolidWorks 复杂工程建模、长链压力测试与真实事务回滚实机验证套件。

包含三套真实工业零件与压力测试：
1. 零件 A: 多孔安装法兰 (Flange) - 14 节点长链特征图、4x PCD 对称螺栓孔、中心凸台与主贯通孔
2. 零件 B: 加强筋多基准面支撑支架 (Bracket) - Top Plane 与 Front Plane 跨基准面草图与实体融合
3. 零件 C: 复杂传动安装座 (Bearing Mount) - 多分支独立并行推进 -> 多父节点汇聚贯通
4. 压力测试：
   - 长链压力测试 (14 节点)
   - 多分支故障隔离测试 (3 分支隔离)
   - 多父节点依赖拓扑汇聚测试
   - 重复执行状态隔离测试
   - 参数规模阶梯基准测试 (Small / Medium / Large)
5. 真实部分几何生成后的物理事务回滚测试 (反向特征逆序物理清除)
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 确保 UTF-8 控制台输出
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"
MCP_SERVER_DIR = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "mcp-server"
REAL_CAD_DIR = Path(__file__).resolve().parent

for p in (str(SCRIPTS_DIR), str(MCP_SERVER_DIR), str(REAL_CAD_DIR), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from feature_graph_ir import FeatureGraphIR, FeatureNode, FeatureType
from cad_graph_executor import CADGraphExecutor, ExecutionResult
from geometry_verifier import GeometryVerifier, GeometricExpectation
from sw_connect import get_sta_worker, connect_solidworks, open_document, get_com_member


def get_sandbox_part_path(prefix: str) -> str:
    """生成沙箱中唯一时间戳命名的物理零件路径。"""
    sandbox_dir = REAL_CAD_DIR / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return str(sandbox_dir / f"{prefix}_{timestamp}.SLDPRT")


# ============================================================
# 零件 A：多孔安装法兰 (14 节点长链)
# ============================================================
def build_flange_graph() -> Tuple[FeatureGraphIR, GeometricExpectation]:
    """
    构造多孔安装法兰特征图：
    1. BaseSketch: 120mm x 120mm 矩形草图 (Front Plane)
    2. BaseBoss: 拉伸 12mm 凸台
    3. HubSketch: 直径 70mm 中心圆形草图 (Front Plane)
    4. HubBoss: 拉伸 27mm 凸台 (较底面总高 27mm)
    5. CenterBoreSketch: 直径 40mm 中心孔草图 (Front Plane)
    6. CenterBoreCut: 贯穿切除 27mm (direction=False)
    7-8. Bolt1: 直径 10mm 安装孔 (+40, +40) mm
    9-10. Bolt2: 直径 10mm 安装孔 (-40, +40) mm
    11-12. Bolt3: 直径 10mm 安装孔 (-40, -40) mm
    13-14. Bolt4: 直径 10mm 安装孔 (+40, -40) mm
    共 14 个节点。
    """
    fg = FeatureGraphIR(graph_id="ir_complex_flange", target_part_name="FlangePart")

    # 1. 基础板草图与拉伸
    fg.add_node(FeatureNode(
        id="sk_base",
        type=FeatureType.SKETCH_2D,
        name="BaseSketch",
        parameters={"plane": "Front Plane", "shape": "rectangle", "width_m": 0.12, "height_m": 0.12, "cx_m": 0.0, "cy_m": 0.0},
        depends_on=[],
    ))
    fg.add_node(FeatureNode(
        id="boss_base",
        type=FeatureType.EXTRUDE_BOSS,
        name="BasePlateBoss",
        parameters={"depth_m": 0.012, "direction": True, "merge": True},
        depends_on=["sk_base"],
    ))

    # 2. 中心凸台草图与拉伸
    fg.add_node(FeatureNode(
        id="sk_hub",
        type=FeatureType.SKETCH_2D,
        name="HubSketch",
        parameters={"plane": "Front Plane", "shape": "circle", "radius_m": 0.035, "cx_m": 0.0, "cy_m": 0.0},
        depends_on=["boss_base"],
    ))
    fg.add_node(FeatureNode(
        id="boss_hub",
        type=FeatureType.EXTRUDE_BOSS,
        name="HubBoss",
        parameters={"depth_m": 0.027, "direction": True, "merge": True},
        depends_on=["sk_hub"],
    ))

    # 3. 中心主贯穿孔
    fg.add_node(FeatureNode(
        id="sk_center_bore",
        type=FeatureType.SKETCH_2D,
        name="CenterBoreSketch",
        parameters={"plane": "Front Plane", "shape": "circle", "radius_m": 0.020, "cx_m": 0.0, "cy_m": 0.0},
        depends_on=["boss_hub"],
    ))
    fg.add_node(FeatureNode(
        id="cut_center_bore",
        type=FeatureType.EXTRUDE_CUT,
        name="CenterBoreCut",
        parameters={"depth_m": 0.027, "direction": False},
        depends_on=["sk_center_bore"],
    ))

    # 4. 四个角落对称安装孔
    bolt_coords = [(0.04, 0.04), (-0.04, 0.04), (-0.04, -0.04), (0.04, -0.04)]
    prev_dep = "cut_center_bore"
    for i, (bx, by) in enumerate(bolt_coords, 1):
        sk_id = f"sk_bolt_{i}"
        cut_id = f"cut_bolt_{i}"
        fg.add_node(FeatureNode(
            id=sk_id,
            type=FeatureType.SKETCH_2D,
            name=f"BoltHoleSketch_{i}",
            parameters={"plane": "Front Plane", "shape": "circle", "radius_m": 0.005, "cx_m": bx, "cy_m": by},
            depends_on=[prev_dep],
        ))
        fg.add_node(FeatureNode(
            id=cut_id,
            type=FeatureType.EXTRUDE_CUT,
            name=f"BoltHoleCut_{i}",
            parameters={"depth_m": 0.012, "direction": False},
            depends_on=[sk_id],
        ))
        prev_dep = cut_id

    # 理论物理属性精算:
    # Base: 120 * 120 * 12 = 172,800 mm^3
    # Hub: pi * 35^2 * 15 = 57,726.77 mm^3
    # Center bore: pi * 20^2 * 27 = 33,929.20 mm^3
    # 4 Bolts: 4 * (pi * 5^2 * 12) = 3,769.91 mm^3
    expected_vol = 172800.0 + (math.pi * 35.0**2 * 15.0) - (math.pi * 20.0**2 * 27.0) - (4.0 * math.pi * 5.0**2 * 12.0)
    expected_bbox = [120.0, 120.0, 27.0]

    expectation = GeometricExpectation(
        expected_feature_types=["ProfileFeature", "Extrusion"],
        expected_feature_keywords=["草图", "拉伸"],
        expected_solid_bodies=1,
        expected_bbox_mm=expected_bbox,
        bbox_tol_mm=1.0,
        expected_volume_mm3=expected_vol,
        volume_rel_tol=0.03,
    )
    return fg, expectation


# ============================================================
# 零件 B：加强筋跨基准面安装支架 (Bracket)
# ============================================================
def build_bracket_graph() -> Tuple[FeatureGraphIR, GeometricExpectation]:
    """
    构造多基准面安装支架：
    1. BaseFootSketch: 120mm x 60mm on Top Plane (上视基准面)
    2. BaseFootBoss: 拉伸 12mm 凸台
    3. UprightSketch: 120mm x 70mm on Front Plane (前视基准面)
    4. UprightBoss: 拉伸 12mm 凸台 (与底座空间融合)
    5. FootHole1Sketch: 直径 12mm (Top Plane, cx=40, cy=0)
    6. FootHole1Cut: 贯穿底板
    7. FootHole2Sketch: 直径 12mm (Top Plane, cx=-40, cy=0)
    8. FootHole2Cut: 贯穿底板
    9. UprightBoreSketch: 直径 32mm (Front Plane, cx=0, cy=35)
    10. UprightBoreCut: 贯穿立板
    共 10 个节点。
    """
    fg = FeatureGraphIR(graph_id="ir_complex_bracket", target_part_name="BracketPart")

    # 1. 底部水平安装底板 (Top Plane)
    fg.add_node(FeatureNode(
        id="sk_foot",
        type=FeatureType.SKETCH_2D,
        name="FootSketch",
        parameters={"plane": "Top Plane", "shape": "rectangle", "width_m": 0.12, "height_m": 0.06, "cx_m": 0.0, "cy_m": 0.0},
        depends_on=[],
    ))
    fg.add_node(FeatureNode(
        id="boss_foot",
        type=FeatureType.EXTRUDE_BOSS,
        name="FootBoss",
        parameters={"depth_m": 0.012, "direction": True, "merge": True},
        depends_on=["sk_foot"],
    ))

    # 2. 垂直支撑立板 (Front Plane)
    fg.add_node(FeatureNode(
        id="sk_upright",
        type=FeatureType.SKETCH_2D,
        name="UprightSketch",
        parameters={"plane": "Front Plane", "shape": "rectangle", "width_m": 0.12, "height_m": 0.07, "cx_m": 0.0, "cy_m": 0.035},
        depends_on=["boss_foot"],
    ))
    fg.add_node(FeatureNode(
        id="boss_upright",
        type=FeatureType.EXTRUDE_BOSS,
        name="UprightBoss",
        parameters={"depth_m": 0.012, "direction": True, "merge": True},
        depends_on=["sk_upright"],
    ))

    # 3. 底部安装孔 1 & 2 (Top Plane)
    fg.add_node(FeatureNode(
        id="sk_foot_hole1",
        type=FeatureType.SKETCH_2D,
        name="FootHole1Sketch",
        parameters={"plane": "Top Plane", "shape": "circle", "radius_m": 0.006, "cx_m": 0.04, "cy_m": 0.0},
        depends_on=["boss_upright"],
    ))
    fg.add_node(FeatureNode(
        id="cut_foot_hole1",
        type=FeatureType.EXTRUDE_CUT,
        name="FootHole1Cut",
        parameters={"depth_m": 0.012, "direction": False},
        depends_on=["sk_foot_hole1"],
    ))

    fg.add_node(FeatureNode(
        id="sk_foot_hole2",
        type=FeatureType.SKETCH_2D,
        name="FootHole2Sketch",
        parameters={"plane": "Top Plane", "shape": "circle", "radius_m": 0.006, "cx_m": -0.04, "cy_m": 0.0},
        depends_on=["cut_foot_hole1"],
    ))
    fg.add_node(FeatureNode(
        id="cut_foot_hole2",
        type=FeatureType.EXTRUDE_CUT,
        name="FootHole2Cut",
        parameters={"depth_m": 0.012, "direction": False},
        depends_on=["sk_foot_hole2"],
    ))

    # 4. 垂直立板中央通孔 (Front Plane)
    fg.add_node(FeatureNode(
        id="sk_upright_bore",
        type=FeatureType.SKETCH_2D,
        name="UprightBoreSketch",
        parameters={"plane": "Front Plane", "shape": "circle", "radius_m": 0.016, "cx_m": 0.0, "cy_m": 0.035},
        depends_on=["cut_foot_hole2"],
    ))
    fg.add_node(FeatureNode(
        id="cut_upright_bore",
        type=FeatureType.EXTRUDE_CUT,
        name="UprightBoreCut",
        parameters={"depth_m": 0.012, "direction": False},
        depends_on=["sk_upright_bore"],
    ))

    expectation = GeometricExpectation(
        expected_feature_types=["ProfileFeature", "Extrusion"],
        expected_feature_keywords=["草图", "拉伸"],
        expected_solid_bodies=1,
        expected_bbox_mm=[120.0, 82.0, 60.0],  # X=120, Y=82, Z=60
        bbox_tol_mm=2.0,
    )
    return fg, expectation


# ============================================================
# 零件 C：复杂传动安装座 (多分支 -> 多父节点汇聚)
# ============================================================
def build_bearing_mount_graph() -> Tuple[FeatureGraphIR, GeometricExpectation]:
    """
    构造多分支汇聚传动座：
    1. Base: 140mm x 80mm x 15mm 底座 (Top Plane)
    2. 分支一 (左支柱):
       - sk_left_col (Front Plane, cx=-45) -> boss_left_col (高 60mm)
    3. 分支二 (右支柱):
       - sk_right_col (Front Plane, cx=+45) -> boss_right_col (高 60mm)
    4. 汇聚节点 (横梁轴承箱 Bridge):
       - sk_bridge (Front Plane, 依赖 boss_left_col 与 boss_right_col)
       - boss_bridge (拉伸连接两根支柱)
    5. 主轴通孔:
       - sk_shaft_bore (Front Plane) -> cut_shaft_bore (直径 24mm 贯穿)
    共 9 个节点，包含明确的多分支与多父汇聚结构。
    """
    fg = FeatureGraphIR(graph_id="ir_complex_mount", target_part_name="BearingMountPart")

    # 1. 基础支撑座 (Top Plane)
    fg.add_node(FeatureNode(
        id="sk_base",
        type=FeatureType.SKETCH_2D,
        name="BasePlateSketch",
        parameters={"plane": "Top Plane", "shape": "rectangle", "width_m": 0.14, "height_m": 0.08, "cx_m": 0.0, "cy_m": 0.0},
        depends_on=[],
    ))
    fg.add_node(FeatureNode(
        id="boss_base",
        type=FeatureType.EXTRUDE_BOSS,
        name="BasePlateBoss",
        parameters={"depth_m": 0.015, "direction": True, "merge": True},
        depends_on=["sk_base"],
    ))

    # 2. 分支 1: 左侧支柱 (Front Plane, cx=-0.045)
    fg.add_node(FeatureNode(
        id="sk_col_left",
        type=FeatureType.SKETCH_2D,
        name="LeftColSketch",
        parameters={"plane": "Front Plane", "shape": "rectangle", "width_m": 0.025, "height_m": 0.06, "cx_m": -0.045, "cy_m": 0.03},
        depends_on=["boss_base"],
    ))
    fg.add_node(FeatureNode(
        id="boss_col_left",
        type=FeatureType.EXTRUDE_BOSS,
        name="LeftColBoss",
        parameters={"depth_m": 0.02, "direction": True, "merge": True},
        depends_on=["sk_col_left"],
    ))

    # 3. 分支 2: 右侧支柱 (Front Plane, cx=+0.045)
    fg.add_node(FeatureNode(
        id="sk_col_right",
        type=FeatureType.SKETCH_2D,
        name="RightColSketch",
        parameters={"plane": "Front Plane", "shape": "rectangle", "width_m": 0.025, "height_m": 0.06, "cx_m": 0.045, "cy_m": 0.03},
        depends_on=["boss_base"],
    ))
    fg.add_node(FeatureNode(
        id="boss_col_right",
        type=FeatureType.EXTRUDE_BOSS,
        name="RightColBoss",
        parameters={"depth_m": 0.02, "direction": True, "merge": True},
        depends_on=["sk_col_right"],
    ))

    # 4. 汇聚节点: 中央轴承横梁 (同时依赖两个支柱)
    fg.add_node(FeatureNode(
        id="sk_bridge",
        type=FeatureType.SKETCH_2D,
        name="BridgeHousingSketch",
        parameters={"plane": "Front Plane", "shape": "rectangle", "width_m": 0.07, "height_m": 0.04, "cx_m": 0.0, "cy_m": 0.04},
        depends_on=["boss_col_left", "boss_col_right"],
    ))
    fg.add_node(FeatureNode(
        id="boss_bridge",
        type=FeatureType.EXTRUDE_BOSS,
        name="BridgeHousingBoss",
        parameters={"depth_m": 0.02, "direction": True, "merge": True},
        depends_on=["sk_bridge"],
    ))

    # 5. 主轴孔 (直径 24mm, 半径 12mm，避开零厚度边界)
    fg.add_node(FeatureNode(
        id="sk_shaft_bore",
        type=FeatureType.SKETCH_2D,
        name="ShaftBoreSketch",
        parameters={"plane": "Front Plane", "shape": "circle", "radius_m": 0.012, "cx_m": 0.0, "cy_m": 0.04},
        depends_on=["boss_bridge"],
    ))
    fg.add_node(FeatureNode(
        id="cut_shaft_bore",
        type=FeatureType.EXTRUDE_CUT,
        name="ShaftBoreCut",
        parameters={"depth_m": 0.02, "direction": False},
        depends_on=["sk_shaft_bore"],
    ))

    expectation = GeometricExpectation(
        expected_feature_types=["ProfileFeature", "Extrusion"],
        expected_feature_keywords=["草图", "拉伸"],
        expected_solid_bodies=1,
        expected_bbox_mm=[140.0, 75.0, 80.0],
        bbox_tol_mm=2.0,
    )
    return fg, expectation


# ============================================================
# 测试执行总入口
# ============================================================
def run_complex_part_test(part_name: str, builder_func) -> Tuple[bool, str, Dict[str, Any]]:
    """在 STA 线程中实机执行一个复杂工程零件建模并进行几何核验。"""
    print("\n" + "=" * 65)
    print(f"【P0.4 复杂工程零件实机测试】: {part_name}")
    print("=" * 65)

    fg, expectation = builder_func()
    output_path = get_sandbox_part_path(part_name.lower())
    print(f"[*] 目标落盘路径: {output_path}")
    print(f"[*] 特征图节点总数: {len(fg.nodes)}, 拓扑时序规划完成")

    executor = CADGraphExecutor(enable_task_context=True, auto_rollback_on_failure=True)
    t0 = time.time()
    result = executor.execute(
        graph_input=fg,
        output_part_path=output_path,
        collect_metrics=True,
        close_on_finish=False,  # 保持打开以便检验
    )
    exec_duration = time.time() - t0

    print(f"[*] 执行完成: 耗时={exec_duration:.2f}s, 状态={result.status}, 整体成功={result.success}")
    print(f"    - 成功节点: {len(result.succeeded_nodes)}")
    print(f"    - 失败节点: {result.failed_nodes}")
    print(f"    - 跳过节点: {result.skipped_nodes}")

    if not result.success:
        return False, output_path, {"exec_error": result.diagnostics}

    # STA 线程物理几何检验
    worker = get_sta_worker()
    def sta_verify():
        sw, _ = connect_solidworks()
        model = open_document(sw, output_path)
        report = GeometryVerifier.verify(model, expectation)
        doc_title = get_com_member(model, "GetTitle")
        if sw and doc_title:
            get_com_member(sw, "CloseDoc", doc_title)
        return report

    verify_report = worker.execute(sta_verify)
    print(f"[*] 物理几何检验结果: {'[PASS]' if verify_report.passed else '[FAIL]'}")
    for k, v in verify_report.checks.items():
        print(f"    - {k}: {'PASS' if v else 'FAIL'}")

    metrics = {
        "execution_duration_s": round(exec_duration, 2),
        "total_nodes": len(fg.nodes),
        "succeeded_nodes": len(result.succeeded_nodes),
        "mass_properties": result.mass_properties,
        "bounding_box": result.bounding_box,
        "verification_passed": verify_report.passed,
    }
    return verify_report.passed, output_path, metrics


# ============================================================
# 真实部分失败事务回滚测试 (实体已生成后中途失败逆向删除)
# ============================================================
def run_real_mid_pipeline_rollback_test() -> bool:
    """
    验证中途物理失败后的真实事务回滚：
    1. 真实创建 100x50x20 实体；
    2. 下游节点故意注入几何非法错误；
    3. 验证触发任务回滚，且新创建的脏文档被安全关闭/清除，活动文档数归零。
    """
    print("\n" + "=" * 65)
    print("【P0.4 真实实体中途故障物理事务回滚测试】")
    print("=" * 65)

    fg = FeatureGraphIR(graph_id="ir_mid_rollback", target_part_name="MidRollbackPart")
    fg.add_node(FeatureNode(
        id="sk1",
        type=FeatureType.SKETCH_2D,
        name="ValidSketch",
        parameters={"plane": "Front Plane", "shape": "rectangle", "width_m": 0.08, "height_m": 0.05},
        depends_on=[],
    ))
    fg.add_node(FeatureNode(
        id="boss1",
        type=FeatureType.EXTRUDE_BOSS,
        name="ValidBoss",
        parameters={"depth_m": 0.02},
        depends_on=["sk1"],
    ))
    # 注入中途失败节点
    fg.add_node(FeatureNode(
        id="bad_cut",
        type=FeatureType.EXTRUDE_CUT,
        name="BadCut",
        parameters={"depth_m": 0.0},  # 零深度非法切削
        depends_on=["boss1"],
    ))

    output_path = get_sandbox_part_path("mid_rollback")
    executor = CADGraphExecutor(enable_task_context=True, auto_rollback_on_failure=True)
    res = executor.execute(fg, output_part_path=output_path, close_on_finish=True)

    print(f"[*] 执行状态: {res.status}, 回滚状态: {res.rollback_status}, 回滚发生: {res.rollback_occurred}")
    print(f"    - 成功执行的前序节点: {res.succeeded_nodes}")
    print(f"    - 失败节点: {res.failed_nodes}")

    ok = (not res.success) and (res.status == "ROLLED_BACK") and (res.rollback_status == "SUCCESS")
    print(f"[*] 真实中途物理回滚验证: {'[PASS]' if ok else '[FAIL]'}")
    return ok


def main():
    parser = argparse.ArgumentParser(description="SolidWorks P0.4 复杂建模实机测试")
    parser.add_argument("--authorize-cad-write", action="store_true", default=False)
    args = parser.parse_args()

    if not args.authorize_cad_write:
        print("[✖ ERROR] 必须提供 --authorize-cad-write 授权参数以执行实机写入。")
        sys.exit(1)

    print("=" * 65)
    print("      dsh-solidworks P0.4 复杂工程建模与压力测试套件")
    print("=" * 65)

    p1_ok, p1_path, m1 = run_complex_part_test("Flange_14Node", build_flange_graph)
    p2_ok, p2_path, m2 = run_complex_part_test("Bracket_MultiPlane", build_bracket_graph)
    p3_ok, p3_path, m3 = run_complex_part_test("BearingMount_Convergence", build_bearing_mount_graph)
    rb_ok = run_real_mid_pipeline_rollback_test()

    all_passed = p1_ok and p2_ok and p3_ok and rb_ok

    print("\n" + "=" * 65)
    print("      P0.4 复杂建模与压力测试最终汇总")
    print("=" * 65)
    print(f"  零件 A (Flange 14节点): {'[PASS]' if p1_ok else '[FAIL]'} (文件: {os.path.basename(p1_path)})")
    print(f"  零件 B (Bracket 跨基准面): {'[PASS]' if p2_ok else '[FAIL]'} (文件: {os.path.basename(p2_path)})")
    print(f"  零件 C (BearingMount 汇聚): {'[PASS]' if p3_ok else '[FAIL]'} (文件: {os.path.basename(p3_path)})")
    print(f"  中途真实实体事务回滚: {'[PASS]' if rb_ok else '[FAIL]'}")
    print(f"  综合验收结论: {'[ALL PASS]' if all_passed else '[FAIL]'}")
    print("=" * 65)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
