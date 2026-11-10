# -*- coding: utf-8 -*-
"""
vendor/solidworks-automation-skill/scripts/design_intent.py
CAD 结构化设计意图与反例边界约束系统 (Design Intent & Semantic Validator)

核心职责：
1. 封装高阶机械设计意图 (DesignIntent)，屏蔽底层 CAD API 细节；
2. 几何与工程可行性反向校验 (Counter-example Rejection)：
   - 越界孔位拦截 (Out of bounds)
   - 非法或非物理尺寸拦截 (Non-positive / NaN / Inf)
   - 壁厚不足与结构干涉检查 (Insufficient wall thickness)
   - 悬空特征与缺失基准引用拦截 (Dangling / Unanchored features)
3. 为 CADTaskPlanner 提供确定性的意图验证凭据。
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


class IntentValidationStatus(str, Enum):
    VALID = "VALID"
    INVALID_DIMENSION = "INVALID_DIMENSION"
    OUT_OF_BOUNDS = "OUT_OF_BOUNDS"
    INSUFFICIENT_WALL = "INSUFFICIENT_WALL"
    MISSING_REFERENCE = "MISSING_REFERENCE"
    GEOMETRY_CONFLICT = "GEOMETRY_CONFLICT"


class IntentValidationResult(BaseModel):
    """设计意图校验结果容器。"""
    is_valid: bool = Field(..., description="意图是否通过全部工程几何校验")
    status: IntentValidationStatus = Field(default=IntentValidationStatus.VALID)
    errors: List[str] = Field(default_factory=list, description="致命错误清单（触发反例拦截）")
    warnings: List[str] = Field(default_factory=list, description="工程优化建议")


class BasePlateIntent(BaseModel):
    """基底支撑板/底座设计意图。"""
    length_mm: float = Field(..., description="底板长度 (X方向, mm)")
    width_mm: float = Field(..., description="底板宽度 (Z方向, mm)")
    thickness_mm: float = Field(..., description="底板厚度 (Y方向, mm)")
    plane: str = Field(default="Top Plane", description="基准参考平面")
    origin_corner: bool = Field(default=True, description="是否以(0,0)为对角起点，否则以中心为原点")


class HoleIntent(BaseModel):
    """单个通孔/盲孔设计意图。"""
    hole_id: str = Field(..., description="孔唯一标识符，例如 center_bore, mount_hole_1")
    diameter_mm: float = Field(..., description="孔直径 (mm)")
    center_x_mm: float = Field(default=0.0, description="孔中心 X 坐标 (mm)")
    center_y_mm: float = Field(default=0.0, description="孔中心 Y 坐标 (草图局部坐标, mm)")
    depth_mm: Optional[float] = Field(default=None, description="盲孔深度 (mm)，None 表示完全贯穿")
    is_through: bool = Field(default=True, description="是否为贯穿通孔")


class MountingPatternIntent(BaseModel):
    """阵列紧固孔设计意图（例如矩形底板四角安装孔或双对称孔）。"""
    pattern_id: str = Field(default="mount_pattern", description="阵列标识符")
    hole_diameter_mm: float = Field(..., description="紧固孔直径 (mm)")
    margin_x_mm: float = Field(..., description="距 X 向边缘距离 (mm)")
    margin_y_mm: float = Field(..., description="距 Y 向边缘距离 (mm)")
    count_type: str = Field(default="four_corners", description="阵列类型: four_corners(四角孔) 或 dual_symmetric(双孔)")
    pitch_x_mm: Optional[float] = Field(default=None, description="孔间距 X (mm)")


class BossFeatureIntent(BaseModel):
    """凸台/垂直支撑板次级特征意图。"""
    boss_id: str = Field(..., description="凸台标识符")
    shape: str = Field(default="rectangle", description="几何形状: rectangle 或 circle")
    width_mm: float = Field(..., description="宽度或外径 (mm)")
    height_mm: float = Field(..., description="高度 (mm)")
    thickness_mm: float = Field(..., description="拉伸厚度 (mm)")
    offset_x_mm: float = Field(default=0.0, description="安装偏移 X (mm)")
    offset_y_mm: float = Field(default=0.0, description="安装偏移 Y (mm)")
    plane: str = Field(default="Front Plane", description="绘制平面")


class DesignIntent(BaseModel):
    """
    统一零件级设计意图模型。
    集中表达自然语言或上层 Agent 的结构化几何诉求。
    """
    part_name: str = Field(default="MechanicalPart", description="零件工程代号")
    base: Optional[BasePlateIntent] = Field(default=None, description="主基底几何")
    holes: List[HoleIntent] = Field(default_factory=list, description="离散孔特征")
    pattern: Optional[MountingPatternIntent] = Field(default=None, description="紧固孔阵列")
    bosses: List[BossFeatureIntent] = Field(default_factory=list, description="附加凸台或立柱")
    parameters: Dict[str, float] = Field(default_factory=dict, description="显式提取的尺寸驱动参数")

    def validate_intent(self) -> IntentValidationResult:
        """
        核心反向工程审查器：
        在未触碰任何底层 COM 或文件系统之前，静态拦截全部非法几何反例。
        """
        errors: List[str] = []
        warnings: List[str] = []
        status = IntentValidationStatus.VALID

        # 1. 基底存在性检查 (缺少基底的悬空特征拦截)
        if self.base is None:
            return IntentValidationResult(
                is_valid=False,
                status=IntentValidationStatus.MISSING_REFERENCE,
                errors=["[MISSING_REFERENCE] 零件缺少主基底特征 (base)，无法在其上构建从属特征。"],
            )

        # 2. 物理正定性检查 (非物理尺寸拦截)
        base = self.base
        if base.length_mm <= 0 or base.width_mm <= 0 or base.thickness_mm <= 0:
            return IntentValidationResult(
                is_valid=False,
                status=IntentValidationStatus.INVALID_DIMENSION,
                errors=[f"[INVALID_DIMENSION] 基底尺寸必须大于0: 长={base.length_mm}, 宽={base.width_mm}, 厚={base.thickness_mm}"],
            )

        if math.isnan(base.length_mm) or math.isinf(base.length_mm):
            return IntentValidationResult(
                is_valid=False,
                status=IntentValidationStatus.INVALID_DIMENSION,
                errors=["[INVALID_DIMENSION] 基底尺寸包含非数值 (NaN 或 Inf)。"],
            )

        # 基底物理坐标包围域
        if base.origin_corner:
            x_min, x_max = 0.0, base.length_mm
            y_min, y_max = 0.0, base.width_mm
        else:
            x_min, x_max = -base.length_mm / 2.0, base.length_mm / 2.0
            y_min, y_max = -base.width_mm / 2.0, base.width_mm / 2.0

        # 3. 离散孔位物理越界与穿透有效性审查
        for h in self.holes:
            if h.diameter_mm <= 0:
                errors.append(f"[INVALID_DIMENSION] 孔 [{h.hole_id}] 直径必须大于0 (当前: {h.diameter_mm}mm)")
                status = IntentValidationStatus.INVALID_DIMENSION
                continue

            r = h.diameter_mm / 2.0
            # 边界容差 (最小保留 1.0mm 结构壁厚)
            min_wall = 1.0

            # 检查孔是否溢出底板物理边界
            if (h.center_x_mm - r < x_min) or (h.center_x_mm + r > x_max) or \
               (h.center_y_mm - r < y_min) or (h.center_y_mm + r > y_max):
                errors.append(
                    f"[OUT_OF_BOUNDS] 孔 [{h.hole_id}] 物理越界: 中心=({h.center_x_mm}, {h.center_y_mm})mm, "
                    f"直径={h.diameter_mm}mm 超出底板包围域 X:[{x_min}, {x_max}], Y:[{y_min}, {y_max}]"
                )
                status = IntentValidationStatus.OUT_OF_BOUNDS

            elif (h.center_x_mm - r - min_wall < x_min) or (h.center_x_mm + r + min_wall > x_max) or \
                 (h.center_y_mm - r - min_wall < y_min) or (h.center_y_mm + r + min_wall > y_max):
                warnings.append(f"[LOW_WALL_THICKNESS] 孔 [{h.hole_id}] 距边缘壁厚不足 {min_wall}mm，可能引发加工破损")

            # 盲孔深度校验
            if not h.is_through and h.depth_mm is not None:
                if h.depth_mm <= 0:
                    errors.append(f"[INVALID_DIMENSION] 盲孔 [{h.hole_id}] 深度必须大于0")
                    status = IntentValidationStatus.INVALID_DIMENSION
                elif h.depth_mm > base.thickness_mm:
                    warnings.append(f"[DEPTH_EXCEEDED] 盲孔 [{h.hole_id}] 深度 {h.depth_mm}mm 大于底板厚度 {base.thickness_mm}mm，将退化为通孔")

        # 4. 阵列紧固孔约束审查
        if self.pattern is not None:
            pat = self.pattern
            if pat.hole_diameter_mm <= 0 or pat.margin_x_mm <= 0 or pat.margin_y_mm <= 0:
                errors.append("[INVALID_DIMENSION] 阵列孔直径与边缘边距必须大于0")
                status = IntentValidationStatus.INVALID_DIMENSION
            else:
                pr = pat.hole_diameter_mm / 2.0
                if pat.margin_x_mm < pr or pat.margin_y_mm < pr:
                    errors.append(
                        f"[OUT_OF_BOUNDS] 阵列孔边距过小: 边距=({pat.margin_x_mm}, {pat.margin_y_mm})mm "
                        f"小于孔半径 {pr}mm，导致孔切断板边"
                    )
                    status = IntentValidationStatus.OUT_OF_BOUNDS

                if (2.0 * pat.margin_x_mm >= base.length_mm) or (2.0 * pat.margin_y_mm >= base.width_mm):
                    errors.append(
                        f"[GEOMETRY_CONFLICT] 阵列孔边距之和超出底板总尺寸: "
                        f"2*margin_x={2*pat.margin_x_mm}mm >= L={base.length_mm}mm 或 "
                        f"2*margin_y={2*pat.margin_y_mm}mm >= W={base.width_mm}mm"
                    )
                    status = IntentValidationStatus.GEOMETRY_CONFLICT

        # 5. 附加凸台结构审查
        for b in self.bosses:
            if b.width_mm <= 0 or b.height_mm <= 0 or b.thickness_mm <= 0:
                errors.append(f"[INVALID_DIMENSION] 凸台 [{b.boss_id}] 尺寸必须为正数")
                status = IntentValidationStatus.INVALID_DIMENSION

        is_valid = len(errors) == 0
        return IntentValidationResult(
            is_valid=is_valid,
            status=status if not is_valid else IntentValidationStatus.VALID,
            errors=errors,
            warnings=warnings,
        )
