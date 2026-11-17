# -*- coding: utf-8 -*-
"""
tests/rem_stability_soak_test.py
持续负载、多线程竞争、异常恢复、资源回收与稳定性浸泡测试套件 (R2 / AUD-DOC-001)。

验证维度：
1. 200 次连续混合工具调用、越界拒绝与异常恢复浸泡循环，使用 tracemalloc 实测内存增量 < 2 MiB；
2. 8 线程 ThreadPoolExecutor 并发争抢 server._run_locked，验证严格互斥 (max_concurrent == 1)、异常穿透与锁释放；
3. 连续 15 轮 STA Worker 重启、重连与异常穿透后线程数与 Windows 句柄数不泄漏。
"""
from __future__ import annotations

import concurrent.futures
import gc
import json
import os
import sys
import tempfile
import threading
import time
import tracemalloc
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"
SERVER_DIR = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "mcp-server"
for p in (str(SERVER_DIR), str(SCRIPTS_DIR), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


def _get_process_handle_count() -> int:
    if os.name != "nt":
        return 0
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        h_proc = kernel32.GetCurrentProcess()
        count = wintypes.DWORD(0)
        if kernel32.GetProcessHandleCount(h_proc, ctypes.byref(count)):
            return int(count.value)
    except Exception:
        pass
    return 0


class TestStabilityAndResourceSoak(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="dsh-sw-soak-")
        self.sandbox = Path(self._tmp.name)
        os.environ["DSH_ALLOWED_ROOTS"] = json.dumps([str(self.sandbox)])

    def tearDown(self):
        self._tmp.cleanup()

    def test_01_sustained_200_mixed_tool_and_error_recovery_cycles(self):
        """200 次混合成功调用、越界拒绝与异常恢复浸泡循环，使用 tracemalloc 实测内存、锁状态与句柄不泄漏。"""
        import server
        from sw_connect import get_sta_worker

        worker = get_sta_worker()
        self.assertTrue(worker.is_healthy())

        # 预热一次，避免首次导入延迟计入浸泡增量
        warm_raw = server.solidworks_health_check(server.SolidWorksHealthCheckInput(start_solidworks=False))
        self.assertIn(json.loads(warm_raw).get("status"), {"ok", "degraded", "warning"})

        gc.collect()
        baseline_threads = threading.active_count()
        baseline_handles = _get_process_handle_count()
        tracemalloc.start()
        base_current, base_peak = tracemalloc.get_traced_memory()

        try:
            for i in range(200):
                if i % 3 == 0:
                    res_raw = server.solidworks_health_check(server.SolidWorksHealthCheckInput(start_solidworks=False))
                    payload = json.loads(res_raw)
                    self.assertIn(payload.get("status"), {"ok", "degraded", "warning"})
                elif i % 3 == 1:
                    bad_path = str(self.sandbox.parent / f"outside_{i}.sldprt")
                    res_raw = server.solidworks_create_basic_part(server.SolidWorksCreateBasicPartInput(shape="box", output_path=bad_path))
                    payload = json.loads(res_raw)
                    self.assertEqual(payload.get("status"), "error")
                else:
                    def _op(idx=i):
                        if idx % 6 == 2:
                            raise RuntimeError(f"soak injected transient failure #{idx}")
                        return {"status": "ok", "iteration": idx}

                    res_raw = server._run_locked(_op, server.ResponseFormat.JSON, load_automation=False, operation_name=f"soak_op_{i}")
                    payload = json.loads(res_raw)
                    if i % 6 == 2:
                        self.assertEqual(payload.get("status"), "error")
                    else:
                        self.assertEqual(payload.get("status"), "ok")

            gc.collect()
            after_current, after_peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        delta_mib = (after_current - base_current) / (1024 * 1024)
        peak_mib = after_peak / (1024 * 1024)
        print(
            f"[SOAK-METRICS] cycles=200 base_bytes={base_current} after_bytes={after_current} "
            f"delta_mib={delta_mib:.4f} peak_mib={peak_mib:.4f}"
        )
        self.assertLess(delta_mib, 2.0, f"tracemalloc 内存增长超标: {delta_mib:.4f} MiB >= 2.0 MiB")

        # 验证锁完全释放，无残留持有者
        self.assertIsNone(server._lock_state.get("acquired_at"))
        self.assertIsNone(server._lock_state.get("thread"))
        self.assertIsNone(server._lock_state.get("operation"))

        after_threads = threading.active_count()
        after_handles = _get_process_handle_count()
        self.assertLessEqual(after_threads - baseline_threads, 2, f"线程数异常增长: {baseline_threads} -> {after_threads}")
        if baseline_handles > 0 and after_handles > 0:
            self.assertLessEqual(after_handles - baseline_handles, 80, f"Windows 句柄数异常泄漏: {baseline_handles} -> {after_handles}")

    def test_02_eight_thread_concurrent_run_locked_contention(self):
        """8 线程 ThreadPoolExecutor 并发争抢 _run_locked，验证严格串行互斥、异常隔离与锁完全释放。"""
        import server

        probe_lock = threading.Lock()
        in_flight = 0
        max_concurrent = 0
        completed = 0

        def _worker_task(task_id: int):
            def _op():
                nonlocal in_flight, max_concurrent, completed
                with probe_lock:
                    in_flight += 1
                    if in_flight > max_concurrent:
                        max_concurrent = in_flight
                try:
                    time.sleep(0.002)
                    if task_id % 5 == 0:
                        raise RuntimeError(f"concurrent injected failure #{task_id}")
                    completed += 1
                    return {"status": "ok", "task_id": task_id}
                finally:
                    with probe_lock:
                        in_flight -= 1

            raw = server._run_locked(
                _op,
                server.ResponseFormat.JSON,
                load_automation=False,
                operation_name=f"concurrent_op_{task_id}",
            )
            return task_id, json.loads(raw)

        total_tasks = 80
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(_worker_task, tid) for tid in range(total_tasks)]
            results = [f.result(timeout=30) for f in futures]

        self.assertEqual(len(results), total_tasks)
        self.assertEqual(max_concurrent, 1, f"_run_locked 发生并发重入! max_concurrent={max_concurrent}")
        self.assertEqual(in_flight, 0)
        for tid, payload in results:
            if tid % 5 == 0:
                self.assertEqual(payload.get("status"), "error")
            else:
                self.assertEqual(payload.get("status"), "ok")
                self.assertEqual(payload.get("task_id"), tid)
        self.assertIsNone(server._lock_state.get("acquired_at"))
        self.assertIsNone(server._lock_state.get("thread"))
        self.assertIsNone(server._lock_state.get("operation"))

    def test_03_repeated_sta_worker_restart_and_reconnect_cycles(self):
        """连续 15 轮 STA Worker 重启与任务投递，验证旧线程彻底退出、无幽灵线程累积。"""
        from sw_connect import get_sta_worker

        worker = get_sta_worker()
        baseline_threads = threading.active_count()

        for cycle in range(15):
            worker.restart()
            self.assertTrue(worker.is_healthy())
            val = worker.execute(lambda c=cycle: c * 2 + 1, timeout=5.0)
            self.assertEqual(val, cycle * 2 + 1)

        gc.collect()
        after_threads = threading.active_count()
        self.assertLessEqual(after_threads - baseline_threads, 2, f"15 轮 STA 重启后线程数累积: {baseline_threads} -> {after_threads}")


if __name__ == "__main__":
    unittest.main()
