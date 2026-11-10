# -*- coding: utf-8 -*-
"""
SolidWorks 生产级特征图执行引擎 (CADGraphExecutor)
vendor/solidworks-automation-skill/scripts/cad_graph_executor.py

设计定位：
1. 消费 Feature Graph IR，进行 DAG 结构校验与 Kahn 确定性拓扑时序执行；
2. 调度 STA Worker 执行线程，严格遵循 SolidWorks Out-of-Process COM 单线程单元（STA）规范；
3. 与 CADTaskContext / CADTaskRollbackManager 深度联动，建立严密的建模任务生命周期与回滚安全闭环；
4. 调度 sw_part.py 等原子 CAD 建模方法，支持草图几何、拉伸凸台/切除、旋转、圆角、倒角、孔向导与阵列；
5. 提供细粒度的节点执行状态转移（PENDING -> RUNNING -> SUCCEEDED / FAILED / SKIPPED / ROLLED_BACK）；
6. 智能实体名称继承：下游特征若未指定草图名，自动从已成功的父草图节点继承 CAD 实体句柄；
7. 故障捕获与局域隔离控制：节点执行失败时精确定位，自动跳过受其波及的下游依赖子图；
8. 结构化执行结果返回（包含每步耗时、节点状态、实体追踪、质量属性、包围盒与诊断报告）；
9. 支持依赖注入与 Adapter 模式，可在离线/Mock 环境与真实 SolidWorks 环境无缝运行。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# 引入本skill内模块，支持独立运行与包内导入
try:
    from .feature_graph_ir import (
        FeatureGraphIR,
        FeatureNode,
        FeatureType,
        NodeStatus,
        CyclicDependencyError,
        UndefinedDependencyError,
        compile_feature_graph_from_dict,
    )
    from .sw_connect import (
        connect_solidworks,
        get_com_member,
        new_document,
        save_document,
        get_sta_worker,
    )
    from .cad_task_context import (
        CADTaskContext,
        CADTaskRollbackManager,
        FeatureCleanupManager,
        DocumentLifecycleManager,
        TaskStatus,
        CleanupStatus,
        RollbackStatus,
        RollbackResult,
    )
    from .sw_part import (
        start_sketch,
        end_sketch,
        sketch_line,
        sketch_rectangle,
        sketch_corner_rectangle,
        sketch_circle,
        sketch_arc,
        sketch_polygon,
        sketch_slot,
        sketch_spline,
        extrude_boss,
        extrude_cut,
        extrude_midplane,
        revolve_boss,
        fillet,
        chamfer,
        linear_pattern,
        circular_pattern,
        hole_wizard,
        current_sketch_name,
    )
    from .sw_measure import (
        collect_mass_properties,
        collect_bounding_box,
    )
except ImportError:
    from feature_graph_ir import (
        FeatureGraphIR,
        FeatureNode,
        FeatureType,
        NodeStatus,
        CyclicDependencyError,
        UndefinedDependencyError,
        compile_feature_graph_from_dict,
    )
    from sw_connect import (
        connect_solidworks,
        get_com_member,
        new_document,
        save_document,
        get_sta_worker,
    )
    from cad_task_context import (
        CADTaskContext,
        CADTaskRollbackManager,
        FeatureCleanupManager,
        DocumentLifecycleManager,
        TaskStatus,
        CleanupStatus,
        RollbackStatus,
        RollbackResult,
    )
    from sw_part import (
        start_sketch,
        end_sketch,
        sketch_line,
        sketch_rectangle,
        sketch_corner_rectangle,
        sketch_circle,
        sketch_arc,
        sketch_polygon,
        sketch_slot,
        sketch_spline,
        extrude_boss,
        extrude_cut,
        extrude_midplane,
        revolve_boss,
        fillet,
        chamfer,
        linear_pattern,
        circular_pattern,
        hole_wizard,
        current_sketch_name,
    )
    from sw_measure import (
        collect_mass_properties,
        collect_bounding_box,
    )

logger = logging.getLogger("solidworks_cad_executor")


@dataclass
class NodeExecutionRecord:
    """单个节点的执行追踪记录。"""
    node_id: str
    feature_type: str
    feature_name: str
    status: NodeStatus
    start_time: float = 0.0
    end_time: float = 0.0
    duration_ms: float = 0.0
    created_cad_entity: Optional[str] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """完整特征图执行的结构化输出结果。"""
    success: bool
    graph_id: str
    target_part_name: str
    total_nodes: int
    executed_count: int
    status: str = "FAILED"  # COMPLETED, FAILED, ROLLED_BACK, PARTIAL_ROLLED_BACK
    execution_id: str = ""
    created_document: Optional[Dict[str, Any]] = None
    succeeded_nodes: List[str] = field(default_factory=list)
    failed_nodes: List[str] = field(default_factory=list)
    skipped_nodes: List[str] = field(default_factory=list)
    rolled_back_nodes: List[str] = field(default_factory=list)
    node_records: Dict[str, NodeExecutionRecord] = field(default_factory=dict)
    created_features: List[str] = field(default_factory=list)
    rollback_status: str = "NOT_NEEDED"  # NOT_NEEDED, SUCCESS, PARTIAL, FAILED
    rollback_errors: List[str] = field(default_factory=list)
    duration_ms: float = 0.0
    mass_properties: Optional[Dict[str, float]] = None
    bounding_box: Optional[Dict[str, float]] = None
    saved_file_path: Optional[str] = None
    task_id: Optional[str] = None
    rollback_occurred: bool = False
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """将执行结果序列化为普通字典，适配 MCP JSON-RPC 返回格式。"""
        records_dict = {}
        for nid, r in self.node_records.items():
            records_dict[nid] = {
                "node_id": r.node_id,
                "feature_type": r.feature_type,
                "feature_name": r.feature_name,
                "status": r.status.value if hasattr(r.status, "value") else str(r.status),
                "duration_ms": round(r.duration_ms, 2),
                "created_cad_entity": r.created_cad_entity,
                "error_type": r.error_type,
                "error_message": r.error_message,
                "details": r.details,
            }

        return {
            "success": self.success,
            "status": self.status,
            "execution_id": self.execution_id or self.task_id or "",
            "graph_id": self.graph_id,
            "target_part_name": self.target_part_name,
            "total_nodes": self.total_nodes,
            "executed_count": self.executed_count,
            "duration_ms": round(self.duration_ms, 2),
            "created_document": self.created_document,
            "succeeded_nodes": self.succeeded_nodes,
            "failed_nodes": self.failed_nodes,
            "skipped_nodes": self.skipped_nodes,
            "rolled_back_nodes": self.rolled_back_nodes,
            "node_records": records_dict,
            "node_results": records_dict,
            "created_features": self.created_features,
            "rollback_status": self.rollback_status,
            "rollback_errors": self.rollback_errors,
            "mass_properties": self.mass_properties,
            "bounding_box": self.bounding_box,
            "saved_file_path": self.saved_file_path,
            "task_id": self.task_id,
            "rollback_occurred": self.rollback_occurred,
            "diagnostics": self.diagnostics,
        }


class CADGraphExecutor:
    """
    生产级 CAD 特征图执行引擎。
    负责接收 FeatureGraphIR，调度 STA Worker 并在 SolidWorks 进程中安全执行。
    """

    def __init__(
        self,
        sta_worker=None,
        sw_app=None,
        enable_task_context: bool = True,
        auto_rollback_on_failure: bool = True,
    ):
        """
        初始化执行引擎。
        支持外部依赖注入（用于 Mock 测试与脱机验证）。
        """
        self._sta_worker = sta_worker
        self._sw_app = sw_app
        self._enable_task_context = enable_task_context
        self._auto_rollback = auto_rollback_on_failure

    def _get_worker(self):
        if self._sta_worker is not None:
            return self._sta_worker
        try:
            return get_sta_worker()
        except Exception as e:
            logger.warning(f"无法获取 STA Worker: {e}")
            return None

    def execute(
        self,
        graph_input: Any,
        output_part_path: Optional[str] = None,
        model_doc: Optional[Any] = None,
        collect_metrics: bool = True,
        close_on_finish: bool = False,
    ) -> ExecutionResult:
        """
        统一外部执行入口。
        1. 静态解析与 DAG 依赖校验；
        2. 调度 STA Worker 执行线程，确保遵循 COM 规范；
        3. 捕获全局异常并返回结构化执行报告。
        """
        # 1. 结构与 DAG 校验
        if isinstance(graph_input, dict):
            ir_graph = compile_feature_graph_from_dict(graph_input)
        elif isinstance(graph_input, FeatureGraphIR):
            ir_graph = graph_input
            ir_graph.validate_dag()
        else:
            raise TypeError(f"不支持的图输入类型: {type(graph_input)}")

        worker = self._get_worker()
        # 若存在 STA Worker 且当前线程不是 Worker 线程，通过 Worker 派发执行
        if worker is not None and hasattr(worker, "execute"):
            return worker.execute(
                lambda: self._execute_internal(
                    ir_graph=ir_graph,
                    output_part_path=output_part_path,
                    model_doc=model_doc,
                    collect_metrics=collect_metrics,
                    close_on_finish=close_on_finish,
                )
            )

        # 否则直接在当前线程执行（例如 Mock 测试环境或无 STA 模式）
        return self._execute_internal(
            ir_graph=ir_graph,
            output_part_path=output_part_path,
            model_doc=model_doc,
            collect_metrics=collect_metrics,
            close_on_finish=close_on_finish,
        )

    def _execute_internal(
        self,
        ir_graph: FeatureGraphIR,
        output_part_path: Optional[str],
        model_doc: Optional[Any],
        collect_metrics: bool,
        close_on_finish: bool,
    ) -> ExecutionResult:
        """实际在 STA 线程中运行的执行主循环。"""
        task_id = f"graph_task_{ir_graph.graph_id}_{int(time.time()*1000)}"
        task_ctx: Optional[CADTaskContext] = None
        rollback_mgr: Optional[CADTaskRollbackManager] = None

        if self._enable_task_context:
            task_ctx = CADTaskContext(task_id=task_id)
            task_ctx.status = TaskStatus.RUNNING

        sw = self._sw_app
        created_doc = False
        model = model_doc

        # 0. 节点状态隔离重置，防止同一 IR 图重入执行时携带历史状态污染
        self._current_graph = ir_graph
        for n in ir_graph.nodes.values():
            n.status = NodeStatus.PENDING
            n.created_cad_entity = None

        start_wall_time = time.time()
        # 初始化执行结果容器
        result = ExecutionResult(
            success=False,
            status="FAILED",
            execution_id=task_id,
            graph_id=ir_graph.graph_id,
            target_part_name=ir_graph.target_part_name,
            total_nodes=len(ir_graph.nodes),
            executed_count=0,
            task_id=task_id,
        )

        try:
            # 2. 如果未传入已有模型，则连接 SolidWorks 并创建新零件
            if model is None:
                if sw is None:
                    sw, active_doc = connect_solidworks(wait_seconds=15, visible=False)
                    if sw is None:
                        raise RuntimeError("无法连接到本地 SolidWorks COM 实例")
                model = new_document(sw, "part")
                if model is None:
                    raise RuntimeError("无法创建 SolidWorks 零件文档")
                created_doc = True

            if model is not None:
                doc_title = str(get_com_member(model, "GetTitle") or "Part1")
                doc_path = str(get_com_member(model, "GetPathName") or "")
                effective_path = doc_path or (output_part_path or f"{doc_title}.SLDPRT")
                result.created_document = {
                    "title": doc_title,
                    "path": effective_path,
                    "is_newly_created": created_doc,
                }
                if task_ctx is not None:
                    task_ctx.register_document(
                        model=model,
                        title=doc_title,
                        path=effective_path,
                        is_newly_created=created_doc,
                    )

            # 3. 获取 Kahn 拓扑排序时序计划
            ordered_nodes = ir_graph.topological_sort()

            # 节点执行追踪表与实体继承映射表 (node_id -> cad_entity_name)
            node_entity_map: Dict[str, str] = {}
            failed_node_ids: Set[str] = set()
            skipped_node_ids: Set[str] = set()

            for node in ordered_nodes:
                rec = NodeExecutionRecord(
                    node_id=node.id,
                    feature_type=node.type.value if hasattr(node.type, "value") else str(node.type),
                    feature_name=node.name,
                    status=NodeStatus.PENDING,
                )
                result.node_records[node.id] = rec

                # 4. 依赖满足性检查：若前置依赖中有任何一个失败或跳过，当前节点自动跳过
                unmet_deps = [dep for dep in node.depends_on if dep in failed_node_ids or dep in skipped_node_ids]
                if unmet_deps:
                    node.status = NodeStatus.SKIPPED
                    rec.status = NodeStatus.SKIPPED
                    rec.error_type = "DependencyFailedError"
                    rec.error_message = f"前置依赖节点未就绪: {unmet_deps}"
                    skipped_node_ids.add(node.id)
                    result.skipped_nodes.append(node.id)
                    continue

                # 5. 执行当前节点
                node.status = NodeStatus.RUNNING
                rec.status = NodeStatus.RUNNING
                rec.start_time = time.time()
                result.executed_count += 1

                try:
                    cad_entity_name = self._dispatch_feature(
                        model=model,
                        node=node,
                        node_entity_map=node_entity_map,
                    )
                    rec.end_time = time.time()
                    rec.duration_ms = (rec.end_time - rec.start_time) * 1000.0
                    rec.status = NodeStatus.SUCCEEDED
                    rec.created_cad_entity = cad_entity_name
                    node.status = NodeStatus.SUCCEEDED
                    node.created_cad_entity = cad_entity_name

                    if cad_entity_name:
                        node_entity_map[node.id] = cad_entity_name
                        result.created_features.append(cad_entity_name)
                        if task_ctx is not None:
                            task_ctx.register_feature(cad_entity_name, node.type.value)

                    result.succeeded_nodes.append(node.id)

                except Exception as ex:
                    rec.end_time = time.time()
                    rec.duration_ms = (rec.end_time - rec.start_time) * 1000.0
                    rec.status = NodeStatus.FAILED
                    rec.error_type = type(ex).__name__
                    rec.error_message = str(ex)
                    node.status = NodeStatus.FAILED

                    failed_node_ids.add(node.id)
                    result.failed_nodes.append(node.id)
                    logger.error(f"特征节点 [{node.id}:{node.name}] 执行失败: {ex}", exc_info=True)

                    # 触发局域波及分析：将受影响的下游依赖子图全部标记为 SKIPPED
                    downstream_affected = ir_graph.get_reverse_rollback_subgraph(node.id)
                    for down_id in downstream_affected:
                        if down_id != node.id and down_id not in failed_node_ids and down_id not in skipped_node_ids:
                            skipped_node_ids.add(down_id)
                            result.skipped_nodes.append(down_id)
                            if down_id in ir_graph.nodes:
                                ir_graph.nodes[down_id].status = NodeStatus.SKIPPED
                            if down_id not in result.node_records:
                                down_node = ir_graph.nodes.get(down_id)
                                result.node_records[down_id] = NodeExecutionRecord(
                                    node_id=down_id,
                                    feature_type=down_node.type.value if down_node else "UNKNOWN",
                                    feature_name=down_node.name if down_node else down_id,
                                    status=NodeStatus.SKIPPED,
                                    error_type="DependencyFailedError",
                                    error_message=f"前置依赖节点 [{node.id}] 故障导致级联跳过",
                                )
                            else:
                                result.node_records[down_id].status = NodeStatus.SKIPPED
                                result.node_records[down_id].error_type = "DependencyFailedError"
                                result.node_records[down_id].error_message = f"前置依赖节点 [{node.id}] 故障导致级联跳过"

                    result.diagnostics[f"failure_{node.id}"] = {
                        "error_type": type(ex).__name__,
                        "error_message": str(ex),
                        "downstream_affected": downstream_affected,
                    }

                    # 若启用了自动回滚，对当前任务启动保护并中止后续执行
                    if self._auto_rollback and task_ctx is not None:
                        result.rollback_occurred = True
                        primary_err = f"节点 {node.id} 执行失败: {ex}"
                        task_ctx.errors.append(primary_err)
                        result.diagnostics["primary_failure"] = primary_err
                        try:
                            rollback_mgr = CADTaskRollbackManager(context=task_ctx, sw_app=sw)
                            rb_res = rollback_mgr.rollback()
                            result.rollback_status = rb_res.status.value
                            result.rollback_errors = list(rb_res.errors)

                            # 标注已创建的实体为回滚状态
                            for r_nid, r_rec in result.node_records.items():
                                if r_rec.status == NodeStatus.SUCCEEDED and r_rec.created_cad_entity:
                                    r_rec.status = NodeStatus.ROLLED_BACK
                                    result.rolled_back_nodes.append(r_nid)

                            if rb_res.status == RollbackStatus.SUCCESS:
                                result.status = "ROLLED_BACK"
                            elif rb_res.status == RollbackStatus.PARTIAL:
                                result.status = "PARTIAL_ROLLED_BACK"
                            else:
                                result.status = "FAILED"
                        except Exception as rb_err:
                            logger.error(f"任务回滚出现二次异常: {rb_err}")
                            result.rollback_status = "FAILED"
                            result.rollback_errors.append(f"二次异常: {str(rb_err)}")
                            result.diagnostics["rollback_error"] = str(rb_err)
                            result.status = "FAILED"
                        break
                    # 若未启用自动回滚，允许主循环继续处理其他不相关的并行独立分支

            # 6. 计算整体成功状态
            result.duration_ms = (time.time() - start_wall_time) * 1000.0
            if len(result.failed_nodes) == 0 and len(result.succeeded_nodes) == len(ordered_nodes):
                result.success = True
                result.status = "COMPLETED"
                result.rollback_status = "NOT_NEEDED"
                if task_ctx is not None:
                    task_ctx.status = TaskStatus.COMPLETED

                # 重建模型
                try:
                    rebuild_code = get_com_member(model, "EditRebuild3")
                    if rebuild_code is False:
                        result.diagnostics["rebuild_warning"] = "EditRebuild3 返回 False"
                except Exception as reb_err:
                    result.diagnostics["rebuild_warning"] = str(reb_err)

                # 落盘保存
                if output_part_path:
                    try:
                        save_document(model, output_part_path)
                        result.saved_file_path = output_part_path
                    except Exception as save_err:
                        logger.warning(f"保存文档失败: {save_err}")
                        result.diagnostics["save_error"] = str(save_err)

                # 测量几何质量属性
                if collect_metrics:
                    try:
                        result.mass_properties = collect_mass_properties(model)
                    except Exception as m_err:
                        logger.debug(f"提取质量属性异常: {m_err}")
                    try:
                        result.bounding_box = collect_bounding_box(model)
                    except Exception as b_err:
                        logger.debug(f"提取包围盒异常: {b_err}")

            return result

        finally:
            # 7. 清理或关闭文档
            # 安全铁律：只有由本任务全新创建的文档 (created_doc=True) 才允许自动关闭，绝对不得误关用户已有文档！
            if close_on_finish and created_doc and sw is not None and model is not None:
                try:
                    # 检查是否此前回滚流程已经安全关闭过
                    already_closed = False
                    if task_ctx is not None:
                        for d in task_ctx.tracked_documents.values():
                            if d.is_newly_created and d.closed:
                                already_closed = True
                                break
                    if not already_closed:
                        doc_title = get_com_member(model, "GetTitle")
                        if doc_title:
                            get_com_member(sw, "CloseDoc", doc_title)
                except Exception as close_err:
                    # 清理异常只记录诊断，绝不覆盖建模原始错误
                    result.diagnostics["close_doc_error"] = str(close_err)

    def _dispatch_feature(
        self,
        model: Any,
        node: FeatureNode,
        node_entity_map: Dict[str, str],
        *args,
        **kwargs,
    ) -> Optional[str]:
        """
        根据节点特征类型分发执行底层的 CAD API。
        同时支持从前置节点自动继承实体名称句柄。
        """
        ftype = node.type
        args = dict(node.parameters)

        # 辅助解析前置草图名称
        def resolve_parent_sketch() -> str:
            # 1. 显式指定的草图名优先级最高
            if "sketch_name" in args and args["sketch_name"]:
                return str(args["sketch_name"])

            # 2. 严格从依赖列表中逆序检索最近的有效草图类型节点
            cur_graph = getattr(self, "_current_graph", None)
            for dep_id in reversed(node.depends_on):
                dep_node = cur_graph.nodes.get(dep_id) if cur_graph else None
                # 只有草图节点才能被拉伸/旋转等实体特征作为轮廓消费
                if dep_node and dep_node.type == FeatureType.SKETCH_2D:
                    if dep_id in node_entity_map:
                        return node_entity_map[dep_id]
                    elif dep_node.created_cad_entity:
                        return dep_node.created_cad_entity
                    elif dep_node.name:
                        return dep_node.name

            # 3. 若依赖链未显式提供草图，且当前特征属于强依赖草图的特征，抛出确定性异常
            raise ValueError(
                f"特征节点 [{node.id}:{node.name}] (类型 {ftype}) 缺少必需的草图依赖引用。"
                f"未在 depends_on: {node.depends_on} 中解析到有效的已执行草图实体。"
            )

        # -------------------------------------------------------------
        # 1. 2D 草图 (SKETCH_2D)
        # -------------------------------------------------------------
        if ftype == FeatureType.SKETCH_2D:
            plane_name = args.get("plane", "Front Plane")
            start_sketch(model, plane_name=plane_name)
            if node.name:
                try:
                    act_sk = model.SketchManager.ActiveSketch
                    if act_sk:
                        act_sk.Name = node.name
                except Exception:
                    pass

            rect_lines = None
            circle_obj = None

            # 若定义了中心旋转轴，提前绘制构造线
            if "centerline" in args and isinstance(args["centerline"], dict):
                cl = args["centerline"]
                model.SketchManager.CreateCenterLine(
                    float(cl.get("x1_m", 0.0)),
                    float(cl.get("y1_m", 0.0)),
                    0.0,
                    float(cl.get("x2_m", 0.0)),
                    float(cl.get("y2_m", 0.0)),
                    0.0,
                )
            shape = args.get("shape", "rectangle")
            if shape == "rectangle":
                w = float(args["width_m"])
                h = float(args["height_m"])
                cx = float(args.get("cx_m", 0.0))
                cy = float(args.get("cy_m", 0.0))
                sketch_rectangle(model, cx, cy, w, h)
            elif shape == "corner_rectangle":
                x1 = float(args["x1_m"])
                y1 = float(args["y1_m"])
                x2 = float(args["x2_m"])
                y2 = float(args["y2_m"])
                rect_lines = sketch_corner_rectangle(model, x1, y1, x2, y2)
            elif shape == "circle":
                r = float(args["radius_m"])
                cx = float(args.get("cx_m", 0.0))
                cy = float(args.get("cy_m", 0.0))
                circle_obj = sketch_circle(model, cx, cy, r)
            elif shape == "line":
                x1 = float(args["x1_m"])
                y1 = float(args["y1_m"])
                x2 = float(args["x2_m"])
                y2 = float(args["y2_m"])
                sketch_line(model, x1, y1, x2, y2)
            elif shape == "arc":
                cx = float(args["cx_m"])
                cy = float(args["cy_m"])
                x1 = float(args["x1_m"])
                y1 = float(args["y1_m"])
                x2 = float(args["x2_m"])
                y2 = float(args["y2_m"])
                direction = int(args.get("direction", 1))
                sketch_arc(model, cx, cy, x1, y1, x2, y2, direction)
            elif shape == "polygon":
                cx = float(args.get("cx_m", 0.0))
                cy = float(args.get("cy_m", 0.0))
                r = float(args["radius_m"])
                sides = int(args.get("sides", 6))
                sketch_polygon(model, cx, cy, r, sides)
            elif shape == "slot":
                x1 = float(args["x1_m"])
                y1 = float(args["y1_m"])
                x2 = float(args["x2_m"])
                y2 = float(args["y2_m"])
                r = float(args["radius_m"])
                sketch_slot(model, x1, y1, x2, y2, r)
            elif shape == "spline":
                points = args.get("points", [])
                sketch_spline(model, points)
            else:
                raise ValueError(f"未知的草图几何图元类型: {shape}")

            # 若请求自动标注尺寸，在草图退出前施加真实 DisplayDimension
            if bool(args.get("add_dimensions", False)):
                try:
                    try:
                        from .sw_part import _empty_callout
                    except Exception:
                        from sw_part import _empty_callout
                    if shape == "corner_rectangle" and rect_lines:
                        model.ClearSelection2(True)
                        rect_lines[0].Select4(False, _empty_callout())
                        model.AddDimension2((x1 + x2) / 2.0, y1 - 0.015, 0)
                        model.ClearSelection2(True)
                        rect_lines[1].Select4(False, _empty_callout())
                        model.AddDimension2(x2 + 0.015, (y1 + y2) / 2.0, 0)
                    elif shape == "circle" and circle_obj:
                        model.ClearSelection2(True)
                        circle_obj.Select4(False, _empty_callout())
                        model.AddDimension2(cx + r * 1.5, cy + r * 1.5, 0)
                except Exception as dim_err:
                    logger.warning(f"草图自动标注尺寸异常: {dim_err}")

            sketch_name = current_sketch_name(model, fallback=node.name or "Sketch1")
            end_sketch(model)
            return sketch_name

        # -------------------------------------------------------------
        # 2. 拉伸凸台 (EXTRUDE_BOSS)
        # -------------------------------------------------------------
        elif ftype == FeatureType.EXTRUDE_BOSS:
            sk_name = resolve_parent_sketch()
            depth_m = float(args["depth_m"])
            direction = bool(args.get("direction", True))
            merge = bool(args.get("merge", True))
            midplane = bool(args.get("midplane", False))

            if midplane:
                feat = extrude_midplane(model, sk_name, depth_m)
            else:
                feat = extrude_boss(model, sk_name, depth_m, direction=direction, merge=merge)
            if feat is False or feat is None:
                raise RuntimeError(f"SolidWorks 凸台拉伸求解失败: 特征 [{node.id}:{node.name}] 返回空对象")
            if feat and node.name:
                try:
                    feat.Name = node.name
                except Exception:
                    pass
            feat_name = getattr(feat, "Name", None) if hasattr(feat, "Name") else None
            return feat_name or node.name or "Boss-Extrude1"

        # -------------------------------------------------------------
        # 3. 拉伸切除 (EXTRUDE_CUT)
        # -------------------------------------------------------------
        elif ftype == FeatureType.EXTRUDE_CUT:
            sk_name = resolve_parent_sketch()
            depth_m = float(args.get("depth_m", 0.01))
            direction = bool(args.get("direction", False))
            flip = bool(args.get("flip", False))
            feat = extrude_cut(model, sk_name, depth_m, direction=direction, flip=flip)
            if feat is False or feat is None:
                raise RuntimeError(f"SolidWorks 拉伸切除求解失败: 特征 [{node.id}:{node.name}] 返回空对象")
            if feat and node.name:
                try:
                    feat.Name = node.name
                except Exception:
                    pass
            feat_name = getattr(feat, "Name", None) if hasattr(feat, "Name") else None
            return feat_name or node.name or "Cut-Extrude1"

        # -------------------------------------------------------------
        # 4. 旋转凸台 (REVOLVE_BOSS)
        # -------------------------------------------------------------
        elif ftype == FeatureType.REVOLVE_BOSS:
            sk_name = resolve_parent_sketch()
            angle_rad = float(args.get("angle_rad", 6.283185307179586))
            axis_name = args.get("axis_name", None)
            feat = revolve_boss(model, sk_name, angle_rad, axis_sketch_name=axis_name)
            if feat is False or feat is None:
                raise RuntimeError(f"SolidWorks 旋转凸台求解失败: 特征 [{node.id}:{node.name}] 返回空对象")
            if feat and node.name:
                try:
                    feat.Name = node.name
                except Exception:
                    pass
            feat_name = getattr(feat, "Name", None) if hasattr(feat, "Name") else None
            return feat_name or node.name or "Revolve1"

        # -------------------------------------------------------------
        # 5. 圆角 (FILLET)
        # -------------------------------------------------------------
        elif ftype == FeatureType.FILLET:
            radius_m = float(args["radius_m"])
            edges = args.get("edges", None)
            feat = fillet(model, radius_m, edges=edges)
            if feat is False or feat is None:
                raise RuntimeError(f"SolidWorks 倒圆角特征求解失败: 特征 [{node.id}:{node.name}] 返回空对象")
            if feat and node.name:
                try:
                    feat.Name = node.name
                except Exception:
                    pass
            feat_name = getattr(feat, "Name", None) if hasattr(feat, "Name") else None
            return feat_name or node.name or "Fillet1"

        # -------------------------------------------------------------
        # 6. 倒角 (CHAMFER)
        # -------------------------------------------------------------
        elif ftype == FeatureType.CHAMFER:
            distance_m = float(args["distance_m"])
            angle_deg = float(args.get("angle_deg", 45.0))
            feat = chamfer(model, distance_m, angle_deg=angle_deg)
            if feat is False or feat is None:
                raise RuntimeError(f"SolidWorks 倒角特征求解失败: 特征 [{node.id}:{node.name}] 返回空对象")
            if feat and node.name:
                try:
                    feat.Name = node.name
                except Exception:
                    pass
            feat_name = getattr(feat, "Name", None) if hasattr(feat, "Name") else None
            return feat_name or node.name or "Chamfer1"

        # -------------------------------------------------------------
        # 7. 线性阵列 (LINEAR_PATTERN)
        # -------------------------------------------------------------
        elif ftype == FeatureType.LINEAR_PATTERN:
            seed_feature = args.get("seed_feature")
            if not seed_feature:
                for dep_id in reversed(node.depends_on):
                    if dep_id in node_entity_map:
                        seed_feature = node_entity_map[dep_id]
                        break
            if not seed_feature:
                raise ValueError(f"线性阵列节点 [{node.id}] 缺少 seed_feature 母特征引用")

            first_dir = tuple(args.get("first_direction", [1.0, 0.0, 0.0]))
            spacing_m = float(args.get("spacing_m", 0.020))
            count = int(args.get("count", 2))
            second_dir = tuple(args.get("second_direction", [0.0, 0.0, 0.0]))
            second_spacing_m = float(args.get("second_spacing_m", 0.0))
            second_count = int(args.get("second_count", 1))

            try:
                from .sw_pattern import linear_pattern
            except Exception:
                from sw_pattern import linear_pattern

            feat = linear_pattern(
                model=model,
                feature_name=seed_feature,
                first=first_dir,
                spacing=spacing_m,
                count=count,
                second=second_dir,
                second_spacing=second_spacing_m,
                second_count=second_count,
            )
            if feat and node.name:
                try:
                    feat.Name = node.name
                except Exception:
                    pass
            feat_name = getattr(feat, "Name", None) if hasattr(feat, "Name") else None
            return feat_name or node.name or "LinearPattern1"

        # -------------------------------------------------------------
        # 8. 圆周阵列 (CIRCULAR_PATTERN)
        # -------------------------------------------------------------
        elif ftype == FeatureType.CIRCULAR_PATTERN:
            seed_feature = args.get("seed_feature")
            if not seed_feature:
                for dep_id in reversed(node.depends_on):
                    if dep_id in node_entity_map:
                        seed_feature = node_entity_map[dep_id]
                        break
            if not seed_feature:
                raise ValueError(f"圆周阵列节点 [{node.id}] 缺少 seed_feature 母特征引用")

            axis = args.get("axis", "axis")
            angle_rad = float(args.get("angle_rad", 6.283185307179586))
            count = int(args.get("count", 4))
            equal_spacing = bool(args.get("equal_spacing", True))

            try:
                from .sw_pattern import circular_pattern
            except Exception:
                from sw_pattern import circular_pattern

            feat = circular_pattern(
                model=model,
                feature_name=seed_feature,
                axis=axis,
                angle=angle_rad,
                count=count,
                equal_spacing=equal_spacing,
            )
            if feat and node.name:
                try:
                    feat.Name = node.name
                except Exception:
                    pass
            feat_name = getattr(feat, "Name", None) if hasattr(feat, "Name") else None
            return feat_name or node.name or "CircularPattern1"

        # -------------------------------------------------------------
        # 9. 异型孔向导 (HOLE_WIZARD)
        # -------------------------------------------------------------
        elif ftype == FeatureType.HOLE_WIZARD:
            hole_type = int(args.get("hole_type", 0))
            standard = int(args.get("standard", 1))
            fastener_type = int(args.get("fastener_type", 0))
            size = str(args.get("size", "M6"))
            depth_m = float(args.get("depth_m", 0.02))
            x = float(args.get("x_m", 0.0))
            y = float(args.get("y_m", 0.0))
            z = float(args.get("z_m", 0.0))
            hole_wizard(model, hole_type, standard, fastener_type, size, depth_m, x, y, z)
            return node.name or "HoleWizard1"

        # -------------------------------------------------------------
        # 其他或扩展特征类型
        # -------------------------------------------------------------
        else:
            raise NotImplementedError(f"FeatureGraph 尚未支持该特征类型分发: {ftype}")
