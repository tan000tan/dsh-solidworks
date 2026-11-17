# -*- coding: utf-8 -*-
"""
tests/drawing_lifecycle_and_pid_identity_test.py
R4 (AUD-CAD-001) & R6 (AUD-TEST-001 / BUG-014) 真实行为与故障注入测试：
1. solidworks_generate_drawing / review_drawing / inspect_drawing 文档所有权与异常清理；
2. target_pid 失配/非法 PID 阻断，以及真实子进程 create_time 存活/退出/PID 复用校验。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_DIR = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "mcp-server"
SCRIPTS_DIR = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"
TESTS_DIR = REPO_ROOT / "tests"
for p in (str(SERVER_DIR), str(SCRIPTS_DIR), str(TESTS_DIR), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import server  # noqa: E402
import sw_connect  # noqa: E402
from _fake_sw_com import FakeModelDoc, FakeSwApp as FakeSolidWorksApp  # noqa: E402


class TestDrawingLifecycleAndPidIdentity(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="dsh-sw-r4r6-")
        self.sandbox = Path(self._tmp.name)
        os.environ["DSH_ALLOWED_ROOTS"] = json.dumps([str(self.sandbox)])
        sw_connect._SESSION_OWNED_DOCUMENTS.clear()

        self.source_part = self.sandbox / "part_a.SLDPRT"
        self.source_part.write_bytes(b"FAKE-SLDPRT")
        self.spec_path = self.sandbox / "drawing_spec.json"
        self.spec_path.write_text(
            json.dumps(
                {
                    "schemaVersion": "1.0",
                    "sourceModel": str(self.source_part),
                    "modelSizeMm": [100.0, 60.0, 20.0],
                    "views": ["front", "top", "right"],
                }
            ),
            encoding="utf-8",
        )
        self.output_dir = self.sandbox / "out"
        self.output_dir.mkdir()

    def tearDown(self):
        sw_connect._SESSION_OWNED_DOCUMENTS.clear()
        self._tmp.cleanup()

    def _run_generate_with_fake_sw(
        self,
        fake_sw: FakeSolidWorksApp,
        *,
        generation_res=None,
        save_ok=True,
        pdf_exc=None,
        preview_exc=None,
        review_exc=None,
        close_exc=None,
        overwrite=True,
    ):
        def _fake_connect(*_a, **_kw):
            return fake_sw, fake_sw.ActiveDoc

        def _fake_open(sw, fp, read_only=False, silent=True, raise_on_error=True):
            existing = sw.GetOpenDocumentByName(fp)
            if existing is not None:
                return existing
            doc = FakeModelDoc(sw, Path(fp).name, doc_type=1, path=str(fp))
            sw._docs.append(doc)
            sw._active = doc
            return doc

        def _fake_new_doc(sw, kind):
            doc = FakeModelDoc(sw, "Draw1.SLDDRW", doc_type=3)
            sw._docs.append(doc)
            sw._active = doc
            sw_connect.register_owned_document(doc)
            return doc

        def _fake_save(doc, path):
            if save_ok:
                Path(path).write_bytes(b"FAKE-SLDDRW")
                doc._path = str(path)
                doc._title = Path(path).name
                return True
            return False

        def _fake_close(sw, doc, force_discard=False, **_kw):
            if close_exc is not None:
                raise close_exc
            if doc in sw._docs:
                sw._docs.remove(doc)
            return True

        def _fake_pdf(*_a, **_kw):
            if pdf_exc is not None:
                raise pdf_exc
            pdf_p = self.output_dir / "part_a.pdf"
            pdf_p.write_bytes(b"%PDF-1.4")
            return True

        def _fake_previews(*_a, **_kw):
            if preview_exc is not None:
                raise preview_exc
            p = self.output_dir / "previews" / "part_a_front.bmp"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"BM")
            return [p]

        def _fake_review(*_a, **_kw):
            if review_exc is not None:
                raise review_exc
            return {"status": "pass", "manual_review_required": False}

        with (
            mock.patch.object(server, "_load_automation_modules", lambda: None),
            mock.patch.object(server, "connect_solidworks", _fake_connect, create=True),
            mock.patch.object(server, "open_document", _fake_open, create=True),
            mock.patch.object(server, "new_document", _fake_new_doc, create=True),
            mock.patch.object(server, "save_document", _fake_save, create=True),
            mock.patch.object(sw_connect, "close_document", _fake_close),
            mock.patch("scripts.sw_drawing.validate_generic_drawing_generation", return_value={"status": "pass"}),
            mock.patch.object(
                server,
                "drawing_validate_spec",
                lambda p: {"status": "pass", "spec": json.loads(Path(p).read_text(encoding="utf-8"))},
                create=True,
            ),
            mock.patch.object(
                server,
                "drawing_generate_from_spec",
                lambda *_a, **_kw: generation_res if generation_res is not None else {"status": "pass", "structure": {}},
                create=True,
            ),
            mock.patch.object(server, "drawing_export_sheet_to_pdf", _fake_pdf, create=True),
            mock.patch.object(server, "drawing_save_review_previews", _fake_previews, create=True),
            mock.patch.object(server, "drawing_inspect_bmp_preview", lambda p: {"path": str(p), "ok": True}, create=True),
            mock.patch.object(server, "drawing_review_artifacts", _fake_review, create=True),
        ):
            raw = server.solidworks_generate_drawing(
                server.SolidWorksGenerateDrawingInput(
                    spec_path=str(self.spec_path),
                    output_dir=str(self.output_dir),
                    drawing_filename="part_a.SLDDRW",
                    overwrite=overwrite,
                )
            )
            return json.loads(raw)

    def test_01_r4_pdf_failure_after_save_closes_both_drawing_and_source(self):
        sw = FakeSolidWorksApp()
        res = self._run_generate_with_fake_sw(sw, pdf_exc=RuntimeError("PDF export COM fault"))
        self.assertEqual(res["status"], "error")
        self.assertEqual(len(sw._docs), 0, f"Leaked open docs after PDF failure: {sw._docs}")

    def test_02_r4_preview_failure_after_save_closes_both_drawing_and_source(self):
        sw = FakeSolidWorksApp()
        res = self._run_generate_with_fake_sw(sw, preview_exc=OSError("Preview BMP write failed"))
        self.assertEqual(res["status"], "error")
        self.assertEqual(len(sw._docs), 0, f"Leaked open docs after preview failure: {sw._docs}")

    def test_03_r4_mid_review_com_exception_closes_both_drawing_and_source(self):
        sw = FakeSolidWorksApp()
        res = self._run_generate_with_fake_sw(sw, review_exc=RuntimeError("Mid-op COM exception"))
        self.assertEqual(res["status"], "error")
        self.assertEqual(len(sw._docs), 0, f"Leaked open docs after mid-op COM exception: {sw._docs}")

    def test_04_r4_generation_blocked_and_save_failed_cleanup(self):
        sw = FakeSolidWorksApp()
        res_blocked = self._run_generate_with_fake_sw(sw, generation_res={"status": "blocked", "reason": "bad view"})
        self.assertEqual(res_blocked["status"], "blocked")
        self.assertEqual(len(sw._docs), 0)

        res_save_fail = self._run_generate_with_fake_sw(sw, save_ok=False)
        self.assertEqual(res_save_fail["status"], "error")
        self.assertEqual(len(sw._docs), 0)

    def test_05_r4_preserves_user_preopened_source_document_and_repeated_calls_zero_leak(self):
        sw = FakeSolidWorksApp()
        user_doc = FakeModelDoc(sw, self.source_part.name, doc_type=1, path=str(self.source_part))
        sw._docs.append(user_doc)
        sw._active = user_doc

        # 连续 3 次调用（含一次故障注入），用户原有文档始终保留，工程图不泄漏
        res1 = self._run_generate_with_fake_sw(sw)
        self.assertEqual(res1["status"], "pass")
        self.assertEqual(sw._docs, [user_doc])

        res2 = self._run_generate_with_fake_sw(sw, pdf_exc=RuntimeError("boom"))
        self.assertEqual(res2["status"], "error")
        self.assertEqual(sw._docs, [user_doc])

        res3 = self._run_generate_with_fake_sw(sw)
        self.assertEqual(res3["status"], "pass")
        self.assertEqual(sw._docs, [user_doc])

    def test_06_r4_cleanup_failure_does_not_mask_primary_error(self):
        sw = FakeSolidWorksApp()
        res = self._run_generate_with_fake_sw(
            sw,
            pdf_exc=RuntimeError("Primary PDF error"),
            close_exc=RuntimeError("Cleanup close error"),
        )
        self.assertEqual(res["status"], "error")
        self.assertIn("Primary PDF error", res["message"])

    def test_07_r6_target_pid_mismatch_and_invalid_pid_fail_closed(self):
        fake_sw = FakeSolidWorksApp()
        fake_sw.GetProcessID = lambda: 12345

        # 非法 PID 立即阻断
        for bad_pid in (0, -1, True, "12345"):
            with self.subTest(bad_pid=bad_pid):
                with self.assertRaises(sw_connect.SolidWorksConnectionError) as ctx:
                    sw_connect.connect_solidworks(target_pid=bad_pid, allow_launch=False)
                self.assertEqual(ctx.exception.code, "SW_INVALID_TARGET_PID")

        # 活动实例 PID 与 target_pid 不一致时必须立即抛出 SW_TARGET_PID_MISMATCH，绝不回退启动或连接错误实例
        with (
            mock.patch.object(sw_connect, "list_solidworks_instances", return_value=[{"pid": 12345}]),
            mock.patch.object(sw_connect, "_get_active_object", return_value=fake_sw),
            mock.patch.object(sw_connect, "solidworks_processes", return_value={12345: 2024}),
        ):
            with self.assertRaises(sw_connect.SolidWorksConnectionError) as ctx:
                sw_connect.connect_solidworks(target_pid=99999, allow_launch=True)
            self.assertEqual(ctx.exception.code, "SW_TARGET_PID_MISMATCH")

    def test_08_r6_real_process_create_time_lifecycle_exit_and_pid_reuse(self):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(10)"])
        try:
            ct = sw_connect._get_process_create_time(proc.pid)
            self.assertIsNotNone(ct)
            sw_connect._LAST_CONNECTED_INSTANCE["pid"] = proc.pid
            sw_connect._LAST_CONNECTED_INSTANCE["create_time"] = ct

            ident = sw_connect.get_connected_instance_identity()
            self.assertTrue(ident["alive"])
            self.assertFalse(ident["instance_replaced"])
            self.assertTrue(ident["identity_valid"])

            ver = sw_connect.verify_connected_instance_identity(proc.pid, ct)
            self.assertTrue(ver["ok"])

            # 模拟 PID 复用（记录的 create_time 与实际存活进程不一致）
            sw_connect._LAST_CONNECTED_INSTANCE["create_time"] = ct - 500.0
            ident_reused = sw_connect.get_connected_instance_identity()
            self.assertTrue(ident_reused["instance_replaced"])
            self.assertFalse(ident_reused["identity_valid"])
            ver_reused = sw_connect.verify_connected_instance_identity(proc.pid, ct - 500.0)
            self.assertFalse(ver_reused["ok"])
            self.assertEqual(ver_reused["reason"], "PID_REUSED_OR_REPLACED")
        finally:
            proc.terminate()
            proc.wait(timeout=5)

        # 进程已退出：必须返回 None 且 identity_valid=False
        self.assertIsNone(sw_connect._get_process_create_time(proc.pid))
        ver_exited = sw_connect.verify_connected_instance_identity(proc.pid, 12345.0)
        self.assertFalse(ver_exited["ok"])
        self.assertEqual(ver_exited["reason"], "PROCESS_EXITED_OR_UNREADABLE")
        self.assertFalse(ver_exited["alive"])

        # 无效 PID 与不可读 create_time
        self.assertIsNone(sw_connect._get_process_create_time(-1))
        self.assertIsNone(sw_connect._get_process_create_time(True))
        self.assertFalse(sw_connect.verify_connected_instance_identity(proc.pid, None)["ok"])


if __name__ == "__main__":
    unittest.main()
