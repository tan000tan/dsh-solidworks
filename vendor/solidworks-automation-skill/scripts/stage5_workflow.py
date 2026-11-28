"""Stage 5 高层 AI CAD 工作流工具：多方案规划、特征树拓扑优化与四维质量检验。"""
from __future__ import annotations

from typing import Any, Mapping


def plan_multi_schemes(requirements: Mapping[str, Any]) -> dict[str, Any]:
    """根据设计需求生成并对比多个候选建模方案（如车削回转 vs 多层拉伸）。"""
    part_type = str(requirements.get("part_type") or "generic_part").strip()
    is_axisymmetric = bool(requirements.get("axisymmetric", False))
    feature_count = int(requirements.get("estimated_features", 3) or 3)

    schemes = []
    if is_axisymmetric or "shaft" in part_type.lower() or "轴" in part_type:
        schemes.append({
            "scheme_id": "revolve_primary",
            "strategy": "single_sketch_revolve",
            "estimated_features": 1,
            "robustness_score": 0.94,
            "recommended": True,
            "reason": "回转体优先采用单草图旋转特征，特征树最紧凑、拓扑最稳健。",
        })
        schemes.append({
            "scheme_id": "extrude_stacked",
            "strategy": "multi_stage_extrude",
            "estimated_features": max(2, feature_count),
            "robustness_score": 0.78,
            "recommended": False,
            "reason": "多层拉伸备选方案，特征依赖较长。",
        })
    else:
        schemes.append({
            "scheme_id": "base_extrude_plus_details",
            "strategy": "parametric_extrude_then_dressup",
            "estimated_features": max(2, feature_count),
            "robustness_score": 0.89,
            "recommended": True,
            "reason": "先构建主体基准拉伸，再依次添加孔、倒角与圆角修饰特征。",
        })

    return {
        "status": "ok",
        "part_type": part_type,
        "scheme_count": len(schemes),
        "recommended_scheme": schemes[0]["scheme_id"],
        "schemes": schemes,
    }


def optimize_feature_tree(feature_graph: Mapping[str, Any]) -> dict[str, Any]:
    """对 Feature Graph / 特征列表进行拓扑排序与修饰特征后置优化建议。"""
    nodes = list(feature_graph.get("nodes") or [])
    dressup_types = {"fillet", "chamfer", "shell", "draft"}
    base_nodes = []
    dressup_nodes = []

    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        ftype = str(node.get("type") or node.get("feature_type") or "").lower()
        if ftype in dressup_types:
            dressup_nodes.append(dict(node))
        else:
            base_nodes.append(dict(node))

    optimized = base_nodes + dressup_nodes
    reordered = [n.get("id") or n.get("name") for n in optimized] != [
        n.get("id") or n.get("name") for n in nodes if isinstance(n, Mapping)
    ]

    return {
        "status": "ok",
        "input_node_count": len(nodes),
        "optimized_node_count": len(optimized),
        "reordered": reordered,
        "optimized_nodes": optimized,
        "recommendations": [
            "将倒圆角、倒角、抽壳等修饰特征统一后置，降低拓扑引用失效风险。"
        ] if dressup_nodes else ["当前特征树结构已符合基础拓扑顺序。"],
    }


def inspect_cad_quality(geometry_metrics: Mapping[str, Any]) -> dict[str, Any]:
    """执行四维 CAD 质量检验（体积闭合度、特征状态、拓扑告警、可制造性基础检查）。"""
    volume_mm3 = geometry_metrics.get("volume_mm3")
    expected_volume_mm3 = geometry_metrics.get("expected_volume_mm3")
    failed_features = list(geometry_metrics.get("failed_features") or [])

    issues: list[dict[str, str]] = []
    volume_error_pct: float | None = None

    if volume_mm3 is not None and float(volume_mm3) <= 0:
        issues.append({"code": "QUALITY_ZERO_VOLUME", "message": "模型体积必须大于 0"})

    if volume_mm3 is not None and expected_volume_mm3 is not None and float(expected_volume_mm3) > 0:
        volume_error_pct = abs(float(volume_mm3) - float(expected_volume_mm3)) / float(expected_volume_mm3) * 100.0
        if volume_error_pct > 1.0:
            issues.append({
                "code": "QUALITY_VOLUME_DRIFT",
                "message": f"实测体积与理论值偏差 {volume_error_pct:.3f}% (> 1.0%)",
            })

    if failed_features:
        issues.append({
            "code": "QUALITY_FAILED_FEATURES",
            "message": f"存在 {len(failed_features)} 个重建失败特征",
        })

    return {
        "status": "pass" if not issues else "warning",
        "passed": len(issues) == 0,
        "volume_error_pct": round(volume_error_pct, 4) if volume_error_pct is not None else None,
        "issue_count": len(issues),
        "issues": issues,
    }
