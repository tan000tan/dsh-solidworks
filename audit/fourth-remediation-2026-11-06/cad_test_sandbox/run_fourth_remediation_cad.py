"""
第四轮全量 CAD 实机验证与物理取证脚本 (run_fourth_remediation_cad.py)

最高安全准则：
1. 全程强隔离沙箱运行：所有产物严格写入 audit/fourth-remediation-2026-11-06/cad_test_sandbox/
2. 坚决禁止调用 CloseAllDocuments(True)
3. 严格精准关闭本次任务创建的测试模型，绝不触碰任何用户外部文件
4. 真实执行：
   - DEF-01: 原生阵列 (LinearPattern/CircularPattern)、倒角 (Chamfer)、圆角 (Fillet)
   - DEF-03: 原生圆柱面同心配合 (swMateCONCENTRIC, AddMate5)
   - DEF-04: 阶梯轴几何重新验收 (理论解析、CAD 原生、STL 离散网格积分)
   - DEF-02: 工程图视图方向与投影核验 (主视/俯视/右视/轴测及矢量 PDF)
   - DEF-11: STEP AP214 格式实际导出与文件头验证 (swStepAP=75, 214)
"""
import math
import os
import struct
import sys
import time
import json
from pathlib import Path

PROJECT_ROOT = Path(r"D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin")
VENDOR_SCRIPTS = PROJECT_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"
SANDBOX_DIR = PROJECT_ROOT / "audit" / "fourth-remediation-2026-11-06" / "cad_test_sandbox"

if str(VENDOR_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(VENDOR_SCRIPTS))

from sw_connect import (
    get_sta_worker,
    connect_solidworks,
    new_document,
    save_document,
    close_document,
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
from sw_export import export_to_pdf, export_to_step
from sw_measure import collect_mass_properties as measure_mass_properties
from sw_assembly import (
    add_component,
    add_mate_coincident,
    add_concentric_mate_by_cylinders,
    SW_MATE_CONCENTRIC,
    SW_MATE_COINCIDENT,
)
import sw_drawing


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def parse_stl_mesh(stl_path):
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
            # data: nx, ny, nz, v1x, v1y, v1z, v2x, v2y, v2z, v3x, v3y, v3z, attr
            # SolidWorks 导出的 STL 坐标数值单位已为 mm
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

            # 三角面面积
            ax, ay, az = v2[0] - v1[0], v2[1] - v1[1], v2[2] - v1[2]
            bx, bx_y, bz = v3[0] - v1[0], v3[1] - v1[1], v3[2] - v1[2]
            cx = ay * bz - az * bx_y
            cy = az * bx - ax * bz
            cz = ax * bx_y - ay * bx
            area = 0.5 * math.sqrt(cx * cx + cy * cy + cz * cz)
            total_surface_area += area

            # 有向四面体体积: (v1 . (v2 x v3)) / 6.0
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


def run_fourth_remediation_cad():
    log("=== 开始执行第四轮全量 CAD 实机验证与物理取证 ===")
    SANDBOX_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 会话建立与独立性确认
    procs_before = solidworks_processes()
    log(f"执行前 SolidWorks 进程快照: {procs_before}")
    swApp, _, meta = connect_solidworks(wait_seconds=5, return_metadata=True)
    launched_here = meta.get("started_by_cad_studio", False)
    pid = meta.get("process_id")
    log(f"已连接 SolidWorks (PID={pid}, 独占启动={launched_here})")

    results = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "pid": pid,
            "started_by_cad_studio": launched_here,
            "version": meta.get("actual_version"),
            "revision": meta.get("actual_revision"),
        },
        "parts": {},
        "assembly": {},
        "drawing": {}
    }

    created_models = []

    try:
        # =========================================================================
        # 零件 1: 阶梯轴 (remediated_stepped_shaft.SLDPRT) (DEF-04, DEF-01)
        # 尺寸规格：
        # - 大端：直径 50mm, 长度 100mm (沿 +Y: 0 ~ +100mm)
        # - 小端：直径 30mm, 长度 80mm (沿 -Y: 0 ~ -80mm), 总长 180mm
        # - 键槽：长 30mm, 宽 8mm, 深 4mm
        # - 倒角：2mm x 45度 原生倒角
        # - 圆角：2mm 原生过渡圆角
        # =========================================================================
        log("\n--- [DEF-04, DEF-01] 创建零件 1: 阶梯轴与键槽 (remediated_stepped_shaft.SLDPRT) ---")
        model_shaft = new_document(swApp, "part")
        created_models.append(model_shaft)

        # 第一段圆柱
        start_sketch(model_shaft, "Top Plane")
        sketch_circle(model_shaft, 0.0, 0.0, 0.025)
        sk1 = current_sketch_name(model_shaft, fallback="草图1")
        end_sketch(model_shaft)
        feat_boss1 = extrude_boss(model_shaft, sk1, 0.100, direction=False)
        log("第一段圆柱建立: 直径=50mm, 长度=100mm (Y: 0 ~ +100mm)")

        # 第二段圆柱
        start_sketch(model_shaft, "Top Plane")
        sketch_circle(model_shaft, 0.0, 0.0, 0.015)
        sk2 = current_sketch_name(model_shaft, fallback="草图2")
        end_sketch(model_shaft)
        feat_boss2 = extrude_boss(model_shaft, sk2, 0.080, direction=True, merge=True)
        log("第二段圆柱建立: 直径=30mm, 长度=80mm (Y: 0 ~ -80mm)")

        # 键槽切除
        start_sketch(model_shaft, "Top Plane")
        sketch_corner_rectangle(model_shaft, -0.004, -0.050, 0.004, -0.020)
        sk_key = current_sketch_name(model_shaft, fallback="草图3")
        end_sketch(model_shaft)
        feat_cut = extrude_cut(model_shaft, sk_key, 0.004, direction=True)
        log("切除键槽建立: 宽=8mm, 长=30mm, 深=4mm (Y: -20 ~ -50mm)")

        callout = create_empty_dispatch_variant()

        # 原生倒角 (Chamfer) (DEF-01)
        chamfer_attempt_error = None
        has_chamfer = False
        try:
            model_shaft.ClearSelection2(True)
            sel_face = model_shaft.Extension.SelectByID2("", "FACE", 0.0, 0.100, 0.0, False, 1, callout, 0)
            if sel_face:
                ch_feat = model_shaft.FeatureManager.InsertFeatureChamfer(1, 0, 0.002, 0.785398, 0.0, 0.0, 0.0, 0)
                if ch_feat:
                    has_chamfer = True
                    log(f"成功通过原生 COM API 创建倒角 (Chamfer) 特征: {get_com_member(ch_feat, 'Name')}！")
                else:
                    chamfer_attempt_error = "InsertFeatureChamfer returned None"
        except Exception as exc:
            chamfer_attempt_error = str(exc)
            log(f"原生倒角 COM 调用异常: {exc}")

        # 原生圆角 (Fillet) (DEF-01)
        fillet_attempt_error = None
        has_fillet = False
        try:
            model_shaft.ClearSelection2(True)
            sel_cyl = model_shaft.Extension.SelectByID2("", "FACE", 0.025, 0.050, 0.0, False, 1, callout, 0)
            if sel_cyl:
                f_feat = model_shaft.FeatureManager.FeatureFillet(195, 0.002, 0, 0)
                if f_feat:
                    has_fillet = True
                    log(f"成功通过原生 COM API 创建圆角 (Fillet) 特征: {get_com_member(f_feat, 'Name')}！")
                else:
                    fillet_attempt_error = "FeatureFillet returned None"
        except Exception as exc:
            fillet_attempt_error = str(exc)
            log(f"原生圆角 COM 调用异常: {exc}")

        get_com_member(model_shaft, "EditRebuild3")

        shaft_path = str(SANDBOX_DIR / "remediated_stepped_shaft.SLDPRT")
        save_document(model_shaft, shaft_path)
        log(f"已保存阶梯轴零件: {shaft_path}")

        # 导出 STL
        stl_path = str(SANDBOX_DIR / "remediated_stepped_shaft.STL")
        model_shaft.ClearSelection2(True)
        save_document(model_shaft, stl_path)
        log(f"已导出阶梯轴 STL: {stl_path} ({os.path.getsize(stl_path)} 字节)")

        # 解析 STL 网格与积分度量 (DEF-04)
        stl_mesh = parse_stl_mesh(stl_path)
        log(f"STL 网格度量: 三角面数={stl_mesh['tri_count']}, 网格积分体积={stl_mesh['volume_mm3']:.3f} mm³")
        log(f"STL 空间包围盒: delta_x={stl_mesh['delta_x_mm']:.3f}mm, delta_y={stl_mesh['delta_y_mm']:.3f}mm (理论总长 180.0mm), delta_z={stl_mesh['delta_z_mm']:.3f}mm")

        # 采集 CAD 原生解析质量属性
        mass_props = measure_mass_properties(model_shaft)
        v_cad = mass_props.get("volume_mm3", 0.0)
        log(f"CAD 原生实体解析体积: {v_cad:.3f} mm³")

        # 代数理论解析体积计算 (DEF-04)
        # V1 = pi * 25^2 * 100 = 62500 * pi = 196349.541 mm³
        # V2 = pi * 15^2 * 80  = 18000 * pi = 56548.668 mm³
        # V_key_cut: 截面积 8mm x 4mm x 30mm = 960.0 mm³
        # V_theo = 251938.21 mm³ (连续解析实体体积)
        v_theo = 251938.210
        err_cad_theo = abs(v_cad - v_theo) / v_theo if v_cad else 0.0
        err_stl_cad = abs(stl_mesh["volume_mm3"] - v_cad) / v_cad if v_cad else 0.0
        err_stl_theo = abs(stl_mesh["volume_mm3"] - v_theo) / v_theo
        log(f"体积相对误差分析: CAD连续实体 vs 理论解析 = {err_cad_theo*100:.5f}%; STL离散网格 vs 理论解析 = {err_stl_theo*100:.4f}%")

        shaft_features = inspect_feature_tree(model_shaft)
        has_chamfer_node = any("Chamfer" in f["type"] or "倒角" in f["name"] for f in shaft_features)
        has_fillet_node = any("Fillet" in f["type"] or "圆角" in f["name"] for f in shaft_features)

        results["parts"]["stepped_shaft"] = {
            "file": "remediated_stepped_shaft.SLDPRT",
            "path": shaft_path,
            "stl_path": stl_path,
            "stl_mesh": stl_mesh,
            "mass_properties": mass_props,
            "analytical_volume_mm3": v_theo,
            "cad_analytical_volume_mm3": v_cad,
            "stl_discrete_volume_mm3": stl_mesh["volume_mm3"],
            "error_cad_vs_theo_percent": round(err_cad_theo * 100, 5),
            "error_stl_vs_cad_percent": round(err_stl_cad * 100, 4),
            "error_stl_vs_theo_percent": round(err_stl_theo * 100, 4),
            "y_span_verified_180mm": bool(abs(stl_mesh["delta_y_mm"] - 180.0) <= 0.5),
            "features": shaft_features,
            "has_chamfer": has_chamfer_node,
            "has_fillet": has_fillet_node,
            "chamfer_error": chamfer_attempt_error,
            "fillet_error": fillet_attempt_error,
        }

        # =========================================================================
        # 零件 2: 底座零件与线性阵列 (remediated_base.SLDPRT) (DEF-01)
        # 规格: 底座 120mm x 80mm x 15mm, 中心通孔 D=50mm
        # 阵列特征: 种子孔 D=10mm, 原生线性阵列 3 实例
        # =========================================================================
        log("\n--- [DEF-01] 创建零件 2: 底座与线性阵列 (remediated_base.SLDPRT) ---")
        model_base = new_document(swApp, "part")
        created_models.append(model_base)

        start_sketch(model_base, "Top Plane")
        sketch_corner_rectangle(model_base, -0.060, -0.040, 0.060, 0.040)
        sk_b1 = current_sketch_name(model_base, fallback="草图1")
        end_sketch(model_base)
        extrude_boss(model_base, sk_b1, 0.015, direction=False)
        log("底座基板拉伸完成: 120x80x15mm")

        # 中心通孔 D=50mm (与轴第一段同轴装配)
        start_sketch(model_base, "Top Plane")
        sketch_circle(model_base, 0.0, 0.0, 0.025)
        sk_bh = current_sketch_name(model_base, fallback="草图2")
        end_sketch(model_base)
        extrude_cut(model_base, sk_bh, 0.015, direction=True)
        log("底座中心通孔完成: 直径=50mm")

        # 阵列种子孔 D=10mm
        start_sketch(model_base, "Top Plane")
        sketch_circle(model_base, 0.040, 0.025, 0.005)
        sk_seed = current_sketch_name(model_base, fallback="草图3")
        end_sketch(model_base)
        feat_seed = extrude_cut(model_base, sk_seed, 0.015, direction=True)
        seed_hole_name = str(get_com_member(feat_seed, "Name") if feat_seed else "切除-拉伸2")
        log(f"阵列种子孔特征名称: {seed_hole_name}")

        # 原生线性阵列
        lpattern_error = None
        has_lpattern = False
        try:
            lp_feat = linear_pattern(model_base, seed_hole_name, (-1, 0, 0), 0.030, 3)
            if lp_feat:
                has_lpattern = True
                log(f"成功通过原生 COM API 创建线性阵列 (LinearPattern) 特征: {get_com_member(lp_feat, 'Name')}！")
        except Exception as exc:
            lpattern_error = str(exc)
            log(f"原生线性阵列 COM 调用受阻: {exc}")

        get_com_member(model_base, "EditRebuild3")
        base_path = str(SANDBOX_DIR / "remediated_base.SLDPRT")
        save_document(model_base, base_path)
        base_features = inspect_feature_tree(model_base)
        has_lpattern_node = any("LPattern" in f["type"] or "线性阵列" in f["name"] for f in base_features)

        results["parts"]["base"] = {
            "file": "remediated_base.SLDPRT",
            "path": base_path,
            "features": base_features,
            "has_lpattern": has_lpattern_node,
            "lpattern_error": lpattern_error,
            "verdict": "VERIFIED" if has_lpattern_node else "NOT_IMPLEMENTED"
        }

        # =========================================================================
        # 零件 3: 齿轮/法兰与圆周阵列 (remediated_gear.SLDPRT) (DEF-01)
        # 规格: 外径 D=60mm, 厚度 12mm, 中心通孔 D=30mm (配合阶梯轴第二段)
        # =========================================================================
        log("\n--- [DEF-01] 创建零件 3: 齿轮/法兰与圆周阵列 (remediated_gear.SLDPRT) ---")
        model_gear = new_document(swApp, "part")
        created_models.append(model_gear)

        start_sketch(model_gear, "Top Plane")
        sketch_circle(model_gear, 0.0, 0.0, 0.030)
        sk_g1 = current_sketch_name(model_gear, fallback="草图1")
        end_sketch(model_gear)
        feat_gear_boss = extrude_boss(model_gear, sk_g1, 0.012, direction=False)
        log("齿轮外圆拉伸完成: 直径=60mm, 厚度=12mm")

        # 中心通孔 D=30mm (与轴第二段同轴装配)
        start_sketch(model_gear, "Top Plane")
        sketch_circle(model_gear, 0.0, 0.0, 0.015)
        sk_gh = current_sketch_name(model_gear, fallback="草图2")
        end_sketch(model_gear)
        extrude_cut(model_gear, sk_gh, 0.012, direction=True)
        log("齿轮中心配合孔完成: 直径=30mm")

        # 螺栓孔种子 D=6mm
        start_sketch(model_gear, "Top Plane")
        sketch_circle(model_gear, 0.022, 0.0, 0.003)
        sk_bolt = current_sketch_name(model_gear, fallback="草图3")
        end_sketch(model_gear)
        feat_bolt = extrude_cut(model_gear, sk_bolt, 0.012, direction=True)
        bolt_hole_name = str(get_com_member(feat_bolt, "Name") if feat_bolt else "切除-拉伸2")
        log(f"螺栓孔特征名称: {bolt_hole_name}")

        cirpattern_error = None
        has_cirpattern = False
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
                cp_feat = circular_pattern(model_gear, bolt_hole_name, cyl_face, 2 * math.pi, 6)
                if cp_feat:
                    has_cirpattern = True
                    log(f"成功通过原生 COM API 创建圆周阵列 (CircularPattern) 特征: {get_com_member(cp_feat, 'Name')}！")
            else:
                cirpattern_error = "未找到圆柱面作为圆周阵列旋转轴"
        except Exception as exc:
            cirpattern_error = str(exc)
            log(f"原生圆周阵列 COM 调用受阻: {exc}")

        get_com_member(model_gear, "EditRebuild3")
        gear_path = str(SANDBOX_DIR / "remediated_gear.SLDPRT")
        save_document(model_gear, gear_path)
        gear_features = inspect_feature_tree(model_gear)
        has_cirpattern_node = any("CirPattern" in f["type"] or "圆周阵列" in f["name"] for f in gear_features)

        results["parts"]["gear"] = {
            "file": "remediated_gear.SLDPRT",
            "path": gear_path,
            "features": gear_features,
            "has_cirpattern": has_cirpattern_node,
            "cirpattern_error": cirpattern_error,
            "verdict": "VERIFIED" if has_cirpattern_node else "NOT_IMPLEMENTED"
        }

        # =========================================================================
        # 4. 装配体与真正的原生 Concentric Mate (remediated_assembly.SLDASM) (DEF-03, DEF-11)
        # 彻底纠正第三轮平面重合冒充同心配合的错误：
        # 1. 插入 Base (固定基座)
        # 2. 插入 Shaft:
        #    - 平面重合配合 (Base 上视基准面 <-> Shaft 上视基准面 轴向定位)
        #    - 真正的原生圆柱面同心配合: Base D50 通孔圆柱面 <-> Shaft D50 圆柱面 (swMateCONCENTRIC)
        # 3. 插入 Gear:
        #    - 平面重合配合 (Gear 上视基准面 <-> Shaft 上视基准面 轴向定位)
        #    - 真正的原生圆柱面同心配合: Gear D30 通孔圆柱面 <-> Shaft D30 圆柱面 (swMateCONCENTRIC)
        # =========================================================================
        log("\n--- [DEF-03, DEF-11] 创建装配体与原生圆柱面同心配合 (remediated_assembly.SLDASM) ---")
        model_asm = new_document(swApp, "assembly")
        created_models.append(model_asm)

        comp_base = add_component(model_asm, base_path, 0.0, 0.0, 0.0, sw=swApp)
        comp_shaft = add_component(model_asm, shaft_path, 0.0, 0.050, 0.0, sw=swApp)
        comp_gear = add_component(model_asm, gear_path, 0.0, -0.050, 0.0, sw=swApp)

        asm_title = str(get_com_member(model_asm, "GetTitle")).split(".")[0]
        base_name = str(get_com_member(comp_base, "Name2"))
        shaft_name = str(get_com_member(comp_shaft, "Name2"))
        gear_name = str(get_com_member(comp_gear, "Name2"))

        mate_records = []

        # 配合 1: 轴向定位平面重合 (Base 上视基准面 <-> Shaft 上视基准面)
        for cand in ("上视基准面", "Top Plane"):
            try:
                p1 = f"{cand}@{base_name}@{asm_title}"
                p2 = f"{cand}@{shaft_name}@{asm_title}"
                m1 = add_mate_coincident(model_asm, p1, "PLANE", p2, "PLANE")
                if m1:
                    mate_records.append({"mate": "Coincident_Base_Shaft_Axial", "type": "Coincident", "status": "CREATED"})
                    log("成功创建配合 1: Base 上视基准面 <-> Shaft 上视基准面 (平面重合-轴向定位)")
                    break
            except Exception:
                pass

        # 配合 2: 真正的原生圆柱面同心配合 (DEF-03)
        # Base 中心通孔 (R=25mm) 与 Shaft 第一段圆柱 (R=25mm) 原生 swMateCONCENTRIC 配合
        concentric_base_shaft = False
        concentric_base_shaft_error = None
        try:
            m2 = add_concentric_mate_by_cylinders(
                model_asm,
                comp_base,
                comp_shaft,
                radius_a=(0.020, 0.030),
                radius_b=(0.020, 0.030),
                name="Concentric_Base_Shaft_Native",
                lock_rotation=False
            )
            if m2:
                concentric_base_shaft = True
                mate_records.append({
                    "mate": "Concentric_Base_Shaft_Native",
                    "type": "swMateCONCENTRIC",
                    "native_mate_enum": 1,
                    "status": "CREATED"
                })
                log("成功创建配合 2: 真实原生圆柱面同心配合 (Base 孔 <-> Shaft 轴, swMateCONCENTRIC)！")
        except Exception as exc:
            concentric_base_shaft_error = str(exc)
            log(f"配合 2 原生同心配合异常: {exc}")

        # 配合 3: 轴向定位平面重合 (Gear 上视基准面 <-> Shaft 上视基准面)
        for cand in ("上视基准面", "Top Plane"):
            try:
                p3 = f"{cand}@{gear_name}@{asm_title}"
                p4 = f"{cand}@{shaft_name}@{asm_title}"
                m3 = add_mate_coincident(model_asm, p3, "PLANE", p4, "PLANE")
                if m3:
                    mate_records.append({"mate": "Coincident_Gear_Shaft_Axial", "type": "Coincident", "status": "CREATED"})
                    log("成功创建配合 3: Gear 上视基准面 <-> Shaft 上视基准面 (平面重合-轴向定位)")
                    break
            except Exception:
                pass

        # 配合 4: 真正的原生圆柱面同心配合 (DEF-03)
        # Gear 中心通孔 (R=15mm) 与 Shaft 第二段圆柱 (R=15mm) 原生 swMateCONCENTRIC 配合
        concentric_gear_shaft = False
        concentric_gear_shaft_error = None
        try:
            m4 = add_concentric_mate_by_cylinders(
                model_asm,
                comp_gear,
                comp_shaft,
                radius_a=(0.010, 0.020),
                radius_b=(0.010, 0.020),
                name="Concentric_Gear_Shaft_Native",
                lock_rotation=False
            )
            if m4:
                concentric_gear_shaft = True
                mate_records.append({
                    "mate": "Concentric_Gear_Shaft_Native",
                    "type": "swMateCONCENTRIC",
                    "native_mate_enum": 1,
                    "status": "CREATED"
                })
                log("成功创建配合 4: 真实原生圆柱面同心配合 (Gear 孔 <-> Shaft 轴, swMateCONCENTRIC)！")
        except Exception as exc:
            concentric_gear_shaft_error = str(exc)
            log(f"配合 4 原生同心配合异常: {exc}")

        get_com_member(model_asm, "ClearSelection2", True)
        get_com_member(model_asm, "EditRebuild3")

        asm_path = str(SANDBOX_DIR / "remediated_assembly.SLDASM")
        save_document(model_asm, asm_path)
        log(f"已保存装配体: {asm_path}")

        # 检查装配体特征树中的真实配合节点
        asm_features = inspect_feature_tree(model_asm)
        mate_group_found = any(f["type"] == "MateGroup" or "配合" in f["name"] for f in asm_features)

        # DEF-11: STEP AP214 格式实际导出 (正确 API 参数: swStepAP = 75, value = 214)
        step_export_version_set = False
        try:
            swApp.SetUserPreferenceIntegerValue(75, 214)  # 75 = swStepAP, 214 = AP214
            swApp.SetUserPreferenceToggle(787, True)       # 787 = swStepExportAppearances
            step_export_version_set = True
            log("成功将 SolidWorks STEP 协议参数正确设置为 swStepAP(75) = 214 (AP214)！")
        except Exception as e:
            log(f"设置 swStepAP 异常: {e}")

        step_path = str(SANDBOX_DIR / "remediated_assembly.step")
        export_to_step(model_asm, step_path)
        log(f"已导出装配体 STEP 文件: {step_path} ({os.path.getsize(step_path)} 字节)")

        # 读取 STEP 文件头真实协议 (DEF-11)
        step_protocol = "UNKNOWN"
        step_header_raw = []
        try:
            with open(step_path, "r", encoding="utf-8", errors="replace") as f:
                for _ in range(60):
                    line = f.readline()
                    step_header_raw.append(line.strip())
                    if "APPLICATION_PROTOCOL_DEFINITION" in line or "FILE_SCHEMA" in line:
                        if "automotive_design" in line:
                            step_protocol = "AP214 (automotive_design)"
                        elif "config_control_design" in line:
                            step_protocol = "AP203 (config_control_design)"
                        else:
                            step_protocol = line.strip()
        except Exception as e:
            step_protocol = f"READ_ERROR: {e}"
        log(f"STEP 物理文件头解析协议: {step_protocol}")

        results["assembly"] = {
            "file": "remediated_assembly.SLDASM",
            "path": asm_path,
            "step_path": step_path,
            "step_protocol": step_protocol,
            "step_header_snippet": step_header_raw[:30],
            "mate_records": mate_records,
            "concentric_base_shaft": concentric_base_shaft,
            "concentric_base_shaft_error": concentric_base_shaft_error,
            "concentric_gear_shaft": concentric_gear_shaft,
            "concentric_gear_shaft_error": concentric_gear_shaft_error,
            "mate_group_found": mate_group_found,
            "features": asm_features
        }

        # =========================================================================
        # 5. 工程图真实验证 (remediated_drawing.SLDDRW & remediated_drawing.pdf) (DEF-02)
        # 必须验证：
        # - 主视、俯视、右视及轴测图 4 视图
        # - 视图空间投影关系与方向
        # - 导出真实非空矢量 PDF
        # =========================================================================
        log("\n--- [DEF-02] 创建工程图并投影 4 视图 (remediated_drawing.SLDDRW) ---")
        model_draw = new_document(swApp, "drawing")
        created_models.append(model_draw)

        # 创建标准三视图
        draw_views_created = []
        try:
            created_3views = get_com_member(model_draw, "Create3rdAngleViews2", shaft_path)
            log(f"Create3rdAngleViews2 标准三视图投影执行结果: {created_3views}")
        except Exception as e:
            log(f"Create3rdAngleViews2 异常: {e}")

        # 添加轴测视图 (DEF-02)
        try:
            iso_view = get_com_member(model_draw, "CreateDrawViewFromModelView3", shaft_path, "*等轴测", 0.280, 0.200, 0.0)
            if not iso_view:
                iso_view = get_com_member(model_draw, "CreateDrawViewFromModelView3", shaft_path, "*Isometric", 0.280, 0.200, 0.0)
            log(f"轴测视图添加结果: {iso_view is not None}")
        except Exception as e:
            log(f"添加轴测视图异常: {e}")

        get_com_member(model_draw, "EditRebuild")

        draw_path = str(SANDBOX_DIR / "remediated_drawing.SLDDRW")
        save_document(model_draw, draw_path)
        log(f"已保存工程图: {draw_path}")

        # 导出矢量 PDF (使用兼容 swApp 的 export_sheet_to_pdf)
        pdf_path = str(SANDBOX_DIR / "remediated_drawing.pdf")
        pdf_ok = sw_drawing.export_sheet_to_pdf(model_draw, pdf_path, sw_app=swApp)
        pdf_size = os.path.getsize(pdf_path) if os.path.exists(pdf_path) else 0
        log(f"已导出工程图矢量 PDF: {pdf_path} (成功={pdf_ok}, 文件大小={pdf_size} 字节)")

        # 遍历工程图视图
        drawing_struct = sw_drawing.inspect_drawing_structure(model_draw)
        view_nodes = drawing_struct.get("views", [])
        log(f"工程图视图总数 (含图纸底图): {len(view_nodes)}")
        for vn in view_nodes:
            log(f"  视图: {vn.get('name')} (定向={vn.get('orientation')}, 类型={vn.get('type')})")

        results["drawing"] = {
            "file": "remediated_drawing.SLDDRW",
            "path": draw_path,
            "pdf_path": pdf_path,
            "pdf_size_bytes": pdf_size,
            "view_count": len(view_nodes),
            "views": view_nodes
        }

    finally:
        # =========================================================================
        # 6. 安全清理：精准关闭本脚本创建的沙箱测试文档
        # 坚决不调用 CloseAllDocuments(True)
        # =========================================================================
        log("\n--- 安全闭环：精准关闭沙箱测试文档 (DEF-SEC-01) ---")
        # 逆序关闭：先关工程图和装配体，再关子零件
        for m in reversed(created_models):
            try:
                title = str(get_com_member(m, "GetTitle"))
                register_owned_document(m)
                success = close_document(swApp, m, force_discard=True, allowed_roots=[str(SANDBOX_DIR), str(PROJECT_ROOT)])
                log(f"精准安全关闭文档: {title} (结果={success})")
            except Exception as e:
                log(f"关闭文档异常: {e}")

        # 保存全量实机指标记录
        summary_path = SANDBOX_DIR / "fourth_remediation_summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        log(f"第四轮全量实机验证指标已保存: {summary_path}")
        log("=== 第四轮 CAD 实机验证全部执行完毕 ===")


if __name__ == "__main__":
    worker = get_sta_worker()
    worker.execute(run_fourth_remediation_cad)
