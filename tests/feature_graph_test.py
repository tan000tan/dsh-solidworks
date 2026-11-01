# -*- coding: utf-8 -*-
"""
tests/feature_graph_test.py

针对 TASK-04: Feature Graph IR 核心模块与拓扑编译器的完整自动化单元测试。
"""

import json
import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "vendor", "solidworks-automation-skill", "scripts")
MCP_SERVER_DIR = os.path.join(REPO_ROOT, "vendor", "solidworks-automation-skill", "mcp-server")
for p in (SCRIPTS_DIR, MCP_SERVER_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from feature_graph_ir import (
    CyclicDependencyError,
    FeatureGraphIR,
    FeatureNode,
    FeatureType,
    UndefinedDependencyError,
    compile_feature_graph_from_dict,
)
from server import FeatureGraphCompileInput, solidworks_compile_feature_graph


class TestFeatureGraphIR(unittest.TestCase):

    def test_linear_dag_topological_sort(self):
        """测试标准线性依赖：基准草图 -> 拉伸凸台 -> 贯穿切除孔。"""
        graph = FeatureGraphIR(graph_id="fg_linear_part")

        n1 = FeatureNode(
            id="node_sketch_1",
            type=FeatureType.SKETCH_2D,
            name="Sketch1",
            parameters={"plane": "Front", "geometry": "rectangle_100x60"},
            depends_on=[],
        )
        n2 = FeatureNode(
            id="node_extrude_1",
            type=FeatureType.EXTRUDE_BOSS,
            name="Boss-Extrude1",
            parameters={"depth_mm": 20.0},
            depends_on=["node_sketch_1"],
        )
        n3 = FeatureNode(
            id="node_cut_1",
            type=FeatureType.EXTRUDE_CUT,
            name="Cut-Extrude1",
            parameters={"diameter_mm": 20.0, "through_all": True},
            depends_on=["node_extrude_1"],
        )

        # 故意打乱顺序加入图中
        graph.add_node(n3).add_node(n1).add_node(n2)

        ordered = graph.topological_sort()
        ordered_ids = [n.id for n in ordered]

        # 验证 Kahn 算法输出为确定性拓扑排序
        self.assertEqual(ordered_ids, ["node_sketch_1", "node_extrude_1", "node_cut_1"])

    def test_branching_dag_compilation(self):
        """测试多分支依赖图（凸台生成后，并行进行圆角切除与沉孔打向导）。"""
        data = {
            "graph_id": "fg_branching",
            "nodes": {
                "base_sketch": {
                    "type": "sketch_2d",
                    "name": "Sketch1",
                    "parameters": {"plane": "Top"},
                    "depends_on": [],
                },
                "base_extrude": {
                    "type": "extrude_boss",
                    "name": "Boss1",
                    "parameters": {"depth_mm": 15.0},
                    "depends_on": ["base_sketch"],
                },
                "corner_fillet": {
                    "type": "fillet",
                    "name": "Fillet1",
                    "parameters": {"radius_mm": 5.0},
                    "depends_on": ["base_extrude"],
                },
                "center_hole": {
                    "type": "hole_wizard",
                    "name": "Hole1",
                    "parameters": {"type": "counterbore", "size": "M6"},
                    "depends_on": ["base_extrude"],
                },
            },
        }
        graph = compile_feature_graph_from_dict(data)
        plan = graph.compile_execution_plan()

        self.assertEqual(len(plan), 4)
        # 前两步必须是 base_sketch 和 base_extrude
        self.assertEqual(plan[0]["node_id"], "base_sketch")
        self.assertEqual(plan[1]["node_id"], "base_extrude")
        # 第三和第四步是 corner_fillet 和 center_hole（分支无前后依赖，字典序稳定排序）
        branch_ids = {plan[2]["node_id"], plan[3]["node_id"]}
        self.assertEqual(branch_ids, {"corner_fillet", "center_hole"})

    def test_cyclic_dependency_detection(self):
        """测试循环回路死锁（A -> B -> C -> A）时准确抛出 CyclicDependencyError。"""
        graph = FeatureGraphIR(graph_id="fg_cyclic")
        graph.add_node(FeatureNode(id="A", type=FeatureType.SKETCH_2D, name="S1", depends_on=["C"]))
        graph.add_node(FeatureNode(id="B", type=FeatureType.EXTRUDE_BOSS, name="E1", depends_on=["A"]))
        graph.add_node(FeatureNode(id="C", type=FeatureType.FILLET, name="F1", depends_on=["B"]))

        with self.assertRaises(CyclicDependencyError) as ctx:
            graph.validate_dag()
        self.assertIn("闭环死锁", str(ctx.exception))

    def test_undefined_dependency_error(self):
        """测试引用不存在的前置节点时准确抛出 UndefinedDependencyError。"""
        graph = FeatureGraphIR(graph_id="fg_hanging")
        graph.add_node(FeatureNode(id="node_1", type=FeatureType.EXTRUDE_BOSS, name="E1", depends_on=["missing_node_999"]))

        with self.assertRaises(UndefinedDependencyError) as ctx:
            graph.validate_dag()
        self.assertIn("未定义的前置依赖", str(ctx.exception))

    def test_reverse_rollback_subgraph(self):
        """测试当某个特征失败时，逆向依赖分析准确圈定需要回滚的受影响子树。"""
        graph = FeatureGraphIR(graph_id="fg_rollback")
        # 拓扑：Base -> Hole -> Chamfer; Base -> Fillet
        graph.add_node(FeatureNode(id="base", type=FeatureType.EXTRUDE_BOSS, name="B", depends_on=[]))
        graph.add_node(FeatureNode(id="hole", type=FeatureType.EXTRUDE_CUT, name="H", depends_on=["base"]))
        graph.add_node(FeatureNode(id="chamfer", type=FeatureType.CHAMFER, name="C", depends_on=["hole"]))
        graph.add_node(FeatureNode(id="fillet", type=FeatureType.FILLET, name="F", depends_on=["base"]))

        # 若 hole 失败，受影响的子树应包含 hole 本身与依赖它的 chamfer，而不影响平行的 fillet！
        affected = graph.get_reverse_rollback_subgraph("hole")
        self.assertEqual(affected, ["chamfer", "hole"])

        # 若 base 失败，所有下游全部受影响
        affected_all = graph.get_reverse_rollback_subgraph("base")
        self.assertEqual(affected_all, ["base", "chamfer", "fillet", "hole"])

    def test_server_mcp_tool_integration(self):
        """测试 FastMCP 服务中新接入的 solidworks_compile_feature_graph 工具调用。"""
        valid_graph_data = {
            "graph_id": "test_mcp_graph",
            "target_part_name": "bracket",
            "nodes": {
                "sk1": {"type": "sketch_2d", "name": "Sketch1", "depends_on": []},
                "ex1": {"type": "extrude_boss", "name": "Boss1", "depends_on": ["sk1"]},
            },
        }
        res_str = solidworks_compile_feature_graph(FeatureGraphCompileInput(graph=valid_graph_data))
        res = json.loads(res_str)

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["node_count"], 2)
        self.assertEqual(len(res["execution_plan"]), 2)
        self.assertEqual(res["execution_plan"][0]["tool_name"], "solidworks_create_sketch")
        self.assertEqual(res["execution_plan"][1]["tool_name"], "solidworks_create_extrude")

        # 测试传入循环依赖图时，工具返回标准的结构化 error
        cyclic_data = {
            "nodes": {
                "n1": {"type": "sketch_2d", "name": "S1", "depends_on": ["n2"]},
                "n2": {"type": "extrude_boss", "name": "E1", "depends_on": ["n1"]},
            }
        }
        res_err_str = solidworks_compile_feature_graph(FeatureGraphCompileInput(graph=cyclic_data))
        res_err = json.loads(res_err_str)
        self.assertEqual(res_err["status"], "error")
        self.assertEqual(res_err["error_type"], "CyclicDependencyError")


if __name__ == "__main__":
    unittest.main()
