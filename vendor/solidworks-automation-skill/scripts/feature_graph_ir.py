# -*- coding: utf-8 -*-
"""
SolidWorks Feature Graph IR (特征拓扑依赖图中间表示与编译器)

设计定位：
在自然语言意图规划与底层 CAD API 执行之间建立结构化 DAG 编译器。
实现能力：
1. 节点与前置时序依赖强校验 (严格有向无环图 DAG)；
2. Kahn 拓扑排序算法，生成确定性建模时序计划；
3. 循环闭环依赖（Cyclic Dependency）与未定义依赖静态检测；
4. 故障逆向依赖子树推导，支持精准局域回滚。
"""

from collections import deque
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, ConfigDict, Field


class FeatureType(str, Enum):
    REFERENCE_PLANE = "reference_plane"
    SKETCH_2D = "sketch_2d"
    EXTRUDE_BOSS = "extrude_boss"
    EXTRUDE_CUT = "extrude_cut"
    REVOLVE_BOSS = "revolve_boss"
    REVOLVE_CUT = "revolve_cut"
    FILLET = "fillet"
    CHAMFER = "chamfer"
    HOLE_WIZARD = "hole_wizard"
    LINEAR_PATTERN = "linear_pattern"
    CIRCULAR_PATTERN = "circular_pattern"


class NodeStatus(str, Enum):
    """特征图节点生命周期状态。"""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"
    SKIPPED = "SKIPPED"


class UndefinedDependencyError(Exception):
    """当特征节点引用了不存在的前置依赖时抛出。"""
    pass


class CyclicDependencyError(Exception):
    """当特征图中存在循环闭环依赖（时序死锁）时抛出。"""
    pass


class FeatureNode(BaseModel):
    """特征图中的单个特征节点。"""
    id: str = Field(..., description="节点唯一标识符, 如 node_sketch_base")
    type: FeatureType = Field(..., description="特征类型")
    name: str = Field(..., description="SolidWorks 对应特征名称, 如 Sketch1")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="特征几何与尺寸参数")
    depends_on: List[str] = Field(default_factory=list, description="前置依赖节点 ID 列表")
    status: NodeStatus = Field(default=NodeStatus.PENDING, description="节点执行状态")
    created_cad_entity: Optional[str] = Field(default=None, description="底层创建的实际 CAD 特征/草图名称")

    model_config = ConfigDict(arbitrary_types_allowed=True)


class FeatureGraphIR(BaseModel):
    """完整的特征有向无环图（DAG）中间表示。"""
    graph_id: str = Field(default="fg_default", description="图唯一标识")
    target_part_name: str = Field(default="part_1", description="目标零件名称")
    nodes: Dict[str, FeatureNode] = Field(default_factory=dict, description="节点字典: id -> FeatureNode")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")

    def add_node(self, node: FeatureNode) -> "FeatureGraphIR":
        """向图中添加新节点。"""
        self.nodes[node.id] = node
        return self

    def validate_dag(self) -> None:
        """
        静态验证图的拓扑有效性。
        1. 检查是否存在未定义的悬挂依赖；
        2. 检查是否存在循环回路。
        """
        # 1. 检查悬空依赖
        all_ids = set(self.nodes.keys())
        for node_id, node in self.nodes.items():
            for dep in node.depends_on:
                if dep not in all_ids:
                    raise UndefinedDependencyError(
                        f"特征节点 '{node_id}' 引用了未定义的前置依赖: '{dep}'"
                    )

        # 2. 检查环路依赖
        self.topological_sort()

    def topological_sort(self) -> List[FeatureNode]:
        """
        使用 Kahn 算法对特征节点进行确定性拓扑排序。
        返回严格按照前置依赖顺序排列的节点序列。
        若存在环路死锁，抛出 CyclicDependencyError。
        """
        all_nodes = self.nodes
        in_degree: Dict[str, int] = {node_id: 0 for node_id in all_nodes}
        adjacency: Dict[str, List[str]] = {node_id: [] for node_id in all_nodes}

        # 构建邻接表与入度表 (u -> v 表示 u 是 v 的前置条件)
        for node_id, node in all_nodes.items():
            for dep in node.depends_on:
                if dep in adjacency:
                    adjacency[dep].append(node_id)
                    in_degree[node_id] += 1
                else:
                    raise UndefinedDependencyError(
                        f"特征节点 '{node_id}' 引用了未定义的前置依赖: '{dep}'"
                    )

        # 收集所有入度为 0 的节点 (没有前置依赖的起点)
        # 为保证排序结果的一致确定性，按 ID 字典序稳定排序
        queue = deque(sorted([node_id for node_id, deg in in_degree.items() if deg == 0]))
        sorted_nodes: List[FeatureNode] = []

        while queue:
            current_id = queue.popleft()
            sorted_nodes.append(all_nodes[current_id])

            for neighbor in sorted(adjacency[current_id]):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # 若排序后的节点数少于总节点数，说明图中存在无法破除的有向环
        if len(sorted_nodes) < len(all_nodes):
            cyclic_nodes = [node_id for node_id, deg in in_degree.items() if deg > 0]
            raise CyclicDependencyError(
                f"特征图存在时序闭环死锁 (Cyclic Dependency)，涉及节点: {cyclic_nodes}"
            )

        return sorted_nodes

    def compile_execution_plan(self) -> List[Dict[str, Any]]:
        """
        将拓扑排序后的特征图编译为可执行的指令流水线（Execution Plan）。
        映射到现有的 MCP 工具契约。
        """
        ordered_nodes = self.topological_sort()
        plan: List[Dict[str, Any]] = []

        TOOL_MAPPING = {
            FeatureType.SKETCH_2D: "solidworks_create_sketch",
            FeatureType.EXTRUDE_BOSS: "solidworks_create_extrude",
            FeatureType.EXTRUDE_CUT: "solidworks_create_cut",
            FeatureType.FILLET: "solidworks_create_fillet",
            FeatureType.CHAMFER: "solidworks_create_chamfer",
            FeatureType.HOLE_WIZARD: "solidworks_create_hole",
        }

        for step_idx, node in enumerate(ordered_nodes, start=1):
            tool_name = TOOL_MAPPING.get(node.type, f"solidworks_create_{node.type.value}")
            step = {
                "step_index": step_idx,
                "node_id": node.id,
                "feature_type": node.type.value,
                "feature_name": node.name,
                "tool_name": tool_name,
                "arguments": dict(node.parameters),
                "depends_on": list(node.depends_on),
            }
            plan.append(step)

        return plan

    def get_reverse_rollback_subgraph(self, failed_node_id: str) -> List[str]:
        """
        当某个节点在执行期发生几何求解失败时，计算所有直接或间接依赖它的下游节点。
        这些下游节点必须随之一同回滚，而与它并行的无依赖分支可安全保留。
        """
        if failed_node_id not in self.nodes:
            return []

        # 构建正向邻接表 (u -> v, v 依赖 u)
        downstream: Dict[str, List[str]] = {nid: [] for nid in self.nodes}
        for nid, node in self.nodes.items():
            for dep in node.depends_on:
                if dep in downstream:
                    downstream[dep].append(nid)

        affected: Set[str] = set()
        queue = deque([failed_node_id])

        while queue:
            curr = queue.popleft()
            affected.add(curr)
            for child in downstream.get(curr, []):
                if child not in affected:
                    queue.append(child)

        return sorted(list(affected))

    def evaluate_failure_and_rollback(self, failed_node_id: str) -> Dict[str, Any]:
        """
        评估节点故障波及面，并生成精准局部回滚与保留计划：
        1. 识别成功且不依赖失败节点的特征（保留）；
        2. 识别失败节点及其下游依赖子图；
        3. 区分已产生 CAD 实体需逆序删除的节点，与尚未执行直接跳过的节点；
        4. 更新图节点状态（FAILED, ROLLED_BACK, SKIPPED）。
        """
        if failed_node_id not in self.nodes:
            return {"status": "error", "message": f"节点不存在: {failed_node_id}"}

        # 标记当前节点失败
        failed_node = self.nodes[failed_node_id]
        failed_node.status = NodeStatus.FAILED

        # 获取下游受波及节点（包含 failed_node_id 本身）
        downstream_ids = set(self.get_reverse_rollback_subgraph(failed_node_id))

        nodes_to_delete_cad: List[Dict[str, str]] = []
        nodes_to_skip: List[str] = []
        nodes_to_keep: List[str] = []

        # 逆序（后执行的先清理）
        ordered = self.topological_sort()
        for node in reversed(ordered):
            if node.id in downstream_ids:
                if node.id == failed_node_id:
                    # 失败节点若产生了部分实体，需要清理
                    if node.created_cad_entity:
                        nodes_to_delete_cad.append({
                            "node_id": node.id,
                            "cad_entity": node.created_cad_entity,
                            "type": node.type.value,
                        })
                else:
                    if node.status in (NodeStatus.SUCCEEDED, NodeStatus.RUNNING) and node.created_cad_entity:
                        node.status = NodeStatus.ROLLED_BACK
                        nodes_to_delete_cad.append({
                            "node_id": node.id,
                            "cad_entity": node.created_cad_entity,
                            "type": node.type.value,
                        })
                    else:
                        node.status = NodeStatus.SKIPPED
                        nodes_to_skip.append(node.id)
            else:
                if node.status == NodeStatus.SUCCEEDED:
                    nodes_to_keep.append(node.id)

        return {
            "failed_node_id": failed_node_id,
            "entities_to_delete_reversed": nodes_to_delete_cad,
            "nodes_skipped": nodes_to_skip,
            "nodes_retained": nodes_to_keep,
        }


def compile_feature_graph_from_dict(data: Dict[str, Any]) -> FeatureGraphIR:
    """从普通字典构造并验证 FeatureGraphIR。"""
    raw_nodes = data.get("nodes", {})
    parsed_nodes = {}
    for nid, nval in raw_nodes.items():
        if isinstance(nval, dict):
            nval["id"] = nid
            parsed_nodes[nid] = FeatureNode(**nval)
        elif isinstance(nval, FeatureNode):
            parsed_nodes[nid] = nval

    graph = FeatureGraphIR(
        graph_id=data.get("graph_id", "fg_default"),
        target_part_name=data.get("target_part_name", "part_1"),
        nodes=parsed_nodes,
        metadata=data.get("metadata", {}),
    )
    graph.validate_dag()
    return graph
