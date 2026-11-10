"""
第五阶段 S5-A 多方案自动规划与比较引擎单元测试
验证：
1. 能够对典型回转零件生成至少 3 个结构化方案；
2. 方案间具有实质工艺差异；
3. 量化加权评分与排序算法符合逻辑；
4. 推荐方案与优选理由透明完备。
"""
import os
import sys
import unittest

# 动态加载 scripts 目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "docs", "stage5_advanced_ai_cad", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from multi_scheme_planner import (
    MultiSchemePlanner,
    ManufacturingIntent,
    MultiSchemePlanResult
)


class TestMultiSchemePlanner(unittest.TestCase):

    def setUp(self):
        self.planner = MultiSchemePlanner()

    def test_flange_multi_scheme_generation(self):
        """测试法兰盘多方案生成与选优"""
        spec = {
            "part_type": "flange",
            "description": "设计外径120mm、中心孔40mm、带4个螺栓孔的标准承压法兰",
            "outer_diameter": 120.0,
            "bore_diameter": 40.0,
            "flange_thickness": 20.0,
            "bolt_count": 4
        }
        result = self.planner.plan_schemes(spec)

        self.assertIsInstance(result, MultiSchemePlanResult)
        self.assertGreaterEqual(len(result.candidate_schemes), 3, "回转类零件应至少生成 3 个候选方案")

        # 验证方案 ID
        scheme_ids = [s.scheme_id for s in result.candidate_schemes]
        self.assertIn("SCHEME_A_TURNING", scheme_ids)
        self.assertIn("SCHEME_B_STACKED_EXTRUSION", scheme_ids)
        self.assertIn("SCHEME_C_SUBTRACTIVE", scheme_ids)

        # 验证方案工艺类型各不相同
        intents = {s.manufacturing_intent for s in result.candidate_schemes}
        self.assertEqual(len(intents), 3, "候选方案必须包含 3 种不同的工艺意图")

    def test_scheme_scoring_and_recommendation(self):
        """测试方案量化打分逻辑与推荐结果"""
        spec = {
            "part_type": "bushing",
            "description": "设计耐磨阶梯轴套"
        }
        result = self.planner.plan_schemes(spec)

        # 回转类零件通常车削方案由于特征树紧凑、重建风险低，应获推荐第一名
        self.assertEqual(result.recommended_scheme_id, "SCHEME_A_TURNING")
        rec_scheme = result.candidate_schemes[0]
        self.assertGreater(rec_scheme.overall_score, 80.0, "推荐方案得分应高于 80 分")
        self.assertTrue(len(result.recommendation_summary) > 20)

    def test_general_box_multi_scheme(self):
        """测试非回转类（箱体/支架）多方案生成"""
        spec = {
            "part_type": "housing",
            "description": "设计齿轮箱外壳底座"
        }
        result = self.planner.plan_schemes(spec)
        self.assertGreaterEqual(len(result.candidate_schemes), 2)
        # 箱体类不应优先推荐回转车削
        scheme_ids = [s.scheme_id for s in result.candidate_schemes]
        self.assertNotIn("SCHEME_A_TURNING", scheme_ids)

    def test_score_boundary(self):
        """测试评分边界与极值稳定性"""
        spec = {"part_type": "flange"}
        result = self.planner.plan_schemes(spec)
        for s in result.candidate_schemes:
            self.assertGreaterEqual(s.overall_score, 0.0)
            self.assertLessEqual(s.overall_score, 100.0)

    def test_scheme_steps_integrity(self):
        """测试各步骤参数与依赖关系完整性"""
        spec = {"part_type": "flange"}
        result = self.planner.plan_schemes(spec)
        for s in result.candidate_schemes:
            self.assertGreater(len(s.steps), 0)
            for step in s.steps:
                self.assertIsNotNone(step.step_id)
                self.assertIsNotNone(step.feature_type)
                self.assertIsInstance(step.params, dict)


if __name__ == "__main__":
    unittest.main()
