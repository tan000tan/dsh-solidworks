"""
多维综合质量评价与优化引擎 (CAD Quality Inspector)
对应第五阶段子阶段 S5-E：
从几何尺寸、局部坐标微观采样、拓扑定义规范、重建稳定性与机械加工工艺性
多维度进行 0~100 分量化评分，彻底攻破单纯依赖体积/表面积核验的孔位偏移钝化盲区。
"""
import math
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class QualityCategoryScore(BaseModel):
    """单个维度的质量评价分项"""
    category_name: str
    score: float                    # 0.0 ~ 100.0
    weight: float                   # 权重 (例如 0.3)
    passed_checks: List[str] = Field(default_factory=list)
    failed_checks: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class ComprehensiveQualityReport(BaseModel):
    """多维综合质量评估最终报告"""
    model_name: str
    overall_quality_score: float    # 综合总分 (0.0 ~ 100.0)
    is_acceptable: bool             # 总分 >= 80 且无致命项
    geometry_score: QualityCategoryScore
    topology_score: QualityCategoryScore
    stability_score: QualityCategoryScore
    manufacturing_score: QualityCategoryScore
    actionable_recommendations: List[str] = Field(default_factory=list)


class CadQualityInspector:
    """多维 CAD 质量检查器"""

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
        sketch_constrained_status: str = "FULLY_CONSTRAINED"
    ) -> ComprehensiveQualityReport:
        """
        执行综合多维质量评价
        """
        # 1. 几何维度核验 (含微观局部坐标采样)
        geom_cat = self._evaluate_geometry(
            measured_props, theoretical_props, feature_point_samples, expected_point_samples
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

        is_acc = overall >= 80.0 and len(geom_cat.failed_checks) == 0

        return ComprehensiveQualityReport(
            model_name=model_name,
            overall_quality_score=round(overall, 1),
            is_acceptable=is_acc,
            geometry_score=geom_cat,
            topology_score=topo_cat,
            stability_score=stab_cat,
            manufacturing_score=mfg_cat,
            actionable_recommendations=recommendations
        )

    def _evaluate_geometry(
        self,
        measured: Dict[str, Any],
        theoretical: Optional[Dict[str, Any]],
        samples: Optional[Dict[str, List[float]]],
        expected_samples: Optional[Dict[str, List[float]]]
    ) -> QualityCategoryScore:
        score = 100.0
        passed = []
        failed = []
        warnings = []

        # (1) 宏观体积核验
        if theoretical and theoretical.get("volume") is not None:
            v_theo = theoretical["volume"]
            v_meas = measured.get("volume", 0.0)
            err_v = abs(v_meas - v_theo) / max(abs(v_theo), 1e-6)
            if err_v <= 0.0001:
                passed.append(f"宏观体积误差极其微小 ({err_v*100:.4f}% <= 0.01%)")
            elif err_v <= 0.01:
                score -= 10.0
                warnings.append(f"宏观体积相对误差偏大 ({err_v*100:.2f}%)")
            else:
                score -= 40.0
                failed.append(f"宏观体积超标严重 ({err_v*100:.2f}% > 1.0%)")
        else:
            warnings.append("缺少理论解析体积，仅执行基本非零体积核验")
            if measured.get("volume", 0.0) > 0:
                passed.append("实测体积大于零")

        # (2) 微观坐标采样核验 (攻破孔位偏移钝化盲区)
        if samples and expected_samples:
            max_dev = 0.0
            for pt_name, pt_meas in samples.items():
                if pt_name in expected_samples:
                    pt_exp = expected_samples[pt_name]
                    dist = math.sqrt(sum((a - b)**2 for a, b in zip(pt_meas, pt_exp)))
                    max_dev = max(max_dev, dist)
                    if dist > 0.001:  # 超出 1 微米公差
                        score -= 35.0
                        failed.append(
                            f"关键特征采样点 [{pt_name}] 坐标偏移超差: 实测 {pt_meas}, 预期 {pt_exp}, 偏差 {dist:.3f}mm"
                        )
                    else:
                        passed.append(f"关键特征点 [{pt_name}] 空间坐标精准吻合")
        return QualityCategoryScore(
            category_name="几何尺寸与局部微观坐标",
            score=max(0.0, score),
            weight=self.weights["geometry"],
            passed_checks=passed,
            failed_checks=failed,
            warnings=warnings
        )

    def _evaluate_topology(
        self,
        sketch_status: str,
        measured: Dict[str, Any]
    ) -> QualityCategoryScore:
        score = 100.0
        passed = []
        failed = []
        warnings = []

        if sketch_status == "FULLY_CONSTRAINED":
            passed.append("草图几何约束处于完全定义 (Fully Defined) 稳定状态")
        elif sketch_status == "UNDER_CONSTRAINED":
            score -= 30.0
            warnings.append("草图存在欠定义 (Under-defined) 元素，后续参数修改容易引发漂移")
        elif sketch_status == "OVER_CONSTRAINED":
            score -= 40.0
            failed.append("草图存在过定义 (Over-defined) 冲突约束")

        body_count = measured.get("body_count", 1)
        if body_count == 1:
            passed.append("单实体零件拓扑闭合完整")
        else:
            warnings.append(f"零件包含 {body_count} 个独立非合并实体，需确认是否为设计意图")

        return QualityCategoryScore(
            category_name="拓扑规范与草图约束",
            score=max(0.0, score),
            weight=self.weights["topology"],
            passed_checks=passed,
            failed_checks=failed,
            warnings=warnings
        )

    def _evaluate_stability(self, rebuild_time_sec: float) -> QualityCategoryScore:
        score = 100.0
        passed = []
        failed = []
        warnings = []

        if rebuild_time_sec <= 1.0:
            passed.append(f"模型强制重建响应迅速 ({rebuild_time_sec:.2f}s <= 1.0s)")
        elif rebuild_time_sec <= 3.0:
            score -= 10.0
            warnings.append(f"模型重建耗时偏长 ({rebuild_time_sec:.2f}s)")
        else:
            score -= 30.0
            failed.append(f"模型特征计算负荷沉重，重建严重滞后 ({rebuild_time_sec:.2f}s > 3.0s)")

        return QualityCategoryScore(
            category_name="重建稳定性与计算负荷",
            score=max(0.0, score),
            weight=self.weights["stability"],
            passed_checks=passed,
            failed_checks=failed,
            warnings=warnings
        )

    def _evaluate_manufacturing(self, measured: Dict[str, Any]) -> QualityCategoryScore:
        score = 100.0
        passed = []
        failed = []
        warnings = []

        min_wall = measured.get("min_wall_thickness", 5.0)
        if min_wall < 1.5:
            score -= 25.0
            warnings.append(f"检测到薄壁结构 (最小壁厚 {min_wall:.2f}mm < 1.5mm)，加工时存在振刀与变形风险")
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
            passed_checks=passed,
            failed_checks=failed,
            warnings=warnings
        )
