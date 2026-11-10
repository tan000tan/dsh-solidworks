# -*- coding: utf-8 -*-
"""
tests/real_cad/real_cad_graph_test.py
SolidWorks 真实环境特征图参数化建模验收测试程序。

包含两大核心建模验收测试：
1. 测试一：最小特征图 (Sketch2D -> BossExtrude)
2. 测试二：多节点特征图 (Sketch2D -> BossExtrude -> CutExtrude)

双模式设计：
- PRECHECK 模式（只读）：检查特征图 IR 结构、拓扑依赖合法性与几何预期参数，不产生真实写入；
- EXECUTE 模式（实机）：必须显式附带 --authorize-cad-write 授权，严格在沙箱目录执行独立零件建模。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path

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
from geometry_verifier import GeometryVerifier, GeometricExpectation, VerificationReport


def get_sandbox_part_path(prefix: str) -> str:
    """生成带毫秒级唯一时间戳的沙箱零件落盘物理路径。"""
    sandbox_dir = REAL_CAD_DIR / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{prefix}_{timestamp}.SLDPRT"
    return str(sandbox_dir / filename)


# ============================================================
# 测试一：最小特征图 (Sketch2D -> BossExtrude)
# ============================================================
def build_minimal_graph() -> Tuple[FeatureGraphIR, GeometricExpectation]:
    """
    构造最小几何特征图：
    - 前视基准面 100mm x 50mm 中心矩形草图
    - 单向拉伸 20mm 凸台
    """
    fg = FeatureGraphIR(graph_id="ir_minimal_plate", target_part_name="MinimalPlate")
    fg.add_node(FeatureNode(
        id="node_sk_base",
        type=FeatureType.SKETCH_2D,
        name="BaseSketch",
        parameters={
            "plane": "Front Plane",
            "shape": "rectangle",
            "width_m": 0.1,    # 100 mm
            "height_m": 0.05,  # 50 mm
            "cx_m": 0.0,
            "cy_m": 0.0,
        },
        depends_on=[],
    ))
    fg.add_node(FeatureNode(
        id="node_boss_base",
        type=FeatureType.EXTRUDE_BOSS,
        name="Boss-Extrude1",
        parameters={
            "depth_m": 0.02,   # 20 mm
            "direction": True,
            "merge": True,
        },
        depends_on=["node_sk_base"],
    ))

    # 预期物理属性计算
    # 体积 = 0.1 * 0.05 * 0.02 = 1.0e-4 m^3 = 100,000 mm^3
    # 表面积 = 2 * (0.1*0.05 + 0.1*0.02 + 0.05*0.02) = 2 * (0.005 + 0.002 + 0.001) = 0.016 m^2 = 16,000 mm^2
    expectation = GeometricExpectation(
        expected_feature_types=["ProfileFeature", "Extrusion"],
        expected_feature_keywords=["草图", "拉伸"],
        expected_solid_bodies=1,
        expected_bbox_mm=[100.0, 50.0, 20.0],
        bbox_tol_mm=0.5,
        expected_volume_mm3=100000.0,
        volume_rel_tol=0.02,
        expected_surface_area_mm2=16000.0,
        surface_area_rel_tol=0.02,
    )
    return fg, expectation


# ============================================================
# 测试二：多节点特征图 (Sketch2D -> BossExtrude -> CutExtrude)
# ============================================================
def build_multi_node_graph() -> Tuple[FeatureGraphIR, GeometricExpectation]:
    """
    构造多节点特征图：
    - 基础草图：100mm x 50mm 中心矩形
    - 凸台拉伸：20mm 深度
    - 贯通切除草图：直径 20mm (半径 10mm) 中心圆孔
    - 拉伸切除：贯穿深度 20mm
    """
    fg = FeatureGraphIR(graph_id="ir_perforated_plate", target_part_name="PerforatedPlate")
    fg.add_node(FeatureNode(
        id="node_sk_base",
        type=FeatureType.SKETCH_2D,
        name="BaseSketch",
        parameters={
            "plane": "Front Plane",
            "shape": "rectangle",
            "width_m": 0.1,    # 100 mm
            "height_m": 0.05,  # 50 mm
            "cx_m": 0.0,
            "cy_m": 0.0,
        },
        depends_on=[],
    ))
    fg.add_node(FeatureNode(
        id="node_boss_base",
        type=FeatureType.EXTRUDE_BOSS,
        name="Boss-Extrude1",
        parameters={
            "depth_m": 0.02,   # 20 mm
            "direction": True,
            "merge": True,
        },
        depends_on=["node_sk_base"],
    ))
    fg.add_node(FeatureNode(
        id="node_sk_hole",
        type=FeatureType.SKETCH_2D,
        name="HoleSketch",
        parameters={
            "plane": "Front Plane",
            "shape": "circle",
            "radius_m": 0.01,  # 直径 20 mm
            "cx_m": 0.0,
            "cy_m": 0.0,
        },
        depends_on=["node_boss_base"],
    ))
    fg.add_node(FeatureNode(
        id="node_cut_hole",
        type=FeatureType.EXTRUDE_CUT,
        name="Cut-Extrude1",
        parameters={
            "depth_m": 0.02,   # 贯通切除 20 mm
            "direction": False, # 切除朝向实体内部
            "flip": False,
        },
        depends_on=["node_sk_hole"],
    ))

    # 体积 = (0.1 * 0.05 - pi * 0.01^2) * 0.02 ≈ (0.005 - 0.000314159) * 0.02 = 9.37168e-5 m^3
    # 表面积 = 0.016 - 2 * (pi * 0.01^2) + (2 * pi * 0.01 * 0.02) ≈ 0.016 - 0.0006283 + 0.0012566 = 0.016628 m^2
    hole_area = math.pi * (0.01 ** 2)
    vol = (0.1 * 0.05 - hole_area) * 0.02
    surface_area = 0.016 - 2 * hole_area + (2 * math.pi * 0.01 * 0.02)

    vol_mm3 = (100.0 * 50.0 - math.pi * 100.0) * 20.0
    surf_mm2 = 16000.0 - 2.0 * math.pi * 100.0 + 2.0 * math.pi * 10.0 * 20.0
    expectation = GeometricExpectation(
        expected_feature_types=["ProfileFeature", "Extrusion"],
        expected_feature_keywords=["草图", "拉伸"],
        expected_solid_bodies=1,
        expected_bbox_mm=[100.0, 50.0, 20.0],
        bbox_tol_mm=0.5,
        expected_volume_mm3=vol_mm3,
        volume_rel_tol=0.02,
        expected_surface_area_mm2=surf_mm2,
        surface_area_rel_tol=0.02,
    )
    return fg, expectation


# ============================================================
# 运行器
# ============================================================
def run_test(
    name: str,
    graph_builder,
    mode: str,
    authorized: bool,
    retain_model_on_finish: bool = False,
) -> bool:
    print("\n" + "-" * 60)
    print(f"【实机特征图测试】: {name} (模式: {mode.upper()})")
    print("-" * 60)

    fg, expectation = graph_builder()

    # 1. PRECHECK 模式：静态拓扑依赖与预期检查
    if mode.lower() == "precheck":
        print(f"[*] 静态编译校验图 ID: {fg.graph_id}, 包含节点数: {len(fg.nodes)}")
        fg.validate_dag()
        ordered = fg.topological_sort()
        print(f"[✔ PASS] Kahn 拓扑排序计划正常: {[n.id + ' (' + n.type.value + ')' for n in ordered]}")
        print(f"[✔ PASS] 预期几何规范配置合规:")
        print(f"    - 预期特征: {expectation.expected_features}")
        print(f"    - 预期实体数: {expectation.expected_solid_bodies}")
        print(f"    - 预期包围盒: {expectation.expected_bbox}")
        if expectation.expected_volume_m3:
            print(f"    - 预期体积: {expectation.expected_volume_m3:.6e} m^3")
        if expectation.expected_surface_area_m2:
            print(f"    - 预期表面积: {expectation.expected_surface_area_m2:.6e} m^2")
        print(f"[INFO] PRECHECK 模式已安全完成，未触发实机 CAD 写入。")
        return True

    # 2. EXECUTE 模式：真实 SolidWorks 环境受控建模
    if not authorized:
        print("[✖ ERROR] 拒绝执行真实 CAD 写入！必须在命令行显式提供 '--authorize-cad-write' 授权参数。")
        return False

    output_path = get_sandbox_part_path(name.lower())
    print(f"[*] 安全沙箱目标零件路径: {output_path}")

    executor = CADGraphExecutor(
        enable_task_context=True,
        auto_rollback_on_failure=True,
    )

    print("[*] 正在通过 STA Worker 派发执行特征图建模...")
    t0 = time.time()
    result = executor.execute(
        graph_input=fg,
        output_part_path=output_path,
        collect_metrics=True,
        close_on_finish=False,  # 先保持打开，以便进行深度几何物理验证
    )
    elapsed = time.time() - t0
    print(f"[*] 引擎执行完毕，耗时: {elapsed:.2f}s, 执行状态: {result.status}, 整体成功: {result.success}")

    if not result.success:
        print(f"[✖ FAIL] 特征图执行失败！")
        print(f"    - 失败节点: {result.failed_nodes}")
        print(f"    - 跳过节点: {result.skipped_nodes}")
        print(f"    - 回滚状态: {result.rollback_status}, 回滚错误: {result.rollback_errors}")
        print(f"    - 诊断详情: {result.diagnostics}")
        print(f"    【现场保护】：沙箱文件保留供排查: {output_path}")
        return False

    # 3. 几何物理断言校验 (必须在 STA Worker 线程内执行以保证 COM 合规)
    print("[*] 正在通过 STA Worker 调用 GeometryVerifier 对模型进行物理验证...")
    from sw_connect import get_sta_worker, connect_solidworks, get_com_member, open_document

    worker = get_sta_worker()

    def sta_verify_and_cleanup():
        sw_app, _ = connect_solidworks(wait_seconds=5, visible=None)
        # 直接使用落盘路径安全定位/复用文档句柄
        doc = open_document(sw_app, output_path)
        v_rep = GeometryVerifier.verify(doc, expectation)

        if not retain_model_on_finish:
            try:
                d_title = get_com_member(doc, "GetTitle")
                if d_title:
                    get_com_member(sw_app, "CloseDoc", d_title)
            except Exception:
                pass
        return v_rep

    v_report = worker.execute(sta_verify_and_cleanup)
    print(v_report.summary())

    if not retain_model_on_finish:
        print(f"[✔ PASS] 测试独立零件已在 STA 线程中按计划安全关闭。")
    else:
        print(f"[INFO] 根据配置保留测试零件处于打开状态以供人工视觉检查。")

    return v_report.passed


def main():
    parser = argparse.ArgumentParser(description="SolidWorks 真实环境端到端验证程序")
    parser.add_argument(
        "--mode",
        choices=["precheck", "execute"],
        default="precheck",
        help="运行模式: precheck (只读无写入) 或 execute (真实几何测试)",
    )
    parser.add_argument(
        "--authorize-cad-write",
        action="store_true",
        default=False,
        help="用户显式授权 CAD 写入参数。在 execute 模式下必选，否则拒绝执行。",
    )
    parser.add_argument(
        "--test",
        choices=["all", "minimal", "multi_node"],
        default="all",
        help="选择测试用例",
    )
    parser.add_argument(
        "--retain",
        action="store_true",
        default=False,
        help="测试完成后保留 SolidWorks 窗口中的模型不关闭",
    )
    args = parser.parse_args()

    print("=" * 65)
    print("      dsh-solidworks 真实环境特征图参数化建模验证套件")
    print("=" * 65)
    print(f"模式: {args.mode.upper()}")
    print(f"授权状态: {'[AUTHORIZED]' if args.authorize_cad_write else '[READ-ONLY PROTECTED]'}")

    success = True
    if args.test in ("all", "minimal"):
        ok = run_test("MinimalGraph", build_minimal_graph, args.mode, args.authorize_cad_write, args.retain)
        success = success and ok

    if args.test in ("all", "multi_node"):
        ok = run_test("MultiNodeGraph", build_multi_node_graph, args.mode, args.authorize_cad_write, args.retain)
        success = success and ok

    print("\n" + "=" * 65)
    print(f"  最终验收结果: {'[ALL PASS]' if success else '[FAIL]'}")
    print("=" * 65)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
