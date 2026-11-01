# -*- coding: utf-8 -*-
"""
SolidWorks 自然语言参数提取器与设计意图编译器 (sw_param_extractor.py)

设计定位：
在非结构化用户需求输入与底层严格的 CAD 参数模型之间建立结构化解析与合规校验层：
1. 参数提取：长/宽/高/直径/半径/壁厚/数量/角度等实体参数解析；
2. 单位换算：标准工程单位换算（mm/cm/m/in 到标准 mm）；
3. 歧义与缺失参数检测：
   - 识别关键缺失尺寸（如要打孔但未给出直径或深度，要做板但未给出厚度）；
   - 自动生成 clarification_questions 明确要求 Agent 向用户反问，严禁凭空瞎猜关键设计尺寸；
4. 几何合理性规则校验：
   - 负数与零尺寸拦截；
   - 壁厚与孔径超限预警；
5. 编译输出：输出结构化的 DesignSpec 字典或 FeatureGraphIR，供下游执行器直接执行。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


# 单位换算系数（统一换算为毫米 mm）
UNIT_SCALES = {
    "mm": 1.0,
    "毫米": 1.0,
    "cm": 10.0,
    "厘米": 10.0,
    "m": 1000.0,
    "米": 1000.0,
    "in": 25.4,
    "inch": 25.4,
    "英寸": 25.4,
}


def normalize_dimension(value: float | str, unit: str = "mm") -> float:
    """将数值按指定单位安全换算为毫米。"""
    try:
        val_float = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"无效的尺寸数值: {value}") from exc

    scale = UNIT_SCALES.get(unit.lower().strip(), 1.0)
    return round(val_float * scale, 6)


class CADParamExtractionResult:
    """参数提取结果容器。"""

    def __init__(self):
        self.parameters: Dict[str, Any] = {}
        self.missing_critical_params: List[str] = []
        self.ambiguities: List[str] = []
        self.clarification_questions: List[str] = []
        self.warnings: List[str] = []
        self.is_executable: bool = False
        self.compiled_spec: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parameters": self.parameters,
            "missing_critical_params": self.missing_critical_params,
            "ambiguities": self.ambiguities,
            "clarification_questions": self.clarification_questions,
            "warnings": self.warnings,
            "is_executable": self.is_executable,
            "compiled_spec": self.compiled_spec,
        }


def extract_cad_parameters(raw_input: Dict[str, Any] | str) -> CADParamExtractionResult:
    """
    从字典输入或文本描述中解析出标准 CAD 参数，并检测关键缺失项与歧义。
    """
    result = CADParamExtractionResult()

    if isinstance(raw_input, str):
        input_text = raw_input
        input_dict = {}
    elif isinstance(raw_input, dict):
        input_dict = dict(raw_input)
        input_text = str(raw_input.get("prompt") or raw_input.get("description") or "")
    else:
        result.warnings.append("输入格式未知，必须为字符串或字典")
        return result

    # 1. 优先从结构化字典提取
    length = input_dict.get("length") or input_dict.get("width") or input_dict.get("x")
    width = input_dict.get("width") or input_dict.get("height") or input_dict.get("y")
    thickness = input_dict.get("thickness") or input_dict.get("depth") or input_dict.get("height") or input_dict.get("z")
    hole_diameter = input_dict.get("hole_diameter") or input_dict.get("diameter") or input_dict.get("hole_d")
    units = str(input_dict.get("units") or "mm").lower().strip()

    # 2. 从自然语言文本正则提取（若字典未直接提供）
    if input_text:
        # 正则匹配长宽高模式，如: "100x60x20mm", "100*60*20 mm"
        dim_match = re.search(r"(\d+(?:\.\d+)?)\s*[*xX×]\s*(\d+(?:\.\d+)?)\s*(?:[*xX×]\s*(\d+(?:\.\d+)?))?\s*([a-zA-Z\u4e00-\u9fa5]+)?", input_text)
        if dim_match:
            d1, d2, d3, unit_str = dim_match.groups()
            if not length:
                length = float(d1)
            if not width:
                width = float(d2)
            if not thickness and d3:
                thickness = float(d3)
            if unit_str and unit_str.lower() in UNIT_SCALES:
                units = unit_str.lower()

        # 正则匹配孔直径，如: "直径20mm", "Φ20", "通孔 10 mm"
        hole_match = re.search(r"(?:直径|径|孔径|[dD]|Φ|φ)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*([a-zA-Z\u4e00-\u9fa5]+)?", input_text)
        if hole_match and not hole_diameter:
            hole_diameter = float(hole_match.group(1))

    # 3. 参数校验与单位归一化
    parsed_params: Dict[str, Any] = {"units": "mm"}
    if length is not None:
        try:
            val = normalize_dimension(length, units)
            if val <= 0:
                result.warnings.append(f"长度参数必须大于 0, 当前为: {val}")
            else:
                parsed_params["length_mm"] = val
        except Exception as e:
            result.warnings.append(f"解析长度数值失败: {e}")

    if width is not None:
        try:
            val = normalize_dimension(width, units)
            if val <= 0:
                result.warnings.append(f"宽度参数必须大于 0, 当前为: {val}")
            else:
                parsed_params["width_mm"] = val
        except Exception as e:
            result.warnings.append(f"解析宽度数值失败: {e}")

    if thickness is not None:
        try:
            val = normalize_dimension(thickness, units)
            if val <= 0:
                result.warnings.append(f"厚度/拉伸深度参数必须大于 0, 当前为: {val}")
            else:
                parsed_params["thickness_mm"] = val
        except Exception as e:
            result.warnings.append(f"解析厚度数值失败: {e}")

    if hole_diameter is not None:
        try:
            val = normalize_dimension(hole_diameter, units)
            if val <= 0:
                result.warnings.append(f"孔直径参数必须大于 0, 当前为: {val}")
            else:
                parsed_params["hole_diameter_mm"] = val
        except Exception as e:
            result.warnings.append(f"解析孔径数值失败: {e}")

    result.parameters = parsed_params

    # 4. 关键设计参数完整性与歧义审查
    has_plate_intent = bool(parsed_params.get("length_mm") or parsed_params.get("width_mm") or "板" in input_text or "矩形" in input_text)
    has_hole_intent = bool(parsed_params.get("hole_diameter_mm") or "孔" in input_text or "通孔" in input_text)

    if has_plate_intent:
        if "length_mm" not in parsed_params:
            result.missing_critical_params.append("length_mm")
            result.clarification_questions.append("请明确零件基础外形的长度 (Length)，单位默认为 mm。")
        if "width_mm" not in parsed_params:
            result.missing_critical_params.append("width_mm")
            result.clarification_questions.append("请明确零件基础外形的宽度 (Width)，单位默认为 mm。")
        if "thickness_mm" not in parsed_params:
            result.missing_critical_params.append("thickness_mm")
            result.clarification_questions.append("请明确零件的基础板厚或拉伸深度 (Thickness)，单位默认为 mm。")

    if has_hole_intent and "hole_diameter_mm" not in parsed_params:
        result.missing_critical_params.append("hole_diameter_mm")
        result.clarification_questions.append("检测到打孔设计意图，但未指定孔径尺寸，请提供所需的孔直径 (Hole Diameter)。")

    # 5. 几何合理性物理检查
    if "length_mm" in parsed_params and "hole_diameter_mm" in parsed_params:
        if parsed_params["hole_diameter_mm"] >= min(parsed_params["length_mm"], parsed_params.get("width_mm", float("inf"))):
            result.ambiguities.append("孔径尺寸大于或等于基准板的长/宽，将导致零件被完全切断破损。")
            result.clarification_questions.append("孔直径超出了基体尺寸边界，请核实孔径是否合理。")

    # 6. 判断可执行性并尝试编译为标准 DesignSpec
    if not result.missing_critical_params and not result.ambiguities:
        if "length_mm" in parsed_params and "width_mm" in parsed_params and "thickness_mm" in parsed_params:
            result.is_executable = True
            holes = []
            if "hole_diameter_mm" in parsed_params:
                # 默认中心打孔
                holes.append({
                    "id": "H1",
                    "type": "through",
                    "diameter": parsed_params["hole_diameter_mm"],
                    "position": [parsed_params["length_mm"] / 2.0, parsed_params["width_mm"] / 2.0],
                })

            result.compiled_spec = {
                "schema_version": "1.0",
                "part_name": input_dict.get("part_name", "parametric_part"),
                "units": "mm",
                "base": {
                    "type": "rect_plate",
                    "width": parsed_params["length_mm"],
                    "height": parsed_params["width_mm"],
                    "thickness": parsed_params["thickness_mm"],
                },
                "holes": holes,
                "verify": {
                    "envelope_mm": [
                        parsed_params["thickness_mm"],
                        parsed_params["width_mm"],
                        parsed_params["length_mm"],
                    ],
                    "solid_body_count": 1,
                },
            }

    return result
