# -*- coding: utf-8 -*-
"""
tests/engine_reliability_test.py
STA Worker 线程模型、超时熔断与生命周期可靠性单元测试。
"""

import sys
import threading
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from sw_connect import DesktopPinnedStaWorker


class TestEngineReliability(unittest.TestCase):

    def setUp(self):
        self.worker = DesktopPinnedStaWorker()
        self.worker.start()

    def tearDown(self):
        self.worker.stop()

    def test_basic_dispatch_and_thread_isolation(self):
        """测试基本任务分发与线程隔离（主线程与工作线程不同）。"""
        main_tid = threading.get_ident()
        worker_tid = self.worker.execute(lambda: threading.get_ident())
        self.assertNotEqual(main_tid, worker_tid)

    def test_timeout_interception_and_non_blocking_recovery(self):
        """测试超时熔断拦截：超时任务抛出 TimeoutError，且不阻塞后续正常任务。"""
        def _slow_task():
            time.sleep(0.5)
            return "finished"

        # 1. 触发超时
        with self.assertRaises(TimeoutError):
            self.worker.execute(_slow_task, timeout=0.05)

        # 2. 等待片刻，验证后续任务依然能够正常调度执行
        time.sleep(0.1)
        res = self.worker.execute(lambda: "healthy", timeout=1.0)
        self.assertEqual(res, "healthy")

    def test_worker_restart_and_health_check(self):
        """测试 Worker 重启与健康探活状态机。"""
        self.assertTrue(self.worker.is_healthy())
        old_tid = self.worker.execute(lambda: threading.get_ident())

        # 执行重启
        self.worker.restart()
        self.assertTrue(self.worker.is_healthy())
        new_tid = self.worker.execute(lambda: threading.get_ident())

        # 新线程 ID 应与旧线程 ID 不同
        self.assertNotEqual(old_tid, new_tid)

    def test_exception_propagation_accuracy(self):
        """测试工作线程异常穿透到主线程时保留类型与消息。"""
        class CustomEngineError(Exception):
            pass

        def _bad_task():
            raise CustomEngineError("COM DISP_E_EXCEPTION 0x80020009")

        with self.assertRaises(CustomEngineError) as cm:
            self.worker.execute(_bad_task)

        self.assertIn("0x80020009", str(cm.exception))

    def test_reentrant_execution_same_thread(self):
        """测试同线程递归调用时直接执行，避免自死锁。"""
        def _outer_task():
            # 内部再次调用 worker.execute
            inner_res = self.worker.execute(lambda: 42)
            return inner_res * 2

        val = self.worker.execute(_outer_task)
        self.assertEqual(val, 84)


if __name__ == "__main__":
    unittest.main()
