"""
多方案自动规划与比较引擎 (Multi-Scheme Planner)
对应第五阶段子阶段 S5-A：
输入零件设计需求规格，自动生成至少 2~3 个结构化、具有实质工艺差异的建模方案，
并从特征复杂度、参数化自由度、加工契合度与重建稳定性多维度进行量化评分选优。
"""
import copy
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ManufacturingIntent(str, Enum):
    """制造工艺意图"""
    TURNING = "turning"                         # 回转车削工艺 (适合回转体轴/盘)
    EXTRUSION_STACK = "extrusion_stack"         # 阶梯拉伸堆叠 (适合台阶座/法兰)
    SUBTRACTIVE_POCKET = "subtractive_pocket"   # 实体减除挖槽 (适合箱体/支架)
    SHEET_METAL = "sheet_metal"                 # 钣金折弯成型


class SchemeStep(BaseModel):
    """方案单步特征构建计划"""
    step_id: str
    feature_type: str
    description: str
    params: Dict[str, Any]
    dependencies: List[str] = Field(default_factory=list)


class ModelingScheme(BaseModel):
    """建模方案结构体"""
    scheme_id: str
    scheme_name: str
    manufacturing_intent: ManufacturingIntent
    steps: List[SchemeStep]
    feature_count: int
    complexity_score: float         # 0.0 ~ 10.0 (越低越紧凑)
    parametric_freedom: float       # 0.0 ~ 10.0 (越高参数化可调性越强)
    rebuild_risk_score: float       # 0.0 ~ 10.0 (越低越稳定)
    overall_score: float            # 综合评分 (0.0 ~ 100.0)
    selection_rationale: str


class MultiSchemePlanResult(BaseModel):
    """多方案规划比选最终结果"""
    design_goal: str
    candidate_schemes: List[ModelingScheme]
    recommended_scheme_id: str
    recommendation_summary: str


class MultiSchemePlanner:
    """多方案自动规划器"""

    def __init__(self):
        pass

    def plan_schemes(self, design_spec: Dict[str, Any]) -> MultiSchemePlanResult:
        """根据设计规格自动生成并评估候选方案"""
        part_type = design_spec.get("part_type", "general").lower()
        design_goal = design_spec.get("description", "设计指定机械零件")

        candidates: List[ModelingScheme] = []

        if part_type in ["flange", "bushing", "shaft", "round_cap", "disk"]:
            # 回转对称类零件：生成 回转车削方案 与 阶梯拉伸堆叠方案
            candidates.append(self._generate_turning_scheme(design_spec))
            candidates.append(self._generate_extrusion_scheme(design_spec))
            candidates.append(self._generate_subtractive_scheme(design_spec))
        else:
            # 箱体、支架与通用块类零件：生成 实体减材方案 与 分层堆叠方案
            candidates.append(self._generate_subtractive_scheme(design_spec))
            candidates.append(self._generate_extrusion_scheme(design_spec))

        # 量化评分与选优
        ranked_schemes = self._rank_schemes(candidates)
        recommended = ranked_schemes[0]

        summary = (
            f"针对设计目标 [{design_goal}]，系统规划了 {len(ranked_schemes)} 个可行方案。"
            f"推荐方案为 [{recommended.scheme_name}] (得分: {recommended.overall_score:.1f}/100)，"
            f"理由：{recommended.selection_rationale}"
        )

        return MultiSchemePlanResult(
            design_goal=design_goal,
            candidate_schemes=ranked_schemes,
            recommended_scheme_id=recommended.scheme_id,
            recommendation_summary=summary
        )

    def _generate_turning_scheme(self, spec: Dict[str, Any]) -> ModelingScheme:
        """生成方案 A：回转车削工艺方案"""
        steps = [
            SchemeStep(
                step_id="step_1_sketch",
                feature_type="sketch_revolve_profile",
                description="在前视基准面上绘制回转半截面轮廓与中心回转轴线",
                params={"plane": "Front Plane", "is_closed": True}
            ),
            SchemeStep(
                step_id="step_2_revolve",
                feature_type="solidworks_revolve_boss",
                description="围绕中心轴执行 360° 回转凸台，一次性成型多阶外圆与中心通孔",
                params={"angle": 360.0},
                dependencies=["step_1_sketch"]
            ),
            SchemeStep(
                step_id="step_3_hole_pattern",
                feature_type="solidworks_extrude_cut",
                description="在端面开设节圆均布螺栓通孔系",
                params={"depth": spec.get("flange_thickness", 20.0), "through_all": True},
                dependencies=["step_2_revolve"]
            ),
            SchemeStep(
                step_id="step_4_chamfer",
                feature_type="solidworks_chamfer",
                description="对轴端与孔口执行 1x45° 引入倒角",
                params={"distance": 1.0, "angle": 45.0},
                dependencies=["step_2_revolve", "step_3_hole_pattern"]
            )
        ]
        return ModelingScheme(
            scheme_id="SCHEME_A_TURNING",
            scheme_name="方案 A：回转车削工艺方案",
            manufacturing_intent=ManufacturingIntent.TURNING,
            steps=steps,
            feature_count=len(steps),
            complexity_score=2.0,       # 草图回转成型，特征树极度紧凑
            parametric_freedom=8.8,     # 半径尺寸修改极为直接
            rebuild_risk_score=1.5,     # 重建失败概率极低
            overall_score=0.0,          # 待计算
            selection_rationale="特征树极简，高度契合车床回转加工工艺，轴向尺寸与半径关联稳定，重建失败率极低。"
        )

    def _generate_extrusion_scheme(self, spec: Dict[str, Any]) -> ModelingScheme:
        """生成方案 B：阶梯拉伸堆叠方案"""
        steps = [
            SchemeStep(
                step_id="step_1_base_extrusion",
                feature_type="solidworks_extrude_boss",
                description="在前视基准面拉伸法兰基盘底座",
                params={"depth": spec.get("base_thickness", 15.0)}
            ),
            SchemeStep(
                step_id="step_2_boss_extrusion",
                feature_type="solidworks_extrude_boss",
                description="在基盘顶面二次拉伸中心凸台轴套",
                params={"depth": spec.get("boss_height", 30.0)},
                dependencies=["step_1_base_extrusion"]
            ),
            SchemeStep(
                step_id="step_3_center_bore",
                feature_type="solidworks_extrude_cut",
                description="贯通切除中心主轴承孔",
                params={"through_all": True},
                dependencies=["step_2_boss_extrusion"]
            ),
            SchemeStep(
                step_id="step_4_bolt_holes",
                feature_type="solidworks_extrude_cut",
                description="在基盘端面均布钻削安装螺栓孔",
                params={"through_all": True},
                dependencies=["step_1_base_extrusion"]
            ),
            SchemeStep(
                step_id="step_5_fillet",
                feature_type="solidworks_fillet",
                description="凸台根部添加 R3 应力释放过渡圆角",
                params={"radius": 3.0},
                dependencies=["step_2_boss_extrusion"]
            )
        ]
        return ModelingScheme(
            scheme_id="SCHEME_B_STACKED_EXTRUSION",
            scheme_name="方案 B：阶梯拉伸堆叠方案",
            manufacturing_intent=ManufacturingIntent.EXTRUSION_STACK,
            steps=steps,
            feature_count=len(steps),
            complexity_score=5.5,       # 特征节点较多，父子依赖多
            parametric_freedom=7.0,     # 易于单独修改基座与凸台
            rebuild_risk_score=4.0,     # 若基底变更，上层草图易漂移
            overall_score=0.0,
            selection_rationale="分步骤直观清晰，各段台阶独立可调，但特征树深度较深，草图基准面依赖相对脆弱。"
        )

    def _generate_subtractive_scheme(self, spec: Dict[str, Any]) -> ModelingScheme:
        """生成方案 C：毛坯减材切削方案"""
        steps = [
            SchemeStep(
                step_id="step_1_solid_block",
                feature_type="solidworks_extrude_boss",
                description="拉伸最大外包络圆柱或实体毛坯",
                params={"depth": 45.0}
            ),
            SchemeStep(
                step_id="step_2_pocket_cut",
                feature_type="solidworks_extrude_cut",
                description="端面大直径阶梯切削减除多余轮廓",
                params={"depth": 25.0},
                dependencies=["step_1_solid_block"]
            ),
            SchemeStep(
                step_id="step_3_bore_cut",
                feature_type="solidworks_extrude_cut",
                description="内孔中心穿透切削",
                params={"through_all": True},
                dependencies=["step_2_pocket_cut"]
            ),
            SchemeStep(
                step_id="step_4_flange_holes",
                feature_type="solidworks_extrude_cut",
                description="外圈螺栓孔切削",
                params={"through_all": True},
                dependencies=["step_1_solid_block"]
            )
        ]
        return ModelingScheme(
            scheme_id="SCHEME_C_SUBTRACTIVE",
            scheme_name="方案 C：毛坯减材切除方案",
            manufacturing_intent=ManufacturingIntent.SUBTRACTIVE_POCKET,
            steps=steps,
            feature_count=len(steps),
            complexity_score=6.8,       # 减法特征多，废料切削量大
            parametric_freedom=6.0,
            rebuild_risk_score=5.5,
            overall_score=0.0,
            selection_rationale="模拟重型铣削挖槽，通用性广，但切除冗余特征较多，模型计算负荷较大。"
        )

    def _rank_schemes(self, schemes: List[ModelingScheme]) -> List[ModelingScheme]:
        """加权评分与优选排序"""
        for s in schemes:
            # 综合公式：
            # Score = 40 * (1 - 复杂度/10) + 35 * (自由度/10) + 25 * (1 - 风险/10)
            score = (
                40.0 * (1.0 - s.complexity_score / 10.0) +
                35.0 * (s.parametric_freedom / 10.0) +
                25.0 * (1.0 - s.rebuild_risk_score / 10.0)
            )
            s.overall_score = max(0.0, min(100.0, score))

        # 按总分降序排序
        return sorted(schemes, key=lambda x: x.overall_score, reverse=True)
