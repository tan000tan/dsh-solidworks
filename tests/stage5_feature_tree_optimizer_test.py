"""
第五阶段 S5-B 复杂特征树规划与优化器单元测试
验证：
1. 终饰特征（圆角/倒角）能够智能后置重排；
2. 循环依赖能够被精确检测并抛出专有异常；
3. 破损的 mirror_feature 特征能够被自动拦截或重构替代；
4. 调度结果严格满足拓扑序前提。
"""
import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "docs", "stage5_advanced_ai_cad", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from complex_feature_tree_optimizer import (
    ComplexFeatureTreeOptimizer,
    CyclicDependencyDetectedError,
    BlockedFeatureError
)


class TestComplexFeatureTreeOptimizer(unittest.TestCase):

    def setUp(self):
        self.optimizer = ComplexFeatureTreeOptimizer(auto_bypass_blocked=True)

    def test_finishing_late_scheduling(self):
        """测试倒角/圆角终饰特征后置重排"""
        # 输入一个倒角被错误放在切除前面的无序依赖图
        raw_nodes = [
            {"feature_id": "feat_1_base", "feature_type": "solidworks_extrude_boss", "depends_on": []},
            {"feature_id": "feat_2_fillet", "feature_type": "solidworks_fillet", "depends_on": ["feat_1_base"]},
            {"feature_id": "feat_3_cut", "feature_type": "solidworks_extrude_cut", "depends_on": ["feat_1_base"]},
            {"feature_id": "feat_4_chamfer", "feature_type": "solidworks_chamfer", "depends_on": ["feat_3_cut"]},
        ]
        optimized = self.optimizer.optimize_tree(raw_nodes)
        order = [n["feature_id"] for n in optimized]

        # 预期：feat_3_cut 应该先于 feat_2_fillet 被调度（切削先于倒圆角）
        cut_idx = order.index("feat_3_cut")
        fillet_idx = order.index("feat_2_fillet")
        self.assertLess(cut_idx, fillet_idx, "主要切削特征应优先于终饰倒角特征调度")

        # 验证基础父子依赖仍然严格满足
        self.assertLess(order.index("feat_1_base"), order.index("feat_3_cut"))
        self.assertLess(order.index("feat_3_cut"), order.index("feat_4_chamfer"))

    def test_cyclic_dependency_rejection(self):
        """测试循环死锁依赖检测"""
        cyclic_nodes = [
            {"feature_id": "A", "feature_type": "extrude", "depends_on": ["C"]},
            {"feature_id": "B", "feature_type": "extrude", "depends_on": ["A"]},
            {"feature_id": "C", "feature_type": "extrude", "depends_on": ["B"]},
        ]
        with self.assertRaises(CyclicDependencyDetectedError):
            self.optimizer.optimize_tree(cyclic_nodes)

    def test_mirror_feature_bypass_and_refactor(self):
        """测试缺陷特征 mirror_feature 自动重构替代 (DEF-11 防护)"""
        raw_nodes = [
            {"feature_id": "boss1", "feature_type": "solidworks_extrude_boss", "depends_on": []},
            {"feature_id": "mirror1", "feature_type": "solidworks_mirror_feature", "depends_on": ["boss1"]}
        ]
        optimized = self.optimizer.optimize_tree(raw_nodes)
        self.assertEqual(len(optimized), 2)
        # 验证 mirror_feature 被改写为对称拉伸实体
        self.assertEqual(optimized[1]["feature_type"], "solidworks_extrude_boss")
        self.assertTrue(optimized[1]["params"].get("symmetric_mode"))
        self.assertIn("[重构替代]", optimized[1]["description"])

    def test_mirror_feature_hard_blocking(self):
        """测试在关闭自动重构时抛出 BlockedFeatureError"""
        strict_optimizer = ComplexFeatureTreeOptimizer(auto_bypass_blocked=False)
        raw_nodes = [
            {"feature_id": "m1", "feature_type": "solidworks_mirror_feature", "depends_on": []}
        ]
        with self.assertRaises(BlockedFeatureError):
            strict_optimizer.optimize_tree(raw_nodes)

    def test_complex_multi_level_dag(self):
        """测试 6 级复杂特征拓扑时序确定性"""
        nodes = [
            {"feature_id": "F1", "feature_type": "extrude", "depends_on": []},
            {"feature_id": "F2", "feature_type": "extrude", "depends_on": ["F1"]},
            {"feature_id": "F3", "feature_type": "cut", "depends_on": ["F2"]},
            {"feature_id": "F4", "feature_type": "fillet", "depends_on": ["F3"]},
            {"feature_id": "F5", "feature_type": "cut", "depends_on": ["F1"]},
            {"feature_id": "F6", "feature_type": "chamfer", "depends_on": ["F5"]},
        ]
        optimized = self.optimizer.optimize_tree(nodes)
        self.assertEqual(len(optimized), 6)
        order = [n["feature_id"] for n in optimized]

        # 检查所有节点的父节点都在其前面出现
        for n in optimized:
            for dep in n.get("depends_on", []):
                self.assertLess(order.index(dep), order.index(n["feature_id"]))


if __name__ == "__main__":
    unittest.main()
