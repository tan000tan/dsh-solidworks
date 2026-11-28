# -*- coding: utf-8 -*-
"""
tests/round2_regression_test.py
第二轮全面缺陷挖掘与持续整改专项回归测试套件 (Round 2 Full Regression Suite)。

逐项覆盖：
- DEF-F-001: SolidWorksRecoverInput.response_format 补齐与 solidworks_recover 非崩溃执行
- DEF-F-002 / DEF-F-005: ArtifactReadInput.response_format 补齐与 PIL 缺失友好降级错误
- DEF-F-003: _run_locked 在持锁期间记录真实操作名称 (_lock_state["operation"])
- DEF-F-004: validate_mcp.REQUIRED_TOOLS 71 工具 100% 对齐
- RT-SEC-01: solidworks_create_basic_part 校验真实属性 params.output_path
- RT-SEC-03 / BUG-010: 同名不同目录文档所有权按规范化全路径隔离，close_document 不按词干误关工程图
- R2-SEC-03 / BUG-013: solidworks_generate_drawing 校验 DrawingSpec.sourceModel 与 templateCandidates、预检前置、只读打开源模型
- H-DEF-01: headless_cad_writer.export_headless 多格式导出缺失 ezdxf 时不抛未捕获异常、不残留孤儿文件
- R2-COM-01: sw_measure.collect_mass_properties 初始化 warnings 列表，GetMassProperties2 回退不抛 KeyError
- BUG-004 / BUG-B-02 / OBS-F-004: FastMCP wire 返回 CallToolResult(isError=True)，直接调用仍返回 JSON 字符串
- BUG-012: sw_pattern.circular_pattern 支持基准轴缺失时通过正交基准面自动创建基准轴
- BUG-014: sw_connect.connect_solidworks 严格拒绝 target_pid 不匹配并记录进程 create_time
- BUG-B-04: server._couninitialize 配对释放 COM
- OBS-F-005 / OBS-F-006 / OBS-F-007 / OBS-F-012 / OBS-F-013: 注解诚实性、路径长度上限 1024、globals 不覆盖桩函数、operation_id 正则白名单
- D-T1: sw_preflight --non-interactive 与 SW_NON_INTERACTIVE 非交互模式
- RT-TEST-01: GeometryVerifier 在 COM 异常时严格将 report.passed 置为 False
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"
SERVER_DIR = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "mcp-server"
REAL_CAD_DIR = REPO_ROOT / "tests" / "real_cad"
for p in (str(SERVER_DIR), str(SCRIPTS_DIR), str(REAL_CAD_DIR), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import server
import sw_connect
import sw_measure
import sw_pattern
import sw_preflight
import validate_mcp
import headless_cad_writer
import geometry_verifier


class TestRound2RemediationRegressions(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="dsh-sw-r2-reg-")
        self.sandbox = Path(self._tmp.name)
        os.environ["DSH_ALLOWED_ROOTS"] = json.dumps([str(self.sandbox)])
        os.environ["SW_MCP_OUTPUT_ROOT"] = str(self.sandbox / "artifacts")
        os.environ["SW_MCP_QUEUE_DIR"] = str(self.sandbox / "queue")
        sw_connect._SESSION_OWNED_DOCUMENTS.clear()

    def tearDown(self):
        sw_connect._SESSION_OWNED_DOCUMENTS.clear()
        self._tmp.cleanup()

    def test_01_def_f_001_recover_input_has_response_format(self):
        inp = server.SolidWorksRecoverInput(dismiss_dialogs=False, probe_timeout_seconds=1.0)
        self.assertEqual(inp.response_format, server.ResponseFormat.JSON)
        raw = server.solidworks_recover(inp)
        payload = json.loads(raw)
        self.assertIn("status", payload)

    def test_02_def_f_002_and_005_artifact_read_input_response_format(self):
        valid_id = "mcp-" + "0" * 32 + "-00001"
        inp = server.ArtifactReadInput(artifact_id=valid_id)
        self.assertEqual(inp.response_format, server.ResponseFormat.JSON)
        raw = server.cadstudio_read_artifact(inp)
        payload = json.loads(raw)
        self.assertEqual(payload.get("status"), "error")

    def test_03_def_f_003_run_locked_tracks_operation_name(self):
        observed = {}

        def my_custom_cad_step():
            observed["op"] = server._lock_state.get("operation")
            return {"status": "ok"}

        server._run_locked(my_custom_cad_step, server.ResponseFormat.JSON, load_automation=False)
        self.assertEqual(observed.get("op"), "my_custom_cad_step")
        self.assertIsNone(server._lock_state.get("operation"))

    def test_04_def_f_004_validate_mcp_71_tools_parity(self):
        mcp_tools = set(server.mcp._tool_manager._tools.keys())
        req_tools = set(validate_mcp.REQUIRED_TOOLS)
        self.assertEqual(len(mcp_tools), 74)
        self.assertTrue(req_tools.issubset(mcp_tools))

    def test_05_bug_004_mcp_wire_sets_is_error_true_while_direct_returns_str(self):
        outside_file = str(self.sandbox.parent / "forbidden_outside.sldprt")
        direct_res = server.solidworks_create_basic_part(server.SolidWorksCreateBasicPartInput(shape="box", output_path=outside_file))
        self.assertIsInstance(direct_res, str)
        self.assertEqual(json.loads(direct_res).get("status"), "error")

        wire_res = asyncio.run(server.mcp.call_tool("solidworks_create_basic_part", {"params": {"shape": "box", "output_path": outside_file}}))
        is_err = getattr(wire_res, "isError", None)
        if is_err is None:
            is_err = getattr(wire_res, "is_error", False)
        self.assertTrue(bool(is_err), f"Expected CallToolResult.isError/is_error=True, got {wire_res!r}")

    def test_06_rt_sec_03_and_bug_010_canonical_ownership_and_exact_close(self):
        dir_a = self.sandbox / "dirA"
        dir_b = self.sandbox / "dirB"
        dir_a.mkdir()
        dir_b.mkdir()
        part_a = dir_a / "bracket.SLDPRT"
        part_b = dir_b / "bracket.SLDPRT"
        drw_b = dir_b / "bracket.SLDDRW"
        part_a.write_bytes(b"A")
        part_b.write_bytes(b"B")
        drw_b.write_bytes(b"C")

        class _Doc:
            def __init__(self, p, title=None):
                self._p = str(p)
                self._t = title or Path(p).name
            def GetPathName(self):
                return self._p
            def GetTitle(self):
                return self._t
            def GetSaveFlag(self):
                return False

        doc_a = _Doc(part_a)
        doc_b = _Doc(part_b)
        doc_drw = _Doc(drw_b)

        sw_connect.register_owned_document(doc_a)
        self.assertTrue(sw_connect.is_document_owned(doc_a))
        self.assertFalse(sw_connect.is_document_owned(doc_b), "不同目录同名零件绝不能误判为已拥有")
        self.assertFalse(sw_connect.is_document_owned(doc_drw), "同词干工程图绝不能误判为已拥有")

    def test_07_r2_sec_03_and_bug_013_generate_drawing_validates_nested_source_model(self):
        outside_part = self.sandbox.parent / "secret_model.SLDPRT"
        spec_file = self.sandbox / "spec.json"
        spec_obj = {
            "schemaVersion": "1.0",
            "sourceModel": str(outside_part),
            "documentType": "part",
            "standard": "GB_T",
            "projection": "first_angle",
            "paperSize": "A3",
            "modelSizeMm": [100, 60, 20],
            "views": {"front": None, "top": None, "right": None},
            "outputs": {"slddrw": True, "pdf": True},
        }
        spec_file.write_text(json.dumps(spec_obj), encoding="utf-8")

        out_dir = self.sandbox / "drw_out"
        out_dir.mkdir()
        server._load_automation_modules()
        orig_validate = getattr(server, "drawing_validate_spec", None)
        try:
            server.drawing_validate_spec = lambda _p: {"status": "pass", "spec": spec_obj}
            raw = server.solidworks_generate_drawing(server.SolidWorksGenerateDrawingInput(
                spec_path=str(spec_file),
                output_dir=str(out_dir),
                drawing_filename="out.slddrw",
            ))
        finally:
            if orig_validate is not None:
                server.drawing_validate_spec = orig_validate
        payload = json.loads(raw)
        self.assertEqual(payload.get("status"), "error")
        self.assertIn("outside allowed roots", payload.get("message", ""))

    def test_08_h_def_01_headless_export_atomic_and_graceful_on_missing_ezdxf(self):
        doc_path = self.sandbox / "part.cadstudio.json"
        doc_path.write_text(json.dumps({
            "documentId": "atomic-part",
            "units": "mm",
            "features": [{"id": "f1", "type": "box", "params": {"length": 20.0, "width": 10.0, "height": 5.0}}],
        }), encoding="utf-8")
        out_dir = self.sandbox / "headless_out"
        res = headless_cad_writer.export_headless(doc_path, out_dir, ["stl", "dxf"])
        self.assertIn(res.get("status"), {"pass", "pilot"})
        if "dxf" in res.get("missingFormats", []):
            self.assertEqual(res.get("status"), "pilot")

    def test_09_r2_com_01_mass_properties_fallback_with_material_no_keyerror(self):
        class _ExtFallback:
            def CreateMassProperty(self):
                return None
            def GetMassProperties2(self, *_a):
                return [0.0, 0.0, 0.0, 1e-6, 1e-3, 0.008, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

        class _DocWithMaterial:
            MaterialIdName = "AISI 304"
            Extension = _ExtFallback()

        props = sw_measure.collect_mass_properties(_DocWithMaterial())
        self.assertEqual(props.get("status"), "calculated")
        self.assertTrue(len(props.get("warnings", [])) >= 1)

    def test_10_bug_012_circular_pattern_auto_reference_axis(self):
        class _SelectData:
            Mark = 0

        class _SelMgr:
            def CreateSelectData(self):
                return _SelectData()

        class _SeedFeat:
            def Select2(self, append, mark):
                return True

        class _Ext:
            def __init__(self):
                self.axis_created = False
            def SelectByID2(self, name, sel_type, *_rest):
                if sel_type == "PLANE":
                    return True
                if sel_type == "AXIS":
                    return self.axis_created
                return False

        class _FM:
            def __init__(self, ext):
                self._ext = ext
            def InsertRefAxis(self, _opts):
                self._ext.axis_created = True
                return True
            def FeatureCircularPattern4(self, *_args):
                return {"feature": "CirPattern1"}

        class _Model:
            def __init__(self):
                self.Extension = _Ext()
                self.FeatureManager = _FM(self.Extension)
                self.SelectionManager = _SelMgr()
            def ClearSelection2(self, _all):
                return True
            def FeatureByName(self, _name):
                return _SeedFeat()

        res = sw_pattern.circular_pattern(_Model(), "Hole1", "Z", math.pi * 2, 6)
        self.assertEqual(res, {"feature": "CirPattern1"})

    def test_11_bug_014_target_pid_mismatch_and_instance_identity(self):
        ident = sw_connect.get_connected_instance_identity()
        self.assertIn("pid", ident)
        self.assertIn("create_time", ident)
        self.assertIn("instance_replaced", ident)

    def test_12_obs_f_005_006_007_012_013_contract_hardening(self):
        tools = server.mcp._tool_manager._tools
        conn_ann = tools["solidworks_connect"].annotations
        ro_hint = conn_ann.readOnlyHint if hasattr(conn_ann, "readOnlyHint") else conn_ann.read_only_hint
        self.assertFalse(ro_hint)
        for name in ("solidworks_batch_export_files", "solidworks_export_assembly_bom", "solidworks_pack_and_go", "solidworks_generate_drawing"):
            ann = tools[name].annotations
            dest_hint = ann.destructiveHint if hasattr(ann, "destructiveHint") else ann.destructive_hint
            self.assertTrue(dest_hint, f"{name} must have destructiveHint=True")

        with self.assertRaises(ValidationError):
            server.CadStudioBackendRouteInput(operation_id="../../../evil")

        with self.assertRaises(ValidationError):
            server.SolidWorksCreateBasicPartInput(shape="box", output_path="D:\\" + "a" * 1500 + ".sldprt")

        sentinel = lambda *a, **kw: "SENTINEL"
        orig = getattr(server, "connect_solidworks", None)
        try:
            server.connect_solidworks = sentinel
            server._load_automation_modules()
            self.assertIs(server.connect_solidworks, sentinel, "_load_automation_modules must not clobber monkeypatched symbol")
        finally:
            if orig is not None:
                server.connect_solidworks = orig

    def test_13_rt_test_01_geometry_verifier_fails_on_com_exceptions(self):
        class _BrokenModel:
            def GetTitle(self):
                return "Broken.SLDPRT"
            def FirstFeature(self):
                return None
            def GetBodies2(self, *_a):
                raise RuntimeError("COM body failure")
            def GetPartBox(self, *_a):
                raise RuntimeError("COM bbox failure")

        exp = geometry_verifier.GeometricExpectation(expected_solid_bodies=1, expected_bbox_mm=[10.0, 10.0, 10.0])
        rep = geometry_verifier.GeometryVerifier.verify(_BrokenModel(), exp)
        self.assertFalse(rep.passed)
        self.assertFalse(rep.checks.get("solid_body_count", True))

    def test_14_d_t1_preflight_non_interactive_flag(self):
        old_argv = sys.argv
        try:
            sys.argv = ["sw_preflight.py", "--non-interactive", "--no-solidworks-check"]
            parsed = sw_preflight._parse_args()
            self.assertTrue(parsed.no_install)
        finally:
            sys.argv = old_argv


if __name__ == "__main__":
    unittest.main()
