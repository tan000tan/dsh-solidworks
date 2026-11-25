import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(REPO, "vendor", "solidworks-automation-skill", "scripts")
MCP_DIR = os.path.join(REPO, "vendor", "solidworks-automation-skill", "mcp-server")
for d in (SCRIPTS_DIR, MCP_DIR):
    if d not in sys.path:
        sys.path.insert(0, d)

import server
import sw_assembly
import sw_connect
import sw_part


class _DummyDoc:
    def __init__(self, title: str, path_name: str):
        self._title = title
        self._path = path_name

    def GetTitle(self):
        return self._title

    def GetPathName(self):
        return self._path

    def GetType(self):
        return 2 if self._path.lower().endswith(".sldasm") else 1


class _FakeFeature:
    def __init__(self, name, type_name="BaseBody", next_feat=None):
        self.Name = name
        self._type_name = type_name
        self._next = next_feat

    def GetTypeName2(self):
        return self._type_name

    def GetNextFeature(self):
        return self._next

    def GetFirstSubFeature(self):
        return None


class V033RemediationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._prev_roots = os.environ.get("DSH_ALLOWED_ROOTS")
        self._prev_mode = os.environ.get("DSH_POLICY_MODE")
        self._prev_launch = os.environ.get("DSH_ALLOW_LAUNCH_SW")
        os.environ["DSH_ALLOWED_ROOTS"] = self.tmp.name
        sw_connect._SESSION_OWNED_DOCUMENTS.clear()
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        sw_connect._SESSION_OWNED_DOCUMENTS.clear()
        for key, prev in (
            ("DSH_ALLOWED_ROOTS", self._prev_roots),
            ("DSH_POLICY_MODE", self._prev_mode),
            ("DSH_ALLOW_LAUNCH_SW", self._prev_launch),
        ):
            if prev is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prev

    def test_d01_connect_and_health_check_launch_policy(self):
        captured = []

        def fake_connect(**kwargs):
            captured.append(kwargs)
            return object(), None

        with mock.patch.object(server, "_load_automation_modules", lambda: None), \
             mock.patch.object(server, "connect_solidworks", fake_connect, create=True), \
             mock.patch.object(server, "get_com_member", lambda obj, name, default=None: "34.4.1" if name == "RevisionNumber" else default, create=True):
            # 1. read-only mode forces allow_launch=False even with start_if_needed=True
            os.environ["DSH_POLICY_MODE"] = "read-only"
            os.environ["DSH_ALLOW_LAUNCH_SW"] = "1"
            res_ro = json.loads(server.solidworks_connect(server.SolidWorksConnectInput(wait_seconds=10, start_if_needed=True)))
            self.assertEqual(res_ro["status"], "ok")
            self.assertEqual(captured[-1]["allow_launch"], False)

            # 2. standard mode with DSH_ALLOW_LAUNCH_SW=1 passes allow_launch=True when start_if_needed=True
            os.environ["DSH_POLICY_MODE"] = "standard"
            os.environ["DSH_ALLOW_LAUNCH_SW"] = "1"
            res_std = json.loads(server.solidworks_connect(server.SolidWorksConnectInput(wait_seconds=12, start_if_needed=True)))
            self.assertEqual(res_std["status"], "ok")
            self.assertEqual(captured[-1]["allow_launch"], True)
            self.assertEqual(captured[-1]["wait_seconds"], 12)

            # 3. standard mode with start_if_needed=False respects opt-out
            server.solidworks_connect(server.SolidWorksConnectInput(wait_seconds=7, start_if_needed=False))
            self.assertEqual(captured[-1]["allow_launch"], False)

            # 4. solidworks_health_check passes allow_launch=True after gate passes
            with mock.patch.object(server, "missing_com_dependencies", return_value=[]), \
                 mock.patch.object(server, "solidworks_installed", return_value=True), \
                 mock.patch.object(server, "ensure_motion_type_library", return_value=None, create=True):
                res_hc = json.loads(server.solidworks_health_check(server.SolidWorksHealthCheckInput(start_solidworks=True, check_motion_type_library=False)))
                self.assertEqual(res_hc["checks"]["solidworks_revision"], "34.4.1")
                self.assertEqual(captured[-1]["allow_launch"], True)
                self.assertEqual(captured[-1]["wait_seconds"], 15)

                os.environ["DSH_POLICY_MODE"] = "read-only"
                res_hc_ro = json.loads(server.solidworks_health_check(server.SolidWorksHealthCheckInput(start_solidworks=True, check_motion_type_library=False)))
                self.assertEqual(res_hc_ro["status"], "error")
                self.assertIn("POLICY_MODE", str(res_hc_ro.get("message") or res_hc_ro))

    def test_d02_open_document_activates_reused_and_opened_models(self):
        part_a = Path(self.tmp.name) / "part_a.SLDPRT"
        part_b = Path(self.tmp.name) / "part_b.SLDPRT"
        part_a.write_bytes(b"a")
        part_b.write_bytes(b"b")

        doc_a = _DummyDoc("part_a.SLDPRT", str(part_a))
        doc_b = _DummyDoc("part_b.SLDPRT", str(part_b))

        class _FakeSw:
            def __init__(self):
                self.ActiveDoc = doc_b
                self.activated_titles = []

            def GetOpenDocumentByName(self, path_str):
                if os.path.normcase(path_str) == os.path.normcase(str(part_a)):
                    return doc_a
                return None

            def OpenDoc6(self, path_str, *_args):
                if os.path.normcase(path_str) == os.path.normcase(str(part_b)):
                    return doc_b
                return None

            def ActivateDoc3(self, title, _use_prefs, _option, _errors):
                self.activated_titles.append(title)
                if title == "part_a.SLDPRT":
                    self.ActiveDoc = doc_a
                    return doc_a
                if title == "part_b.SLDPRT":
                    self.ActiveDoc = doc_b
                    return doc_b
                return None

        sw = _FakeSw()
        reused = sw_connect.open_document(sw, str(part_a), read_only=False, raise_on_error=True, activate=True)
        self.assertIs(reused, doc_a)
        self.assertIs(sw.ActiveDoc, doc_a)
        self.assertIn("part_a.SLDPRT", sw.activated_titles)

        opened = sw_connect.open_document(sw, str(part_b), read_only=False, raise_on_error=True, activate=False)
        self.assertIs(opened, doc_b)
        self.assertIs(sw.ActiveDoc, doc_a, "activate=False must not steal ActiveDoc focus")

    def test_d03a_add_component_and_mates_register_ownership_and_reactivate_asm(self):
        asm_path = Path(self.tmp.name) / "asm_test.SLDASM"
        part_path = Path(self.tmp.name) / "comp_a.SLDPRT"
        asm_path.write_bytes(b"asm")
        part_path.write_bytes(b"part")

        asm_doc = _DummyDoc("asm_test.SLDASM", str(asm_path))
        comp_doc = _DummyDoc("comp_a.SLDPRT", str(part_path))
        fake_sw = object()
        fake_component = mock.MagicMock()

        activated = []

        def fake_activate(sw_obj, model_obj):
            activated.append(model_obj)
            return True

        with mock.patch.object(server, "_active_assembly_required", return_value=(fake_sw, asm_doc)), \
             mock.patch.object(server, "assembly_add_component", return_value=fake_component, create=True), \
             mock.patch.object(server, "resolve_component", lambda _c: None, create=True), \
             mock.patch.object(server, "activate_document", fake_activate, create=True), \
             mock.patch.object(server, "register_owned_document", sw_connect.register_owned_document, create=True), \
             mock.patch.object(server, "validate_path_against_allowed_roots", sw_connect.validate_path_against_allowed_roots, create=True), \
             mock.patch.object(server, "_expand_path", sw_connect._expand_path, create=True), \
             mock.patch.object(server, "_component_summary", lambda _c: {"name": "comp_a-1"}, create=True), \
             mock.patch.object(server, "get_components", lambda _a: [fake_component], create=True), \
             mock.patch.object(server, "_model_summary", lambda m: {"title": m.GetTitle()}, create=True), \
             mock.patch.object(server, "get_com_member", lambda obj, name, default=None: comp_doc if name == "GetModelDoc2" else (str(part_path) if obj is comp_doc and name == "GetPathName" else "comp_a-1"), create=True):
            res = json.loads(server.solidworks_add_component(server.SolidWorksAddComponentInput(path=str(part_path), fix_component=False)))
            self.assertEqual(res["status"], "ok")
            self.assertTrue(sw_connect.is_document_owned(comp_doc), "component added inside allowed_roots must be owned")
            self.assertEqual(activated, [asm_doc], "parent assembly must be re-activated after add_component")

        activated.clear()
        with mock.patch.object(server, "_active_assembly_required", return_value=(fake_sw, asm_doc)), \
             mock.patch.object(server, "find_component_by_name", lambda _a, kw: _DummyDoc(kw, ""), create=True), \
             mock.patch.object(server, "get_component_feature_entity", lambda _c, f: f, create=True), \
             mock.patch.object(server, "collect_mate_feature_summary", side_effect=[[], [{"name": "m1"}], [], [{"name": "m2"}], [], [{"name": "m3"}]], create=True), \
             mock.patch.object(server, "select_entities_for_mate", lambda *_a, **_k: True, create=True), \
             mock.patch.object(server, "add_mate5_checked", return_value=mock.MagicMock(Name="m"), create=True), \
             mock.patch.object(server, "add_concentric_mate_by_cylinders", return_value=mock.MagicMock(Name="m3"), create=True), \
             mock.patch.object(server, "activate_document", fake_activate, create=True), \
             mock.patch.object(server, "_model_summary", lambda m: {"title": m.GetTitle()}, create=True), \
             mock.patch.object(server, "get_com_member", lambda obj, name, default=None: "comp" if name == "Name2" else "m", create=True):
            r_c = json.loads(server.solidworks_add_coincident_mate(server.SolidWorksPlaneCoincidentMateInput(component_a_keyword="a", component_b_keyword="b", feature_a_name="Front Plane", feature_b_name="Front Plane")))
            r_d = json.loads(server.solidworks_add_distance_mate(server.SolidWorksPlaneDistanceMateInput(component_a_keyword="a", component_b_keyword="b", feature_a_name="Front Plane", feature_b_name="Front Plane", distance_mm=10.0)))
            r_o = json.loads(server.solidworks_add_concentric_mate(server.SolidWorksConcentricMateInput(component_a_keyword="a", component_b_keyword="b")))
            self.assertEqual(r_c["status"], "ok")
            self.assertEqual(r_d["status"], "ok")
            self.assertEqual(r_o["status"], "ok")
            self.assertEqual(activated, [asm_doc, asm_doc, asm_doc])

    def test_d04_solidworks_shell_tool_accepts_vt_void_and_rejects_unchanged_tree(self):
        class _VtVoidPart:
            def __init__(self, create_shell: bool):
                self._create_shell = create_shell
                self._called = False
                self._boss = _FakeFeature("凸台-拉伸1", "Extrusion", None)
                self._shell = _FakeFeature("抽壳1", "Shell", None)
                self._boss_plus = _FakeFeature("凸台-拉伸1", "Extrusion", next_feat=self._shell)

            def GetType(self):
                return 1

            def ClearSelection2(self, _):
                return True

            def EditRebuild3(self):
                return True

            def FirstFeature(self):
                if self._called and self._create_shell:
                    return self._boss_plus
                return self._boss

            def FeatureByName(self, name):
                return self._shell if (self._create_shell and name == "抽壳1") else None

            def InsertFeatureShell(self, _t, _o):
                self._called = True
                return None

        ok_part = _VtVoidPart(create_shell=True)
        with mock.patch.object(server, "_active_part_required", return_value=(object(), ok_part)), \
             mock.patch.object(server, "shell", sw_part.shell, create=True), \
             mock.patch.object(server, "mm", lambda v: v / 1000.0, create=True), \
             mock.patch.object(server, "get_com_member", lambda obj, name, default=None: getattr(obj, name, default), create=True):
            res_ok = json.loads(server.solidworks_shell(server.SolidWorksShellInput(thickness_mm=2.0)))
            self.assertEqual(res_ok["status"], "ok")
            self.assertEqual(res_ok["feature_created"], True)
            self.assertEqual(res_ok["feature_name"], "抽壳1")

        bad_part = _VtVoidPart(create_shell=False)
        with mock.patch.object(server, "_active_part_required", return_value=(object(), bad_part)), \
             mock.patch.object(server, "shell", sw_part.shell, create=True), \
             mock.patch.object(server, "mm", lambda v: v / 1000.0, create=True), \
             mock.patch.object(server, "get_com_member", lambda obj, name, default=None: getattr(obj, name, default), create=True):
            res_bad = json.loads(server.solidworks_shell(server.SolidWorksShellInput(thickness_mm=25.0)))
            self.assertEqual(res_bad["status"], "error")
            self.assertEqual(res_bad["feature_created"], False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
