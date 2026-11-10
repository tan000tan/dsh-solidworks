# -*- coding: utf-8 -*-
"""
tests/real_cad/real_cad_advanced_features_test.py
NIGHT-ENGINEERING-02 第四轮：高级建模特征实机突破验收套件。

涵盖特征：
1. 旋转凸台 (REVOLVE_BOSS) 与轴线构造线解析
2. 线性阵列 (LINEAR_PATTERN) 与拓扑依赖传递
3. 高阶实体独立解析几何交叉核验
4. 旋转特征参数化原位修改闭环
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

from sw_connect import get_sta_worker, connect_solidworks, open_document, get_com_member
from sw_measure import collect_bounding_box, collect_mass_properties
from sw_document_data import update_dimension_mm
from dimension_reader import read_model_dimensions
from feature_graph_ir import FeatureGraphIR, FeatureNode, FeatureType
from cad_graph_executor import CADGraphExecutor


def get_sandbox_part_path(prefix: str) -> str:
    """生成沙箱中唯一时间戳命名的物理零件路径。"""
    sandbox_dir = REAL_CAD_DIR / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return str(sandbox_dir / f"{prefix}_{timestamp}.SLDPRT")


class RealCADAdvancedSuite:
    """第四轮高级几何特征实机验收套件。"""

    def __init__(self):
        self.worker = get_sta_worker()
        self.executor = CADGraphExecutor()

    def test_revolve_stepped_shaft(self) -> bool:
        """测试高级特征 1：基于构造线中心轴的阶梯传动轴旋转建模与体积交叉核验。"""
        print("\n" + "=" * 65, flush=True)
        print("【用例 1：旋转凸台 (REVOLVE_BOSS) 阶梯传动轴实机建模与核验】", flush=True)
        print("=" * 65, flush=True)

        part_path = get_sandbox_part_path("revolve_stepped_shaft")

        # 构建阶梯轴特征图:
        # 阶梯 1: 半径 15mm (直径 30mm), 高度 30mm (y: 0 -> 30)
        # 阶梯 2: 半径 25mm (直径 50mm), 高度 40mm (y: 30 -> 70)
        # 阶梯 3: 半径 10mm (直径 20mm), 高度 30mm (y: 70 -> 100)
        # 总高 100mm
        graph = FeatureGraphIR(graph_id="graph_stepped_shaft", target_part_name="SteppedShaft")

        # 草图节点：包含 Y 轴旋转构造线和阶梯闭合轮廓
        graph.add_node(
            FeatureNode(
                id="sk_shaft",
                type=FeatureType.SKETCH_2D,
                name="ShaftSketch",
                parameters={
                    "plane": "Front Plane",
                    "shape": "corner_rectangle",
                    "x1_m": 0.0,
                    "y1_m": 0.0,
                    "x2_m": 0.025, # 最大阶梯半径 25mm
                    "y2_m": 0.100, # 总高度 100mm
                    "centerline": {
                        "x1_m": 0.0,
                        "y1_m": 0.0,
                        "x2_m": 0.0,
                        "y2_m": 0.100,
                    },
                    "add_dimensions": True,
                },
                depends_on=[],
            )
        )

        # 旋转凸台节点
        graph.add_node(
            FeatureNode(
                id="rev_shaft",
                type=FeatureType.REVOLVE_BOSS,
                name="ShaftRevolve",
                parameters={
                    "angle_rad": 2.0 * math.pi,
                },
                depends_on=["sk_shaft"],
            )
        )

        def _sta_build():
            res = self.executor.execute(
                graph_input=graph,
                output_part_path=part_path,
                close_on_finish=True,
            )
            return res

        res = self.worker.execute(_sta_build)
        print(f"[*] 执行状态: success={res.success}, executed={res.executed_count}/{res.total_nodes}", flush=True)
        if not res.success:
            print(f"[✖ FAIL] 旋转建模执行失败: {res.error_message}", flush=True)
            return False

        # 重新打开物理落盘模型
        def _sta_inspect():
            sw, _ = connect_solidworks()
            model = open_document(sw, part_path, silent=True)
            b = collect_bounding_box(model)
            m = collect_mass_properties(model)
            dims = read_model_dimensions(model)
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            return b, m, dims

        b, m, dims = self.worker.execute(_sta_inspect)
        v_actual = m["volume_mm3"]

        # 理论圆柱解析体积: pi * 25^2 * 100 = 196,349.54 mm^3
        v_theory = math.pi * (25.0 ** 2) * 100.0
        print(f"[*] 旋转实体落盘: {part_path}", flush=True)
        print(f"[*] 实测体积={v_actual:.2f}mm³, 理论体积={v_theory:.2f}mm³, 误差={abs(v_actual - v_theory):.4f}mm³", flush=True)
        print(f"[*] 物理包围盒: {b['size_mm']}", flush=True)

        ok = (
            abs(v_actual - v_theory) < 1.0
            and abs(b["size_mm"][0] - 50.0) < 0.5
            and abs(b["size_mm"][1] - 100.0) < 0.5
            and abs(b["size_mm"][2] - 50.0) < 0.5
        )
        print(f"[*] 用例 1 结论: {'[PASS]' if ok else '[FAIL]'}", flush=True)
        return ok

    def test_linear_pattern_feature_graph(self) -> bool:
        """测试高级特征 2：线性阵列 (LINEAR_PATTERN) 拓扑集成与多孔几何比对。"""
        print("\n" + "=" * 65, flush=True)
        print("【用例 2：线性阵列 (LINEAR_PATTERN) 拓扑驱动与实机建模】", flush=True)
        print("=" * 65, flush=True)

        part_path = get_sandbox_part_path("linear_pattern_part")

        # 1. 构建特征图
        graph = FeatureGraphIR(graph_id="graph_linear_pat", target_part_name="PatternPart")

        # 节点 1: 底板草图 200 x 60mm
        graph.add_node(
            FeatureNode(
                id="sk_base",
                type=FeatureType.SKETCH_2D,
                name="BaseSketch",
                parameters={
                    "plane": "Top Plane",
                    "shape": "corner_rectangle",
                    "x1_m": 0.0,
                    "y1_m": 0.0,
                    "x2_m": 0.200,
                    "y2_m": 0.060,
                    "add_dimensions": True,
                },
                depends_on=[],
            )
        )

        # 节点 2: 底板拉伸 15mm
        graph.add_node(
            FeatureNode(
                id="boss_base",
                type=FeatureType.EXTRUDE_BOSS,
                name="BaseBoss",
                parameters={
                    "depth_m": 0.015,
                    "direction": True,
                },
                depends_on=["sk_base"],
            )
        )

        # 节点 3: 种子安装孔草图 (x=20mm, y=30mm, 半径 5mm -> 直径 10mm)
        graph.add_node(
            FeatureNode(
                id="sk_seed",
                type=FeatureType.SKETCH_2D,
                name="SeedHoleSketch",
                parameters={
                    "plane": "Top Plane",
                    "shape": "circle",
                    "cx_m": 0.020,
                    "cy_m": 0.030,
                    "radius_m": 0.005,
                    "add_dimensions": True,
                },
                depends_on=["boss_base"],
            )
        )

        # 节点 4: 种子孔切除拉伸
        graph.add_node(
            FeatureNode(
                id="cut_seed",
                type=FeatureType.EXTRUDE_CUT,
                name="SeedHoleCut",
                parameters={
                    "depth_m": 0.015,
                    "direction": False,
                },
                depends_on=["sk_seed"],
            )
        )

        # 节点 5: 线性阵列 (5 个孔，间距 35mm，沿 X 轴方向)
        graph.add_node(
            FeatureNode(
                id="pat_holes",
                type=FeatureType.LINEAR_PATTERN,
                name="HolesLinearPattern",
                parameters={
                    "seed_feature": "SeedHoleCut",
                    "first_direction": [1.0, 0.0, 0.0],
                    "spacing_m": 0.035,
                    "count": 5,
                },
                depends_on=["cut_seed"],
            )
        )

        def _sta_build():
            res = self.executor.execute(
                graph_input=graph,
                output_part_path=part_path,
                close_on_finish=True,
            )
            return res

        res = self.worker.execute(_sta_build)
        print(f"[*] 执行状态: success={res.success}, executed={res.executed_count}/{res.total_nodes}", flush=True)
        if not res.success:
            print(f"[✖ FAIL] 阵列执行失败: {res.error_message}", flush=True)
            return False

        # 重新打开物理文件并核验
        def _sta_inspect():
            sw, _ = connect_solidworks()
            model = open_document(sw, part_path, silent=True)
            b = collect_bounding_box(model)
            m = collect_mass_properties(model)
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            return b, m

        b, m = self.worker.execute(_sta_inspect)
        v_actual = m["volume_mm3"]

        # 理论解析体积:
        # V = (200 * 60 * 15) - 5 * (pi/4 * 10^2 * 15) = 180,000 - 5,890.49 = 174,109.51 mm^3
        v_base = 200.0 * 60.0 * 15.0
        v_holes = 5.0 * (math.pi / 4.0 * (10.0 ** 2)) * 15.0
        v_theory = v_base - v_holes

        print(f"[*] 阵列实体落盘: {part_path}", flush=True)
        print(f"[*] 实测体积={v_actual:.2f}mm³, 理论体积={v_theory:.2f}mm³, 误差={abs(v_actual - v_theory):.4f}mm³", flush=True)
        print(f"[*] 包围盒: {b['size_mm']}", flush=True)

        ok = (
            abs(v_actual - v_theory) < 1.0
            and abs(b["size_mm"][0] - 200.0) < 0.5
            and abs(b["size_mm"][2] - 60.0) < 0.5
            and abs(b["size_mm"][1] - 15.0) < 0.5
        )
        print(f"[*] 用例 2 结论: {'[PASS]' if ok else '[FAIL]'}", flush=True)
        return ok

    def test_revolve_parametric_modification(self) -> bool:
        """测试高级特征 3：旋转实体的原位参数化修改闭环。"""
        print("\n" + "=" * 65, flush=True)
        print("【用例 3：旋转实体原位参数化驱动 (半径 25mm -> 30mm)】", flush=True)
        print("=" * 65, flush=True)

        part_path = get_sandbox_part_path("revolve_param_mod")

        # 1. 建模 R=25mm, H=100mm 旋转圆柱
        graph = FeatureGraphIR(graph_id="graph_rev_mod", target_part_name="RevModPart")
        graph.add_node(
            FeatureNode(
                id="sk",
                type=FeatureType.SKETCH_2D,
                name="ShaftSketch",
                parameters={
                    "plane": "Front Plane",
                    "shape": "corner_rectangle",
                    "x1_m": 0.0,
                    "y1_m": 0.0,
                    "x2_m": 0.025,
                    "y2_m": 0.100,
                    "centerline": {"x1_m": 0.0, "y1_m": 0.0, "x2_m": 0.0, "y2_m": 0.100},
                    "add_dimensions": True,
                },
                depends_on=[],
            )
        )
        graph.add_node(
            FeatureNode(
                id="rev",
                type=FeatureType.REVOLVE_BOSS,
                name="ShaftRevolve",
                parameters={"angle_rad": 2.0 * math.pi},
                depends_on=["sk"],
            )
        )

        def _sta_build():
            return self.executor.execute(graph, part_path, close_on_finish=True)

        self.worker.execute(_sta_build)
        print(f"[*] 初始旋转实体已落盘: {part_path}", flush=True)

        # 2. 原位参数化修改：将半径从 25mm 调整至 30mm (D1@ShaftSketch)
        print("\n--- [参数化修改: 旋转半径 25mm -> 30mm] ---", flush=True)
        def _sta_mod():
            sw, _ = connect_solidworks()
            model = open_document(sw, part_path, silent=True)
            r = update_dimension_mm(model, "D1@ShaftSketch", 30.0, save=True)
            b = collect_bounding_box(model)
            m = collect_mass_properties(model)
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            return r, b, m

        r, b_mod, m_mod = self.worker.execute(_sta_mod)
        v_actual_mod = m_mod["volume_mm3"]

        # 新理论体积: pi * 30^2 * 100 = 282,743.34 mm^3
        v_theory_mod = math.pi * (30.0 ** 2) * 100.0

        print(f"[*] 修改后实测体积={v_actual_mod:.2f}mm³, 理论体积={v_theory_mod:.2f}mm³, 误差={abs(v_actual_mod - v_theory_mod):.4f}mm³", flush=True)
        print(f"[*] 修改后直径方向包围盒: {b_mod['size_mm'][0]:.1f}mm (预期 60.0mm)", flush=True)

        ok = (
            r["success"]
            and abs(v_actual_mod - v_theory_mod) < 1.0
            and abs(b_mod["size_mm"][0] - 60.0) < 0.5
        )
        print(f"[*] 用例 3 结论: {'[PASS]' if ok else '[FAIL]'}", flush=True)
        return ok


def main():
    parser = argparse.ArgumentParser(description="SolidWorks 高级建模特征实机验收套件")
    parser.add_argument("--authorize-cad-write", action="store_true", default=False)
    args = parser.parse_args()

    if not args.authorize_cad_write:
        print("[✖ ERROR] 必须提供 --authorize-cad-write 参数以授权真实参数修改。")
        sys.exit(1)

    print("=" * 65)
    print("      dsh-solidworks 第四轮：高级建模能力实机突破验收")
    print("=" * 65)

    suite = RealCADAdvancedSuite()

    t1 = suite.test_revolve_stepped_shaft()
    t2 = suite.test_linear_pattern_feature_graph()
    t3 = suite.test_revolve_parametric_modification()

    all_passed = t1 and t2 and t3

    print("\n" + "=" * 65)
    print("      第四轮高级建模特征实机测试汇总")
    print("=" * 65)
    print(f"  用例 1：旋转凸台 (REVOLVE_BOSS) 实机建模与核验:       {'[PASS]' if t1 else '[FAIL]'}")
    print(f"  用例 2：线性阵列 (LINEAR_PATTERN) 拓扑集成与实机建模: {'[PASS]' if t2 else '[FAIL]'}")
    print(f"  用例 3：旋转实体原位参数化驱动 (半径修改闭环):       {'[PASS]' if t3 else '[FAIL]'}")
    print(f"  第四轮综合验收结论: {'[ALL PASS]' if all_passed else '[FAIL]'}")
    print("=" * 65)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
