# -*- coding: utf-8 -*-
"""
tests/dimension_system_test.py
P1 尺寸驱动与参数化修改体系离线单元测试套件。

涵盖：
1. Dimension IR 数据结构、单位转换与检索
2. Dimension Resolver 自然语言解析、单位换算、消歧与约束校验
3. Dimension Reader 尺寸类型推断与拓扑装配
4. Model Rebuilder 重建健康状态评估
5. Dimension Modifier 就地参数修改与异常快照回滚
6. Dimension Validator 前后参数比对与几何趋势校验
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"

for p in (str(SCRIPTS_DIR), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from dimension_ir import DimensionIRNode, DimensionModelIR, DimensionType, DimensionRole
from dimension_reader import infer_dimension_type
from dimension_resolver import DimensionResolver, parse_numeric_with_unit
from model_rebuilder import ModelRebuilder, RebuildReport
from dimension_modifier import DimensionModifier, ModificationResult
from dimension_validator import DimensionValidator


class TestDimensionIR(unittest.TestCase):
    """测试 Dimension IR 节点与模型容器。"""

    def test_node_creation_and_unit_conversion(self):
        # 0.1 米 -> 100 毫米
        node = DimensionIRNode.create(
            dimension_name="D1@Sketch1",
            system_value=0.1,
            feature_name="Sketch1",
            feature_type="ProfileFeature",
            dim_type=DimensionType.SKETCH_LINEAR,
        )
        self.assertEqual(node.value, 100.0)
        self.assertEqual(node.unit, "mm")
        self.assertEqual(node.system_value, 0.1)
        self.assertEqual(node.role, DimensionRole.DRIVING)
        self.assertTrue(node.editable)

    def test_angle_unit_conversion(self):
        # pi/2 弧度 -> 90 度
        import math
        node = DimensionIRNode.create(
            dimension_name="A1@Revolve1",
            system_value=math.pi / 2,
            feature_name="Revolve1",
            feature_type="Revolve",
            dim_type=DimensionType.REVOLVE_ANGLE,
        )
        self.assertAlmostEqual(node.value, 90.0, places=2)
        self.assertEqual(node.unit, "deg")

    def test_model_ir_queries(self):
        model_ir = DimensionModelIR(model_title="Flange.SLDPRT")
        n1 = DimensionIRNode.create("D1@Sketch1", 0.12, "Sketch1", dim_type=DimensionType.SKETCH_LINEAR)
        n2 = DimensionIRNode.create("D2@Sketch1", 0.08, "Sketch1", dim_type=DimensionType.SKETCH_LINEAR)
        n3 = DimensionIRNode.create("D1@Boss1", 0.02, "Boss1", dim_type=DimensionType.EXTRUSION_DEPTH)
        n4 = DimensionIRNode.create("RD1@Sketch1", 0.05, "Sketch1", is_driven=True)

        model_ir.add_dimension(n1)
        model_ir.add_dimension(n2)
        model_ir.add_dimension(n3)
        model_ir.add_dimension(n4)

        self.assertEqual(model_ir.total_count, 4)
        self.assertEqual(len(model_ir.get_driving_dimensions()), 3)
        self.assertEqual(len(model_ir.get_by_feature("Sketch1")), 3)

        # 名字检索
        self.assertIsNotNone(model_ir.get_dimension("d1@sketch1"))
        self.assertIsNotNone(model_ir.get_dimension("D1@Boss1"))
        self.assertIsNone(model_ir.get_dimension("NonExistent"))


class TestDimensionResolver(unittest.TestCase):
    """测试自然语言与目标尺寸的解析消歧。"""

    def setUp(self):
        self.model_ir = DimensionModelIR(model_title="Flange.SLDPRT")
        self.model_ir.add_dimension(
            DimensionIRNode.create("D1@BaseSketch", 0.12, "BaseSketch", dim_type=DimensionType.SKETCH_LINEAR)
        )
        self.model_ir.add_dimension(
            DimensionIRNode.create("D2@BaseSketch", 0.08, "BaseSketch", dim_type=DimensionType.SKETCH_LINEAR)
        )
        self.model_ir.add_dimension(
            DimensionIRNode.create("D1@BossPlate", 0.015, "BossPlate", dim_type=DimensionType.EXTRUSION_DEPTH)
        )
        self.model_ir.add_dimension(
            DimensionIRNode.create("Dia1@HoleSketch", 0.025, "HoleSketch", dim_type=DimensionType.SKETCH_DIAMETER)
        )
        self.resolver = DimensionResolver(self.model_ir)

    def test_numeric_unit_extraction(self):
        self.assertEqual(parse_numeric_with_unit("150 mm"), (150.0, "mm"))
        self.assertEqual(parse_numeric_with_unit("25毫米"), (25.0, "mm"))
        self.assertEqual(parse_numeric_with_unit("0.05 m"), (50.0, "mm"))
        self.assertEqual(parse_numeric_with_unit("10 cm"), (100.0, "mm"))
        self.assertAlmostEqual(parse_numeric_with_unit("2 inch")[0], 50.8, places=2)

    def test_resolve_absolute_modification(self):
        res = self.resolver.resolve("把底座长度改为 150 毫米")
        self.assertTrue(res.success)
        self.assertIsNotNone(res.resolved_target)
        self.assertEqual(res.resolved_target.dimension_name, "D1@BaseSketch")
        self.assertEqual(res.resolved_target.target_value_mm, 150.0)

    def test_resolve_hole_diameter(self):
        res = self.resolver.resolve("将中央孔直径改为 30 mm")
        self.assertTrue(res.success)
        self.assertEqual(res.resolved_target.dimension_name, "Dia1@HoleSketch")
        self.assertEqual(res.resolved_target.target_value_mm, 30.0)

    def test_resolve_relative_increment(self):
        res = self.resolver.resolve("把底座板厚增加 5 mm")
        self.assertTrue(res.success)
        # 原始 15mm + 5mm = 20mm
        self.assertEqual(res.resolved_target.dimension_name, "D1@BossPlate")
        self.assertEqual(res.resolved_target.target_value_mm, 20.0)
        self.assertEqual(res.resolved_target.delta_mm, 5.0)

    def test_illegal_non_positive_value(self):
        res = self.resolver.resolve("把底座板厚减小 20 mm")
        # 原始 15mm - 20mm = -5mm 非法
        self.assertFalse(res.success)
        self.assertIn("非物理非法值", res.error_message)


class TestDimensionModifierAndRollback(unittest.TestCase):
    """测试就地修改执行器与快照回滚机制。"""

    def setUp(self):
        self.mock_model = MagicMock()
        self.mock_model.FirstFeature = None
        self.mock_model.GetBodies2.return_value = [1]
        self.mock_dim = MagicMock()
        self.mock_dim.SystemValue = 0.1  # 100mm
        self.mock_dim.DrivenState = 0
        self.mock_dim.SetSystemValue3.return_value = 0  # 成功

        self.mock_model.Parameter.return_value = self.mock_dim
        self.mock_model.EditRebuild3.return_value = True

    def test_successful_modify(self):
        modifier = DimensionModifier(self.mock_model, auto_rollback=True)
        res = modifier.modify_single("D1@Sketch1", 150.0)

        self.assertTrue(res.success)
        self.assertIn(res.status, ("SUCCESS", "COMPLETED"))
        self.assertEqual(res.modified_count, 1)
        # 验证调用了 SetSystemValue3(0.15, 1, None)
        self.mock_dim.SetSystemValue3.assert_called_with(0.15, 1, None)

    def test_rollback_on_rebuild_failure(self):
        # 模拟重建失败
        self.mock_model.EditRebuild3.side_effect = [False, True]  # 第一次修改后失败，第二次恢复时成功

        modifier = DimensionModifier(self.mock_model, auto_rollback=True)
        res = modifier.modify_single("D1@Sketch1", 200.0)

        self.assertFalse(res.success)
        self.assertIn(res.status, ("ROLLBACK_SUCCESS", "ROLLED_BACK"))
        self.assertTrue(res.rollback_occurred)
        # 验证逆向回滚调用了原始值 0.1m
        self.mock_dim.SetSystemValue3.assert_called_with(0.1, 1, None)

    def test_rollback_partial_and_failed_states(self):
        # 1. 模拟参数还原成功但重构失败 -> ROLLBACK_PARTIAL
        modifier = DimensionModifier(self.mock_model, auto_rollback=True)
        self.mock_model.EditRebuild3.side_effect = [False, False]
        res_partial = modifier.modify_single("D1@Sketch1", 999.0)
        self.assertFalse(res_partial.success)
        self.assertEqual(res_partial.status, "ROLLBACK_PARTIAL")

        # 2. 模拟参数还原自身崩溃报错 -> ROLLBACK_FAILED
        self.mock_dim.SetSystemValue3.side_effect = [0, RuntimeError("COM write error")]
        res_failed = modifier.modify_single("D1@Sketch1", 888.0)
        self.assertFalse(res_failed.success)
        self.assertEqual(res_failed.status, "ROLLBACK_FAILED")


class TestDimensionValidator(unittest.TestCase):
    """测试尺寸修改前后对比核验器。"""

    def test_validation_all_pass(self):
        b_ir = DimensionModelIR()
        b_ir.add_dimension(DimensionIRNode.create("D1@S1", 0.10, "S1"))
        b_ir.add_dimension(DimensionIRNode.create("D2@S1", 0.05, "S1"))

        a_ir = DimensionModelIR()
        a_ir.add_dimension(DimensionIRNode.create("D1@S1", 0.15, "S1"))  # 目标改变
        a_ir.add_dimension(DimensionIRNode.create("D2@S1", 0.05, "S1"))  # 非目标保持

        reb_before = RebuildReport(success=True, status="CLEAN", volume_mm3=10000.0)
        reb_after = RebuildReport(success=True, status="CLEAN", volume_mm3=15000.0)

        report = DimensionValidator.validate(
            before_ir=b_ir,
            after_ir=a_ir,
            target_updates={"D1@S1": 150.0},
            rebuild_before=reb_before,
            rebuild_after=reb_after,
        )

        self.assertTrue(report.passed)
        self.assertEqual(len(report.target_checks), 1)
        self.assertTrue(report.target_checks[0].passed)
        self.assertEqual(report.volume_delta_mm3, 5000.0)


if __name__ == "__main__":
    unittest.main()
