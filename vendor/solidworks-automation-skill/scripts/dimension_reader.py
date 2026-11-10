# -*- coding: utf-8 -*-
"""
vendor/solidworks-automation-skill/scripts/dimension_reader.py
SolidWorks 模型尺寸参数全景提取与读取器 (Dimension Reader)。

核心职责：
1. 递归扫描当前或指定文档的特征树及其子特征；
2. 提取草图尺寸（DisplayDimension）与特征拉伸/切除深度参数（Parameter）；
3. 准确识别尺寸所属文档、特征上下文与从动/驱动状态；
4. 构建结构化 DimensionModelIR 返回，保证数据来源可追溯。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

try:
    from .sw_connect import get_com_member
    from .dimension_ir import DimensionIRNode, DimensionModelIR, DimensionType
except ImportError:
    from sw_connect import get_com_member
    from dimension_ir import DimensionIRNode, DimensionModelIR, DimensionType

logger = logging.getLogger("dimension_reader")


def _iter_chain(start_obj, next_method: str = "GetNextFeature"):
    """安全遍历 COM 链表，防御循环引用死锁。"""
    curr = start_obj
    count = 0
    while curr is not None and count < 2048:
        yield curr
        count += 1
        try:
            curr = get_com_member(curr, next_method)
        except Exception:
            break


def walk_all_features(model) -> List[Any]:
    """递归遍历模型所有顶层特征及其子特征（如拉伸实体下的底层草图）。"""
    features: List[Any] = []
    seen = set()

    def _visit(feat):
        if feat is None:
            return
        name = str(get_com_member(feat, "Name") or "")
        ftype = str(get_com_member(feat, "GetTypeName2") or "")
        key = (name, ftype)
        if key not in seen:
            seen.add(key)
            features.append(feat)

        # 深入遍历子特征（例如 Extrusion 下的 ProfileFeature）
        try:
            sub = get_com_member(feat, "GetFirstSubFeature")
        except Exception:
            sub = None
        for child in _iter_chain(sub, "GetNextSubFeature"):
            _visit(child)

    top_feature = get_com_member(model, "FirstFeature")
    for feat in _iter_chain(top_feature, "GetNextFeature"):
        _visit(feat)

    return features


def infer_dimension_type(feature_type: str, dim_name: str) -> DimensionType:
    """根据特征类型与尺寸名称推断几何语义类型。"""
    ft_lower = (feature_type or "").lower()
    name_lower = (dim_name or "").lower()

    if "profile" in ft_lower or "sketch" in ft_lower or "草图" in ft_lower:
        if "dia" in name_lower or "rad" in name_lower:
            return DimensionType.SKETCH_DIAMETER
        return DimensionType.SKETCH_LINEAR
    elif "extru" in ft_lower or "拉伸" in ft_lower or "boss" in ft_lower:
        return DimensionType.EXTRUSION_DEPTH
    elif "cut" in ft_lower or "ice" in ft_lower or "切除" in ft_lower:
        return DimensionType.CUT_DEPTH
    elif "revolv" in ft_lower or "旋转" in ft_lower:
        return DimensionType.REVOLVE_ANGLE
    elif "fillet" in ft_lower or "圆角" in ft_lower:
        return DimensionType.FILLET_RADIUS
    elif "chamfer" in ft_lower or "倒角" in ft_lower:
        return DimensionType.CHAMFER_DISTANCE
    return DimensionType.UNKNOWN


def read_model_dimensions(model) -> DimensionModelIR:
    """
    从打开的 SolidWorks 模型对象中全量提取尺寸拓扑。
    
    参数:
        model: IModelDoc2 COM 对象
        
    返回:
        DimensionModelIR 完整模型尺寸中间表示对象
    """
    if model is None:
        raise ValueError("model 对象不能为空")

    title = str(get_com_member(model, "GetTitle") or "Untitled")
    path = str(get_com_member(model, "GetPathName") or "")
    
    model_ir = DimensionModelIR(model_title=title, model_path=path)
    all_features = walk_all_features(model)

    for feat in all_features:
        feat_name = str(get_com_member(feat, "Name") or "")
        feat_type = str(get_com_member(feat, "GetTypeName2") or "")

        # 1. 尝试从 DisplayDimension 枚举（主要是草图特征和显式标注尺寸）
        try:
            disp_dim = get_com_member(feat, "GetFirstDisplayDimension")
        except Exception:
            disp_dim = None

        while disp_dim is not None:
            try:
                dim = get_com_member(disp_dim, "GetDimension2", 0)
                if dim is None:
                    dim = get_com_member(disp_dim, "GetDimension")
            except Exception:
                dim = None

            if dim is not None:
                # 优先从 COM 权威 FullName (例如 D1@BaseSketch@PartName) 提取规范特征归属
                full_name_raw = str(get_com_member(dim, "FullName") or "")
                if "@" in full_name_raw:
                    parts = full_name_raw.split("@")
                    dname = parts[0]
                    canonical_feat = parts[1]
                    dim_full = f"{dname}@{canonical_feat}"
                else:
                    dname = str(get_com_member(dim, "Name") or "D1")
                    canonical_feat = feat_name
                    dim_full = f"{dname}@{feat_name}"

                if dim_full not in model_ir.dimensions:
                    try:
                        sys_val = float(get_com_member(dim, "SystemValue") or 0.0)
                    except Exception:
                        sys_val = 0.0

                    # SolidWorks swDimensionDrivenState_e: 1 = swDimensionDrivenState_Driven, 2 = swDimensionDrivenState_Driving
                    driven_code = int(get_com_member(dim, "DrivenState") or 0)
                    is_driven = (driven_code == 1)
                    dim_type = infer_dimension_type(feat_type, dim_full)

                    node = DimensionIRNode.create(
                        dimension_name=dim_full,
                        system_value=sys_val,
                        feature_name=canonical_feat,
                        feature_type=feat_type,
                        dim_type=dim_type,
                        is_driven=is_driven,
                        editable=not is_driven,
                        source="sketch" if "Profile" in feat_type or "Sketch" in canonical_feat else "feature",
                    )
                    model_ir.add_dimension(node)

            try:
                disp_dim = get_com_member(feat, "GetNextDisplayDimension", disp_dim)
            except Exception:
                break

        # 2. 尝试从特征默认参数查询（例如拉伸深度的 D1@Boss-Extrude1 / D1@凸台-拉伸1）
        for default_param in ("D1", "D2", "A1"):
            param_key = f"{default_param}@{feat_name}"
            if param_key in model_ir.dimensions:
                continue
            try:
                dim_obj = get_com_member(model, "Parameter", param_key)
                if dim_obj is not None:
                    # 检查参数底层是否指向已注册的草图尺寸别名
                    full_name_raw = str(get_com_member(dim_obj, "FullName") or "")
                    if "@" in full_name_raw:
                        parts = full_name_raw.split("@")
                        canon_key = f"{parts[0]}@{parts[1]}"
                        if canon_key in model_ir.dimensions:
                            continue

                    sys_val = float(get_com_member(dim_obj, "SystemValue") or 0.0)
                    if sys_val > 0.0:
                        dim_type = infer_dimension_type(feat_type, default_param)
                        node = DimensionIRNode.create(
                            dimension_name=param_key,
                            system_value=sys_val,
                            feature_name=feat_name,
                            feature_type=feat_type,
                            dim_type=dim_type,
                            is_driven=False,
                            editable=True,
                            source="feature_parameter",
                        )
                        model_ir.add_dimension(node)
            except Exception:
                pass

    return model_ir
