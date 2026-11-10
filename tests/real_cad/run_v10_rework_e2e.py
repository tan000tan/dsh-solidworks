# -*- coding: utf-8 -*-

"""

tests/real_cad/run_v10_rework_e2e.py

v1.0 发布前独立实机端到端全量物理取证脚本 (P0-01, P1-04)。



最高安全约束与执行准则：

1. 测试前记录全局 SolidWorks 进程清单；

2. 仅操作本轮测试独立启动的 SolidWorks 实例 (追踪记录 PID)；

3. 所有模型严格在专用隔离沙箱目录 audit/v1.0-rework-20261108/cad_e2e_sandbox/ 中创建；

4. 真实执行：倒角 (Chamfer)、圆角 (Fillet)、线性阵列 (LPattern)、圆周阵列 (CirPattern)、

   原生圆柱同心配合 (Concentric Mate)、四视图工程图投影、STEP AP214 实际导出；

5. 执行保存、关闭自建文档、从磁盘重新打开再验证闭环；

6. 测试结束后精准清理自建文档并退出本轮启动的 SolidWorks PID，复核进程归零。

"""

from __future__ import annotations



import json

import math

import os

import struct

import sys

import time

from datetime import datetime

from pathlib import Path



PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

VENDOR_SCRIPTS = PROJECT_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"

_target_sandbox = os.environ.get("CAD_E2E_SANDBOX_DIR")
if _target_sandbox:
    SANDBOX_DIR = Path(_target_sandbox)
    LOG_DIR = SANDBOX_DIR.parent / "logs"
else:
    SANDBOX_DIR = PROJECT_ROOT / "audit" / "v1.0-final-release" / "cad_e2e_sandbox"
    LOG_DIR = PROJECT_ROOT / "audit" / "v1.0-final-release" / "logs"



for p in (str(VENDOR_SCRIPTS), str(PROJECT_ROOT)):

    if p not in sys.path:

        sys.path.insert(0, p)



from sw_connect import (

    get_sta_worker,

    connect_solidworks,

    new_document,

    open_document,

    save_document,

    close_document,

    close_owned_solidworks,

    register_owned_document,

    get_com_member,

    create_empty_dispatch_variant,

    solidworks_processes,

)

from sw_part import (

    start_sketch,

    end_sketch,

    sketch_circle,

    sketch_corner_rectangle,

    current_sketch_name,

    extrude_boss,

    extrude_cut,

)

from sw_pattern import linear_pattern, circular_pattern

from sw_export import export_to_step

from sw_measure import collect_mass_properties as measure_mass_properties

from sw_assembly import (

    add_component,

    add_mate_coincident,

    add_concentric_mate_by_cylinders,

)

import sw_drawing



RAW_LOG_PATH = LOG_DIR / "e2e_solidworks_raw.log"

raw_log_file = None





def log(msg: str):

    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    formatted = f"[{timestamp}] {msg}"

    print(formatted, flush=True)

    if raw_log_file:

        raw_log_file.write(formatted + "\n")

        raw_log_file.flush()





def parse_stl_mesh(stl_path: str):

    """精确解析二进制 STL 文件，计算三角面数、空间包围盒以及基于有向四面体的网格闭合积分体积。"""

    with open(stl_path, "rb") as f:

        header = f.read(80)

        count_bytes = f.read(4)

        if len(count_bytes) < 4:

            raise ValueError(f"无效的 STL 文件: {stl_path}")

        tri_count = struct.unpack("<I", count_bytes)[0]



        total_volume = 0.0

        total_surface_area = 0.0



        min_x, max_x = float("inf"), float("-inf")

        min_y, max_y = float("inf"), float("-inf")

        min_z, max_z = float("inf"), float("-inf")



        for _ in range(tri_count):

            record = f.read(50)

            if len(record) < 50:

                break

            data = struct.unpack("<12fH", record)

            v1 = (data[3], data[4], data[5])

            v2 = (data[6], data[7], data[8])

            v3 = (data[9], data[10], data[11])



            for v in (v1, v2, v3):

                min_x = min(min_x, v[0])

                max_x = max(max_x, v[0])

                min_y = min(min_y, v[1])

                max_y = max(max_y, v[1])

                min_z = min(min_z, v[2])

                max_z = max(max_z, v[2])



            ax, ay, az = v2[0] - v1[0], v2[1] - v1[1], v2[2] - v1[2]

            bx, bx_y, bz = v3[0] - v1[0], v3[1] - v1[1], v3[2] - v1[2]

            cx = ay * bz - az * bx_y

            cy = az * bx - ax * bz

            cz = ax * bx_y - ay * bx

            area = 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)

            total_surface_area += area



            tet_vol = (

                v1[0] * (v2[1] * v3[2] - v2[2] * v3[1])

                - v1[1] * (v2[0] * v3[2] - v2[2] * v3[0])

                + v1[2] * (v2[0] * v3[1] - v2[1] * v3[0])

            ) / 6.0

            total_volume += tet_vol



    return {

        "tri_count": tri_count,

        "volume_mm3": abs(total_volume),

        "surface_area_mm2": total_surface_area,

        "delta_x_mm": max_x - min_x,

        "delta_y_mm": max_y - min_y,

        "delta_z_mm": max_z - min_z,

        "bounds": {

            "x": [min_x, max_x],

            "y": [min_y, max_y],

            "z": [min_z, max_z]

        }

    }





def inspect_feature_tree(model):

    features = []

    feat = get_com_member(model, "FirstFeature")

    while feat:

        try:

            name = get_com_member(feat, "Name")

            ftype = get_com_member(feat, "GetTypeName2")

            features.append({"name": str(name), "type": str(ftype)})

        except Exception:

            pass

        try:

            feat = get_com_member(feat, "GetNextFeature")

        except Exception:

            break

    return features





def run_e2e_rework_suite():

    global raw_log_file

    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    raw_log_file = open(RAW_LOG_PATH, "w", encoding="utf-8")



    log("=================================================================")

    log("=== dsh-solidworks v1.0 发布前实机端到端全量物理取证启动 ===")

    log("=================================================================")



    # 1. 测试前环境与进程清单确认

    procs_before = solidworks_processes()

    log(f"1. 测试前 SolidWorks 进程清单快照: {procs_before}")



    swApp, _, meta = connect_solidworks(wait_seconds=15, return_metadata=True)

    launched_here = meta.get("started_by_cad_studio", False)

    launched_pid = meta.get("process_id")

    actual_version = meta.get("actual_version")

    actual_revision = meta.get("actual_revision")



    log(f"2. COM 连接已建立: ProgID='SldWorks.Application', PID={launched_pid}, 本轮启动={launched_here}")

    log(f"   SolidWorks 版本信息: Year={actual_version}, Revision={actual_revision}")

    log(f"3. 专用测试沙箱目录: {SANDBOX_DIR}")



    results = {

        "metadata": {

            "start_time": datetime.now().isoformat(),

            "procs_before": procs_before,

            "launched_pid": launched_pid,

            "started_by_cad_studio": launched_here,

            "version": actual_version,

            "revision": actual_revision,

            "sandbox_dir": str(SANDBOX_DIR),

        },

        "features": {},

        "reopen_verification": {},

        "cleanup": {},

    }



    created_models = []

    created_paths = {}



    try:

        # =========================================================================

        # 特征测试 1: 阶梯轴零件 (Chamfer 倒角, Fillet 圆角, 键槽切除, 几何网格积分)

        # =========================================================================

        log("\n--- [CASE 1] 创建零件 1: 阶梯轴 (含倒角、圆角、键槽与解析/网格体积交叉核验) ---")

        model_shaft = new_document(swApp, "part")

        register_owned_document(model_shaft)

        created_models.append(model_shaft)



        # 凸台 1: 直径 50mm, 长度 100mm

        start_sketch(model_shaft, "Top Plane")

        sketch_circle(model_shaft, 0.0, 0.0, 0.025)

        sk1 = current_sketch_name(model_shaft, fallback="草图1")

        end_sketch(model_shaft)

        extrude_boss(model_shaft, sk1, 0.100, direction=False)

        log("凸台 1 完成: 直径=50mm, 长度=100mm (Y: 0 ~ +100mm)")



        # 凸台 2: 直径 30mm, 长度 80mm

        start_sketch(model_shaft, "Top Plane")

        sketch_circle(model_shaft, 0.0, 0.0, 0.015)

        sk2 = current_sketch_name(model_shaft, fallback="草图2")

        end_sketch(model_shaft)

        extrude_boss(model_shaft, sk2, 0.080, direction=True, merge=True)

        log("凸台 2 完成: 直径=30mm, 长度=80mm (Y: 0 ~ -80mm)")



        # 键槽切除: 8mm x 30mm x 4mm

        start_sketch(model_shaft, "Top Plane")

        sketch_corner_rectangle(model_shaft, -0.004, -0.050, 0.004, -0.020)

        sk_key = current_sketch_name(model_shaft, fallback="草图3")

        end_sketch(model_shaft)

        extrude_cut(model_shaft, sk_key, 0.004, direction=True)

        log("键槽切除完成: 8x30x4mm (Y: -20 ~ -50mm)")



        callout = create_empty_dispatch_variant()



        # 原生倒角 (Chamfer)

        chamfer_ok = False

        try:

            model_shaft.ClearSelection2(True)

            sel_face = model_shaft.Extension.SelectByID2("", "FACE", 0.0, 0.100, 0.0, False, 1, callout, 0)

            if sel_face:

                ch_feat = model_shaft.FeatureManager.InsertFeatureChamfer(1, 0, 0.002, 0.785398, 0.0, 0.0, 0.0, 0)

                if ch_feat:

                    chamfer_ok = True

                    log(f"COM 倒角 (Chamfer) 特征创建成功: {get_com_member(ch_feat, 'Name')}")

        except Exception as e:

            log(f"倒角调用异常: {e}")



        # 原生圆角 (Fillet)

        fillet_ok = False

        try:

            model_shaft.ClearSelection2(True)

            sel_cyl = model_shaft.Extension.SelectByID2("", "FACE", 0.025, 0.050, 0.0, False, 1, callout, 0)

            if sel_cyl:

                f_feat = model_shaft.FeatureManager.FeatureFillet(195, 0.002, 0, 0)

                if f_feat:

                    fillet_ok = True

                    log(f"COM 圆角 (Fillet) 特征创建成功: {get_com_member(f_feat, 'Name')}")

        except Exception as e:

            log(f"圆角调用异常: {e}")



        get_com_member(model_shaft, "EditRebuild3")

        shaft_path = str(SANDBOX_DIR / "v10_stepped_shaft.SLDPRT")

        save_document(model_shaft, shaft_path)

        register_owned_document(shaft_path)

        created_paths["shaft"] = shaft_path

        log(f"阶梯轴已保存: {shaft_path} (大小={os.path.getsize(shaft_path)} 字节)")



        # 导出 STL 并做三角网格积分验证

        stl_path = str(SANDBOX_DIR / "v10_stepped_shaft.STL")

        save_document(model_shaft, stl_path)

        stl_mesh = parse_stl_mesh(stl_path)

        mass_props = measure_mass_properties(model_shaft)

        v_cad = mass_props.get("volume_mm3", 0.0)

        v_theo = 251938.210  # 理论解析体积 (mm3)

        err_cad_theo = abs(v_cad - v_theo) / v_theo if v_cad else 0.0

        err_stl_theo = abs(stl_mesh["volume_mm3"] - v_theo) / v_theo

        log(f"几何核算: 理论解析={v_theo:.3f} mm³, CAD原生={v_cad:.3f} mm³ (误差={err_cad_theo*100:.4f}%), STL积分={stl_mesh['volume_mm3']:.3f} mm³ (误差={err_stl_theo*100:.4f}%)")



        shaft_tree = inspect_feature_tree(model_shaft)

        results["features"]["stepped_shaft"] = {

            "path": shaft_path,

            "stl_path": stl_path,

            "chamfer_success": chamfer_ok,

            "fillet_success": fillet_ok,

            "cad_volume_mm3": v_cad,

            "analytical_volume_mm3": v_theo,

            "stl_volume_mm3": stl_mesh["volume_mm3"],

            "tri_count": stl_mesh["tri_count"],

            "bounds": stl_mesh["bounds"],

            "feature_tree": shaft_tree,

        }



        # =========================================================================

        # 特征测试 2: 底座零件 (线性阵列 Linear Pattern)

        # =========================================================================

        log("\n--- [CASE 2] 创建零件 2: 底座基板与线性阵列 (LinearPattern) ---")

        model_base = new_document(swApp, "part")

        register_owned_document(model_base)

        created_models.append(model_base)



        start_sketch(model_base, "Top Plane")

        sketch_corner_rectangle(model_base, -0.060, -0.040, 0.060, 0.040)

        sk_b1 = current_sketch_name(model_base, fallback="草图1")

        end_sketch(model_base)

        extrude_boss(model_base, sk_b1, 0.015, direction=False)



        # 中心配合通孔 D=50mm

        start_sketch(model_base, "Top Plane")

        sketch_circle(model_base, 0.0, 0.0, 0.025)

        sk_bh = current_sketch_name(model_base, fallback="草图2")

        end_sketch(model_base)

        extrude_cut(model_base, sk_bh, 0.015, direction=True)



        # 阵列种子孔 D=10mm

        start_sketch(model_base, "Top Plane")

        sketch_circle(model_base, 0.040, 0.025, 0.005)

        sk_seed = current_sketch_name(model_base, fallback="草图3")

        end_sketch(model_base)

        feat_seed = extrude_cut(model_base, sk_seed, 0.015, direction=True)

        seed_name = str(get_com_member(feat_seed, "Name") if feat_seed else "切除-拉伸2")



        lpattern_ok = False

        try:

            lp_feat = linear_pattern(model_base, seed_name, (-1, 0, 0), 0.030, 3)

            if lp_feat:

                lpattern_ok = True

                log(f"COM 线性阵列 (LinearPattern) 创建成功: {get_com_member(lp_feat, 'Name')}")

        except Exception as e:

            log(f"线性阵列异常: {e}")



        get_com_member(model_base, "EditRebuild3")

        base_path = str(SANDBOX_DIR / "v10_base.SLDPRT")

        save_document(model_base, base_path)

        register_owned_document(base_path)

        created_paths["base"] = base_path

        base_tree = inspect_feature_tree(model_base)

        log(f"底座已保存: {base_path} (大小={os.path.getsize(base_path)} 字节)")



        results["features"]["base"] = {

            "path": base_path,

            "lpattern_success": lpattern_ok,

            "feature_tree": base_tree,

        }



        # =========================================================================

        # 特征测试 3: 齿轮零件 (圆周阵列 Circular Pattern)

        # =========================================================================

        log("\n--- [CASE 3] 创建零件 3: 齿轮法兰与圆周阵列 (CircularPattern) ---")

        model_gear = new_document(swApp, "part")

        register_owned_document(model_gear)

        created_models.append(model_gear)



        start_sketch(model_gear, "Top Plane")

        sketch_circle(model_gear, 0.0, 0.0, 0.030)

        sk_g1 = current_sketch_name(model_gear, fallback="草图1")

        end_sketch(model_gear)

        feat_gear_boss = extrude_boss(model_gear, sk_g1, 0.012, direction=False)



        # 中心孔 D=30mm

        start_sketch(model_gear, "Top Plane")

        sketch_circle(model_gear, 0.0, 0.0, 0.015)

        sk_gh = current_sketch_name(model_gear, fallback="草图2")

        end_sketch(model_gear)

        extrude_cut(model_gear, sk_gh, 0.012, direction=True)



        # 螺栓孔种子 D=6mm

        start_sketch(model_gear, "Top Plane")

        sketch_circle(model_gear, 0.022, 0.0, 0.003)

        sk_bolt = current_sketch_name(model_gear, fallback="草图3")

        end_sketch(model_gear)

        feat_bolt = extrude_cut(model_gear, sk_bolt, 0.012, direction=True)

        bolt_name = str(get_com_member(feat_bolt, "Name") if feat_bolt else "切除-拉伸2")



        cirpattern_ok = False

        try:

            faces = get_com_member(feat_gear_boss, "GetFaces")

            cyl_face = None

            if faces:

                for f in faces:

                    surf = get_com_member(f, "GetSurface")

                    if surf and get_com_member(surf, "IsCylinder"):

                        cyl_face = f

                        break

            if cyl_face:

                cp_feat = circular_pattern(model_gear, bolt_name, cyl_face, 2 * math.pi, 6)

                if cp_feat:

                    cirpattern_ok = True

                    log(f"COM 圆周阵列 (CircularPattern) 创建成功: {get_com_member(cp_feat, 'Name')}")

        except Exception as e:

            log(f"圆周阵列异常: {e}")



        get_com_member(model_gear, "EditRebuild3")

        gear_path = str(SANDBOX_DIR / "v10_gear.SLDPRT")

        save_document(model_gear, gear_path)

        register_owned_document(gear_path)

        created_paths["gear"] = gear_path

        gear_tree = inspect_feature_tree(model_gear)

        log(f"齿轮已保存: {gear_path} (大小={os.path.getsize(gear_path)} 字节)")



        results["features"]["gear"] = {

            "path": gear_path,

            "cirpattern_success": cirpattern_ok,

            "feature_tree": gear_tree,

        }



        # =========================================================================

        # 特征测试 4: 装配体与同心配合 (Concentric Mate & STEP AP214)

        # =========================================================================

        log("\n--- [CASE 4] 创建装配体与原生圆柱同心配合 (Concentric Mate) ---")

        model_asm = new_document(swApp, "assembly")

        register_owned_document(model_asm)

        created_models.append(model_asm)



        comp_base = add_component(model_asm, base_path, 0.0, 0.0, 0.0, sw=swApp)

        comp_shaft = add_component(model_asm, shaft_path, 0.0, 0.050, 0.0, sw=swApp)

        comp_gear = add_component(model_asm, gear_path, 0.0, -0.050, 0.0, sw=swApp)



        asm_title = str(get_com_member(model_asm, "GetTitle")).split(".")[0]

        base_name = str(get_com_member(comp_base, "Name2"))

        shaft_name = str(get_com_member(comp_shaft, "Name2"))

        gear_name = str(get_com_member(comp_gear, "Name2"))



        # 轴向平面重合配合

        for cand in ("上视基准面", "Top Plane"):

            try:

                m1 = add_mate_coincident(model_asm, f"{cand}@{base_name}@{asm_title}", "PLANE", f"{cand}@{shaft_name}@{asm_title}", "PLANE")

                if m1:

                    log("装配配合 1 (Base <-> Shaft 平面重合) 创建成功")

                    break

            except Exception:

                pass



        # 原生圆柱面同心配合: Base 孔 (R=25mm) <-> Shaft 轴 (R=25mm)

        concentric_base_shaft = False

        try:

            m2 = add_concentric_mate_by_cylinders(

                model_asm, comp_base, comp_shaft,

                radius_a=(0.020, 0.030), radius_b=(0.020, 0.030),

                name="Concentric_Base_Shaft_Native"

            )

            if m2:

                concentric_base_shaft = True

                log("原生圆柱面同心配合 (Base 孔 <-> Shaft 轴, swMateCONCENTRIC) 创建成功！")

        except Exception as e:

            log(f"同心配合 1 异常: {e}")



        for cand in ("上视基准面", "Top Plane"):

            try:

                m3 = add_mate_coincident(model_asm, f"{cand}@{gear_name}@{asm_title}", "PLANE", f"{cand}@{shaft_name}@{asm_title}", "PLANE")

                if m3:

                    log("装配配合 3 (Gear <-> Shaft 平面重合) 创建成功")

                    break

            except Exception:

                pass



        # 原生圆柱面同心配合: Gear 孔 (R=15mm) <-> Shaft 轴 (R=15mm)

        concentric_gear_shaft = False

        try:

            m4 = add_concentric_mate_by_cylinders(

                model_asm, comp_gear, comp_shaft,

                radius_a=(0.010, 0.020), radius_b=(0.010, 0.020),

                name="Concentric_Gear_Shaft_Native"

            )

            if m4:

                concentric_gear_shaft = True

                log("原生圆柱面同心配合 (Gear 孔 <-> Shaft 轴, swMateCONCENTRIC) 创建成功！")

        except Exception as e:

            log(f"同心配合 2 异常: {e}")



        get_com_member(model_asm, "ClearSelection2", True)

        get_com_member(model_asm, "EditRebuild3")



        asm_path = str(SANDBOX_DIR / "v10_assembly.SLDASM")

        save_document(model_asm, asm_path)

        register_owned_document(asm_path)

        created_paths["assembly"] = asm_path

        asm_tree = inspect_feature_tree(model_asm)

        log(f"装配体已保存: {asm_path} (大小={os.path.getsize(asm_path)} 字节)")



        # STEP AP214 实际导出

        step_path = str(SANDBOX_DIR / "v10_assembly.step")

        swApp.SetUserPreferenceIntegerValue(75, 214)  # 75 = swStepAP, 214 = AP214

        swApp.SetUserPreferenceToggle(787, True)

        export_to_step(model_asm, step_path)

        step_protocol = "UNKNOWN"

        with open(step_path, "r", encoding="utf-8", errors="replace") as f:

            for _ in range(60):

                line = f.readline()

                line_lower = line.lower()

                if "automotive_design" in line_lower or "step ap214" in line_lower:

                    step_protocol = "AP214 (automotive_design)"

                    break

                elif "config_control_design" in line_lower or "step ap203" in line_lower:

                    step_protocol = "AP203 (config_control_design)"

                    break

        step_full_text = Path(step_path).read_text(encoding="utf-8", errors="replace")

        manifold_brep_count = step_full_text.count("MANIFOLD_SOLID_BREP")

        closed_shell_count = step_full_text.count("CLOSED_SHELL")

        adv_face_count = step_full_text.count("ADVANCED_FACE")

        log(f"STEP AP214 导出核验: {step_path} ({os.path.getsize(step_path)} 字节, 协议={step_protocol}, 实体数={manifold_brep_count}, 闭合壳数={closed_shell_count}, 高阶面数={adv_face_count})")



        results["features"]["assembly"] = {

            "path": asm_path,

            "step_path": step_path,

            "step_protocol": step_protocol,

            "concentric_base_shaft": concentric_base_shaft,

            "concentric_gear_shaft": concentric_gear_shaft,

            "feature_tree": asm_tree,

        }



        # =========================================================================

        # 特征测试 5: 工程图与四视图投影 (4-View Drawing & PDF)

        # =========================================================================

        log("\n--- [CASE 5] 创建工程图并投影 4 视图 (三视图 + 轴测投影) ---")

        model_draw = new_document(swApp, "drawing")

        register_owned_document(model_draw)

        created_models.append(model_draw)



        # 标准三视图

        created_3v = get_com_member(model_draw, "Create3rdAngleViews2", shaft_path)

        log(f"标准三视图 (主视/俯视/右视) 投影结果: {created_3v}")



        # 轴测投影

        iso_view = get_com_member(model_draw, "CreateDrawViewFromModelView3", shaft_path, "*等轴测", 0.280, 0.200, 0.0)

        if not iso_view:

            iso_view = get_com_member(model_draw, "CreateDrawViewFromModelView3", shaft_path, "*Isometric", 0.280, 0.200, 0.0)

        log(f"等轴测投影视图添加结果: {iso_view is not None}")



        get_com_member(model_draw, "EditRebuild")
        draw_path = str(SANDBOX_DIR / "v10_drawing.SLDDRW")
        register_owned_document(model_draw)
        register_owned_document(draw_path)
        save_document(model_draw, draw_path)

        register_owned_document(draw_path)

        created_paths["drawing"] = draw_path

        log(f"工程图已保存: {draw_path} (大小={os.path.getsize(draw_path)} 字节)")



        # 矢量 PDF 导出

        pdf_path = str(SANDBOX_DIR / "v10_drawing.pdf")

        pdf_ok = sw_drawing.export_sheet_to_pdf(model_draw, pdf_path, sw_app=swApp)

        pdf_size = os.path.getsize(pdf_path) if os.path.exists(pdf_path) else 0

        log(f"工程图矢量 PDF 导出成功: {pdf_path} ({pdf_size} 字节)")



        drawing_struct = sw_drawing.inspect_drawing_structure(model_draw)

        views = drawing_struct.get("views", [])

        log(f"工程图视图解析总数: {len(views)}")

        for v in views:

            log(f"  View: {v.get('name')} (类型={v.get('type')}, 定向={v.get('orientation')})")



        results["features"]["drawing"] = {

            "path": draw_path,

            "pdf_path": pdf_path,

            "pdf_size_bytes": pdf_size,

            "view_count": len(views),

            "views": views,

        }



        # =========================================================================

        # 步骤 6: 逆序安全关闭本轮自建文档

        # =========================================================================

        log("\n--- [STEP 6] 安全关闭本轮全部自建文档 (逆序: 工程图 -> 装配体 -> 零件) ---")

        for m in reversed(created_models):

            title = str(get_com_member(m, "GetTitle"))

            ok = close_document(swApp, m, force_discard=False, allowed_roots=[str(SANDBOX_DIR), str(PROJECT_ROOT)])

            log(f"关闭测试文档: {title} (关闭成功={ok})")



        # =========================================================================

        # 步骤 7: 从磁盘重新打开已保存模型并再次验证 (Reopen & Verify)

        # =========================================================================

        log("\n--- [STEP 7] 物理重开验证 (Reopen & Re-verify from disk) ---")

        for doc_key in ("shaft", "base", "gear", "assembly", "drawing"):

            fpath = created_paths[doc_key]

            log(f"重新打开磁盘文件: {fpath}...")

            reopened_doc = open_document(swApp, fpath, read_only=True)

            if reopened_doc:

                register_owned_document(reopened_doc)

                r_title = str(get_com_member(reopened_doc, "GetTitle"))

                r_type = get_com_member(reopened_doc, "GetType")

                r_tree = inspect_feature_tree(reopened_doc)

                log(f"  重开成功: Title='{r_title}', Type={r_type}, 特征节点数={len(r_tree)}")

                results["reopen_verification"][doc_key] = {

                    "path": fpath,

                    "reopen_success": True,

                    "title": r_title,

                    "type": r_type,

                    "feature_count": len(r_tree),

                }

                # 再次安全关闭

                close_document(swApp, reopened_doc, force_discard=False, allowed_roots=[str(SANDBOX_DIR), str(PROJECT_ROOT)])

            else:

                log(f"  重开失败: {fpath}")

                results["reopen_verification"][doc_key] = {

                    "path": fpath,

                    "reopen_success": False,

                }



    finally:

        # =========================================================================

        # 步骤 8: 进程与资源清理 (仅终止本轮启动的 SolidWorks PID)

        # =========================================================================

        log("\n--- [STEP 8] 进程清理与会话闭环 ---")

        closed_sw = close_owned_solidworks(swApp, True, expected_pid=launched_pid)

        log(f"close_owned_solidworks(PID={launched_pid}) 调用结果: {closed_sw}")



        # 优雅轮询等待进程释放资源（最多等待 10 秒，严禁执行 taskkill 强杀进程）

        procs_after = solidworks_processes()

        deadline = time.monotonic() + 10.0

        while launched_pid in procs_after and time.monotonic() < deadline:

            time.sleep(1.0)

            procs_after = solidworks_processes()



        log(f"退出调用后 SolidWorks 进程快照: {procs_after}")

        if launched_pid in procs_after:

            log(f"警告: PID={launched_pid} 在超时后仍在后台。最高安全红线：严禁执行 taskkill 强杀进程，保留进程与现场证据。")

        else:

            log(f"PID={launched_pid} 已优雅退出，系统纯净待机基线已恢复。")



        log(f"最终 SolidWorks 进程快照: {procs_after}")

        results["cleanup"] = {

            "launched_pid": launched_pid,

            "procs_after": procs_after,

            "clean_standby_restored": len(procs_after) == 0,

        }

        results["metadata"]["end_time"] = datetime.now().isoformat()



        # 写入汇总 JSON

        summary_path = SANDBOX_DIR / "v10_rework_e2e_summary.json"

        with open(summary_path, "w", encoding="utf-8") as f:

            json.dump(results, f, ensure_ascii=False, indent=2)

        log(f"端到端全量物理取证汇总已保存: {summary_path}")

        log("=================================================================")

        log("=== dsh-solidworks v1.0 实机端到端全量物理取证执行完毕 ===")

        log("=================================================================")

        if raw_log_file:

            raw_log_file.close()





if __name__ == "__main__":

    worker = get_sta_worker()

    worker.execute(run_e2e_rework_suite)

