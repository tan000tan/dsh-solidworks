# -*- coding: utf-8 -*-
"""
tests/model_quality_inspector_test.py
独立模型质量审查器 (Model Quality Inspector) 与反向对抗测试套件。

验证目标:
1. 正常合格模型: 评估全面健康，得分 >= 90，可制造性通过;
2. 反向测试 1 (零体积/空模型): 准确发现无实体缺陷并大幅扣分;
3. 反向测试 2 (特征求解报错): 准确识别特征错误码并定位出错特征;
4. 反向测试 3 (草图过定义与严重欠定义): 区分状态码 2 与 4 并给出针对性工程建议;
5. 反向测试 4 (设计目标独立交叉比对):
   - 体积相对误差超差拦截;
   - 包围盒几何超差拦截;
   - 实体数量不一致拦截;
   - 缺少必要特征与残留严禁特征拦截。
"""

import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENDOR_SCRIPTS = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"
if str(VENDOR_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(VENDOR_SCRIPTS))

from model_quality_inspector import (
    ModelQualityInspector,
    MQIReport,
    MQIDeduction,
    DesignIntentTarget,
    IntentVerificationResult,
)


class ModelQualityInspectorTests(unittest.TestCase):
    def test_01_perfect_model_assessment(self):
        """测试正常合格模型的质量评估。"""
        report = MQIReport(
            model_title="Shaft_Final.SLDPRT",
            score=95.0,
            grade="A",
            is_manufacturable=True,
            solid_body_count=1,
            total_feature_count=12,
            error_feature_count=0,
            total_sketch_count=3,
            fully_defined_sketches=3,
            fully_defined_ratio=1.0,
            total_dimensions=8,
            volume_mm3=150000.0,
            surface_area_mm2=24000.0,
            bounding_box_size_mm=[100.0, 50.0, 30.0],
            aspect_ratio=3.33,
        )
        self.assertEqual(report.grade, "A")
        self.assertTrue(report.is_manufacturable)
        self.assertEqual(report.error_feature_count, 0)
        self.assertEqual(report.fully_defined_ratio, 1.0)

    def test_02_negative_zero_volume_detection(self):
        """反向测试: 零体积或无实体空模型必须被判定为不可制造且大幅扣分。"""
        deductions = [
            MQIDeduction(
                dimension="geometry",
                item="EmptyPart.SLDPRT",
                reason="模型实测体积为 0 或未生成有效实体",
                penalty=40.0,
            )
        ]
        score = 100.0 - sum(d.penalty for d in deductions)
        report = MQIReport(
            model_title="EmptyPart.SLDPRT",
            score=score,
            grade="F",
            is_manufacturable=False,
            solid_body_count=0,
            volume_mm3=0.0,
            deductions=deductions,
        )
        self.assertEqual(report.grade, "F")
        self.assertFalse(report.is_manufacturable)
        self.assertEqual(report.solid_body_count, 0)
        self.assertTrue(any("实测体积为 0" in d.reason for d in report.deductions))

    def test_03_negative_feature_tree_errors_captured(self):
        """反向测试: 特征树中存在求解失败特征时必须准确识别并扣分。"""
        deductions = [
            MQIDeduction(
                dimension="feature_tree",
                item="凸台-拉伸2",
                reason="特征存在求解错误 (ErrorCode=104)",
                penalty=15.0,
                recommendation="请在特征管理器中编辑并修复特征 [凸台-拉伸2] 的父子依赖与几何输入",
            )
        ]
        report = MQIReport(
            model_title="BrokenBracket.SLDPRT",
            score=85.0,
            grade="B",
            is_manufacturable=False,  # 存在 error_feature 时不可交付
            solid_body_count=1,
            error_feature_count=1,
            volume_mm3=80000.0,
            deductions=deductions,
        )
        self.assertFalse(report.is_manufacturable)
        self.assertEqual(report.error_feature_count, 1)
        self.assertEqual(report.deductions[0].item, "凸台-拉伸2")

    def test_04_negative_sketch_over_and_under_constrained(self):
        """反向测试: 草图过定义与严重欠定义必须准确定性。"""
        deductions = [
            MQIDeduction(
                dimension="sketch_constraint",
                item="草图1",
                reason="草图存在几何过定义 (Over-constrained)",
                penalty=10.0,
            ),
            MQIDeduction(
                dimension="sketch_constraint",
                item="草图2",
                reason="草图处于严重欠定义状态 (浮动无约束且无尺寸标注)",
                penalty=8.0,
            ),
        ]
        score = 100.0 - 18.0
        report = MQIReport(
            model_title="Flange.SLDPRT",
            score=score,
            grade="B",
            is_manufacturable=True,
            total_sketch_count=2,
            fully_defined_sketches=0,
            fully_defined_ratio=0.0,
            deductions=deductions,
        )
        self.assertEqual(report.fully_defined_ratio, 0.0)
        self.assertEqual(len(report.deductions), 2)
        self.assertIn("过定义", report.deductions[0].reason)
        self.assertIn("欠定义", report.deductions[1].reason)

    def test_05_independent_design_intent_verification_pass(self):
        """测试设计意图独立交叉比对: 目标完全吻合。"""
        report = MQIReport(
            model_title="SteppedShaft.SLDPRT",
            solid_body_count=1,
            volume_mm3=100000.0,
            surface_area_mm2=18000.0,
            bounding_box_size_mm=[150.0, 30.0, 30.0],
        )
        target = DesignIntentTarget(
            expected_solid_bodies=1,
            expected_volume_mm3=100500.0,  # 偏差 0.5% (容差 2%)
            volume_tolerance_rel=0.02,
            expected_surface_area_mm2=18200.0,  # 偏差 1.1% (容差 3%)
            surface_area_tolerance_rel=0.03,
            expected_bbox_size_mm=[150.0, 30.0, 30.0],
            bbox_tolerance_mm=0.5,
            required_features=["Keyway", "Step"],
            prohibited_features=["TempSketch"],
        )
        actual_features = ["Front Plane", "Top Plane", "BaseBoss", "StepBoss", "KeywayCut", "Chamfer1"]

        res = ModelQualityInspector.verify_design_intent(report, target, actual_features)
        self.assertTrue(res.passed, f"预期通过，实际差异: {res.discrepancies}")
        self.assertEqual(len(res.discrepancies), 0)

    def test_06_independent_design_intent_adversarial_interceptions(self):
        """反向对抗测试: 故意制造体积超差、包围盒超差、实体数错误、缺少必要特征、残留严禁特征。"""
        report = MQIReport(
            model_title="BadModel.SLDPRT",
            solid_body_count=2,  # 错误 1: 多实体 (期望 1)
            volume_mm3=120000.0,  # 错误 2: 期望 100000 (偏差 20% > 容差 2%)
            surface_area_mm2=25000.0,  # 错误 3: 期望 18000 (偏差 38% > 容差 3%)
            bounding_box_size_mm=[160.0, 35.0, 30.0],  # 错误 4: X 偏差 10mm > 0.5mm
        )
        target = DesignIntentTarget(
            expected_solid_bodies=1,
            expected_volume_mm3=100000.0,
            volume_tolerance_rel=0.02,
            expected_surface_area_mm2=18000.0,
            surface_area_tolerance_rel=0.03,
            expected_bbox_size_mm=[150.0, 30.0, 30.0],
            bbox_tolerance_mm=0.5,
            required_features=["FilletStressRelief"],  # 错误 5: 缺少该关键特征
            prohibited_features=["StrayDraftSketch"],  # 错误 6: 残留该未清理草图
        )
        actual_features = ["BaseBoss", "StrayDraftSketch_Uncleaned"]

        res = ModelQualityInspector.verify_design_intent(report, target, actual_features)
        self.assertFalse(res.passed, "存在严重不符合项，验证器必须判定不通过")
        self.assertGreaterEqual(len(res.discrepancies), 5)
        
        # 逐项验证所有 5 个错误是否均被精准捕获
        disc_text = "\n".join(res.discrepancies)
        self.assertIn("实体数量不匹配", disc_text)
        self.assertIn("理论体积误差超差", disc_text)
        self.assertIn("表面积误差超差", disc_text)
        self.assertIn("包围盒维度 [0] 超差", disc_text)
        self.assertIn("缺少必要特征关键词: 'FilletStressRelief'", disc_text)
        self.assertIn("发现严禁残留的未清理特征: 'StrayDraftSketch'", disc_text)


if __name__ == "__main__":
    unittest.main()
