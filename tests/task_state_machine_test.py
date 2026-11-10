# -*- coding: utf-8 -*-
"""
tests/task_state_machine_test.py

NIGHT-ENGINEERING-07 阶段一专项测试:
CAD 任务有限状态机 (FSM) 与生命周期流转合法性单元测试。

验证点:
1. 12 项标准状态枚举完整性 (CREATED, VALIDATING, QUEUED, RUNNING, CANCELLING, COMMITTING,
   ROLLING_BACK, SUCCEEDED, FAILED, CANCELLED, TIMEOUT, RECOVERY_REQUIRED);
2. 历史别名 (PENDING, COMPLETED, ABORTED) 向后兼容解析;
3. 合法流转全流程测试 (正向成功、超时异常、主动取消、故障回滚重试);
4. 非法状态流转严格拦截 (抛出 InvalidStateTransitionError);
5. 终态不可逆与防重复执行;
6. 取消请求的协作式标记与幂等性;
7. 状态流转时序审计追踪 (state_history)。
"""

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "vendor", "solidworks-automation-skill", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from cad_task_context import (
    CADTaskContext,
    InvalidStateTransitionError,
    TaskStatus,
)


class TestCADTaskStateMachine(unittest.TestCase):

    def test_twelve_standard_statuses_completeness(self):
        """验证 12 项标准生命周期状态全部存在。"""
        expected = [
            "CREATED",
            "VALIDATING",
            "QUEUED",
            "RUNNING",
            "CANCELLING",
            "COMMITTING",
            "ROLLING_BACK",
            "SUCCEEDED",
            "FAILED",
            "CANCELLED",
            "TIMEOUT",
            "RECOVERY_REQUIRED",
        ]
        status_names = [s.name for s in TaskStatus]
        for name in expected:
            self.assertIn(name, status_names, f"状态枚举缺少标准状态: {name}")

    def test_backward_compatibility_aliases(self):
        """验证历史别名向后兼容。"""
        self.assertEqual(TaskStatus.PENDING.value, "CREATED")
        self.assertEqual(TaskStatus.COMPLETED.value, "SUCCEEDED")
        self.assertEqual(TaskStatus.ABORTED.value, "CANCELLED")

    def test_valid_happy_path_transitions(self):
        """验证正常建模正向合法流转: CREATED -> VALIDATING -> QUEUED -> RUNNING -> COMMITTING -> SUCCEEDED。"""
        ctx = CADTaskContext(task_id="test_happy_01")
        self.assertEqual(ctx.status.value, "CREATED")

        ctx.transition_to(TaskStatus.VALIDATING, "Feature Graph IR 几何求解检查")
        self.assertEqual(ctx.status, TaskStatus.VALIDATING)

        ctx.transition_to(TaskStatus.QUEUED, "提交至 STA Worker 任务队列")
        self.assertEqual(ctx.status, TaskStatus.QUEUED)

        ctx.transition_to(TaskStatus.RUNNING, "Worker 线程获取任务开始调用 SolidWorks")
        self.assertEqual(ctx.status, TaskStatus.RUNNING)

        ctx.transition_to(TaskStatus.COMMITTING, "所有特征生成完成，触发 Rebuild 与文件保存")
        self.assertEqual(ctx.status, TaskStatus.COMMITTING)

        ctx.transition_to(TaskStatus.SUCCEEDED, "事务成功提交")
        self.assertEqual(ctx.status, TaskStatus.SUCCEEDED)
        self.assertTrue(ctx.is_terminal())

        # 检查审计历史完整记录了 6 次流转
        self.assertEqual(len(ctx.state_history), 6)

    def test_illegal_state_transition_interception(self):
        """验证非法状态跳转被强类型异常拦截，状态不被脏化。"""
        ctx = CADTaskContext(task_id="test_illegal_01")
        self.assertEqual(ctx.status.value, "CREATED")

        # 1. 尝试直接从 CREATED 跳到 SUCCEEDED (未执行即声称成功)
        with self.assertRaises(InvalidStateTransitionError) as cm:
            ctx.transition_to(TaskStatus.SUCCEEDED, "跳过执行直接成功")
        self.assertIn("CREATED -> SUCCEEDED", str(cm.exception))
        self.assertEqual(ctx.status.value, "CREATED")  # 保持原状态不变

        # 2. 正常流转到 RUNNING
        ctx.transition_to(TaskStatus.RUNNING, "直接运行")
        self.assertEqual(ctx.status, TaskStatus.RUNNING)

        # 3. 尝试从 RUNNING 倒退回 VALIDATING
        with self.assertRaises(InvalidStateTransitionError) as cm2:
            ctx.transition_to(TaskStatus.VALIDATING, "执行中倒退")
        self.assertIn("RUNNING -> VALIDATING", str(cm2.exception))

    def test_terminal_states_are_immutable(self):
        """验证进入终态后禁止再次流转。"""
        terminal_statuses = [
            TaskStatus.SUCCEEDED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
            TaskStatus.TIMEOUT,
            TaskStatus.RECOVERY_REQUIRED,
        ]

        for term in terminal_statuses:
            ctx = CADTaskContext(task_id=f"test_term_{term.name}")
            # 强行设置到终态
            ctx.status = term
            self.assertTrue(ctx.is_terminal())
            self.assertFalse(ctx.can_cancel())

            # 尝试从终态跳转到任何其他状态
            with self.assertRaises(InvalidStateTransitionError):
                ctx.transition_to(TaskStatus.RUNNING, "企图从终态死灰复燃")

    def test_cancellation_workflow(self):
        """验证协作式取消机制与幂等性。"""
        ctx = CADTaskContext(task_id="test_cancel_01")
        ctx.transition_to(TaskStatus.RUNNING, "正在执行")

        self.assertTrue(ctx.can_cancel())
        self.assertFalse(ctx.is_cancelled())

        # 发起取消请求
        ok = ctx.request_cancellation("用户点击取消按钮")
        self.assertTrue(ok)
        self.assertTrue(ctx.is_cancelled())
        self.assertEqual(ctx.status, TaskStatus.CANCELLING)

        # 模拟执行回滚并达到最终 CANCELLED 终态
        ctx.transition_to(TaskStatus.ROLLING_BACK, "正在回滚半成品特征")
        ctx.transition_to(TaskStatus.CANCELLED, "回滚完成，任务彻底取消")
        self.assertEqual(ctx.status, TaskStatus.CANCELLED)
        self.assertTrue(ctx.is_terminal())

        # 重复请求取消应保持幂等
        self.assertTrue(ctx.request_cancellation("二次取消"))
        self.assertEqual(ctx.status, TaskStatus.CANCELLED)

    def test_failure_rollback_and_recovery_required(self):
        """验证故障回滚失败时流转到 RECOVERY_REQUIRED 阻断重试。"""
        ctx = CADTaskContext(task_id="test_recov_01")
        ctx.transition_to(TaskStatus.RUNNING, "正在执行")
        ctx.transition_to(TaskStatus.ROLLING_BACK, "特征创建失败，触发回滚")

        # 模拟物理回滚失败（特征树残留无法删除）
        ctx.transition_to(TaskStatus.RECOVERY_REQUIRED, "物理删除失败，需人工干预")
        self.assertEqual(ctx.status, TaskStatus.RECOVERY_REQUIRED)
        self.assertTrue(ctx.is_terminal())
        self.assertFalse(ctx.can_retry())


if __name__ == "__main__":
    unittest.main()
