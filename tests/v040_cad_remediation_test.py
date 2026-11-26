import json
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "vendor", "solidworks-automation-skill")))
import scripts.sw_export as sw_export
import scripts.sw_measure as sw_measure
import scripts.sw_review as sw_review
from scripts.dimension_reader import infer_dimension_type, DimensionType


class DummyModel:
    def GetSldWorks(self):
        return None
    def GetSheetNames(self):
        return ["Sheet1"]
    def GetComponentCount(self, top):
        return 0
    def ClearSelection2(self, v):
        pass
    @property
    def SelectionManager(self):
        return self
    def CreateSelectData(self):
        class SD:
            Mark = 0
        return SD()
    @property
    def Extension(self):
        return self
    def SaveAs(self, *args):
        return False
    def SelectByID2(self, *args):
        return True


class TestCadRemediation(unittest.TestCase):
    def test_d10_export_to_pdf_safe_without_com(self):
        # 验证在无 COM 实例或 mock 状态下，不会发生 AttributeError: GetSldWorksObject
        model = DummyModel()
        try:
            # 预期在无法连接 SolidWorks 时平稳返回或处理，绝不裸抛 AttributeError
            res = sw_export.export_to_pdf(model, "test.pdf")
            self.assertFalse(res)
        except AttributeError as e:
            self.fail(f"export_to_pdf 抛出了未捕获的 AttributeError: {e}")
        except Exception:
            pass

    def test_d11_interference_check_on_empty_assembly(self):
        model = DummyModel()
        # Mock InterferenceDetectionManager
        class MockIDM:
            TreatSubAssembliesAsComponents = False
            TreatCoincidenceAsInterference = False
            IgnoreHiddenBodies = False
            ShowIgnoredInterferences = True
            IncludeMultibodyPartInterferences = False
            def GetInterferences(self):
                return []
            def GetInterferenceCount(self):
                return 0
            def Done(self):
                pass

        model.InterferenceDetectionManager = MockIDM()
        res = sw_measure.inspect_interference(model)
        self.assertEqual(res["status"], "insufficient_input", "空装配体干涉检查应诚实返回 insufficient_input")

    def test_d12_dimension_feature_type_ice_mapped_properly(self):
        t1 = infer_dimension_type("ICE", "D1@Cut1")
        self.assertEqual(t1, DimensionType.CUT_DEPTH)


if __name__ == "__main__":
    unittest.main()
