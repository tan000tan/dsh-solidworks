# -*- coding: utf-8 -*-
"""
vendor/solidworks-automation-skill/scripts/dimension_resolver.py
自然语言目标与模型尺寸参数智能解析与消歧器 (Dimension Resolver)。

核心职责：
1. 解析用户自然语言需求（例如“把底座长度改为 150 mm”、“将中央孔直径改为 25 mm”）；
2. 识别目标零件、目标特征、候选尺寸及目标工程数值；
3. 处理绝对修改（改为 X）与相对修改（增加/缩小 ΔX）；
4. 统一换算为工程标准单位（mm / deg）；
5. 多候选尺寸上下文消歧与安全边界前置核验。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

try:
    from .dimension_ir import DimensionIRNode, DimensionModelIR, DimensionType
except ImportError:
    from dimension_ir import DimensionIRNode, DimensionModelIR, DimensionType


class ResolvedDimensionTarget(BaseModel):
    """消歧并解析完成的尺寸修改操作目标。"""
    dimension_name: str = Field(..., description="SolidWorks 原生尺寸全名，例如 D1@草图1")
    target_value_mm: float = Field(..., description="计算后的目标工程绝对数值（毫米或角度）")
    original_value_mm: float = Field(..., description="修改前的原始工程数值")
    delta_mm: float = Field(default=0.0, description="变化量")
    feature_name: str = Field(default="", description="所属特征名称")
    confidence: float = Field(default=1.0, description="语义匹配置信度 (0.0~1.0)")
    matched_reason: str = Field(default="", description="匹配解析依据")
    unit: str = Field(default="mm", description="单位")


class ResolutionResult(BaseModel):
    """解析流程的完整返回结果。"""
    success: bool = Field(..., description="是否成功完成消歧并获得唯一目标")
    resolved_target: Optional[ResolvedDimensionTarget] = Field(default=None, description="成功解析出的操作目标")
    candidates: List[Dict[str, Any]] = Field(default_factory=list, description="若存在多义性，返回所有候选列表")
    error_message: Optional[str] = Field(default=None, description="未成功解析时的说明")


def parse_numeric_with_unit(text: str) -> Optional[Tuple[float, str]]:
    """从文本中提取数值与单位，支持中英文常见单位。"""
    # 匹配数字后跟单位：例如 150 mm, 25毫米, 0.05m, 10cm, 5
    pattern = r"([+-]?\d+(?:\.\d+)?)\s*(毫米|mm|米|m|厘米|cm|英寸|inch|in|度|deg)?"
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    
    val = float(match.group(1))
    unit_str = (match.group(2) or "mm").lower()

    # 统一转换到工程基准单位 mm / deg
    if unit_str in ("米", "m"):
        return val * 1000.0, "mm"
    elif unit_str in ("厘米", "cm"):
        return val * 10.0, "mm"
    elif unit_str in ("英寸", "inch", "in"):
        return val * 25.4, "mm"
    elif unit_str in ("度", "deg"):
        return val, "deg"
    return val, "mm"


class DimensionResolver:
    """尺寸参数自然语言解析与消歧器。"""

    # 常见特征与尺寸意图同义词映射词典
    FEATURE_KEYWORD_MAP = {
        "base": ["base", "底座", "基体", "板", "plate", "草图1", "sketch1", "拉伸1", "extrude1", "boss1", "boss-extrude1", "凸台-拉伸1"],
        "length": ["长", "length", "width_m", "d1"],
        "width": ["宽", "width", "height_m", "d2"],
        "thickness": ["厚", "thickness", "depth", "高度", "height", "凸台", "boss", "拉伸"],
        "hole": ["孔", "hole", "bore", "切除", "cut", "直孔"],
        "diameter": ["直径", "dia", "直徑", "半径", "radius", "r"],
        "hub": ["安装台", "凸台", "hub", "台", "boss2", "拉伸2", "boss-extrude2", "凸台-拉伸2"],
        "spacing": ["间距", "距离", "pitch", "spacing", "offset"],
    }

    def __init__(self, model_ir: DimensionModelIR):
        self.model_ir = model_ir

    def resolve(
        self,
        query: str,
        target_feature_hint: Optional[str] = None,
        target_dimension_hint: Optional[str] = None,
    ) -> ResolutionResult:
        """
        根据自然语言描述或提示解析并消歧目标尺寸。
        """
        q = query.strip()
        num_unit = parse_numeric_with_unit(q)
        if not num_unit:
            return ResolutionResult(
                success=False,
                error_message=f"未能从输入语句 '{query}' 中提取到合法的数值及单位。",
            )

        extracted_val, extracted_unit = num_unit
        is_relative = bool(re.search(r"(增加|增大|加上|\+|扩大|加高|加长)", q))
        is_negative_relative = bool(re.search(r"(减少|减小|缩小|\-|缩短|变小)", q))

        # 1. 若提供了显式尺寸名提示且直接存在
        if target_dimension_hint:
            direct_node = self.model_ir.get_dimension(target_dimension_hint)
            if direct_node:
                final_val = direct_node.value + extracted_val if is_relative else (
                    direct_node.value - extracted_val if is_negative_relative else extracted_val
                )
                return ResolutionResult(
                    success=True,
                    resolved_target=ResolvedDimensionTarget(
                        dimension_name=direct_node.dimension_name,
                        target_value_mm=final_val,
                        original_value_mm=direct_node.value,
                        delta_mm=final_val - direct_node.value,
                        feature_name=direct_node.feature_name,
                        confidence=1.0,
                        matched_reason="通过显式尺寸名称精确匹配",
                        unit=direct_node.unit,
                    ),
                )

        # 2. 候选池筛选与打分
        driving_dims = self.model_ir.get_driving_dimensions()
        scored_candidates: List[Tuple[float, DimensionIRNode, str]] = []

        q_lower = q.lower()
        for node in driving_dims:
            score = 0.0
            reasons = []

            # 特征提示命中
            if target_feature_hint and target_feature_hint.lower() in node.feature_name.lower():
                score += 0.5
                reasons.append(f"特征提示匹配: {target_feature_hint}")

            # 语义关键词匹配
            for category, keywords in self.FEATURE_KEYWORD_MAP.items():
                kw_in_query = any(kw in q_lower for kw in keywords)
                if kw_in_query:
                    # 检查节点特征名或尺寸名是否匹配该类别
                    node_text = f"{node.feature_name} {node.dimension_name}".lower()
                    if any(kw in node_text for kw in keywords):
                        score += 0.3
                        reasons.append(f"语义类别 [{category}] 关键词匹配")

            # 特征类型吻合度加权
            if ("长" in q_lower or "宽" in q_lower or "length" in q_lower or "width" in q_lower) and node.dimension_type == DimensionType.SKETCH_LINEAR:
                score += 0.2
                reasons.append("平面草图长宽几何类型吻合")
            elif ("厚" in q_lower or "高度" in q_lower or "凸台" in q_lower) and node.dimension_type == DimensionType.EXTRUSION_DEPTH:
                score += 0.3
                reasons.append("实体厚度/高度特征类型契合")
            elif ("孔" in q_lower or "hole" in q_lower or "切除" in q_lower) and node.dimension_type in (
                DimensionType.SKETCH_DIAMETER, DimensionType.CUT_DEPTH
            ):
                score += 0.3
                reasons.append("孔或切除特征几何类型契合")
            elif ("厚" in q_lower or "高度" in q_lower or "深" in q_lower) and node.dimension_type in (
                DimensionType.EXTRUSION_DEPTH, DimensionType.CUT_DEPTH
            ):
                score += 0.2
                reasons.append("拉伸/切除深度类型契合")

            if score > 0.2:
                scored_candidates.append((score, node, "; ".join(reasons)))

        # 排序
        scored_candidates.sort(key=lambda x: x[0], reverse=True)

        if not scored_candidates:
            return ResolutionResult(
                success=False,
                error_message=f"未能在模型中找到与 '{query}' 相关的可编辑驱动尺寸。",
                candidates=[{"name": d.dimension_name, "value": d.value, "feat": d.feature_name} for d in driving_dims],
            )

        top_score, best_node, best_reason = scored_candidates[0]

        # 检查是否有多义歧义（前两名得分完全相同）
        if len(scored_candidates) > 1 and abs(scored_candidates[0][0] - scored_candidates[1][0]) < 1e-4:
            ambiguous_candidates = [
                {
                    "dimension_name": item[1].dimension_name,
                    "feature_name": item[1].feature_name,
                    "current_value_mm": item[1].value,
                    "score": item[0],
                    "matched_reason": item[2],
                }
                for item in scored_candidates[:4]
            ]
            return ResolutionResult(
                success=False,
                error_message="检测到多个置信度相同的候选尺寸，存在歧义，需要明确指定特征名或尺寸名。",
                candidates=ambiguous_candidates,
            )

        # 计算最终目标值
        if is_relative:
            target_val = best_node.value + extracted_val
        elif is_negative_relative:
            target_val = best_node.value - extracted_val
        else:
            target_val = extracted_val

        # 约束校验：尺寸必须 > 0
        if target_val <= 0:
            return ResolutionResult(
                success=False,
                error_message=f"修改后的尺寸计算值为 {target_val} {best_node.unit}，非物理非法值 (必须 > 0)。",
            )

        return ResolutionResult(
            success=True,
            resolved_target=ResolvedDimensionTarget(
                dimension_name=best_node.dimension_name,
                target_value_mm=round(target_val, 4),
                original_value_mm=best_node.value,
                delta_mm=round(target_val - best_node.value, 4),
                feature_name=best_node.feature_name,
                confidence=min(1.0, top_score),
                matched_reason=best_reason,
                unit=best_node.unit,
            ),
        )
