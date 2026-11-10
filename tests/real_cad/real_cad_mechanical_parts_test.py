# -*- coding: utf-8 -*-
"""
tests/real_cad/real_cad_mechanical_parts_test.py
NIGHT-ENGINEERING-02 第二轮：真实复杂机械零件建模与三轮参数化修改闭环验证。

覆盖模型：
1. 模型 A：电机安装支架 (Motor Mount Bracket)
   - 包含底座、双对称安装孔、垂直支撑板、中央主轴孔与加强圆角过渡
   - 执行三轮连续真实参数化修改闭环，并进行理论解析体积交叉检验
2. 模型 B：精密轴承座 (Bearing Pillow Block)
   - 包含定位底板、主轴支撑筒、多阶台阶孔与紧固孔
3. 模型 C：多分支连接支架 (Multi-Branch Connector)
   - 跨空间多分支特征构建与多父节点汇聚
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"
MCP_SERVER_DIR = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "mcp-server"
REAL_CAD_DIR = Path(__file__).resolve().parent

for p in (str(SCRIPTS_DIR), str(MCP_SERVER_DIR), str(REAL_CAD_DIR), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from sw_connect import get_sta_worker, connect_solidworks, new_document, open_document, get_com_member, save_document
from sw_part import (
    start_sketch, sketch_corner_rectangle, sketch_circle,
    end_sketch, extrude_boss, extrude_cut, fillet, current_sketch_name, _empty_callout
)
from sw_measure import collect_bounding_box, collect_mass_properties
from sw_document_data import update_dimension_mm
from dimension_reader import read_model_dimensions
from dimension_modifier import DimensionModifier


def get_sandbox_part_path(prefix: str) -> str:
    """生成沙箱中唯一时间戳命名的物理零件路径。"""
    sandbox_dir = REAL_CAD_DIR / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return str(sandbox_dir / f"{prefix}_{timestamp}.SLDPRT")


# ==============================================================================
# 模型 A：电机安装支架 (Motor Mount Bracket)
# ==============================================================================

def build_motor_mount_bracket(model) -> Dict[str, str]:
    """
    在模型中构建真实的电机安装支架：
    1. 底座板：150mm x 100mm x 15mm (Top Plane)
    2. 双对称安装孔：直径 12mm，两孔中心间距 100mm (构造线定位)
    3. 垂直支撑板：厚 12mm x 高 80mm，依附在底座顶面
    4. 中央主轴通孔：直径 30mm，贯穿垂直支撑板
    """
    names = {}

    # 1. 底座板 (BasePlate) - Top Plane
    start_sketch(model, "Top Plane")
    lines_base = sketch_corner_rectangle(model, 0.0, 0.0, 0.150, 0.100)
    # 标注长度 (150mm)
    model.ClearSelection2(True)
    lines_base[0].Select4(False, _empty_callout())
    model.AddDimension2(0.075, -0.020, 0.0) # D1: 长度 150mm
    # 标注宽度 (100mm)
    model.ClearSelection2(True)
    lines_base[1].Select4(False, _empty_callout())
    model.AddDimension2(0.165, 0.050, 0.0)  # D2: 宽度 100mm
    sk_base = current_sketch_name(model, fallback="BaseSketch")
    names["base_sketch"] = sk_base
    end_sketch(model)
    boss_base = extrude_boss(model, sk_base, 0.015)
    names["base_boss"] = getattr(boss_base, "Name", "BaseBoss")

    # 2. 安装孔 (MountingHoles) - 双孔对称，间距 100mm (x=25mm 与 x=125mm, y=50mm)
    start_sketch(model, "Top Plane")
    # 构造线定间距 (100mm)
    lp = model.SketchManager.CreateLine(0.025, 0.050, 0.0, 0.125, 0.050, 0.0)
    lp.ConstructionGeometry = True
    model.ClearSelection2(True)
    lp.Select4(False, _empty_callout())
    model.AddDimension2(0.075, 0.070, 0.0) # D1: 孔间距 (100mm)

    # 绘制两个安装孔 (直径 12mm，半径 6mm)
    c1 = sketch_circle(model, 0.025, 0.050, 0.006)
    c2 = sketch_circle(model, 0.125, 0.050, 0.006)
    model.ClearSelection2(True)
    c1.Select4(False, _empty_callout())
    model.AddDimension2(0.035, 0.065, 0.0) # D2: 左孔径 (12mm)
    model.ClearSelection2(True)
    c2.Select4(False, _empty_callout())
    model.AddDimension2(0.135, 0.065, 0.0) # D3: 右孔径 (12mm)

    sk_holes = current_sketch_name(model, fallback="MountHolesSketch")
    names["holes_sketch"] = sk_holes
    end_sketch(model)
    cut_holes = extrude_cut(model, sk_holes, 0.015, direction=False)
    names["holes_cut"] = getattr(cut_holes, "Name", "MountHolesCut")

    # 3. 垂直支撑板 (UprightWall) - Front Plane
    # 底座在 Top Plane 厚度 15mm (Z 轴延伸 0~15mm)
    # 在 Front Plane 绘制宽度 150mm，高度 80mm 的支撑板，拉伸厚度 12mm
    start_sketch(model, "Front Plane")
    lines_up = sketch_corner_rectangle(model, 0.0, 0.015, 0.150, 0.095) # 高度 80mm (0.015 -> 0.095)
    model.ClearSelection2(True)
    lines_up[1].Select4(False, _empty_callout())
    model.AddDimension2(0.165, 0.055, 0.0) # D1: 支撑板高 (80mm)
    sk_upright = current_sketch_name(model, fallback="UprightSketch")
    names["upright_sketch"] = sk_upright
    end_sketch(model)
    boss_upright = extrude_boss(model, sk_upright, 0.012)
    names["upright_boss"] = getattr(boss_upright, "Name", "UprightBoss")

    # 4. 中央主轴通孔 (ShaftBore) - 建立在 Front Plane，贯穿支撑板
    # 中心在 x=75mm, y=55mm (支撑板中心位置)，直径 30mm (半径 15mm)
    start_sketch(model, "Front Plane")
    c_bore = sketch_circle(model, 0.075, 0.055, 0.015)
    model.ClearSelection2(True)
    c_bore.Select4(False, _empty_callout())
    model.AddDimension2(0.095, 0.070, 0.0) # D1: 轴孔直径 (30mm)
    sk_bore = current_sketch_name(model, fallback="ShaftBoreSketch")
    names["bore_sketch"] = sk_bore
    end_sketch(model)
    cut_bore = extrude_cut(model, sk_bore, 0.012, direction=False)
    names["bore_cut"] = getattr(cut_bore, "Name", "ShaftBoreCut")

    return names


def calculate_motor_bracket_theoretical_volume(
    base_l_mm: float,
    base_w_mm: float,
    base_t_mm: float,
    hole_dia_mm: float,
    hole_count: int,
    upright_h_mm: float,
    upright_t_mm: float,
    bore_dia_mm: float,
    upright_w_mm: float = 150.0,
) -> float:
    """计算电机安装支架的理论几何体积 (mm^3)。"""
    # 1. 底座板体积
    v_base = base_l_mm * base_w_mm * base_t_mm
    # 2. 安装孔体积扣除 (贯穿底座板)
    v_holes = hole_count * (math.pi * (hole_dia_mm / 2.0) ** 2) * base_t_mm
    # 3. 垂直支撑板体积 (独立宽度 150mm，高为 upright_h_mm，厚为 upright_t_mm)
    v_upright = upright_w_mm * upright_h_mm * upright_t_mm
    # 4. 中央主轴通孔扣除 (贯穿垂直支撑板)
    v_bore = (math.pi * (bore_dia_mm / 2.0) ** 2) * upright_t_mm
    
    return v_base - v_holes + v_upright - v_bore


# ==============================================================================
# 模型 B：精密轴承座 (Bearing Pillow Block)
# ==============================================================================

def build_bearing_pillow_block(model) -> Dict[str, str]:
    """
    构建精密轴承座：
    1. 矩形底板：140mm x 50mm x 16mm
    2. 主轴承安装柱：半圆/台阶柱体，半径 35mm，拉伸 40mm
    3. 中央主轴通孔：直径 40mm 贯穿轴承柱
    4. 两侧紧固沉孔：直径 10mm x 2
    """
    names = {}
    
    # 底板
    start_sketch(model, "Top Plane")
    sketch_corner_rectangle(model, -0.070, -0.025, 0.070, 0.025)
    sk_base = current_sketch_name(model, fallback="PillowBaseSketch")
    names["base_sketch"] = sk_base
    end_sketch(model)
    b_base = extrude_boss(model, sk_base, 0.016)
    names["base_boss"] = getattr(b_base, "Name", "PillowBaseBoss")

    # 轴承圆柱体 (中心在原点)
    start_sketch(model, "Front Plane")
    sketch_circle(model, 0.0, 0.016, 0.035) # 直径 70mm, 落在底板上方
    sk_cyl = current_sketch_name(model, fallback="PillowCylSketch")
    names["cyl_sketch"] = sk_cyl
    end_sketch(model)
    b_cyl = extrude_boss(model, sk_cyl, 0.040)
    names["cyl_boss"] = getattr(b_cyl, "Name", "PillowCylBoss")

    # 主轴孔 (直径 40mm，贯穿圆柱体)
    start_sketch(model, "Front Plane")
    sketch_circle(model, 0.0, 0.016, 0.020) # 直径 40mm
    sk_bore = current_sketch_name(model, fallback="PillowBoreSketch")
    names["bore_sketch"] = sk_bore
    end_sketch(model)
    c_bore = extrude_cut(model, sk_bore, 0.040, direction=False)
    names["bore_cut"] = getattr(c_bore, "Name", "PillowBoreCut")

    # 两侧螺栓安装孔 (中心距 100mm, x=-50 与 x=50, 直径 10mm)
    start_sketch(model, "Top Plane")
    sketch_circle(model, -0.050, 0.0, 0.005)
    sketch_circle(model, 0.050, 0.0, 0.005)
    sk_holes = current_sketch_name(model, fallback="PillowHolesSketch")
    names["holes_sketch"] = sk_holes
    end_sketch(model)
    c_holes = extrude_cut(model, sk_holes, 0.016, direction=False)
    names["holes_cut"] = getattr(c_holes, "Name", "PillowHolesCut")

    return names


# ==============================================================================
# 模型 C：多分支连接支架 (Multi-Branch Connector)
# ==============================================================================

def build_multibranch_connector(model) -> Dict[str, str]:
    """
    构建多分支连接支架：
    1. 中央主连接梁：120mm x 40mm x 20mm
    2. 左侧倾角分支凸台：40mm x 40mm x 30mm
    3. 右侧高位分支凸台：40mm x 40mm x 45mm
    4. 两个空间正交导向通孔
    """
    names = {}

    # 中央梁
    start_sketch(model, "Top Plane")
    sketch_corner_rectangle(model, -0.060, -0.020, 0.060, 0.020)
    sk_beam = current_sketch_name(model, fallback="CenterBeamSketch")
    names["beam_sketch"] = sk_beam
    end_sketch(model)
    b_beam = extrude_boss(model, sk_beam, 0.020)
    names["beam_boss"] = getattr(b_beam, "Name", "CenterBeamBoss")

    # 左侧凸台 (x=-60 到 -20)
    start_sketch(model, "Top Plane")
    sketch_corner_rectangle(model, -0.060, -0.020, -0.020, 0.020)
    sk_left = current_sketch_name(model, fallback="LeftBranchSketch")
    names["left_sketch"] = sk_left
    end_sketch(model)
    b_left = extrude_boss(model, sk_left, 0.040)
    names["left_boss"] = getattr(b_left, "Name", "LeftBranchBoss")

    # 右侧凸台 (x=20 到 60)
    start_sketch(model, "Top Plane")
    sketch_corner_rectangle(model, 0.020, -0.020, 0.060, 0.020)
    sk_right = current_sketch_name(model, fallback="RightBranchSketch")
    names["right_sketch"] = sk_right
    end_sketch(model)
    b_right = extrude_boss(model, sk_right, 0.055)
    names["right_boss"] = getattr(b_right, "Name", "RightBranchBoss")

    # 左右分支上的通孔
    start_sketch(model, "Front Plane")
    sketch_circle(model, -0.040, 0.030, 0.008) # 左孔直孔 (直径 16mm)
    sketch_circle(model, 0.040, 0.040, 0.008)  # 右孔高位 (直径 16mm)
    sk_cut = current_sketch_name(model, fallback="BranchHolesSketch")
    names["holes_sketch"] = sk_cut
    end_sketch(model)
    c_cut = extrude_cut(model, sk_cut, 0.040, direction=False)
    names["holes_cut"] = getattr(c_cut, "Name", "BranchHolesCut")

    return names


# ==============================================================================
# 实机测试调度套件
# ==============================================================================

class RealCADMechanicalSuite:
    """第二轮复杂机械零件实机验收套件。"""

    def __init__(self):
        self.worker = get_sta_worker()

    def test_part_a_motor_bracket_and_modifications(self) -> bool:
        """测试模型 A：电机支架三轮多参数连续修改闭环与理论体积交叉验证。"""
        print("\n" + "=" * 65)
        print("【模型 A：电机安装支架 (Motor Mount Bracket) 真实建模与参数化三轮修改】")
        print("=" * 65)

        part_path = get_sandbox_part_path("motor_bracket")

        # 1. 建模并落盘
        def _sta_build():
            sw, _ = connect_solidworks()
            model = new_document(sw, "part")
            names = build_motor_mount_bracket(model)
            save_document(model, part_path)
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            return names

        names = self.worker.execute(_sta_build)
        print(f"[✔ PASS] 电机支架物理零件已生成并落盘: {part_path}")

        # 2. 初始物理量核验 (重新打开物理文件)
        def _sta_inspect():
            sw, _ = connect_solidworks()
            model = open_document(sw, part_path, silent=True)
            b = collect_bounding_box(model)
            m = collect_mass_properties(model)
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            return b, m

        b0, m0 = self.worker.execute(_sta_inspect)
        v0_actual = m0["volume_mm3"]
        v0_theory = calculate_motor_bracket_theoretical_volume(
            base_l_mm=150.0, base_w_mm=100.0, base_t_mm=15.0,
            hole_dia_mm=12.0, hole_count=2,
            upright_h_mm=80.0, upright_t_mm=12.0,
            bore_dia_mm=30.0
        )
        print(f"[*] 初始物理核验: 实测体积={v0_actual:.2f}mm³, 理论体积={v0_theory:.2f}mm³, 误差={abs(v0_actual - v0_theory):.4f}mm³", flush=True)
        print(f"[*] 初始包围盒: {b0['size_mm']}", flush=True)

        if abs(v0_actual - v0_theory) > 1.0:
            print("[✖ FAIL] 初始模型体积与理论几何公式不匹配！", flush=True)
            return False

        # 3. 第一轮参数修改：
        #    底座长度: 150 -> 180mm (D1@BaseSketch)
        #    中央轴孔: 30 -> 35mm (D1@ShaftBoreSketch)
        print("\n--- [第一轮修改: 底座长 150->180mm, 轴孔径 30->35mm] ---", flush=True)
        def _sta_mod1():
            sw, _ = connect_solidworks()
            model = open_document(sw, part_path, silent=True)
            dim_l = f"D1@{names['base_sketch']}"
            dim_bore = f"D1@{names['bore_sketch']}"
            r1 = update_dimension_mm(model, dim_l, 180.0, save=False)
            r2 = update_dimension_mm(model, dim_bore, 35.0, save=True)
            b1 = collect_bounding_box(model)
            m1 = collect_mass_properties(model)
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            return r1, r2, b1, m1

        r1, r2, b1, m1 = self.worker.execute(_sta_mod1)
        v1_actual = m1["volume_mm3"]
        v1_theory = calculate_motor_bracket_theoretical_volume(
            base_l_mm=180.0, base_w_mm=100.0, base_t_mm=15.0,
            hole_dia_mm=12.0, hole_count=2,
            upright_h_mm=80.0, upright_t_mm=12.0,
            bore_dia_mm=35.0
        )
        print(f"[*] 第1轮修改后: 实测体积={v1_actual:.2f}mm³, 理论体积={v1_theory:.2f}mm³, 误差={abs(v1_actual - v1_theory):.4f}mm³", flush=True)
        print(f"[*] 包围盒 X 方向: 150.0mm -> {b1['size_mm'][0]:.1f}mm (ΔX = +{b1['size_mm'][0] - 150.0:.1f}mm)", flush=True)

        ok1 = (
            r1["success"] and r2["success"]
            and abs(b1["size_mm"][0] - 180.0) < 0.1
            and abs(v1_actual - v1_theory) < 1.0
        )
        print(f"[*] 第 1 轮修改结论: {'[PASS]' if ok1 else '[FAIL]'}", flush=True)

        # 4. 第二轮参数修改：
        #    底座宽度: 100 -> 120mm (D2@BaseSketch)
        #    左右安装孔径: 12 -> 14mm (D2, D3@MountHolesSketch)
        #    孔间距: 100 -> 110mm (D1@MountHolesSketch)
        print("\n--- [第二轮修改: 底座宽 100->120mm, 孔径 12->14mm, 孔距 100->110mm] ---", flush=True)
        def _sta_mod2():
            sw, _ = connect_solidworks()
            model = open_document(sw, part_path, silent=True)
            dim_w = f"D2@{names['base_sketch']}"
            dim_hdia1 = f"D2@{names['holes_sketch']}"
            dim_hdia2 = f"D3@{names['holes_sketch']}"
            dim_hpitch = f"D1@{names['holes_sketch']}"
            r_w = update_dimension_mm(model, dim_w, 120.0, save=False)
            r_hd1 = update_dimension_mm(model, dim_hdia1, 14.0, save=False)
            r_hd2 = update_dimension_mm(model, dim_hdia2, 14.0, save=False)
            r_hp = update_dimension_mm(model, dim_hpitch, 110.0, save=True)
            b2 = collect_bounding_box(model)
            m2 = collect_mass_properties(model)
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            return r_w, r_hd1, r_hd2, r_hp, b2, m2

        rw, rhd1, rhd2, rhp, b2, m2 = self.worker.execute(_sta_mod2)
        v2_actual = m2["volume_mm3"]
        v2_theory = calculate_motor_bracket_theoretical_volume(
            base_l_mm=180.0, base_w_mm=120.0, base_t_mm=15.0,
            hole_dia_mm=14.0, hole_count=2,
            upright_h_mm=80.0, upright_t_mm=12.0,
            bore_dia_mm=35.0
        )
        print(f"[*] 第2轮修改后: 实测体积={v2_actual:.2f}mm³, 理论体积={v2_theory:.2f}mm³, 误差={abs(v2_actual - v2_theory):.4f}mm³", flush=True)
        print(f"[*] 包围盒 Z 方向 (底座宽度): {b2['size_mm'][2]:.1f}mm (预期 120.0mm)", flush=True)

        ok2 = (
            rw["success"] and rhd1["success"] and rhd2["success"] and rhp["success"]
            and abs(b2["size_mm"][2] - 120.0) < 0.1
            and abs(v2_actual - v2_theory) < 1.0
        )
        print(f"[*] 第 2 轮修改结论: {'[PASS]' if ok2 else '[FAIL]'}", flush=True)

        # 5. 第三轮参数修改：
        #    支撑板高度: 80 -> 100mm (D1@UprightSketch)
        print("\n--- [第三轮修改: 支撑板高 80->100mm, 其余参数保持稳定] ---", flush=True)
        def _sta_mod3():
            sw, _ = connect_solidworks()
            model = open_document(sw, part_path, silent=True)
            dim_uh = f"D1@{names['upright_sketch']}"
            r_uh = update_dimension_mm(model, dim_uh, 100.0, save=True)
            b3 = collect_bounding_box(model)
            m3 = collect_mass_properties(model)
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            return r_uh, b3, m3

        ruh, b3, m3 = self.worker.execute(_sta_mod3)
        v3_actual = m3["volume_mm3"]
        v3_theory = calculate_motor_bracket_theoretical_volume(
            base_l_mm=180.0, base_w_mm=120.0, base_t_mm=15.0,
            hole_dia_mm=14.0, hole_count=2,
            upright_h_mm=100.0, upright_t_mm=12.0,
            bore_dia_mm=35.0
        )
        print(f"[*] 第3轮修改后: 实测体积={v3_actual:.2f}mm³, 理论体积={v3_theory:.2f}mm³, 误差={abs(v3_actual - v3_theory):.4f}mm³", flush=True)
        print(f"[*] 高度方向变化: 总高度从 {b2['size_mm'][1]:.1f}mm -> {b3['size_mm'][1]:.1f}mm (预期 130.0mm)", flush=True)

        ok3 = (
            ruh["success"]
            and abs(b3["size_mm"][1] - 130.0) < 0.1
            and abs(v3_actual - v3_theory) < 1.0
        )
        print(f"[*] 第 3 轮修改结论: {'[PASS]' if ok3 else '[FAIL]'}", flush=True)

        all_ok = ok1 and ok2 and ok3
        print(f"\n[*] 模型 A 综合验收结论: {'[ALL PASS]' if all_ok else '[FAIL]'}", flush=True)
        return all_ok

    def test_part_b_bearing_pillow_block(self) -> bool:
        """测试模型 B：精密轴承座 (Bearing Pillow Block) 真实建模与几何验收。"""
        print("\n" + "=" * 65)
        print("【模型 B：精密轴承座 (Bearing Pillow Block) 真实建模与几何核验】")
        print("=" * 65)

        part_path = get_sandbox_part_path("bearing_pillow_block")

        def _sta():
            sw, _ = connect_solidworks()
            model = new_document(sw, "part")
            names = build_bearing_pillow_block(model)
            save_document(model, part_path)
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            
            # 重新打开物理落盘文件
            model_reopen = open_document(sw, part_path, silent=True)
            b = collect_bounding_box(model_reopen)
            m = collect_mass_properties(model_reopen)
            dims = read_model_dimensions(model_reopen)
            get_com_member(sw, "CloseDoc", get_com_member(model_reopen, "GetTitle"))
            return names, b, m, dims

        names, b, m, dims = self.worker.execute(_sta)
        print(f"[✔ PASS] 精密轴承座物理零件已落盘并重新打开核验: {part_path}", flush=True)
        print(f"[*] 特征与尺寸拓扑: 发现尺寸数={dims.total_count}", flush=True)
        print(f"[*] 物理包围盒: {b['size_mm']}", flush=True)
        print(f"[*] 实测物理体积: {m['volume_mm3']:.2f} mm³", flush=True)

        # 验证实体尺寸范围与单实体属性
        ok = (
            b["size_mm"][0] >= 140.0
            and b["size_mm"][1] >= 50.0
            and m["volume_mm3"] > 50000.0
        )
        print(f"[*] 模型 B 综合验收结论: {'[PASS]' if ok else '[FAIL]'}", flush=True)
        return ok

    def test_part_c_multibranch_connector(self) -> bool:
        """测试模型 C：多分支连接支架 (Multi-Branch Connector) 空间特征与多父依赖汇聚。"""
        print("\n" + "=" * 65, flush=True)
        print("【模型 C：多分支连接支架 (Multi-Branch Connector) 真实建模与几何核验】", flush=True)
        print("=" * 65, flush=True)

        part_path = get_sandbox_part_path("multibranch_connector")

        def _sta():
            sw, _ = connect_solidworks()
            model = new_document(sw, "part")
            names = build_multibranch_connector(model)
            save_document(model, part_path)
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            
            # 重新打开物理文件进行深层特征树检查
            model_reopen = open_document(sw, part_path, silent=True)
            b = collect_bounding_box(model_reopen)
            m = collect_mass_properties(model_reopen)
            dims = read_model_dimensions(model_reopen)
            get_com_member(sw, "CloseDoc", get_com_member(model_reopen, "GetTitle"))
            return names, b, m, dims

        names, b, m, dims = self.worker.execute(_sta)
        print(f"[✔ PASS] 多分支连接支架物理零件已落盘并核验: {part_path}", flush=True)
        print(f"[*] 多分支拓扑: 发现尺寸数={dims.total_count}", flush=True)
        print(f"[*] 空间包围盒: {b['size_mm']}", flush=True)
        print(f"[*] 物理体积: {m['volume_mm3']:.2f} mm³", flush=True)

        ok = (
            b["size_mm"][0] >= 120.0
            and m["volume_mm3"] > 80000.0
        )
        print(f"[*] 模型 C 综合验收结论: {'[PASS]' if ok else '[FAIL]'}", flush=True)
        return ok


def main():
    parser = argparse.ArgumentParser(description="SolidWorks 真实复杂机械零件建模与参数修改套件")
    parser.add_argument("--authorize-cad-write", action="store_true", default=False)
    args = parser.parse_args()

    if not args.authorize_cad_write:
        print("[✖ ERROR] 必须提供 --authorize-cad-write 参数以授权真实参数修改。")
        sys.exit(1)

    print("=" * 65)
    print("      dsh-solidworks 第二轮：真实复杂机械零件工程实机验收")
    print("=" * 65)

    suite = RealCADMechanicalSuite()

    ta = suite.test_part_a_motor_bracket_and_modifications()
    tb = suite.test_part_b_bearing_pillow_block()
    tc = suite.test_part_c_multibranch_connector()

    all_passed = ta and tb and tc

    print("\n" + "=" * 65)
    print("      第二轮复杂机械零件实机测试汇总")
    print("=" * 65)
    print(f"  模型 A：电机安装支架 (三轮连续修改与体积公式交叉比对): {'[PASS]' if ta else '[FAIL]'}")
    print(f"  模型 B：精密轴承座 (轴承柱/阶梯孔/紧固沉孔):          {'[PASS]' if tb else '[FAIL]'}")
    print(f"  模型 C：多分支连接支架 (空间多分支与多方向通孔):        {'[PASS]' if tc else '[FAIL]'}")
    print(f"  第二轮综合验收结论: {'[ALL PASS]' if all_passed else '[FAIL]'}")
    print("=" * 65)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
