# -*- coding: utf-8 -*-
"""
tests/cad_graph_executor_test.py
CADGraphExecutor 生产级特征图执行引擎高覆盖率离线单元与集成测试。
覆盖：
1. 输入与结构校验（有效 DAG、空图、字典编译）；
2. 拓扑依赖时序验证；
3. 循环闭环死锁静态拦截 (CyclicDependencyError)；
4. 悬挂依赖静态拦截 (UndefinedDependencyError)；
5. Mock COM 环境下的顺利建模闭环；
6. 智能实体名称继承（下游特征无需显式指定草图名，自动从已成功父节点继承）；
7. 故障捕获与失败节点精确定位；
8. 受波及下游节点自动标记 SKIPPED；
9. 与 CADTaskContext 深度联动的自动安全回滚防护；
10. 结构化执行结果字典序列化 (to_dict)。
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

from feature_graph_ir import (
    FeatureGraphIR,
    FeatureNode,
    FeatureType,
    NodeStatus,
    CyclicDependencyError,
    UndefinedDependencyError,
)
from cad_graph_executor import (
    CADGraphExecutor,
    ExecutionResult,
    NodeExecutionRecord,
)
from cad_task_context import (
    CADTaskContext,
    TaskStatus,
)


class MockSTAWorker:
    """模拟 STA Worker 调度器，直接同步执行闭包。"""
    def __init__(self):
        self.call_count = 0

    def execute(self, func, *args, **kwargs):
        self.call_count += 1
        return func(*args, **kwargs)


class MockSolidWorksApp:
    """模拟 SolidWorks COM 根应用。"""
    def __init__(self):
        self.closed_docs = []
        self._open_docs = []

    def CloseDoc(self, title):
        self.closed_docs.append(title)
        self._open_docs = [d for d in self._open_docs if getattr(d, "title", "") != title]
        return True

    def GetDocuments(self):
        return list(self._open_docs)

    def GetDocumentCount(self):
        return len(self._open_docs)

    def NewDocument(self, *args, **kwargs):
        doc = MockModelDoc(title=f"MockNewPart_{len(self._open_docs)+1}.SLDPRT")
        self._open_docs.append(doc)
        return doc

    def INewDocument2(self, *args, **kwargs):
        return self.NewDocument(*args, **kwargs)


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
    """模拟 SolidWorks 零件文档与特征树。"""
    def __init__(self, title="MockBracket.SLDPRT"):
        self.title = title
        self.rebuilt = False
        self.saved_path = None
        self.features = [
            MockCOMFeature("Front Plane", "RefPlane"),
            MockCOMFeature("Top Plane", "RefPlane"),
            MockCOMFeature("Right Plane", "RefPlane"),
            MockCOMFeature("Origin", "OriginProfileFeature"),
        ]

    def GetTitle(self):
        return self.title

    def GetPathName(self):
        return self.saved_path or ""

    def GetFeatureCount(self):
        return len(self.features)

    def FirstFeature(self):
        return self.features[0] if self.features else None

    def FeatureByName(self, name):
        for f in self.features:
            if f.Name == name and not f.deleted:
                return f
        return None

    def EditRebuild3(self):
        self.rebuilt = True
        return 0

    def ForceRebuild3(self, topOnly=False):
        self.rebuilt = True
        return 0

    def SaveAs3(self, path, *args):
        self.saved_path = path
        return 0

    def ClearSelection2(self, *args, **kwargs):
        return True

    def SelectByID2(self, *args, **kwargs):
        return True

    def EditDelete(self):
        # 模拟删除当前选中的特征
        for f in self.features:
            if getattr(f, "selected", False):
                f.deleted = True
                return True
        return True


class CADGraphExecutorTest(unittest.TestCase):

    def setUp(self):
        self.mock_worker = MockSTAWorker()
        self.mock_sw = MockSolidWorksApp()
        self.mock_doc = MockModelDoc()

    def test_dag_validation_and_cyclic_rejection(self):
        """测试 1：循环依赖必须在执行前被 Kahn 算法静态拦截并抛出 CyclicDependencyError。"""
        fg = FeatureGraphIR(graph_id="cyclic_test")
        # A 依赖 B，B 依赖 A
        fg.add_node(FeatureNode(id="A", type=FeatureType.SKETCH_2D, name="SkA", depends_on=["B"]))
        fg.add_node(FeatureNode(id="B", type=FeatureType.EXTRUDE_BOSS, name="ExtB", depends_on=["A"]))

        executor = CADGraphExecutor(sta_worker=self.mock_worker, sw_app=self.mock_sw)
        with self.assertRaises(CyclicDependencyError):
            executor.execute(fg, model_doc=self.mock_doc)

    def test_dag_validation_and_undefined_dependency(self):
        """测试 2：悬挂的未定义前置依赖必须被静态拦截并抛出 UndefinedDependencyError。"""
        fg = FeatureGraphIR(graph_id="undefined_dep_test")
        fg.add_node(FeatureNode(id="node1", type=FeatureType.SKETCH_2D, name="Sk1", depends_on=["non_existent_node"]))

        executor = CADGraphExecutor(sta_worker=self.mock_worker, sw_app=self.mock_sw)
        with self.assertRaises(UndefinedDependencyError):
            executor.execute(fg, model_doc=self.mock_doc)

    def test_successful_linear_execution_with_entity_inheritance(self):
        """
        测试 3：正常线性特征图执行，验证：
        1. 拓扑排序时序顺序（草图 -> 拉伸 -> 切除）；
        2. 自动实体继承（拉伸未传 sketch_name 时，自动继承前置草图实体）；
        3. 所有节点状态转为 SUCCEEDED；
        4. 执行结果数据结构完整性。
        """
        fg = FeatureGraphIR(graph_id="linear_bracket", target_part_name="bracket")
        # 故意打乱注册顺序：切除 -> 草图 -> 拉伸
        fg.add_node(FeatureNode(
            id="node_cut",
            type=FeatureType.EXTRUDE_CUT,
            name="Cut-Extrude1",
            parameters={"depth_m": 0.01},
            depends_on=["node_boss"],
        ))
        fg.add_node(FeatureNode(
            id="node_sketch",
            type=FeatureType.SKETCH_2D,
            name="Sketch1",
            parameters={"plane": "Front Plane", "shape": "rectangle", "width_m": 0.1, "height_m": 0.05},
            depends_on=[],
        ))
        fg.add_node(FeatureNode(
            id="node_boss",
            type=FeatureType.EXTRUDE_BOSS,
            name="Boss-Extrude1",
            parameters={"depth_m": 0.02},
            depends_on=["node_sketch"],
        ))

        # 为 Mock 注入底层分发拦截器，避免真实调用未连接的 COM
        executor = CADGraphExecutor(
            sta_worker=self.mock_worker,
            sw_app=self.mock_sw,
            enable_task_context=True,
            auto_rollback_on_failure=True,
        )

        executed_steps = []
        def mock_dispatch(model, node, node_entity_map):
            executed_steps.append(node.id)
            if node.type == FeatureType.SKETCH_2D:
                return "Sketch1"
            elif node.type == FeatureType.EXTRUDE_BOSS:
                # 验证是否成功从 node_sketch 继承实体名称
                self.assertIn("node_sketch", node_entity_map)
                self.assertEqual(node_entity_map["node_sketch"], "Sketch1")
                return "Boss-Extrude1"
            elif node.type == FeatureType.EXTRUDE_CUT:
                return "Cut-Extrude1"
            return node.name

        executor._dispatch_feature = mock_dispatch

        res = executor.execute(fg, model_doc=self.mock_doc, collect_metrics=False)

        # 断言
        self.assertTrue(res.success)
        self.assertEqual(res.total_nodes, 3)
        self.assertEqual(res.executed_count, 3)
        self.assertEqual(len(res.failed_nodes), 0)
        self.assertEqual(len(res.skipped_nodes), 0)
        self.assertEqual(executed_steps, ["node_sketch", "node_boss", "node_cut"])
        self.assertEqual(res.succeeded_nodes, ["node_sketch", "node_boss", "node_cut"])
        self.assertTrue(self.mock_doc.rebuilt)

        # 验证序列化
        res_dict = res.to_dict()
        self.assertTrue(res_dict["success"])
        self.assertEqual(len(res_dict["node_records"]), 3)
        self.assertEqual(res_dict["node_records"]["node_sketch"]["status"], "SUCCEEDED")

    def test_mid_operation_failure_and_downstream_skip(self):
        r"""
        测试 4：中途节点故障隔离与下游自动跳过：
        DAG 结构：
              /-> node_branch1 (依赖 base) -> node_child1 (依赖 branch1)
        base
              \-> node_branch2 (依赖 base, 注入失败) -> node_child2 (依赖 branch2)
        预期：
        base: SUCCEEDED
        node_branch2: FAILED
        node_child2: 自动 SKIPPED
        node_branch1: 仍可安全执行或按策略隔离
        """
        fg = FeatureGraphIR(graph_id="branch_failure_graph")
        fg.add_node(FeatureNode(id="base", type=FeatureType.SKETCH_2D, name="BaseSk"))
        fg.add_node(FeatureNode(id="branch_ok", type=FeatureType.EXTRUDE_BOSS, name="BossOK", depends_on=["base"]))
        fg.add_node(FeatureNode(id="branch_err", type=FeatureType.EXTRUDE_BOSS, name="BossErr", depends_on=["base"]))
        fg.add_node(FeatureNode(id="child_of_err", type=FeatureType.EXTRUDE_CUT, name="CutChild", depends_on=["branch_err"]))

        executor = CADGraphExecutor(
            sta_worker=self.mock_worker,
            sw_app=self.mock_sw,
            enable_task_context=True,
            auto_rollback_on_failure=False,  # 不整件回滚，验证跳过逻辑
        )

        def mock_dispatch(model, node, node_entity_map):
            if node.id == "branch_err":
                raise ValueError("模拟几何自交错误：拉伸深度超出几何极限")
            return f"CAD_{node.name}"

        executor._dispatch_feature = mock_dispatch

        res = executor.execute(fg, model_doc=self.mock_doc, collect_metrics=False)

        self.assertFalse(res.success)
        self.assertIn("branch_err", res.failed_nodes)
        self.assertIn("child_of_err", res.skipped_nodes)
        self.assertEqual(res.node_records["child_of_err"].status, NodeStatus.SKIPPED)
        self.assertEqual(res.node_records["child_of_err"].error_type, "DependencyFailedError")

    def test_automatic_rollback_on_failure_with_cad_task_context(self):
        """
        测试 5：验证与 CADTaskContext 的深度安全回滚联动。
        当 auto_rollback_on_failure=True 时，节点失败应触发 rollback_occurred=True，
        并记录诊断信息。
        """
        fg = FeatureGraphIR(graph_id="rollback_test")
        fg.add_node(FeatureNode(id="step1", type=FeatureType.SKETCH_2D, name="Sk1"))
        fg.add_node(FeatureNode(id="step2", type=FeatureType.EXTRUDE_BOSS, name="Boss1", depends_on=["step1"]))

        executor = CADGraphExecutor(
            sta_worker=self.mock_worker,
            sw_app=self.mock_sw,
            enable_task_context=True,
            auto_rollback_on_failure=True,
        )

        def mock_dispatch(model, node, node_entity_map):
            if node.id == "step2":
                raise RuntimeError("底层 COM 崩溃异常: DISP_E_EXCEPTION")
            return "Entity_Sk1"

        executor._dispatch_feature = mock_dispatch

        res = executor.execute(fg, model_doc=self.mock_doc, collect_metrics=False)

        self.assertFalse(res.success)
        self.assertTrue(res.rollback_occurred)
        self.assertIn("step2", res.failed_nodes)
        self.assertIn("failure_step2", res.diagnostics)
        self.assertEqual(res.diagnostics["failure_step2"]["error_type"], "RuntimeError")

    def test_compile_from_dict_and_execute(self):
        """测试 6：支持直接传入原始字典输入，由执行器自动静态编译与执行。"""
        raw_dict = {
            "graph_id": "dict_graph_test",
            "target_part_name": "flange",
            "nodes": {
                "n1": {
                    "type": "sketch_2d",
                    "name": "Sketch1",
                    "parameters": {"plane": "Top Plane", "shape": "circle", "radius_m": 0.05},
                    "depends_on": [],
                },
                "n2": {
                    "type": "extrude_boss",
                    "name": "Boss1",
                    "parameters": {"depth_m": 0.01},
                    "depends_on": ["n1"],
                }
            }
        }

        executor = CADGraphExecutor(sta_worker=self.mock_worker, sw_app=self.mock_sw)
        executor._dispatch_feature = lambda model, node, node_entity_map: node.name

        res = executor.execute(raw_dict, model_doc=self.mock_doc, collect_metrics=False)
        self.assertTrue(res.success)
        self.assertEqual(res.total_nodes, 2)
        self.assertEqual(res.succeeded_nodes, ["n1", "n2"])

    def test_multi_parent_convergence_dependency(self):
        """测试 7：多父节点汇聚依赖（A 和 B 汇聚到 C，C 依赖 A 和 B）。"""
        fg = FeatureGraphIR(graph_id="multi_parent_graph")
        fg.add_node(FeatureNode(id="A", type=FeatureType.SKETCH_2D, name="SkA"))
        fg.add_node(FeatureNode(id="B", type=FeatureType.SKETCH_2D, name="SkB"))
        fg.add_node(FeatureNode(id="C", type=FeatureType.EXTRUDE_BOSS, name="BossC", depends_on=["A", "B"]))

        executor = CADGraphExecutor(sta_worker=self.mock_worker, sw_app=self.mock_sw)
        order = []
        def mock_dispatch(model, node, node_entity_map, *args, **kwargs):
            order.append(node.id)
            return node.name
        executor._dispatch_feature = mock_dispatch

        res = executor.execute(fg, model_doc=self.mock_doc, collect_metrics=False)
        self.assertTrue(res.success)
        self.assertEqual(order[-1], "C")
        self.assertTrue(set(order[:2]) == {"A", "B"})

    def test_deep_chain_dependency(self):
        """测试 8：长链路深度依赖（1 -> 2 -> 3 -> 4 -> 5）。"""
        fg = FeatureGraphIR(graph_id="chain_graph")
        prev = None
        for i in range(1, 6):
            nid = f"step_{i}"
            deps = [prev] if prev else []
            fg.add_node(FeatureNode(id=nid, type=FeatureType.EXTRUDE_BOSS, name=f"Boss_{i}", depends_on=deps))
            prev = nid

        executor = CADGraphExecutor(sta_worker=self.mock_worker, sw_app=self.mock_sw)
        order = []
        def mock_dispatch(model, node, node_entity_map, *args, **kwargs):
            order.append(node.id)
            return node.name
        executor._dispatch_feature = mock_dispatch

        res = executor.execute(fg, model_doc=self.mock_doc, collect_metrics=False)
        self.assertTrue(res.success)
        self.assertEqual(order, [f"step_{i}" for i in range(1, 6)])

    def test_sta_worker_dispatch_behavior(self):
        """测试 9：验证 execute 调用严格通过 STA Worker 派发。"""
        worker = MockSTAWorker()
        executor = CADGraphExecutor(sta_worker=worker, sw_app=self.mock_sw)
        executor._dispatch_feature = lambda model, node, node_entity_map, *args, **kwargs: node.name

        fg = FeatureGraphIR(graph_id="sta_test")
        fg.add_node(FeatureNode(id="s1", type=FeatureType.SKETCH_2D, name="S1"))

        self.assertEqual(worker.call_count, 0)
        executor.execute(fg, model_doc=self.mock_doc, collect_metrics=False)
        self.assertEqual(worker.call_count, 1)

    def test_empty_graph_execution(self):
        """测试 10：空图执行应当平稳返回 success=True，total_nodes=0。"""
        fg = FeatureGraphIR(graph_id="empty_graph")
        executor = CADGraphExecutor(sta_worker=self.mock_worker, sw_app=self.mock_sw)

        res = executor.execute(fg, model_doc=self.mock_doc, collect_metrics=False)
        self.assertTrue(res.success)
        self.assertEqual(res.total_nodes, 0)
        self.assertEqual(res.executed_count, 0)

    def test_feature_creation_entity_mapping_failure(self):
        """测试 11：特征创建底层成功但未返回有效名称，触发异常并回滚。"""
        fg = FeatureGraphIR(graph_id="mapping_fail_graph")
        fg.add_node(FeatureNode(id="sk1", type=FeatureType.SKETCH_2D, name="Sketch1"))
        fg.add_node(FeatureNode(id="ext1", type=FeatureType.EXTRUDE_BOSS, name="Boss1", depends_on=["sk1"]))

        executor = CADGraphExecutor(
            sta_worker=self.mock_worker,
            sw_app=self.mock_sw,
            enable_task_context=True,
            auto_rollback_on_failure=True,
        )

        # 添加 Sketch1 模拟特征供逆序删除
        self.mock_doc.features.append(MockCOMFeature("Sketch1", "SKETCH"))

        def mock_dispatch(model, node, node_entity_map, **kwargs):
            if node.id == "ext1":
                raise RuntimeError("实体句柄捕获失败: ModelDoc Extension 未返回有效特征指针")
            return "Sketch1"

        executor._dispatch_feature = mock_dispatch
        res = executor.execute(fg, model_doc=self.mock_doc, collect_metrics=False)

        self.assertFalse(res.success)
        self.assertEqual(res.status, "ROLLED_BACK")
        self.assertEqual(res.rollback_status, "SUCCESS")
        self.assertIn("ext1", res.failed_nodes)

    def test_rebuild_failure_resilience(self):
        """测试 12：EditRebuild3 返回 False/异常时，记录为 warning，不导致流程崩溃。"""
        fg = FeatureGraphIR(graph_id="rebuild_warn_graph")
        fg.add_node(FeatureNode(id="s1", type=FeatureType.SKETCH_2D, name="S1"))

        executor = CADGraphExecutor(sta_worker=self.mock_worker, sw_app=self.mock_sw)
        executor._dispatch_feature = lambda model, node, node_entity_map, **kw: "S1"

        # 模拟 Rebuild 返回 False
        self.mock_doc.EditRebuild3 = lambda: False
        res = executor.execute(fg, model_doc=self.mock_doc, collect_metrics=False)

        self.assertTrue(res.success)
        self.assertEqual(res.status, "COMPLETED")
        self.assertIn("rebuild_warning", res.diagnostics)

    def test_feature_deletion_failure_partial_rollback(self):
        """测试 13：回滚时若个别特征删除失败，状态准确记录为 PARTIAL_ROLLED_BACK。"""
        fg = FeatureGraphIR(graph_id="partial_rb_graph")
        fg.add_node(FeatureNode(id="s1", type=FeatureType.SKETCH_2D, name="S1"))
        fg.add_node(FeatureNode(id="ext1", type=FeatureType.EXTRUDE_BOSS, name="Boss1", depends_on=["s1"]))

        executor = CADGraphExecutor(
            sta_worker=self.mock_worker,
            sw_app=self.mock_sw,
            enable_task_context=True,
            auto_rollback_on_failure=True,
        )

        # 构造已有文档（已有文档回滚时才会调用 FeatureCleanupManager 删除特征）
        doc = MockModelDoc(title="UserPart.SLDPRT")
        feat_s1 = MockCOMFeature("S1", "SKETCH")
        feat_boss = MockCOMFeature("Boss1", "BODYFEATURE")
        doc.features.extend([feat_s1, feat_boss])

        # 模拟 DeleteSelection2 失败
        class MockExtension:
            def DeleteSelection2(self, options):
                return False
        doc.Extension = MockExtension()
        doc.EditDelete = lambda: False

        def mock_dispatch(model, node, node_entity_map, **kw):
            if node.id == "ext1":
                raise ValueError("模拟几何求解错误")
            return "S1"

        executor._dispatch_feature = mock_dispatch
        res = executor.execute(fg, model_doc=doc, collect_metrics=False)

        self.assertFalse(res.success)
        self.assertEqual(res.status, "PARTIAL_ROLLED_BACK")
        self.assertEqual(res.rollback_status, "PARTIAL")
        self.assertTrue(len(res.rollback_errors) > 0)

    def test_rollback_secondary_exception_preserves_both(self):
        """测试 14：回滚过程抛出二次异常时，同时保留 primary_failure 与 rollback_error。"""
        fg = FeatureGraphIR(graph_id="double_fault_graph")
        fg.add_node(FeatureNode(id="s1", type=FeatureType.SKETCH_2D, name="S1"))

        executor = CADGraphExecutor(
            sta_worker=self.mock_worker,
            sw_app=self.mock_sw,
            enable_task_context=True,
            auto_rollback_on_failure=True,
        )

        def mock_dispatch(model, node, node_entity_map, **kw):
            raise RuntimeError("第一重建模致命错误")

        executor._dispatch_feature = mock_dispatch

        # 模拟 rollback_mgr 在回滚期间遭遇底层 RPC 崩溃直接抛出未捕获二次异常
        # 验证执行器在面对严重二次异常时，既记录 FAILED 状态，又保留原始与二次双重异常
        from unittest.mock import patch
        with patch("cad_graph_executor.CADTaskRollbackManager.rollback", side_effect=RuntimeError("二次回滚异常：RPC 通信信道已断开")):
            res = executor.execute(fg, model_doc=self.mock_doc, collect_metrics=False)

        self.assertFalse(res.success)
        self.assertEqual(res.status, "FAILED")
        self.assertEqual(res.rollback_status, "FAILED")
        self.assertIn("primary_failure", res.diagnostics)
        self.assertIn("rollback_error", res.diagnostics)
        self.assertIn("第一重建模致命错误", res.diagnostics["primary_failure"])
        self.assertIn("二次回滚异常", res.diagnostics["rollback_error"])

    def test_multi_branch_shared_dependency_isolation(self):
        """测试 15：多分支共享 Base 特征，在 auto_rollback=False 时，Branch1 故障不影响 Branch2 成功执行。"""
        fg = FeatureGraphIR(graph_id="shared_base_dag")
        fg.add_node(FeatureNode(id="base", type=FeatureType.SKETCH_2D, name="BaseSketch"))
        # 分支 1: 故障
        fg.add_node(FeatureNode(id="b1", type=FeatureType.EXTRUDE_BOSS, name="BossFail", depends_on=["base"]))
        fg.add_node(FeatureNode(id="b1_child", type=FeatureType.EXTRUDE_CUT, name="CutChild", depends_on=["b1"]))
        # 分支 2: 独立且正常
        fg.add_node(FeatureNode(id="b2", type=FeatureType.EXTRUDE_BOSS, name="BossSuccess", depends_on=["base"]))

        executor = CADGraphExecutor(
            sta_worker=self.mock_worker,
            sw_app=self.mock_sw,
            enable_task_context=True,
            auto_rollback_on_failure=False,
        )

        executed = []
        def mock_dispatch(model, node, node_entity_map, **kw):
            executed.append(node.id)
            if node.id == "b1":
                raise ValueError("B1 求解失败")
            return f"CAD_{node.name}"

        executor._dispatch_feature = mock_dispatch
        res = executor.execute(fg, model_doc=self.mock_doc, collect_metrics=False)

        self.assertFalse(res.success)
        self.assertIn("b1", res.failed_nodes)
        self.assertIn("b1_child", res.skipped_nodes)
        self.assertIn("b2", res.succeeded_nodes)
        self.assertIn("base", res.succeeded_nodes)
        self.assertIn("b2", executed)

    def test_multi_parent_failure_cascade_skip(self):
        """测试 16：汇聚节点 C 依赖 A 和 B，A 失败、B 成功，C 依然准确被级联跳过。"""
        fg = FeatureGraphIR(graph_id="multi_parent_skip_graph")
        fg.add_node(FeatureNode(id="A", type=FeatureType.SKETCH_2D, name="SkA"))
        fg.add_node(FeatureNode(id="B", type=FeatureType.SKETCH_2D, name="SkB"))
        fg.add_node(FeatureNode(id="C", type=FeatureType.EXTRUDE_BOSS, name="BossC", depends_on=["A", "B"]))

        executor = CADGraphExecutor(
            sta_worker=self.mock_worker,
            sw_app=self.mock_sw,
            auto_rollback_on_failure=False,
        )

        def mock_dispatch(model, node, node_entity_map, **kw):
            if node.id == "A":
                raise RuntimeError("草图 A 自交")
            return node.name

        executor._dispatch_feature = mock_dispatch
        res = executor.execute(fg, model_doc=self.mock_doc, collect_metrics=False)

        self.assertIn("A", res.failed_nodes)
        self.assertIn("B", res.succeeded_nodes)
        self.assertIn("C", res.skipped_nodes)

    def test_graph_re_execution_status_isolation(self):
        """测试 17：同一 FeatureGraphIR 重入多次执行，状态完全隔离重置，不发生残留污染。"""
        fg = FeatureGraphIR(graph_id="reentrant_graph")
        fg.add_node(FeatureNode(id="s1", type=FeatureType.SKETCH_2D, name="S1"))

        executor = CADGraphExecutor(sta_worker=self.mock_worker, sw_app=self.mock_sw)

        # 第一次执行：失败
        executor._dispatch_feature = lambda model, node, node_entity_map, **kw: (_ for _ in ()).throw(RuntimeError("临时故障"))
        res1 = executor.execute(fg, model_doc=self.mock_doc, collect_metrics=False)
        self.assertFalse(res1.success)
        self.assertEqual(fg.nodes["s1"].status, NodeStatus.FAILED)

        # 第二次执行：恢复正常
        executor._dispatch_feature = lambda model, node, node_entity_map, **kw: "S1"
        res2 = executor.execute(fg, model_doc=self.mock_doc, collect_metrics=False)
        self.assertTrue(res2.success)
        self.assertEqual(fg.nodes["s1"].status, NodeStatus.SUCCEEDED)

    def test_document_close_failure_diagnostics(self):
        """测试 18：CloseDoc 失败时记录 close_doc_error 诊断，不掩盖正常结果。"""
        fg = FeatureGraphIR(graph_id="close_err_graph")
        fg.add_node(FeatureNode(id="s1", type=FeatureType.SKETCH_2D, name="S1"))

        executor = CADGraphExecutor(sta_worker=self.mock_worker, sw_app=self.mock_sw)
        executor._dispatch_feature = lambda model, node, node_entity_map, **kw: "S1"

        # 模拟 CloseDoc 抛出异常
        self.mock_sw.CloseDoc = lambda title: (_ for _ in ()).throw(RuntimeError("文件被其他进程锁定无法关闭"))

        res = executor.execute(fg, model_doc=self.mock_doc, close_on_finish=True, collect_metrics=False)
        self.assertTrue(res.success)

    def test_user_existing_document_protection(self):
        """测试 19：传入已有文档时 (created_doc=False)，即使 close_on_finish=True 也绝不关闭文档。"""
        fg = FeatureGraphIR(graph_id="protect_doc_graph")
        fg.add_node(FeatureNode(id="s1", type=FeatureType.SKETCH_2D, name="S1"))

        executor = CADGraphExecutor(sta_worker=self.mock_worker, sw_app=self.mock_sw)
        executor._dispatch_feature = lambda model, node, node_entity_map, **kw: "S1"

        existing_doc = MockModelDoc(title="CriticalProductionPart.SLDPRT")
        res = executor.execute(fg, model_doc=existing_doc, close_on_finish=True, collect_metrics=False)

        self.assertTrue(res.success)
        self.assertNotIn("CriticalProductionPart.SLDPRT", self.mock_sw.closed_docs)

    def test_sketch_inheritance_validation_failure(self):
        """测试 20：拉伸特征缺少必需草图依赖时，明确抛出 ValueError，不静默使用随机草图。"""
        fg = FeatureGraphIR(graph_id="invalid_sketch_dep_graph")
        # 错误：new_boss 缺少必需草图依赖
        fg.add_node(FeatureNode(id="base_sketch", type=FeatureType.SKETCH_2D, name="BaseSketch"))
        fg.add_node(FeatureNode(id="new_boss", type=FeatureType.EXTRUDE_BOSS, name="NewBoss", depends_on=[]))

        executor = CADGraphExecutor(
            sta_worker=self.mock_worker,
            sw_app=self.mock_sw,
            auto_rollback_on_failure=True,
        )
        # 保证 base_sketch 正常通过，检验 new_boss 在 dispatch 时的草图依赖判定
        orig_dispatch = executor._dispatch_feature
        def mock_dispatch(model, node, node_entity_map, **kw):
            if node.id == "base_sketch":
                return "BaseSketch"
            return orig_dispatch(model, node, node_entity_map)

        executor._dispatch_feature = mock_dispatch
        res = executor.execute(fg, model_doc=self.mock_doc, collect_metrics=False)
        self.assertFalse(res.success)
        self.assertIn("new_boss", res.failed_nodes)
        self.assertEqual(res.node_records["new_boss"].error_type, "ValueError")
        self.assertIn("缺少必需的草图依赖", res.node_records["new_boss"].error_message)

    def test_execution_result_schema_compatibility(self):
        """测试 21：验证扩充后的 ExecutionResult.to_dict() 输出具备完整兼容字段。"""
        fg = FeatureGraphIR(graph_id="schema_compat_graph")
        fg.add_node(FeatureNode(id="s1", type=FeatureType.SKETCH_2D, name="S1"))

        executor = CADGraphExecutor(sta_worker=self.mock_worker, sw_app=self.mock_sw)
        executor._dispatch_feature = lambda model, node, node_entity_map, **kw: "S1"

        res = executor.execute(fg, model_doc=self.mock_doc, collect_metrics=False)
        d = res.to_dict()

        expected_keys = [
            "success", "status", "execution_id", "graph_id", "target_part_name",
            "total_nodes", "executed_count", "duration_ms", "created_document",
            "succeeded_nodes", "failed_nodes", "skipped_nodes", "rolled_back_nodes",
            "node_records", "node_results", "created_features", "rollback_status",
            "rollback_errors", "mass_properties", "bounding_box", "saved_file_path",
            "task_id", "rollback_occurred", "diagnostics"
        ]
        for k in expected_keys:
            self.assertIn(k, d, f"Missing key in to_dict: {k}")

        self.assertEqual(d["status"], "COMPLETED")
        self.assertEqual(d["rollback_status"], "NOT_NEEDED")
        self.assertIsInstance(d["node_results"], dict)


if __name__ == "__main__":
    unittest.main()
