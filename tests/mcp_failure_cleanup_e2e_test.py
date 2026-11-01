# -*- coding: utf-8 -*-
"""
tests/mcp_failure_cleanup_e2e_test.py
真实 MCP 工具入口调用链、失败自动回滚、文档生命周期与已有文档保护端到端测试。
涵盖：
1. 真实 MCP 入口新建零件故障回滚与重试（solidworks_create_basic_part）；
2. 真实 MCP 入口已有零件失败草图自动逆序清理（solidworks_sketch_and_extrude）；
3. 已有用户 CAD 资产保护测试（验证原有几何、尺寸、特征 100% 不受破坏）；
4. 清理失败熔断测试（验证 CLEANUP_FAILED 状态下严格阻断重试）。
"""

import json
import math
import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"
SERVER_DIR = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "mcp-server"

for p in (str(SERVER_DIR), str(SCRIPTS_DIR), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

SANDBOX_DIR = REPO_ROOT / "测试代码" / "sandbox_benchmark"
SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
os.environ["DSH_ALLOWED_ROOTS"] = json.dumps([str(SANDBOX_DIR)])

from sw_connect import connect_solidworks, get_com_member, get_sta_worker, new_document, save_document, mm
from sw_part import sketch_rectangle, extrude_boss
from sw_measure import collect_mass_properties
from dimension_manager import iter_all_features
from cad_task_context import (
    CADTaskContext,
    CADTaskRollbackManager,
    FeatureCleanupManager,
    DocumentLifecycleManager,
    TaskStatus,
    CleanupStatus,
    CleanupVerificationError,
)
import server
from server import (
    solidworks_create_basic_part,
    solidworks_sketch_and_extrude,
    SolidWorksCreateBasicPartInput,
    SolidWorksSketchOnPlaneInput,
    BasicPartShape,
    ResponseFormat,
)


class TestMCPFailureCleanupE2E(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.sw, _ = connect_solidworks(wait_seconds=5, visible=True)
        if cls.sw is None:
            raise unittest.SkipTest("未连接到本地 SolidWorks COM 实例，跳过端到端测试")

    def test_mcp_entry_new_document_failure_and_retry(self):
        """测试一：经过真实 MCP 工具入口 (solidworks_create_basic_part) 的故障回滚与重试。"""
        sw = self.sw
        worker = get_sta_worker()

        initial_docs = worker.execute(lambda: list(get_com_member(sw, "GetDocuments") or []))
        initial_count = len(initial_docs)

        # 1. 真实 MCP 客户端调用：传入非法基准面名称故意制造失败
        fail_params = SolidWorksCreateBasicPartInput(
            shape=BasicPartShape.BOX,
            plane_name="Invalid_Plane_Nonexistent_404",
            width_mm=80.0,
            height_mm=60.0,
            depth_mm=30.0,
            response_format=ResponseFormat.JSON,
        )
        raw_res = solidworks_create_basic_part(fail_params)
        res = json.loads(raw_res)

        # 验证 MCP 工具返回的清理结构体
        self.assertEqual(res.get("status"), "error")
        self.assertTrue(res.get("cleanup_performed"), "必须执行清理")
        self.assertTrue(res.get("cleanup_verified"), "清理必须验证成功")
        self.assertEqual(res.get("residual_documents_in_sw"), 0, "后台残留文档数必须为 0")
        self.assertTrue(res.get("ready_to_retry"), "必须标记为可安全重试")

        # 验证 SolidWorks 进程中没有遗留未命名文档
        after_fail_docs = worker.execute(lambda: list(get_com_member(sw, "GetDocuments") or []))
        self.assertEqual(len(after_fail_docs), initial_count, "失败后不得在 SolidWorks 后台残留未关闭文档")

        # 2. 从干净状态发起合法重试
        out_path = str(SANDBOX_DIR / "mcp_e2e_retry_success.SLDPRT")
        if os.path.exists(out_path):
            try:
                os.remove(out_path)
            except Exception:
                pass

        success_params = SolidWorksCreateBasicPartInput(
            shape=BasicPartShape.BOX,
            plane_name="前视基准面",
            width_mm=100.0,
            height_mm=60.0,
            depth_mm=20.0,
            output_path=out_path,
            response_format=ResponseFormat.JSON,
        )
        raw_res2 = solidworks_create_basic_part(success_params)
        res2 = json.loads(raw_res2)

        self.assertEqual(res2.get("status"), "ok")
        self.assertTrue(res2.get("feature_created"))
        self.assertTrue(os.path.exists(out_path), "最终模型必须成功落盘")

        # 清理测试文档
        worker.execute(lambda: get_com_member(sw, "CloseDoc", "mcp_e2e_retry_success.SLDPRT"))
        if os.path.exists(out_path):
            try:
                os.remove(out_path)
            except Exception:
                pass

    def test_mcp_entry_sketch_failure_cleanup(self):
        """测试二：经过真实 MCP 工具入口 (solidworks_sketch_and_extrude) 的失败草图自动逆序清理。"""
        sw = self.sw

        def run_test():
            # 1. 先创建一个合法的基础模型
            model = new_document(sw, "part")
            title = get_com_member(model, "GetTitle")

            try:
                from tests.failure_injection_test import safe_start_sketch
                safe_start_sketch(model, "前视基准面")
                sketch_rectangle(model, 0.0, 0.0, mm(100), mm(60))
                extrude_boss(model, None, mm(20))
                get_com_member(model, "ForceRebuild3", False)

                initial_features = {get_com_member(f, "Name") for f in iter_all_features(model)}
                initial_count = len(initial_features)

                # 2. 调用 solidworks_sketch_and_extrude 传入非法基准面制造失败
                fail_params = SolidWorksSketchOnPlaneInput(
                    plane_name="Nonexistent_Plane_XYZ",
                    shape="circle",
                    radius_mm=10.0,
                    depth_mm=15.0,
                    response_format=ResponseFormat.JSON,
                )
                raw_res = solidworks_sketch_and_extrude(fail_params)
                res = json.loads(raw_res)

                self.assertEqual(res.get("status"), "error")

                # 3. 验证零件特征树中没有残留任何破损草图或特征
                current_features = {get_com_member(f, "Name") for f in iter_all_features(model)}
                self.assertEqual(len(current_features), initial_count, "模型中不得残留失败草图")
                self.assertEqual(current_features, initial_features, "特征树集合必须 100% 保持一致")

            finally:
                get_com_member(sw, "CloseDoc", title)

        get_sta_worker().execute(run_test)

    def test_existing_customer_asset_protection(self):
        """测试三：已有用户 CAD 资产保护测试（验证几何、尺寸、特征 100% 不受破坏）。"""
        sw = self.sw
        customer_asset_path = str(SANDBOX_DIR / "customer_original_asset.SLDPRT")

        def run_test():
            # 1. 准备用户已有零件：长方体 80 x 50 x 25 mm，保存至磁盘
            model = new_document(sw, "part")
            from tests.failure_injection_test import safe_start_sketch
            safe_start_sketch(model, "前视基准面")
            sketch_rectangle(model, 0.0, 0.0, mm(80), mm(50))
            extrude_boss(model, None, mm(25))
            get_com_member(model, "ForceRebuild3", False)
            save_document(model, customer_asset_path)

            # 记录任务开始前的基线数据
            initial_features = [get_com_member(f, "Name") for f in iter_all_features(model)]
            initial_feature_count = len(initial_features)
            mass_before = collect_mass_properties(model)
            initial_volume = mass_before.get("volume_mm3")
            # 理论体积: 80 * 50 * 25 = 100000.0 mm³
            self.assertAlmostEqual(initial_volume, 100000.0, delta=0.01)

            # 2. 发起一次建模任务，登记为已有文档 (is_newly_created=False)
            ctx = CADTaskContext(task_id="protect_customer_asset_task", max_retries=1)
            doc_entry = ctx.register_document(model, path=customer_asset_path, is_newly_created=False)
            rollback_mgr = CADTaskRollbackManager(ctx, sw_app=sw)

            # 在该文档上创建了一个新草图和一个特征，随后故意抛出异常
            try:
                safe_start_sketch(model, "前视基准面")
                sketch_rectangle(model, 0.0, 0.0, mm(20), mm(20))
                sk_name = None
                try:
                    sk_mgr = getattr(model, "SketchManager", None)
                    if sk_mgr:
                        active_sk = get_com_member(sk_mgr, "ActiveSketch")
                        if active_sk:
                            sk_name = get_com_member(active_sk, "Name")
                except Exception:
                    pass
                ctx.register_feature(sk_name or "草图2", "SKETCH", doc_entry.title)
                # 模拟后续建模中途失败
                raise RuntimeError("业务建模中途几何崩溃异常")
            except Exception as exc:
                # 触发任务回滚
                ctx.status = TaskStatus.FAILED
                cleanup_ok = rollback_mgr.rollback()
                self.assertTrue(cleanup_ok, "回滚必须成功")

            # 3. 严格核实已有用户资产数据
            # 验证 1: 原有文档未被关闭
            open_titles = [str(get_com_member(d, "GetTitle") or "") for d in list(get_com_member(sw, "GetDocuments") or [])]
            self.assertIn("customer_original_asset.SLDPRT", open_titles, "已有用户文档绝不能被意外关闭")

            # 验证 2: 重新获取特征列表，验证临时草图已被清理，原有特征完好无损
            after_features = [get_com_member(f, "Name") for f in iter_all_features(model)]
            self.assertEqual(len(after_features), initial_feature_count, "已有文档特征数必须完全一致")
            self.assertEqual(set(after_features), set(initial_features), "原有特征集合必须 100% 保留")

            # 验证 3: 几何质量属性与体积完全无损
            mass_after = collect_mass_properties(model)
            final_volume = mass_after.get("volume_mm3")
            self.assertAlmostEqual(final_volume, initial_volume, delta=0.001, msg="已有零件体积发生变异，几何受到破坏！")

            # 安全清理测试文件
            get_com_member(sw, "CloseDoc", "customer_original_asset.SLDPRT")
            if os.path.exists(customer_asset_path):
                try:
                    os.remove(customer_asset_path)
                except Exception:
                    pass

        get_sta_worker().execute(run_test)

    def test_cleanup_failure_circuit_breaker(self):
        """测试四：清理失败时的熔断机制验证（阻止盲目重试，保留诊断信息）。"""
        ctx = CADTaskContext(task_id="circuit_breaker_test", max_retries=2)
        mgr = CADTaskRollbackManager(ctx)

        # 模拟清理验证失败（例如遇到文件独占锁或 COM 拒绝）
        mgr.rollback = lambda: False

        def always_failing_task(context):
            raise RuntimeError("建模抛出异常")

        # 验证：熔断机制必须抛出 CleanupVerificationError，严禁继续自动重试
        with self.assertRaises(CleanupVerificationError) as err:
            mgr.execute_with_retry(always_failing_task)

        self.assertIn("严禁盲目重试", str(err.exception))
        self.assertEqual(ctx.status, TaskStatus.CLEANUP_FAILED)
        self.assertEqual(ctx.retry_count, 0, "清理未成功时，重试计数必须为 0，绝对禁止重试")
        self.assertFalse(ctx.can_retry(), "can_retry 必须返回 False")


if __name__ == "__main__":
    unittest.main()
