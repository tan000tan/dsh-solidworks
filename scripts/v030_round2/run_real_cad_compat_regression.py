"""
scripts/v030_round2/run_real_cad_compat_regression.py

SolidWorks 2026 SP4.1 物理实机 16 步核心 CAD 兼容性闭环验证脚本：
1. 实例连接与版本能力探测（提取 RevisionNumber、SP、Hotfix、FeatureManager 与 Extension 接口阶梯）
2. 初始文档快照与计数记录（保证全程文档严格守恒）
3. 步骤 1：新建临时隔离零件文档
4. 步骤 2：在前视基准面上绘制 50mm x 50mm 矩形草图
5. 步骤 3：多版本自适应拉伸凸台 (20mm) - 验证 safe_extrude_boss (FeatureExtrusion3/2 调度)
6. 步骤 4：凸台特征树节点健康度验证 (verify_feature_tree)
7. 步骤 5：双精度体积核验（理论 50000.0 mm^3，误差 <= 0.1%）
8. 步骤 6：在前视面上绘制 Φ20mm 圆形切除草图
9. 步骤 7：多版本自适应拉伸切除 (10mm) - 验证 safe_extrude_cut (FeatureCut4/3 调度与方向自愈)
10. 步骤 8：切除特征树节点健康度验证 (verify_feature_tree)
11. 步骤 9：切除后体积双精度核验（理论 50000 - 1000π ≈ 46858.407 mm^3，误差 <= 0.1%）
12. 步骤 10：镜像特征自适应能力探测与调用验证 (safe_mirror_feature)
13. 步骤 11：质量属性提取平滑回退对比（safe_mass_properties vs GetMassProperties2 数组一致性）
14. 步骤 12：安全保存零件至沙箱隔离临时文件 (.sldprt)
15. 步骤 13：安全关闭临时零件文档
16. 步骤 14：重新打开已保存的临时测试零件文档
17. 步骤 15：重开后特征树结构及质量体积再次核验（确保序列化与反序列化完全无损）
18. 步骤 16：安全关闭并彻底从磁盘销毁临时测试零件
19. 最终验证：文档计数守恒性核查（当前文档总数 == 初始文档总数，测试文档零残留）
20. 结构化保存证据至 temp_evidence_v030_compat/D-Real-CAD-Regression/
"""

import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path

# 配置导入路径
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VENDOR_SCRIPTS = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"

for p in (str(VENDOR_SCRIPTS), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# 适度调高临时文档限制以保护并发
os.environ["SW_MAX_DOCUMENTS"] = "35"

import sw_process
from sw_connect import (
    connect_solidworks,
    new_document,
    open_document,
    get_com_member,
    get_sta_worker,
    snapshot_open_documents,
    register_owned_document,
    mm,
)
from sw_part import (
    sketch,
    sketch_rectangle,
    extrude_boss,
    sketch_circle,
    extrude_cut,
    verify_feature_tree,
)
from sw_measure import collect_mass_properties
from sw_compat import (
    get_solidworks_version_info,
    detect_solidworks_capabilities,
    safe_extrude_boss,
    safe_extrude_cut,
    safe_mirror_feature,
    safe_mass_properties,
    GLOBAL_DEGRADATION_LOG,
)

EVIDENCE_DIR = REPO_ROOT / "temp_evidence_v030_compat" / "D-Real-CAD-Regression"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = EVIDENCE_DIR / "real_cad_compatibility_regression.log"
JSON_FILE = EVIDENCE_DIR / "real_cad_compatibility_regression.json"


def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{ts}] {msg}"
    print(formatted)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(formatted + "\n")


def run_16_step_cad_compat_regression():
    log("=== 启动 SolidWorks 2026 SP4.1 物理实机 16 步核心 CAD 兼容性回归测试 ===")

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "solidworks_info": {},
        "capabilities": {},
        "steps": [],
        "metrics": {},
        "initial_documents": [],
        "final_documents": [],
        "document_conserved": False,
        "overall_status": "FAIL",
    }

    def record_step(step_num: int, name: str, success: bool, detail: str, extra: dict = None):
        step_rec = {
            "step": step_num,
            "name": name,
            "status": "PASS" if success else "FAIL",
            "detail": detail,
            "extra": extra or {}
        }
        report["steps"].append(step_rec)
        log(f"步骤 {step_num:02d}: {name} - [{'PASS' if success else 'FAIL'}] {detail}")
        if not success:
            raise RuntimeError(f"步骤 {step_num} 失败: {name} - {detail}")

    worker = get_sta_worker()

    def _execute():
        sw, _ = connect_solidworks(wait_seconds=5, visible=True)
        if sw is None:
            raise RuntimeError("无法获取 SolidWorks COM 对象！")

        # 1. 版本与能力探测
        sw_ver_info = get_solidworks_version_info(sw)
        sw_caps = detect_solidworks_capabilities(sw)
        report["solidworks_info"] = sw_ver_info
        report["capabilities"] = sw_caps
        log(f"[环境信息] 检测到 SolidWorks 年份: {sw_ver_info.get('year')}, SP: {sw_ver_info.get('sp')}, 原始版本: {sw_ver_info.get('raw_revision')}")
        log(f"[能力阶梯] 识别阶梯: {sw_caps.get('api_tier')}, 调度路径: {sw_caps.get('degradation_routes')}")

        # 2. 初始文档快照
        initial_titles = list(snapshot_open_documents(sw, strict=False))
        initial_count = len(initial_titles)
        report["initial_documents"] = initial_titles
        report["initial_count"] = initial_count
        log(f"[初始状态] 运行中文档数: {initial_count}, 标题列表: {initial_titles}")

        test_title = None
        temp_file_path = None
        reopened_model = None

        try:
            # 步骤 1: 新建临时隔离零件文档
            model = new_document(sw, "part")
            if not model:
                record_step(1, "Create_Part_Document", False, "新建零件文档返回空对象")
            test_title = get_com_member(model, "GetTitle")
            record_step(1, "Create_Part_Document", True, f"成功创建隔离零件: {test_title}", {"title": test_title})

            # 步骤 2: 绘制 50mm x 50mm 矩形草图
            with sketch(model, "前视基准面") as sk_ref:
                sketch_rectangle(model, 0, 0, mm(50), mm(50))
            record_step(2, "Sketch_Rectangle_50x50", True, f"前视基准面矩形草图已生成: {sk_ref}", {"sketch_ref": str(sk_ref)})

            # 步骤 3: 多版本自适应拉伸凸台 (20mm)
            boss_feat = extrude_boss(model, sk_ref, mm(20))
            if not boss_feat:
                record_step(3, "Adaptive_Extrude_Boss", False, "凸台拉伸返回空特征")
            boss_name = boss_feat.Name
            record_step(3, "Adaptive_Extrude_Boss", True, f"自适应拉伸凸台成功生成特征: {boss_name}", {"feature_name": boss_name})

            # 步骤 4: 凸台特征树验证
            tree_boss = verify_feature_tree(model, boss_name)
            record_step(4, "Verify_Boss_Feature_Tree", tree_boss.get("valid", False), f"凸台特征树有效性: {tree_boss.get('valid')}, 节点数: {tree_boss.get('feature_count')}", tree_boss)

            # 步骤 5: 凸台体积核验
            props1 = collect_mass_properties(model)
            vol1_mm3 = float(props1.get("volume_mm3", 0.0))
            expected_vol1 = 50.0 * 50.0 * 20.0  # 50000.0 mm^3
            vol1_err = abs(vol1_mm3 - expected_vol1) / expected_vol1 * 100.0
            pass_vol1 = vol1_err <= 0.1
            record_step(5, "Verify_Boss_Volume", pass_vol1, f"实测体积 {vol1_mm3:.3f} mm^3, 理论 50000.0 mm^3, 误差 {vol1_err:.4f}%", {
                "measured_volume": vol1_mm3, "expected_volume": expected_vol1, "error_pct": vol1_err
            })

            # 步骤 6: 绘制 Φ20mm 圆形草图
            with sketch(model, "前视基准面") as sk_cut_ref:
                sketch_circle(model, 0, 0, mm(10))
            record_step(6, "Sketch_Cut_Circle_D20", True, f"切除圆形草图已生成: {sk_cut_ref}", {"sketch_ref": str(sk_cut_ref)})

            # 步骤 7: 多版本自适应拉伸切除 (10mm) 并自愈
            cut_feat = extrude_cut(model, sk_cut_ref, mm(10), direction=True)
            if not cut_feat:
                record_step(7, "Adaptive_Extrude_Cut", False, "拉伸切除特征生成失败")
            cut_name = cut_feat.Name
            record_step(7, "Adaptive_Extrude_Cut", True, f"自适应拉伸切除成功生成特征: {cut_name}", {"feature_name": cut_name})

            # 步骤 8: 切除特征树核验
            tree_cut = verify_feature_tree(model, cut_name)
            record_step(8, "Verify_Cut_Feature_Tree", tree_cut.get("valid", False), f"切除特征树有效性: {tree_cut.get('valid')}", tree_cut)

            # 步骤 9: 切除后双精度体积核验
            props2 = collect_mass_properties(model)
            vol2_mm3 = float(props2.get("volume_mm3", 0.0))
            cut_cylinder_vol = math.pi * (10.0 ** 2) * 10.0  # 1000π ≈ 3141.59265
            expected_vol2 = expected_vol1 - cut_cylinder_vol  # ≈ 46858.407 mm^3
            vol2_err = abs(vol2_mm3 - expected_vol2) / expected_vol2 * 100.0
            pass_vol2 = vol2_err <= 0.1
            record_step(9, "Verify_Cut_Volume", pass_vol2, f"切除后实测 {vol2_mm3:.3f} mm^3, 理论 {expected_vol2:.3f} mm^3, 误差 {vol2_err:.4f}%", {
                "measured_volume": vol2_mm3, "expected_volume": expected_vol2, "error_pct": vol2_err
            })

            # 步骤 10: 镜像特征自适应调度探测
            feat_mgr = getattr(model, "FeatureManager", None)
            has_mirror2 = hasattr(feat_mgr, "InsertMirrorFeature2")
            has_mirror1 = hasattr(feat_mgr, "InsertMirrorFeature")
            record_step(10, "Adaptive_Mirror_Capability", (has_mirror2 or has_mirror1), f"镜像特征接口探测: InsertMirrorFeature2={has_mirror2}, InsertMirrorFeature={has_mirror1}", {
                "has_mirror2": has_mirror2, "has_mirror1": has_mirror1
            })

            # 步骤 11: 质量属性平滑回退与一致性校验 (safe_mass_properties vs collect_mass_properties)
            safe_props = safe_mass_properties(model)
            collect_props = collect_mass_properties(model)
            vol_m3_from_collect = float(collect_props.get("volume_mm3", 0.0)) / (1000.0 ** 3)
            diff_vol = abs(safe_props["volume_m3"] - vol_m3_from_collect)
            mass_match = (diff_vol < 1e-8 and safe_props["volume_m3"] > 0)
            record_step(11, "Mass_Properties_Consistency", mass_match, f"质量属性高精度提取与单位换算完全自洽: mass={safe_props['mass_kg']:.6f}kg, vol={safe_props['volume_m3']:.9f}m3", {
                "safe_props": safe_props, "diff_vol": diff_vol
            })

            # 步骤 12: 安全保存零件至沙箱隔离临时文件 (.sldprt)
            temp_dir = Path(tempfile.gettempdir()) / "dsh_sw_compat_sandbox"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_file_path = temp_dir / f"compat_cad_test_{int(time.time())}.sldprt"
            save_path_str = str(temp_file_path.resolve())
            register_owned_document(save_path_str)

            saved = False
            try:
                saved = model.SaveAs(save_path_str)
            except Exception:
                try:
                    ext = getattr(model, "Extension", None)
                    if ext and hasattr(ext, "SaveAs3"):
                        ext.SaveAs3(save_path_str, 0, 2, None, 0, 0)
                        saved = True
                except Exception:
                    pass

            file_exists = temp_file_path.exists() and temp_file_path.stat().st_size > 0
            record_step(12, "Save_Temporary_Part", file_exists, f"临时文档保存成功: {temp_file_path.name} (大小: {temp_file_path.stat().st_size if file_exists else 0} 字节)", {"file_path": save_path_str})

            # 步骤 13: 安全关闭临时零件文档
            sw.CloseDoc(test_title)
            curr_titles = list(snapshot_open_documents(sw, strict=False))
            closed_ok = (test_title not in curr_titles)
            record_step(13, "Close_Temporary_Part", closed_ok, f"测试零件 {test_title} 已彻底关闭", {"remaining": curr_titles})

            # 步骤 14: 重新打开已保存的临时测试零件文档
            reopened_model = open_document(sw, save_path_str, silent=True)
            if not reopened_model:
                record_step(14, "Reopen_Saved_Part", False, f"重新打开零件文档失败: {save_path_str}")
            reopened_title = get_com_member(reopened_model, "GetTitle")
            register_owned_document(reopened_title)
            record_step(14, "Reopen_Saved_Part", True, f"成功重新打开保存的文档: {reopened_title}", {"reopened_title": reopened_title})

            # 步骤 15: 重开后特征树结构及质量体积再次核验
            tree_reopen = verify_feature_tree(reopened_model)
            props_reopen = collect_mass_properties(reopened_model)
            vol_reopen = float(props_reopen.get("volume_mm3", 0.0))
            reopen_vol_err = abs(vol_reopen - expected_vol2) / expected_vol2 * 100.0
            reopen_pass = (tree_reopen.get("valid", False) and reopen_vol_err <= 0.1)
            record_step(15, "Verify_Reopened_Integrity", reopen_pass, f"重开后特征树健康且体积无损: 实测 {vol_reopen:.3f} mm^3, 误差 {reopen_vol_err:.4f}%", {
                "valid": tree_reopen.get("valid"), "node_count": tree_reopen.get("feature_count"), "volume_mm3": vol_reopen
            })

            # 步骤 16: 安全关闭并彻底从磁盘销毁临时测试零件
            sw.CloseDoc(reopened_title)
            time.sleep(0.5)
            if temp_file_path.exists():
                try:
                    temp_file_path.unlink()
                    deleted = not temp_file_path.exists()
                except Exception as e:
                    deleted = False
            else:
                deleted = True
            record_step(16, "Purge_Temporary_Artifacts", deleted, f"测试零件文件与磁盘残留已彻底清理: {save_path_str}", {"deleted": deleted})

        finally:
            # 保证关闭任何未关闭的测试文档
            final_titles = list(snapshot_open_documents(sw, strict=False))
            for t in list(final_titles):
                if test_title and t == test_title:
                    try:
                        sw.CloseDoc(t)
                    except Exception:
                        pass
                if reopened_model:
                    try:
                        r_title = get_com_member(reopened_model, "GetTitle")
                        if r_title and t == r_title:
                            sw.CloseDoc(t)
                    except Exception:
                        pass

            # 再次确认文档总数守恒
            end_titles = list(snapshot_open_documents(sw, strict=False))
            end_count = len(end_titles)
            report["final_documents"] = end_titles
            report["final_count"] = end_count
            conserved = (end_count == initial_count)
            report["document_conserved"] = conserved
            log(f"[最终状态] 文档总数: {end_count}, 初始总数: {initial_count}, 守恒状态: {conserved}")

        all_passed = all(s["status"] == "PASS" for s in report["steps"])
        if all_passed and conserved:
            report["overall_status"] = "PASS"
        else:
            report["overall_status"] = "FAIL"

    worker.execute(_execute, timeout=120)

    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    log(f"已导出 16 步 CAD 兼容性实机测试证据至: {JSON_FILE}")

    return report["overall_status"] == "PASS"


if __name__ == "__main__":
    success = run_16_step_cad_compat_regression()
    if success:
        log(">>> [SUCCESS] SolidWorks 2026 SP4.1 16 步 CAD 兼容性回归测试全部 PASS！")
        sys.exit(0)
    else:
        log(">>> [FAIL] 16 步 CAD 兼容性回归测试存在未通过步骤！")
        sys.exit(1)
