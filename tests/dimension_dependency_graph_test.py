# -*- coding: utf-8 -*-
"""
tests/dimension_dependency_graph_test.py
DDG 参数依赖图单元测试套件。
涵盖：
1. 拓扑排序与分层解析
2. 环路依赖检测
3. 变更影响域分析
4. 零漂移比对核验器
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from dimension_ir import DimensionIRNode, DimensionModelIR, DimensionRole, DimensionType
from dimension_dependency_graph import DimensionDependencyGraph, DDGImpactReport


class TestDimensionDependencyGraph(unittest.TestCase):

    def setUp(self):
        self.ddg = DimensionDependencyGraph(model_title="MotorBracket")

    def test_topological_sort_linear_pipeline(self):
        """测试标准线性依赖管线的拓扑排序。"""
        # BaseSketch (D1, D2) -> BaseBoss -> MountHolesSketch (D1) -> MountHolesCut
        d1 = DimensionIRNode.create("D1@BaseSketch", 0.150, feature_name="BaseSketch")
        d2 = DimensionIRNode.create("D2@BaseSketch", 0.100, feature_name="BaseSketch")
        d3 = DimensionIRNode.create("D1@MountHolesSketch", 0.012, feature_name="MountHolesSketch")

        self.ddg.add_dimension(d1)
        self.ddg.add_dimension(d2)
        self.ddg.add_dimension(d3)
        self.ddg.add_feature("BaseBoss", "Extrusion")
        self.ddg.add_feature("MountHolesCut", "Cut")

        self.ddg.add_dependency("BaseSketch", "BaseBoss")
        self.ddg.add_dependency("BaseBoss", "MountHolesSketch")
        self.ddg.add_dependency("MountHolesSketch", "MountHolesCut")

        topo = self.ddg.topological_sort()
        # 验证偏序关系
        self.assertLess(topo.index("D1@BaseSketch"), topo.index("BaseSketch"))
        self.assertLess(topo.index("BaseSketch"), topo.index("BaseBoss"))
        self.assertLess(topo.index("BaseBoss"), topo.index("MountHolesSketch"))
        self.assertLess(topo.index("MountHolesSketch"), topo.index("MountHolesCut"))

    def test_cycle_detection(self):
        """测试循环依赖检测。"""
        self.ddg.add_feature("FeatA")
        self.ddg.add_feature("FeatB")
        self.ddg.add_feature("FeatC")

        self.ddg.add_dependency("FeatA", "FeatB")
        self.ddg.add_dependency("FeatB", "FeatC")
        self.ddg.add_dependency("FeatC", "FeatA")  # 环路

        cycles = self.ddg.detect_cycles()
        self.assertGreater(len(cycles), 0)
        with self.assertRaises(ValueError):
            self.ddg.topological_sort()

    def test_impact_scope_analysis(self):
        """测试变更影响域提取。"""
        d1 = DimensionIRNode.create("D1@BaseSketch", 0.150, feature_name="BaseSketch")
        self.ddg.add_dimension(d1)
        self.ddg.add_feature("BaseBoss")
        self.ddg.add_feature("UprightBoss")
        self.ddg.add_feature("MountHolesCut")

        self.ddg.add_dependency("BaseSketch", "BaseBoss")
        self.ddg.add_dependency("BaseBoss", "UprightBoss")
        self.ddg.add_dependency("BaseBoss", "MountHolesCut")

        scope = self.ddg.get_impact_scope("D1@BaseSketch")
        # 修改底板长度，底板拉伸、立柱和安装孔都应在影响域中
        self.assertIn("BaseSketch", scope)
        self.assertIn("BaseBoss", scope)
        self.assertIn("UprightBoss", scope)
        self.assertIn("MountHolesCut", scope)

    def test_zero_drift_validator(self):
        """测试零漂移验证器逻辑。"""
        baseline = {
            "D1@BaseSketch": 150.0,
            "D2@BaseSketch": 100.0,
            "D1@MountHolesSketch": 12.0,
            "D2@MountHolesSketch": 100.0,
        }

        # 场景 1: 完美匹配
        current_perfect = {
            "D1@BaseSketch": 180.0,  # 目标修改
            "D2@BaseSketch": 100.0,  # 保持
            "D1@MountHolesSketch": 12.0,  # 保持
            "D2@MountHolesSketch": 100.0,  # 保持
        }
        passed, violations = DimensionDependencyGraph.verify_zero_drift(
            baseline, current_perfect, {"D1@BaseSketch": 180.0}
        )
        self.assertTrue(passed)
        self.assertEqual(len(violations), 0)

        # 场景 2: 目标未达成
        current_bad_target = {
            "D1@BaseSketch": 175.0,  # 预期 180.0
            "D2@BaseSketch": 100.0,
            "D1@MountHolesSketch": 12.0,
            "D2@MountHolesSketch": 100.0,
        }
        passed, violations = DimensionDependencyGraph.verify_zero_drift(
            baseline, current_bad_target, {"D1@BaseSketch": 180.0}
        )
        self.assertFalse(passed)
        self.assertEqual(violations[0]["type"], "TARGET_DEVIATION")

        # 场景 3: 非目标尺寸发生意外漂移
        current_drift = {
            "D1@BaseSketch": 180.0,
            "D2@BaseSketch": 105.0,  # 意外漂移 +5mm
            "D1@MountHolesSketch": 12.0,
            "D2@MountHolesSketch": 100.0,
        }
        passed, violations = DimensionDependencyGraph.verify_zero_drift(
            baseline, current_drift, {"D1@BaseSketch": 180.0}
        )
        self.assertFalse(passed)
        self.assertEqual(violations[0]["type"], "UNINTENDED_DRIFT")
        self.assertAlmostEqual(violations[0]["drift_mm"], 5.0)


if __name__ == "__main__":
    unittest.main()
