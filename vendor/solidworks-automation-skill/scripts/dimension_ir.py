# -*- coding: utf-8 -*-
"""
vendor/solidworks-automation-skill/scripts/dimension_ir.py
SolidWorks 统一尺寸中间表示 (Dimension IR)。

核心职责：
1. 定义标准尺寸类型与生命周期枚举；
2. 封装单个尺寸元数据 (DimensionIRNode)；
3. 封装模型级尺寸拓扑容器 (DimensionModelIR)；
4. 严格处理 SI 单位（米）与工程显示单位（毫米、角度）之间的换算。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DimensionType(str, Enum):
    """尺寸参数几何与物理语义类型。"""
    SKETCH_LINEAR = "sketch_linear"        # 草图线性距离（长/宽/间距）
    SKETCH_DIAMETER = "sketch_diameter"    # 草图圆直径
    SKETCH_RADIUS = "sketch_radius"        # 草图圆弧半径
    SKETCH_ANGLE = "sketch_angle"          # 草图夹角
    EXTRUSION_DEPTH = "extrusion_depth"    # 凸台拉伸深度
    CUT_DEPTH = "cut_depth"                # 切除拉伸深度
    REVOLVE_ANGLE = "revolve_angle"        # 旋转角度
    FILLET_RADIUS = "fillet_radius"        # 圆角半径
    CHAMFER_DISTANCE = "chamfer_distance"  # 倒角距离
    UNKNOWN = "unknown"                    # 未分类参数


class DimensionRole(str, Enum):
    """尺寸驱动角色。"""
    DRIVING = "DRIVING"      # 驱动尺寸（用户可主动修改并驱动几何变化）
    DRIVEN = "DRIVEN"        # 从动尺寸（由草图几何约束反算，通常只读）
    REFERENCE = "REFERENCE"  # 参考尺寸


class DimensionIRNode(BaseModel):
    """单个尺寸参数在 IR 中的规范表示。"""
    dimension_id: str = Field(..., description="尺寸唯一标识符，例如 dim_d1_sketch1")
    dimension_name: str = Field(..., description="SolidWorks 原生尺寸全名，例如 D1@Sketch1 或 D1@草图1")
    parameter_name: str = Field(default="", description="尺寸内部代号，例如 D1")
    feature_name: str = Field(default="", description="所属特征名称，例如 Sketch1, Boss-Extrude1")
    feature_type: str = Field(default="", description="所属特征的 COM 类型，例如 ProfileFeature, Extrusion")
    dimension_type: DimensionType = Field(default=DimensionType.UNKNOWN, description="几何语义类型")
    
    # 数值与单位 (以工程常用毫米 mm 为基准展示，内部保留 SI 米)
    value: float = Field(..., description="当前尺寸数值（默认工程单位：长度为 mm，角度为 deg）")
    unit: str = Field(default="mm", description="当前尺寸工程单位")
    system_value: float = Field(..., description="SolidWorks COM 内部底层使用的 SI 数值（长度为米 m，角度为弧度 rad）")
    
    # 状态与约束
    editable: bool = Field(default=True, description="是否允许写入修改")
    role: DimensionRole = Field(default=DimensionRole.DRIVING, description="驱动角色")
    is_driven: bool = Field(default=False, description="是否从动")
    dimension_path: str = Field(default="", description="全限定访问路径，例如 Part.SLDPRT/草图1/D1")
    
    # 关联依赖
    dependency_ids: List[str] = Field(default_factory=list, description="依赖该尺寸的下游特征或尺寸 ID")
    source: str = Field(default="sketch", description="尺寸来源：sketch, feature, pattern, mate 等")
    validation_status: str = Field(default="VALID", description="校验状态：VALID, OUT_OF_BOUNDS, OVER_DEFINED")

    @classmethod
    def create(
        cls,
        dimension_name: str,
        system_value: float,
        feature_name: str = "",
        feature_type: str = "",
        dim_type: DimensionType = DimensionType.UNKNOWN,
        is_driven: bool = False,
        editable: bool = True,
        source: str = "sketch",
    ) -> "DimensionIRNode":
        """工厂方法：根据底层系统数值构造 IR 节点并自动完成单位转换。"""
        clean_name = dimension_name.strip()
        param_name = clean_name.split("@")[0] if "@" in clean_name else clean_name
        
        # 判定单位体系
        if dim_type in (DimensionType.SKETCH_ANGLE, DimensionType.REVOLVE_ANGLE):
            unit = "deg"
            import math
            display_val = round(math.degrees(system_value), 4)
        else:
            unit = "mm"
            display_val = round(system_value * 1000.0, 4)

        dim_id = f"dim_{param_name.lower()}_{feature_name.lower()}".replace(" ", "_").replace("-", "_")
        role = DimensionRole.DRIVEN if is_driven else DimensionRole.DRIVING
        
        return cls(
            dimension_id=dim_id,
            dimension_name=clean_name,
            parameter_name=param_name,
            feature_name=feature_name,
            feature_type=feature_type,
            dimension_type=dim_type,
            value=display_val,
            unit=unit,
            system_value=system_value,
            editable=editable and (not is_driven),
            role=role,
            is_driven=is_driven,
            dimension_path=f"{feature_name}/{clean_name}",
            source=source,
            validation_status="VALID",
        )


class DimensionModelIR(BaseModel):
    """整套 CAD 模型的尺寸全景中间表示。"""
    model_title: str = Field(default="Part", description="模型文档标题")
    model_path: str = Field(default="", description="零件物理磁盘路径")
    dimensions: Dict[str, DimensionIRNode] = Field(default_factory=dict, description="按 dimension_name 索引的尺寸映射表")
    total_count: int = Field(default=0, description="尺寸总数")

    def add_dimension(self, node: DimensionIRNode) -> None:
        """向模型注册一个尺寸节点。"""
        self.dimensions[node.dimension_name] = node
        self.total_count = len(self.dimensions)

    def get_dimension(self, name_or_id: str) -> Optional[DimensionIRNode]:
        """通过名称、代号或 ID 检索尺寸。"""
        # 1. 严格全名匹配
        if name_or_id in self.dimensions:
            return self.dimensions[name_or_id]
        
        # 2. 忽略大小写匹配
        query_lower = name_or_id.lower().strip()
        for k, v in self.dimensions.items():
            if k.lower() == query_lower or v.dimension_id == query_lower:
                return v
        
        # 3. 匹配 parameter_name@feature_name
        for k, v in self.dimensions.items():
            if v.parameter_name.lower() == query_lower:
                return v
        return None

    def get_by_feature(self, feature_name: str) -> List[DimensionIRNode]:
        """获取指定特征下的所有尺寸。"""
        f_lower = feature_name.lower().strip()
        return [d for d in self.dimensions.values() if d.feature_name.lower() == f_lower]

    def get_driving_dimensions(self) -> List[DimensionIRNode]:
        """获取所有可编辑驱动尺寸。"""
        return [d for d in self.dimensions.values() if d.role == DimensionRole.DRIVING and d.editable]

    def to_summary_dict(self) -> Dict[str, Any]:
        """导出结构化摘要报告。"""
        return {
            "model_title": self.model_title,
            "model_path": self.model_path,
            "total_dimensions": self.total_count,
            "driving_count": len(self.get_driving_dimensions()),
            "dimensions": [
                {
                    "name": d.dimension_name,
                    "feature": d.feature_name,
                    "value": d.value,
                    "unit": d.unit,
                    "type": d.dimension_type.value,
                    "editable": d.editable,
                    "role": d.role.value,
                }
                for d in self.dimensions.values()
            ],
        }
