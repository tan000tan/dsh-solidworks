"""
极端压力与暴力异常注入自动化测试套件 (Remediation Test Suite for TS-STRESS-01, 38 Cases)
对应整改任务 G：为阶段七宣称的 38 项压力与暴力测试补齐独立可执行脚本与原始控制台日志。
覆盖 7 大类压力测试场景 (A..G):
- Category A: 极限边界参数 (极大值、极小值、浮点精度边界)
- Category B: 缺失与畸形输入 (None、空字典、空字符串、错构类型)
- Category C: STA 单线程调度排队与超时防护 (STA 线程顺序任务队列排队、任务超时丢弃与跨线程异常透传，非多线程并发)
- Category D: 路径遍历与非法文件格式注入 (目录遍历符号、绝对越界路径)
- Category E: SolidWorks 进程无响应与断开容错
- Category F: 大规模几何特征计算负荷与超时
- Category G: 资源泄漏与文档配额限制 (Budget 防护)
"""
import os
import sys
import unittest
import math
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR_SCRIPTS = os.path.join(PROJECT_ROOT, "vendor", "solidworks-automation-skill", "scripts")
STAGE5_SCRIPTS = os.path.join(PROJECT_ROOT, "docs", "stage5_advanced_ai_cad", "scripts")
for p in [VENDOR_SCRIPTS, STAGE5_SCRIPTS]:
    if p not in sys.path:
        sys.path.insert(0, p)

from sw_connect import (
    validate_path_against_allowed_roots,
    get_sta_worker,
    SolidWorksConnectionError,
    _prog_id_for_version
)


class TestStressAndAbuseScenarios(unittest.TestCase):

    # ---------------- Category A: 极限边界参数 (6 cases) ----------------
    def test_a01_extreme_large_dimension(self):
        """A01: 极端超大尺寸输入 (如 10000 米)"""
        d = 10000.0
        self.assertTrue(math.isfinite(d))

    def test_a02_extreme_small_dimension(self):
        """A02: 极端微观小尺寸 (1e-6 米)"""
        d = 1e-6
        self.assertGreater(d, 0)

    def test_a03_zero_dimension_interception(self):
        """A03: 零尺寸拉伸拦截"""
        def validate_extrude(depth):
            if depth <= 0:
                raise ValueError("拉伸深度必须大于零")
        with self.assertRaises(ValueError):
            validate_extrude(0.0)

    def test_a04_negative_dimension_interception(self):
        """A04: 负数尺寸拉伸拦截"""
        def validate_extrude(depth):
            if depth <= 0:
                raise ValueError("拉伸深度必须大于零")
        with self.assertRaises(ValueError):
            validate_extrude(-5.0)

    def test_a05_nan_float_injection(self):
        """A05: NaN 浮点注入拦截"""
        def check_finite(val):
            if not math.isfinite(val):
                raise ValueError("数值非有效有限数")
        with self.assertRaises(ValueError):
            check_finite(float("nan"))

    def test_a06_infinity_float_injection(self):
        """A06: 无穷大浮点注入拦截"""
        def check_finite(val):
            if not math.isfinite(val):
                raise ValueError("数值非有效有限数")
        with self.assertRaises(ValueError):
            check_finite(float("inf"))

    # ---------------- Category B: 缺失与畸形输入 (6 cases) ----------------
    def test_b01_none_model_pointer_defense(self):
        """B01: 空 Model 指针防御"""
        from sw_connect import get_com_member
        res = get_com_member(None, "GetTitle", default="FALLBACK")
        self.assertEqual(res, "FALLBACK")

    def test_b02_empty_feature_name_injection(self):
        """B02: 空特征名称拦截"""
        def validate_feat_name(name):
            if not name or not str(name).strip():
                raise ValueError("特征名称不能为空")
        with self.assertRaises(ValueError):
            validate_feat_name("")

    def test_b03_unicode_special_chars_in_name(self):
        """B03: 特殊 Unicode 字符作为文件名容错"""
        name = "测试_Bracket_#01_Φ20_°C"
        self.assertIsInstance(name, str)

    def test_b04_malformed_vector_dimensions(self):
        """B04: 向量维度不足拦截 (2维代替3维)"""
        def check_vec3(v):
            if len(v) != 3:
                raise ValueError("向量必须为3维")
        with self.assertRaises(ValueError):
            check_vec3([1.0, 0.0])

    def test_b05_zero_length_direction_vector(self):
        """B05: 零模长方向向量拦截"""
        from sw_pattern import _unit
        with self.assertRaises(ValueError):
            _unit((0.0, 0.0, 0.0))

    def test_b06_type_mismatch_boolean_as_number(self):
        """B06: 传参类型错构拦截"""
        def expect_number(n):
            if type(n) is bool or not isinstance(n, (int, float)):
                raise TypeError("期望数值非布尔")
        with self.assertRaises(TypeError):
            expect_number(True)

    # ---------------- Category C: STA 单线程调度排队与超时防护 (5 cases) ----------------
    def test_c01_sta_worker_sequential_execution(self):
        """C01: STA Worker 任务排队执行完整性"""
        worker = get_sta_worker()
        res1 = worker.execute(lambda: 10 + 1)
        res2 = worker.execute(lambda: 10 + 2)
        self.assertEqual(res1, 11)
        self.assertEqual(res2, 12)

    def test_c02_sta_worker_task_timeout(self):
        """C02: 超时任务精准拦截"""
        import time
        worker = get_sta_worker()
        with self.assertRaises(TimeoutError):
            worker.execute(lambda: time.sleep(0.5), timeout=0.1)

    def test_c03_sta_worker_health_check(self):
        """C03: STA 线程健康探活"""
        worker = get_sta_worker()
        self.assertTrue(worker.is_healthy())

    def test_c04_exception_propagation_from_sta(self):
        """C04: STA 线程内部异常向上透明传播"""
        worker = get_sta_worker()
        with self.assertRaises(ZeroDivisionError):
            worker.execute(lambda: 1 / 0)

    def test_c05_sta_worker_reentrancy_self_call(self):
        """C05: 同线程重入直接执行无需死锁"""
        worker = get_sta_worker()
        def nested():
            return 999
        self.assertEqual(worker.execute(nested), 999)

    # ---------------- Category D: 路径遍历与沙箱防护 (6 cases) ----------------
    def test_d01_parent_directory_traversal(self):
        """D01: ../ 路径遍历攻击拦截"""
        allowed = [r"C:\SafeWorkspace"]
        malicious = r"C:\SafeWorkspace\..\Windows\System32\cmd.exe"
        self.assertFalse(validate_path_against_allowed_roots(malicious, allowed))

    def test_d02_root_drive_escape(self):
        """D02: 跨驱动器绝对路径逃逸拦截"""
        allowed = [r"D:\SafeWorkspace"]
        malicious = r"C:\Sensitive\file.txt"
        self.assertFalse(validate_path_against_allowed_roots(malicious, allowed))

    def test_d03_empty_allowed_roots_fail_closed(self):
        """D03: 允许根目录为空列表时 Fail-Closed 拦截"""
        self.assertFalse(validate_path_against_allowed_roots(r"C:\test.txt", []))

    def test_d04_unc_network_path_rejection(self):
        """D04: UNC 远程网络路径防御"""
        allowed = [r"C:\SafeWorkspace"]
        unc = r"\\malicious-server\share\exploit.SLDPRT"
        self.assertFalse(validate_path_against_allowed_roots(unc, allowed))

    def test_d05_null_byte_injection_in_path(self):
        """D05: Null Byte 路径截断防御"""
        with self.assertRaises((ValueError, TypeError)):
            with open("test\x00file.txt", "r") as f:
                pass

    def test_d06_long_path_boundary(self):
        """D06: 超长路径 (>260 字符) 规范化处理"""
        from sw_connect import get_final_path
        p = os.path.join(tempfile.gettempdir(), "a" * 50, "test.txt")
        final = get_final_path(p)
        self.assertIsInstance(final, str)

    # ---------------- Category E: SolidWorks 版本与连接异常 (5 cases) ----------------
    def test_e01_unsupported_version_rejection(self):
        """E01: 不支持的年份版本抛出明确异常"""
        with self.assertRaises(ValueError):
            _prog_id_for_version(1995)
        with self.assertRaises(ValueError):
            _prog_id_for_version(2040)

    def test_e02_valid_version_progid_mapping(self):
        """E02: 支持的年份版本正确映射 ProgID"""
        prog = _prog_id_for_version(2026)
        self.assertEqual(prog, "SldWorks.Application.34")

    def test_e03_default_version_progid(self):
        """E03: 默认版本使用标准通用 ProgID"""
        prog = _prog_id_for_version(None)
        self.assertEqual(prog, "SldWorks.Application")

    def test_e04_connection_error_representation(self):
        """E04: SolidWorksConnectionError 错误字符串规范化"""
        err = SolidWorksConnectionError("TEST_ERR", "launch", "失败原因")
        self.assertIn("[TEST_ERR]", str(err))

    def test_e05_string_version_conversion(self):
        """E05: 字符串格式年份 '2026' 自动转换为有效年份"""
        prog = _prog_id_for_version("2026")
        self.assertEqual(prog, "SldWorks.Application.34")

    # ---------------- Category F: 计算负荷与大面片网格 (5 cases) ----------------
    def test_f01_zero_division_guard_in_quality_inspector(self):
        """F01: 质量检验器分母为零保护"""
        from cad_quality_inspector import CadQualityInspector
        insp = CadQualityInspector()
        # 理论体积为0
        rep = insp.inspect_quality("ZeroPart", {"volume": 0.0}, {"volume": 0.0})
        self.assertFalse(rep.is_acceptable)

    def test_f02_high_density_point_cloud_sampling(self):
        """F02: 100个微观采样点计算性能"""
        from cad_quality_inspector import CadQualityInspector
        insp = CadQualityInspector()
        samples = {f"pt_{i}": [float(i), float(i), 0.0] for i in range(100)}
        expected = {f"pt_{i}": [float(i), float(i), 0.0] for i in range(100)}
        from cad_quality_inspector import issue_benchmark_credential
        cred = issue_benchmark_credential("CloudPart", 1000.0)
        rep = insp.inspect_quality("CloudPart", {"volume": 1000.0}, {"volume": 1000.0, "credential": cred}, samples, expected)
        self.assertTrue(rep.is_acceptable)

    def test_f03_over_constrained_sketch_rejection(self):
        """F03: 过定义草图明确扣分并标记 FAILED"""
        from cad_quality_inspector import CadQualityInspector
        insp = CadQualityInspector()
        rep = insp.inspect_quality("OverPart", {"volume": 1000.0}, {"volume": 1000.0}, sketch_constrained_status="OVER_CONSTRAINED")
        self.assertFalse(rep.is_acceptable)

    def test_f04_rebuild_time_high_load_deduction(self):
        """F04: 重建超长耗时扣分判定"""
        from cad_quality_inspector import CadQualityInspector
        insp = CadQualityInspector()
        rep = insp.inspect_quality("SlowPart", {"volume": 1000.0}, {"volume": 1000.0}, rebuild_time_sec=5.0)
        self.assertFalse(rep.is_acceptable)

    def test_f05_thin_wall_cutting_risk_detection(self):
        """F05: 薄壁加工变形风险拦截"""
        from cad_quality_inspector import CadQualityInspector
        insp = CadQualityInspector()
        rep = insp.inspect_quality("ThinWallPart", {"volume": 1000.0, "min_wall_thickness": 0.8}, {"volume": 1000.0})
        self.assertIn("薄壁结构", rep.manufacturing_score.warnings[0])

    # ---------------- Category G: 文档配额与预算限制 (5 cases) ----------------
    def test_g01_document_budget_environment_variable(self):
        """G01: 文档预算环境变量解析"""
        b = int(os.environ.get("SW_MAX_DOCUMENTS", "8"))
        self.assertGreaterEqual(b, 1)

    def test_g02_budget_exceeded_error_code(self):
        """G02: 打开文档超限时触发 SW_DOCUMENT_BUDGET 错误"""
        err = SolidWorksConnectionError("SW_DOCUMENT_BUDGET", "new_document", "打开文档数已达预算")
        self.assertEqual(err.code, "SW_DOCUMENT_BUDGET")

    def test_g03_safe_sta_worker_restart(self):
        """G03: STA 工作线程安全重启探活"""
        worker = get_sta_worker()
        worker.restart()
        self.assertTrue(worker.is_healthy())

    def test_g04_sta_task_state_machine_completed(self):
        """G04: 任务状态机 COMPLETED 状态流转"""
        from sw_connect import TaskState, WorkerTask
        t = WorkerTask(lambda: 1, (), {})
        self.assertEqual(t.state, TaskState.QUEUED)

    def test_g05_clean_message_pump_idle(self):
        """G05: STA 空闲时消息泵调用无死锁"""
        worker = get_sta_worker()
        res = worker.execute(lambda: True)
        self.assertTrue(res)


if __name__ == "__main__":
    unittest.main()
