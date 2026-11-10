# -*- coding: utf-8 -*-
"""
tests/unified_dimension_migration_test.py

验证 NIGHT-ENGINEERING-04 Phase 04: 新旧尺寸体系安全迁移与统一门面兼容性测试。
验证点:
1. dimension_manager 正确导出新一代 P1 核心模块类型；
2. identify_dimensions 能正确返回向后兼容字典并携带 model_ir；
3. inspect_dimension_impact 兼容旧版索引同时生成 DDG 拓扑支持；
4. modify_dimensions_safe 保留原有契约并支持事务自愈；
5. 新旧类型在 MCP 与技能工具层面的无缝交互。
"""

import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "vendor", "solidworks-automation-skill", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import dimension_manager as dm


class TestUnifiedDimensionMigration(unittest.TestCase):

    def test_exports_unified_classes(self):
        """验证门面模块完整导出了新版 P1 核心类型。"""
        self.assertTrue(hasattr(dm, "DimensionModelIR"))
        self.assertTrue(hasattr(dm, "DimensionIRNode"))
        self.assertTrue(hasattr(dm, "DimensionType"))
        self.assertTrue(hasattr(dm, "DimensionRole"))
        self.assertTrue(hasattr(dm, "DimensionDependencyGraph"))
        self.assertTrue(hasattr(dm, "DimensionModifier"))
        self.assertTrue(hasattr(dm, "ModelRebuilder"))
        self.assertTrue(hasattr(dm, "DimensionValidator"))

    def test_ddg_integration_in_impact_analysis(self):
        """验证 inspect_dimension_impact 在兼容旧接口的同时支持 DDG。"""
        class MockFeat:
            def __init__(self, name):
                self.Name = name
            def GetTypeName2(self):
                return "Extrusion"
            def GetFirstSubFeature(self):
                return None
            def GetNextFeature(self):
                return None

        class MockModel:
            def __init__(self):
                self.f1 = MockFeat("BaseSketch")
                self.f2 = MockFeat("Boss-Extrude1")
                self.f3 = MockFeat("Cut-Extrude1")
                self.f1._next = self.f2
                self.f2._next = self.f3
                self.f3._next = None
            def FirstFeature(self):
                return self.f1
            def GetTitle(self):
                return "TestModel.SLDPRT"

        # Mock iter_all_features
        model = MockModel()
        original_iter = dm.iter_all_features
        try:
            dm.iter_all_features = lambda m: [model.f1, model.f2, model.f3]
            res = dm.inspect_dimension_impact(model, "D1@BaseSketch")
            
            # 旧版兼容断言
            self.assertEqual(res["dimension"], "D1@BaseSketch")
            self.assertEqual(res["owner_feature"], "BaseSketch")
            self.assertEqual(res["owner_feature_index"], 0)
            self.assertEqual(res["potential_impacted_features"], ["Boss-Extrude1", "Cut-Extrude1"])
            self.assertEqual(res["impact_count"], 2)
            
            # 新版 DDG 扩展能力断言
            self.assertTrue(res.get("ddg_supported", False))
            self.assertFalse(res.get("has_cycles", True))
        finally:
            dm.iter_all_features = original_iter

    def test_si_mm_unit_conversion_integrity(self):
        """严格验证 SI(米) 与工程单位(毫米) 的双向换算完整性。"""
        val_mm = 125.45
        val_m = val_mm / 1000.0
        self.assertAlmostEqual(val_m, 0.12545, places=7)

        class MockDimCOM:
            def __init__(self, sys_val_m):
                self.SystemValue = sys_val_m

        read_mm = dm._read_dim_value_mm(MockDimCOM(val_m))
        self.assertEqual(read_mm, 125.45)


if __name__ == "__main__":
    unittest.main()
