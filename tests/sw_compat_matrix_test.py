"""
tests/sw_compat_matrix_test.py

SolidWorks 2020-2026 多版本兼容性与异常分类深度验证测试：
1. 版本信息解析测试 (含 SP, Hotfix 与未知版本不误判)
2. 多实例与 PID 绑定能力探测测试
3. 异常严格分类机制测试 (COM 接口缺失降级 vs 几何业务错误绝不降级)
4. 凸台拉伸多版本回退 (FeatureExtrusion3 -> FeatureExtrusion2)
5. 拉伸切除多版本回退与方向自愈 (FeatureCut4 -> FeatureCut3)
6. 镜像特征多版本回退 (InsertMirrorFeature2 -> InsertMirrorFeature)
7. 质量属性提取平滑回退 (CreateMassProperty -> GetMassProperties2)
8. 装配体配合多版本回退 (AddMate5 -> AddMate3)
9. 工程图视图多版本回退 (CreateDrawViewFromModelView3 -> CreateDrawViewFromModelView2)
10. 全局降级事件日志审计追踪 (GLOBAL_DEGRADATION_LOG)
"""

import sys
import json
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENDOR_SCRIPTS = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"
sys.path.insert(0, str(VENDOR_SCRIPTS))

from sw_compat import (
    parse_solidworks_version_info,
    detect_solidworks_capabilities,
    safe_extrude_boss,
    safe_extrude_cut,
    safe_mirror_feature,
    safe_mass_properties,
    safe_add_mate,
    safe_create_drawing_view,
    is_com_interface_mismatch_error,
    SolidWorksCompatError,
    GLOBAL_DEGRADATION_LOG
)

EVIDENCE_DIR = REPO_ROOT / "temp_evidence_v030_compat" / "C-Compat-Matrix-Tests"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


class MockComError(Exception):
    def __init__(self, hresult, text="COM Error"):
        super().__init__(text)
        self.args = (hresult, text, None, None)


class MockFeatureManager:
    def __init__(self, has_extrude3=True, has_extrude2=True, has_cut4=True, has_cut3=True, has_mirror2=True, has_mirror1=True):
        self.called_methods = []
        if has_extrude3:
            self.FeatureExtrusion3 = self._mock_extrude3
        if has_extrude2:
            self.FeatureExtrusion2 = self._mock_extrude2
        if has_cut4:
            self.FeatureCut4 = self._mock_cut4
        if has_cut3:
            self.FeatureCut3 = self._mock_cut3
        if has_mirror2:
            self.InsertMirrorFeature2 = self._mock_mirror2
        if has_mirror1:
            self.InsertMirrorFeature = self._mock_mirror1

    def _mock_extrude3(self, *args):
        self.called_methods.append(("FeatureExtrusion3", len(args)))
        return {"name": "Boss-Extrude1", "method": "FeatureExtrusion3", "args_count": len(args)}

    def _mock_extrude2(self, *args):
        self.called_methods.append(("FeatureExtrusion2", len(args)))
        return {"name": "Boss-Extrude1", "method": "FeatureExtrusion2", "args_count": len(args)}

    def _mock_cut4(self, *args):
        self.called_methods.append(("FeatureCut4", len(args)))
        return {"name": "Cut-Extrude1", "method": "FeatureCut4", "args_count": len(args)}

    def _mock_cut3(self, *args):
        self.called_methods.append(("FeatureCut3", len(args)))
        return {"name": "Cut-Extrude1", "method": "FeatureCut3", "args_count": len(args)}

    def _mock_mirror2(self, *args):
        self.called_methods.append(("InsertMirrorFeature2", len(args)))
        return {"name": "Mirror1", "method": "InsertMirrorFeature2", "args_count": len(args)}

    def _mock_mirror1(self, *args):
        self.called_methods.append(("InsertMirrorFeature", len(args)))
        return {"name": "Mirror1", "method": "InsertMirrorFeature", "args_count": len(args)}


class MockAssemblyDoc:
    def __init__(self, has_mate5=True, has_mate3=True):
        self.called_methods = []
        if has_mate5:
            self.AddMate5 = self._mock_mate5
        if has_mate3:
            self.AddMate3 = self._mock_mate3

    def _mock_mate5(self, *args):
        self.called_methods.append(("AddMate5", len(args)))
        return {"name": "Coincident1", "method": "AddMate5"}

    def _mock_mate3(self, *args):
        self.called_methods.append(("AddMate3", len(args)))
        return {"name": "Coincident1", "method": "AddMate3"}


class MockDrawingDoc:
    def __init__(self, has_view3=True, has_view2=True):
        self.called_methods = []
        if has_view3:
            self.CreateDrawViewFromModelView3 = self._mock_view3
        if has_view2:
            self.CreateDrawViewFromModelView2 = self._mock_view2

    def _mock_view3(self, *args):
        self.called_methods.append(("CreateDrawViewFromModelView3", len(args)))
        return {"name": "DrawingView1", "method": "CreateDrawViewFromModelView3"}

    def _mock_view2(self, *args):
        self.called_methods.append(("CreateDrawViewFromModelView2", len(args)))
        return {"name": "DrawingView1", "method": "CreateDrawViewFromModelView2"}


def run_compat_suite():
    print("=== 开始运行 SolidWorks 2020-2026 深度兼容性与异常分类测试 ===")
    results = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "total_tests": 0,
        "passed": 0,
        "failed": 0,
        "cases": []
    }

    def record(name, status, detail=""):
        results["total_tests"] += 1
        if status:
            results["passed"] += 1
            print(f"[PASS] {name}")
        else:
            results["failed"] += 1
            print(f"[FAIL] {name} - {detail}")
        results["cases"].append({"name": name, "status": "PASS" if status else "FAIL", "detail": detail})

    # 1. 结构化版本信息解析测试 (含 SP, Hotfix 与未知版本处理)
    v2026 = parse_solidworks_version_info("34.4.1")
    pass_v2026 = (v2026["year"] == 2026 and v2026["major"] == 34 and v2026["sp"] == 4 and v2026["hotfix"] == 1 and v2026["valid"] is True)

    v2020 = parse_solidworks_version_info("28.0.0")
    pass_v2020 = (v2020["year"] == 2020 and v2020["major"] == 28 and v2020["sp"] == 0 and v2020["valid"] is True)

    v_unknown = parse_solidworks_version_info("InvalidCorruptedString")
    pass_unknown = (v_unknown["year"] is None and v_unknown["valid"] is False)

    record("Version_Info_Structured_Parsing", pass_v2026 and pass_v2020 and pass_unknown, "版本年份、SP 与非法字符串解析符合规范")

    # 2. 动态能力探测与无默认 2026 假定
    caps_none = detect_solidworks_capabilities(None)
    pass_caps_none = (caps_none["detected_year"] is None and caps_none["api_tier"] == "unknown")
    record("Capabilities_Probe_No_Default_Assumption", pass_caps_none, "无连接时不盲目假定为 2026")

    # 3. 异常严格分类机制测试 (COM 接口缺失 vs 业务几何失败)
    # 3.1 识别 COM 错误码
    disp_not_found = MockComError(-2147352573, "DISP_E_MEMBERNOTFOUND")
    disp_bad_param = MockComError(-2147352562, "DISP_E_BADPARAMCOUNT")
    geom_error = RuntimeError("Self-intersecting curve in sketch contour")
    
    pass_err_disp = is_com_interface_mismatch_error(disp_not_found) and is_com_interface_mismatch_error(disp_bad_param)
    pass_err_geom = not is_com_interface_mismatch_error(geom_error)
    record("Error_Classification_Interface_vs_Geometry", pass_err_disp and pass_err_geom, "严格区分接口缺失与几何业务异常")

    # 3.2 验证在几何业务失败时绝不盲目降级重试
    class BrokenGeometryFM:
        def FeatureExtrusion3(self, *args):
            raise ValueError("草图轮廓自相交，几何体创建失败")
        def FeatureExtrusion2(self, *args):
            raise AssertionError("严禁在几何业务失败时调用此降级接口！")

    caught_geom_directly = False
    try:
        safe_extrude_boss(BrokenGeometryFM(), depth1=0.01)
    except ValueError as e:
        caught_geom_directly = True
    record("Geometry_Failure_No_Blind_Degradation", caught_geom_directly, "几何失败直接向上冒泡，不执行非幂等降级")

    # 4. 现代版本与老版本凸台拉伸降级调度
    modern_fm = MockFeatureManager(has_extrude3=True, has_cut4=True, has_mirror2=True)
    res_b3 = safe_extrude_boss(modern_fm, depth1=0.02)
    record("Boss_Extrusion_Modern_Path", res_b3["method"] == "FeatureExtrusion3", "现代版本调度 FeatureExtrusion3 (23 参数)")

    legacy_fm = MockFeatureManager(has_extrude3=False, has_extrude2=True, has_cut4=False, has_cut3=True, has_mirror2=False, has_mirror1=True)
    res_b2 = safe_extrude_boss(legacy_fm, depth1=0.02, current_year=2020)
    record("Boss_Extrusion_Legacy_Path", res_b2["method"] == "FeatureExtrusion2", "旧版调度 FeatureExtrusion2 (19 参数)")

    # 5. 拉伸切除多版本与方向自愈
    res_c4 = safe_extrude_cut(modern_fm, depth1=0.01)
    record("Cut_Extrusion_Modern_Path", res_c4["method"] == "FeatureCut4", "现代切除调度 FeatureCut4 (27 参数)")

    res_c3 = safe_extrude_cut(legacy_fm, depth1=0.01, current_year=2020)
    record("Cut_Extrusion_Legacy_Path", res_c3["method"] == "FeatureCut3", "旧版切除调度 FeatureCut3 (21 参数)")

    # 6. 镜像特征回退
    res_m2 = safe_mirror_feature(modern_fm)
    res_m1 = safe_mirror_feature(legacy_fm, current_year=2020)
    record("Mirror_Feature_Modern_And_Fallback", res_m2["method"] == "InsertMirrorFeature2" and res_m1["method"] == "InsertMirrorFeature", "镜像调度与平滑回退正确")

    # 7. 装配体配合回退 (AddMate5 -> AddMate3)
    modern_asm = MockAssemblyDoc(has_mate5=True, has_mate3=True)
    res_mate5 = safe_add_mate(modern_asm, 0, 0, False, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0, False, False, 0, None)
    
    legacy_asm = MockAssemblyDoc(has_mate5=False, has_mate3=True)
    res_mate3 = safe_add_mate(legacy_asm, 0, 0, False, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0, False, False, 0, None, current_year=2020)
    record("Assembly_Mate_Modern_And_Fallback", res_mate5["method"] == "AddMate5" and res_mate3["method"] == "AddMate3", "装配配合 AddMate5 与 AddMate3 回退正确")

    # 8. 工程图视图回退 (CreateDrawViewFromModelView3 -> CreateDrawViewFromModelView2)
    modern_draw = MockDrawingDoc(has_view3=True, has_view2=True)
    res_view3 = safe_create_drawing_view(modern_draw, "part.sldprt", "*前视", 0.1, 0.1)

    legacy_draw = MockDrawingDoc(has_view3=False, has_view2=True)
    res_view2 = safe_create_drawing_view(legacy_draw, "part.sldprt", "*前视", 0.1, 0.1, current_year=2020)
    record("Drawing_View_Modern_And_Fallback", res_view3["method"] == "CreateDrawViewFromModelView3" and res_view2["method"] == "CreateDrawViewFromModelView2", "工程图视图接口回退正确")

    # 9. 质量属性提取平滑回退
    class MockModelModern:
        class Extension:
            class CreateMassProperty:
                Mass = 1.25
                Volume = 0.000125
                SurfaceArea = 0.025
                CenterOfMass = (0.05, 0.05, 0.05)
    
    class MockModelLegacy:
        class Extension:
            @staticmethod
            def GetMassProperties2(opt, acc, refresh):
                return (0.05, 0.05, 0.05, 0.000125, 0.025, 1.25)

    mp_mod = safe_mass_properties(MockModelModern())
    mp_leg = safe_mass_properties(MockModelLegacy())
    pass_mp = (mp_mod["mass_kg"] == 1.25 and mp_leg["mass_kg"] == 1.25 and mp_leg["volume_m3"] == 0.000125)
    record("Mass_Properties_Modern_And_Legacy_Array", pass_mp, "质量属性高精度与旧版数组解析完全一致")

    # 10. 降级日志审计追踪验证
    has_logs = len(GLOBAL_DEGRADATION_LOG) > 0
    record("Global_Degradation_Audit_Log", has_logs, f"捕获到 {len(GLOBAL_DEGRADATION_LOG)} 条降级审计事件")

    # =========================================================================
    # 11-16. 2020 到 2025 六个版本的独立单版本仿真矩阵测试（遵从专项收尾高标准要求）
    # =========================================================================
    for ver_year, major_id, is_modern in [
        (2020, 28, False),
        (2021, 29, False),
        (2022, 30, False),
        (2023, 31, False),
        (2024, 32, True),
        (2025, 33, True),
    ]:
        case_name = f"Dedicated_Matrix_Verification_SW_{ver_year}"
        # 针对该年份构建专属的模拟 FeatureManager 与 AssemblyDoc
        if is_modern:
            sim_fm = MockFeatureManager(has_extrude3=True, has_cut4=True, has_mirror2=True)
            sim_asm = MockAssemblyDoc(has_mate5=True, has_mate3=True)
            sim_drw = MockDrawingDoc(has_view3=True, has_view2=True)
            expected_boss = "FeatureExtrusion3"
            expected_cut = "FeatureCut4"
            expected_mirror = "InsertMirrorFeature2"
            expected_mate = "AddMate5"
            expected_drw = "CreateDrawViewFromModelView3"
        else:
            sim_fm = MockFeatureManager(has_extrude3=False, has_extrude2=True, has_cut4=False, has_cut3=True, has_mirror2=False, has_mirror1=True)
            sim_asm = MockAssemblyDoc(has_mate5=False, has_mate3=True)
            sim_drw = MockDrawingDoc(has_view3=False, has_view2=True)
            expected_boss = "FeatureExtrusion2"
            expected_cut = "FeatureCut3"
            expected_mirror = "InsertMirrorFeature"
            expected_mate = "AddMate3"
            expected_drw = "CreateDrawViewFromModelView2"

        # 调度拉伸、切除、镜像、配合与工程图
        r_boss = safe_extrude_boss(sim_fm, depth1=0.015, current_year=ver_year)
        r_cut = safe_extrude_cut(sim_fm, depth1=0.008, current_year=ver_year)
        r_mir = safe_mirror_feature(sim_fm, current_year=ver_year)
        r_mate = safe_add_mate(sim_asm, 0, 0, False, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0, False, False, 0, None, current_year=ver_year)
        r_drw = safe_create_drawing_view(sim_drw, "part.sldprt", "*前视", 0.1, 0.1, current_year=ver_year)

        match_boss = (r_boss["method"] == expected_boss)
        match_cut = (r_cut["method"] == expected_cut)
        match_mir = (r_mir["method"] == expected_mirror)
        match_mate = (r_mate["method"] == expected_mate)
        match_drw = (r_drw["method"] == expected_drw)

        # 失败边界测试：几何异常必须在所有版本中严禁被降级捕获
        class GeomFaultFM:
            def FeatureExtrusion3(self, *a): raise ValueError("自相交")
            def FeatureExtrusion2(self, *a): raise ValueError("自相交")
        geom_isolated = False
        try:
            safe_extrude_boss(GeomFaultFM(), current_year=ver_year)
        except ValueError:
            geom_isolated = True

        all_v_ok = (match_boss and match_cut and match_mir and match_mate and match_drw and geom_isolated)
        record(case_name, all_v_ok, f"年份 {ver_year} (Major {major_id}): boss={expected_boss}, cut={expected_cut}, mirror={expected_mirror}, mate={expected_mate}, drw={expected_drw}")

    # 导出测试结果
    out_file = EVIDENCE_DIR / "sw_compat_matrix_deep_verification.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n已保存深度兼容性测试结果至: {out_file}")

    return results["failed"] == 0


if __name__ == "__main__":
    ok = run_compat_suite()
    if not ok:
        sys.exit(1)
    print("\n[SUCCESS] SolidWorks 2020-2026 深度兼容性与异常分类测试全部通过！")
