"""
第五阶段 S5-F 高级 AI CAD 协调调度器全链路集成测试
验证：
1. 从高阶设计需求到多方案比选、特征树优化与多维质量评估的端到端闭环；
2. 装配规划端到端联动；
3. 自动迭代修改与影响域分析端到端联动；
4. 报告输出规范性与指标满足度。
"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "docs", "stage5_advanced_ai_cad", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from advanced_ai_cad_coordinator import (
    AdvancedAicadCoordinator,
    AutonomousCadWorkflowResult
)


class TestAdvancedAicadCoordinator(unittest.TestCase):

    def setUp(self):
        self.coordinator = AdvancedAicadCoordinator()

    def test_end_to_end_design_and_evaluation(self):
        """测试自主设计与多维评价端到端全链路"""
        spec = {
            "part_type": "flange",
            "description": "设计高压管道连接法兰盘，需具备螺栓均布孔与密封环槽",
            "flange_thickness": 22.0
        }
        res = self.coordinator.run_autonomous_design_and_evaluation(
            workflow_id="WF-AUTOCAD-001",
            design_spec=spec
        )
        self.assertIsInstance(res, AutonomousCadWorkflowResult)
        self.assertEqual(res.overall_status, "SUCCESS")
        self.assertEqual(res.selected_scheme_id, "SCHEME_A_TURNING")
        self.assertGreaterEqual(res.optimized_steps_count, 3)
        self.assertGreaterEqual(res.quality_report.overall_quality_score, 85.0)
        self.assertTrue(res.quality_report.is_acceptable)
        self.assertIn("成功完成自主设计与核验", res.workflow_summary)

    def test_assembly_coordination(self):
        """测试装配体项目调度与规划"""
        parts = [
            {"part_name": "bearing_housing", "instance_id": "housing_1"},
            {"part_name": "roller_bearing", "instance_id": "bearing_1"}
        ]
        mates = [
            {"mate_id": "m1", "mate_type": "concentric", "comp_a": "housing_1", "comp_b": "bearing_1"}
        ]
        asm_plan = self.coordinator.plan_assembly_project("GearboxSubAsm", parts, mates)
        self.assertEqual(asm_plan.base_component_id, "housing_1")
        self.assertFalse(asm_plan.has_conflicts)
        self.assertEqual(len(asm_plan.assembly_sequence), 2)

    def test_incremental_iteration_coordination(self):
        """测试增量修改影响域推导与 Diff 调度"""
        feature_dag = [
            {"feature_id": "base", "depends_on": []},
            {"feature_id": "flange_cut", "depends_on": ["base"]}
        ]
        dim_graph = {"flange_thickness": []}
        param_map = {"flange_thickness": "base"}

        diff = self.coordinator.perform_incremental_iteration(
            feature_dag=feature_dag,
            dim_graph=dim_graph,
            target_param="flange_thickness",
            param_feature_map=param_map,
            old_val=20.0,
            new_val=25.0,
            geom_before={"volume": 100000.0, "surface_area": 15000.0},
            geom_after={"volume": 120000.0, "surface_area": 16500.0}
        )
        self.assertTrue(diff.success)
        self.assertTrue(diff.is_safe)
        self.assertEqual(diff.delta_volume, 20000.0)

    def test_low_quality_model_flagged(self):
        """测试低品质模型执行全流程时状态标记为 FAILED"""
        spec = {"part_type": "flange", "description": "低质量测试件"}
        # 传入严重偏差点
        bad_measured = {
            "volume": 80000.0, # 相对理论值 117809.72 偏差 >30%
            "body_count": 2,    # 存在非合并实体
            "min_wall_thickness": 0.5 # 极薄壁
        }
        res = self.coordinator.run_autonomous_design_and_evaluation(
            workflow_id="WF-AUTOCAD-BAD",
            design_spec=spec,
            simulated_measured_data=bad_measured
        )
        self.assertEqual(res.overall_status, "FAILED")
        self.assertFalse(res.quality_report.is_acceptable)
        self.assertGreater(len(res.quality_report.actionable_recommendations), 0)


if __name__ == "__main__":
    unittest.main()
