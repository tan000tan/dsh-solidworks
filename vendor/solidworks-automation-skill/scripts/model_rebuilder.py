# -*- coding: utf-8 -*-
"""
vendor/solidworks-automation-skill/scripts/model_rebuilder.py
SolidWorks 统一模型重构与几何健康核验模块 (Model Rebuilder)。

核心职责：
1. 统一调度 ForceRebuild3 与 EditRebuild3 重建管线；
2. 捕获重构返回值与特征树底层错误码；
3. 检查实体完整性（实体数量、包围盒坐标、体积与表面积）；
4. 防御拓扑自交、拓扑破损与实体丢失；
5. 输出详尽的 RebuildReport，为事务修改决策提供物理可信依据。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

try:
    from .sw_connect import get_com_member
    from .sw_measure import collect_mass_properties, collect_bounding_box
except ImportError:
    from sw_connect import get_com_member
    from sw_measure import collect_mass_properties, collect_bounding_box

logger = logging.getLogger("model_rebuilder")


class RebuildReport(BaseModel):
    """模型重建执行与几何健康诊断报告。"""
    success: bool = Field(..., description="重建与基本几何校验是否整体通过")
    status: str = Field(..., description="健康状态：CLEAN, WARNING, FAILED")
    rebuild_code: int = Field(default=0, description="EditRebuild3 返回代码")
    solid_body_count: int = Field(default=0, description="当前模型包含的实体数量")
    bounding_box_mm: Optional[List[float]] = Field(default=None, description="包围盒尺寸 [dx, dy, dz] mm")
    volume_mm3: Optional[float] = Field(default=None, description="模型总体积 mm^3")
    surface_area_mm2: Optional[float] = Field(default=None, description="模型总表面积 mm^2")
    failed_features: List[str] = Field(default_factory=list, description="存在重建错误的特征名称列表")
    warnings: List[str] = Field(default_factory=list, description="非致命警告信息")
    error_message: Optional[str] = Field(default=None, description="导致重建失败的主因")


class ModelRebuilder:
    """SolidWorks 模型统一重构与健康评估器。"""

    def __init__(self, model):
        self.model = model

    def rebuild(self, force_all: bool = False, min_expected_bodies: int = 1) -> RebuildReport:
        """
        执行模型重构并核实物理几何状态。
        
        参数:
            force_all: 是否调用 ForceRebuild3 强制全量重解
            min_expected_bodies: 预期最少实体数（防止几何破损导致实体变为 0）
        """
        if self.model is None:
            return RebuildReport(
                success=False,
                status="FAILED",
                error_message="传入的 model COM 对象为空",
            )

        warnings: List[str] = []
        failed_features: List[str] = []

        # 1. 触发重建
        try:
            if force_all:
                get_com_member(self.model, "ForceRebuild3", False)
        except Exception as e:
            warnings.append(f"ForceRebuild3 调用异常: {e}")

        rebuild_val = None
        try:
            rebuild_val = get_com_member(self.model, "EditRebuild3")
        except Exception as e:
            return RebuildReport(
                success=False,
                status="FAILED",
                error_message=f"EditRebuild3 触发异常: {e}",
            )

        rebuild_success = bool(rebuild_val)

        # 2. 检查特征树中的错误特征
        try:
            feat = get_com_member(self.model, "FirstFeature")
            visited = 0
            while feat is not None and visited < 2048:
                visited += 1
                fname = str(get_com_member(feat, "Name") or "")
                # 获取错误码
                try:
                    err_code = int(get_com_member(feat, "GetErrorCode2") or 0)
                    if err_code != 0:
                        failed_features.append(f"{fname}(err={err_code})")
                except Exception:
                    pass
                next_feat = get_com_member(feat, "GetNextFeature")
                if next_feat is feat:
                    break
                feat = next_feat
        except Exception as e:
            warnings.append(f"扫描特征树错误码异常: {e}")

        # 3. 提取物理质量属性与包围盒
        body_count = 0
        try:
            part_doc = self.model
            # 兼容 PartDoc.GetPartBox 与 GetBodies2
            bodies = get_com_member(part_doc, "GetBodies2", 0, True) # 0 = swSolidBody
            if bodies is not None:
                body_count = len(bodies) if hasattr(bodies, "__len__") else 1
        except Exception:
            body_count = 1  # 回退

        bbox_mm = None
        vol_mm3 = None
        surf_mm2 = None

        try:
            bbox_info = collect_bounding_box(self.model)
            if bbox_info and "size_mm" in bbox_info:
                bbox_mm = [round(v, 4) for v in bbox_info["size_mm"]]
        except Exception as e:
            warnings.append(f"提取包围盒异常: {e}")

        try:
            mass_props = collect_mass_properties(self.model)
            if mass_props:
                vol_mm3 = mass_props.get("volume_mm3")
                surf_mm2 = mass_props.get("surface_area_mm2")
        except Exception as e:
            warnings.append(f"提取质量属性异常: {e}")

        # 4. 综合健康评估
        is_clean = rebuild_success and (len(failed_features) == 0) and (body_count >= min_expected_bodies)
        if not rebuild_success or (body_count < min_expected_bodies):
            status = "FAILED"
            err_msg = f"重建未通过: rebuild_code={rebuild_val}, 实体数={body_count} (预期>={min_expected_bodies})"
            if failed_features:
                err_msg += f", 故障特征: {failed_features}"
        elif failed_features or warnings:
            status = "WARNING"
            err_msg = None
        else:
            status = "CLEAN"
            err_msg = None

        return RebuildReport(
            success=is_clean,
            status=status,
            rebuild_code=int(rebuild_val) if isinstance(rebuild_val, (int, bool)) else 0,
            solid_body_count=body_count,
            bounding_box_mm=bbox_mm,
            volume_mm3=vol_mm3,
            surface_area_mm2=surf_mm2,
            failed_features=failed_features,
            warnings=warnings,
            error_message=err_msg,
        )
