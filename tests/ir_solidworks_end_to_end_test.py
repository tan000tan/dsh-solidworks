# -*- coding: utf-8 -*-
"""
tests/ir_solidworks_end_to_end_test.py
Feature Graph IR 驱动真实 SolidWorks 2026 的端到端建模验证。
"""

import json
import math
import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"
for p in (str(SCRIPTS_DIR), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

SANDBOX_DIR = REPO_ROOT / "测试代码" / "sandbox_benchmark"
SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
os.environ["DSH_ALLOWED_ROOTS"] = json.dumps([str(SANDBOX_DIR)])

from feature_graph_ir import (
    FeatureGraphIR,
    FeatureNode,
    FeatureType,
    CyclicDependencyError,
)
from sw_connect import (
    connect_solidworks,
    get_com_member,
    new_document,
    save_document,
    open_document,
    get_sta_worker,
)
from sw_part import (
    start_sketch,
    sketch_rectangle,
    sketch_circle,
    extrude_boss,
    extrude_cut,
)
from sw_measure import (
    collect_mass_properties,
    collect_bounding_box,
)


def execute_ir_plan_on_live_solidworks(ir_graph: FeatureGraphIR, output_part_path: str):
    """
    通过 STA Worker 将 FeatureGraphIR 编译出的执行计划投递到 SolidWorks 物理引擎中执行。
    """
    plan = ir_graph.compile_execution_plan()
    sw, active_doc = connect_solidworks(wait_seconds=15, visible=False)
    if sw is None:
        raise RuntimeError("无法连接到本地 SolidWorks COM 实例")

    # 创建新文档
    model = new_document(sw, "part")
    if model is None:
        raise RuntimeError("无法创建零件文档")

    execution_log = []

    try:
        for step in plan:
            ftype = step["feature_type"]
            args = step["arguments"]
            node_id = step["node_id"]

            if ftype == FeatureType.SKETCH_2D.value:
                plane = args.get("plane", "Front Plane")
                start_sketch(model, plane_name=plane)
                shape = args.get("shape", "rectangle")
                if shape == "rectangle":
                    w = args["width_m"]
                    h = args["height_m"]
                    sketch_rectangle(model, 0.0, 0.0, w, h)
                elif shape == "circle":
                    r = args["radius_m"]
                    cx = args.get("cx_m", 0.0)
                    cy = args.get("cy_m", 0.0)
                    sketch_circle(model, cx, cy, r)
                execution_log.append({"step": step["step_index"], "node_id": node_id, "status": "SKETCH_OK"})

            elif ftype == FeatureType.EXTRUDE_BOSS.value:
                depth_m = args["depth_m"]
                extrude_boss(model, None, depth_m)
                execution_log.append({"step": step["step_index"], "node_id": node_id, "status": "EXTRUDE_OK"})

            elif ftype == FeatureType.EXTRUDE_CUT.value:
                depth_m = args.get("depth_m", 0.05)
                direction = args.get("direction", False)
                extrude_cut(model, None, depth_m, direction=direction)
                execution_log.append({"step": step["step_index"], "node_id": node_id, "status": "CUT_OK"})

        # 执行整体重构与保存
        get_com_member(model, "EditRebuild3")
        save_document(model, output_part_path)

        # 测量几何质量属性
        mass = collect_mass_properties(model)
        box = collect_bounding_box(model)

        return {
            "success": True,
            "steps_executed": len(execution_log),
            "log": execution_log,
            "mass_properties": mass,
            "bounding_box": box,
        }
    finally:
        if sw and model:
            try:
                title = get_com_member(model, "GetTitle")
                if title:
                    get_com_member(sw, "CloseDoc", title)
            except Exception:
                pass


class FeatureGraphLiveSolidWorksTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from sw_connect import solidworks_processes
        if not solidworks_processes():
            raise unittest.SkipTest("未检测到运行中的 SolidWorks 进程，跳过实机物理测试以保护待机基线")

    def setUp(self):
        self.part_path = str(SANDBOX_DIR / "ir_e2e_test_part.SLDPRT")
        if os.path.exists(self.part_path):
            try:
                os.remove(self.part_path)
            except Exception:
                pass

    def test_ir_dag_topological_and_live_execution(self):
        # 1. 构建 Feature Graph DAG:
        # node_base_sk -> node_extrude_base -> node_cut_sk -> node_cut_feature
        # 故意打乱顺序存入字典，验证 Kahn 拓扑排序能否恢复确定性因果时序
        fg = FeatureGraphIR(graph_id="ir_e2e_bracket", target_part_name="bracket")

        # 节点 4: 切除特征 (依赖 切除草图 和 基础凸台)
        fg.add_node(FeatureNode(
            id="node_cut_feature",
            type=FeatureType.EXTRUDE_CUT,
            name="Cut-Extrude1",
            parameters={"depth_m": 0.05, "direction": False},
            depends_on=["node_cut_sk", "node_extrude_base"],
        ))

        # 节点 1: 基础草图 (无依赖，作为基石)
        fg.add_node(FeatureNode(
            id="node_base_sk",
            type=FeatureType.SKETCH_2D,
            name="Sketch1",
            parameters={"plane": "Front Plane", "shape": "rectangle", "width_m": 0.10, "height_m": 0.06},
            depends_on=[],
        ))

        # 节点 3: 切除草图 (依赖 基础凸台，以原点中心开孔)
        fg.add_node(FeatureNode(
            id="node_cut_sk",
            type=FeatureType.SKETCH_2D,
            name="Sketch2",
            parameters={"plane": "Front Plane", "shape": "circle", "radius_m": 0.01, "cx_m": 0.0, "cy_m": 0.0},
            depends_on=["node_extrude_base"],
        ))

        # 节点 2: 基础拉伸 (依赖 基础草图)
        fg.add_node(FeatureNode(
            id="node_extrude_base",
            type=FeatureType.EXTRUDE_BOSS,
            name="Boss-Extrude1",
            parameters={"depth_m": 0.02},
            depends_on=["node_base_sk"],
        ))

        # 验证拓扑排序生成的计划
        ordered_plan = fg.compile_execution_plan()
        ordered_ids = [step["node_id"] for step in ordered_plan]
        self.assertEqual(
            ordered_ids,
            ["node_base_sk", "node_extrude_base", "node_cut_sk", "node_cut_feature"],
            "Kahn 拓扑排序必须严格恢复特征树因果构建时序！"
        )

        # 2. 将编译好的计划在真实的 SolidWorks 中执行
        worker = get_sta_worker()
        result = worker.execute(lambda: execute_ir_plan_on_live_solidworks(fg, self.part_path))

        self.assertTrue(result["success"])
        self.assertEqual(result["steps_executed"], 4)

        # 3. 双精度质量属性断言：100x60x20mm 带 d20mm 孔的体积必须精准吻合 113716.815 mm³
        actual_vol = result["mass_properties"].get("volume_mm3")
        self.assertIsNotNone(actual_vol)
        THEO_VOL = 113716.815
        self.assertAlmostEqual(actual_vol, THEO_VOL, delta=5.0)

        # 清理沙箱测试文件
        if os.path.exists(self.part_path):
            try:
                os.remove(self.part_path)
            except Exception:
                pass


if __name__ == "__main__":
    unittest.main()
