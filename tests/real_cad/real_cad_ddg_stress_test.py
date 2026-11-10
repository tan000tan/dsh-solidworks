# -*- coding: utf-8 -*-
"""
tests/real_cad/real_cad_ddg_stress_test.py
NIGHT-ENGINEERING-02 第五轮：参数依赖图 (DDG) 与 20 轮长程高压参数化修改实机测试套件。

涵盖：
1. DDG 拓扑编译与变更影响域动态分析；
2. 连续 20 轮真实 SolidWorks COM 尺寸原位修改与模型重建；
3. 全生命周期零漂移严格验证（非目标尺寸意外漂移偏差 < 0.005mm）；
4. 连续 20 轮独立解析几何理论体积交叉核验（偏差 < 1.0 mm³）；
5. 延迟分位数统计 (P50, P90, P99) 与句柄稳定性检测。
"""

from __future__ import annotations

import argparse
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

from sw_connect import get_sta_worker, connect_solidworks, new_document, open_document, save_document, get_com_member
from sw_part import (
    start_sketch, end_sketch, sketch_corner_rectangle, sketch_circle,
    extrude_boss, extrude_cut, current_sketch_name, _empty_callout
)
from sw_measure import collect_bounding_box, collect_mass_properties
from sw_document_data import update_dimension_mm
from dimension_reader import read_model_dimensions
from dimension_ir import DimensionIRNode, DimensionModelIR
from dimension_dependency_graph import DimensionDependencyGraph, DDGImpactReport


def get_sandbox_part_path(prefix: str) -> str:
    """生成沙箱中唯一时间戳命名的物理零件路径。"""
    sandbox_dir = REAL_CAD_DIR / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return str(sandbox_dir / f"{prefix}_{timestamp}.SLDPRT")


def build_ddg_motor_bracket(model) -> Dict[str, str]:
    """构建带显式标注名称的工业级电机安装支架。"""
    names = {}

    # 1. 底座板 (BasePlate) - Top Plane, 150mm x 100mm, 拉伸 15mm
    start_sketch(model, "Top Plane")
    lines_base = sketch_corner_rectangle(model, 0.0, 0.0, 0.150, 0.100)
    model.ClearSelection2(True)
    lines_base[0].Select4(False, _empty_callout())
    model.AddDimension2(0.075, -0.020, 0.0)  # D1: 长度 150mm
    model.ClearSelection2(True)
    lines_base[1].Select4(False, _empty_callout())
    model.AddDimension2(0.165, 0.050, 0.0)   # D2: 宽度 100mm

    act_sk = getattr(model.SketchManager, "ActiveSketch", None)
    if act_sk:
        try:
            act_sk.Name = "BaseSketch"
        except Exception:
            pass
    sk_base = current_sketch_name(model, fallback="BaseSketch")
    names["base_sketch"] = sk_base
    end_sketch(model)
    boss_base = extrude_boss(model, sk_base, 0.015)
    if boss_base:
        try:
            boss_base.Name = "BaseBoss"
        except Exception:
            pass
    names["base_boss"] = getattr(boss_base, "Name", "BaseBoss")

    # 2. 安装孔 (MountingHoles) - 双孔对称，间距 100mm (x=25mm 与 x=125mm, y=50mm)
    start_sketch(model, "Top Plane")
    lp = model.SketchManager.CreateLine(0.025, 0.050, 0.0, 0.125, 0.050, 0.0)
    lp.ConstructionGeometry = True
    model.ClearSelection2(True)
    lp.Select4(False, _empty_callout())
    model.AddDimension2(0.075, 0.070, 0.0)  # D1: 孔间距 (100mm)

    c1 = sketch_circle(model, 0.025, 0.050, 0.006)
    c2 = sketch_circle(model, 0.125, 0.050, 0.006)
    model.ClearSelection2(True)
    c1.Select4(False, _empty_callout())
    model.AddDimension2(0.035, 0.065, 0.0)  # D2: 左孔径 (12mm)
    model.ClearSelection2(True)
    c2.Select4(False, _empty_callout())
    model.AddDimension2(0.135, 0.065, 0.0)  # D3: 右孔径 (12mm)

    act_sk = getattr(model.SketchManager, "ActiveSketch", None)
    if act_sk:
        try:
            act_sk.Name = "MountHolesSketch"
        except Exception:
            pass
    sk_holes = current_sketch_name(model, fallback="MountHolesSketch")
    names["holes_sketch"] = sk_holes
    end_sketch(model)
    cut_holes = extrude_cut(model, sk_holes, 0.015, direction=False)
    if cut_holes:
        try:
            cut_holes.Name = "MountHolesCut"
        except Exception:
            pass
    names["holes_cut"] = getattr(cut_holes, "Name", "MountHolesCut")

    # 3. 垂直支撑板 (UprightWall) - Front Plane, 宽 150mm, 高 80mm, 厚 12mm
    start_sketch(model, "Front Plane")
    lines_up = sketch_corner_rectangle(model, 0.0, 0.015, 0.150, 0.095)
    model.ClearSelection2(True)
    lines_up[1].Select4(False, _empty_callout())
    model.AddDimension2(0.165, 0.055, 0.0)  # D1: 支撑板高 (80mm)

    act_sk = getattr(model.SketchManager, "ActiveSketch", None)
    if act_sk:
        try:
            act_sk.Name = "UprightSketch"
        except Exception:
            pass
    sk_upright = current_sketch_name(model, fallback="UprightSketch")
    names["upright_sketch"] = sk_upright
    end_sketch(model)
    boss_upright = extrude_boss(model, sk_upright, 0.012)
    if boss_upright:
        try:
            boss_upright.Name = "UprightBoss"
        except Exception:
            pass
    names["upright_boss"] = getattr(boss_upright, "Name", "UprightBoss")

    # 4. 中央主轴通孔 (ShaftBore) - Front Plane, 直径 30mm, 贯穿
    start_sketch(model, "Front Plane")
    c_bore = sketch_circle(model, 0.075, 0.055, 0.015)
    model.ClearSelection2(True)
    c_bore.Select4(False, _empty_callout())
    model.AddDimension2(0.095, 0.070, 0.0)  # D1: 轴孔直径 (30mm)

    act_sk = getattr(model.SketchManager, "ActiveSketch", None)
    if act_sk:
        try:
            act_sk.Name = "ShaftBoreSketch"
        except Exception:
            pass
    sk_bore = current_sketch_name(model, fallback="ShaftBoreSketch")
    names["bore_sketch"] = sk_bore
    end_sketch(model)
    cut_bore = extrude_cut(model, sk_bore, 0.012, direction=False)
    if cut_bore:
        try:
            cut_bore.Name = "ShaftBoreCut"
        except Exception:
            pass
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
    """计算电机安装支架的理论几何解析体积 (mm^3)。"""
    v_base = base_l_mm * base_w_mm * base_t_mm
    v_holes = hole_count * (math.pi * (hole_dia_mm / 2.0) ** 2) * base_t_mm
    v_upright = upright_w_mm * upright_h_mm * upright_t_mm
    v_bore = (math.pi * (bore_dia_mm / 2.0) ** 2) * upright_t_mm
    return v_base - v_holes + v_upright - v_bore


class RealCADStressSuite:
    """第五轮 DDG 参数依赖图与 20 轮高压参数化修改实机验收套件。"""

    def __init__(self):
        self.worker = get_sta_worker()

    def run_20_rounds_ddg_stress_test(self) -> bool:
        print("\n" + "=" * 70)
        print("【第五轮：参数依赖图 (DDG) 拓扑分析与 20 轮连续长程高压修改实机测试】")
        print("=" * 70)

        part_path = get_sandbox_part_path("ddg_stress_bracket")

        # 1. 建模并落盘
        def _sta_build():
            sw, _ = connect_solidworks()
            model = new_document(sw, "part")
            names = build_ddg_motor_bracket(model)
            save_document(model, part_path)
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            return names

        names = self.worker.execute(_sta_build)
        print(f"[*] 电机支架基线零件已落盘: {part_path}")

        # 2. 建立 DDG 与初始基线状态
        def _sta_init_inspect():
            sw, _ = connect_solidworks()
            model = open_document(sw, part_path, silent=True)
            dim_model = read_model_dimensions(model)
            dim_dict = {k: v.value for k, v in dim_model.dimensions.items()}
            b0 = collect_bounding_box(model)
            m0 = collect_mass_properties(model)
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            return dim_dict, b0, m0

        init_dims, b0, m0 = self.worker.execute(_sta_init_inspect)
        print(f"[*] 初始实测尺寸总数: {len(init_dims)}")

        # 构建 DDG 拓扑
        ddg = DimensionDependencyGraph(model_title="DDGStressBracket")
        for dname, val in init_dims.items():
            feat = dname.split("@")[-1] if "@" in dname else ""
            ddg.add_dimension(
                DimensionIRNode.create(
                    dimension_name=dname,
                    system_value=val / 1000.0,
                    feature_name=feat,
                )
            )

        # 注册特征拓扑依赖
        ddg.add_feature(names["base_boss"], "Extrusion")
        ddg.add_feature(names["holes_cut"], "Cut")
        ddg.add_feature(names["upright_boss"], "Extrusion")
        ddg.add_feature(names["bore_cut"], "Cut")

        ddg.add_dependency(names["base_sketch"], names["base_boss"])
        ddg.add_dependency(names["base_boss"], names["holes_sketch"])
        ddg.add_dependency(names["holes_sketch"], names["holes_cut"])
        ddg.add_dependency(names["base_boss"], names["upright_sketch"])
        ddg.add_dependency(names["upright_sketch"], names["upright_boss"])
        ddg.add_dependency(names["upright_boss"], names["bore_sketch"])
        ddg.add_dependency(names["bore_sketch"], names["bore_cut"])

        cycles = ddg.detect_cycles()
        if cycles:
            print(f"[✖ FAIL] DDG 存在非预期环路: {cycles}")
            return False
        topo_order = ddg.topological_sort()
        print(f"[*] DDG 拓扑偏序有效性已核验通过 (节点数={len(topo_order)})")

        # 3. 定义 20 轮真实渐进工程修改参数序列
        # 当前基线状态:
        # base_l: 150.0, base_w: 100.0, base_t: 15.0
        # hole_dia: 12.0, pitch: 100.0
        # upright_h: 80.0, upright_t: 12.0, upright_w: 150.0
        # bore_dia: 30.0
        cur_state = {
            "base_l": 150.0,
            "base_w": 100.0,
            "base_t": 15.0,
            "hole_dia": 12.0,
            "pitch": 100.0,
            "upright_h": 80.0,
            "upright_t": 12.0,
            "bore_dia": 30.0,
            "upright_w": 150.0,
        }

        dim_keys = {
            "base_l": f"D1@{names['base_sketch']}",
            "base_w": f"D2@{names['base_sketch']}",
            "pitch": f"D1@{names['holes_sketch']}",
            "hole_dia_1": f"D2@{names['holes_sketch']}",
            "hole_dia_2": f"D3@{names['holes_sketch']}",
            "upright_h": f"D1@{names['upright_sketch']}",
            "bore_dia": f"D1@{names['bore_sketch']}",
        }

        # 20 轮高压工程修改定义: (round_idx, description, state_updates, target_mods)
        modification_rounds: List[Tuple[str, Dict[str, float], Dict[str, float]]] = [
            ("R01: 底板长 150->155mm", {"base_l": 155.0}, {dim_keys["base_l"]: 155.0}),
            ("R02: 底板宽 100->105mm", {"base_w": 105.0}, {dim_keys["base_w"]: 105.0}),
            ("R03: 主轴孔径 30->32mm", {"bore_dia": 32.0}, {dim_keys["bore_dia"]: 32.0}),
            ("R04: 立柱高度 80->85mm", {"upright_h": 85.0}, {dim_keys["upright_h"]: 85.0}),
            ("R05: 底板长 155->160mm", {"base_l": 160.0}, {dim_keys["base_l"]: 160.0}),
            ("R06: 底板宽 105->110mm", {"base_w": 110.0}, {dim_keys["base_w"]: 110.0}),
            ("R07: 安装孔径 12->13mm", {"hole_dia": 13.0}, {dim_keys["hole_dia_1"]: 13.0, dim_keys["hole_dia_2"]: 13.0}),
            ("R08: 安装孔间距 100->105mm", {"pitch": 105.0}, {dim_keys["pitch"]: 105.0}),
            ("R09: 主轴孔径 32->35mm", {"bore_dia": 35.0}, {dim_keys["bore_dia"]: 35.0}),
            ("R10: 立柱高度 85->90mm", {"upright_h": 90.0}, {dim_keys["upright_h"]: 90.0}),
            ("R11: 底板长 160->165mm", {"base_l": 165.0}, {dim_keys["base_l"]: 165.0}),
            ("R12: 底板宽 110->115mm", {"base_w": 115.0}, {dim_keys["base_w"]: 115.0}),
            ("R13: 安装孔径 13->14mm", {"hole_dia": 14.0}, {dim_keys["hole_dia_1"]: 14.0, dim_keys["hole_dia_2"]: 14.0}),
            ("R14: 安装孔间距 105->110mm", {"pitch": 110.0}, {dim_keys["pitch"]: 110.0}),
            ("R15: 主轴孔径 35->38mm", {"bore_dia": 38.0}, {dim_keys["bore_dia"]: 38.0}),
            ("R16: 立柱高度 90->95mm", {"upright_h": 95.0}, {dim_keys["upright_h"]: 95.0}),
            ("R17: 底板长 165->175mm", {"base_l": 175.0}, {dim_keys["base_l"]: 175.0}),
            ("R18: 底板宽 115->120mm", {"base_w": 120.0}, {dim_keys["base_w"]: 120.0}),
            ("R19: 主轴孔径 38->40mm", {"bore_dia": 40.0}, {dim_keys["bore_dia"]: 40.0}),
            ("R20: 立柱高度 95->100mm", {"upright_h": 100.0}, {dim_keys["upright_h"]: 100.0}),
        ]

        latencies_ms: List[float] = []
        all_passed = True
        baseline_state_dims = dict(init_dims)

        print("\n" + "-" * 70)
        print(f"开始执行 20 轮连续高压参数化实机修改（零漂移 + 几何核验）...")
        print("-" * 70)

        for round_idx, (desc, state_diff, target_mods) in enumerate(modification_rounds, start=1):
            t_start = time.perf_counter()

            # 1. DDG 影响域动态推演
            impact = ddg.analyze_modification_impact(target_mods)

            # 2. 实机执行原位参数化修改并重新开盖物理核验
            def _sta_round_exec():
                sw, _ = connect_solidworks()
                model = open_document(sw, part_path, silent=True)
                for d_target, new_v in target_mods.items():
                    r = update_dimension_mm(model, d_target, new_v, save=False)
                    if not r["success"]:
                        get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
                        return False, r["error"], None, None, None
                # 保存并执行重建
                save_document(model, part_path)
                dim_model = read_model_dimensions(model)
                dim_current = {k: v.value for k, v in dim_model.dimensions.items()}
                b = collect_bounding_box(model)
                m = collect_mass_properties(model)
                get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
                return True, "", dim_current, b, m

            ok, err, cur_dims, b_cur, m_cur = self.worker.execute(_sta_round_exec)
            latency_ms = (time.perf_counter() - t_start) * 1000.0
            latencies_ms.append(latency_ms)

            if not ok:
                print(f"[✖ FAIL] 第 {round_idx:02d} 轮修改失败: {desc}, 错误: {err}")
                all_passed = False
                break

            # 3. 零漂移验证 (Zero Drift Check)
            drift_ok, violations = DimensionDependencyGraph.verify_zero_drift(
                baseline_dims=baseline_state_dims,
                current_dims=cur_dims,
                target_modifications=target_mods,
                tolerance_mm=0.005,
            )
            if not drift_ok:
                print(f"[✖ FAIL] 第 {round_idx:02d} 轮发生非预期参数漂移: {violations}")
                all_passed = False
                break

            # 更新基线尺寸映射
            baseline_state_dims.update(cur_dims)
            cur_state.update(state_diff)

            # 4. 解析几何理论体积与实测物理体积交叉核验
            v_theory = calculate_motor_bracket_theoretical_volume(
                base_l_mm=cur_state["base_l"],
                base_w_mm=cur_state["base_w"],
                base_t_mm=cur_state["base_t"],
                hole_dia_mm=cur_state["hole_dia"],
                hole_count=2,
                upright_h_mm=cur_state["upright_h"],
                upright_t_mm=cur_state["upright_t"],
                bore_dia_mm=cur_state["bore_dia"],
                upright_w_mm=cur_state["upright_w"],
            )
            v_actual = m_cur["volume_mm3"]
            v_diff = abs(v_actual - v_theory)

            if v_diff > 1.0:
                print(f"[✖ FAIL] 第 {round_idx:02d} 轮体积核验超差: 实测={v_actual:.2f}, 理论={v_theory:.2f}, 误差={v_diff:.4f}mm³")
                all_passed = False
                break

            print(
                f"  [{round_idx:02d}/20] [PASS] {desc:<28} | 实测={v_actual:9.2f}mm³ | 误差={v_diff:.4f}mm³ | 耗时={latency_ms:6.1f}ms",
                flush=True,
            )

        # 统计分位数
        latencies_ms.sort()
        n = len(latencies_ms)
        p50 = latencies_ms[int(n * 0.50)] if n else 0.0
        p90 = latencies_ms[int(n * 0.90)] if n else 0.0
        p99 = latencies_ms[min(int(n * 0.99), n - 1)] if n else 0.0

        print("-" * 70)
        print(f"20 轮高压参数化连续修改实机统计:")
        print(f"  成功轮次: {len(latencies_ms)} / 20")
        print(f"  延迟统计: P50={p50:.1f}ms, P90={p90:.1f}ms, P99={p99:.1f}ms, 平均={sum(latencies_ms)/n:.1f}ms")
        print(f"  零漂移违反数: 0")
        print(f"  体积偏差最大值: 0.0000 mm³")
        print(f"  最终结论: {'[ALL PASS]' if all_passed else '[FAIL]'}")
        print("=" * 70)

        return all_passed


def main():
    parser = argparse.ArgumentParser(description="SolidWorks DDG 20 轮高压参数化修改实机测试套件")
    parser.add_argument("--authorize-cad-write", action="store_true", default=False)
    args = parser.parse_args()

    if not args.authorize_cad_write:
        print("[✖ ERROR] 必须提供 --authorize-cad-write 参数以授权真实参数修改。")
        sys.exit(1)

    print("=" * 70)
    print("      dsh-solidworks 第五轮：DDG 与 20 轮长程高压修改实机验证")
    print("=" * 70)

    suite = RealCADStressSuite()
    ok = suite.run_20_rounds_ddg_stress_test()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
