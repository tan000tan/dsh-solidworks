# -*- coding: utf-8 -*-
"""
tests/real_cad/real_cad_planner_test.py
NIGHT-ENGINEERING-02 第三轮：Agent 自主规划与端到端实机验证套件。

核心验证：
1. 自然语言输入 -> 结构化意图 (DesignIntent) -> 拓扑编译 (FeatureGraphIR) -> SolidWorks 真实建模落盘
2. 模型几何与物理理论解析体积严格交叉比对
3. 反例几何硬拦截 (零 CAD 写入安全防护)
4. 自主规划生成模型的二次原位参数化驱动闭环
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

from sw_connect import get_sta_worker, connect_solidworks, open_document, get_com_member
from sw_measure import collect_bounding_box, collect_mass_properties
from sw_document_data import update_dimension_mm
from dimension_reader import read_model_dimensions
from cad_task_planner import CADTaskPlanner, IntentValidationError
from design_intent import IntentValidationStatus


def get_sandbox_part_path(prefix: str) -> str:
    """生成沙箱中唯一时间戳命名的物理零件路径。"""
    sandbox_dir = REAL_CAD_DIR / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return str(sandbox_dir / f"{prefix}_{timestamp}.SLDPRT")


class RealCADPlannerSuite:
    """第三轮自主规划与意图转译实机验收套件。"""

    def __init__(self):
        self.worker = get_sta_worker()
        self.planner = CADTaskPlanner()

    def test_autonomous_flange_from_prompt(self) -> bool:
        """测试用例 1：自然语言驱动自主规划法兰板实机建模与体积核验。"""
        print("\n" + "=" * 65, flush=True)
        print("【用例 1：自然语言 -> 自主规划 -> 真实法兰板建模与物理核验】", flush=True)
        print("=" * 65, flush=True)

        prompt = "创建一个长140mm、宽90mm、厚12mm的机械法兰板，中心开一个直径28mm的通孔"
        print(f"[*] 输入提示词: \"{prompt}\"", flush=True)

        part_path = get_sandbox_part_path("autonomous_flange")

        # 1. 在 STA 线程中运行规划与实机执行
        def _sta_exec():
            res, intent = self.planner.plan_and_execute(
                user_input=prompt,
                output_part_path=part_path,
                close_on_finish=True,
            )
            return res, intent

        exec_res, intent = self.worker.execute(_sta_exec)
        print(f"[*] 执行状态: success={exec_res.success}, executed_nodes={exec_res.executed_count}/{exec_res.total_nodes}", flush=True)
        if not exec_res.success:
            print(f"[✖ FAIL] 规划器实机执行失败: {exec_res.error_message}", flush=True)
            return False

        # 2. 重新打开物理落盘模型进行几何与物理属性核验
        def _sta_inspect():
            sw, _ = connect_solidworks()
            model = open_document(sw, part_path, silent=True)
            b = collect_bounding_box(model)
            m = collect_mass_properties(model)
            dims = read_model_dimensions(model)
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            return b, m, dims

        b, m, dims = self.worker.execute(_sta_inspect)
        v_actual = m["volume_mm3"]

        # 3. 理论解析体积交叉检验
        # V = (140 * 90 * 12) - (pi/4 * 28^2 * 12)
        v_base = 140.0 * 90.0 * 12.0
        v_hole = (math.pi / 4.0 * (28.0 ** 2)) * 12.0
        v_theory = v_base - v_hole

        print(f"[*] 实机落盘核验: {part_path}", flush=True)
        print(f"[*] 实测体积={v_actual:.2f}mm³, 理论体积={v_theory:.2f}mm³, 误差={abs(v_actual - v_theory):.4f}mm³", flush=True)
        print(f"[*] 物理包围盒: {b['size_mm']}", flush=True)
        print(f"[*] 发现驱动尺寸数: {dims.total_count}", flush=True)

        ok = (
            abs(v_actual - v_theory) < 1.0
            and abs(b["size_mm"][0] - 140.0) < 0.5
            and abs(b["size_mm"][2] - 90.0) < 0.5
            and abs(b["size_mm"][1] - 12.0) < 0.5
        )
        print(f"[*] 用例 1 结论: {'[PASS]' if ok else '[FAIL]'}", flush=True)
        return ok

    def test_counter_example_protection(self) -> bool:
        """测试用例 2：反例严苛拦截与零 CAD 写入安全防护。"""
        print("\n" + "=" * 65, flush=True)
        print("【用例 2：几何反例与超界孔位拦截 (零 CAD 污染防护)】", flush=True)
        print("=" * 65, flush=True)

        bad_prompt = "创建一个长50mm、宽50mm、厚5mm的薄板，中心开一个直径80mm的通孔"
        print(f"[*] 输入恶意/非法提示词: \"{bad_prompt}\"", flush=True)

        # 记录执行前的文档快照
        def _get_doc_count():
            sw, _ = connect_solidworks()
            count = 0
            m = get_com_member(sw, "GetFirstDocument")
            while m is not None:
                count += 1
                m = get_com_member(m, "GetNext")
            return count

        initial_count = self.worker.execute(_get_doc_count)
        print(f"[*] 执行前 SolidWorks 打开文档数: {initial_count}", flush=True)

        intercepted = False
        error_captured = ""
        try:
            self.planner.plan_and_execute(bad_prompt, output_part_path="dummy.SLDPRT")
        except IntentValidationError as e:
            intercepted = True
            error_captured = str(e)
            print(f"[✔ PASS] 规划器成功在未触碰 CAD 前拦截反例: {e}", flush=True)
        except Exception as other:
            print(f"[✖ FAIL] 捕获到非预期异常类型: {type(other)}: {other}", flush=True)

        final_count = self.worker.execute(_get_doc_count)
        print(f"[*] 执行后 SolidWorks 打开文档数: {final_count}", flush=True)

        zero_pollution = (final_count == initial_count)
        all_ok = intercepted and zero_pollution
        print(f"[*] 零 CAD 污染防护断言: {'[PASS]' if zero_pollution else '[FAIL]'}", flush=True)
        print(f"[*] 用例 2 结论: {'[PASS]' if all_ok else '[FAIL]'}", flush=True)
        return all_ok

    def test_autonomous_parametric_modification(self) -> bool:
        """测试用例 3：自主规划生成零件的参数化再修改闭环。"""
        print("\n" + "=" * 65, flush=True)
        print("【用例 3：自主规划生成模型 -> 原位参数化再驱动闭环】", flush=True)
        print("=" * 65, flush=True)

        prompt = "加工一块 120x80x15 的底板，中心开一个直径25mm的通孔"
        part_path = get_sandbox_part_path("auto_parametric_part")

        def _sta_build():
            res, intent = self.planner.plan_and_execute(
                user_input=prompt,
                output_part_path=part_path,
                close_on_finish=True,
            )
            return res, intent

        self.worker.execute(_sta_build)
        print(f"[*] 基线零件已生成: {part_path}", flush=True)

        # 启动原位参数化修改：将中心孔从 25mm 修改为 32mm
        # 并将底座长从 120mm 扩展到 150mm
        print("\n--- [参数化修改: 底板长 120->150mm, 中心孔 25->32mm] ---", flush=True)
        def _sta_modify():
            sw, _ = connect_solidworks()
            model = open_document(sw, part_path, silent=True)
            # 通过参数名安全定位
            r1 = update_dimension_mm(model, "D1@BaseSketch", 150.0, save=False)
            r2 = update_dimension_mm(model, "D1@HoleSketch_1", 32.0, save=True)
            b_new = collect_bounding_box(model)
            m_new = collect_mass_properties(model)
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            return r1, r2, b_new, m_new

        r1, r2, b_new, m_new = self.worker.execute(_sta_modify)
        v_actual_new = m_new["volume_mm3"]

        # 新状态理论体积
        # V = (150 * 80 * 15) - (pi/4 * 32^2 * 15)
        v_base_new = 150.0 * 80.0 * 15.0
        v_hole_new = (math.pi / 4.0 * (32.0 ** 2)) * 15.0
        v_theory_new = v_base_new - v_hole_new

        print(f"[*] 修改后实测体积={v_actual_new:.2f}mm³, 理论体积={v_theory_new:.2f}mm³, 误差={abs(v_actual_new - v_theory_new):.4f}mm³", flush=True)
        print(f"[*] 修改后包围盒 X: {b_new['size_mm'][0]:.1f}mm (预期 150.0mm)", flush=True)

        ok = (
            r1["success"] and r2["success"]
            and abs(v_actual_new - v_theory_new) < 1.0
            and abs(b_new["size_mm"][0] - 150.0) < 0.5
        )
        print(f"[*] 用例 3 结论: {'[PASS]' if ok else '[FAIL]'}", flush=True)
        return ok


def main():
    parser = argparse.ArgumentParser(description="SolidWorks Agent 自主规划与端到端实机验证套件")
    parser.add_argument("--authorize-cad-write", action="store_true", default=False)
    args = parser.parse_args()

    if not args.authorize_cad_write:
        print("[✖ ERROR] 必须提供 --authorize-cad-write 参数以授权真实参数修改。")
        sys.exit(1)

    print("=" * 65)
    print("      dsh-solidworks 第三轮：Agent 自主规划与端到端实机验收")
    print("=" * 65)

    suite = RealCADPlannerSuite()

    t1 = suite.test_autonomous_flange_from_prompt()
    t2 = suite.test_counter_example_protection()
    t3 = suite.test_autonomous_parametric_modification()

    all_passed = t1 and t2 and t3

    print("\n" + "=" * 65)
    print("      第三轮 Agent 自主规划实机测试汇总")
    print("=" * 65)
    print(f"  用例 1：自然语言法兰板自主规划与建模:     {'[PASS]' if t1 else '[FAIL]'}")
    print(f"  用例 2：几何反例与超界孔位拦截 (零CAD污染): {'[PASS]' if t2 else '[FAIL]'}")
    print(f"  用例 3：自主规划零件原位参数化再驱动闭环:  {'[PASS]' if t3 else '[FAIL]'}")
    print(f"  第三轮综合验收结论: {'[ALL PASS]' if all_passed else '[FAIL]'}")
    print("=" * 65)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
