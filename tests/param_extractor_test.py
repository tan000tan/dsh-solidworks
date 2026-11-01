# -*- coding: utf-8 -*-
"""
tests/param_extractor_test.py
参数提取与意图解析器单元测试套件。
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from sw_param_extractor import extract_cad_parameters, normalize_dimension


class ParamExtractorTest(unittest.TestCase):

    def test_normalize_dimension(self):
        # 毫米
        self.assertEqual(normalize_dimension(100, "mm"), 100.0)
        # 厘米
        self.assertEqual(normalize_dimension(5, "cm"), 50.0)
        # 米
        self.assertEqual(normalize_dimension(0.02, "m"), 20.0)
        # 英寸
        self.assertEqual(normalize_dimension(2, "in"), 50.8)

    def test_dict_extraction_complete(self):
        # 完整参数输入
        data = {
            "length": 120,
            "width": 80,
            "thickness": 10,
            "hole_diameter": 15,
            "units": "mm",
        }
        res = extract_cad_parameters(data)
        self.assertTrue(res.is_executable)
        self.assertEqual(len(res.missing_critical_params), 0)
        self.assertEqual(len(res.clarification_questions), 0)
        self.assertEqual(res.parameters["length_mm"], 120.0)
        self.assertEqual(res.parameters["width_mm"], 80.0)
        self.assertEqual(res.parameters["thickness_mm"], 10.0)
        self.assertEqual(res.parameters["hole_diameter_mm"], 15.0)

        # 校验编译出的 DesignSpec
        spec = res.compiled_spec
        self.assertIsNotNone(spec)
        self.assertEqual(spec["base"]["width"], 120.0)
        self.assertEqual(spec["base"]["height"], 80.0)
        self.assertEqual(spec["holes"][0]["diameter"], 15.0)

    def test_natural_language_extraction(self):
        # 文本正则提取: "100x60x20mm 直径20mm"
        text = "设计一个 100x60x20mm 的基准块，中间开一个直径20mm的通孔"
        res = extract_cad_parameters(text)
        self.assertTrue(res.is_executable)
        self.assertEqual(res.parameters["length_mm"], 100.0)
        self.assertEqual(res.parameters["width_mm"], 60.0)
        self.assertEqual(res.parameters["thickness_mm"], 20.0)
        self.assertEqual(res.parameters["hole_diameter_mm"], 20.0)

    def test_missing_critical_parameters_triggers_clarification(self):
        # 故意缺失厚度和孔径，测试歧义反问机制（绝不瞎猜）
        text = "帮我建一个 100x60 的零件，上面打个孔"
        res = extract_cad_parameters(text)
        self.assertFalse(res.is_executable)
        self.assertIn("thickness_mm", res.missing_critical_params)
        self.assertIn("hole_diameter_mm", res.missing_critical_params)
        self.assertTrue(len(res.clarification_questions) >= 2)
        # 确认包含了要求用户明确厚度与孔径的提问
        q_str = " ".join(res.clarification_questions)
        self.assertIn("Thickness", q_str)
        self.assertIn("Hole Diameter", q_str)

    def test_geometry_interference_check(self):
        # 孔径 120mm 大于板宽度 60mm，触发物理干涉报错
        data = {
            "length": 100,
            "width": 60,
            "thickness": 20,
            "hole_diameter": 120,
        }
        res = extract_cad_parameters(data)
        self.assertFalse(res.is_executable)
        self.assertTrue(len(res.ambiguities) > 0)
        self.assertTrue(len(res.clarification_questions) > 0)


if __name__ == "__main__":
    unittest.main()
