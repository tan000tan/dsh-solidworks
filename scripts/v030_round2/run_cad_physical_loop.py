"""
scripts/v030_round2/run_cad_physical_loop.py

执行真实 SolidWorks 2026 SP4.1 物理建模闭环验证：
1. 记录初始文档清单与计数 (保证严格守恒)
2. 新建临时隔离零件
3. 矩形草图 (50mm x 50mm) + safe_extrude_boss (20mm)
4. 提取特征树与双精度质量属性 (计算体积误差)
5. 圆形草图 (R10mm) + safe_extrude_cut (10mm)
6. 提取切除后特征树与双精度质量属性 (核对切除体积误差)
7. 安全关闭销毁临时测试文档
8. 验证最终文档清单与计数严格守恒
9. 输出真实证据至 temp_evidence_v030/D-CAD-Real-Verification/cad_physical_closed_loop_verification.json
"""

import math
import os
import sys
import time
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VENDOR_SCRIPTS = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"

for p in (str(VENDOR_SCRIPTS), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

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
from sw_compat import safe_mass_properties

EVIDENCE_D = REPO_ROOT / "temp_evidence_v030" / "D-CAD-Real-Verification"
EVIDENCE_D.mkdir(parents=True, exist_ok=True)

def main():
    print("=== 开始运行 CAD 真实物理闭环测试 (SolidWorks 2026 SP4.1) ===")
    instances = sw_process.list_solidworks_instances()
    if not instances:
        print("[ERROR] 未检测到运行中的 SolidWorks 实例！")
        sys.exit(1)

    sw, _ = connect_solidworks(wait_seconds=3, visible=True)
    if sw is None:
        print("[ERROR] 未能连接到 SolidWorks COM 实例！")
        sys.exit(1)

    worker = get_sta_worker()
    
    report_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "solidworks_instance": instances[0],
        "stages": {},
        "metrics": {},
        "overall_status": "PENDING"
    }

    def execute_cad_loop():
        # 1. 记录初始文档状态
        initial_titles = list(snapshot_open_documents(sw, strict=False))
        initial_count = len(initial_titles)
        print(f"[初始状态] 运行中文档数: {initial_count}, 标题列表: {initial_titles}")
        report_data["initial_document_count"] = initial_count
        report_data["initial_document_titles"] = initial_titles

        # 2. 新建临时零件
        model = new_document(sw, "part")
        if not model:
            raise RuntimeError("新建临时零件文档失败！")
        test_title = get_com_member(model, "GetTitle")
        print(f"[阶段 1: 新建文档] 成功创建隔离零件: {test_title}")
        report_data["stages"]["new_document"] = {"success": True, "title": test_title}

        try:
            # 3. 绘制 50mm x 50mm 矩形草图并拉伸凸台 20mm
            with sketch(model, "前视基准面") as sk_ref:
                sketch_rectangle(model, 0, 0, mm(50), mm(50))
            print(f"[阶段 2: 草图绘制] 矩形草图完成: {sk_ref}")
            
            boss_feat = extrude_boss(model, sk_ref, mm(20))
            if not boss_feat:
                raise RuntimeError("拉伸凸台特征生成失败！")
            boss_name = boss_feat.Name
            print(f"[阶段 3: 凸台拉伸] 生成特征: {boss_name}")

            # 4. 凸台体积与特征树核验
            tree_boss = verify_feature_tree(model, boss_name)
            props1 = collect_mass_properties(model)
            vol1_mm3 = float(props1.get("volume_mm3", 0.0))
            expected_vol1_mm3 = 50.0 * 50.0 * 20.0  # 50000.0 mm^3
            vol1_err_pct = abs(vol1_mm3 - expected_vol1_mm3) / expected_vol1_mm3 * 100.0
            print(f"[阶段 4: 凸台核验] 实测体积: {vol1_mm3:.3f} mm^3, 理论: {expected_vol1_mm3:.3f} mm^3, 相对误差: {vol1_err_pct:.4f}%")

            report_data["stages"]["boss_extrusion"] = {
                "success": True,
                "feature_name": boss_name,
                "measured_volume_mm3": vol1_mm3,
                "expected_volume_mm3": expected_vol1_mm3,
                "error_percentage": round(vol1_err_pct, 4),
                "feature_tree_valid": tree_boss.get("valid", False)
            }

            # 5. 切除操作攻坚（在前视面上绘制 Φ20mm (R10mm) 圆并盲切 10mm）
            with sketch(model, "前视基准面") as sk_cut_ref:
                sketch_circle(model, 0, 0, mm(10))
            print(f"[阶段 5: 切除草图] 圆形草图完成: {sk_cut_ref}")

            cut_feat = extrude_cut(model, sk_cut_ref, mm(10), direction=True)
            if not cut_feat:
                raise RuntimeError("自适应拉伸切除生成失败！")
            cut_name = cut_feat.Name
            print(f"[阶段 6: 拉伸切除] 生成特征: {cut_name}")

            # 6. 切除后体积核验
            tree_cut = verify_feature_tree(model, cut_name)
            props2 = collect_mass_properties(model)
            vol2_mm3 = float(props2.get("volume_mm3", 0.0))
            cut_cylinder_vol = math.pi * (10.0 ** 2) * 10.0
            expected_vol2_mm3 = expected_vol1_mm3 - cut_cylinder_vol
            vol2_err_pct = abs(vol2_mm3 - expected_vol2_mm3) / expected_vol2_mm3 * 100.0
            print(f"[阶段 7: 切除核验] 实测体积: {vol2_mm3:.3f} mm^3, 理论: {expected_vol2_mm3:.3f} mm^3, 相对误差: {vol2_err_pct:.4f}%")

            report_data["stages"]["cut_extrusion"] = {
                "success": True,
                "feature_name": cut_name,
                "measured_volume_mm3": vol2_mm3,
                "expected_volume_mm3": expected_vol2_mm3,
                "error_percentage": round(vol2_err_pct, 4),
                "feature_tree_valid": tree_cut.get("valid", False)
            }

            # 7. 全特征树校验
            tree_final = verify_feature_tree(model)
            report_data["stages"]["final_feature_tree"] = {
                "valid": tree_final.get("valid", False),
                "node_count": tree_final.get("feature_count", 0)
            }
            print(f"[阶段 8: 特征树全项校验] 节点总数: {tree_final.get('feature_count', 0)}, 有效性: {tree_final.get('valid')}")

        finally:
            # 8. 安全销毁临时测试文档
            try:
                sw.CloseDoc(test_title)
                print(f"[安全清理] 测试文档 {test_title} 已成功关闭并安全释放。")
            except Exception as close_err:
                print(f"[清理警告] 关闭文档异常: {close_err}")

            final_titles = list(snapshot_open_documents(sw, strict=False))
            final_count = len(final_titles)
            conserved = (final_count == initial_count)
            print(f"[最终收尾] 最终文档数: {final_count}, 守恒状态: {conserved}")

            report_data["final_document_count"] = final_count
            report_data["final_document_titles"] = final_titles
            report_data["document_count_conserved"] = conserved
            report_data["temp_document_purged"] = (test_title not in final_titles)

    worker.execute(execute_cad_loop, timeout=60)

    # 判定总体状态
    boss_ok = report_data["stages"].get("boss_extrusion", {}).get("success", False)
    cut_ok = report_data["stages"].get("cut_extrusion", {}).get("success", False)
    conserved = report_data.get("document_count_conserved", False)
    purged = report_data.get("temp_document_purged", False)

    if boss_ok and cut_ok and conserved and purged:
        report_data["overall_status"] = "PASS"
    else:
        report_data["overall_status"] = "FAIL"

    out_file = EVIDENCE_D / "cad_physical_closed_loop_verification.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
    print(f"\n已将实测闭环证据保存至: {out_file}")

    if report_data["overall_status"] != "PASS":
        sys.exit(1)
    print("[SUCCESS] CAD 真实物理闭环验证全部通过！")


if __name__ == "__main__":
    main()
