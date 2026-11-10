"""
第五阶段 S5-D 装配智能规划与约束分析器单元测试
验证：
1. 能够自动识别基准件并施加固定约束；
2. 能够正确构建装配零部件列表与配合关系；
3. 能够生成以基准件为核心的有序装配引入时序；
4. 能够静态检测距离配合数值矛盾冲突。
"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "docs", "stage5_advanced_ai_cad", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from assembly_planner import (
    AssemblyPlanner,
    AssemblyPlan,
    MateType
)


class TestAssemblyPlanner(unittest.TestCase):

    def setUp(self):
        self.planner = AssemblyPlanner()

    def test_base_part_auto_identification(self):
        """测试自动识别 base / housing 为基准件并固定"""
        parts = [
            {"part_name": "shaft", "instance_id": "shaft_1"},
            {"part_name": "flange_base", "instance_id": "flange_base_1"},
            {"part_name": "bolt", "instance_id": "bolt_1"},
        ]
        plan = self.planner.plan_assembly("TestAssembly", parts, [])
        self.assertEqual(plan.base_component_id, "flange_base_1")
        # 验证该零件被显式固定
        fixed_parts = [c.instance_id for c in plan.components if c.is_fixed]
        self.assertEqual(fixed_parts, ["flange_base_1"])

    def test_assembly_sequence_propagation(self):
        """测试从基准件出发的配合拓扑引入时序"""
        parts = [
            {"part_name": "housing", "instance_id": "housing_1"},
            {"part_name": "bearing", "instance_id": "bearing_1"},
            {"part_name": "shaft", "instance_id": "shaft_1"},
        ]
        # housing 配合 bearing, bearing 配合 shaft
        constraints = [
            {"mate_id": "m1", "mate_type": "concentric", "comp_a": "housing_1", "comp_b": "bearing_1"},
            {"mate_id": "m2", "mate_type": "coincident", "comp_a": "bearing_1", "comp_b": "shaft_1"}
        ]
        plan = self.planner.plan_assembly("BearingUnit", parts, constraints)
        self.assertEqual(plan.assembly_sequence[0], "housing_1")
        self.assertEqual(plan.assembly_sequence[1], "bearing_1")
        self.assertEqual(plan.assembly_sequence[2], "shaft_1")

    def test_distance_mate_conflict_detection(self):
        """测试相同几何面矛盾距离配合冲突检测"""
        parts = [
            {"part_name": "base", "instance_id": "base_1"},
            {"part_name": "plate", "instance_id": "plate_1"}
        ]
        # 矛盾约束：同一面对齐指定距离 10mm 又指定距离 20mm
        constraints = [
            {"mate_id": "m1", "mate_type": "distance", "comp_a": "base_1", "ref_a": "top", "comp_b": "plate_1", "ref_b": "bot", "value": 10.0},
            {"mate_id": "m2", "mate_type": "distance", "comp_a": "base_1", "ref_a": "top", "comp_b": "plate_1", "ref_b": "bot", "value": 20.0}
        ]
        plan = self.planner.plan_assembly("ConflictAssembly", parts, constraints)
        self.assertTrue(plan.has_conflicts)
        self.assertEqual(len(plan.conflict_details), 1)
        self.assertIn("矛盾的距离配合", plan.conflict_details[0])

    def test_empty_constraints_plan(self):
        """测试无配合约束下的装配体退化规划"""
        parts = [{"part_name": "part_A", "instance_id": "A"}]
        plan = self.planner.plan_assembly("SinglePartAsm", parts, [])
        self.assertFalse(plan.has_conflicts)
        self.assertEqual(len(plan.assembly_sequence), 1)

    def test_multiple_mate_types(self):
        """测试多种配合类型支持 (同心 + 重合)"""
        parts = [
            {"part_name": "base", "instance_id": "base_1"},
            {"part_name": "pin", "instance_id": "pin_1"}
        ]
        constraints = [
            {"mate_id": "m1", "mate_type": "concentric", "comp_a": "base_1", "comp_b": "pin_1"},
            {"mate_id": "m2", "mate_type": "coincident", "comp_a": "base_1", "comp_b": "pin_1"}
        ]
        plan = self.planner.plan_assembly("PinAsm", parts, constraints)
        self.assertFalse(plan.has_conflicts)
        self.assertEqual(len(plan.mates), 2)


if __name__ == "__main__":
    unittest.main()
