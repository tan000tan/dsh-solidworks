# -*- coding: utf-8 -*-
"""
tests/dimension_manager_test.py

针对 TASK-05: 尺寸参数识别、修改和依赖更新能力与影子备份自动回滚的完整单元测试。
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "vendor", "solidworks-automation-skill", "scripts")
MCP_SERVER_DIR = os.path.join(REPO_ROOT, "vendor", "solidworks-automation-skill", "mcp-server")
for p in (SCRIPTS_DIR, MCP_SERVER_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from dimension_manager import (
    DimensionUpdateError,
    identify_dimensions,
    inspect_dimension_impact,
    modify_dimensions_safe,
)
from server import (
    SolidWorksIdentifyDimensionsInput,
    SolidWorksDimensionImpactInput,
    SolidWorksSafeDimensionUpdateInput,
    solidworks_identify_dimensions,
    solidworks_inspect_dimension_impact,
    solidworks_modify_dimension_safe,
)


class MockDimension:
    def __init__(self, name: str, full_name: str, value_m: float, driven: int = 0):
        self.Name = name
        self.FullName = full_name
        self.SystemValue = value_m
        self.DrivenState = driven

    def SetSystemValue3(self, val_m, mode, config_names):
        self.SystemValue = val_m
        return 0


class MockDisplayDimension:
    def __init__(self, dim: MockDimension):
        self._dim = dim

    def GetDimension2(self, index=0):
        return self._dim

    def GetDimension(self):
        return self._dim


class MockFeature:
    def __init__(self, name: str, type_name: str, dims=None, sub_features=None):
        self.Name = name
        self._type_name = type_name
        self._dims = dims or []
        self._sub_features = sub_features or []
        self._next_feature = None
        self._next_sub = None

    def GetTypeName2(self):
        return self._type_name

    def GetFirstDisplayDimension(self):
        return MockDisplayDimension(self._dims[0]) if self._dims else None

    def GetNextDisplayDimension(self, curr_disp):
        for i, d in enumerate(self._dims):
            if MockDisplayDimension(d).GetDimension2() == curr_disp.GetDimension2():
                if i + 1 < len(self._dims):
                    return MockDisplayDimension(self._dims[i + 1])
        return None

    def GetFirstSubFeature(self):
        return self._sub_features[0] if self._sub_features else None

    def GetNextSubFeature(self, curr):
        for i, f in enumerate(self._sub_features):
            if f == curr and i + 1 < len(self._sub_features):
                return self._sub_features[i + 1]
        return None

    def GetNextFeature(self):
        return self._next_feature


class MockModelDoc:
    def __init__(self, features, title="MockPart.SLDPRT"):
        self._features = features
        self._title = title
        self.rebuild_should_succeed = True
        self.param_dict = {}

        # 链表化 top features
        for i in range(len(features) - 1):
            features[i]._next_feature = features[i + 1]

        # 缓存参数
        for feat in features:
            for d in feat._dims:
                self.param_dict[d.FullName] = d
                self.param_dict[d.Name] = d

    def FirstFeature(self):
        return self._features[0] if self._features else None

    def Parameter(self, name):
        return self.param_dict.get(name)

    def EditRebuild3(self):
        return 1 if self.rebuild_should_succeed else 0

    def GetTitle(self):
        return self._title

    def GetApplication(self):
        return None


class TestDimensionManager(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_sw_dim_")
        self.dim1 = MockDimension("D1", "D1@Sketch1", 0.100, 0)  # 100 mm
        self.dim2 = MockDimension("D2", "D2@Sketch1", 0.060, 0)  # 60 mm
        self.dim3 = MockDimension("D1", "D1@Boss-Extrude1", 0.020, 0)  # 20 mm

        self.f1 = MockFeature("Sketch1", "ProfileFeature", [self.dim1, self.dim2])
        self.f2 = MockFeature("Boss-Extrude1", "Extrusion", [self.dim3])
        self.model = MockModelDoc([self.f1, self.f2])

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_identify_dimensions(self):
        """测试自动枚举与识别模型中的特征及草图尺寸。"""
        result = identify_dimensions(self.model)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["count"], 3)

        dim_names = [d["full_name"] for d in result["dimensions"]]
        self.assertIn("D1@Sketch1", dim_names)
        self.assertIn("D2@Sketch1", dim_names)
        self.assertIn("D1@Boss-Extrude1", dim_names)

        # 校验尺寸数值换算为毫米
        d1 = result["dimension_map"]["D1@Sketch1"]
        self.assertEqual(d1["value_mm"], 100.0)
        self.assertEqual(d1["feature_name"], "Sketch1")

        d3 = result["dimension_map"]["D1@Boss-Extrude1"]
        self.assertEqual(d3["value_mm"], 20.0)
        self.assertEqual(d3["feature_name"], "Boss-Extrude1")

    def test_inspect_dimension_impact(self):
        """测试评估尺寸修改对下游特征链的影响面。"""
        # 修改 Sketch1 的尺寸，下游 Boss-Extrude1 应该在影响列表中
        impact = inspect_dimension_impact(self.model, "D1@Sketch1")
        self.assertEqual(impact["dimension"], "D1@Sketch1")
        self.assertEqual(impact["owner_feature"], "Sketch1")
        self.assertEqual(impact["owner_feature_index"], 0)
        self.assertEqual(impact["potential_impacted_features"], ["Boss-Extrude1"])
        self.assertEqual(impact["impact_count"], 1)

        # 修改 Boss-Extrude1 的尺寸，它是最后一个特征，下游影响应为空
        impact_last = inspect_dimension_impact(self.model, "D1@Boss-Extrude1")
        self.assertEqual(impact_last["potential_impacted_features"], [])
        self.assertEqual(impact_last["impact_count"], 0)

    def test_modify_dimensions_safe_success(self):
        """测试安全事务性尺寸修改成功流程（含影子备份创建与自动销毁）。"""
        part_path = os.path.join(self.test_dir, "bracket.SLDPRT")
        with open(part_path, "wb") as f:
            f.write(b"ORIGINAL_VALID_MODEL_DATA_VERSION_1")

        updates = {"D1@Sketch1": 150.0, "D1@Boss-Extrude1": 35.0}
        res = modify_dimensions_safe(
            self.model,
            updates,
            doc_path=part_path,
            auto_rollback=True,
            rebuild=True,
            save=False,
        )

        self.assertEqual(res["status"], "success")
        self.assertTrue(res["rebuild_success"])
        self.assertEqual(res["modified_count"], 2)
        self.assertEqual(res["after_values_mm"]["D1@Sketch1"], 150.0)
        self.assertEqual(res["after_values_mm"]["D1@Boss-Extrude1"], 35.0)

        # 检查原文件依然保留，且影子备份已被成功销毁清理
        self.assertTrue(os.path.exists(part_path))
        from shadow_backup import ShadowBackupManager
        mgr = ShadowBackupManager()
        self.assertFalse(mgr.is_protected(part_path))

    def test_modify_dimensions_safe_rollback_on_rebuild_error(self):
        """测试当尺寸修改引发几何崩溃或重构错误时，影子备份自动无损回滚。"""
        part_path = os.path.join(self.test_dir, "flange.SLDPRT")
        original_content = b"PRECIOUS_ORIGINAL_FLANGE_DATA"
        with open(part_path, "wb") as f:
            f.write(original_content)

        # 模拟重构失败 (例如尺寸过大导致几何自交)
        self.model.rebuild_should_succeed = False

        updates = {"D1@Sketch1": 9999.0}
        with self.assertRaises(DimensionUpdateError) as ctx:
            modify_dimensions_safe(
                self.model,
                updates,
                doc_path=part_path,
                auto_rollback=True,
                rebuild=True,
                save=False,
            )

        err_msg = str(ctx.exception)
        self.assertIn("EditRebuild3 重建失败", err_msg)
        self.assertIn("已自动从影子备份无损还原", err_msg)

        # 验证文件内容是否被无损还原回原始数据！
        with open(part_path, "rb") as f:
            restored_content = f.read()
        self.assertEqual(restored_content, original_content)

    def test_server_mcp_tools(self):
        """测试在 FastMCP 工具层面的尺寸识别、影响面评估与安全修改端到端封装。"""
        import unittest.mock as mock

        with mock.patch("server._active_model_required", return_value=(None, self.model)), \
             mock.patch("server._model_summary", return_value={"name": "MockPart.SLDPRT"}):

            # 1. 测试尺寸识别工具
            res_json = json.loads(solidworks_identify_dimensions(SolidWorksIdentifyDimensionsInput()))
            self.assertEqual(res_json["status"], "success")
            self.assertEqual(res_json["count"], 3)

            # 2. 测试指定特征过滤
            res_filtered = json.loads(solidworks_identify_dimensions(
                SolidWorksIdentifyDimensionsInput(feature_name="Sketch1")
            ))
            self.assertEqual(res_filtered["count"], 2)

            # 3. 测试影响面评估工具
            res_impact = json.loads(solidworks_inspect_dimension_impact(
                SolidWorksDimensionImpactInput(dimension_name="D1@Sketch1")
            ))
            self.assertEqual(res_impact["owner_feature"], "Sketch1")
            self.assertIn("Boss-Extrude1", res_impact["potential_impacted_features"])

            # 4. 测试安全修改工具
            part_path = os.path.join(self.test_dir, "mcp_test_part.SLDPRT")
            with open(part_path, "wb") as f:
                f.write(b"ORIGINAL_MCP_MODEL_DATA")

            with mock.patch.object(self.model, "GetPathName", return_value=part_path, create=True):
                res_mod = json.loads(solidworks_modify_dimension_safe(
                    SolidWorksSafeDimensionUpdateInput(updates={"D1@Sketch1": 120.0})
                ))
                self.assertEqual(res_mod["status"], "success")
                self.assertEqual(res_mod["after_values_mm"]["D1@Sketch1"], 120.0)


if __name__ == "__main__":
    unittest.main()
