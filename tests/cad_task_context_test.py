# -*- coding: utf-8 -*-
"""
tests/cad_task_context_test.py
CAD 任务上下文、失败自动清理与安全重试状态机单元测试。
"""

import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"
for p in (str(SCRIPTS_DIR), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from cad_task_context import (
    CADTaskContext,
    CADTaskRollbackManager,
    FeatureCleanupManager,
    DocumentLifecycleManager,
    TaskStatus,
    CleanupStatus,
    CleanupVerificationError,
    PROTECTED_FEATURE_NAMES,
)
from feature_graph_ir import (
    FeatureGraphIR,
    FeatureNode,
    FeatureType,
    NodeStatus,
)


class MockCOMFeature:
    def __init__(self, name: str, ftype: str = "BODYFEATURE"):
        self.Name = name
        self._ftype = ftype
        self.selected = False
        self.deleted = False

    def GetTypeName2(self):
        return self._ftype

    def Select2(self, append, mark):
        self.selected = True
        return True


class MockModelDoc:
    def __init__(self, title: str = "MockPart1"):
        self.title = title
        self.features = [
            MockCOMFeature("前视基准面", "RefPlane"),
            MockCOMFeature("上视基准面", "RefPlane"),
            MockCOMFeature("右视基准面", "RefPlane"),
            MockCOMFeature("原点", "OriginProfileFeature"),
            MockCOMFeature("材质", "MaterialFolder"),
        ]
        self.edit_undo_called = 0
        self.selection_cleared = False
        self.rebuilt = False

    def GetTitle(self):
        return self.title

    def GetPathName(self):
        return ""

    def GetFeatureCount(self):
        return len(self.features)

    def FeatureByName(self, name):
        for f in self.features:
            if f.Name == name and not f.deleted:
                return f
        return None

    def EditDelete(self):
        for f in self.features:
            if f.selected and not f.deleted:
                f.deleted = True
                f.selected = False
                return True
        return False

    def EditUndo(self):
        self.edit_undo_called += 1
        if self.features:
            self.features.pop()
        return True

    def ForceRebuild3(self, flag):
        self.rebuilt = True
        return True

    def ClearSelection2(self, flag):
        self.selection_cleared = True
        for f in self.features:
            f.selected = False
        return True


class MockSolidWorksApp:
    def __init__(self):
        self.documents = []

    def GetDocuments(self):
        return list(self.documents)

    def CloseDoc(self, title):
        self.documents = [d for d in self.documents if d.GetTitle() != title]
        return True


class TestCADTaskContext(unittest.TestCase):

    def test_task_context_initialization(self):
        ctx = CADTaskContext(task_id="test_001", max_retries=2)
        self.assertEqual(ctx.task_id, "test_001")
        self.assertEqual(ctx.status, TaskStatus.PENDING)
        self.assertEqual(ctx.cleanup_status, CleanupStatus.CLEAN)
        self.assertEqual(ctx.max_retries, 2)
        self.assertEqual(ctx.retry_count, 0)
        self.assertFalse(ctx.can_retry())

    def test_protected_features_whitelist(self):
        # 固有基准面与原点必须受绝对保护
        self.assertTrue(FeatureCleanupManager.is_protected_feature("Front Plane"))
        self.assertTrue(FeatureCleanupManager.is_protected_feature("前视基准面"))
        self.assertTrue(FeatureCleanupManager.is_protected_feature("上视基准面"))
        self.assertTrue(FeatureCleanupManager.is_protected_feature("右视基准面"))
        self.assertTrue(FeatureCleanupManager.is_protected_feature("Origin"))
        self.assertTrue(FeatureCleanupManager.is_protected_feature("原点"))
        self.assertTrue(FeatureCleanupManager.is_protected_feature("材质"))

        # 用户原有的固有特征也在保护白名单中
        initial_set = {"BasePlate_Old", "BossExtrude1_Old"}
        self.assertTrue(FeatureCleanupManager.is_protected_feature("BasePlate_Old", initial_set=initial_set))

        # 新增的特征不在保护名单
        self.assertFalse(FeatureCleanupManager.is_protected_feature("FailedSketch1", initial_set=initial_set))
        self.assertFalse(FeatureCleanupManager.is_protected_feature("Boss-Extrude2", initial_set=initial_set))

    def test_state_machine_happy_path(self):
        ctx = CADTaskContext(task_id="test_happy")
        mgr = CADTaskRollbackManager(ctx)

        def dummy_task(context):
            context.register_feature("Sketch1", "SKETCH")
            return "SUCCESS_MODEL"

        res = mgr.execute_with_retry(dummy_task)
        self.assertEqual(res, "SUCCESS_MODEL")
        self.assertEqual(ctx.status, TaskStatus.COMPLETED)
        self.assertEqual(ctx.cleanup_status, CleanupStatus.CLEAN)
        self.assertEqual(ctx.retry_count, 0)

    def test_state_machine_retry_flow(self):
        ctx = CADTaskContext(task_id="test_retry", max_retries=2)
        sw = MockSolidWorksApp()
        doc = MockModelDoc("NewPart1")
        sw.documents.append(doc)
        mgr = CADTaskRollbackManager(ctx, sw_app=sw)

        attempt = 0

        def failing_then_succeeding_task(context):
            nonlocal attempt
            attempt += 1
            # 登记新文档
            context.register_document(doc, is_newly_created=True)
            if attempt == 1:
                raise RuntimeError("首次拉伸参数非法，模拟建模失败")
            return "RETRY_SUCCESS"

        res = mgr.execute_with_retry(failing_then_succeeding_task)
        self.assertEqual(res, "RETRY_SUCCESS")
        self.assertEqual(attempt, 2)
        self.assertEqual(ctx.retry_count, 1)
        self.assertEqual(ctx.status, TaskStatus.COMPLETED)

    def test_cleanup_failed_prohibits_retry(self):
        ctx = CADTaskContext(task_id="test_cleanup_fail", max_retries=2)
        mgr = CADTaskRollbackManager(ctx)

        # 模拟 rollback 返回 False（例如文件锁死或文档无法关闭）
        mgr.rollback = lambda: False

        def always_fail(context):
            raise RuntimeError("建模崩溃")

        with self.assertRaises(CleanupVerificationError):
            mgr.execute_with_retry(always_fail)

        self.assertEqual(ctx.status, TaskStatus.CLEANUP_FAILED)
        self.assertEqual(ctx.retry_count, 0)  # 严格禁止进入重试

    def test_max_retries_limit(self):
        ctx = CADTaskContext(task_id="test_max_retry", max_retries=1)
        sw = MockSolidWorksApp()
        mgr = CADTaskRollbackManager(ctx, sw_app=sw)

        attempts = 0

        def always_fail_task(context):
            nonlocal attempts
            attempts += 1
            doc = MockModelDoc(f"Part_{attempts}")
            context.register_document(doc, is_newly_created=True)
            raise RuntimeError(f"反复几何自交第 {attempts} 次")

        with self.assertRaises(RuntimeError):
            mgr.execute_with_retry(always_fail_task)

        # 初始 1 次 + 重试 1 次 = 共 2 次尝试
        self.assertEqual(attempts, 2)
        self.assertEqual(ctx.status, TaskStatus.ABORTED)
        self.assertEqual(ctx.retry_count, 1)

    def test_feature_reverse_cleanup_on_existing_document(self):
        doc = MockModelDoc("ExistingCustomerPart")
        initial_count = len(doc.features)

        ctx = CADTaskContext(task_id="task_existing_doc")
        doc_entry = ctx.register_document(doc, is_newly_created=False)

        # 模拟在已有零件上创建了基准面、草图和拉伸
        plane_feat = MockCOMFeature("Plane1", "RefPlane")
        sketch_feat = MockCOMFeature("Sketch1", "SKETCH")
        boss_feat = MockCOMFeature("Boss-Extrude1", "BODYFEATURE")

        doc.features.extend([plane_feat, sketch_feat, boss_feat])
        ctx.register_feature("Plane1", "REFERENCE_PLANE", doc_entry.title)
        ctx.register_feature("Sketch1", "SKETCH", doc_entry.title)
        ctx.register_feature("Boss-Extrude1", "BODYFEATURE", doc_entry.title)

        # 执行逆序特征清理
        cleaned_count, cleaned_names = FeatureCleanupManager.cleanup_document_features(
            doc, doc_entry, ctx.tracked_features
        )

        self.assertEqual(cleaned_count, 3)
        # 逆序验证：后创建的先清理
        self.assertEqual(cleaned_names, ["Boss-Extrude1", "Sketch1", "Plane1"])

        # 验证原有特征（前视/上视/右视/原点/材质）100% 完好无损
        active_features = [f for f in doc.features if not f.deleted]
        self.assertEqual(len(active_features), initial_count)
        self.assertTrue(all(f.Name in doc_entry.initial_feature_names for f in active_features))

    def test_new_document_closed_and_purged(self):
        sw = MockSolidWorksApp()
        doc = MockModelDoc("NewFailedPart")
        sw.documents.append(doc)

        ctx = CADTaskContext(task_id="task_purge_new")
        doc_entry = ctx.register_document(doc, is_newly_created=True)

        self.assertFalse(DocumentLifecycleManager.verify_document_closed(sw, "NewFailedPart"))

        closed_ok = DocumentLifecycleManager.close_and_purge_document(sw, doc_entry, ctx)
        self.assertTrue(closed_ok)
        self.assertTrue(doc_entry.closed)
        self.assertTrue(doc_entry.cleaned)
        # 验证已从 SolidWorks 内存列表完全移除
        self.assertTrue(DocumentLifecycleManager.verify_document_closed(sw, "NewFailedPart"))
        self.assertEqual(len(sw.documents), 0)

    def test_feature_graph_failure_evaluation(self):
        ir = FeatureGraphIR(graph_id="fg_test")
        ir.add_node(FeatureNode(id="n1", type=FeatureType.SKETCH_2D, name="Sketch1", status=NodeStatus.SUCCEEDED, created_cad_entity="Sketch1"))
        ir.add_node(FeatureNode(id="n2", type=FeatureType.EXTRUDE_BOSS, name="Boss1", depends_on=["n1"], status=NodeStatus.SUCCEEDED, created_cad_entity="Boss1"))
        # 节点 n3 在执行时失败
        ir.add_node(FeatureNode(id="n3", type=FeatureType.SKETCH_2D, name="Sketch2", depends_on=["n2"], status=NodeStatus.RUNNING, created_cad_entity="Sketch2"))
        # 节点 n4 依赖 n3，尚未执行
        ir.add_node(FeatureNode(id="n4", type=FeatureType.EXTRUDE_CUT, name="Cut1", depends_on=["n3"], status=NodeStatus.PENDING))

        eval_res = ir.evaluate_failure_and_rollback("n3")

        # n1 和 n2 必须安全保留
        self.assertIn("n1", eval_res["nodes_retained"])
        self.assertIn("n2", eval_res["nodes_retained"])
        # n4 必须标记为跳过
        self.assertIn("n4", eval_res["nodes_skipped"])
        self.assertEqual(ir.nodes["n4"].status, NodeStatus.SKIPPED)
        # n3 的 CAD 实体必须标记待删除
        entities_to_delete = [item["cad_entity"] for item in eval_res["entities_to_delete_reversed"]]
        self.assertIn("Sketch2", entities_to_delete)
        self.assertEqual(ir.nodes["n3"].status, NodeStatus.FAILED)


if __name__ == "__main__":
    unittest.main()
