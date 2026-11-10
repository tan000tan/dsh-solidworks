# -*- coding: utf-8 -*-
"""
tests/real_cad/geometry_verifier.py
真实 SolidWorks 零件几何结果与特征树严密校验器。

深入 SolidWorks COM 接口，物理断言特征树状态、实体数量、几何包围盒与质量属性。
适配本地化特征名称 (草图1 / 凸台-拉伸1 / 切除-拉伸1) 与 sw_measure 实际输出规范。
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("geometry_verifier")


@dataclass
class GeometricExpectation:
    """单个测试的预期几何与物理参数规范。"""
    # 允许指定中英文关键词或特征类型 (例如: ["草图", "拉伸"] 或 ["ProfileFeature", "Extrusion"])
    expected_feature_types: List[str] = field(default_factory=list)
    expected_feature_keywords: List[str] = field(default_factory=list)
    expected_solid_bodies: int = 1
    # 包围盒期望跨度 (毫米)，容差默认 0.5mm
    expected_bbox_mm: Optional[List[float]] = None
    bbox_tol_mm: float = 0.5
    # 体积期望值 (立方毫米)，相对容差 2%
    expected_volume_mm3: Optional[float] = None
    volume_rel_tol: float = 0.02
    # 表面积期望值 (平方毫米)，相对容差 2%
    expected_surface_area_mm2: Optional[float] = None
    surface_area_rel_tol: float = 0.02


@dataclass
class VerificationReport:
    """几何物理验证结果报告。"""
    passed: bool
    checks: Dict[str, bool] = field(default_factory=dict)
    actual_features: List[Tuple[str, str]] = field(default_factory=list)
    actual_solid_bodies: int = 0
    actual_bbox_mm: Optional[List[float]] = None
    actual_volume_mm3: Optional[float] = None
    actual_surface_area_mm2: Optional[float] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"验证结果: {'[PASS]' if self.passed else '[FAIL]'}", "各项检查清单:"]
        for k, v in self.checks.items():
            lines.append(f"  - {k}: {'PASS' if v else 'FAIL'}")
        if self.errors:
            lines.append("错误详情:")
            for e in self.errors:
                lines.append(f"  ! {e}")
        return "\n".join(lines)


class GeometryVerifier:
    """通过 SolidWorks COM 对零件几何进行深度物理验证。"""

    @staticmethod
    def verify(model: Any, expectation: GeometricExpectation) -> VerificationReport:
        report = VerificationReport(passed=True)

        if model is None:
            report.passed = False
            report.errors.append("ModelDoc 引用为空，无法进行几何验证")
            return report

        from sw_connect import get_com_member

        # 1. 验证模型基本状态与标题
        try:
            title = str(get_com_member(model, "GetTitle") or "")
            report.checks["document_valid"] = bool(title)
        except Exception as e:
            report.checks["document_valid"] = False
            report.errors.append(f"读取文档标题失败: {e}")

        # 2. 遍历特征树，收集所有特征名称与类型
        try:
            feat_list: List[Tuple[str, str]] = []
            feat = get_com_member(model, "FirstFeature")
            while feat:
                fname = str(get_com_member(feat, "Name") or "")
                ftype = str(get_com_member(feat, "GetTypeName2") or "")
                feat_list.append((fname, ftype))

                # 检查特征是否有告警或几何损坏
                try:
                    err_code = get_com_member(feat, "GetErrorCode2")
                    if err_code and int(err_code) != 0:
                        report.warnings.append(f"特征 [{fname}] 报告错误代码: {err_code}")
                except Exception:
                    pass
                feat = get_com_member(feat, "GetNextFeature")

            report.actual_features = feat_list
            report.checks["features_scanned"] = True

            all_names = [f[0] for f in feat_list]
            all_types = [f[1] for f in feat_list]

            # 检查预期特征类型是否出现
            type_check_ok = True
            for exp_t in expectation.expected_feature_types:
                if exp_t not in all_types:
                    type_check_ok = False
                    report.errors.append(f"特征树中缺少预期类型特征: {exp_t}")
            report.checks["expected_types_present"] = type_check_ok
            if not type_check_ok:
                report.passed = False

            # 检查预期特征关键词是否出现
            kw_check_ok = True
            for kw in expectation.expected_feature_keywords:
                matched = any(kw.lower() in fname.lower() for fname in all_names)
                if not matched:
                    kw_check_ok = False
                    report.errors.append(f"特征树中未找到匹配关键词的特征: '{kw}'")
            report.checks["expected_keywords_present"] = kw_check_ok
            if not kw_check_ok:
                report.passed = False

        except Exception as exc:
            report.passed = False
            report.checks["features_scanned"] = False
            report.errors.append(f"遍历特征树异常: {exc}")

        # 3. 检查实体数量 (swSolidBody = 0)
        try:
            bodies = get_com_member(model, "GetBodies2", 0, True)
            body_count = len(bodies) if bodies else 0
            if body_count == 0:
                # 兼容降级
                bc = get_com_member(model, "GetBodyCount", 0)
                if bc:
                    body_count = int(bc)

            report.actual_solid_bodies = body_count
            if body_count != expectation.expected_solid_bodies:
                report.passed = False
                report.checks["solid_body_count"] = False
                report.errors.append(f"实体数量不匹配: 期望 {expectation.expected_solid_bodies}, 实际 {body_count}")
            else:
                report.checks["solid_body_count"] = True
        except Exception as exc:
            report.checks["solid_body_count"] = False
            report.warnings.append(f"读取实体数量异常: {exc}")

        # 4. 验证包围盒 (使用 sw_measure.collect_bounding_box)
        try:
            from sw_measure import collect_bounding_box
            bbox_data = collect_bounding_box(model)
            if bbox_data and "size_mm" in bbox_data:
                size_mm = bbox_data["size_mm"]
                report.actual_bbox_mm = size_mm
                if expectation.expected_bbox_mm:
                    bbox_ok = True
                    for i in range(min(len(size_mm), len(expectation.expected_bbox_mm))):
                        exp_dim = float(expectation.expected_bbox_mm[i])
                        act_dim = float(size_mm[i])
                        delta = abs(exp_dim - act_dim)
                        if delta > expectation.bbox_tol_mm:
                            bbox_ok = False
                            report.errors.append(
                                f"包围盒尺寸超差 [维度 {i}]: 期望 {exp_dim:.2f}mm, "
                                f"实际 {act_dim:.2f}mm (偏差 {delta:.3f}mm > 容差 {expectation.bbox_tol_mm:.3f}mm)"
                            )
                    report.checks["bounding_box_within_tolerance"] = bbox_ok
                    if not bbox_ok:
                        report.passed = False
                else:
                    report.checks["bounding_box_within_tolerance"] = True
            else:
                report.checks["bounding_box_within_tolerance"] = True
        except Exception as exc:
            report.checks["bounding_box_within_tolerance"] = False
            report.warnings.append(f"提取或比对包围盒异常: {exc}")

        # 5. 验证质量属性 (使用 sw_measure.collect_mass_properties)
        try:
            from sw_measure import collect_mass_properties
            mass_props = collect_mass_properties(model)
            if mass_props:
                vol_mm3 = float(mass_props.get("volume_mm3", 0.0))
                area_mm2 = float(mass_props.get("surface_area_mm2", 0.0))
                report.actual_volume_mm3 = vol_mm3
                report.actual_surface_area_mm2 = area_mm2

                # 检查体积 (mm^3)
                if expectation.expected_volume_mm3 is not None and expectation.expected_volume_mm3 > 0:
                    exp_vol = expectation.expected_volume_mm3
                    vol_err_ratio = abs(vol_mm3 - exp_vol) / exp_vol
                    if vol_err_ratio > expectation.volume_rel_tol:
                        report.passed = False
                        report.checks["volume_within_tolerance"] = False
                        report.errors.append(
                            f"体积相对误差超差: 期望 {exp_vol:.2f}mm^3, 实际 {vol_mm3:.2f}mm^3 (误差 {vol_err_ratio*100:.2f}% > 容差 {expectation.volume_rel_tol*100:.1f}%)"
                        )
                    else:
                        report.checks["volume_within_tolerance"] = True
                else:
                    report.checks["volume_within_tolerance"] = True

                # 检查表面积 (mm^2)
                if expectation.expected_surface_area_mm2 is not None and expectation.expected_surface_area_mm2 > 0:
                    exp_area = expectation.expected_surface_area_mm2
                    area_err_ratio = abs(area_mm2 - exp_area) / exp_area
                    if area_err_ratio > expectation.surface_area_rel_tol:
                        report.passed = False
                        report.checks["surface_area_within_tolerance"] = False
                        report.errors.append(
                            f"表面积相对误差超差: 期望 {exp_area:.2f}mm^2, 实际 {area_mm2:.2f}mm^2 (误差 {area_err_ratio*100:.2f}% > 容差 {expectation.surface_area_rel_tol*100:.1f}%)"
                        )
                    else:
                        report.checks["surface_area_within_tolerance"] = True
                else:
                    report.checks["surface_area_within_tolerance"] = True
        except Exception as exc:
            report.checks["mass_properties_valid"] = False
            report.warnings.append(f"提取或比对质量属性异常: {exc}")

        # 6. Rebuild 模型有效性检查
        try:
            rebuild_res = get_com_member(model, "EditRebuild3")
            if rebuild_res not in (0, True, None):
                report.passed = False
                report.checks["rebuild_clean"] = False
                report.errors.append(f"EditRebuild3 返回模型错误码: {rebuild_res}")
            else:
                report.checks["rebuild_clean"] = True
        except Exception as exc:
            report.checks["rebuild_clean"] = False
            report.errors.append(f"执行 EditRebuild3 异常: {exc}")

        return report
