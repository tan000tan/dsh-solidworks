"""
高阶 CAD 质量检查器回归测试套件 (DEF-05 重构与防伪加固版)
(Remediation Test for DEF-05: cad_quality_inspector.py)

测试覆盖：
1. 携带权威基准凭证的理论值与实测值吻合优秀 (VERIFIED)
2. 正常工程容差范围内的微小偏差 (0.02% <= 0.05%)
3. 超出工程容差的严重超差拦截 (FAILED)
4. 理论值缺失严格拦截 (NOT_VERIFIED 且 is_acceptable=False)
5. 字段兼容性 (volume 与 volume_mm3 结合凭据验证)
6. 非法数值防御 (实测 <= 0, NaN 等)
7. 指针同一性自比对虚假核验硬拦截 (FAILED)
8. 微观采样点空间偏移拦截 (FAILED)
9. 字典浅拷贝克隆攻击硬拦截 (FAILED)
10. 字典深拷贝克隆攻击硬拦截 (FAILED)
11. 拒绝明文 provenance 伪装，必须通过密码学基准验签 (DEF-05 核心防伪)
"""
import copy
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "docs", "stage5_advanced_ai_cad", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from cad_quality_inspector import (
    CadQualityInspector,
    BenchmarkCredential,
    issue_benchmark_credential,
)


class TestCadQualityInspectorRemediation(unittest.TestCase):

    def setUp(self):
        self.inspector = CadQualityInspector()

    def test_01_ideal_match_with_authenticated_source(self):
        """场景 1: 理论值与实测值吻合，且附带权威独立基准凭证"""
        meas = {"volume": 55600.0, "body_count": 1, "min_wall_thickness": 4.0}
        cred = issue_benchmark_credential(
            model_id="IndependentPerfectPart",
            volume_analytical_mm3=55600.0
        )
        theo = {"volume": 55600.0, "credential": cred}
        report = self.inspector.inspect_quality(
            model_name="IndependentPerfectPart",
            measured_props=meas,
            theoretical_props=theo,
            independent_theoretical_source=True
        )
        self.assertTrue(report.is_acceptable)
        self.assertEqual(report.verification_status, "VERIFIED")
        self.assertEqual(report.geometry_score.score, 100.0)
        self.assertEqual(len(report.geometry_score.failed_checks), 0)

    def test_02_normal_engineering_tolerance(self):
        """场景 2: 宏观微小工程容差 (相对误差 0.02% <= 0.05%)"""
        meas = {"volume": 55611.12, "body_count": 1}
        cred = issue_benchmark_credential(
            model_id="NormalTolerancePart",
            volume_analytical_mm3=55600.0
        )
        theo = {"volume": 55600.0, "credential": cred}
        report = self.inspector.inspect_quality(
            model_name="NormalTolerancePart",
            measured_props=meas,
            theoretical_props=theo
        )
        self.assertTrue(report.is_acceptable)
        self.assertEqual(report.verification_status, "VERIFIED")
        self.assertEqual(report.geometry_score.score, 100.0)

    def test_03_out_of_tolerance_failure(self):
        """场景 3: 体积超出允许误差 (如偏差 2.5% > 1.0%)"""
        meas = {"volume": 57000.0, "body_count": 1}
        cred = issue_benchmark_credential(
            model_id="OutOfTolerancePart",
            volume_analytical_mm3=55600.0
        )
        theo = {"volume": 55600.0, "credential": cred}
        report = self.inspector.inspect_quality(
            model_name="OutOfTolerancePart",
            measured_props=meas,
            theoretical_props=theo
        )
        self.assertFalse(report.is_acceptable)
        self.assertEqual(report.verification_status, "FAILED")
        self.assertLessEqual(report.geometry_score.score, 60.0)
        self.assertIn("超标严重", report.geometry_score.failed_checks[0])

    def test_04_missing_theoretical_volume_defense(self):
        """场景 4: 理论值缺失 (不得给 100 分，必须标记 NOT_VERIFIED 且 is_acceptable=False)"""
        meas = {"volume": 55600.0, "body_count": 1}
        report = self.inspector.inspect_quality(
            model_name="MissingTheoreticalPart",
            measured_props=meas,
            theoretical_props=None
        )
        self.assertFalse(report.is_acceptable, "缺失理论值绝不能判定为 is_acceptable=True！")
        self.assertEqual(report.verification_status, "NOT_VERIFIED")
        self.assertEqual(report.geometry_score.status, "NOT_VERIFIED")
        self.assertLessEqual(report.geometry_score.score, 60.0)
        self.assertIn("缺少理论解析体积", report.geometry_score.warnings[0])

    def test_05_field_name_compatibility_volume_mm3(self):
        """场景 5: 字段名称多样性兼容 (实测使用 volume_mm3，凭证使用 volume_analytical_mm3)"""
        meas = {"volume_mm3": 43275.44, "body_count": 1}
        cred = issue_benchmark_credential(
            model_id="KeyNameCompatiblePart",
            volume_analytical_mm3=43275.44
        )
        theo = {"volume_mm3": 43275.44, "credential": cred}
        report = self.inspector.inspect_quality(
            model_name="KeyNameCompatiblePart",
            measured_props=meas,
            theoretical_props=theo
        )
        self.assertTrue(report.is_acceptable)
        self.assertEqual(report.metrics_summary.get("volume_measured_mm3"), 43275.44)
        self.assertEqual(report.metrics_summary.get("volume_theoretical_mm3"), 43275.44)

    def test_06_illegal_and_negative_volume_defense(self):
        """场景 6: 非法数值防御 (实测体积 <= 0, NaN, 负值等)"""
        meas_neg = {"volume": -100.0, "body_count": 1}
        report_neg = self.inspector.inspect_quality("NegPart", meas_neg, {"volume": 100.0})
        self.assertFalse(report_neg.is_acceptable)
        self.assertEqual(report_neg.verification_status, "FAILED")
        self.assertEqual(report_neg.geometry_score.score, 0.0)

        meas_nan = {"volume": float("nan"), "body_count": 1}
        report_nan = self.inspector.inspect_quality("NanPart", meas_nan, {"volume": 100.0})
        self.assertFalse(report_nan.is_acceptable)
        self.assertEqual(report_nan.geometry_score.score, 0.0)

    def test_07_self_comparison_intercepted(self):
        """场景 7: 自比对虚假核验精准拦截 (measured is theoretical)"""
        shared_dict = {"volume": 55600.0, "body_count": 1}
        report = self.inspector.inspect_quality(
            model_name="FakeSelfComparisonPart",
            measured_props=shared_dict,
            theoretical_props=shared_dict  # 传入同一对象！
        )
        self.assertFalse(report.is_acceptable)
        self.assertEqual(report.verification_status, "FAILED")
        self.assertEqual(report.geometry_score.score, 0.0)
        self.assertIn("自比对虚假核验", report.geometry_score.failed_checks[0])
        self.assertTrue(report.metrics_summary.get("self_comparison_detected"))

    def test_08_micro_point_sample_deviation(self):
        """场景 8: 宏观体积一致但微观空间采样点偏移精准拦截"""
        meas = {"volume": 55600.0, "body_count": 1}
        cred = issue_benchmark_credential(
            model_id="DeviatedSamplePart",
            volume_analytical_mm3=55600.0
        )
        theo = {"volume": 55600.0, "credential": cred}
        samples = {"keyway_corner": [25.0, 0.0, 15.5]}
        expected = {"keyway_corner": [25.0, 0.0, 15.0]}  # Z 轴偏移了 0.5mm > 0.005mm
        report = self.inspector.inspect_quality(
            model_name="DeviatedSamplePart",
            measured_props=meas,
            theoretical_props=theo,
            feature_point_samples=samples,
            expected_point_samples=expected
        )
        self.assertFalse(report.is_acceptable)
        self.assertEqual(report.verification_status, "FAILED")
        self.assertIn("坐标偏移超差", report.geometry_score.failed_checks[0])

    def test_09_dict_clone_bypass_intercepted(self):
        """场景 9: 字典浅拷贝克隆攻击精准拦截 (theo = dict(meas)) 判为 FAILED"""
        meas = {"volume": 55600.0, "body_count": 1, "min_wall_thickness": 4.0}
        theo_clone = dict(meas)  # 新字典对象，指针不同
        self.assertIsNot(meas, theo_clone)

        report = self.inspector.inspect_quality(
            model_name="DictCloneBypassPart",
            measured_props=meas,
            theoretical_props=theo_clone
        )
        self.assertFalse(report.is_acceptable, "克隆字典绝不允许通过验收")
        self.assertEqual(report.verification_status, "FAILED")
        self.assertEqual(report.geometry_score.score, 0.0)
        self.assertTrue(report.metrics_summary.get("clone_attack_detected"))

    def test_10_deepcopy_clone_bypass_intercepted(self):
        """场景 10: 字典深拷贝克隆攻击精准拦截 (theo = copy.deepcopy(meas)) 判为 FAILED"""
        meas = {"volume": 43275.44, "body_count": 1, "surface_area_mm2": 12000.0}
        theo_deep = copy.deepcopy(meas)
        self.assertIsNot(meas, theo_deep)

        report = self.inspector.inspect_quality(
            model_name="DeepCopyClonePart",
            measured_props=meas,
            theoretical_props=theo_deep
        )
        self.assertFalse(report.is_acceptable)
        self.assertEqual(report.verification_status, "FAILED")
        self.assertEqual(report.geometry_score.score, 0.0)
        self.assertTrue(report.metrics_summary.get("clone_attack_detected"))

    def test_11_reject_plaintext_provenance_and_require_cryptographic_credential(self):
        """场景 11: 绝不盲信明文 provenance，仅信任密码学验签凭据"""
        meas = {"volume": 55600.0, "body_count": 1}
        # 1. 尝试注入明文 provenance 绕过：拒绝给予 VERIFIED
        forged_plaintext = {"volume": 55600.0, "provenance": "analytical_calculation"}
        report_forged = self.inspector.inspect_quality(
            model_name="TrustedProvenancePart",
            measured_props=meas,
            theoretical_props=forged_plaintext
        )
        self.assertFalse(report_forged.is_acceptable, "明文 provenance 绝不能直接通过验证")
        self.assertEqual(report_forged.verification_status, "NOT_VERIFIED")

        # 2. 携带真正的密码学基准凭证：顺利通过验签
        cred = issue_benchmark_credential(
            model_id="TrustedProvenancePart",
            volume_analytical_mm3=55600.0
        )
        legit_theo = {"volume": 55600.0, "credential": cred}
        report_legit = self.inspector.inspect_quality(
            model_name="TrustedProvenancePart",
            measured_props=meas,
            theoretical_props=legit_theo
        )
        self.assertTrue(report_legit.is_acceptable)
        self.assertEqual(report_legit.verification_status, "VERIFIED")
        self.assertTrue(report_legit.metrics_summary.get("credential_verified"))


if __name__ == "__main__":
    unittest.main()
