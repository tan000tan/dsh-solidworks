"""
Unit tests for DesktopPinnedStaWorker and Python-side path safety validations.
"""
import os
import sys
import threading
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
VENDOR_SCRIPTS = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"
sys.path.insert(0, str(VENDOR_SCRIPTS))

from sw_connect import (
    DesktopPinnedStaWorker,
    get_sta_worker,
    get_final_path,
    get_default_workspace,
    validate_path_against_allowed_roots,
    _is_default_desktop,
)


class TestDesktopPinnedStaWorker(unittest.TestCase):
    def test_worker_lifecycle_and_execution(self):
        worker = DesktopPinnedStaWorker()
        try:
            worker.start()
            self.assertTrue(worker._running)
            self.assertIsNotNone(worker._thread)
            self.assertTrue(worker._thread.is_alive())

            # Test execution from calling thread
            def sample_task(x, y):
                return x + y

            res = worker.execute(sample_task, 10, 32, timeout=2.0)
            self.assertEqual(res, 42)

            # Test execution thread identity
            worker_tid = worker.execute(lambda: threading.current_thread().ident)
            self.assertEqual(worker_tid, worker._thread.ident)
            self.assertNotEqual(worker_tid, threading.current_thread().ident)

            # Test recursive/internal execution inside worker
            def nested_task():
                # Calling execute from inside the worker thread must execute directly without deadlocking
                return worker.execute(lambda: "nested_ok")

            nested_res = worker.execute(nested_task, timeout=2.0)
            self.assertEqual(nested_res, "nested_ok")

        finally:
            worker.stop()
            self.assertFalse(worker._running)

    def test_exception_propagation(self):
        worker = DesktopPinnedStaWorker()
        try:
            worker.start()

            def failing_task():
                raise ValueError("custom_test_error")

            with self.assertRaises(ValueError) as ctx:
                worker.execute(failing_task, timeout=2.0)
            self.assertIn("custom_test_error", str(ctx.exception))
        finally:
            worker.stop()

    def test_timeout_handling(self):
        worker = DesktopPinnedStaWorker()
        try:
            worker.start()

            def slow_task():
                time.sleep(0.5)
                return "done"

            with self.assertRaises(TimeoutError):
                worker.execute(slow_task, timeout=0.05)
        finally:
            worker.stop()

    def test_singleton_get_sta_worker(self):
        w1 = get_sta_worker()
        w2 = get_sta_worker()
        self.assertIs(w1, w2)
        self.assertTrue(w1._running)

    def test_path_safety_and_default_workspace(self):
        workspace = get_default_workspace()
        self.assertTrue(os.path.isabs(workspace))
        self.assertTrue("DSH-SolidWorks-Workspace" in workspace)

        # Final path resolution
        cwd = os.getcwd()
        final_cwd = get_final_path(cwd)
        self.assertTrue(os.path.isabs(final_cwd))

        # Allowed roots validation
        allowed = [cwd]
        test_file_inside = os.path.join(cwd, "test_file.sldprt")
        self.assertTrue(validate_path_against_allowed_roots(test_file_inside, allowed))

        test_file_outside = "C:\\Windows\\System32\\calc.exe"
        self.assertFalse(validate_path_against_allowed_roots(test_file_outside, allowed))

    def test_timeout_skips_queued_stale_tasks(self):
        worker = DesktopPinnedStaWorker()
        try:
            worker.start()
            executed_stale = []

            # Blocker task to hold the worker for 0.2s
            worker.execute(lambda: None, timeout=1.0)

            # Block worker with a slow operation
            event_start = threading.Event()

            def slow_blocker():
                event_start.set()
                time.sleep(0.15)
                return "blocker_done"

            t1 = threading.Thread(target=lambda: worker.execute(slow_blocker, timeout=1.0))
            t1.start()
            event_start.wait(timeout=1.0)

            # Now submit a fast task with very short timeout (0.02s) so it times out while QUEUED
            def stale_task():
                executed_stale.append(True)
                return "stale_done"

            with self.assertRaises(TimeoutError):
                worker.execute(stale_task, timeout=0.02)

            t1.join(timeout=1.0)
            # Give the worker a moment to process the queue
            time.sleep(0.05)
            # The stale task should have been dropped and never executed
            self.assertEqual(len(executed_stale), 0)
        finally:
            worker.stop()

    def test_allowed_roots_empty_fail_closed(self):
        old_env = os.environ.get("DSH_ALLOWED_ROOTS")
        try:
            os.environ["DSH_ALLOWED_ROOTS"] = "[]"
            self.assertFalse(validate_path_against_allowed_roots("C:\\work\\file.sldprt"))
            self.assertFalse(validate_path_against_allowed_roots("relative.sldprt"))
        finally:
            if old_env is None:
                os.environ.pop("DSH_ALLOWED_ROOTS", None)
            else:
                os.environ["DSH_ALLOWED_ROOTS"] = old_env

    def test_open_document_blocks_outside_allowed_roots(self):
        old_env = os.environ.get("DSH_ALLOWED_ROOTS")
        try:
            os.environ["DSH_ALLOWED_ROOTS"] = '["C:\\\\safe_workspace"]'
            from sw_connect import open_document
            with self.assertRaises(PermissionError):
                open_document(None, "C:\\evil\\target.sldprt")
        finally:
            if old_env is None:
                os.environ.pop("DSH_ALLOWED_ROOTS", None)
            else:
                os.environ["DSH_ALLOWED_ROOTS"] = old_env

    def test_unc_prefix_normalization(self):
        unc_path = r"\\server\share\file.sldprt"
        final_unc = get_final_path(unc_path)
        self.assertFalse(final_unc.startswith(r"\\?\UNC"))
        self.assertTrue(final_unc.startswith(r"\\"))

    def test_cad_transaction_rollback_and_commit(self):
        from sw_session import CADSessionState, CADTransaction

        class MockFeatureManager:
            def __init__(self):
                self.EnableFeatureTree = True

        class MockModel:
            def __init__(self):
                self.FeatureManager = MockFeatureManager()
                self._features = ["f1", "f2"]
                self.rebuilt = False
                self.cleared = False

            def GetTitle(self):
                return "MockPart"

            def GetFeatureCount(self):
                return len(self._features)

            def EditUndo(self):
                if self._features:
                    self._features.pop()

            def EditRebuild3(self):
                self.rebuilt = True

            def ClearSelection2(self, all_items):
                self.cleared = True

        class MockSession:
            def __init__(self):
                self.state = CADSessionState.CONNECTED_IDLE
                self.active_doc = MockModel()

        sess = MockSession()
        model = sess.active_doc

        # Scenario 1: Failure rollback
        try:
            with CADTransaction(sess, model=model):
                self.assertEqual(sess.state, CADSessionState.EXECUTING)
                self.assertFalse(model.FeatureManager.EnableFeatureTree)
                # Simulate adding two features
                model._features.append("f3")
                model._features.append("f4")
                self.assertEqual(model.GetFeatureCount(), 4)
                # Simulate failure before commit
                raise RuntimeError("geometry_intersection_failed")
        except RuntimeError:
            pass

        # Assert rollback occurred
        self.assertEqual(sess.state, CADSessionState.ERROR)
        self.assertEqual(model.GetFeatureCount(), 2)
        self.assertTrue(model.FeatureManager.EnableFeatureTree)
        self.assertTrue(model.cleared)

        # Scenario 2: Success commit
        with CADTransaction(sess, model=model) as tx:
            model._features.append("f3")
            tx.commit()

        self.assertEqual(sess.state, CADSessionState.CONNECTED_IDLE)
        self.assertEqual(model.GetFeatureCount(), 3)
        self.assertTrue(model.rebuilt)
        self.assertTrue(model.FeatureManager.EnableFeatureTree)


if __name__ == "__main__":
    unittest.main()
