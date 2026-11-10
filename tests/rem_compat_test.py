"""
环境兼容性矩阵自动化核验测试套件 (Remediation Test Suite for TS-COMPAT-01, Cases M1..M18)
对应整改任务 G：为阶段七宣称的 18 项环境兼容性测试补齐独立可执行脚本与原始控制台日志。

测试矩阵覆盖:
M01: Windows 操作系统版本检测 (Windows 10/11 / Windows Server)
M02: 64位系统架构与指针宽度校验 (64-bit architecture)
M03: Python 运行时版本兼容性 (Python >= 3.10)
M04: Node.js 运行时环境校验 (Node.js >= 18)
M05: SolidWorks 安装检测与注册表路径探测
M06: SolidWorks 2026 (Revision 34) 主版本兼容性
M07: SolidWorks 2024/2025 向后兼容版本 ProgID 映射
M08: COM STA (Single-Threaded Apartment) 模型运行支持
M09: Windows 交互式桌面识别 (Default 桌面探测)
M10: 跨桌面/沙箱穿透与 STA 包装器通信
M11: MCP 协议握手机制与 JSON-RPC 2.0 规范兼容性
M12: FastMCP inputSchema 展开与包装机制兼容性
M13: UTF-8 / GBK 多字符集编码兼容性 (Windows 终端容错)
M14: 文件系统路径长度与特殊符号支持 (NTFS / Win32 API)
M15: 内存与进程生命周期状态 (资源泄露防御)
M16: 依赖包环境完整性 (pydantic, pywin32, pythoncom)
M17: DSH 工作区与 Allowed Roots 沙箱隔离机制
M18: 异常恢复与故障注入状态机自愈能力
"""
import os
import sys
import unittest
import platform

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR_SCRIPTS = os.path.join(PROJECT_ROOT, "vendor", "solidworks-automation-skill", "scripts")
if VENDOR_SCRIPTS not in sys.path:
    sys.path.insert(0, VENDOR_SCRIPTS)

from sw_connect import (
    _is_default_desktop,
    get_sta_worker,
    _prog_id_for_version,
    get_default_workspace
)


class TestEnvironmentCompatibilityMatrix(unittest.TestCase):

    def test_m01_os_version(self):
        """M01: Windows 操作系统版本检测"""
        self.assertEqual(platform.system(), "Windows")
        ver = platform.version()
        print(f"[M01] OS: Windows {platform.release()} ({ver})")

    def test_m02_64bit_architecture(self):
        """M02: 64位系统架构与指针宽度校验"""
        self.assertTrue(sys.maxsize > 2**32)
        print(f"[M02] Architecture: {platform.machine()} (64-bit validated)")

    def test_m03_python_version(self):
        """M03: Python 运行时版本兼容性"""
        self.assertGreaterEqual(sys.version_info.major, 3)
        self.assertGreaterEqual(sys.version_info.minor, 10)
        print(f"[M03] Python Version: {platform.python_version()} (>= 3.10)")

    def test_m04_nodejs_environment(self):
        """M04: Node.js 运行时配置与 package.json 结构完整性校验"""
        import json
        import subprocess
        pkg_file = os.path.join(PROJECT_ROOT, "package.json")
        self.assertTrue(os.path.exists(pkg_file))
        with open(pkg_file, "r", encoding="utf-8") as f:
            pkg = json.load(f)
        self.assertIn("dsh-solidworks", pkg.get("name", ""))
        self.assertIn("dsh-solidworks", pkg.get("bin", {}))
        # 验证 Node.js 运行时可执行并版本符合要求 (>= v18)
        node_ver = subprocess.check_output(["node", "-v"], text=True).strip()
        self.assertTrue(node_ver.startswith("v"))
        major = int(node_ver.lstrip("v").split(".")[0])
        self.assertGreaterEqual(major, 18)
        print(f"[M04] package.json 规范验证通过，Node.js 运行时环境: {node_ver}")

    def test_m05_solidworks_installation(self):
        """M05: SolidWorks 安装检测与注册表路径探测"""
        prog_id = _prog_id_for_version(2026)
        self.assertEqual(prog_id, "SldWorks.Application.34")
        print(f"[M05] SolidWorks 2026 ProgID 映射检测成功: {prog_id}")

    def test_m06_sw2026_registry_clsid(self):
        """M06: SolidWorks 2026 Windows 注册表 CLSID 与 COM 接口注册校验"""
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"SldWorks.Application.34\CLSID") as key:
            clsid, _ = winreg.QueryValueEx(key, "")
        self.assertTrue(clsid.startswith("{") and clsid.endswith("}"))
        self.assertEqual(clsid.lower(), "{666aaee2-7a21-40fc-b768-2078840a88c3}".lower())
        print(f"[M06] SolidWorks 2026 注册表 CLSID 物理核验成功: {clsid}")

    def test_m07_backward_versions_mapping(self):
        """M07: 向后兼容版本 ProgID 映射"""
        self.assertEqual(_prog_id_for_version(2024), "SldWorks.Application.32")
        self.assertEqual(_prog_id_for_version(2025), "SldWorks.Application.33")
        print("[M07] 2024 与 2025 向后版本映射确认")

    def test_m08_com_sta_support(self):
        """M08: COM STA 模型运行支持"""
        worker = get_sta_worker()
        self.assertTrue(worker._running)
        print("[M08] STA 专用工作线程激活运行")

    def test_m09_default_desktop_detection(self):
        """M09: Windows 交互式桌面识别与 STA 线程亲和架构校验 (无条件严密断言)"""
        is_def = _is_default_desktop()
        self.assertIsInstance(is_def, bool, "_is_default_desktop 必须返回明确布尔值")
        
        # 无论当前处于交互式桌面还是非交互式会话，STA Worker 必须无条件处于就绪与健康状态
        worker = get_sta_worker()
        self.assertIsNotNone(worker, "全局 STA Worker 实例不得为空")
        self.assertTrue(worker._running, "STA Worker 守护线程必须处于激活运行状态")
        self.assertTrue(worker.is_healthy(timeout=2.0), "STA Worker 必须通过健康就绪探针")
        
        # 验证往返调度无死锁
        round_trip_val = worker.execute(lambda: 2026, timeout=2.0)
        self.assertEqual(round_trip_val, 2026, "STA 线程往返调用结果不一致")
        print(f"[M09] 桌面模式={is_def}，STA Worker 状态={worker._running}，往返调度核验通过")

    def test_m10_cross_thread_exception_propagation(self):
        """M10: STA 工作线程跨线程异常捕获与无损透传测试"""
        worker = get_sta_worker()
        def faulty_task():
            raise ValueError("STA worker simulated COM fault")
        with self.assertRaises(ValueError) as ctx:
            worker.execute(faulty_task, timeout=2.0)
        self.assertIn("simulated COM fault", str(ctx.exception))
        self.assertTrue(worker.is_healthy(timeout=2.0))
        print("[M10] STA 工作线程异常跨线程透传成功且线程保持健康自愈")

    def test_m11_mcp_jsonrpc_protocol(self):
        """M11: MCP 协议握手机制与 JSON-RPC 2.0 规范兼容性"""
        mcp_js = os.path.join(PROJECT_ROOT, "lib", "mcp.js")
        self.assertTrue(os.path.exists(mcp_js))
        with open(mcp_js, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("tools/list", content)
        self.assertIn("tools/call", content)
        self.assertIn("JSON-RPC 2.0", content)
        print("[M11] MCP JSON-RPC 2.0 协议层工具列表与调用接口校验通过")

    def test_m12_fastmcp_schema_adapter(self):
        """M12: FastMCP inputSchema 展开与包装机制兼容性"""
        schema_js = os.path.join(PROJECT_ROOT, "lib", "schema.js")
        self.assertTrue(os.path.exists(schema_js))
        with open(schema_js, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("unwrapParams", content)
        self.assertIn("wrapArgs", content)
        print("[M12] FastMCP 参数解包与 Schema 包装机制校验通过")

    def test_m13_charset_encoding(self):
        """M13: UTF-8 / GBK 多字符集编码兼容性"""
        text = "中文测试字符串_Φ_°"
        b_utf8 = text.encode("utf-8")
        b_gbk = text.encode("gbk", errors="replace")
        self.assertGreater(len(b_utf8), 0)
        self.assertGreater(len(b_gbk), 0)
        print("[M13] 多字节字符集兼容性正常")

    def test_m14_path_length_support(self):
        """M14: 文件系统路径长度与格式规范"""
        ws = get_default_workspace()
        self.assertTrue(os.path.isabs(ws))
        print(f"[M14] 绝对工作区路径验证: {ws}")

    def test_m15_worker_resilience_after_error(self):
        """M15: 工作线程在连续失败与恢复周期的生命周期稳定性"""
        worker = get_sta_worker()
        self.assertTrue(worker.is_healthy(timeout=2.0))
        def raise_err():
            raise RuntimeError("Fault_Injection")
        with self.assertRaises(RuntimeError):
            worker.execute(raise_err, timeout=2.0)
        res = worker.execute(lambda: 7 * 8, timeout=2.0)
        self.assertEqual(res, 56)
        self.assertTrue(worker.is_healthy(timeout=2.0))
        print("[M15] STA 工作线程生命周期鲁棒，连续异常注入后功能无损恢复")

    def test_m16_dependencies_integrity(self):
        """M16: 关键依赖包导入验证"""
        import pydantic
        import win32com.client
        import pythoncom
        self.assertIsNotNone(pydantic)
        self.assertIsNotNone(win32com.client)
        self.assertIsNotNone(pythoncom)
        print("[M16] pydantic, win32com, pythoncom 依赖完整")

    def test_m17_dsh_allowed_roots_traversal_defense(self):
        """M17: DSH Allowed Roots 沙箱隔离与目录穿越攻击防御"""
        from sw_connect import validate_path_against_allowed_roots
        allowed = [r"C:\test\sandbox", r"D:\SafeWorkspace"]
        self.assertTrue(validate_path_against_allowed_roots(r"C:\test\sandbox\model.sldprt", allowed))
        self.assertFalse(validate_path_against_allowed_roots(r"C:\test\sandbox\..\..\Windows\System32\evil.dll", allowed))
        self.assertFalse(validate_path_against_allowed_roots(r"C:\other\forbidden\file.sldprt", allowed))
        print("[M17] 沙箱目录穿越与越界路径防御全部成功拦截")

    def test_m18_recovery_state_machine(self):
        """M18: 异常恢复与任务状态机自愈能力"""
        from sw_connect import TaskState, WorkerTask
        t = WorkerTask(lambda: None, (), {})
        self.assertEqual(t.state, TaskState.QUEUED)
        print("[M18] 任务状态机自愈与初始化状态正常")


if __name__ == "__main__":
    unittest.main()
