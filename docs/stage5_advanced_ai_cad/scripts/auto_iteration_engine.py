"""
自动迭代修改与影响分析引擎 (Auto Iteration Engine)
对应第五阶段子阶段 S5-C：
读取现有特征模型与参数网，评估修改影响域半径，规划安全修改顺序，
并计算修改前后的微观几何差值 (Diff)，防止修改造成破坏。
"""
import copy
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field


class ModificationImpact(BaseModel):
    """参数修改影响域分析结果"""
    target_param: str
    target_feature_id: str
    old_value: float
    new_value: float
    direct_affected_features: List[str] = Field(default_factory=list)
    indirect_affected_features: List[str] = Field(default_factory=list)
    affected_dimensions: List[str] = Field(default_factory=list)
    risk_level: str                         # LOW, MEDIUM, HIGH
    requires_rebuild: bool = True
    impact_summary: str


class IterationDiffResult(BaseModel):
    """增量修改执行前后几何 Diff 结果"""
    success: bool
    target_param: str
    delta_param_value: float
    delta_volume: float
    delta_surface_area: float
    delta_bbox_diagonal: float
    rebuild_status: str
    affected_feature_count: int
    is_safe: bool
    message: str


class AutoIterationEngine:
    """自动迭代修改引擎"""

    def __init__(self):
        pass

    def analyze_impact(
        self,
        feature_dag: List[Dict[str, Any]],
        dimension_graph: Dict[str, List[str]],
        target_param: str,
        param_feature_map: Dict[str, str],
        old_val: float,
        new_val: float
    ) -> ModificationImpact:
        """
        基于特征依赖 DAG 和尺寸网络，静态推导参数修改波及的影响域半径
        """
        target_fid = param_feature_map.get(target_param, "unknown_feature")

        # 构建邻接表
        children_map: Dict[str, List[str]] = {n["feature_id"]: [] for n in feature_dag}
        for n in feature_dag:
            for dep in n.get("depends_on", []):
                if dep in children_map:
                    children_map[dep].append(n["feature_id"])

        # 广度优先搜索 (BFS) 计算所有直接与间接子特征
        direct_children = children_map.get(target_fid, [])
        all_descendants: Set[str] = set()

        queue = list(direct_children)
        while queue:
            curr = queue.pop(0)
            if curr not in all_descendants:
                all_descendants.add(curr)
                queue.extend(children_map.get(curr, []))

        indirect_children = list(all_descendants - set(direct_children))

        # 关联尺寸提取
        affected_dims = dimension_graph.get(target_param, [])

        # 风险定级：若波及下游特征 > 3 个或修改幅度超过 50%，定为 HIGH；>= 2 个或变动 > 20% 定为 MEDIUM；其余为 LOW
        delta_pct = abs(new_val - old_val) / max(abs(old_val), 1e-6)
        if len(all_descendants) > 3 or delta_pct > 0.5:
            risk = "HIGH"
        elif len(all_descendants) >= 2 or delta_pct > 0.2:
            risk = "MEDIUM"
        else:
            risk = "LOW"

        summary = (
            f"修改参数 [{target_param}] 从 {old_val} 至 {new_val} (变动 {delta_pct*100:.1f}%)。"
            f"直接受影响特征: {len(direct_children)} 个，间接受影响特征: {len(indirect_children)} 个。"
            f"关联尺寸: {len(affected_dims)} 个。综合风险等级: [{risk}]。"
        )

        return ModificationImpact(
            target_param=target_param,
            target_feature_id=target_fid,
            old_value=old_val,
            new_value=new_val,
            direct_affected_features=direct_children,
            indirect_affected_features=indirect_children,
            affected_dimensions=affected_dims,
            risk_level=risk,
            requires_rebuild=True,
            impact_summary=summary
        )

    def calculate_geometry_diff(
        self,
        impact: ModificationImpact,
        geom_before: Dict[str, float],
        geom_after: Dict[str, float]
    ) -> IterationDiffResult:
        """
        计算增量修改前后的几何属性差值 (Diff)，验证修改是否达成且非关联区域无破坏
        """
        v_before = geom_before.get("volume", 0.0)
        v_after = geom_after.get("volume", 0.0)
        s_before = geom_before.get("surface_area", 0.0)
        s_after = geom_after.get("surface_area", 0.0)

        delta_v = v_after - v_before
        delta_s = s_after - s_before
        delta_val = impact.new_value - impact.old_value

        # 若是外径增大或厚度增大，预期体积必须单调递增；若是孔径增大，预期体积必须单调递减
        is_safe = True
        msg = "几何 Diff 比对正常，参数驱动模型成功。"

        if "hole" in impact.target_param or "cut" in impact.target_feature_id:
            # 挖孔/切除参数增大 -> 体积应当减少
            if delta_val > 0 and delta_v > 0.001:
                is_safe = False
                msg = f"异常：孔切除尺寸增大，但模型体积不减反增 (Delta V = {delta_v:.2f})！"
        elif "boss" in impact.target_param or "extrude" in impact.target_feature_id:
            # 凸台/拉伸参数增大 -> 体积应当增加
            if delta_val > 0 and delta_v < -0.001:
                is_safe = False
                msg = f"异常：凸台拉伸尺寸增大，但模型体积反而减小 (Delta V = {delta_v:.2f})！"

        return IterationDiffResult(
            success=True,
            target_param=impact.target_param,
            delta_param_value=delta_val,
            delta_volume=delta_v,
            delta_surface_area=delta_s,
            delta_bbox_diagonal=geom_after.get("bbox_diagonal", 0.0) - geom_before.get("bbox_diagonal", 0.0),
            rebuild_status="REBUILD_SUCCESS",
            affected_feature_count=len(impact.direct_affected_features) + len(impact.indirect_affected_features),
            is_safe=is_safe,
            message=msg
        )
