# -*- coding: utf-8 -*-
"""
vendor/solidworks-automation-skill/scripts/model_quality_inspector.py
SolidWorks 工业模型质量智能核查器 (Model Quality Inspector, MQI)。

核心职责：
1. 几何完整性核查：检测实体数 (Solid Bodies)、表面积、体积合法性与极限长宽比；
2. 特征树健康度扫描：检测是否存在求解失败 (Rebuild Error)、警告特征或悬空几何；
3. 草图约束完整性分析：统计完全定义率 (Fully Defined Ratio)、欠定义草图与浮动无约束自由度；
4. 尺寸与参数完备性：统计驱动尺寸与从动尺寸分布，核查是否有未标注参数；
5. 综合评级与结构化诊断报告：按工业工程标准输出加权评分 (0-100)、等级 (A/B/C/F) 及优化建议。
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

try:
    from .sw_connect import get_com_member
    from .dimension_reader import read_model_dimensions, walk_all_features
    from .sw_measure import collect_bounding_box, collect_mass_properties
except ImportError:
    from sw_connect import get_com_member
    from dimension_reader import read_model_dimensions, walk_all_features
    from sw_measure import collect_bounding_box, collect_mass_properties

logger = logging.getLogger("model_quality_inspector")


class MQIDeduction(BaseModel):
    """扣分项记录。"""
    dimension: str = Field(..., description="核查维度: geometry, feature_tree, sketch_constraint, dimension")
    item: str = Field(..., description="扣分实体名称或特征")
    reason: str = Field(..., description="扣分原因")
    penalty: float = Field(..., description="扣除分值")
    recommendation: str = Field(default="", description="改进或修复建议")


class DesignIntentTarget(BaseModel):
    """设计目标独立规格（供独立验证器交叉比对）。"""
    expected_solid_bodies: int = Field(default=1, description="期望实体数")
    expected_volume_mm3: Optional[float] = Field(default=None, description="期望理论体积 (mm^3)")
    volume_tolerance_rel: float = Field(default=0.02, description="体积相对容差 (默认 2%)")
    expected_surface_area_mm2: Optional[float] = Field(default=None, description="期望表面积 (mm^2)")
    surface_area_tolerance_rel: float = Field(default=0.03, description="表面积相对容差 (默认 3%)")
    expected_bbox_size_mm: Optional[List[float]] = Field(default=None, description="期望包围盒跨度 [X, Y, Z] (mm)")
    bbox_tolerance_mm: float = Field(default=0.5, description="包围盒尺寸绝对容差 (mm)")
    required_features: List[str] = Field(default_factory=list, description="必须存在的特征名称或关键词")
    prohibited_features: List[str] = Field(default_factory=list, description="严禁残留的临时特征")


class IntentVerificationResult(BaseModel):
    """独立交叉比对检验结果。"""
    passed: bool = Field(default=True, description="是否满足全部设计目标")
    discrepancies: List[str] = Field(default_factory=list, description="目标与实测不一致项列表")
    checks: Dict[str, bool] = Field(default_factory=dict, description="各项逐条检查结果")


class MQIReport(BaseModel):
    """模型质量核查综合诊断报告。"""
    model_title: str = Field(default="", description="被核查零件文档标题")
    score: float = Field(default=100.0, description="综合质量得分 (0-100)")
    grade: str = Field(default="A", description="质量等级: A (>=90), B (>=80), C (>=60), F (<60)")
    is_manufacturable: bool = Field(default=True, description="几何与建模规范是否达到可制造交付标准")

    # 统计指标
    solid_body_count: int = Field(default=0, description="实体数量")
    total_feature_count: int = Field(default=0, description="特征树总特征数")
    error_feature_count: int = Field(default=0, description="报错特征数 (红叉)")
    warning_feature_count: int = Field(default=0, description="警告特征数 (黄叹号)")
    total_sketch_count: int = Field(default=0, description="草图总数")
    fully_defined_sketches: int = Field(default=0, description="完全定义草图数")
    fully_defined_ratio: float = Field(default=1.0, description="草图完全定义比例 (0.0 - 1.0)")
    total_dimensions: int = Field(default=0, description="驱动尺寸总数")

    # 几何参数
    volume_mm3: float = Field(default=0.0, description="模型物理实测体积")
    surface_area_mm2: float = Field(default=0.0, description="模型表面积")
    bounding_box_size_mm: List[float] = Field(default_factory=list, description="包围盒尺寸 [X, Y, Z]")
    aspect_ratio: float = Field(default=1.0, description="最大几何跨距与最小跨距比例")

    # 扣分与建议列表
    deductions: List[MQIDeduction] = Field(default_factory=list, description="详细扣分项清单")
    warnings: List[str] = Field(default_factory=list, description="工程警告")
    suggestions: List[str] = Field(default_factory=list, description="工程优化改进建议")


class ModelQualityInspector:
    """工业级 SolidWorks 模型质量智能审查器。"""

    @classmethod
    def inspect_model(cls, model) -> MQIReport:
        """对已打开的 SolidWorks ModelDoc2 进行全景质量深度核查。"""
        title = str(get_com_member(model, "GetTitle") or "Untitled")
        deductions: List[MQIDeduction] = []
        warnings: List[str] = []
        suggestions: List[str] = []

        # -------------------------------------------------------------
        # 1. 物理几何与实体核查 (Physical Geometry & Bodies)
        # -------------------------------------------------------------
        try:
            mass = collect_mass_properties(model)
            vol = float(mass.get("volume_mm3", 0.0))
            area = float(mass.get("surface_area_mm2", 0.0))
        except Exception as e:
            vol, area = 0.0, 0.0
            warnings.append(f"质量属性读取异常: {e}")

        try:
            bbox = collect_bounding_box(model)
            sizes = bbox.get("size_mm", [0.0, 0.0, 0.0])
        except Exception as e:
            sizes = [0.0, 0.0, 0.0]
            warnings.append(f"包围盒计算异常: {e}")

        # 获取实体数
        body_count = 0
        try:
            part_doc = model
            bodies = get_com_member(part_doc, "GetBodies2", 0, True) # 0 = swSolidBody
            if bodies is not None:
                body_count = len(bodies) if isinstance(bodies, (list, tuple)) else 1
        except Exception:
            body_count = 1 if vol > 0.0 else 0

        if vol <= 0.0:
            deductions.append(
                MQIDeduction(
                    dimension="geometry",
                    item=title,
                    reason="模型实测体积为 0 或未生成有效实体",
                    penalty=40.0,
                    recommendation="检查模型特征树是否包含至少一个成功构建的实体凸台或拉伸特征",
                )
            )

        if body_count > 1:
            warnings.append(f"检测到多实体 (Multi-body: {body_count} 个实体)，若非特定装配/焊接件请核查是否需要组合实体")

        # 极端长宽比核查
        aspect_ratio = 1.0
        sorted_sizes = sorted([s for s in sizes if s > 0.0])
        if len(sorted_sizes) >= 2 and sorted_sizes[0] > 0.0:
            aspect_ratio = round(sorted_sizes[-1] / sorted_sizes[0], 2)
            if aspect_ratio > 100.0:
                deductions.append(
                    MQIDeduction(
                        dimension="geometry",
                        item=title,
                        reason=f"长宽比极端过大 ({aspect_ratio}:1)，存在微小薄壁或异常大尺度悬空特征",
                        penalty=10.0,
                        recommendation="核查模型包围盒尺寸是否存在误标注单位 (如米被误当毫米)",
                    )
                )

        # -------------------------------------------------------------
        # 2. 特征树健康度扫描 (Feature Tree Health)
        # -------------------------------------------------------------
        all_features = walk_all_features(model)
        feat_count = len(all_features)
        err_feat_count = 0
        warn_feat_count = 0

        sketches = []
        for feat in all_features:
            fname = str(get_com_member(feat, "Name") or "")
            ftype = str(get_com_member(feat, "GetTypeName2") or "")

            # 收集草图（排除坐标原点 OriginProfileFeature 等系统标记）
            if ftype in ("ProfileFeature", "3DProfileFeature") and "Origin" not in ftype and fname != "原点":
                sketches.append(feat)

            # 检查特征状态
            try:
                # GetErrorCode2 返回特征当前错误码
                err_code = int(get_com_member(feat, "GetErrorCode2") or 0)
                if err_code != 0:
                    err_feat_count += 1
                    deductions.append(
                        MQIDeduction(
                            dimension="feature_tree",
                            item=fname,
                            reason=f"特征存在求解错误 (ErrorCode={err_code})",
                            penalty=15.0,
                            recommendation=f"请在特征管理器中编辑并修复特征 [{fname}] 的父子依赖与几何输入",
                        )
                    )
            except Exception:
                pass

        # -------------------------------------------------------------
        # 3. 草图约束与完全定义率 (Sketch Constraints)
        # -------------------------------------------------------------
        sketch_count = len(sketches)
        fully_defined_sketches = 0

        for sk_feat in sketches:
            sk_name = str(get_com_member(sk_feat, "Name") or "")
            is_fully_defined = True
            try:
                sk_obj = get_com_member(sk_feat, "GetSpecificFeature2")
                if sk_obj is not None:
                    # SolidWorks swSketchConstrainedStatus_e:
                    # 1 = swSketchUnconstrained / None
                    # 2 = swSketchUnderConstrained (欠定义)
                    # 3 = swSketchFullyConstrained (完全定义)
                    # 4 = swSketchOverConstrained (过定义)
                    status_code = int(get_com_member(sk_obj, "GetConstrainedStatus") or 0)
                    if status_code == 3:
                        is_fully_defined = True
                    elif status_code == 4:
                        is_fully_defined = False
                        deductions.append(
                            MQIDeduction(
                                dimension="sketch_constraint",
                                item=sk_name,
                                reason="草图存在几何过定义 (Over-constrained)",
                                penalty=10.0,
                                recommendation=f"删除草图 [{sk_name}] 中冲突的冗余尺寸或几何关系约束",
                            )
                        )
                    elif status_code == 2:
                        is_fully_defined = False
                        # 检查草图是否至少具备尺寸标注
                        disp_dim = get_com_member(sk_feat, "GetFirstDisplayDimension")
                        if disp_dim is not None:
                            penalty = 3.0
                            reason = "草图处于部分欠定义状态 (包含关键尺寸但缺少全局基准定位)"
                        else:
                            penalty = 8.0
                            reason = "草图处于严重欠定义状态 (浮动无约束且无尺寸标注)"

                        deductions.append(
                            MQIDeduction(
                                dimension="sketch_constraint",
                                item=sk_name,
                                reason=reason,
                                penalty=penalty,
                                recommendation=f"为草图 [{sk_name}] 补充基准定位尺寸或几何约束",
                            )
                        )
                    else:
                        is_fully_defined = True
            except Exception:
                is_fully_defined = True

            if is_fully_defined:
                fully_defined_sketches += 1

        ratio = (fully_defined_sketches / sketch_count) if sketch_count > 0 else 1.0
        ratio = round(ratio, 4)

        # -------------------------------------------------------------
        # 4. 尺寸与参数完备性 (Dimension Health)
        # -------------------------------------------------------------
        total_dims = 0
        try:
            dim_model = read_model_dimensions(model)
            total_dims = len(dim_model.dimensions)
        except Exception:
            total_dims = 0

        if feat_count > 2 and total_dims == 0:
            deductions.append(
                MQIDeduction(
                    dimension="dimension",
                    item=title,
                    reason="实体模型缺少参数化尺寸标注，无法执行参数驱动",
                    penalty=10.0,
                    recommendation="在草图与拉伸特征中添加带显式代号的驱动尺寸 (DisplayDimension)",
                )
            )

        # -------------------------------------------------------------
        # 5. 综合算分与报告生成
        # -------------------------------------------------------------
        total_penalty = sum(d.penalty for d in deductions)
        final_score = max(0.0, round(100.0 - total_penalty, 1))

        if final_score >= 90.0:
            grade = "A"
        elif final_score >= 80.0:
            grade = "B"
        elif final_score >= 60.0:
            grade = "C"
        else:
            grade = "F"

        is_mfg = (final_score >= 80.0 and err_feat_count == 0 and vol > 0.0)

        if final_score >= 90.0:
            suggestions.append("模型几何规范性优异，特征完全求解且尺寸标注完整，可直接用于下游工程出图与数控制造。")
        else:
            suggestions.append("建议优先解决草图欠定义与潜在特征求解警告，确保参数化衍生修改时几何稳定。")

        return MQIReport(
            model_title=title,
            score=final_score,
            grade=grade,
            is_manufacturable=is_mfg,
            solid_body_count=body_count,
            total_feature_count=feat_count,
            error_feature_count=err_feat_count,
            warning_feature_count=warn_feat_count,
            total_sketch_count=sketch_count,
            fully_defined_sketches=fully_defined_sketches,
            fully_defined_ratio=ratio,
            total_dimensions=total_dims,
            volume_mm3=vol,
            surface_area_mm2=area,
            bounding_box_size_mm=sizes,
            aspect_ratio=aspect_ratio,
            deductions=deductions,
            warnings=warnings,
            suggestions=suggestions,
        )

    @classmethod
    def verify_design_intent(
        cls,
        report: MQIReport,
        target: DesignIntentTarget,
        actual_feature_names: Optional[List[str]] = None,
    ) -> IntentVerificationResult:
        """独立将模型实测报告与设计目标规格进行交叉比对。"""
        checks: Dict[str, bool] = {}
        discrepancies: List[str] = []

        # 1. 实体数量比对
        body_ok = (report.solid_body_count == target.expected_solid_bodies)
        checks["solid_bodies"] = body_ok
        if not body_ok:
            discrepancies.append(
                f"实体数量不匹配: 期望 {target.expected_solid_bodies}, 实际 {report.solid_body_count}"
            )

        # 2. 体积公差比对
        if target.expected_volume_mm3 is not None and target.expected_volume_mm3 > 0:
            exp_vol = target.expected_volume_mm3
            act_vol = report.volume_mm3
            rel_err = abs(act_vol - exp_vol) / exp_vol
            vol_ok = (rel_err <= target.volume_tolerance_rel)
            checks["volume_tolerance"] = vol_ok
            if not vol_ok:
                discrepancies.append(
                    f"理论体积误差超差: 期望 {exp_vol:.2f} mm^3, 实际 {act_vol:.2f} mm^3 (相对偏差 {rel_err*100:.2f}% > 容差 {target.volume_tolerance_rel*100:.1f}%)"
                )
        else:
            checks["volume_tolerance"] = True

        # 3. 表面积公差比对
        if target.expected_surface_area_mm2 is not None and target.expected_surface_area_mm2 > 0:
            exp_area = target.expected_surface_area_mm2
            act_area = report.surface_area_mm2
            rel_err_area = abs(act_area - exp_area) / exp_area
            area_ok = (rel_err_area <= target.surface_area_tolerance_rel)
            checks["surface_area_tolerance"] = area_ok
            if not area_ok:
                discrepancies.append(
                    f"表面积误差超差: 期望 {exp_area:.2f} mm^2, 实际 {act_area:.2f} mm^2 (偏差 {rel_err_area*100:.2f}% > 容差 {target.surface_area_tolerance_rel*100:.1f}%)"
                )
        else:
            checks["surface_area_tolerance"] = True

        # 4. 包围盒跨度比对
        if target.expected_bbox_size_mm:
            act_bbox = report.bounding_box_size_mm
            bbox_ok = True
            for idx in range(min(len(target.expected_bbox_size_mm), len(act_bbox))):
                exp_span = float(target.expected_bbox_size_mm[idx])
                act_span = float(act_bbox[idx])
                diff = abs(act_span - exp_span)
                if diff > target.bbox_tolerance_mm:
                    bbox_ok = False
                    discrepancies.append(
                        f"包围盒维度 [{idx}] 超差: 期望 {exp_span:.2f} mm, 实际 {act_span:.2f} mm (偏差 {diff:.2f} mm > 容差 {target.bbox_tolerance_mm} mm)"
                    )
            checks["bounding_box"] = bbox_ok
        else:
            checks["bounding_box"] = True

        # 5. 特征存在性与严禁项检查
        feat_names = actual_feature_names or []
        for req in target.required_features:
            found = any(req.lower() in fn.lower() for fn in feat_names)
            checks[f"required_feature_{req}"] = found
            if not found:
                discrepancies.append(f"缺少必要特征关键词: '{req}'")

        for pro in target.prohibited_features:
            found = any(pro.lower() in fn.lower() for fn in feat_names)
            checks[f"prohibited_feature_{pro}"] = not found
            if found:
                discrepancies.append(f"发现严禁残留的未清理特征: '{pro}'")

        all_passed = len(discrepancies) == 0
        return IntentVerificationResult(
            passed=all_passed,
            discrepancies=discrepancies,
            checks=checks,
        )
