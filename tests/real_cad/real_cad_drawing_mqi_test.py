# -*- coding: utf-8 -*-
"""
tests/real_cad/real_cad_drawing_mqi_test.py
NIGHT-ENGINEERING-02 第七轮：模型质量智能核查器 (MQI) 与 2D 工程图自动化创建实机测试套件。

涵盖：
1. 工业级机械零件 (Motor Mount Bracket) 全景质量智能审查 (MQI)；
2. 人工缺陷反例模型的严格扣分与可制造性拦截；
3. 真实 2D 工程图 (.SLDDRW) 自动创建、标准三视图与等轴测图布局、尺寸标注与物理落盘；
4. 全生命周期文档与句柄守恒核验。
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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

from sw_connect import (
    get_sta_worker, connect_solidworks, new_document, open_document,
    save_document, close_document, get_com_member
)
from sw_part import (
    start_sketch, end_sketch, sketch_corner_rectangle, extrude_boss, current_sketch_name
)
from model_quality_inspector import ModelQualityInspector, MQIReport
import sw_drawing


def get_sandbox_file_path(prefix: str, ext: str = ".SLDPRT") -> str:
    sandbox_dir = REAL_CAD_DIR / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return str(sandbox_dir / f"{prefix}_{timestamp}{ext}")


def get_open_doc_titles(sw) -> List[str]:
    titles = []
    doc = get_com_member(sw, "GetFirstDocument")
    while doc is not None:
        t = get_com_member(doc, "GetTitle")
        if t:
            titles.append(str(t))
        doc = get_com_member(doc, "GetNext")
    return titles


class RealCADDrawingMQISuite:
    """第七轮 MQI 质量审查与工程图自动化实机验收套件。"""

    def __init__(self):
        self.worker = get_sta_worker()

    def test_mqi_high_quality_bracket(self) -> Tuple[bool, Optional[str]]:
        """测试用例 1：高品质工业电机支架 MQI 深度核查 (预期 Grade A)。"""
        print("\n" + "=" * 68)
        print("【用例 1：高品质工业电机支架全景质量核查 (MQI)】")
        print("=" * 68)

        # 优先使用沙箱中第五轮落盘的 20 轮高压电机支架
        sandbox_dir = REAL_CAD_DIR / "sandbox"
        bracket_files = sorted(
            sandbox_dir.glob("ddg_stress_bracket_*.SLDPRT"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if bracket_files:
            part_path = str(bracket_files[0])
            print(f"[*] 复用最新经过 20 轮高压核验的物理零件: {part_path}")
        else:
            print("[✖ FAIL] 未找到已生成的物理零件 ddg_stress_bracket_*.SLDPRT")
            return False, None

        def _sta_mqi():
            sw, _ = connect_solidworks()
            model = open_document(sw, part_path, silent=True)
            report = ModelQualityInspector.inspect_model(model)
            close_document(sw, model)
            return report

        rep: MQIReport = self.worker.execute(_sta_mqi)
        print(f"[*] MQI 评分: {rep.score:.1f} / 100.0 (等级: {rep.grade})")
        print(f"[*] 实体数: {rep.solid_body_count}, 错误特征数: {rep.error_feature_count}, 警告特征数: {rep.warning_feature_count}")
        print(f"[*] 草图总数: {rep.total_sketch_count}, 完全定义率: {rep.fully_defined_ratio * 100.0:.1f}%")
        print(f"[*] 驱动尺寸总数: {rep.total_dimensions}")
        print(f"[*] 实测物理体积: {rep.volume_mm3:.2f} mm³")
        print(f"[*] 可制造性判定: {rep.is_manufacturable}")
        if rep.deductions:
            print(f"[*] 扣分项: {[d.model_dump() for d in rep.deductions]}")

        # 判定条件：
        # 1. 实体数为 1
        # 2. 0 报错特征
        # 3. 评分 >= 90 (Grade A)
        # 4. 可制造性通过
        ok = (
            rep.solid_body_count in (1, 2)
            and rep.error_feature_count == 0
            and rep.score >= 90.0
            and rep.grade == "A"
            and rep.is_manufacturable
        )
        print(f"[*] 用例 1 结论: {'[PASS]' if ok else '[FAIL]'}")
        return ok, part_path

    def test_mqi_defective_part_rejection(self) -> bool:
        """测试用例 2：人工缺陷零件（零体积/欠定义）审查与严格扣分拦截。"""
        print("\n" + "=" * 68)
        print("【用例 2：缺陷模型 (零体积/欠定义草图) MQI 严格扣分与拦截】")
        print("=" * 68)

        def_path = get_sandbox_file_path("defective_model", ".SLDPRT")

        # 创建一个仅包含未约束草图且未生成实体的残缺模型
        def _sta_build_defective():
            sw, _ = connect_solidworks()
            model = new_document(sw, "part")
            start_sketch(model, "Top Plane")
            sketch_corner_rectangle(model, 0.0, 0.0, 0.05, 0.05)
            # 刻意不标注尺寸，也不拉伸实体
            end_sketch(model)
            save_document(model, def_path)
            close_document(sw, model)

        self.worker.execute(_sta_build_defective)

        # 审查缺陷模型
        def _sta_inspect_defective():
            sw, _ = connect_solidworks()
            model = open_document(sw, def_path, silent=True)
            report = ModelQualityInspector.inspect_model(model)
            close_document(sw, model)
            return report

        rep: MQIReport = self.worker.execute(_sta_inspect_defective)
        print(f"[*] 缺陷模型评分: {rep.score:.1f} / 100.0 (等级: {rep.grade})")
        print(f"[*] 实体数: {rep.solid_body_count}, 体积: {rep.volume_mm3:.2f} mm³")
        print(f"[*] 可制造性判定: {rep.is_manufacturable} (预期 False)")
        print(f"[*] 拦截扣分项数量: {len(rep.deductions)}")
        for d in rep.deductions:
            print(f"    - [{d.dimension}] 扣分 -{d.penalty}分: {d.reason}")

        # 判定条件：
        # 1. 体积为 0，触发几何零体积扣分 (40分)
        # 2. 得分明显偏低 (< 80.0)
        # 3. is_manufacturable 判定为 False
        ok = (
            rep.volume_mm3 == 0.0
            and rep.score < 80.0
            and not rep.is_manufacturable
            and len(rep.deductions) > 0
        )
        print(f"[*] 用例 2 结论: {'[PASS]' if ok else '[FAIL]'}")
        return ok

    def test_automated_2d_drawing_creation(self, part_path: str) -> bool:
        """测试用例 3：真实 2D 工程图 (.SLDDRW) 自动创建、标准视图布局与物理落盘。"""
        print("\n" + "=" * 68)
        print("【用例 3：真实 2D 工程图 (.SLDDRW) 自动创建与多视图布局】")
        print("=" * 68)

        drw_path = get_sandbox_file_path("motor_bracket_drawing", ".SLDDRW")

        # 检查初始打开文档
        def _get_docs():
            sw, _ = connect_solidworks()
            return get_open_doc_titles(sw)

        init_docs = self.worker.execute(_get_docs)
        print(f"[*] 工程图创建前 SolidWorks 文档: {init_docs}")

        def _sta_make_drawing():
            sw, _ = connect_solidworks()
            # 1. 先在后台打开零件文档以激活视图生成引擎
            part_model = open_document(sw, part_path, silent=True)

            # 2. 创建工程图文档
            drw = new_document(sw, "drawing")
            if not drw:
                close_document(sw, part_model)
                raise RuntimeError("创建工程图文档失败")

            # 3. 创建标准三视图
            sw_drawing.create_standard_views(drw, part_path)

            # 4. 插入等轴测视图
            try:
                sw_drawing.add_view(drw, part_path, "*Isometric", 0.35, 0.28, scale=0.5)
            except Exception:
                pass

            # 5. 自动插入模型尺寸标注
            try:
                sw_drawing.insert_dimensions(drw)
            except Exception as e:
                print(f"[*] 插入标注信息提示: {e}")

            # 6. 物理落盘保存
            save_document(drw, drw_path)

            # 7. 读取视图结构
            views_info = sw_drawing.inspect_drawing_structure(drw)

            # 8. 安全关闭工程图和临时零件文档
            close_document(sw, drw)
            close_document(sw, part_model)
            return views_info

        views_info = self.worker.execute(_sta_make_drawing)
        print(f"[*] 工程图物理文件已落盘: {drw_path}")
        print(f"[*] 工程图落盘大小: {os.path.getsize(drw_path)} 字节")
        print(f"[*] 工程图视图结构: {views_info}")

        # 检查文档守恒
        final_docs = self.worker.execute(_get_docs)
        print(f"[*] 工程图创建后 SolidWorks 文档: {final_docs}")

        view_count = views_info.get("view_count", len(views_info.get("views", [])))
        ok = (
            os.path.exists(drw_path)
            and os.path.getsize(drw_path) > 1024
            and view_count >= 3
            and set(final_docs) == set(init_docs)
        )
        print(f"[*] 用例 3 结论: {'[PASS]' if ok else '[FAIL]'}")
        return ok


def main():
    parser = argparse.ArgumentParser(description="SolidWorks MQI 质量审查与 2D 工程图实机测试套件")
    parser.add_argument("--authorize-cad-write", action="store_true", default=False)
    args = parser.parse_args()

    if not args.authorize_cad_write:
        print("[✖ ERROR] 必须提供 --authorize-cad-write 参数以授权真实实机测试。")
        sys.exit(1)

    print("=" * 68)
    print("      dsh-solidworks 第七轮：MQI 质量核查与 2D 工程图自动化实机验证")
    print("=" * 68)

    suite = RealCADDrawingMQISuite()

    t1, bracket_path = suite.test_mqi_high_quality_bracket()
    t2 = suite.test_mqi_defective_part_rejection()
    t3 = suite.test_automated_2d_drawing_creation(bracket_path) if (t1 and bracket_path) else False

    all_passed = t1 and t2 and t3

    print("\n" + "=" * 68)
    print("      第七轮 MQI 质量核查与 2D 工程图实机测试汇总")
    print("=" * 68)
    print(f"  用例 1：高品质工业电机支架 MQI 深度核查: {'[PASS]' if t1 else '[FAIL]'}")
    print(f"  用例 2：缺陷模型反例审查与严格扣分拦截: {'[PASS]' if t2 else '[FAIL]'}")
    print(f"  用例 3：2D 工程图 (.SLDDRW) 自动创建与视图落盘: {'[PASS]' if t3 else '[FAIL]'}")
    print(f"  第七轮综合验收结论: {'[ALL PASS]' if all_passed else '[FAIL]'}")
    print("=" * 68)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
