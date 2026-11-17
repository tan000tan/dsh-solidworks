# -*- coding: utf-8 -*-
"""
tests/d11_head_of_line_and_fastfail_test.py
D-11 / 历史 12 FAIL / AUD-COM-001 行为验证套件：
1. COM 持锁阻塞期间，非 COM/离线工具 (load_automation=False) 零阻塞即时返回 (<0.5s)；
2. 另一个 COM 工具在有限等待后快速返回 SolidWorksBusyTimeout 与 holder 诊断，不再静默挂死 300s；
3. 无 SolidWorks 实例时（read-only / DSH_ALLOW_LAUNCH_SW=0），12 个历史超时工具全部在 <1s 内结构化失败，0 超时；
4. _com_initialized() 在成功与异常路径均严格配对调用 CoInitialize / CoUninitialize (AUD-COM-001)。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_DIR = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "mcp-server"
SCRIPTS_DIR = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"
for p in (str(SERVER_DIR), str(SCRIPTS_DIR), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import server  # noqa: E402
import sw_connect  # noqa: E402


class TestD11HeadOfLineAndFastFail(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="dsh-sw-d11-")
        self.sandbox = Path(self._tmp.name)
        os.environ["DSH_ALLOWED_ROOTS"] = json.dumps([str(self.sandbox)])
        os.environ["DSH_POLICY_MODE"] = "read-only"
        os.environ["DSH_ALLOW_LAUNCH_SW"] = "0"

    def tearDown(self):
        self._tmp.cleanup()

    def test_01_non_com_tools_bypass_sw_lock_during_com_stall(self):
        """D-11: COM 全局锁被占住时，非 COM 工具不得发生队头阻塞。"""
        entered = threading.Event()
        release = threading.Event()
        holder_result = {}

        def _wedged_com_op():
            entered.set()
            release.wait(timeout=5.0)
            return {"status": "ok"}

        def _run_holder():
            holder_result["raw"] = server._run_locked(
                _wedged_com_op,
                server.ResponseFormat.JSON,
                load_automation=True,
                operation_name="wedged_com_simulation",
            )

        t = threading.Thread(target=_run_holder, daemon=True)
        t.start()
        self.assertTrue(entered.wait(timeout=3.0), "COM holder did not enter lock in time")

        try:
            t0 = time.perf_counter()
            r1 = json.loads(server.solidworks_health_check(server.SolidWorksHealthCheckInput(start_solidworks=False)))
            r2 = json.loads(server.cadstudio_resolve_backend(server.CadStudioBackendRouteInput(operation_id="create_box")))
            r3 = json.loads(server.cadstudio_routing_preflight(server.CadStudioRoutingPreflightInput()))
            r4 = json.loads(server.cadstudio_fea_preflight(server.CadStudioFeaPreflightInput()))
            r5 = json.loads(server.solidworks_compile_feature_graph(server.FeatureGraphCompileInput(graph={
                "graph_id": "g1",
                "target_part_name": "p1",
                "nodes": [{"id": "n1", "kind": "sketch_profile", "op": "sketch_rectangle", "params": {"plane": "Front", "width_mm": 10, "height_mm": 10}}],
            })))
            elapsed = time.perf_counter() - t0
            self.assertLess(elapsed, 2.0, f"Non-COM tools suffered head-of-line blocking ({elapsed:.2f}s)")
            self.assertIn(r1["status"], {"ok", "warning"})
            self.assertIn("status", r2)
            self.assertIn("status", r3)
            self.assertIn("status", r4)
            self.assertIn("status", r5)

            # 第二个 COM 请求在短等待超时后应快速返回 SolidWorksBusyTimeout
            orig_wait = server.DEFAULT_LOCK_WAIT_TIMEOUT_SECONDS
            server.DEFAULT_LOCK_WAIT_TIMEOUT_SECONDS = 1.0
            try:
                t1 = time.perf_counter()
                busy_res = json.loads(
                    server._run_locked(lambda: {"status": "ok"}, server.ResponseFormat.JSON, load_automation=True, operation_name="second_com")
                )
                busy_elapsed = time.perf_counter() - t1
                self.assertLess(busy_elapsed, 2.5)
                self.assertEqual(busy_res["status"], "error")
                self.assertEqual(busy_res["error_type"], "SolidWorksBusyTimeout")
                self.assertEqual(busy_res["holder"]["operation"], "wedged_com_simulation")
            finally:
                server.DEFAULT_LOCK_WAIT_TIMEOUT_SECONDS = orig_wait
        finally:
            release.set()
            t.join(timeout=5.0)

        self.assertEqual(json.loads(holder_result["raw"])["status"], "ok")

    def test_02_twelve_historical_timeout_tools_fail_fast_without_sw(self):
        """D-11 / 历史 12 FAIL：无 SolidWorks 实例时 12 个无必填参工具均应在 <1s 内结构化返回 error，无一挂起。"""
        # 使用 mock 确保即使测试机有残留 SW 进程也不触发真实 COM
        with mock.patch.object(sw_connect, "solidworks_processes", return_value={}), \
             mock.patch.object(sw_connect, "ensure_solidworks_installed", return_value="C:\\Program Files\\SOLIDWORKS Corp\\SOLIDWORKS\\SLDWORKS.exe"), \
             mock.patch.object(sw_connect, "_get_active_object", side_effect=RuntimeError("MK_E_UNAVAILABLE")):
            calls = [
                ("solidworks_connect", lambda: server.solidworks_connect(server.SolidWorksConnectInput(wait_seconds=1))),
                ("solidworks_list_edges", lambda: server.solidworks_list_edges(server.SolidWorksEdgeInspectionInput())),
                ("solidworks_mass_properties", lambda: server.solidworks_mass_properties(server.SolidWorksMassPropertiesInput())),
                ("solidworks_bounding_box", lambda: server.solidworks_bounding_box(server.SolidWorksBoundingBoxInput())),
                ("solidworks_interference_check", lambda: server.solidworks_interference_check(server.SolidWorksInterferenceInput())),
                ("solidworks_document_units", lambda: server.solidworks_document_units(server.SolidWorksUnitsInput())),
                ("solidworks_save_document", lambda: server.solidworks_save_document(server.SolidWorksSaveDocumentInput())),
                ("solidworks_inspect_configurations", lambda: server.solidworks_inspect_configurations(server.SolidWorksConfigurationInspectInput())),
                ("solidworks_identify_dimensions", lambda: server.solidworks_identify_dimensions(server.SolidWorksIdentifyDimensionsInput())),
                ("solidworks_inspect_hole_features", lambda: server.solidworks_inspect_hole_features(server.SolidWorksHoleInspectionInput())),
                ("solidworks_inspect_motion_studies", lambda: server.solidworks_inspect_motion_studies(server.SolidWorksMotionAuditInput())),
                ("solidworks_validate_motion_study", lambda: server.solidworks_validate_motion_study(server.SolidWorksMotionValidationInput())),
            ]
            t0 = time.perf_counter()
            for name, fn in calls:
                c0 = time.perf_counter()
                res = json.loads(fn())
                dt = time.perf_counter() - c0
                self.assertEqual(res.get("status"), "error", f"{name} unexpected status: {res}")
                self.assertLess(dt, 1.5, f"{name} blocked for {dt:.2f}s without SW")
            self.assertLess(time.perf_counter() - t0, 5.0)

    def test_03_aud_com_001_com_initialized_pairs_uninitialize_on_exception(self):
        """AUD-COM-001: _com_initialized() 在正常与异常路径均成对调用 CoInitialize / CoUninitialize。"""
        calls = []
        fake_pycom = types.SimpleNamespace(
            CoInitialize=lambda: calls.append("init"),
            CoUninitialize=lambda: calls.append("uninit"),
        )
        with mock.patch.object(server, "pythoncom", fake_pycom):
            with server._com_initialized():
                pass
            with self.assertRaises(RuntimeError):
                with server._com_initialized():
                    raise RuntimeError("boom")
        self.assertEqual(calls, ["init", "uninit", "init", "uninit"])


if __name__ == "__main__":
    unittest.main()
