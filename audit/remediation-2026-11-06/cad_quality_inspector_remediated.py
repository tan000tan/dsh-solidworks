"""
多维综合质量评价与优化引擎 (CAD Quality Inspector - Remediated Version)
对应第五阶段子阶段 S5-E 整改版：
整改要点：
1. 统一键名与单位：兼容 volume 与 volume_mm3，surface_area 与 surface_area_mm2，严格校验数据合法性。
2. 自比对探测与防御：严格检查实测值与理论值是否为同一内存对象或同一来源且未显式声明，拦截虚假自比对。
3. 理论值缺失严格处理：当缺少理论解析体积时，明确标记为 NOT VERIFIED，不给予虚假满分，几何项封顶并标记不合格。
4. 异常数值防御：处理负值、零值、NaN、非数字类型等非法输入。
5. 详细记录实测值、理论值、允许公差、实际绝对误差、相对误差与判定状态。
"""
import math
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class QualityCategoryScore(BaseModel):
    """单个维度的质量评价分项"""
    category_name: str
    score: float                    # 0.0 ~ 100.0
    weight: float                   # 权重 (例如 0.3)
    status: str = "VERIFIED"        # VERIFIED, PARTIALLY_VERIFIED, NOT_VERIFIED, FAILED
    passed_checks: List[str] = Field(default_factory=list)
    failed_checks: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class ComprehensiveQualityReport(BaseModel):
    """多维综合质量评估最终报告"""
    model_name: str
    overall_quality_score: float    # 综合总分 (0.0 ~ 100.0)
    is_acceptable: bool             # 总分 >= 80 且无致命项
    verification_status: str        # VERIFIED, PARTIAL, NOT_VERIFIED, FAILED
    geometry_score: QualityCategoryScore
    topology_score: QualityCategoryScore
    stability_score: QualityCategoryScore
    manufacturing_score: QualityCategoryScore
    metrics_summary: Dict[str, Any] = Field(default_factory=dict)
    actionable_recommendations: List[str] = Field(default_factory=list)


def _extract_number(data: Dict[str, Any], *keys, default=None) -> Optional[float]:
    """安全提取指定键名候选列表中的浮点数值"""
    if not isinstance(data, dict):
        return default
    for k in keys:
        if k in data and data[k] is not None:
            try:
                v = float(data[k])
                if math.isnan(v) or math.isinf(v):
                    return None
                return v
            except (ValueError, TypeError):
                return None
    return default


class CadQualityInspector:
    """多维 CAD 质量检查器 (修复与防御增强版)"""

    def __init__(self):
        # 四个维度的基准权重：几何 30%，拓扑 25%，稳定性 25%，工艺性 20%
        self.weights = {
            "geometry": 0.30,
            "topology": 0.25,
            "stability": 0.25,
            "manufacturing": 0.20
        }

    def inspect_quality(
        self,
        model_name: str,
        measured_props: Dict[str, Any],
        theoretical_props: Optional[Dict[str, Any]] = None,
        feature_point_samples: Optional[Dict[str, List[float]]] = None,
        expected_point_samples: Optional[Dict[str, List[float]]] = None,
        rebuild_time_sec: float = 0.5,
        sketch_constrained_status: str = "FULLY_CONSTRAINED",
        independent_theoretical_source: bool = True
    ) -> ComprehensiveQualityReport:
        """
        执行综合多维质量评价
        """
        # 1. 几何维度核验 (含宏观体积、自比对防范与局部微观坐标采样)
        geom_cat, geom_metrics = self._evaluate_geometry(
            measured_props, theoretical_props, feature_point_samples, expected_point_samples,
            independent_theoretical_source=independent_theoretical_source
        )

        # 2. 拓扑与约束规范核验
        topo_cat = self._evaluate_topology(sketch_constrained_status, measured_props)

        # 3. 重建稳定性核验
        stab_cat = self._evaluate_stability(rebuild_time_sec)

        # 4. 机械加工工艺性核验
        mfg_cat = self._evaluate_manufacturing(measured_props)

        # 5. 计算加权总分
        overall = (
            geom_cat.score * self.weights["geometry"] +
            topo_cat.score * self.weights["topology"] +
            stab_cat.score * self.weights["stability"] +
            mfg_cat.score * self.weights["manufacturing"]
        )
        overall = max(0.0, min(100.0, overall))

        # 6. 收集优化建议
        recommendations = []
        for cat in [geom_cat, topo_cat, stab_cat, mfg_cat]:
            for w in cat.warnings:
                recommendations.append(f"[{cat.category_name} 优化项] {w}")
            for f in cat.failed_checks:
                recommendations.append(f"[{cat.category_name} 整改项] {f}")

        # 判定最终接受状态：总分 >= 80，几何项必须为 VERIFIED，且各维度不得有任何 FAILED 或未通过检查项
        all_categories = [geom_cat, topo_cat, stab_cat, mfg_cat]
        has_any_failed = any(c.status == "FAILED" or len(c.failed_checks) > 0 for c in all_categories)
        is_acc = (overall >= 80.0) and (not has_any_failed) and (geom_cat.status == "VERIFIED")

        verdict_status = "VERIFIED"
        if not is_acc:
            if has_any_failed or len(geom_cat.failed_checks) > 0:
                verdict_status = "FAILED"
            elif geom_cat.status == "NOT_VERIFIED":
                verdict_status = "NOT_VERIFIED"
            else:
                verdict_status = "PARTIALLY_VERIFIED"

        return ComprehensiveQualityReport(
            model_name=model_name,
            overall_quality_score=round(overall, 1),
            is_acceptable=is_acc,
            verification_status=verdict_status,
            geometry_score=geom_cat,
            topology_score=topo_cat,
            stability_score=stab_cat,
            manufacturing_score=mfg_cat,
            metrics_summary=geom_metrics,
            actionable_recommendations=recommendations
        )

    def _evaluate_geometry(
        self,
        measured: Dict[str, Any],
        theoretical: Optional[Dict[str, Any]],
        samples: Optional[Dict[str, List[float]]],
        expected_samples: Optional[Dict[str, List[float]]],
        independent_theoretical_source: bool = True
    ) -> tuple[QualityCategoryScore, Dict[str, Any]]:
        score = 100.0
        passed = []
        failed = []
        warnings = []
        status = "VERIFIED"
        metrics: Dict[str, Any] = {}

        # 提取实测体积与理论体积 (兼容 volume 与 volume_mm3)
        v_meas = _extract_number(measured, "volume", "volume_mm3")
        v_theo = _extract_number(theoretical, "volume", "volume_mm3") if theoretical else None

        # (0) 自比对与引用同一数据探测
        if theoretical is not None:
            if measured is theoretical:
                failed.append("严重缺陷：实测值与理论值指向完全相同的字典对象 (自比对虚假核验)")
                score = 0.0
                status = "FAILED"
                metrics["self_comparison_detected"] = True
                return QualityCategoryScore(
                    category_name="几何尺寸与局部微观坐标",
                    score=0.0,
                    weight=self.weights["geometry"],
                    status="FAILED",
                    passed_checks=passed,
                    failed_checks=failed,
                    warnings=warnings
                ), metrics

            if not independent_theoretical_source:
                warnings.append("提示：理论数据源未显式声明为独立来源，存在潜在偶合风险")
                score -= 15.0

        # (1) 宏观体积核验
        if v_meas is None or v_meas <= 0:
            failed.append(f"实测体积非法或非正数 (实测值={v_meas})")
            score = 0.0
            status = "FAILED"
        elif v_theo is None:
            # 严格整改：没有理论值不得报告 100 分，明确标记 NOT_VERIFIED！
            warnings.append("缺少理论解析体积，无法执行独立相对误差计算")
            score -= 40.0 # 缺少理论值扣除几何项 40 分
            status = "NOT_VERIFIED"
            passed.append(f"实测体积有效且大于零 ({v_meas:.2f} mm³)")
            metrics["volume_measured_mm3"] = v_meas
            metrics["volume_theoretical_mm3"] = None
            metrics["volume_relative_error"] = None
        elif v_theo <= 0:
            failed.append(f"理论解析体积定义非法或非正数 (理论值={v_theo})")
            score -= 50.0
            status = "FAILED"
        else:
            # 正常执行独立比对
            err_v = abs(v_meas - v_theo) / v_theo
            metrics["volume_measured_mm3"] = v_meas
            metrics["volume_theoretical_mm3"] = v_theo
            metrics["volume_relative_error"] = err_v

            # 探测数值完全雷同但无理论推导的自填充
            if err_v == 0.0 and (v_meas > 1000.0) and (not isinstance(v_theo, int)) and (len(str(v_meas)) == len(str(v_theo))):
                if samples == expected_samples and samples is not None:
                    warnings.append("警告：实测值与理论值浮点完全重合且采样点完全一致，请确认非复制填充")

            if err_v <= 0.0005:  # 0.05% 以内
                passed.append(f"宏观体积误差吻合优秀 (实测={v_meas:.2f}, 理论={v_theo:.2f}, 相对误差={err_v*100:.4f}% <= 0.05%)")
            elif err_v <= 0.01:   # 1.0% 以内
                score -= 10.0
                warnings.append(f"宏观体积相对误差偏大 (相对误差={err_v*100:.2f}%)")
            else:
                score -= 40.0
                failed.append(f"宏观体积超标严重 (实测={v_meas:.2f}, 理论={v_theo:.2f}, 相对误差={err_v*100:.2f}% > 1.0%)")
                status = "FAILED"

        # (2) 微观坐标采样核验
        if samples and expected_samples:
            max_dev = 0.0
            for pt_name, pt_meas in samples.items():
                if pt_name in expected_samples:
                    pt_exp = expected_samples[pt_name]
                    dist = math.sqrt(sum((a - b)**2 for a, b in zip(pt_meas, pt_exp)))
                    max_dev = max(max_dev, dist)
                    if dist > 0.005:  # 超出 5 微米公差
                        score -= 35.0
                        failed.append(
                            f"关键特征采样点 [{pt_name}] 坐标偏移超差: 实测 {pt_meas}, 预期 {pt_exp}, 偏差 {dist:.4f}mm > 0.005mm"
                        )
                        status = "FAILED"
                    else:
                        passed.append(f"关键特征点 [{pt_name}] 空间坐标精准吻合 (偏差={dist*1000:.1f}um)")
            metrics["max_point_deviation_mm"] = max_dev
        elif expected_samples and not samples:
            warnings.append("缺少实测微观空间采样点，微观几何项未覆盖")
            score -= 15.0

        return QualityCategoryScore(
            category_name="几何尺寸与局部微观坐标",
            score=max(0.0, score),
            weight=self.weights["geometry"],
            status=status,
            passed_checks=passed,
            failed_checks=failed,
            warnings=warnings
        ), metrics

    def _evaluate_topology(
        self,
        sketch_status: str,
        measured: Dict[str, Any]
    ) -> QualityCategoryScore:
        score = 100.0
        passed = []
        failed = []
        warnings = []
        status = "VERIFIED"

        if sketch_status == "FULLY_CONSTRAINED":
            passed.append("草图几何约束处于完全定义 (Fully Defined) 稳定状态")
        elif sketch_status == "UNDER_CONSTRAINED":
            score -= 30.0
            warnings.append("草图存在欠定义 (Under-defined) 元素，后续参数修改容易引发漂移")
            status = "PARTIALLY_VERIFIED"
        elif sketch_status == "OVER_CONSTRAINED":
            score -= 40.0
            failed.append("草图存在过定义 (Over-defined) 冲突约束")
            status = "FAILED"

        body_count = measured.get("body_count", 1)
        if body_count == 1:
            passed.append("单实体零件拓扑闭合完整")
        else:
            warnings.append(f"零件包含 {body_count} 个独立非合并实体，需确认是否为设计意图")

        return QualityCategoryScore(
            category_name="拓扑规范与草图约束",
            score=max(0.0, score),
            weight=self.weights["topology"],
            status=status,
            passed_checks=passed,
            failed_checks=failed,
            warnings=warnings
        )

    def _evaluate_stability(self, rebuild_time_sec: float) -> QualityCategoryScore:
        score = 100.0
        passed = []
        failed = []
        warnings = []
        status = "VERIFIED"

        if rebuild_time_sec <= 1.0:
            passed.append(f"模型强制重建响应迅速 ({rebuild_time_sec:.2f}s <= 1.0s)")
        elif rebuild_time_sec <= 3.0:
            score -= 10.0
            warnings.append(f"模型重建耗时偏长 ({rebuild_time_sec:.2f}s)")
            status = "PARTIALLY_VERIFIED"
        else:
            score -= 30.0
            failed.append(f"模型特征计算负荷沉重，重建严重滞后 ({rebuild_time_sec:.2f}s > 3.0s)")
            status = "FAILED"

        return QualityCategoryScore(
            category_name="重建稳定性与计算负荷",
            score=max(0.0, score),
            weight=self.weights["stability"],
            status=status,
            passed_checks=passed,
            failed_checks=failed,
            warnings=warnings
        )

    def _evaluate_manufacturing(self, measured: Dict[str, Any]) -> QualityCategoryScore:
        score = 100.0
        passed = []
        failed = []
        warnings = []
        status = "VERIFIED"

        min_wall = _extract_number(measured, "min_wall_thickness", default=5.0)
        if min_wall is not None and min_wall < 1.5:
            score -= 25.0
            warnings.append(f"检测到薄壁结构 (最小壁厚 {min_wall:.2f}mm < 1.5mm)，加工时存在振刀与变形风险")
            status = "PARTIALLY_VERIFIED"
        else:
            passed.append(f"壁厚满足常规切削加工要求 ({min_wall:.2f}mm >= 1.5mm)")

        has_sharp_internal_corners = measured.get("has_sharp_internal_corners", False)
        if has_sharp_internal_corners:
            score -= 20.0
            warnings.append("存在内凹尖角未执行倒圆角 (应力集中源，建议增加 R2~R3 圆角)")
        else:
            passed.append("内角平滑过渡良好")

        return QualityCategoryScore(
            category_name="机械加工工艺性",
            score=max(0.0, score),
            weight=self.weights["manufacturing"],
            status=status,
            passed_checks=passed,
            failed_checks=failed,
            warnings=warnings
        )
