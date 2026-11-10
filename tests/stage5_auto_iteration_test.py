"""
第五阶段 S5-C 自动迭代修改与影响分析引擎单元测试
验证：
1. 能够基于特征 DAG 正确推导直接受影响特征和间接受影响特征；
2. 能够推导参数修改的风险等级 (LOW, MEDIUM, HIGH)；
3. 能够精确计算修改前后的体积与表面积 Diff；
4. 能够智能校验切削与凸台修改后的几何物理单调性。
"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "docs", "stage5_advanced_ai_cad", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from auto_iteration_engine import (
    AutoIterationEngine,
    ModificationImpact,
    IterationDiffResult
)


class TestAutoIterationEngine(unittest.TestCase):

    def setUp(self):
        self.engine = AutoIterationEngine()
        # 构建一个典型的 4 级特征依赖图
        # F1_base -> F2_boss -> F3_hole -> F4_chamfer
        self.feature_dag = [
            {"feature_id": "F1_base", "depends_on": []},
            {"feature_id": "F2_boss", "depends_on": ["F1_base"]},
            {"feature_id": "F3_hole", "depends_on": ["F2_boss"]},
            {"feature_id": "F4_chamfer", "depends_on": ["F3_hole"]}
        ]
        self.dim_graph = {
            "base_radius": ["flange_outer_diam"],
            "hole_diameter": ["drill_clearance"]
        }
        self.param_map = {
            "base_radius": "F1_base",
            "boss_height": "F2_boss",
            "hole_diameter": "F3_hole"
        }

    def test_impact_analysis_root_parameter(self):
        """测试根节点参数（底座半径）修改影响域分析"""
        impact = self.engine.analyze_impact(
            feature_dag=self.feature_dag,
            dimension_graph=self.dim_graph,
            target_param="base_radius",
            param_feature_map=self.param_map,
            old_val=50.0,
            new_val=60.0
        )
        self.assertIsInstance(impact, ModificationImpact)
        self.assertEqual(impact.direct_affected_features, ["F2_boss"])
        # 间接受影响特征应包括 F3_hole 和 F4_chamfer
        self.assertIn("F3_hole", impact.indirect_affected_features)
        self.assertIn("F4_chamfer", impact.indirect_affected_features)
        self.assertEqual(impact.risk_level, "MEDIUM")

    def test_impact_analysis_leaf_parameter(self):
        """测试末端叶子节点参数修改影响域分析"""
        impact = self.engine.analyze_impact(
            feature_dag=self.feature_dag,
            dimension_graph=self.dim_graph,
            target_param="hole_diameter",
            param_feature_map=self.param_map,
            old_val=20.0,
            new_val=22.0
        )
        # 末端特征修改，直接波及仅 F4_chamfer，无间接波及，变幅 10% -> LOW 风险
        self.assertEqual(impact.direct_affected_features, ["F4_chamfer"])
        self.assertEqual(len(impact.indirect_affected_features), 0)
        self.assertEqual(impact.risk_level, "LOW")

    def test_geometry_diff_boss_increase(self):
        """测试凸台拉伸增大时的几何 Diff 正常比对"""
        impact = self.engine.analyze_impact(
            self.feature_dag, self.dim_graph, "boss_height", self.param_map, 30.0, 40.0
        )
        geom_before = {"volume": 100000.0, "surface_area": 15000.0, "bbox_diagonal": 120.0}
        geom_after = {"volume": 125000.0, "surface_area": 17000.0, "bbox_diagonal": 130.0}

        diff = self.engine.calculate_geometry_diff(impact, geom_before, geom_after)
        self.assertTrue(diff.success)
        self.assertTrue(diff.is_safe)
        self.assertEqual(diff.delta_volume, 25000.0)
        self.assertEqual(diff.delta_param_value, 10.0)

    def test_geometry_diff_hole_abnormal_warning(self):
        """测试挖孔增大但体积反常增加的异常捕获与警告"""
        impact = self.engine.analyze_impact(
            self.feature_dag, self.dim_graph, "hole_diameter", self.param_map, 20.0, 30.0
        )
        # 假定异常数据：挖孔变大，体积反而增加
        geom_before = {"volume": 100000.0, "surface_area": 15000.0}
        geom_after = {"volume": 105000.0, "surface_area": 16000.0}

        diff = self.engine.calculate_geometry_diff(impact, geom_before, geom_after)
        self.assertFalse(diff.is_safe, "孔增大体积增加应当判定为不安全异常")
        self.assertIn("异常：孔切除尺寸增大", diff.message)

    def test_impact_high_risk_threshold(self):
        """测试剧烈修改（>50%）自动升为 HIGH 风险"""
        impact = self.engine.analyze_impact(
            self.feature_dag, self.dim_graph, "base_radius", self.param_map, 50.0, 100.0
        )
        self.assertEqual(impact.risk_level, "HIGH")


if __name__ == "__main__":
    unittest.main()
