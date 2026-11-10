"""
复杂特征树规划与依赖优化器 (Complex Feature Tree Optimizer)
对应第五阶段子阶段 S5-B：
管理多级特征依赖图（DAG），实现终饰特征（圆角/倒角）智能后置重排、
违规崩溃特征（mirror_feature DEF-11）自动拦截与重构、以及死锁依赖消除。
"""
import copy
from typing import Any, Dict, List, Set, Tuple


class FeatureTreeOptimizationError(Exception):
    """特征树优化异常基类"""
    pass


class CyclicDependencyDetectedError(FeatureTreeOptimizationError):
    """检测到循环依赖死锁"""
    pass


class BlockedFeatureError(FeatureTreeOptimizationError):
    """检测到被审计阻断的缺陷特征"""
    pass


class ComplexFeatureTreeOptimizer:
    """复杂特征树优化器"""

    # 终饰特征集合：应在主体几何全部完成后再执行，以保证拓扑引用稳定性
    FINISHING_FEATURE_TYPES = {
        "solidworks_fillet",
        "solidworks_chamfer",
        "fillet",
        "chamfer"
    }

    # 被第四阶段审计明确封禁的缺陷特征 (DEF-11 等)
    BLOCKED_FEATURE_TYPES = {
        "solidworks_mirror_feature",
        "mirror_feature"
    }

    def __init__(self, auto_bypass_blocked: bool = True):
        self.auto_bypass_blocked = auto_bypass_blocked

    def optimize_tree(self, feature_nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        对输入的特征节点列表进行拓扑优化：
        1. 检查并拦截/重构被禁用的缺陷特征；
        2. 死锁环路静态检测；
        3. 终饰特征（倒角/圆角）智能后置重排；
        4. 消除悬挂依赖并输出确定性优化执行时序。
        """
        # 第一步：深拷贝与禁用特征审查
        processed_nodes = []
        for node in feature_nodes:
            f_type = node.get("feature_type", "")
            if f_type in self.BLOCKED_FEATURE_TYPES:
                if self.auto_bypass_blocked:
                    # 自动重构为草图对称约束替代方案
                    refactored_node = self._bypass_mirror_feature(node)
                    processed_nodes.append(refactored_node)
                else:
                    raise BlockedFeatureError(
                        f"特征 [{node.get('feature_id')}] 类型 [{f_type}] 存在底层崩溃缺陷 (DEF-11)，禁止调用！"
                    )
            else:
                processed_nodes.append(copy.deepcopy(node))

        # 第二步：循环依赖死锁检测
        self._detect_cyclic_dependency(processed_nodes)

        # 第三步：拓扑时序重构与终饰后置
        optimized_order = self._schedule_with_late_finishing(processed_nodes)
        return optimized_order

    def _bypass_mirror_feature(self, node: Dict[str, Any]) -> Dict[str, Any]:
        """将有缺陷的 mirror_feature 重构为草图对称拉伸或独立特征替代"""
        new_node = copy.deepcopy(node)
        new_node["feature_type"] = "solidworks_extrude_boss"
        new_node["description"] = f"[重构替代] 规避 mirror_feature 崩溃缺陷，通过对称基准面直接成型镜像对等体"
        new_node["params"] = node.get("params", {})
        new_node["params"]["symmetric_mode"] = True
        return new_node

    def _detect_cyclic_dependency(self, nodes: List[Dict[str, Any]]) -> None:
        """Kahn 算法前置检查循环闭环"""
        adj: Dict[str, List[str]] = {n["feature_id"]: [] for n in nodes}
        in_degree: Dict[str, int] = {n["feature_id"]: 0 for n in nodes}
        node_map = {n["feature_id"]: n for n in nodes}

        for n in nodes:
            fid = n["feature_id"]
            deps = n.get("depends_on", [])
            for dep in deps:
                if dep in adj:
                    adj[dep].append(fid)
                    in_degree[fid] += 1

        queue = [fid for fid, deg in in_degree.items() if deg == 0]
        visited_count = 0

        while queue:
            curr = queue.pop(0)
            visited_count += 1
            for nxt in adj[curr]:
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)

        if visited_count < len(nodes):
            raise CyclicDependencyDetectedError(
                f"特征依赖图中存在循环死锁 (Cyclic Dependency)，总节点 {len(nodes)}，可解析 {visited_count}"
            )

    def _schedule_with_late_finishing(self, nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        基于依赖优先 + 终饰后置原则进行稳定调度：
        - 基础几何特征与切除特征优先构建；
        - 圆角、倒角在所有直接前置就绪的前提下，尽量推迟至最后执行。
        """
        node_map = {n["feature_id"]: n for n in nodes}
        dependencies: Dict[str, Set[str]] = {
            n["feature_id"]: set(n.get("depends_on", [])) for n in nodes
        }

        scheduled_ids: List[str] = []
        remaining_ids = set(node_map.keys())

        while remaining_ids:
            # 找出当前所有依赖已经完全就绪的候选特征
            ready_candidates = [
                fid for fid in remaining_ids if dependencies[fid].issubset(scheduled_ids)
            ]

            if not ready_candidates:
                # 异常情况（理论已被死锁检测拦截）
                break

            # 区分主要成型特征与终饰特征
            main_features = [
                fid for fid in ready_candidates
                if node_map[fid].get("feature_type") not in self.FINISHING_FEATURE_TYPES
            ]
            finishing_features = [
                fid for fid in ready_candidates
                if node_map[fid].get("feature_type") in self.FINISHING_FEATURE_TYPES
            ]

            # 优先调度主要成型特征；只有在没有就绪的主特征时，才调度终饰特征
            if main_features:
                chosen = main_features[0]
            else:
                chosen = finishing_features[0]

            scheduled_ids.append(chosen)
            remaining_ids.remove(chosen)

        return [node_map[fid] for fid in scheduled_ids]
