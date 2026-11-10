# -*- coding: utf-8 -*-
"""
tests/mcp_mid_operation_failure_test.py
真实 CAD 中途故障注入、事务回滚、清理验证与安全重试专项测试套件。

严格遵循"真实 CAD 副作用已发生 -> 中途故障注入 -> 自动逆序清理 -> 验证彻底清除 -> 安全重试"证据链。
涵盖 7 大真实 CAD 中途故障注入场景及端到端真实 MCP 重试与已有文档保护。
"""

import json
import os
import sys
import time
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

from sw_connect import (
    connect_solidworks,
    get_com_member,
    get_sta_worker,
    new_document,
    save_document,
    mm,
)
from sw_part import (
    sketch_rectangle,
    sketch_circle,
    extrude_boss,
    extrude_cut,
)
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
    SolidWorksCreateBasicPartInput,
    BasicPartShape,
    ResponseFormat,
)


class TestMCPMidOperationFailure(unittest.TestCase):
    """真实 CAD 中途故障注入与安全清理全套专项验收用例。"""

    @classmethod
    def setUpClass(cls):
        from sw_connect import solidworks_processes
        if not solidworks_processes():
            raise unittest.SkipTest("未检测到运行中的 SolidWorks 进程，跳过实机物理测试以保护待机基线")
        cls.sw, _ = connect_solidworks(wait_seconds=5, visible=True)
        if cls.sw is None:
            raise unittest.SkipTest("未连接到本地 SolidWorks COM 实例，跳过端到端测试")
        cls.worker = get_sta_worker()

    def test_01_mid_failure_after_document_creation(self):
        """测试 1：新建文档后中途故障（文档已真实创建并存在，后续建模失败触发彻底关闭销毁）。"""
        sw = self.sw
        worker = self.worker

        def run():
            initial_docs = list(get_com_member(sw, "GetDocuments") or [])
            initial_count = len(initial_docs)

            ctx = CADTaskContext(task_id="mid_fail_doc_creation", max_retries=1)
            rollback_mgr = CADTaskRollbackManager(ctx, sw_app=sw)

            # 1. 真实创建 CAD 零件文档
            model = new_document(sw, "part")
            title = get_com_member(model, "GetTitle")
            doc_entry = ctx.register_document(model, is_newly_created=True)

            # 2. 证据：SolidWorks 中真实存在该文档
            current_docs = list(get_com_member(sw, "GetDocuments") or [])
            current_titles = [get_com_member(d, "GetTitle") for d in current_docs]
            self.assertEqual(len(current_docs), initial_count + 1)
            self.assertIn(title, current_titles, "新零件必须在 SolidWorks 实际打开列表中")

            # 3. 中途注入异常（模拟后续建模或参数计算崩溃）
            try:
                raise RuntimeError("中途注入故障：创建文档后在特征构建前崩溃")
            except Exception:
                ctx.status = TaskStatus.FAILED
                cleanup_ok = rollback_mgr.rollback()
                self.assertTrue(cleanup_ok, "回滚清理必须成功")

            # 4. 验证：SolidWorks 进程中该文档已被彻底关闭，后台文档数恢复初始状态
            after_docs = list(get_com_member(sw, "GetDocuments") or [])
            after_titles = [get_com_member(d, "GetTitle") for d in after_docs]
            self.assertEqual(len(after_docs), initial_count, "失败后后台残留文档数必须为 0")
            self.assertNotIn(title, after_titles, "该未完成文档必须已从 SolidWorks 中彻底移除")

        worker.execute(run, timeout=60)

    def test_02_mid_failure_after_plane_creation(self):
        """测试 2：创建基准面后中途故障（新基准面已进入特征树，后续失败触发逆序清除，默认基准面受保护）。"""
        sw = self.sw
        worker = self.worker

        def run():
            model = new_document(sw, "part")
            title = get_com_member(model, "GetTitle")
            ctx = CADTaskContext(task_id="mid_fail_plane_creation", max_retries=1)
            doc_entry = ctx.register_document(model, is_newly_created=False)
            rollback_mgr = CADTaskRollbackManager(ctx, sw_app=sw)

            try:
                initial_features = {get_com_member(f, "Name") for f in iter_all_features(model)}

                # 1. 真实创建一个偏置基准面
                front_plane = get_com_member(model, "FeatureByName", "前视基准面") or get_com_member(model, "FeatureByName", "Front Plane")
                self.assertIsNotNone(front_plane, "前视基准面必须存在")
                get_com_member(front_plane, "Select2", False, 0)
                feat_mgr = model.FeatureManager
                plane_feat = feat_mgr.InsertRefPlane(8, mm(50), 0, 0, 0, 0)
                self.assertIsNotNone(plane_feat, "偏置基准面必须成功创建")
                plane_name = get_com_member(plane_feat, "Name")

                # 2. 证据：确认新基准面真实进入特征树
                ctx.register_feature(plane_name, "REFERENCE_PLANE", doc_entry.title)
                feat_in_tree = get_com_member(model, "FeatureByName", plane_name)
                self.assertIsNotNone(feat_in_tree, "新增基准面必须实际存在于特征树中")

                # 3. 在基准面已创建后注入中途异常
                try:
                    raise RuntimeError("中途注入故障：基准面已生成，在下一阶段特征操作中崩溃")
                except Exception:
                    ctx.status = TaskStatus.FAILED
                    cleanup_ok = rollback_mgr.rollback()
                    self.assertTrue(cleanup_ok, "回滚清理必须成功")

                # 4. 验证：新增基准面被物理删除，默认基准面完好保留
                after_feat = get_com_member(model, "FeatureByName", plane_name)
                self.assertIsNone(after_feat, "新增基准面必须已被物理删除")

                current_features = {get_com_member(f, "Name") for f in iter_all_features(model)}
                self.assertEqual(current_features, initial_features, "系统默认基准面与初始特征树必须完全保留")

            finally:
                get_com_member(sw, "CloseDoc", title)

        worker.execute(run, timeout=60)

    def test_03_mid_failure_after_sketch_creation(self):
        """测试 3：创建草图后中途故障（真实进入草图并创建几何实体，退出草图编辑态，逆序清除失败草图及实体）。"""
        sw = self.sw
        worker = self.worker

        def run():
            model = new_document(sw, "part")
            title = get_com_member(model, "GetTitle")
            ctx = CADTaskContext(task_id="mid_fail_sketch_creation", max_retries=1)
            doc_entry = ctx.register_document(model, is_newly_created=False)
            rollback_mgr = CADTaskRollbackManager(ctx, sw_app=sw)

            try:
                initial_features = {get_com_member(f, "Name") for f in iter_all_features(model)}

                # 1. 真实进入草图并绘制几何实体
                front_plane = get_com_member(model, "FeatureByName", "前视基准面") or get_com_member(model, "FeatureByName", "Front Plane")
                get_com_member(front_plane, "Select2", False, 0)
                sk_mgr = model.SketchManager
                sk_mgr.InsertSketch(True)

                # 绘制一个中心矩形
                rect_ret = sketch_rectangle(model, 0.0, 0.0, mm(80), mm(50))
                self.assertIsNotNone(rect_ret, "草图实体线段必须成功生成")

                active_sk = get_com_member(sk_mgr, "ActiveSketch")
                self.assertIsNotNone(active_sk, "必须处于活跃草图编辑状态")
                sk_name = get_com_member(active_sk, "Name")
                ctx.register_feature(sk_name, "SKETCH", doc_entry.title)

                # 2. 证据：草图处于编辑态且草图对象真实存在
                self.assertTrue(bool(get_com_member(sk_mgr, "ActiveSketch")), "草图编辑态已真实激活")

                # 3. 中途注入异常（模拟在草图编辑完成但未拉伸时崩溃）
                try:
                    raise RuntimeError("中途注入故障：草图实体已产生，在拉伸前几何自交崩溃")
                except Exception:
                    ctx.status = TaskStatus.FAILED
                    cleanup_ok = rollback_mgr.rollback()
                    self.assertTrue(cleanup_ok, "回滚清理必须成功")

                # 4. 验证：必须安全退出草图编辑态，失败草图彻底清除，特征树无残留
                self.assertIsNone(get_com_member(sk_mgr, "ActiveSketch"), "回滚后绝不能残留草图编辑态")
                after_sk_feat = get_com_member(model, "FeatureByName", sk_name)
                self.assertIsNone(after_sk_feat, "失败草图必须从特征树中物理清除")

                current_features = {get_com_member(f, "Name") for f in iter_all_features(model)}
                self.assertEqual(current_features, initial_features, "特征树必须恢复初始干净基线")

            finally:
                get_com_member(sw, "CloseDoc", title)

        worker.execute(run, timeout=60)

    def test_04_mid_failure_after_extrude_boss_success(self):
        """测试 4：拉伸成功后中途故障（实体已进入特征树且体积大于 0，后续切除失败触发逆序清理实体）。"""
        sw = self.sw
        worker = self.worker

        def run():
            model = new_document(sw, "part")
            title = get_com_member(model, "GetTitle")
            ctx = CADTaskContext(task_id="mid_fail_extrude_boss", max_retries=1)
            doc_entry = ctx.register_document(model, is_newly_created=False)
            rollback_mgr = CADTaskRollbackManager(ctx, sw_app=sw)

            try:
                initial_features = {get_com_member(f, "Name") for f in iter_all_features(model)}

                # 1. 真实创建草图并拉伸 100 x 60 x 30 mm
                front_plane = get_com_member(model, "FeatureByName", "前视基准面") or get_com_member(model, "FeatureByName", "Front Plane")
                get_com_member(front_plane, "Select2", False, 0)
                model.SketchManager.InsertSketch(True)
                sketch_rectangle(model, 0.0, 0.0, mm(100), mm(60))
                sk_name = get_com_member(model.SketchManager.ActiveSketch, "Name")
                ctx.register_feature(sk_name, "SKETCH", doc_entry.title)

                boss_feat = extrude_boss(model, None, mm(30))
                self.assertIsNotNone(boss_feat, "拉伸实体必须成功生成")
                boss_name = get_com_member(boss_feat, "Name")
                ctx.register_feature(boss_name, "BODYFEATURE", doc_entry.title)
                get_com_member(model, "ForceRebuild3", False)

                # 2. 证据：实体特征已在特征树中，物理体积产生
                mass = collect_mass_properties(model)
                vol = mass.get("volume_mm3", 0.0)
                # 理论体积: 100 * 60 * 30 = 180000 mm³
                self.assertAlmostEqual(vol, 180000.0, delta=1.0)
                self.assertIsNotNone(get_com_member(model, "FeatureByName", boss_name))

                # 3. 实体已成功存在后，在后续操作中注入中途异常
                try:
                    raise RuntimeError("中途注入故障：拉伸凸台已生成，后续切除或倒角计算失败")
                except Exception:
                    ctx.status = TaskStatus.FAILED
                    cleanup_ok = rollback_mgr.rollback()
                    self.assertTrue(cleanup_ok, "回滚清理必须成功")

                # 4. 验证：拉伸实体被逆序彻底清理，体积恢复为 0，特征树恢复初始基线
                self.assertIsNone(get_com_member(model, "FeatureByName", boss_name), "拉伸特征必须已被物理删除")
                mass_after = collect_mass_properties(model)
                self.assertAlmostEqual(mass_after.get("volume_mm3", 0.0), 0.0, delta=0.01)

                current_features = {get_com_member(f, "Name") for f in iter_all_features(model)}
                self.assertEqual(current_features, initial_features, "特征树恢复初始干净状态")

            finally:
                get_com_member(sw, "CloseDoc", title)

        worker.execute(run, timeout=60)

    def test_05_mid_failure_after_extrude_cut_success(self):
        """测试 5：切除成功后中途故障（测试基体上切除已使体积发生变化，后续验证失败触发逆序回滚恢复原体积）。"""
        sw = self.sw
        worker = self.worker

        def run():
            model = new_document(sw, "part")
            title = get_com_member(model, "GetTitle")

            try:
                # 1. 建立基础零件：100 x 60 x 20 mm 长方体（体积 120,000 mm³）
                front_plane = get_com_member(model, "FeatureByName", "前视基准面") or get_com_member(model, "FeatureByName", "Front Plane")
                get_com_member(front_plane, "Select2", False, 0)
                model.SketchManager.InsertSketch(True)
                sketch_rectangle(model, 0.0, 0.0, mm(100), mm(60))
                extrude_boss(model, None, mm(20))
                get_com_member(model, "ForceRebuild3", False)

                baseline_features = {get_com_member(f, "Name") for f in iter_all_features(model)}
                baseline_mass = collect_mass_properties(model)
                initial_volume = baseline_mass.get("volume_mm3", 0.0)
                self.assertAlmostEqual(initial_volume, 120000.0, delta=1.0)

                # 2. 发起新建模任务：切除一个直径 20mm 的通孔
                ctx = CADTaskContext(task_id="mid_fail_cut_task", max_retries=1)
                doc_entry = ctx.register_document(model, is_newly_created=False)
                rollback_mgr = CADTaskRollbackManager(ctx, sw_app=sw)

                get_com_member(front_plane, "Select2", False, 0)
                model.SketchManager.InsertSketch(True)
                sketch_circle(model, 0.0, 0.0, mm(10)) # 半径 10mm
                cut_sk_name = get_com_member(model.SketchManager.ActiveSketch, "Name")
                ctx.register_feature(cut_sk_name, "SKETCH", doc_entry.title)

                cut_feat = extrude_cut(model, None, mm(20), direction=False)
                self.assertIsNotNone(cut_feat, "切除特征必须成功生成")
                cut_name = get_com_member(cut_feat, "Name")
                ctx.register_feature(cut_name, "BODYFEATURE", doc_entry.title)
                get_com_member(model, "ForceRebuild3", False)

                # 3. 证据：切除已发生，物理体积真实减少
                # 切除圆柱体积: pi * 10^2 * 20 ≈ 6283.185 mm³
                # 预期体积: 120000 - 6283.185 ≈ 113716.81 mm³
                cut_mass = collect_mass_properties(model)
                cut_volume = cut_mass.get("volume_mm3", 0.0)
                self.assertLess(cut_volume, initial_volume - 5000.0, "体积必须发生真实切除减少")

                # 4. 在切除成功之后注入后续异常（模拟工程规范校验失败）
                try:
                    raise RuntimeError("中途注入故障：切除已完成，后续 DFM 制造准则检查不通过")
                except Exception:
                    ctx.status = TaskStatus.FAILED
                    cleanup_ok = rollback_mgr.rollback()
                    self.assertTrue(cleanup_ok, "回滚清理必须成功")

                # 5. 验证：切除特征已被逆序删除，体积无损恢复至 120,000 mm³
                self.assertIsNone(get_com_member(model, "FeatureByName", cut_name), "切除特征必须已被删除")
                recovered_mass = collect_mass_properties(model)
                self.assertAlmostEqual(recovered_mass.get("volume_mm3", 0.0), initial_volume, delta=0.01)

                current_features = {get_com_member(f, "Name") for f in iter_all_features(model)}
                self.assertEqual(current_features, baseline_features, "特征树完全恢复到切除前的干净基线")

            finally:
                get_com_member(sw, "CloseDoc", title)

        worker.execute(run, timeout=60)

    def test_06_mid_failure_rebuild_error_recovery(self):
        """测试 6：ForceRebuild3 重建阶段故障（模拟几何拓扑重构失败触发回滚与干净恢复）。"""
        sw = self.sw
        worker = self.worker

        def run():
            model = new_document(sw, "part")
            title = get_com_member(model, "GetTitle")
            ctx = CADTaskContext(task_id="mid_fail_rebuild", max_retries=1)
            doc_entry = ctx.register_document(model, is_newly_created=False)
            rollback_mgr = CADTaskRollbackManager(ctx, sw_app=sw)

            try:
                initial_features = {get_com_member(f, "Name") for f in iter_all_features(model)}

                # 1. 创建草图与拉伸
                front_plane = get_com_member(model, "FeatureByName", "前视基准面") or get_com_member(model, "FeatureByName", "Front Plane")
                get_com_member(front_plane, "Select2", False, 0)
                model.SketchManager.InsertSketch(True)
                sketch_rectangle(model, 0.0, 0.0, mm(50), mm(50))
                sk_name = get_com_member(model.SketchManager.ActiveSketch, "Name")
                ctx.register_feature(sk_name, "SKETCH", doc_entry.title)
                feat = extrude_boss(model, None, mm(25))
                feat_name = get_com_member(feat, "Name")
                ctx.register_feature(feat_name, "BODYFEATURE", doc_entry.title)

                # 2. 模拟 ForceRebuild 报错或返回失败
                try:
                    rebuild_ret = bool(get_com_member(model, "ForceRebuild3", False))
                    # 人为注入重构校验失败异常
                    if rebuild_ret:
                        raise RuntimeError("重构后几何校验异常: 拓扑相交校验未通过")
                except Exception:
                    ctx.status = TaskStatus.FAILED
                    cleanup_ok = rollback_mgr.rollback()
                    self.assertTrue(cleanup_ok, "回滚清理必须成功")

                # 3. 验证特征已被逆序清理，特征树干净
                self.assertIsNone(get_com_member(model, "FeatureByName", feat_name))
                current_features = {get_com_member(f, "Name") for f in iter_all_features(model)}
                self.assertEqual(current_features, initial_features)

            finally:
                get_com_member(sw, "CloseDoc", title)

        worker.execute(run, timeout=60)

    def test_07_cleanup_operation_itself_fails_circuit_breaker(self):
        """测试 7：清理操作本身失败时的熔断机制（进入 CLEANUP_FAILED，ready_to_retry 锁定为 False，杜绝死循环）。"""
        sw = self.sw
        worker = self.worker

        def run():
            ctx = CADTaskContext(task_id="circuit_breaker_mid_fail", max_retries=3)
            rollback_mgr = CADTaskRollbackManager(ctx, sw_app=sw)

            # 1. 真实创建一个测试文档和特征
            model = new_document(sw, "part")
            title = get_com_member(model, "GetTitle")
            doc_entry = ctx.register_document(model, is_newly_created=True)

            try:
                # 2. 模拟清理操作本身发生故障（例如系统遭遇独占死锁，rollback 返回 False）
                rollback_mgr.rollback = lambda: False

                def failing_modeling_step(context):
                    raise RuntimeError("建模中途抛出不可恢复的底层崩溃")

                # 3. 验证熔断机制触发：调度器抛出 CleanupVerificationError，严禁盲目重试
                with self.assertRaises(CleanupVerificationError) as err:
                    rollback_mgr.execute_with_retry(failing_modeling_step)

                self.assertIn("严禁盲目重试", str(err.exception))
                self.assertEqual(ctx.status, TaskStatus.CLEANUP_FAILED)
                self.assertEqual(ctx.cleanup_status, CleanupStatus.CLEANUP_FAILED)
                self.assertEqual(ctx.retry_count, 0, "清理失败时重试计数必须为 0，绝对阻断自动重试")
                self.assertFalse(ctx.can_retry(), "can_retry 必须严格返回 False")

            finally:
                # 人工干预安全清理
                get_com_member(sw, "CloseDoc", title)

        worker.execute(run, timeout=60)

    def test_08_end_to_end_mcp_mid_failure_and_safe_retry(self):
        """测试 8：真实 MCP 工具入口中途故障自动清理与第二轮合法请求安全重试全流程。"""
        sw = self.sw
        worker = self.worker

        # 1. 记录初始文档状态
        initial_docs = worker.execute(lambda: list(get_com_member(sw, "GetDocuments") or []))
        initial_count = len(initial_docs)

        # 2. 第一次调用：传入非法基准面制造真实 MCP 调用中途失败
        fail_params = SolidWorksCreateBasicPartInput(
            shape=BasicPartShape.BOX,
            plane_name="Nonexistent_Plane_MidFail_999",
            width_mm=80.0,
            height_mm=60.0,
            depth_mm=30.0,
            response_format=ResponseFormat.JSON,
        )
        raw_res1 = solidworks_create_basic_part(fail_params)
        res1 = json.loads(raw_res1)

        # 检查清理验证结果
        self.assertEqual(res1.get("status"), "error")
        self.assertTrue(res1.get("cleanup_performed"), "MCP 工具必须报告 cleanup_performed=True")
        self.assertTrue(res1.get("cleanup_verified"), "清理验证必须通过")
        self.assertEqual(res1.get("residual_documents_in_sw"), 0, "后台残留文档必须为 0")
        self.assertTrue(res1.get("ready_to_retry"), "系统必须标记为可安全重试")

        # 检查 SolidWorks 实际打开文档数：必须严格等于初始数量
        after_fail_docs = worker.execute(lambda: list(get_com_member(sw, "GetDocuments") or []))
        self.assertEqual(len(after_fail_docs), initial_count, "第一次失败后后台绝不能遗留残留文档")

        # 3. 第二次调用：从干净环境中发起合法请求重试
        retry_out_path = str(SANDBOX_DIR / "mcp_mid_fail_retry_bench.SLDPRT")
        if os.path.exists(retry_out_path):
            try:
                os.remove(retry_out_path)
            except Exception:
                pass

        success_params = SolidWorksCreateBasicPartInput(
            shape=BasicPartShape.BOX,
            plane_name="前视基准面",
            width_mm=100.0,
            height_mm=50.0,
            depth_mm=25.0,
            output_path=retry_out_path,
            response_format=ResponseFormat.JSON,
        )
        raw_res2 = solidworks_create_basic_part(success_params)
        res2 = json.loads(raw_res2)

        self.assertEqual(res2.get("status"), "ok")
        self.assertTrue(res2.get("feature_created"))
        self.assertTrue(os.path.exists(retry_out_path), "重试零件必须成功在磁盘落盘")

        # 4. 验证重试后模型的几何物理属性
        def check_retry_part():
            open_model = get_com_member(sw, "GetOpenDocumentByName", retry_out_path)
            self.assertIsNotNone(open_model, "重试落盘零件必须可在 SolidWorks 中正常读取")
            mass = collect_mass_properties(open_model)
            # 理论体积: 100 * 50 * 25 = 125000 mm³
            self.assertAlmostEqual(mass.get("volume_mm3", 0.0), 125000.0, delta=1.0)
            get_com_member(sw, "CloseDoc", "mcp_mid_fail_retry_bench.SLDPRT")

        worker.execute(check_retry_part, timeout=60)
        if os.path.exists(retry_out_path):
            try:
                os.remove(retry_out_path)
            except Exception:
                pass

    def test_09_customer_asset_protection_during_mid_operation_failure(self):
        """测试 9：已有客户 CAD 文档保护（中途故障回滚后，文档保持打开、特征树 100% 保持、体积 0 误差）。"""
        sw = self.sw
        worker = self.worker
        customer_asset_path = str(SANDBOX_DIR / "customer_mid_protection_asset.SLDPRT")

        def run():
            # 1. 准备客户原有模型：长方体 80 x 50 x 25 mm，落盘并保存
            model = new_document(sw, "part")
            front_plane = get_com_member(model, "FeatureByName", "前视基准面") or get_com_member(model, "FeatureByName", "Front Plane")
            get_com_member(front_plane, "Select2", False, 0)
            model.SketchManager.InsertSketch(True)
            sketch_rectangle(model, 0.0, 0.0, mm(80), mm(50))
            extrude_boss(model, None, mm(25))
            get_com_member(model, "ForceRebuild3", False)
            save_document(model, customer_asset_path)

            # 采集任务开始前的完整物理基线数据
            baseline_features = [get_com_member(f, "Name") for f in iter_all_features(model)]
            baseline_feature_count = len(baseline_features)
            baseline_mass = collect_mass_properties(model)
            baseline_volume = baseline_mass.get("volume_mm3", 0.0)
            # 理论体积: 80 * 50 * 25 = 100000 mm³
            self.assertAlmostEqual(baseline_volume, 100000.0, delta=0.01)

            # 2. 在已有文档上发起任务（is_newly_created=False）
            ctx = CADTaskContext(task_id="protect_customer_asset_mid_fail", max_retries=1)
            doc_entry = ctx.register_document(model, path=customer_asset_path, is_newly_created=False)
            rollback_mgr = CADTaskRollbackManager(ctx, sw_app=sw)

            # 真实创建草图和特征，并在中途注入异常
            try:
                get_com_member(front_plane, "Select2", False, 0)
                model.SketchManager.InsertSketch(True)
                sketch_rectangle(model, 0.0, 0.0, mm(20), mm(20))
                sk_name = get_com_member(model.SketchManager.ActiveSketch, "Name")
                ctx.register_feature(sk_name, "SKETCH", doc_entry.title)

                # 中途注入不可逆的几何异常
                raise RuntimeError("业务建模中途几何崩溃异常")
            except Exception:
                ctx.status = TaskStatus.FAILED
                cleanup_ok = rollback_mgr.rollback()
                self.assertTrue(cleanup_ok, "回滚必须成功")

            # 3. 严格核验已有资产保护指标
            # 指标 A: 原有文档未被关闭
            open_docs = list(get_com_member(sw, "GetDocuments") or [])
            open_titles = [str(get_com_member(d, "GetTitle") or "") for d in open_docs]
            self.assertIn("customer_mid_protection_asset.SLDPRT", open_titles, "已有客户文档绝不能被意外关闭")

            # 指标 B: 特征总数与特征集合 100% 保持一致
            after_features = [get_com_member(f, "Name") for f in iter_all_features(model)]
            self.assertEqual(len(after_features), baseline_feature_count, "已有文档特征数量必须完全一致")
            self.assertEqual(set(after_features), set(baseline_features), "原有特征集合必须 100% 保留")

            # 指标 C: 几何质量属性与体积 0 误差
            after_mass = collect_mass_properties(model)
            after_volume = after_mass.get("volume_mm3", 0.0)
            self.assertAlmostEqual(after_volume, baseline_volume, delta=0.001, msg="已有零件体积发生变异！")

            # 安全清理测试物料
            get_com_member(sw, "CloseDoc", "customer_mid_protection_asset.SLDPRT")
            if os.path.exists(customer_asset_path):
                try:
                    os.remove(customer_asset_path)
                except Exception:
                    pass

        worker.execute(run, timeout=60)


if __name__ == "__main__":
    unittest.main()
