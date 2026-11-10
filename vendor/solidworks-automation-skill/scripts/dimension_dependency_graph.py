# -*- coding: utf-8 -*-
"""
vendor/solidworks-automation-skill/scripts/dimension_dependency_graph.py
SolidWorks 参数/尺寸依赖图 (Dimension Dependency Graph, DDG)。

核心职责：
1. 建立特征拓扑 (Feature Graph) 与尺寸参数 (Dimension IR) 之间的多对多映射网络；
2. 识别上游驱动尺寸 (Upstream Driving Dimensions) 与下游从动特征/尺寸 (Downstream Features/Dimensions)；
3. 支持循环依赖检测 (Cycle Detection) 与拓扑偏序分析 (Topological Sort)；
4. 变更影响域分析 (Impact Scope Analysis)：当某个驱动尺寸变更时，自动提取受波及的特征链与从动尺寸；
5. 多轮连续修改零漂移核验 (Zero Drift Tracker)：严苛确保未被指定修改的尺寸在全过程中无意外位移或参数退化。
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field

from dimension_ir import DimensionIRNode, DimensionModelIR, DimensionRole, DimensionType


class DDGEdge(BaseModel):
    """DDG 依赖边元数据。"""
    upstream: str = Field(..., description="上游尺寸或特征标识符")
    downstream: str = Field(..., description="下游尺寸或特征标识符")
    relation_type: str = Field(default="feature_hierarchy", description="依赖类型: feature_hierarchy, sketch_to_feature, equation, geometric_align")
    description: str = Field(default="", description="关系描述")


class DDGImpactReport(BaseModel):
    """变更影响域分析报告。"""
    target_modifications: Dict[str, float] = Field(default_factory=dict, description="本轮目标变更尺寸及目标值")
    direct_nodes: List[str] = Field(default_factory=list, description="直接修改的目标节点")
    affected_features: List[str] = Field(default_factory=list, description="受波及需要更新/重建的特征列表")
    affected_dimensions: List[str] = Field(default_factory=list, description="间接受影响的下游尺寸列表")
    topological_rebuild_order: List[str] = Field(default_factory=list, description="建议的特征重建与刷新拓扑序")
    has_cycles: bool = Field(default=False, description="是否存在循环依赖")
    cycle_paths: List[List[str]] = Field(default_factory=list, description="检测到的循环路径")


class DimensionDependencyGraph:
    """SolidWorks 参数与尺寸依赖拓扑图 (DDG)。"""

    def __init__(self, model_title: str = "Part"):
        self.model_title = model_title
        # 尺寸节点容器: name -> DimensionIRNode
        self.dimension_nodes: Dict[str, DimensionIRNode] = {}
        # 特征节点容器: feature_name -> 特征类型
        self.feature_types: Dict[str, str] = {}
        # 特征所属的尺寸映射: feature_name -> Set[dimension_name]
        self.feature_to_dimensions: Dict[str, Set[str]] = defaultdict(set)
        # 尺寸所属的特征映射: dimension_name -> feature_name
        self.dimension_to_feature: Dict[str, str] = {}

        # 依赖有向图：上游 -> 下游
        self.forward_edges: Dict[str, Set[str]] = defaultdict(set)
        # 反向依赖图：下游 -> 上游
        self.reverse_edges: Dict[str, Set[str]] = defaultdict(set)
        # 边元数据
        self.edge_details: Dict[Tuple[str, str], DDGEdge] = {}

    def add_dimension(self, node: DimensionIRNode, feature_name: Optional[str] = None) -> None:
        """向依赖图注册尺寸节点。"""
        dim_name = node.dimension_name
        self.dimension_nodes[dim_name] = node
        feat = feature_name or node.feature_name
        if feat:
            self.dimension_to_feature[dim_name] = feat
            self.feature_to_dimensions[feat].add(dim_name)
            # 草图尺寸天然驱动所属特征
            self.add_dependency(dim_name, feat, relation_type="sketch_to_feature", desc=f"尺寸 {dim_name} 驱动特征 {feat}")

    def add_feature(self, feature_name: str, feature_type: str = "Feature") -> None:
        """注册特征节点。"""
        self.feature_types[feature_name] = feature_type

    def add_dependency(self, upstream: str, downstream: str, relation_type: str = "feature_hierarchy", desc: str = "") -> None:
        """添加一条上游到下游的依赖有向边 (upstream -> downstream)。"""
        self.forward_edges[upstream].add(downstream)
        self.reverse_edges[downstream].add(upstream)
        self.edge_details[(upstream, downstream)] = DDGEdge(
            upstream=upstream,
            downstream=downstream,
            relation_type=relation_type,
            description=desc,
        )

    def detect_cycles(self) -> List[List[str]]:
        """检测图中是否存在环路 (Tarjan / DFS 回溯)。"""
        visited: Dict[str, int] = {}  # 0: 未访问, 1: 正在当前路径, 2: 已完全访问
        cycle_paths: List[List[str]] = []
        path: List[str] = []

        all_nodes = set(self.dimension_nodes.keys()) | set(self.feature_types.keys()) | set(self.forward_edges.keys())

        def _dfs(u: str):
            visited[u] = 1
            path.append(u)
            for v in self.forward_edges.get(u, set()):
                if visited.get(v, 0) == 1:
                    # 发现环路
                    idx = path.index(v)
                    cycle_paths.append(path[idx:] + [v])
                elif visited.get(v, 0) == 0:
                    _dfs(v)
            path.pop()
            visited[u] = 2

        for node in all_nodes:
            if visited.get(node, 0) == 0:
                _dfs(node)

        return cycle_paths

    def topological_sort(self) -> List[str]:
        """返回拓扑排序序列（Kahn 算法）。如果存在环路则抛出 ValueError。"""
        cycles = self.detect_cycles()
        if cycles:
            raise ValueError(f"DDG 图中存在循环依赖，无法进行拓扑排序: {cycles}")

        all_nodes = set(self.dimension_nodes.keys()) | set(self.feature_types.keys()) | set(self.forward_edges.keys()) | set(self.reverse_edges.keys())
        in_degree: Dict[str, int] = {node: 0 for node in all_nodes}

        for u, neighbors in self.forward_edges.items():
            for v in neighbors:
                in_degree[v] = in_degree.get(v, 0) + 1

        queue = deque([node for node, deg in in_degree.items() if deg == 0])
        sorted_order: List[str] = []

        while queue:
            curr = queue.popleft()
            sorted_order.append(curr)
            for nxt in self.forward_edges.get(curr, set()):
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)

        if len(sorted_order) < len(all_nodes):
            unresolved = all_nodes - set(sorted_order)
            raise ValueError(f"拓扑排序未完全解析节点: {unresolved}")

        return sorted_order

    def get_impact_scope(self, dim_or_feat_name: str) -> Set[str]:
        """获取某个尺寸或特征变更后波及的全部下游节点（传递闭包）。"""
        visited: Set[str] = set()
        queue = deque([dim_or_feat_name])

        while queue:
            curr = queue.popleft()
            for child in self.forward_edges.get(curr, set()):
                if child not in visited:
                    visited.add(child)
                    queue.append(child)

        return visited

    def analyze_modification_impact(self, target_modifications: Dict[str, float]) -> DDGImpactReport:
        """分析一组尺寸变更的影响域与重建拓扑建议。"""
        cycles = self.detect_cycles()
        direct_nodes = list(target_modifications.keys())
        all_affected: Set[str] = set()

        for dim_name in direct_nodes:
            all_affected.update(self.get_impact_scope(dim_name))

        affected_features: List[str] = []
        affected_dimensions: List[str] = []

        for item in all_affected:
            if item in self.feature_types:
                affected_features.append(item)
            else:
                affected_dimensions.append(item)

        # 提取相关特征的拓扑刷新次序
        topo_rebuild: List[str] = []
        if not cycles:
            try:
                full_order = self.topological_sort()
                topo_rebuild = [x for x in full_order if x in affected_features or x in direct_nodes]
            except Exception:
                topo_rebuild = affected_features

        return DDGImpactReport(
            target_modifications=target_modifications,
            direct_nodes=direct_nodes,
            affected_features=affected_features,
            affected_dimensions=affected_dimensions,
            topological_rebuild_order=topo_rebuild,
            has_cycles=len(cycles) > 0,
            cycle_paths=cycles,
        )

    @classmethod
    def from_feature_graph_ir(
        cls,
        feature_graph: Any,
        model_ir: Optional[DimensionModelIR] = None,
    ) -> "DimensionDependencyGraph":
        """
        从 FeatureGraphIR 与 DimensionModelIR 交叉编译构建完整的参数依赖图。
        """
        ddg = cls(model_title=getattr(feature_graph, "target_part_name", "Part"))

        # 1. 注册特征节点与特征级依赖
        nodes = getattr(feature_graph, "nodes", {})
        for node_id, feat_node in nodes.items():
            feat_name = feat_node.name or node_id
            ddg.add_feature(feat_name, str(feat_node.type))

        for node_id, feat_node in nodes.items():
            downstream_feat = feat_node.name or node_id
            for dep_id in feat_node.depends_on:
                parent_node = nodes.get(dep_id)
                if parent_node:
                    upstream_feat = parent_node.name or dep_id
                    ddg.add_dependency(
                        upstream_feat,
                        downstream_feat,
                        relation_type="feature_hierarchy",
                        desc=f"特征 {upstream_feat} 支撑特征 {downstream_feat}",
                    )

        # 2. 映射尺寸节点
        if model_ir:
            for dim_name, dim_node in model_ir.dimensions.items():
                ddg.add_dimension(dim_node, feature_name=dim_node.feature_name)
                # 如果所属特征存在下游特征，则尺寸天然间接影响下游特征
                feat = dim_node.feature_name
                if feat and feat in ddg.forward_edges:
                    for downstream in ddg.forward_edges[feat]:
                        ddg.add_dependency(
                            dim_name,
                            downstream,
                            relation_type="sketch_to_downstream_feature",
                            desc=f"尺寸 {dim_name} 传递影响下游特征 {downstream}",
                        )

        return ddg

    @staticmethod
    def verify_zero_drift(
        baseline_dims: Dict[str, float],
        current_dims: Dict[str, float],
        target_modifications: Dict[str, float],
        tolerance_mm: float = 0.005,
    ) -> Tuple[bool, List[Dict[str, Any]]]:
        """
        零漂移验证器 (Zero Drift Validator)。
        在参数化修改后核验：
        1. 目标尺寸是否准确逼近目标值；
        2. 所有非目标尺寸是否保持与基线一致，绝对漂移不得超过 tolerance_mm。
        """
        drift_violations: List[Dict[str, Any]] = []

        # 1. 校验目标修改
        for tgt_name, expected_val in target_modifications.items():
            cur_val = current_dims.get(tgt_name)
            if cur_val is None:
                drift_violations.append({
                    "dimension": tgt_name,
                    "type": "TARGET_MISSING",
                    "expected": expected_val,
                    "actual": None,
                    "drift_mm": 0.0,
                })
            elif abs(cur_val - expected_val) > tolerance_mm:
                drift_violations.append({
                    "dimension": tgt_name,
                    "type": "TARGET_DEVIATION",
                    "expected": expected_val,
                    "actual": cur_val,
                    "drift_mm": abs(cur_val - expected_val),
                })

        # 2. 校验非目标尺寸是否发生意外位移
        target_keys = set(target_modifications.keys())
        for dim_name, base_val in baseline_dims.items():
            if dim_name in target_keys:
                continue
            cur_val = current_dims.get(dim_name)
            if cur_val is not None:
                drift = abs(cur_val - base_val)
                if drift > tolerance_mm:
                    drift_violations.append({
                        "dimension": dim_name,
                        "type": "UNINTENDED_DRIFT",
                        "baseline": base_val,
                        "actual": cur_val,
                        "drift_mm": drift,
                    })

        passed = len(drift_violations) == 0
        return passed, drift_violations
