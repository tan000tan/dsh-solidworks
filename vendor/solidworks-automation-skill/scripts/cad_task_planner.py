# -*- coding: utf-8 -*-
"""
vendor/solidworks-automation-skill/scripts/cad_task_planner.py
Agent 自主任务规划器 (CAD Task Planner & Intent Compiler)

核心职责：
1. 自然语言与结构化规范解析：将用户/Agent 输入转译为高精度 DesignIntent；
2. 反向约束几何审查 (Counter-example Rejection)：在规划阶段拦截非法几何与反例；
3. 拓扑编译器 (Intent -> Feature Graph IR)：将业务意图确定性降阶编译为带驱动尺寸的 DAG；
4. 端到端实机执行桥接：衔接 CADGraphExecutor，实现从自然语言到真实实体建模的完整闭环。
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from .design_intent import (
        BasePlateIntent, BossFeatureIntent, DesignIntent,
        HoleIntent, IntentValidationResult, IntentValidationStatus, MountingPatternIntent
    )
    from .feature_graph_ir import FeatureGraphIR, FeatureNode, FeatureType
    from .cad_graph_executor import CADGraphExecutor, ExecutionResult
except ImportError:
    from design_intent import (
        BasePlateIntent, BossFeatureIntent, DesignIntent,
        HoleIntent, IntentValidationResult, IntentValidationStatus, MountingPatternIntent
    )
    from feature_graph_ir import FeatureGraphIR, FeatureNode, FeatureType
    from cad_graph_executor import CADGraphExecutor, ExecutionResult

logger = logging.getLogger("cad_task_planner")


class IntentValidationError(Exception):
    """当设计意图违反工程或几何边界时抛出。"""
    def __init__(self, message: str, result: IntentValidationResult):
        super().__init__(message)
        self.result = result


class CADTaskPlanner:
    """Agent 级自主 CAD 任务规划器与意图编译器。"""

    def __init__(self, executor: Optional[CADGraphExecutor] = None):
        self.executor = executor or CADGraphExecutor()

    # =========================================================================
    # 1. 自然语言与字典输入解析器
    # =========================================================================

    def parse_intent(self, user_input: Union[str, Dict[str, Any]]) -> DesignIntent:
        """
        将自然语言文本或 JSON 字典解析为强类型 DesignIntent。
        """
        if isinstance(user_input, dict):
            return DesignIntent.model_validate(user_input)

        text = str(user_input).strip()
        part_name = "PlannedPart"

        # 1. 提取底座板尺寸: 长、宽、厚
        # 支持: "长120mm、宽80mm、厚10mm" 或 "120x80x10" 或 "120*80*10"
        l_val, w_val, t_val = 100.0, 50.0, 10.0 # 默认基线

        dim_match = re.search(r"(\d+(?:\.\d+)?)\s*[xX*×]\s*(\d+(?:\.\d+)?)\s*[xX*×]\s*(\d+(?:\.\d+)?)", text)
        if dim_match:
            l_val = float(dim_match.group(1))
            w_val = float(dim_match.group(2))
            t_val = float(dim_match.group(3))
        else:
            m_l = re.search(r"长(?:度)?\s*[:：=]?\s*(\d+(?:\.\d+)?)\s*(?:mm|毫米)?", text)
            m_w = re.search(r"宽(?:度)?\s*[:：=]?\s*(\d+(?:\.\d+)?)\s*(?:mm|毫米)?", text)
            m_t = re.search(r"厚(?:度)?\s*[:：=]?\s*(\d+(?:\.\d+)?)\s*(?:mm|毫米)?", text)
            if m_l: l_val = float(m_l.group(1))
            if m_w: w_val = float(m_w.group(1))
            if m_t: t_val = float(m_t.group(1))

        base = BasePlateIntent(
            length_mm=l_val,
            width_mm=w_val,
            thickness_mm=t_val,
            plane="Top Plane",
            origin_corner=True,
        )

        holes: List[HoleIntent] = []
        pattern: Optional[MountingPatternIntent] = None
        bosses: List[BossFeatureIntent] = []

        # 2. 提取中央通孔 / 主轴孔
        # 例如: "中心开一个直径30mm的通孔" 或 "中央孔径25mm"
        m_center_hole = re.search(r"(?:中心|中央|中间).*?(?:孔径|直径|孔)?\s*[:：=]?\s*(\d+(?:\.\d+)?)\s*(?:mm|毫米)?", text)
        if m_center_hole:
            c_dia = float(m_center_hole.group(1))
            holes.append(
                HoleIntent(
                    hole_id="center_bore",
                    diameter_mm=c_dia,
                    center_x_mm=l_val / 2.0,
                    center_y_mm=w_val / 2.0,
                    is_through=True,
                )
            )

        # 3. 提取四角安装孔阵列
        # 例如: "四角打四个直径8mm的安装孔，距边缘各10mm" 或 "四角安装孔 8mm，边距12mm"
        if re.search(r"四角|4角|4个安装孔|四个安装孔", text):
            h_dia = 8.0
            margin_x = 10.0
            margin_y = 10.0
            m_hd = re.search(r"(?:安装孔|孔径|直径)\s*[:：=]?\s*(\d+(?:\.\d+)?)\s*(?:mm|毫米)?", text)
            m_mg = re.search(r"(?:距边缘|边距)(?:各)?\s*[:：=]?\s*(\d+(?:\.\d+)?)\s*(?:mm|毫米)?", text)
            if m_hd and not m_center_hole:
                h_dia = float(m_hd.group(1))
            elif m_hd and m_center_hole:
                # 寻找第二个直径匹配
                all_dias = re.findall(r"(?:直径|孔径)\s*[:：=]?\s*(\d+(?:\.\d+)?)", text)
                if len(all_dias) > 1:
                    h_dia = float(all_dias[1])
            if m_mg:
                margin_x = float(m_mg.group(1))
                margin_y = margin_x

            pattern = MountingPatternIntent(
                pattern_id="four_corner_holes",
                hole_diameter_mm=h_dia,
                margin_x_mm=margin_x,
                margin_y_mm=margin_y,
                count_type="four_corners",
            )

        # 4. 提取双对称孔 (例如电机支架或轴承安装孔)
        # 例如: "双对称孔 间距 100mm 直径 12mm"
        m_pitch = re.search(r"(?:间距|中心距|孔距)\s*[:：=]?\s*(\d+(?:\.\d+)?)\s*(?:mm|毫米)?", text)
        if m_pitch and pattern is None:
            pitch_x = float(m_pitch.group(1))
            h_dia = 12.0
            m_hd = re.search(r"(?:孔径|直径)\s*[:：=]?\s*(\d+(?:\.\d+)?)\s*(?:mm|毫米)?", text)
            if m_hd:
                h_dia = float(m_hd.group(1))
            margin_x = (l_val - pitch_x) / 2.0
            pattern = MountingPatternIntent(
                pattern_id="dual_symmetric_holes",
                hole_diameter_mm=h_dia,
                margin_x_mm=max(1.0, margin_x),
                margin_y_mm=w_val / 2.0,
                count_type="dual_symmetric",
                pitch_x_mm=pitch_x,
            )

        # 5. 提取垂直支撑板 / 凸台
        # 例如: "垂直支撑板高 80mm，厚 12mm"
        m_upright = re.search(r"(?:垂直板|立板|支撑板|立柱).*?高(?:度)?\s*[:：=]?\s*(\d+(?:\.\d+)?)\s*(?:mm|毫米)?.*?厚(?:度)?\s*[:：=]?\s*(\d+(?:\.\d+)?)", text)
        if m_upright:
            u_h = float(m_upright.group(1))
            u_t = float(m_upright.group(2))
            bosses.append(
                BossFeatureIntent(
                    boss_id="upright_wall",
                    shape="rectangle",
                    width_mm=l_val,
                    height_mm=u_h,
                    thickness_mm=u_t,
                    plane="Front Plane",
                )
            )

        return DesignIntent(
            part_name=part_name,
            base=base,
            holes=holes,
            pattern=pattern,
            bosses=bosses,
            parameters={
                "base_length": l_val,
                "base_width": w_val,
                "base_thickness": t_val,
            },
        )

    # =========================================================================
    # 2. 意图到 FeatureGraphIR 的拓扑编译 (Compile Intent -> DAG)
    # =========================================================================

    def compile_to_feature_graph(self, intent: DesignIntent) -> FeatureGraphIR:
        """
        将经过校验的设计意图降阶编译为可执行的 FeatureGraphIR 有向无环图。
        自动创建参数化 DisplayDimension 标注，保证生成的模型具备原位修改能力。
        """
        # 1. 严格执行反向几何审查
        val_res = intent.validate_intent()
        if not val_res.is_valid:
            error_msg = "; ".join(val_res.errors)
            logger.error(f"[CADTaskPlanner] 意图审查未通过，拒绝编译: {error_msg}")
            raise IntentValidationError(f"设计意图几何审查未通过: {error_msg}", val_res)

        graph_id = f"graph_{intent.part_name.lower()}"
        graph = FeatureGraphIR(
            graph_id=graph_id,
            target_part_name=intent.part_name,
        )

        base = intent.base
        assert base is not None

        # 2. 节点 1: 底座板草图 (BaseSketch) - Top Plane
        sk_base_id = "node_sketch_base"
        sk_base_name = "BaseSketch"
        graph.add_node(
            FeatureNode(
                id=sk_base_id,
                type=FeatureType.SKETCH_2D,
                name=sk_base_name,
                parameters={
                    "plane": base.plane,
                    "shape": "corner_rectangle",
                    "x1_m": 0.0,
                    "y1_m": 0.0,
                    "x2_m": base.length_mm / 1000.0,
                    "y2_m": base.width_mm / 1000.0,
                    "add_dimensions": True,
                },
                depends_on=[],
            )
        )

        # 3. 节点 2: 底座板拉伸凸台 (BaseBoss)
        boss_base_id = "node_boss_base"
        boss_base_name = "BaseBoss"
        graph.add_node(
            FeatureNode(
                id=boss_base_id,
                type=FeatureType.EXTRUDE_BOSS,
                name=boss_base_name,
                parameters={
                    "depth_m": base.thickness_mm / 1000.0,
                    "direction": True,
                    "merge": True,
                },
                depends_on=[sk_base_id],
            )
        )

        last_solid_node_id = boss_base_id

        # 4. 节点 3: 处理离散通孔 (例如中心孔)
        for idx, hole in enumerate(intent.holes):
            sk_hole_id = f"node_sketch_hole_{idx+1}"
            sk_hole_name = f"HoleSketch_{idx+1}"
            graph.add_node(
                FeatureNode(
                    id=sk_hole_id,
                    type=FeatureType.SKETCH_2D,
                    name=sk_hole_name,
                    parameters={
                        "plane": base.plane,
                        "shape": "circle",
                        "cx_m": hole.center_x_mm / 1000.0,
                        "cy_m": hole.center_y_mm / 1000.0,
                        "radius_m": (hole.diameter_mm / 2.0) / 1000.0,
                        "add_dimensions": True,
                    },
                    depends_on=[last_solid_node_id],
                )
            )

            cut_depth = hole.depth_mm if (not hole.is_through and hole.depth_mm) else base.thickness_mm
            cut_hole_id = f"node_cut_hole_{idx+1}"
            cut_hole_name = f"HoleCut_{idx+1}"
            graph.add_node(
                FeatureNode(
                    id=cut_hole_id,
                    type=FeatureType.EXTRUDE_CUT,
                    name=cut_hole_name,
                    parameters={
                        "depth_m": cut_depth / 1000.0,
                        "direction": False,
                    },
                    depends_on=[sk_hole_id],
                )
            )
            last_solid_node_id = cut_hole_id

        # 5. 节点 4: 处理紧固孔阵列
        if intent.pattern is not None:
            pat = intent.pattern
            sk_pat_id = "node_sketch_mount_pattern"
            sk_pat_name = "MountPatternSketch"

            # 构建阵列草图节点
            # 支持四角孔和双孔
            if pat.count_type == "four_corners":
                # 我们通过一个综合切除节点实现，草图先绘制第一个基准孔
                x0 = pat.margin_x_mm
                y0 = pat.margin_y_mm
                graph.add_node(
                    FeatureNode(
                        id=sk_pat_id,
                        type=FeatureType.SKETCH_2D,
                        name=sk_pat_name,
                        parameters={
                            "plane": base.plane,
                            "shape": "circle",
                            "cx_m": x0 / 1000.0,
                            "cy_m": y0 / 1000.0,
                            "radius_m": (pat.hole_diameter_mm / 2.0) / 1000.0,
                            "add_dimensions": True,
                        },
                        depends_on=[last_solid_node_id],
                    )
                )
            else: # dual_symmetric
                x0 = pat.margin_x_mm
                y0 = pat.margin_y_mm
                graph.add_node(
                    FeatureNode(
                        id=sk_pat_id,
                        type=FeatureType.SKETCH_2D,
                        name=sk_pat_name,
                        parameters={
                            "plane": base.plane,
                            "shape": "circle",
                            "cx_m": x0 / 1000.0,
                            "cy_m": y0 / 1000.0,
                            "radius_m": (pat.hole_diameter_mm / 2.0) / 1000.0,
                            "add_dimensions": True,
                        },
                        depends_on=[last_solid_node_id],
                    )
                )

            cut_pat_id = "node_cut_mount_pattern"
            cut_pat_name = "MountPatternCut"
            graph.add_node(
                FeatureNode(
                    id=cut_pat_id,
                    type=FeatureType.EXTRUDE_CUT,
                    name=cut_pat_name,
                    parameters={
                        "depth_m": base.thickness_mm / 1000.0,
                        "direction": False,
                    },
                    depends_on=[sk_pat_id],
                )
            )
            last_solid_node_id = cut_pat_id

        # 6. 节点 5: 处理附加立柱/支撑板
        for b_idx, boss in enumerate(intent.bosses):
            sk_boss_id = f"node_sketch_boss_{b_idx+1}"
            sk_boss_name = f"UprightSketch_{b_idx+1}"
            graph.add_node(
                FeatureNode(
                    id=sk_boss_id,
                    type=FeatureType.SKETCH_2D,
                    name=sk_boss_name,
                    parameters={
                        "plane": boss.plane,
                        "shape": "corner_rectangle",
                        "x1_m": 0.0,
                        "y1_m": base.thickness_mm / 1000.0,
                        "x2_m": boss.width_mm / 1000.0,
                        "y2_m": (base.thickness_mm + boss.height_mm) / 1000.0,
                        "add_dimensions": True,
                    },
                    depends_on=[last_solid_node_id],
                )
            )

            boss_ext_id = f"node_ext_boss_{b_idx+1}"
            boss_ext_name = f"UprightBoss_{b_idx+1}"
            graph.add_node(
                FeatureNode(
                    id=boss_ext_id,
                    type=FeatureType.EXTRUDE_BOSS,
                    name=boss_ext_name,
                    parameters={
                        "depth_m": boss.thickness_mm / 1000.0,
                        "direction": True,
                        "merge": True,
                    },
                    depends_on=[sk_boss_id],
                )
            )
            last_solid_node_id = boss_ext_id

        # 7. 静态拓扑序强校验，确保编译输出的 DAG 无死锁
        graph.topological_sort()
        return graph

    # =========================================================================
    # 3. 规划与实机端到端执行流水线
    # =========================================================================

    def plan_and_execute(
        self,
        user_input: Union[str, Dict[str, Any]],
        output_part_path: Optional[str] = None,
        model_doc: Optional[Any] = None,
        collect_metrics: bool = True,
        close_on_finish: bool = False,
    ) -> Tuple[ExecutionResult, DesignIntent]:
        """
        端到端全自动流水线：
        自然语言/意图 -> 解析 -> 几何反例拦截 -> 编译成 FeatureGraphIR -> 驱动 SolidWorks 执行。
        若触发反例拦截，直接抛出 IntentValidationError，绝不触碰任何物理 CAD 文件。
        """
        # 1. 解析意图
        intent = self.parse_intent(user_input)

        # 2. 编译并校验（若非法在此刻抛出异常拦截）
        ir_graph = self.compile_to_feature_graph(intent)

        # 3. 分发给底层 CADGraphExecutor 执行
        result = self.executor.execute(
            graph_input=ir_graph,
            output_part_path=output_part_path,
            model_doc=model_doc,
            collect_metrics=collect_metrics,
            close_on_finish=close_on_finish,
        )

        return result, intent
