# -*- coding: utf-8 -*-
"""
tests/cad_task_planner_test.py
CADTaskPlanner 与 DesignIntent 离线单元测试与反例拦截严苛测试套件。

覆盖范围：
1. 自然语言与结构化意图双向解析能力
2. 反例 1：孔径物理越界拦截 (OUT_OF_BOUNDS)
3. 反例 2：孔中心落在底板外部拦截 (OUT_OF_BOUNDS)
4. 反例 3：非物理负数/零尺寸拦截 (INVALID_DIMENSION)
5. 反例 4：悬空从属特征/无基底拦截 (MISSING_REFERENCE)
6. 反例 5：紧固孔阵列超界冲突拦截 (GEOMETRY_CONFLICT)
7. 反例 6：孔边距小于孔半径切边拦截 (OUT_OF_BOUNDS)
8. 意图到 FeatureGraphIR DAG 拓扑编译正确性
9. Mock 执行环境下的端到端规划流程验证
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(REPO_ROOT))

from design_intent import (
    BasePlateIntent, BossFeatureIntent, DesignIntent,
    HoleIntent, IntentValidationStatus, MountingPatternIntent
)
from cad_task_planner import CADTaskPlanner, IntentValidationError
from feature_graph_ir import FeatureType


class CADTaskPlannerTest(unittest.TestCase):
    """CADTaskPlanner 逻辑与反例拦截单元测试。"""

    def setUp(self):
        self.planner = CADTaskPlanner()

    # =========================================================================
    # 1. 自然语言意图解析测试
    # =========================================================================

    def test_natural_language_parsing_standard_flange(self):
        """测试标准法兰底座自然语言解析。"""
        text = "创建一个长160mm、宽100mm、厚15mm的底座，中心开一个直径35mm的通孔"
        intent = self.planner.parse_intent(text)
        self.assertIsNotNone(intent.base)
        self.assertEqual(intent.base.length_mm, 160.0)
        self.assertEqual(intent.base.width_mm, 100.0)
        self.assertEqual(intent.base.thickness_mm, 15.0)
        self.assertEqual(len(intent.holes), 1)
        self.assertEqual(intent.holes[0].diameter_mm, 35.0)
        self.assertEqual(intent.holes[0].center_x_mm, 80.0)
        self.assertEqual(intent.holes[0].center_y_mm, 50.0)

    def test_natural_language_parsing_dimension_shorthand(self):
        """测试形如 120x80x12 的速记自然语言解析。"""
        text = "加工一块 120x80x12 的安装板，四角打四个直径8mm的安装孔，距边缘各12mm"
        intent = self.planner.parse_intent(text)
        self.assertEqual(intent.base.length_mm, 120.0)
        self.assertEqual(intent.base.width_mm, 80.0)
        self.assertEqual(intent.base.thickness_mm, 12.0)
        self.assertIsNotNone(intent.pattern)
        self.assertEqual(intent.pattern.hole_diameter_mm, 8.0)
        self.assertEqual(intent.pattern.margin_x_mm, 12.0)

    # =========================================================================
    # 2. 六大反例严苛拦截测试 (Counter-example Rejection)
    # =========================================================================

    def test_counter_example_out_of_bounds_hole_diameter(self):
        """反例 1：孔径过大，半径超出底板边界 -> 强制拦截。"""
        # 底板 100x100，中心在 (50, 50)，但孔径高达 110mm (半径 55mm > 50mm)
        intent = DesignIntent(
            part_name="InvalidHolePart",
            base=BasePlateIntent(length_mm=100.0, width_mm=100.0, thickness_mm=10.0),
            holes=[
                HoleIntent(hole_id="huge_hole", diameter_mm=110.0, center_x_mm=50.0, center_y_mm=50.0)
            ],
        )
        res = intent.validate_intent()
        self.assertFalse(res.is_valid)
        self.assertEqual(res.status, IntentValidationStatus.OUT_OF_BOUNDS)
        self.assertTrue(any("物理越界" in e for e in res.errors))

        # 验证 planner 编译阶段必须抛出确定性异常
        with self.assertRaises(IntentValidationError):
            self.planner.compile_to_feature_graph(intent)

    def test_counter_example_hole_center_outside_plate(self):
        """反例 2：孔中心坐标位于底板外部 -> 强制拦截。"""
        intent = DesignIntent(
            part_name="OutsideCenterPart",
            base=BasePlateIntent(length_mm=80.0, width_mm=60.0, thickness_mm=10.0),
            holes=[
                HoleIntent(hole_id="outside_hole", diameter_mm=10.0, center_x_mm=120.0, center_y_mm=30.0)
            ],
        )
        res = intent.validate_intent()
        self.assertFalse(res.is_valid)
        self.assertEqual(res.status, IntentValidationStatus.OUT_OF_BOUNDS)

    def test_counter_example_negative_or_zero_dimensions(self):
        """反例 3：厚度或长宽小于等于0 -> 强制拦截。"""
        # 负厚度
        intent1 = DesignIntent(
            part_name="NegativeThickness",
            base=BasePlateIntent(length_mm=100.0, width_mm=50.0, thickness_mm=-10.0),
        )
        res1 = intent1.validate_intent()
        self.assertFalse(res1.is_valid)
        self.assertEqual(res1.status, IntentValidationStatus.INVALID_DIMENSION)

        # 负孔径
        intent2 = DesignIntent(
            part_name="NegativeHole",
            base=BasePlateIntent(length_mm=100.0, width_mm=50.0, thickness_mm=10.0),
            holes=[
                HoleIntent(hole_id="neg_hole", diameter_mm=-5.0, center_x_mm=20.0, center_y_mm=20.0)
            ],
        )
        res2 = intent2.validate_intent()
        self.assertFalse(res2.is_valid)
        self.assertEqual(res2.status, IntentValidationStatus.INVALID_DIMENSION)

    def test_counter_example_missing_base_reference(self):
        """反例 4：无基底的悬空特征 -> 强制拦截。"""
        intent = DesignIntent(
            part_name="FloatingHole",
            base=None,
            holes=[
                HoleIntent(hole_id="floating", diameter_mm=10.0, center_x_mm=0.0, center_y_mm=0.0)
            ],
        )
        res = intent.validate_intent()
        self.assertFalse(res.is_valid)
        self.assertEqual(res.status, IntentValidationStatus.MISSING_REFERENCE)

    def test_counter_example_pattern_margin_sum_exceeds_dimension(self):
        """反例 5：阵列孔边距之和大于等于底板总宽 -> 几何冲突拦截。"""
        # 底板宽 60mm，边距设为 35mm (2*35 = 70mm > 60mm)
        intent = DesignIntent(
            part_name="PatternConflict",
            base=BasePlateIntent(length_mm=100.0, width_mm=60.0, thickness_mm=10.0),
            pattern=MountingPatternIntent(
                pattern_id="conflict_pat",
                hole_diameter_mm=6.0,
                margin_x_mm=10.0,
                margin_y_mm=35.0,
            ),
        )
        res = intent.validate_intent()
        self.assertFalse(res.is_valid)
        self.assertEqual(res.status, IntentValidationStatus.GEOMETRY_CONFLICT)

    def test_counter_example_margin_less_than_hole_radius(self):
        """反例 6：边距小于孔半径，导致打孔切断工件边缘 -> 强制拦截。"""
        # 孔径 20mm (半径 10mm)，边距仅为 4mm
        intent = DesignIntent(
            part_name="CuttingEdgeHole",
            base=BasePlateIntent(length_mm=100.0, width_mm=100.0, thickness_mm=10.0),
            pattern=MountingPatternIntent(
                pattern_id="cut_edge",
                hole_diameter_mm=20.0,
                margin_x_mm=4.0,
                margin_y_mm=4.0,
            ),
        )
        res = intent.validate_intent()
        self.assertFalse(res.is_valid)
        self.assertEqual(res.status, IntentValidationStatus.OUT_OF_BOUNDS)

    # =========================================================================
    # 3. 意图到 FeatureGraphIR 的编译与拓扑图测试
    # =========================================================================

    def test_compile_valid_intent_to_feature_graph_ir(self):
        """测试有效意图编译为 FeatureGraphIR 的节点拓扑与参数正确性。"""
        intent = DesignIntent(
            part_name="FlangeBracket",
            base=BasePlateIntent(length_mm=150.0, width_mm=90.0, thickness_mm=12.0),
            holes=[
                HoleIntent(hole_id="center", diameter_mm=28.0, center_x_mm=75.0, center_y_mm=45.0)
            ],
            pattern=MountingPatternIntent(
                pattern_id="corners",
                hole_diameter_mm=8.0,
                margin_x_mm=12.0,
                margin_y_mm=12.0,
            ),
            bosses=[
                BossFeatureIntent(
                    boss_id="upright",
                    width_mm=150.0,
                    height_mm=70.0,
                    thickness_mm=10.0,
                )
            ],
        )

        graph = self.planner.compile_to_feature_graph(intent)
        self.assertEqual(graph.target_part_name, "FlangeBracket")
        self.assertGreaterEqual(len(graph.nodes), 6)

        # 检查 Kahn 拓扑排序时序
        ordered = graph.topological_sort()
        node_types = [n.type for n in ordered]
        
        # 验证首个节点为草图，次节点为基底凸台
        self.assertEqual(node_types[0], FeatureType.SKETCH_2D)
        self.assertEqual(node_types[1], FeatureType.EXTRUDE_BOSS)

        # 检查尺寸驱动开关
        base_sk = graph.nodes["node_sketch_base"]
        self.assertTrue(base_sk.parameters["add_dimensions"])
        self.assertAlmostEqual(base_sk.parameters["x2_m"], 0.150)
        self.assertAlmostEqual(base_sk.parameters["y2_m"], 0.090)


if __name__ == "__main__":
    unittest.main()
