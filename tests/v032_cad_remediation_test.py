import json
import math
import os
import sys
import unittest
from unittest.mock import MagicMock

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(REPO, "vendor", "solidworks-automation-skill", "scripts")
MCP_DIR = os.path.join(REPO, "vendor", "solidworks-automation-skill", "mcp-server")
for d in (SCRIPTS_DIR, MCP_DIR):
    if d not in sys.path:
        sys.path.insert(0, d)

import sw_part
import sw_assembly
import server


class _FakeVariant:
    def __init__(self, _t, val):
        self.value = val


class _FakeFeature:
    def __init__(self, name, type_name="BaseBody", next_feat=None, first_sub=None):
        self.Name = name
        self._type_name = type_name
        self._next = next_feat
        self._first_sub = first_sub

    def GetTypeName2(self):
        return self._type_name

    def GetNextFeature(self):
        return self._next

    def GetFirstSubFeature(self):
        return self._first_sub


class V032CadRemediationTests(unittest.TestCase):
    def test_01_shell_uses_imodeldoc2_not_featuremanager_and_checks_faces(self):
        """D-01: 依据 sldworks.tlb 实证，InsertFeatureShell 位于 IModelDoc2 上，而非 IFeatureManager。"""
        # 构造没有 FeatureManager.InsertFeatureShell、仅在 model 上暴露 InsertFeatureShell 的真实接口形态
        f_shell = _FakeFeature("抽壳1", "Shell")
        f_boss = _FakeFeature("凸台-拉伸1", "Extrusion", next_feat=f_shell)

        class ModelDoc2OnlyShell:
            def __init__(self):
                self.Extension = MagicMock()
                self.Extension.SelectByID2.return_value = True
                self.FeatureManager = object()  # 故意无 InsertFeatureShell
                self.calls = []
                self._created = False

            def ClearSelection2(self, _all):
                return True

            def FirstFeature(self):
                return f_boss if not self._created else f_boss

            def FeatureByName(self, name):
                return f_shell if name == "抽壳1" else None

            def InsertFeatureShell(self, thickness, outward):
                self.calls.append((thickness, outward))
                self._created = True
                return True

        m = ModelDoc2OnlyShell()
        # 第一次调用前特征树只有 f_boss；为了模拟抽壳后多出 f_shell，覆盖 FirstFeature
        seq = [0]
        def first_feat():
            seq[0] += 1
            if seq[0] == 1:
                return _FakeFeature("凸台-拉伸1", "Extrusion", None)
            return f_boss
        m.FirstFeature = first_feat

        res = sw_part.shell(m, 0.002, faces_to_remove="TopFace")
        self.assertEqual(m.calls, [(0.002, False)])
        self.assertIs(res, f_shell)

    def test_02_shell_rejects_invalid_thickness_and_unselected_face(self):
        m = MagicMock()
        m.Extension.SelectByID2.return_value = False
        with self.assertRaises(ValueError):
            sw_part.shell(m, 0.0)
        with self.assertRaises(ValueError):
            sw_part.shell(m, -0.002)
        with self.assertRaises(ValueError):
            sw_part.shell(m, float("nan"))
        with self.assertRaises(ValueError):
            sw_part.shell(m, 0.002, faces_to_remove="NonExistentFace")

    def test_03_shell_returns_none_when_insert_returns_false(self):
        class FailShellModel:
            def ClearSelection2(self, _):
                return True
            def InsertFeatureShell(self, _t, _o):
                return False

        self.assertIsNone(sw_part.shell(FailShellModel(), 0.002))

    def test_03b_shell_vt_void_none_requires_feature_tree_growth(self):
        """D-04: sldworks.tlb 中 InsertFeatureShell 返回 VT_VOID(None)，仅特征树确有新增才成功。"""
        f_shell = _FakeFeature("抽壳1", "Shell")
        f_boss_only = _FakeFeature("凸台-拉伸1", "Extrusion", None)
        f_boss_and_shell = _FakeFeature("凸台-拉伸1", "Extrusion", next_feat=f_shell)

        class VtVoidShellModel:
            def __init__(self, grow: bool):
                self.grow = grow
                self.rebuilt = False
                self._after_insert = False

            def ClearSelection2(self, _):
                return True

            def EditRebuild3(self):
                self.rebuilt = True
                return True

            def FirstFeature(self):
                if self._after_insert and self.grow:
                    return f_boss_and_shell
                return f_boss_only

            def FeatureByName(self, name):
                return f_shell if (self.grow and name == "抽壳1") else None

            def InsertFeatureShell(self, _t, _o):
                self._after_insert = True
                return None  # COM VT_VOID

        ok_model = VtVoidShellModel(grow=True)
        res_ok = sw_part.shell(ok_model, 0.002)
        self.assertTrue(ok_model.rebuilt)
        self.assertIs(res_ok, f_shell)

        fail_model = VtVoidShellModel(grow=False)
        res_fail = sw_part.shell(fail_model, 0.025)
        self.assertTrue(fail_model.rebuilt)
        self.assertIsNone(res_fail)

    def test_04_add_mate5_checked_blocks_suspect_false_success_when_tree_unchanged(self):
        """D-02/D-03: 当 AddMate5 返回非空代理但特征树 MateGroup 数量未增加时，禁止假成功。"""
        orig_variant = sw_assembly.VARIANT
        orig_safe_mate = sw_assembly.safe_add_mate
        try:
            sw_assembly.VARIANT = _FakeVariant
            sw_assembly.safe_add_mate = None
            mate_group = _FakeFeature("配合", "MateGroup", None, None)

            class _FakeAsm:
                def FirstFeature(self):
                    return mate_group

                def AddMate5(self, *_args):
                    return MagicMock(Name="PhantomMate")

                def ClearSelection2(self, _flag):
                    return True

            asm = _FakeAsm()
            with self.assertRaises(RuntimeError) as ctx:
                sw_assembly.add_mate5_checked(asm, sw_assembly.SW_MATE_DISTANCE, distance=0.01)
            self.assertIn("疑似假成功", str(ctx.exception))
        finally:
            sw_assembly.VARIANT = orig_variant
            sw_assembly.safe_add_mate = orig_safe_mate

    def test_05_server_mate_delta_payload_detects_no_new_mate(self):
        before = [{"name": "配合", "type": "MateGroup", "depth": 0}, {"name": "重合1", "type": "MateCoincident", "depth": 1}]
        after_same = list(before)
        after_added = list(before) + [{"name": "距离1", "type": "MateDistanceDim", "depth": 1}]
        self.assertEqual(server._mate_delta_payload(before, after_same), [])
        self.assertEqual(server._mate_delta_payload(before, after_added), ["距离1"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
