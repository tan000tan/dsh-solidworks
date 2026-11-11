# -*- coding: utf-8 -*-
"""
tests/phase2_architecture_test.py
验证阶段二：COM 与 DSH 执行架构重构、CO_E_SERVER_EXEC_FAILURE 防御、多实例管理与孤儿进程保护。
"""

import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENDOR_SCRIPTS = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"

for p in (str(VENDOR_SCRIPTS), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

import sw_process
from sw_connect import (
    is_co_e_server_exec_failure,
    connect_solidworks,
    get_sta_worker
)
import sw_job_object


class TestPhase2Architecture(unittest.TestCase):
    """阶段二架构核心能力验证套件。"""

    def test_01_co_e_server_exec_failure_detection(self):
        """测试 1：准确识别 CO_E_SERVER_EXEC_FAILURE (0x80080005) 错误形式。"""
        # Form 1: PyIDispatch exception with integer hresult
        class MockPyComError(Exception):
            def __init__(self, hresult):
                super().__init__(f"(-2146959355, 'Server execution failed', None, None)")
                self.hresult = hresult
                self.args = (hresult, 'Server execution failed')

        err1 = MockPyComError(-2146959355)
        self.assertTrue(is_co_e_server_exec_failure(err1), "必须识别 -2146959355 整数 hresult")

        # Form 2: Exception with 0x80080005 string
        err2 = RuntimeError("COM Error: 0x80080005 Server execution failed")
        self.assertTrue(is_co_e_server_exec_failure(err2), "必须识别 0x80080005 字符串")

        # Form 3: Normal unrelated exception should return False
        err3 = ValueError("Invalid argument")
        self.assertFalse(is_co_e_server_exec_failure(err3), "普通异常不得误报")

    def test_02_multi_instance_discovery(self):
        """测试 2：多实例探测函数 list_solidworks_instances 返回结构化元数据。"""
        instances = sw_process.list_solidworks_instances()
        self.assertIsInstance(instances, list, "返回值必须是列表")
        for inst in instances:
            self.assertIn("pid", inst)
            self.assertIn("year", inst)
            self.assertIn("exe_path", inst)
            self.assertIn("responding", inst)
            self.assertIsInstance(inst["pid"], int)
            self.assertIsInstance(inst["responding"], bool)

    def test_03_instance_responsiveness(self):
        """测试 3：实例响应状态检测。"""
        instances = sw_process.list_solidworks_instances()
        if instances:
            first_pid = instances[0]["pid"]
            is_ok = sw_process.is_instance_responding(first_pid)
            self.assertIsInstance(is_ok, bool, "必须返回布尔值响应状态")

    def test_04_job_object_orphan_guard(self):
        """测试 4：Windows Job Object 初始化与防孤儿守护。"""
        if os.name == "nt":
            job = sw_job_object.init_orphan_guard()
            self.assertIsNotNone(job, "Job Object 必须初始化成功")

    def test_05_safe_connection_without_touching_user_docs(self):
        """测试 5：安全连接到当前实例，核实 STA Worker 隔离性与只读元数据。"""
        instances = sw_process.list_solidworks_instances()
        if not instances:
            raise unittest.SkipTest("未运行 SolidWorks，跳过物理连接测试")
        
        sw, _ = connect_solidworks(wait_seconds=3, visible=True)
        self.assertIsNotNone(sw, "已有实例时必须成功连接")
        worker = get_sta_worker()
        self.assertIsNotNone(worker, "必须运行在专用 STA Worker 线程中")


if __name__ == "__main__":
    unittest.main()
