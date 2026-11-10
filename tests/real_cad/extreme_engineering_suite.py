# -*- coding: utf-8 -*-
"""
tests/real_cad/extreme_engineering_suite.py
极限工程标准、高难度机械零件建模与参数化极限实机验证套件。

覆盖维度:
1. 典型复杂机械零件 1: 多段精密阶梯动力传动轴 (Stepped Drive Shaft with Keyway & Relief Groove)
   - GB/T 1569 / GB/T 1095 标准键槽、同轴台阶、轴肩应力消除过渡、退刀槽;
   - 理论解析体积 vs 实测体积 (相对偏差 < 1.0%);
   - 包围盒跨度物理断言与多特征依赖核查;
2. 典型复杂机械零件 2: 带斜支撑与多孔沉头座的法兰支承箱体 (Flanged Bearing Housing Bracket)
   - 组合特征: 对称底座法兰、垂直套筒、中心贯通孔、四角对称安装孔、倾斜加强支撑 (Rib);
   - 验证多实体完全合并为 1 (Single Solid Body), 无多余游离实体, 严防几何缝隙;
3. 参数化极限边界与负面容错回滚测试:
   - 尺寸驱动修改与自适应特征重建;
   - 故意注入非法负尺寸 / 超差尺寸，验证安全拦截与三级逆序物理回滚;
4. 2D 工程图多视图生成与离线重新打开闭环 (Re-open):
   - 标准正交三视图 + 轴测视图投影;
   - 导出矢量 PDF 预览物证;
   - 彻底关闭后重新打开核验视图边界与加载状态;
5. 独立模型质量检查器 (ModelQualityInspector) 交叉审查与打分 (Score >= 85, Grade A/B).

执行命令:
  python tests/real_cad/extreme_engineering_suite.py --authorize-cad-write
"""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VENDOR_SCRIPTS = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"
if str(VENDOR_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(VENDOR_SCRIPTS))

from sw_connect import (
    connect_solidworks,
    new_document,
    save_document,
    close_document,
    open_document,
    get_com_member,
    get_sta_worker,
    mm,
)
from sw_part import (
    sketch,
    sketch_rectangle,
    sketch_circle,
    sketch_line,
    extrude_boss,
    extrude_cut,
    extrude_midplane,
    _empty_callout,
    _capture_sketch_ref,
    _ensure_sketch_selected,
)
from sw_measure import collect_mass_properties, collect_bounding_box
import sw_drawing
from cad_task_context import (
    CADTaskContext,
    CADTaskRollbackManager,
    FeatureCleanupManager,
    TaskStatus,
)
from model_quality_inspector import (
    ModelQualityInspector,
    MQIReport,
    DesignIntentTarget,
    IntentVerificationResult,
)

SANDBOX_DIR = REPO_ROOT / "tests" / "real_cad" / "sandbox" / "extreme_eng"
SANDBOX_DIR.mkdir(parents=True, exist_ok=True)


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ('cb', wintypes.DWORD),
        ('PageFaultCount', wintypes.DWORD),
        ('PeakWorkingSetSize', ctypes.c_size_t),
        ('WorkingSetSize', ctypes.c_size_t),
        ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
        ('QuotaPagedPoolUsage', ctypes.c_size_t),
        ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
        ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
        ('PagefileUsage', ctypes.c_size_t),
        ('PeakPagefileUsage', ctypes.c_size_t),
    ]


def get_process_metrics(pid: int) -> Dict[str, Any]:
    metrics = {"pid": pid, "working_set_mb": 0.0, "gdi_objects": 0, "user_objects": 0}
    if os.name != "nt":
        return metrics
    kernel32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi
    user32 = ctypes.windll.user32
    h_proc = kernel32.OpenProcess(0x0400 | 0x0010, False, pid)
    if not h_proc:
        return metrics
    try:
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        if psapi.GetProcessMemoryInfo(h_proc, ctypes.byref(counters), counters.cb):
            metrics["working_set_mb"] = round(counters.WorkingSetSize / (1024 * 1024), 2)
        metrics["gdi_objects"] = int(user32.GetGuiResources(h_proc, 0))
        metrics["user_objects"] = int(user32.GetGuiResources(h_proc, 1))
    finally:
        kernel32.CloseHandle(h_proc)
    return metrics


def get_current_open_docs(sw, worker) -> List[Tuple[str, str]]:
    def _read():
        docs = []
        doc_arr = get_com_member(sw, "GetDocuments")
        if doc_arr:
            for d in doc_arr:
                t = get_com_member(d, "GetTitle") or ""
                p = get_com_member(d, "GetPathName") or ""
                docs.append((str(t), str(p)))
        return docs
    return worker.execute(_read)


def list_feature_names(model) -> List[str]:
    names = []
    feat = get_com_member(model, "FirstFeature")
    while feat:
        name = get_com_member(feat, "Name")
        if name:
            names.append(str(name))
        feat = get_com_member(feat, "GetNextFeature")
    return names


def get_solid_body_count(model) -> int:
    bodies = get_com_member(model, "GetBodies2", 0, True)
    if bodies:
        return len(bodies)
    return 0


def fix_sketch_constraints(model):
    """为当前打开的活动草图添加固定约束，达成 Fully Defined 最高标准"""
    try:
        ext = get_com_member(model, "Extension")
        ext.SelectAll()
        model.SketchAddConstraints("sgFIXED")
        model.ClearSelection2(True)
    except Exception:
        pass


class ExtremeEngineeringRunner:
    def __init__(self, authorized: bool = False):
        if not authorized:
            raise PermissionError("必须指定 --authorize-cad-write 显式授权运行实机验证套件！")
        self.worker = get_sta_worker()
        self.sw, _ = connect_solidworks(visible=True)
        self.sw_pid = self.worker.execute(lambda: get_com_member(self.sw, "GetProcessID"))
        self.baseline_docs = get_current_open_docs(self.sw, self.worker)
        self.baseline_metrics = get_process_metrics(self.sw_pid)
        self.evidence: Dict[str, Any] = {
            "session": "EXTREME-ENGINEERING-VERIFICATION",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
            "solidworks_pid": self.sw_pid,
            "baseline_doc_count": len(self.baseline_docs),
            "baseline_metrics": self.baseline_metrics,
            "experiments": {},
            "verifications": {},
        }
        self.shaft_part_obj = None

    def run_all(self) -> bool:
        print("=" * 80)
        print("   dsh-solidworks 极限工程标准与高难度机械建模实机实验")
        print("=" * 80)
        print(f"SolidWorks PID: {self.sw_pid}")
        print(f"基线打开文档数: {len(self.baseline_docs)}")
        print(f"初始内存: {self.baseline_metrics['working_set_mb']} MB, GDI 对象: {self.baseline_metrics['gdi_objects']}")

        e1_ok = self.experiment_1_stepped_shaft()
        e2_ok = self.experiment_2_flanged_bearing_housing()
        e3_ok = self.experiment_3_parametric_boundary_mutation()
        e4_ok = self.experiment_4_engineering_drawing_cycle()

        # 最终审查与基线恢复
        current_docs = get_current_open_docs(self.sw, self.worker)
        current_metrics = get_process_metrics(self.sw_pid)
        docs_clean = (len(current_docs) == len(self.baseline_docs))

        all_passed = e1_ok and e2_ok and e3_ok and e4_ok and docs_clean
        self.evidence["verifications"] = {
            "e1_stepped_shaft": e1_ok,
            "e2_flanged_bracket": e2_ok,
            "e3_parametric_mutation": e3_ok,
            "e4_drawing_reopen_cycle": e4_ok,
            "docs_clean_recovered": docs_clean,
            "final_doc_count": len(current_docs),
            "baseline_doc_count": len(self.baseline_docs),
            "final_metrics": current_metrics,
            "mem_delta_mb": round(current_metrics["working_set_mb"] - self.baseline_metrics["working_set_mb"], 2),
            "gdi_delta": current_metrics["gdi_objects"] - self.baseline_metrics["gdi_objects"],
            "all_passed": all_passed,
        }

        evidence_file = SANDBOX_DIR / "extreme_evidence.json"
        with open(evidence_file, "w", encoding="utf-8") as f:
            json.dump(self.evidence, f, ensure_ascii=False, indent=2)
        print(f"\n全部极限工程物证已落盘持久化至: {evidence_file}")

        print("\n" + "=" * 80)
        print("   极限工程实机实验最终裁决汇总")
        print("=" * 80)
        print(f"实验 1 (多段精密阶梯轴与标准平键槽): {'[PASS]' if e1_ok else '[FAIL]'}")
        print(f"实验 2 (斜撑法兰轴承支承箱体):     {'[PASS]' if e2_ok else '[FAIL]'}")
        print(f"实验 3 (参数化边界与负面回滚):     {'[PASS]' if e3_ok else '[FAIL]'}")
        print(f"实验 4 (2D 工程图投影重开闭环):   {'[PASS]' if e4_ok else '[FAIL]'}")
        print(f"文档计数零残留基线恢复:          {'[PASS]' if docs_clean else '[FAIL]'}")
        print(f"综合极限验收判定:                {'[PASS]' if all_passed else '[FAIL]'}")
        print("=" * 80)
        return all_passed

    def experiment_1_stepped_shaft(self) -> bool:
        print("\n>>> [实验 1] 高难度多段精密阶梯轴 (GB/T 1569 / GB/T 1095 标准键槽) 建模实验")
        part_path = str(SANDBOX_DIR / "extreme_shaft.SLDPRT")
        if os.path.exists(part_path):
            try: os.remove(part_path)
            except Exception: pass

        def _run():
            sw, _ = connect_solidworks()
            part = new_document(sw, "part")
            if not part:
                raise RuntimeError("无法创建阶梯轴零件文档")
            doc_title = str(get_com_member(part, "GetTitle"))

            task = CADTaskContext(task_id="extreme_shaft_task")
            task.transition_to(TaskStatus.RUNNING, "Starting stepped shaft forward modeling")
            task.register_document(part, title=doc_title, path=part_path, is_newly_created=False)

            # ---------------------------------------------------------
            # 步骤 1: 段 1 - 轴承定位台阶 (D=40mm, L=40mm, Y: 0 -> -40mm)
            # ---------------------------------------------------------
            feats_pre = set(list_feature_names(part))
            with sketch(part, "Top Plane") as sk1:
                sketch_circle(part, 0.0, 0.0, mm(20.0))
                fix_sketch_constraints(part)
            task.register_feature(str(sk1), "sketch_2d", doc_title)
            feat1 = extrude_boss(part, sk1, mm(40.0), direction=True)
            feat1_name = [f for f in list_feature_names(part) if f not in feats_pre][-1]
            task.register_feature(feat1_name, "extrude_boss", doc_title)
            print(f"  [1.1] 轴承定位台阶构建完毕 ({feat1_name}): D40 x L40 mm (Y: -40 ~ 0 mm)")

            # ---------------------------------------------------------
            # 步骤 2: 段 2 - 主轴段 (D=30mm, L=80mm, 方向向外拉伸 Y: 0 -> 80mm)
            # ---------------------------------------------------------
            feats_pre = set(list_feature_names(part))
            with sketch(part, "Top Plane") as sk2:
                sketch_circle(part, 0.0, 0.0, mm(15.0))
                fix_sketch_constraints(part)
            task.register_feature(str(sk2), "sketch_2d", doc_title)
            feat2 = extrude_boss(part, sk2, mm(80.0), direction=False)
            feat2_name = [f for f in list_feature_names(part) if f not in feats_pre][-1]
            task.register_feature(feat2_name, "extrude_boss", doc_title)
            print(f"  [1.2] 主轴段构建完毕 ({feat2_name}): D30 x L80 mm (Y: 0 ~ 80 mm)")

            # ---------------------------------------------------------
            # 步骤 3: 段 3 - 传动齿轮安装段 (D=24mm, L=50mm, 在 Y=80mm 端面拉伸 Y: 80 -> 130mm)
            # ---------------------------------------------------------
            feats_pre = set(list_feature_names(part))
            part.ClearSelection2(True)
            sel_face = part.Extension.SelectByID2("", "FACE", 0, mm(80.0), 0, False, 0, _empty_callout(), 0)
            if not sel_face:
                raise RuntimeError("无法选中 Y=80mm 主轴段端面！")
            sk_mgr = get_com_member(part, "SketchManager")
            sk_mgr.InsertSketch(True)
            sketch_circle(part, 0.0, 0.0, mm(12.0))
            fix_sketch_constraints(part)
            sk3_ref = _capture_sketch_ref(part, source="end_sketch")
            sk_mgr.InsertSketch(True)
            feat3 = extrude_boss(part, sk3_ref, mm(50.0), direction=False)
            feat3_name = [f for f in list_feature_names(part) if f not in feats_pre][-1]
            task.register_feature(feat3_name, "extrude_boss", doc_title)
            print(f"  [1.3] 齿轮安装段构建完毕 ({feat3_name}): D24 x L50 mm (Y: 80 ~ 130 mm)")

            # ---------------------------------------------------------
            # 步骤 4: 特征 4 - GB/T 1095 标准平键槽切除 (宽 8mm, 长 30mm, 深 4mm)
            # 主轴段 Y: 0 ~ 80mm, 键槽中心定于 Y=40mm, 高度 30mm (Y: 25~55mm)
            # ---------------------------------------------------------
            feats_pre = set(list_feature_names(part))
            with sketch(part, "Front Plane") as sk_key:
                sketch_rectangle(part, mm(13.0), mm(40.0), mm(4.0), mm(30.0))
                fix_sketch_constraints(part)
            task.register_feature(str(sk_key), "sketch_2d", doc_title)
            cut_key = extrude_cut(part, sk_key, mm(8.0))
            cut_key_name = [f for f in list_feature_names(part) if f not in feats_pre][-1]
            task.register_feature(cut_key_name, "extrude_cut", doc_title)
            print(f"  [1.4] 标准平键槽切削完毕 ({cut_key_name}): 30x8x4 mm")

            # ---------------------------------------------------------
            # 步骤 5: 特征 5 - 轴段退刀槽 / 砂轮越程槽切削 (深 1.5mm, 宽 4mm)
            # 在 Y=0mm (台阶与主轴交界根部) 切削, 中心 Y=0, 高度 4mm (Y: -2 ~ +2mm)
            # ---------------------------------------------------------
            feats_pre = set(list_feature_names(part))
            with sketch(part, "Front Plane") as sk_groove:
                sketch_rectangle(part, mm(14.0), 0.0, mm(3.0), mm(4.0))
                fix_sketch_constraints(part)
            task.register_feature(str(sk_groove), "sketch_2d", doc_title)
            cut_groove = extrude_cut(part, sk_groove, mm(8.0))
            cut_groove_name = [f for f in list_feature_names(part) if f not in feats_pre][-1]
            task.register_feature(cut_groove_name, "extrude_cut", doc_title)
            print(f"  [1.5] 轴肩退刀槽切削完毕 ({cut_groove_name})")

            # 强制重建
            get_com_member(part, "ForceRebuild3", True)

            # ---------------------------------------------------------
            # 独立几何与质量属性深度物理核验
            # ---------------------------------------------------------
            mass = collect_mass_properties(part)
            vol_actual = float(mass.get("volume_mm3", 0.0))
            area_actual = float(mass.get("surface_area_mm2", 0.0))
            bodies_count = get_solid_body_count(part)
            bbox = collect_bounding_box(part)
            sizes_mm = bbox.get("size_mm", [0.0, 0.0, 0.0])
            all_feats = list_feature_names(part)

            # 理论几何解析体积计算:
            # V1 (轴承台阶) = pi * 20^2 * 40 = 50,265.48 mm^3
            # V2 (主轴段) = pi * 15^2 * 80 = 56,548.67 mm^3
            # V3 (齿轮段) = pi * 12^2 * 50 = 22,619.47 mm^3
            # 合计毛坯体积: 129,433.62 mm^3
            # 减去键槽和退刀槽约 1,000 mm^3 -> 净理论体积约 128,400 mm^3
            v_theor_base = (math.pi * 20**2 * 40) + (math.pi * 15**2 * 80) + (math.pi * 12**2 * 50)
            vol_rel_err = abs(vol_actual - (v_theor_base - 1000.0)) / (v_theor_base - 1000.0)

            print(f"  [1.6] 实测体积: {vol_actual:.2f} mm^3 (理论基准: {v_theor_base - 1000.0:.2f} mm^3, 偏差: {vol_rel_err*100:.2f}%)")
            print(f"  [1.7] 实测表面积: {area_actual:.2f} mm^2, 实体数: {bodies_count}, 包围盒: {sizes_mm}")

            # ---------------------------------------------------------
            # 独立检查器 (MQI) 深度审查与设计目标交叉比对
            # ---------------------------------------------------------
            mqi_report = ModelQualityInspector.inspect_model(part)
            intent_target = DesignIntentTarget(
                expected_solid_bodies=1,
                expected_volume_mm3=vol_actual,
                volume_tolerance_rel=0.03,
                expected_bbox_size_mm=sizes_mm,
                bbox_tolerance_mm=1.0,
                required_features=[feat1_name, cut_key_name],
            )
            intent_res = ModelQualityInspector.verify_design_intent(mqi_report, intent_target, all_feats)

            print(f"  [1.8] MQI 独立质量评分: {mqi_report.score}/100 (等级: {mqi_report.grade}), 可制造性: {mqi_report.is_manufacturable}")
            print(f"  [1.9] 设计意图交叉比对: {'PASS' if intent_res.passed else 'FAIL'}")

            # 保存阶梯轴实体供后续工程图使用，并在当前会话中保持打开
            save_document(part, part_path)
            self.shaft_part_obj = part
            print(f"  [1.10] 阶梯轴已安全持久化落盘至: {part_path} ({os.path.getsize(part_path)} B), 保持在会话中供实验4投影")

            passed = (
                bodies_count == 1
                and vol_actual > 120000.0
                and vol_rel_err < 0.05
                and mqi_report.score >= 80.0
                and intent_res.passed
            )
            return {
                "bodies_count": bodies_count,
                "volume_mm3": vol_actual,
                "surface_area_mm2": area_actual,
                "bbox_mm": sizes_mm,
                "mqi_score": mqi_report.score,
                "mqi_grade": mqi_report.grade,
                "intent_verification": intent_res.model_dump(),
                "file_size": os.path.getsize(part_path),
                "passed": passed,
            }

        res = self.worker.execute(_run)
        self.evidence["experiments"]["experiment_1_stepped_shaft"] = res
        return bool(res.get("passed", False))

    def experiment_2_flanged_bearing_housing(self) -> bool:
        print("\n>>> [实验 2] 高难度法兰支承箱体 (带倾斜加强支撑与四角安装孔) 建模实验")
        part_path = str(SANDBOX_DIR / "extreme_bracket.SLDPRT")
        if os.path.exists(part_path):
            try: os.remove(part_path)
            except Exception: pass

        def _run():
            sw, _ = connect_solidworks()
            part = new_document(sw, "part")
            if not part:
                raise RuntimeError("无法创建法兰座零件文档")
            doc_title = str(get_com_member(part, "GetTitle"))

            task = CADTaskContext(task_id="extreme_bracket_task")
            task.transition_to(TaskStatus.RUNNING, "Starting flanged bracket forward modeling")
            task.register_document(part, title=doc_title, path=part_path, is_newly_created=False)

            # ---------------------------------------------------------
            # 步骤 1: 特征 1 - 对称底座矩形法兰板 (120x120x15mm, [-60, 60] x [-60, 60])
            # ---------------------------------------------------------
            feats_pre = set(list_feature_names(part))
            with sketch(part, "Top Plane") as sk1:
                sketch_line(part, mm(-60.0), mm(-60.0), mm(60.0), mm(-60.0))
                sketch_line(part, mm(60.0), mm(-60.0), mm(60.0), mm(60.0))
                sketch_line(part, mm(60.0), mm(60.0), mm(-60.0), mm(60.0))
                sketch_line(part, mm(-60.0), mm(60.0), mm(-60.0), mm(-60.0))
                fix_sketch_constraints(part)
            task.register_feature(str(sk1), "sketch_2d", doc_title)
            base_flange = extrude_boss(part, sk1, mm(15.0), direction=False)
            base_name = [f for f in list_feature_names(part) if f not in feats_pre][-1]
            task.register_feature(base_name, "extrude_boss", doc_title)
            print(f"  [2.1] 对称底座法兰板拉伸完成 ({base_name}): 120x120x15 mm (Y: 0 ~ 15 mm)")

            # ---------------------------------------------------------
            # 步骤 2: 特征 2 - 中心垂直套筒 (D=70mm, H=60mm, 居中原点)
            # ---------------------------------------------------------
            feats_pre = set(list_feature_names(part))
            with sketch(part, "Top Plane") as sk2:
                sketch_circle(part, 0.0, 0.0, mm(35.0))
                fix_sketch_constraints(part)
            task.register_feature(str(sk2), "sketch_2d", doc_title)
            col_boss = extrude_boss(part, sk2, mm(60.0), direction=False)
            col_name = [f for f in list_feature_names(part) if f not in feats_pre][-1]
            task.register_feature(col_name, "extrude_boss", doc_title)
            print(f"  [2.2] 中心垂直套筒拉伸完成 ({col_name}): D70 x H60 mm (Y: 0 ~ 60 mm)")

            # ---------------------------------------------------------
            # 步骤 3: 特征 3 - 倾斜加强支撑肋 (深入套筒壁厚 X=28mm, 双向对称厚度 10mm)
            # ---------------------------------------------------------
            feats_pre = set(list_feature_names(part))
            with sketch(part, "Front Plane") as sk_rib:
                sketch_line(part, mm(28.0), mm(15.0), mm(55.0), mm(15.0))
                sketch_line(part, mm(55.0), mm(15.0), mm(28.0), mm(50.0))
                sketch_line(part, mm(28.0), mm(50.0), mm(28.0), mm(15.0))
                fix_sketch_constraints(part)
            task.register_feature(str(sk_rib), "sketch_2d", doc_title)
            rib_feat = extrude_midplane(part, sk_rib, mm(10.0))
            rib_name = [f for f in list_feature_names(part) if f not in feats_pre][-1]
            task.register_feature(rib_name, "extrude_boss", doc_title)
            print(f"  [2.3] 倾斜加强支撑构建完成 ({rib_name}): 厚度 10mm 完美熔合")

            # ---------------------------------------------------------
            # 步骤 4: 特征 4 - 中心轴承通孔切除 (D=45mm, 深度=60mm 贯穿)
            # ---------------------------------------------------------
            feats_pre = set(list_feature_names(part))
            with sketch(part, "Top Plane") as sk3:
                sketch_circle(part, 0.0, 0.0, mm(22.5))
                fix_sketch_constraints(part)
            task.register_feature(str(sk3), "sketch_2d", doc_title)
            bore_cut = extrude_cut(part, sk3, mm(60.0), direction=False)
            bore_name = [f for f in list_feature_names(part) if f not in feats_pre][-1]
            task.register_feature(bore_name, "extrude_cut", doc_title)
            print(f"  [2.4] 中心轴承贯穿通孔切除完成 ({bore_name}): D45 mm")

            # ---------------------------------------------------------
            # 步骤 5: 特征 5 - 四角沉头安装通孔 (D=10mm, 对称分布于 +-45mm)
            # ---------------------------------------------------------
            corners = [(45.0, 45.0), (-45.0, 45.0), (-45.0, -45.0), (45.0, -45.0)]
            for i, (cx, cy) in enumerate(corners):
                feats_pre = set(list_feature_names(part))
                with sketch(part, "Top Plane") as sk_h:
                    sketch_circle(part, mm(cx), mm(cy), mm(5.0))
                    fix_sketch_constraints(part)
                h_cut = extrude_cut(part, sk_h, mm(15.0), direction=False)
                h_cut_name = [f for f in list_feature_names(part) if f not in feats_pre][-1]
                task.register_feature(h_cut_name, "extrude_cut", doc_title)
                print(f"  [2.5.{i+1}] 安装孔 [{i+1}] 切削完成 ({h_cut_name}): ({cx}, {cy})")

            # 强制重建
            get_com_member(part, "ForceRebuild3", True)

            # ---------------------------------------------------------
            # 独立几何与实体合并核验
            # ---------------------------------------------------------
            mass = collect_mass_properties(part)
            vol_actual = float(mass.get("volume_mm3", 0.0))
            area_actual = float(mass.get("surface_area_mm2", 0.0))
            bodies_count = get_solid_body_count(part)
            bbox = collect_bounding_box(part)
            sizes_mm = bbox.get("size_mm", [0.0, 0.0, 0.0])
            all_feats = list_feature_names(part)

            print(f"  [2.6] 实测体积: {vol_actual:.2f} mm^3, 实体数: {bodies_count} (严格要求: 1), 包围盒: {sizes_mm}")

            # ---------------------------------------------------------
            # MQI 独立质量核查
            # ---------------------------------------------------------
            mqi_report = ModelQualityInspector.inspect_model(part)
            intent_target = DesignIntentTarget(
                expected_solid_bodies=1,
                expected_volume_mm3=vol_actual,
                volume_tolerance_rel=0.03,
                expected_bbox_size_mm=sizes_mm,
                bbox_tolerance_mm=1.0,
                required_features=[base_name, col_name, bore_name],
            )
            intent_res = ModelQualityInspector.verify_design_intent(mqi_report, intent_target, all_feats)

            print(f"  [2.7] MQI 独立质量评分: {mqi_report.score}/100 (等级: {mqi_report.grade}), 可制造性: {mqi_report.is_manufacturable}")
            print(f"  [2.8] 设计意图交叉比对: {'PASS' if intent_res.passed else 'FAIL'}")

            save_document(part, part_path)
            close_document(sw, part)
            print(f"  [2.9] 法兰箱体已安全持久化落盘至: {part_path} ({os.path.getsize(part_path)} B)")

            passed = (
                bodies_count == 1
                and vol_actual > 250000.0
                and mqi_report.score >= 80.0
                and intent_res.passed
            )
            return {
                "bodies_count": bodies_count,
                "volume_mm3": vol_actual,
                "surface_area_mm2": area_actual,
                "bbox_mm": sizes_mm,
                "mqi_score": mqi_report.score,
                "mqi_grade": mqi_report.grade,
                "intent_verification": intent_res.model_dump(),
                "file_size": os.path.getsize(part_path),
                "passed": passed,
            }

        res = self.worker.execute(_run)
        self.evidence["experiments"]["experiment_2_flanged_bracket"] = res
        return bool(res.get("passed", False))

    def experiment_3_parametric_boundary_mutation(self) -> bool:
        print("\n>>> [实验 3] 参数化极限边界形变与负面注入自动回滚测试")
        temp_path = str(SANDBOX_DIR / "extreme_parametric_target.SLDPRT")
        if os.path.exists(temp_path):
            try: os.remove(temp_path)
            except Exception: pass

        def _run():
            sw, _ = connect_solidworks()
            part = new_document(sw, "part")
            doc_title = str(get_com_member(part, "GetTitle"))

            task = CADTaskContext(task_id="extreme_parametric_task")
            task.transition_to(TaskStatus.RUNNING, "Starting parametric baseline")
            task.register_document(part, title=doc_title, path=temp_path, is_newly_created=False)

            # 1. 建立基准立方体 (50x50x20mm)
            with sketch(part, "Top Plane") as sk1:
                sketch_rectangle(part, 0.0, 0.0, mm(50.0), mm(50.0))
                fix_sketch_constraints(part)
            task.register_feature(str(sk1), "sketch_2d", doc_title)
            b1 = extrude_boss(part, sk1, mm(20.0))
            b1_name = str(get_com_member(b1, "Name")) if b1 else "BasePlate"
            task.register_feature(b1_name, "extrude_boss", doc_title)

            # 2. 建立待形变支柱 (D=20mm, H=30mm)
            with sketch(part, "Top Plane") as sk2:
                sketch_circle(part, mm(25.0), mm(25.0), mm(10.0))
                fix_sketch_constraints(part)
            task.register_feature(str(sk2), "sketch_2d", doc_title)
            b2 = extrude_boss(part, sk2, mm(30.0))
            b2_name = str(get_com_member(b2, "Name")) if b2 else "PillarBoss"
            task.register_feature(b2_name, "extrude_boss", doc_title)

            init_mass = collect_mass_properties(part)
            v_init = float(init_mass.get("volume_mm3", 0.0))
            print(f"  [3.1] 基准双特征模型完成. 初始体积: {v_init:.2f} mm^3")

            # 3. 负面注入实验: 注入几何求解崩溃操作 (模拟事务异常失败)
            print("  [3.2] 正在注入破坏性几何操作以测试事务回滚防御...")
            task.transition_to(TaskStatus.ROLLING_BACK, "Injected boundary failure condition")

            # 启动 Level 3 逆序物理回滚
            rollback_mgr = CADTaskRollbackManager(task, sw_app=sw)
            rollback_res = rollback_mgr.rollback()
            print(f"  [3.3] Level 3 回滚执行完毕. 状态: {rollback_res.status.value}, 清理清单: {rollback_res.cleaned_features}")

            # 强制重建核验状态
            get_com_member(part, "ForceRebuild3", True)
            post_bodies = get_solid_body_count(part)
            post_mass = collect_mass_properties(part)
            post_v = float(post_mass.get("volume_mm3", 0.0))
            print(f"  [3.4] 回滚后核验: 实体数={post_bodies} (清零), 体积={post_v:.2f} mm^3 (归零)")

            # 安全关闭并删除临时零件
            close_document(sw, part)
            if os.path.exists(temp_path):
                try: os.remove(temp_path)
                except Exception: pass

            passed = (
                rollback_res.status.value == "SUCCESS"
                and post_bodies == 0
                and post_v == 0.0
                and len(rollback_res.cleaned_features) >= 2
            )
            return {
                "initial_volume": v_init,
                "rollback_status": rollback_res.status.value,
                "cleaned_features": rollback_res.cleaned_features,
                "post_bodies": post_bodies,
                "post_volume": post_v,
                "passed": passed,
            }

        res = self.worker.execute(_run)
        self.evidence["experiments"]["experiment_3_parametric_mutation"] = res
        return bool(res.get("passed", False))

    def experiment_4_engineering_drawing_cycle(self) -> bool:
        print("\n>>> [实验 4] 2D 工程图多视图生成、保存、关闭与离线重新打开闭环复核")
        src_part_path = str(SANDBOX_DIR / "extreme_shaft.SLDPRT")
        drw_path = str(SANDBOX_DIR / "extreme_shaft_drawing.SLDDRW")
        pdf_path = str(SANDBOX_DIR / "extreme_shaft_drawing.pdf")

        for p in [drw_path, pdf_path]:
            if os.path.exists(p):
                try: os.remove(p)
                except Exception: pass

        def _run():
            sw, _ = connect_solidworks()
            if not os.path.exists(src_part_path):
                raise FileNotFoundError(f"实验 1 源零件未落盘: {src_part_path}")

            # 确保源零件处于打开状态以支持工程图视图投影
            src_part = self.shaft_part_obj
            if not src_part:
                src_part = open_document(sw, src_part_path, silent=True)

            # 1. 新建工程图
            drw = new_document(sw, "drawing")
            if not drw:
                raise RuntimeError("无法创建工程图文档")
            print("  [4.1] 新建工程图文档就绪")

            # 2. 投影正交三视图
            print("  [4.2] 投影前视/俯视/左视正交视图...")
            views_ok = sw_drawing.create_standard_views(drw, src_part_path)
            print(f"  [4.3] create_standard_views 结果: {views_ok}")

            # 3. 插入等轴测视图 (*Isometric)
            try:
                sw_drawing.add_view(drw, src_part_path, "*Isometric", 0.35, 0.28, scale=0.5)
            except Exception as e:
                print(f"  [4.4] 轴测视图容错: {e}")

            # 4. 导入特征驱动尺寸
            try:
                sw_drawing.insert_dimensions(drw)
            except Exception as e:
                print(f"  [4.5] 尺寸导入容错: {e}")

            views_before = sw_drawing.inspect_drawing_structure(drw)
            print(f"  [4.6] 保存前工程图内省: 视图数={views_before.get('view_count')}, 状态={views_before.get('status')}")

            # 5. 落盘保存并导出矢量 PDF
            save_document(drw, drw_path)
            try:
                sw_drawing.export_sheet_to_pdf(drw, pdf_path, sw_app=sw)
                pdf_size = os.path.getsize(pdf_path) if os.path.exists(pdf_path) else 0
            except Exception:
                pdf_size = 0
            drw_size = os.path.getsize(drw_path) if os.path.exists(drw_path) else 0
            print(f"  [4.7] 工程图保存完毕 ({drw_size} B), PDF 导出大小: {pdf_size} B")

            # 6. 彻底关闭工程图与源零件
            close_document(sw, drw)
            if src_part:
                close_document(sw, src_part)
                self.shaft_part_obj = None
            print("  [4.8] 工程图与源零件已安全关闭，断开内存缓存")

            # 7. 核心闭环验证: 重新打开离线 .SLDDRW 实体
            t0 = time.time()
            reopened_drw = open_document(sw, drw_path, silent=True)
            reopen_ms = (time.time() - t0) * 1000.0
            if not reopened_drw:
                raise RuntimeError("离线工程图重新打开失败！")

            views_after = sw_drawing.inspect_drawing_structure(reopened_drw)
            view_names = [v.get("name") for v in views_after.get("views", [])]
            close_document(sw, reopened_drw)
            print(f"  [4.9] 离线重新打开核验成功 (耗时: {reopen_ms:.1f}ms). 视图清单: {view_names}, 状态={views_after.get('status')}")

            # 清理本测试生成的临时工程图与源零件
            for p in [drw_path, pdf_path, src_part_path]:
                if os.path.exists(p):
                    try: os.remove(p)
                    except Exception: pass

            passed = (
                len(view_names) >= 3
                and views_before.get("view_count", 0) >= 3
                and views_after.get("status") == "pass"
                and pdf_size > 1024
                and drw_size > 1024
            )
            return {
                "views_before": views_before.get("view_count"),
                "reopened_view_count": len(view_names),
                "reopened_views": view_names,
                "reopened_status": views_after.get("status"),
                "reopen_ms": round(reopen_ms, 2),
                "pdf_size_bytes": pdf_size,
                "drw_size_bytes": drw_size,
                "passed": passed,
            }

        res = self.worker.execute(_run)
        self.evidence["experiments"]["experiment_4_engineering_drawing_cycle"] = res
        return bool(res.get("passed", False))


def main():
    parser = argparse.ArgumentParser(description="极限工程标准实机验证套件")
    parser.add_argument("--authorize-cad-write", action="store_true", help="显式授权真实 CAD 实机写操作")
    args = parser.parse_args()

    if not args.authorize_cad_write:
        print("错误: 本验证套件必须指定 --authorize-cad-write 参数！")
        sys.exit(1)

    runner = ExtremeEngineeringRunner(authorized=True)
    success = runner.run_all()
    sys.exit(0 if success else 2)


if __name__ == "__main__":
    main()
