# -*- coding: utf-8 -*-
"""
tests/phase4_cad_loop_test.py
验证阶段四：CAD 核心操作闭环实机验证（草图 -> 拉伸 -> 切除攻坚 -> 特征树验证 -> 双精度体积核对 -> 安全销毁闭环）。
严格遵守安全红线：在隔离沙箱中新建临时文档，测试结束后彻底关闭，绝不保存、不覆盖、不干扰用户既有工程文档。
"""

import math
import os
import sys
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENDOR_SCRIPTS = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"

for p in (str(VENDOR_SCRIPTS), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# 动态调整当前会话测试文档预算，以便在既有用户打开 20 个文档的前提下安全创建 1 个临时测试文档
os.environ["SW_MAX_DOCUMENTS"] = "35"

import sw_process
from sw_connect import (
    connect_solidworks,
    new_document,
    get_com_member,
    get_sta_worker,
    snapshot_open_documents,
    mm
)
from sw_part import (
    sketch,
    sketch_rectangle,
    extrude_boss,
    sketch_circle,
    extrude_cut,
    verify_feature_tree
)
from sw_measure import collect_mass_properties


class TestPhase4CADLoop(unittest.TestCase):
    """阶段四核心 CAD 操作实机闭环验证。"""

    @classmethod
    def setUpClass(cls):
        instances = sw_process.list_solidworks_instances()
        if not instances:
            raise unittest.SkipTest("未检测到运行中的 SolidWorks 实例，跳过物理实机验证")
        cls.sw, _ = connect_solidworks(wait_seconds=3, visible=True)
        if cls.sw is None:
            raise unittest.SkipTest("未能连接到 SolidWorks COM 实例")
        cls.worker = get_sta_worker()

    def test_full_cad_feature_chain_loop(self):
        """执行完整 CAD 特征操作链实机闭环测试。"""
        sw = self.sw
        worker = self.worker

        def run():
            # 1. 记录初始文档状态，确保最后恢复
            initial_titles = set(snapshot_open_documents(sw, strict=False))
            print(f"[测试启动] 当前用户文档总数: {len(initial_titles)}")

            # 2. 新建临时零件
            model = new_document(sw, "part")
            self.assertIsNotNone(model, "新建零件文档必须成功")
            test_title = get_com_member(model, "GetTitle")
            print(f"[阶段 1] 成功创建隔离测试零件: {test_title}")

            try:
                # 3. 绘制 50mm x 50mm 矩形草图并拉伸凸台 20mm
                with sketch(model, "前视基准面") as sk_ref:
                    sketch_rectangle(model, 0, 0, mm(50), mm(50))
                print(f"[阶段 2] 创建矩形草图完成: {sk_ref}")

                boss_feat = extrude_boss(model, sk_ref, mm(20))
                self.assertIsNotNone(boss_feat, "拉伸凸台特征生成必须成功")
                boss_name = boss_feat.Name
                print(f"[阶段 3] 实体凸台拉伸完成: {boss_name}")

                # 4. 特征树验证与初始体积复核
                tree_res1 = verify_feature_tree(model, boss_name)
                self.assertTrue(tree_res1["valid"], "凸台特征树必须有效无报错")
                self.assertTrue(tree_res1["target_found"])

                props1 = collect_mass_properties(model)
                vol1 = props1.get("volume_mm3", 0.0)  # 单位 mm^3
                # 理论体积: 50 * 50 * 20 mm^3 = 50000 mm^3
                expected_vol1 = 50.0 * 50.0 * 20.0
                print(f"[阶段 4] 凸台实测体积: {vol1:.4f} mm^3, 理论体积: {expected_vol1:.4f} mm^3")
                self.assertAlmostEqual(vol1, expected_vol1, places=1, msg="双精度体积与理论误差必须 <= 0.1 mm^3")

                # 5. 切除操作专项攻坚验证（在前视面上绘制 Φ20mm 圆并盲切 10mm）
                with sketch(model, "前视基准面") as sk_cut_ref:
                    sketch_circle(model, 0, 0, mm(10))
                print(f"[阶段 5] 绘制切除圆形草图完成: {sk_cut_ref}")

                cut_feat = extrude_cut(model, sk_cut_ref, mm(10), direction=True)
                self.assertIsNotNone(cut_feat, "自适应切除拉伸必须成功生成特征")
                cut_name = cut_feat.Name
                print(f"[阶段 6] 切除特征生成成功: {cut_name}")

                # 6. 切除后特征树与体积复核
                tree_res2 = verify_feature_tree(model, cut_name)
                self.assertTrue(tree_res2["valid"], "切除特征树必须无错误")

                props2 = collect_mass_properties(model)
                vol2 = props2.get("volume_mm3", 0.0)
                expected_cut_vol = math.pi * (10.0 ** 2) * 10.0
                expected_vol2 = expected_vol1 - expected_cut_vol
                print(f"[阶段 7] 切除后实测体积: {vol2:.4f} mm^3, 理论体积: {expected_vol2:.4f} mm^3")
                self.assertAlmostEqual(vol2, expected_vol2, places=1, msg="切除后体积双精度核对必须吻合")

                # 7. 特征树全量节点校验
                tree_res3 = verify_feature_tree(model)
                self.assertTrue(tree_res3["valid"], "全特征树最终结构必须健康")
                print(f"[阶段 8] 特征树全项校验通过，共 {tree_res3['feature_count']} 个节点")

            finally:
                # 8. 彻底安全清理与销毁测试文档，绝不残留
                try:
                    sw.CloseDoc(test_title)
                    print(f"[安全清理] 测试文档 {test_title} 已彻底关闭并销毁。")
                except Exception as close_err:
                    print(f"[清理告警] 关闭文档失败: {close_err}")

                final_titles = set(snapshot_open_documents(sw, strict=False))
                self.assertEqual(len(final_titles), len(initial_titles), "测试结束后打开文档总数必须严格守恒")
                self.assertNotIn(test_title, final_titles, "测试零件必须完全脱离 SolidWorks")
                print(f"[测试收尾] 用户文档总数严格守恒于 {len(final_titles)}，无任何副作用残留。")

        worker.execute(run, timeout=60)


if __name__ == "__main__":
    unittest.main()
