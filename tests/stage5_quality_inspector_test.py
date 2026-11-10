"""
第五阶段 S5-E 多维综合质量评价引擎单元测试
验证：
1. 四维加权雷达评分机制；
2. 彻底攻破孔位偏移钝化盲区（体积不变但坐标错位时精准拦截并扣分）；
3. 草图欠定义与过长重建耗时的扣分判定；
4. 制造工艺性（薄壁变形风险与内角应力集中）诊断。
"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "docs", "stage5_advanced_ai_cad", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from cad_quality_inspector import (
    CadQualityInspector,
    ComprehensiveQualityReport
)


class TestCadQualityInspector(unittest.TestCase):

    def setUp(self):
        self.inspector = CadQualityInspector()

    def test_ideal_model_high_score(self):
        """测试高标准理想零件获得 90 分以上卓越评价"""
        meas = {
            "volume": 100000.0,
            "surface_area": 15000.0,
            "body_count": 1,
            "min_wall_thickness": 4.0,
            "has_sharp_internal_corners": False
        }
        from cad_quality_inspector import issue_benchmark_credential
        cred = issue_benchmark_credential("IdealFlange", 100000.0)
        theo = {"volume": 100000.0, "credential": cred}
        samples = {"hole_center": [45.0, 0.0, 20.0]}
        expected = {"hole_center": [45.0, 0.0, 20.0]}

        report = self.inspector.inspect_quality(
            model_name="IdealFlange",
            measured_props=meas,
            theoretical_props=theo,
            feature_point_samples=samples,
            expected_point_samples=expected,
            rebuild_time_sec=0.2,
            sketch_constrained_status="FULLY_CONSTRAINED"
        )
        self.assertTrue(report.is_acceptable)
        self.assertGreaterEqual(report.overall_quality_score, 95.0)
        self.assertEqual(len(report.geometry_score.failed_checks), 0)

    def test_hole_offset_blindspot_breach(self):
        """
        核心反向测试：攻破孔位偏移钝化盲区！
        体积完全一致，但孔中心偏离 8mm。系统必须扣分并标记不合格！
        """
        meas = {"volume": 100000.0, "body_count": 1}
        theo = {"volume": 100000.0} # 体积完全相等！
        # 错位孔坐标
        samples = {"hole_1": [53.0, 0.0, 20.0]}
        expected = {"hole_1": [45.0, 0.0, 20.0]} # 预期在 45，偏移了 8mm

        report = self.inspector.inspect_quality(
            model_name="DefectiveHoleOffsetPart",
            measured_props=meas,
            theoretical_props=theo,
            feature_point_samples=samples,
            expected_point_samples=expected
        )
        # 预期：几何分项必须记录 failed_check，并且整体不接受 (is_acceptable = False)
        self.assertFalse(report.is_acceptable, "孔位严重偏移的伪劣模型绝不能判定为合格！")
        self.assertGreater(len(report.geometry_score.failed_checks), 0)
        self.assertIn("坐标偏移超差", report.geometry_score.failed_checks[0])

    def test_under_constrained_sketch_deduction(self):
        """测试草图欠定义扣分"""
        meas = {"volume": 50000.0, "body_count": 1}
        report = self.inspector.inspect_quality(
            model_name="UnderConstrainedPart",
            measured_props=meas,
            sketch_constrained_status="UNDER_CONSTRAINED"
        )
        self.assertLess(report.topology_score.score, 80.0)
        self.assertIn("欠定义", report.topology_score.warnings[0])

    def test_slow_rebuild_stability_deduction(self):
        """测试模型重建超长耗时扣分"""
        meas = {"volume": 50000.0, "body_count": 1}
        report = self.inspector.inspect_quality(
            model_name="HeavyPart",
            measured_props=meas,
            rebuild_time_sec=4.5 # 严重超时 (4.5s > 3.0s)
        )
        self.assertLess(report.stability_score.score, 80.0)
        self.assertIn("重建严重滞后", report.stability_score.failed_checks[0])

    def test_manufacturing_thin_wall_and_sharp_corner(self):
        """测试薄壁振刀风险与尖角应力集中警告"""
        meas = {
            "volume": 50000.0,
            "min_wall_thickness": 0.8, # 过薄 (<1.5mm)
            "has_sharp_internal_corners": True # 存在尖角
        }
        report = self.inspector.inspect_quality(
            model_name="FragilePart",
            measured_props=meas
        )
        self.assertLess(report.manufacturing_score.score, 60.0)
        rec_str = " ".join(report.actionable_recommendations)
        self.assertIn("薄壁结构", rec_str)
        self.assertIn("应力集中", rec_str)

    def test_missing_theory_graceful_handling(self):
        """测试缺失理论体积时的优雅降级"""
        meas = {"volume": 50000.0, "body_count": 1}
        report = self.inspector.inspect_quality(
            model_name="NoTheoryPart",
            measured_props=meas,
            theoretical_props=None
        )
        self.assertIn("缺少理论解析体积", report.geometry_score.warnings[0])


if __name__ == "__main__":
    unittest.main()
