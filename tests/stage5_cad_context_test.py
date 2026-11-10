# -*- coding: utf-8 -*-
"""
tests/stage5_cad_context_test.py
Stage 5 高级 CAD 任务上下文、状态机与事务生命周期集成测试套件。

验证目标：
1. 上下文初始化与会话绑定
2. 状态机严格合法跃迁与历史审计链
3. 非法状态跃迁 Fail-Closed 阻断
4. 文档生命周期跟踪与快照基准
5. 特征多步骤跟踪与 LIFO 逆序保障
6. 任务取消请求与阻断响应
7. 回滚管理器重试边界与耗尽流转
8. 清理验证失败立即锁定 CLEANUP_FAILED 阻断盲目重试
9. 异常捕获与审计轨迹时间戳单调性
"""

import os
import sys
import time
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
    TaskStatus,
    CleanupStatus,
    CleanupVerificationError,
    InvalidStateTransitionError,
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
    def __init__(self, title: str = "MockPart_Stage5"):
        self.title = title
        self.features = [
            MockCOMFeature("Front Plane", "RefPlane"),
            MockCOMFeature("Top Plane", "RefPlane"),
            MockCOMFeature("Right Plane", "RefPlane"),
            MockCOMFeature("Origin", "OriginProfileFeature"),
        ]
        self.edit_undo_called = 0
        self.selection_cleared = False
        self.rebuilt = False

    def GetTitle(self):
        return self.title

    def GetPathName(self):
        return f"C:\\Sandbox\\{self.title}.sldprt"

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

    def ForceRebuild3(self, flag):
        self.rebuilt = True
        return True

    def ClearSelection2(self, flag):
        self.selection_cleared = True
        return True


class MockSolidWorksApp:
    def __init__(self):
        self.documents = []

    def GetDocuments(self):
        return list(self.documents)

    def CloseDoc(self, title):
        self.documents = [d for d in self.documents if d.GetTitle() != title]
        return True


class TestStage5CADContextIntegration(unittest.TestCase):

    def test_stage5_01_task_context_initialization_and_session_binding(self):
        """01: 上下文初始化、会话绑定与默认安全属性校验"""
        mock_session = {"user": "qa_operator", "session_id": "sess_stage5_001"}
        ctx = CADTaskContext(task_id="task_s5_init", max_retries=3, session=mock_session)

        self.assertEqual(ctx.task_id, "task_s5_init")
        self.assertEqual(ctx.status, TaskStatus.CREATED)
        self.assertEqual(ctx.cleanup_status, CleanupStatus.CLEAN)
        self.assertEqual(ctx.max_retries, 3)
        self.assertEqual(ctx.retry_count, 0)
        self.assertEqual(ctx.session, mock_session)
        self.assertFalse(ctx.is_cancelled())
        self.assertEqual(len(ctx.state_history), 1)
        self.assertEqual(ctx.state_history[0][0], TaskStatus.CREATED.value)

    def test_stage5_02_strict_state_machine_valid_transitions(self):
        """02: 状态机严格合法跃迁: CREATED -> RUNNING -> COMMITTING -> SUCCEEDED"""
        ctx = CADTaskContext(task_id="task_s5_fsm")

        # 合法跳转至 RUNNING
        st = ctx.transition_to(TaskStatus.RUNNING, "Starting CAD model generation")
        self.assertEqual(st, TaskStatus.RUNNING)
        self.assertEqual(ctx.status, TaskStatus.RUNNING)

        # 合法跳转至 COMMITTING
        st = ctx.transition_to(TaskStatus.COMMITTING, "Committing model geometry")
        self.assertEqual(st, TaskStatus.COMMITTING)

        # 合法跳转至 SUCCEEDED (终态)
        st = ctx.transition_to(TaskStatus.SUCCEEDED, "Model generated and verified")
        self.assertEqual(st, TaskStatus.SUCCEEDED)
        self.assertTrue(ctx.is_terminal())

        # 验证审计日志记录完整包含 4 个节点
        history_statuses = [h[0] for h in ctx.state_history]
        self.assertEqual(
            history_statuses,
            [TaskStatus.CREATED.value, TaskStatus.RUNNING.value, TaskStatus.COMMITTING.value, TaskStatus.SUCCEEDED.value]
        )

    def test_stage5_03_invalid_state_transition_fails_closed(self):
        """03: 非法状态跃迁 Fail-Closed 阻断，拒绝跨状态越级或终态逆转"""
        ctx = CADTaskContext(task_id="task_s5_invalid_fsm")

        # CREATED 不能直接跳跃到 SUCCEEDED
        with self.assertRaises(InvalidStateTransitionError):
            ctx.transition_to(TaskStatus.SUCCEEDED, "Illegal jump")

        # 转移至 RUNNING 后，转移至终态 FAILED
        ctx.transition_to(TaskStatus.RUNNING)
        ctx.transition_to(TaskStatus.FAILED, "Fatal geometry defect")

        # 终态 FAILED 严禁逆向再次跃迁到 RUNNING
        with self.assertRaises(InvalidStateTransitionError):
            ctx.transition_to(TaskStatus.RUNNING, "Illegal restart from terminal")

    def test_stage5_04_document_registration_and_tracking(self):
        """04: 文档生命周期跟踪与快照基准"""
        ctx = CADTaskContext(task_id="task_s5_doc")
        doc = MockModelDoc("EngineBlock")

        tracked_doc = ctx.register_document(doc, is_newly_created=False)
        self.assertEqual(tracked_doc.title, "EngineBlock")
        self.assertFalse(tracked_doc.is_newly_created)
        self.assertEqual(tracked_doc.initial_feature_count, 4)
        self.assertIn("Front Plane", tracked_doc.initial_feature_names)
        self.assertIn("Origin", tracked_doc.initial_feature_names)

        # 验证以文档 title 准确索引
        self.assertIn("EngineBlock", ctx.tracked_documents)
        self.assertEqual(ctx.tracked_documents["EngineBlock"].doc_id, tracked_doc.doc_id)

    def test_stage5_05_feature_registration_and_lifo_order(self):
        """05: 特征多步骤跟踪与逆向 (LIFO) 清理顺序保证"""
        ctx = CADTaskContext(task_id="task_s5_lifo")
        doc = MockModelDoc("Bracket")
        ctx.register_document(doc, is_newly_created=True)

        ctx.register_feature("Sketch1", "SKETCH", "Bracket")
        ctx.register_feature("Boss-Extrude1", "BODYFEATURE", "Bracket")
        ctx.register_feature("Fillet1", "FILLET", "Bracket")

        self.assertEqual(len(ctx.tracked_features), 3)
        self.assertEqual(ctx.tracked_features[0].feature_name, "Sketch1")
        self.assertEqual(ctx.tracked_features[1].feature_name, "Boss-Extrude1")
        self.assertEqual(ctx.tracked_features[2].feature_name, "Fillet1")

        # 逆序提取特征名称以支持安全回滚 (LIFO)
        reverse_names = [f.feature_name for f in reversed(ctx.tracked_features)]
        self.assertEqual(reverse_names, ["Fillet1", "Boss-Extrude1", "Sketch1"])

    def test_stage5_06_cancellation_request_flow(self):
        """06: 任务取消请求与阻断响应"""
        ctx = CADTaskContext(task_id="task_s5_cancel")
        ctx.transition_to(TaskStatus.RUNNING)

        self.assertFalse(ctx.is_cancelled())
        ctx.request_cancellation(reason="Operator aborted task from UI")
        self.assertTrue(ctx.is_cancelled())
        self.assertEqual(ctx._cancellation_reason, "Operator aborted task from UI")

        # 状态机支持由 RUNNING 流转至 CANCELLING
        ctx.transition_to(TaskStatus.CANCELLING, "Processing cancellation")
        self.assertEqual(ctx.status, TaskStatus.CANCELLING)

    def test_stage5_07_rollback_manager_automatic_retry_and_exhaustion(self):
        """07: 回滚管理器重试边界与耗尽流转"""
        ctx = CADTaskContext(task_id="task_s5_exhaust", max_retries=1)
        sw = MockSolidWorksApp()
        mgr = CADTaskRollbackManager(ctx, sw_app=sw)

        attempts = 0

        def persistent_failing_task(context):
            nonlocal attempts
            attempts += 1
            doc = MockModelDoc(f"FaultyPart_{attempts}")
            context.register_document(doc, is_newly_created=True)
            raise RuntimeError(f"Simulated CAD kernel failure on attempt {attempts}")

        with self.assertRaises(RuntimeError) as ctx_err:
            mgr.execute_with_retry(persistent_failing_task)

        self.assertIn("Simulated CAD kernel failure", str(ctx_err.exception))
        self.assertEqual(attempts, 2)  # 初始 1 次 + 重试 1 次 = 共 2 次
        self.assertEqual(ctx.retry_count, 1)
        self.assertEqual(ctx.status, TaskStatus.ABORTED)

    def test_stage5_08_cleanup_verification_failure_blocks_retry(self):
        """08: 清理验证失败立即锁定 CLEANUP_FAILED 阻断盲目重试"""
        ctx = CADTaskContext(task_id="task_s5_cleanup_fail", max_retries=3)
        mgr = CADTaskRollbackManager(ctx)

        # 注入回滚失败 (模拟文档被 Windows 锁定或 COM 挂死)
        mgr.rollback = lambda: False

        def faulty_task(context):
            raise RuntimeError("Primary design operation failed")

        with self.assertRaises(CleanupVerificationError) as ctx_err:
            mgr.execute_with_retry(faulty_task)

        # 严格阻断重试：重试次数必须为 0，状态必须锁定为 CLEANUP_FAILED
        self.assertEqual(ctx.status, TaskStatus.CLEANUP_FAILED)
        self.assertEqual(ctx.retry_count, 0)
        self.assertFalse(ctx.can_retry())

    def test_stage5_09_audit_trail_and_error_capture(self):
        """09: 异常捕获与审计轨迹时间戳单调性验证"""
        ctx = CADTaskContext(task_id="task_s5_audit")
        t_start = ctx.start_time

        time.sleep(0.01)
        ctx.transition_to(TaskStatus.RUNNING, "Run Step 1")
        time.sleep(0.01)
        ctx.errors.append("CAD warning: non-critical surface self-intersection")
        ctx.transition_to(TaskStatus.COMMITTING, "Run Step 2")
        time.sleep(0.01)
        ctx.transition_to(TaskStatus.SUCCEEDED, "Done")

        # 验证错误被正确记录
        self.assertEqual(len(ctx.errors), 1)
        self.assertIn("surface self-intersection", ctx.errors[0])

        # 验证时间戳严格单调递增
        timestamps = [h[1] for h in ctx.state_history]
        self.assertTrue(len(timestamps) >= 4)
        for i in range(len(timestamps) - 1):
            self.assertLessEqual(timestamps[i], timestamps[i + 1])
        self.assertGreater(timestamps[-1], t_start)


if __name__ == "__main__":
    unittest.main()
