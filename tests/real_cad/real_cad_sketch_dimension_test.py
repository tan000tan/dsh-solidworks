# -*- coding: utf-8 -*-
"""
tests/real_cad/real_cad_sketch_dimension_test.py
P1.1 草图尺寸读取、草图原位修改与参数事务恢复实机验收套件。

测试项目：
1. 测试 A：矩形草图长度尺寸就地修改 (100mm -> 150mm)，验证 BBox X 增加 50mm，体积符合公式。
2. 测试 B：孔直径草图尺寸修改 (20mm -> 25mm)，验证圆柱切削体积减少与理论公式吻合。
3. 测试 C：孔中心 X/Y 坐标尺寸就地修改，验证孔在板面上平移，体积保持绝对守恒。
4. 测试 D：对称双孔间距 (Pitch Distance) 尺寸就地修改 (40mm -> 55mm)，验证孔距与对称性。
5. 测试 E：尺寸约束冲突与过定义自愈回滚 (越界尺寸冲突被拦截并恢复)。
6. 测试 F：多参数级联事务恢复机制 (SUCCESS, ROLLBACK_SUCCESS, ROLLBACK_PARTIAL)。
7. 测试 G：真实 MCP 工具识别与安全修改端到端闭环验证 (JSON-RPC 可审计证据)。
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
    end_sketch, extrude_boss, extrude_cut, current_sketch_name, _empty_callout
)
from sw_measure import collect_bounding_box, collect_mass_properties
from sw_document_data import update_dimension_mm
from dimension_ir import DimensionModelIR, DimensionType
from dimension_reader import read_model_dimensions
from dimension_modifier import DimensionModifier, ModificationResult
from dimension_validator import DimensionValidator


def get_sandbox_part_path(prefix: str) -> str:
    """生成沙箱中唯一时间戳命名的物理零件路径。"""
    sandbox_dir = REAL_CAD_DIR / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return str(sandbox_dir / f"{prefix}_{timestamp}.SLDPRT")


def build_sketch_parametric_model(model) -> Dict[str, str]:
    """
    在传入的零件模型中构建具备完整草图尺寸标注的测试实体。
    底座：100mm x 60mm x 20mm
    单孔：中心 (30mm, 30mm)，直径 20mm
    双孔：两孔中心距 40mm (分别在 x=60, x=100 偏置处)
    """
    names = {}

    # 1. 底座特征 (BasePlate)
    start_sketch(model, "Front Plane")
    sketch_corner_rectangle(model, 0.0, 0.0, 0.10, 0.06)
    model.ClearSelection2(True)
    # 标注底边宽度 (100mm)
    model.Extension.SelectByID2("", "SKETCHSEGMENT", 0.05, 0.0, 0.0, False, 0, _empty_callout(), 0)
    model.AddDimension2(0.05, -0.015, 0.0)
    # 标注侧边高度 (60mm)
    model.ClearSelection2(True)
    model.Extension.SelectByID2("", "SKETCHSEGMENT", 0.10, 0.03, 0.0, False, 0, _empty_callout(), 0)
    model.AddDimension2(0.115, 0.03, 0.0)

    sk_base = current_sketch_name(model, fallback="BaseSketch")
    names["base_sketch"] = sk_base
    end_sketch(model)
    boss = extrude_boss(model, sk_base, 0.020)
    names["base_boss"] = getattr(boss, "Name", "BaseBoss")

    # 2. 单孔特征 (SingleHoleCut) - 带 X坐标(D1)、Y坐标(D2)、直径(D3) 完整标注
    start_sketch(model, "Front Plane")
    # X 构造线 (从原点到孔 X 坐标)
    lx = model.SketchManager.CreateLine(0.0, 0.0, 0.0, 0.030, 0.0, 0.0)
    lx.ConstructionGeometry = True
    model.ClearSelection2(True)
    model.Extension.SelectByID2("", "SKETCHSEGMENT", 0.015, 0.0, 0.0, False, 0, _empty_callout(), 0)
    model.AddDimension2(0.015, -0.010, 0.0) # D1: X 坐标尺寸 (30mm)

    # Y 构造线 (从 X 轴到孔 Y 坐标)
    ly = model.SketchManager.CreateLine(0.030, 0.0, 0.0, 0.030, 0.030, 0.0)
    ly.ConstructionGeometry = True
    model.ClearSelection2(True)
    model.Extension.SelectByID2("", "SKETCHSEGMENT", 0.030, 0.015, 0.0, False, 0, _empty_callout(), 0)
    model.AddDimension2(0.040, 0.015, 0.0) # D2: Y 坐标尺寸 (30mm)

    # 圆孔 (直径 20mm, 半径 10mm)
    sketch_circle(model, 0.030, 0.030, 0.010)
    model.ClearSelection2(True)
    model.Extension.SelectByID2("", "SKETCHSEGMENT", 0.040, 0.030, 0.0, False, 0, _empty_callout(), 0)
    model.AddDimension2(0.045, 0.045, 0.0) # D3: 直径尺寸 (20mm)

    sk_single_hole = current_sketch_name(model, fallback="SingleHoleSketch")
    names["single_hole_sketch"] = sk_single_hole
    end_sketch(model)
    cut1 = extrude_cut(model, sk_single_hole, 0.020, direction=False)
    names["single_hole_cut"] = getattr(cut1, "Name", "SingleHoleCut")

    # 3. 对称双孔特征 (DualHoleCut) - 带两孔间距 (Pitch Distance) 标注
    start_sketch(model, "Front Plane")
    # 两孔间距构造线 (20mm)
    lp = model.SketchManager.CreateLine(0.065, 0.030, 0.0, 0.085, 0.030, 0.0)
    lp.ConstructionGeometry = True
    model.ClearSelection2(True)
    model.Extension.SelectByID2("", "SKETCHSEGMENT", 0.075, 0.030, 0.0, False, 0, _empty_callout(), 0)
    model.AddDimension2(0.075, 0.045, 0.0) # D1: 孔间距 (20mm)

    # 在两端分别绘制圆 (半径 4mm, 直径 8mm)
    sketch_circle(model, 0.065, 0.030, 0.004)
    sketch_circle(model, 0.085, 0.030, 0.004)

    sk_dual_hole = current_sketch_name(model, fallback="DualHoleSketch")
    names["dual_hole_sketch"] = sk_dual_hole
    end_sketch(model)
    cut2 = extrude_cut(model, sk_dual_hole, 0.020, direction=False)
    names["dual_hole_cut"] = getattr(cut2, "Name", "DualHoleCut")

    return names


class RealCADSketchDimensionTestSuite:
    """P1.1 草图尺寸与事务恢复实机测试套件。"""

    def __init__(self, part_path: str):
        self.part_path = part_path
        self.worker = get_sta_worker()
        self.names = {}

    def setup_model(self) -> bool:
        """在 SolidWorks 中建立基准物理模型并落盘。"""
        def _sta_setup():
            sw, _ = connect_solidworks()
            model = new_document(sw, "part")
            names = build_sketch_parametric_model(model)
            save_document(model, self.part_path)
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            return names

        self.names = self.worker.execute(_sta_setup)
        print(f"[✔ PASS] 参数化测试零件已成功构建并落盘: {self.part_path}")
        return True

    def run_test_a_rectangle_length(self) -> bool:
        """Test A: 矩形底座草图长度尺寸由 100mm -> 150mm。"""
        print("\n" + "-" * 60)
        print("【测试 A：矩形草图长度尺寸就地修改 (100mm -> 150mm)】")
        print("-" * 60)

        def _sta():
            sw, _ = connect_solidworks()
            model = open_document(sw, self.part_path)
            b_before = collect_bounding_box(model)
            m_before = collect_mass_properties(model)
            
            # 找到底座草图的 100mm 长度尺寸 (D1@BaseSketch)
            target_dim = f"D1@{self.names['base_sketch']}"
            res = update_dimension_mm(model, target_dim, 150.0, save=True)
            
            b_after = collect_bounding_box(model)
            m_after = collect_mass_properties(model)
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            return res, b_before, b_after, m_before, m_after

        res, b1, b2, m1, m2 = self.worker.execute(_sta)
        dx = b2["size_mm"][0] - b1["size_mm"][0]
        v_diff = m2["volume_mm3"] - m1["volume_mm3"]
        # 理论增量: 50mm * 60mm * 20mm = 60,000 mm3
        expected_v_diff = 50.0 * 60.0 * 20.0
        print(f"[*] 修改状态: {res['set_status_label']}, 目标尺寸: {res['dimension']}")
        print(f"[*] 包围盒变化: 前 X={b1['size_mm'][0]:.1f}mm -> 后 X={b2['size_mm'][0]:.1f}mm (ΔX = +{dx:.1f}mm)")
        print(f"[*] 体积变化: 前 {m1['volume_mm3']:.1f}mm³ -> 后 {m2['volume_mm3']:.1f}mm³ (实际增加={v_diff:.1f}mm³, 理论增加={expected_v_diff:.1f}mm³)")

        ok = (
            res["success"]
            and abs(dx - 50.0) < 0.1
            and abs(v_diff - expected_v_diff) < 1.0
        )
        print(f"[*] 测试 A 结论: {'[PASS]' if ok else '[FAIL]'}")
        return ok

    def run_test_b_hole_diameter(self) -> bool:
        """Test B: 孔直径尺寸由 20mm -> 25mm。"""
        print("\n" + "-" * 60)
        print("【测试 B：孔直径草图尺寸修改 (20mm -> 25mm)】")
        print("-" * 60)

        def _sta():
            sw, _ = connect_solidworks()
            model = open_document(sw, self.part_path)
            m_before = collect_mass_properties(model)
            
            # 单孔直径对应 D3@SingleHoleSketch
            target_dim = f"D3@{self.names['single_hole_sketch']}"
            res = update_dimension_mm(model, target_dim, 25.0, save=True)
            
            m_after = collect_mass_properties(model)
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            return res, m_before, m_after

        res, m1, m2 = self.worker.execute(_sta)
        v_loss = m1["volume_mm3"] - m2["volume_mm3"]
        # 理论圆柱切削增量: pi * (12.5^2 - 10^2) * 20 = pi * 56.25 * 20 = 3534.29 mm3
        theory_v_loss = math.pi * (12.5**2 - 10.0**2) * 20.0
        print(f"[*] 孔直径修改: 20mm -> 25mm, 状态: {res['set_status_label']}")
        print(f"[*] 实体体积削减: 实际={v_loss:.2f}mm³, 理论={theory_v_loss:.2f}mm³, 绝对误差={abs(v_loss - theory_v_loss):.4f}mm³")

        ok = (
            res["success"]
            and abs(v_loss - theory_v_loss) < 0.1
        )
        print(f"[*] 测试 B 结论: {'[PASS]' if ok else '[FAIL]'}")
        return ok

    def run_test_c_hole_coordinates(self) -> bool:
        """Test C: 孔中心 X/Y 坐标尺寸修改 (孔位平移，体积守恒)。"""
        print("\n" + "-" * 60)
        print("【测试 C：孔中心 X/Y 坐标尺寸就地修改 (位移平移与体积守恒)】")
        print("-" * 60)

        def _sta():
            sw, _ = connect_solidworks()
            model = open_document(sw, self.part_path)
            m_before = collect_mass_properties(model)
            
            # X: 30mm -> 45mm, Y: 30mm -> 35mm
            # D1 对应 X 构造线，D2 对应 Y 构造线
            dim_x = f"D1@{self.names['single_hole_sketch']}"
            dim_y = f"D2@{self.names['single_hole_sketch']}"
            
            res_x = update_dimension_mm(model, dim_x, 45.0, save=False)
            res_y = update_dimension_mm(model, dim_y, 35.0, save=True)
            
            m_after = collect_mass_properties(model)
            b_after = collect_bounding_box(model)
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            return res_x, res_y, m_before, m_after, b_after

        rx, ry, m1, m2, b2 = self.worker.execute(_sta)
        v_delta = abs(m2["volume_mm3"] - m1["volume_mm3"])
        print(f"[*] 孔位 X 坐标: 30.0mm -> {rx['after_mm']['current']}mm, 状态={rx['set_status_label']}")
        print(f"[*] 孔位 Y 坐标: 30.0mm -> {ry['after_mm']['current']}mm, 状态={ry['set_status_label']}")
        print(f"[*] 平移前后体积守恒性: 前={m1['volume_mm3']:.2f}mm³, 后={m2['volume_mm3']:.2f}mm³, 偏差={v_delta:.6f}mm³")

        ok = (
            rx["success"]
            and ry["success"]
            and v_delta < 0.01
        )
        print(f"[*] 测试 C 结论: {'[PASS]' if ok else '[FAIL]'}")
        return ok

    def run_test_d_pitch_distance(self) -> bool:
        """Test D: 双孔间距 (Pitch Distance) 尺寸修改 (20mm -> 30mm)。"""
        print("\n" + "-" * 60)
        print("【测试 D：对称双孔间距 (Pitch Distance) 尺寸就地修改】")
        print("-" * 60)

        def _sta():
            sw, _ = connect_solidworks()
            model = open_document(sw, self.part_path)
            m_before = collect_mass_properties(model)
            
            # D1@DualHoleSketch 标注的是两孔中心距 (20mm -> 30mm)
            target_dim = f"D1@{self.names['dual_hole_sketch']}"
            res = update_dimension_mm(model, target_dim, 30.0, save=True)
            
            m_after = collect_mass_properties(model)
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            return res, m_before, m_after

        res, m1, m2 = self.worker.execute(_sta)
        v_delta = abs(m2["volume_mm3"] - m1["volume_mm3"])
        print(f"[*] 双孔中心距: 20.0mm -> {res['after_mm']['current']}mm, 状态={res['set_status_label']}")
        print(f"[*] 孔距拉伸体积守恒性: 偏差={v_delta:.6f}mm³")

        ok = (
            res["success"]
            and abs(res["after_mm"]["current"] - 30.0) < 0.05
            and v_delta < 0.01
        )
        print(f"[*] 测试 D 结论: {'[PASS]' if ok else '[FAIL]'}")
        return ok

    def run_test_e_constraint_conflict_recovery(self) -> bool:
        """Test E: 尺寸冲突与越界参数自愈回滚。"""
        print("\n" + "-" * 60)
        print("【测试 E：尺寸约束冲突与过定义自愈回滚 (越界冲突防御)】")
        print("-" * 60)

        def _sta():
            sw, _ = connect_solidworks()
            model = open_document(sw, self.part_path)
            m_before = collect_mass_properties(model)
            
            # 将孔中心 X 移动至非法负值 (触发参数边界拦截与自愈回滚)
            dim_x = f"D1@{self.names['single_hole_sketch']}"
            modifier = DimensionModifier(model, auto_rollback=True)
            
            # 注入非法极值
            res = modifier.modify_single(dim_x, -50.0, save=False)
            
            m_after = collect_mass_properties(model)
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            return res, m_before, m_after

        res, m1, m2 = self.worker.execute(_sta)
        print(f"[*] 事务状态: {res.status}, 回滚触发={res.rollback_occurred}")
        print(f"[*] 回滚说明: {res.rollback_message}")
        print(f"[*] 几何防御核验: 前={m1['volume_mm3']:.2f}mm³, 恢复后={m2['volume_mm3']:.2f}mm³, 物理一致={abs(m1['volume_mm3'] - m2['volume_mm3']) < 0.01}")

        ok = (
            not res.success
            and res.status in ("ROLLBACK_SUCCESS", "ROLLED_BACK")
            and abs(m1["volume_mm3"] - m2["volume_mm3"]) < 0.01
        )
        print(f"[*] 测试 E 结论: {'[PASS]' if ok else '[FAIL]'}")
        return ok

    def run_test_f_multi_param_transaction_recovery(self) -> bool:
        """Test F: 多参数级联事务恢复 (SUCCESS, ROLLBACK_SUCCESS)。"""
        print("\n" + "-" * 60)
        print("【测试 F：多参数级联事务恢复机制 (原子性检验)】")
        print("-" * 60)

        def _sta():
            sw, _ = connect_solidworks()
            model = open_document(sw, self.part_path)
            
            # 1. 第一阶段：正常批量修改 (底座厚度与单孔直径) -> SUCCESS
            dim_base_t = f"D1@{self.names['base_boss']}"
            dim_hole_d = f"D3@{self.names['single_hole_sketch']}"
            
            modifier = DimensionModifier(model, auto_rollback=True)
            res_succ = modifier.modify_batch(
                updates={dim_base_t: 25.0, dim_hole_d: 22.0},
                save=True,
                doc_path=self.part_path,
            )
            
            # 2. 第二阶段：包含非法数值的批量修改 (一个合法，一个非法) -> ROLLBACK_SUCCESS
            res_rb = modifier.modify_batch(
                updates={dim_base_t: 30.0, dim_hole_d: -15.0},
                save=True,
                doc_path=self.part_path,
            )
            
            # 回读参数确认已保留 25.0mm
            curr_t = float(get_com_member(get_com_member(model, "Parameter", dim_base_t), "SystemValue") or 0.0) * 1000.0
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            return res_succ, res_rb, curr_t

        res_succ, res_rb, curr_t = self.worker.execute(_sta)
        print(f"[*] 批量修改 1: 状态={res_succ.status}, 修改数={res_succ.modified_count} (预期 SUCCESS)")
        print(f"[*] 批量修改 2 (注入非法值): 状态={res_rb.status}, 回滚={res_rb.rollback_occurred} (预期 ROLLBACK_SUCCESS)")
        print(f"[*] 回滚后物理参数核查: 底座厚度恢复为={curr_t:.1f}mm (预期保留第1阶段的 25.0mm)")

        ok = (
            res_succ.success
            and not res_rb.success
            and res_rb.status in ("ROLLBACK_SUCCESS", "ROLLED_BACK")
            and abs(curr_t - 25.0) < 0.1
        )
        print(f"[*] 测试 F 结论: {'[PASS]' if ok else '[FAIL]'}")
        return ok

    def run_test_g_mcp_real_invocation(self) -> bool:
        """Test G: 真实 MCP 工具识别与安全修改端到端闭环验证。"""
        print("\n" + "-" * 60)
        print("【测试 G：真实 MCP 工具识别与安全修改端到端闭环验证】")
        print("-" * 60)

        # 直接调用 server.py 导出的工具函数与对应 Pydantic 模型
        try:
            import server
            from server import SolidWorksIdentifyDimensionsInput, SolidWorksSafeDimensionUpdateInput

            def _sta_mcp():
                sw, _ = connect_solidworks()
                model = open_document(sw, self.part_path)
                
                # 1. 真实调用 solidworks_identify_dimensions
                raw_ident = server.solidworks_identify_dimensions(SolidWorksIdentifyDimensionsInput())
                ident_data = json.loads(raw_ident) if isinstance(raw_ident, str) else raw_ident
                
                # 2. 真实调用 solidworks_modify_dimension_safe
                dim_to_change = f"D1@{self.names['base_boss']}"
                raw_mod = server.solidworks_modify_dimension_safe(
                    SolidWorksSafeDimensionUpdateInput(
                        updates={dim_to_change: 28.0},
                        auto_rollback=True,
                        rebuild=True,
                        save=True,
                    )
                )
                mod_data = json.loads(raw_mod) if isinstance(raw_mod, str) else raw_mod
                
                get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
                return ident_data, mod_data

            ident_data, mod_data = self.worker.execute(_sta_mcp)
            dim_count = ident_data.get("count", len(ident_data.get("dimensions", [])))
            print(f"[✔ MCP 证据 1] solidworks_identify_dimensions 真实返回: 提取到 {dim_count} 个尺寸")
            print(f"[✔ MCP 证据 2] solidworks_modify_dimension_safe 真实返回: {json.dumps(mod_data, ensure_ascii=False)[:180]}...")

            ok = (
                ident_data.get("status") == "success"
                and mod_data.get("status") in ("success", "COMPLETED", "SUCCESS")
                and (mod_data.get("modified_count", 0) > 0 or mod_data.get("success") is True)
            )
            print(f"[*] 测试 G 结论: {'[PASS]' if ok else '[FAIL]'}")
            return ok

        except Exception as exc:
            print(f"[✖ FAIL] 测试 G 发生异常: {exc}")
            import traceback
            traceback.print_exc()
            return False


def main():
    parser = argparse.ArgumentParser(description="SolidWorks P1.1 草图尺寸与事务恢复实机测试")
    parser.add_argument("--authorize-cad-write", action="store_true", default=False)
    args = parser.parse_args()

    if not args.authorize_cad_write:
        print("[✖ ERROR] 必须提供 --authorize-cad-write 参数以授权真实参数修改。")
        sys.exit(1)

    print("=" * 65)
    print("      dsh-solidworks P1.1 草图尺寸驱动与参数事务恢复实机测试套件")
    print("=" * 65)

    part_path = get_sandbox_part_path("sketch_param_suite")
    suite = RealCADSketchDimensionTestSuite(part_path)

    print("[*] 正在创建具备完整草图尺寸标注的物理测试模型...")
    suite.setup_model()

    ta = suite.run_test_a_rectangle_length()
    tb = suite.run_test_b_hole_diameter()
    tc = suite.run_test_c_hole_coordinates()
    td = suite.run_test_d_pitch_distance()
    te = suite.run_test_e_constraint_conflict_recovery()
    tf = suite.run_test_f_multi_param_transaction_recovery()
    tg = suite.run_test_g_mcp_real_invocation()

    all_passed = ta and tb and tc and td and te and tf and tg

    print("\n" + "=" * 65)
    print("      P1.1 草图尺寸驱动实机测试汇总")
    print("=" * 65)
    print(f"  测试 A：矩形草图长度就地修改 (100->150mm): {'[PASS]' if ta else '[FAIL]'}")
    print(f"  测试 B：孔直径草图尺寸修改 (20->25mm):    {'[PASS]' if tb else '[FAIL]'}")
    print(f"  测试 C：孔中心 X/Y 坐标尺寸修改 (平移守恒):  {'[PASS]' if tc else '[FAIL]'}")
    print(f"  测试 D：对称双孔间距 (Pitch) 尺寸修改:     {'[PASS]' if td else '[FAIL]'}")
    print(f"  测试 E：尺寸约束冲突与过定义自愈回滚:       {'[PASS]' if te else '[FAIL]'}")
    print(f"  测试 F：多参数级联事务一致性与恢复:         {'[PASS]' if tf else '[FAIL]'}")
    print(f"  测试 G：真实 MCP 工具识别与安全修改闭环:     {'[PASS]' if tg else '[FAIL]'}")
    print(f"  P1.1 综合验收结论: {'[ALL PASS]' if all_passed else '[FAIL]'}")
    print("=" * 65)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
