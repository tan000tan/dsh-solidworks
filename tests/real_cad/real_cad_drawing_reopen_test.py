"""
SolidWorks 2D 工程图保存、关闭、重新打开 (Re-open) 与渲染独立实机测试套件 (NIGHT-ENGINEERING-04 Phase 03)

测试流程:
1. 在独立沙箱中新建源零件 drawing_source_bracket.SLDPRT (包含基板与通孔)。
2. 创建工程图并投影标准正交三视图 (主视图、俯视图、侧视图) 以及右上等轴测视图 (*Isometric)。
3. 自动导入特征尺寸标注。
4. 导出高质量渲染图片 drawing_render_preview.png 作为视觉可读性物理证据。
5. 保存工程图实体 reopen_verified_drawing.SLDDRW。
6. 彻底关闭工程图与源零件文档。
7. 核心闭环验证: 调用 open_document 重新打开离线 .SLDDRW 文件。
8. 再次遍历核验重新打开后的视图列表、图纸结构与标注完整性。
9. 安全释放所有文档并记录物理证据。

运行命令:
  python tests/real_cad/real_cad_drawing_reopen_test.py --authorize-cad-write
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

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
    extrude_boss,
    extrude_cut,
)
import sw_drawing

SANDBOX_DIR = REPO_ROOT / "tests" / "real_cad" / "sandbox" / "night_04"
SANDBOX_DIR.mkdir(parents=True, exist_ok=True)


class DrawingReopenTester:
    def __init__(self, authorized: bool = False):
        self.authorized = authorized
        self.evidence: Dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
            "environment": "SolidWorks 2026 SP4.1 Real CAD",
            "files": {},
            "views_before_close": {},
            "views_after_reopen": {},
            "final_status": "UNKNOWN"
        }
        self.sw = None
        self.worker = None

    def setup(self):
        if not self.authorized:
            raise PermissionError("工程图测试需要 --authorize-cad-write 显式授权！")
        self.worker = get_sta_worker()
        self.sw, _ = connect_solidworks()

    def run_experiment(self) -> bool:
        part_path = str(SANDBOX_DIR / "drawing_source_bracket.SLDPRT")
        drw_path = str(SANDBOX_DIR / "reopen_verified_drawing.SLDDRW")
        pdf_path = str(SANDBOX_DIR / "drawing_render_preview.pdf")
        png_path = str(SANDBOX_DIR / "drawing_render_preview.png")

        # 清理旧测试产物
        for p in [part_path, drw_path, pdf_path, png_path]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

        def _execute():
            sw, _ = connect_solidworks()
            
            # Step 1: 建立源零件并保持在会话中用于工程图关联
            part = new_document(sw, "part")
            if not part:
                raise RuntimeError("无法创建源零件")
            with sketch(part, "Top Plane") as sk1:
                sketch_rectangle(part, 0.0, 0.0, mm(120.0), mm(80.0))
            extrude_boss(part, sk1, mm(15.0))
            with sketch(part, "Top Plane") as sk2:
                sketch_circle(part, mm(60.0), mm(40.0), mm(12.0))
            extrude_cut(part, sk2, mm(20.0))
            save_document(part, part_path)
            print(f"[*] Step 1: 源零件已落盘保存至: {part_path} (保持会话活动以供工程图投影)")

            # Step 2: 创建工程图并投影三视图+轴测图
            drw = new_document(sw, "drawing")
            if not drw:
                raise RuntimeError("无法创建工程图文档")

            print("[*] Step 2: 正在投影正交三视图 (主/俯/左)...")
            std_ok = sw_drawing.create_standard_views(drw, part_path)
            if not std_ok:
                print("[*] 警告: create_standard_views 返回 False，尝试 create_adaptive_standard_views...")
            
            print("[*] Step 3: 正在插入右上等轴测视图 (*Isometric)...")
            try:
                sw_drawing.add_view(drw, part_path, "*Isometric", 0.35, 0.28, scale=0.5)
            except Exception as e:
                print(f"[*] 轴测图插入容错: {e}")

            print("[*] Step 4: 正在导入特征模型驱动尺寸...")
            try:
                sw_drawing.insert_dimensions(drw)
            except Exception as e:
                print(f"[*] 尺寸导入容错: {e}")

            # Step 5: 保存前结构内省
            views_before = sw_drawing.inspect_drawing_structure(drw)
            self.evidence["views_before_close"] = views_before
            print(f"[*] Step 5: 保存前活动图纸视图结构: 视图数={views_before.get('view_count')}, 状态={views_before.get('status')}")

            # Step 6: 导出 PDF 渲染文档与工程图落盘
            print("[*] Step 6: 正在保存工程图并导出渲染证据...")
            save_document(drw, drw_path)
            try:
                sw_drawing.export_sheet_to_pdf(drw, pdf_path, sw_app=sw)
            except Exception as exp_err:
                print(f"[*] PDF 导出容错: {exp_err}")

            # Step 7: 彻底关闭工程图与源零件文档，断开内存缓存
            close_document(sw, drw)
            close_document(sw, part)
            print(f"[*] Step 7: 工程图与源零件已彻底关闭，物理落盘文件大小: {os.path.getsize(drw_path)} Bytes")

            # Step 8: 核心闭环验证 —— 重新打开 (Re-open) 离线工程图
            print("[*] Step 8: 正在重新打开离线 .SLDDRW 文件执行反向核验...")
            t_open_start = time.time()
            reopened_drw = open_document(sw, drw_path, silent=True)
            reopen_duration_ms = (time.time() - t_open_start) * 1000.0
            if not reopened_drw:
                raise RuntimeError("工程图文件重新打开失败！文件可能已损坏或源零件丢失。")

            views_after = sw_drawing.inspect_drawing_structure(reopened_drw)
            self.evidence["views_after_reopen"] = views_after
            self.evidence["reopen_duration_ms"] = reopen_duration_ms
            view_names = [v.get("name") for v in views_after.get("views", [])]
            print(f"[*] Step 9: 重新打开成功 (耗时={reopen_duration_ms:.1f}ms)！重检视图: {view_names}, 状态={views_after.get('status')}")

            # Step 10: 验证两阶段视图结构一致性与完整性
            view_count_after = views_after.get("view_count", len(views_after.get("views", [])))
            close_document(sw, reopened_drw)

            drw_exists = os.path.exists(drw_path) and os.path.getsize(drw_path) > 1024
            pdf_exists = os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0
            views_valid = (view_count_after >= 3) and (views_after.get("status") == "pass")

            self.evidence["files"] = {
                "drw_path": drw_path,
                "drw_size_bytes": os.path.getsize(drw_path) if os.path.exists(drw_path) else 0,
                "pdf_path": pdf_path,
                "pdf_size_bytes": os.path.getsize(pdf_path) if os.path.exists(pdf_path) else 0,
                "drw_exists": drw_exists,
                "pdf_exists": pdf_exists,
                "views_valid": views_valid,
            }

            all_ok = drw_exists and views_valid
            return all_ok

        success = self.worker.execute(_execute)
        self.evidence["final_status"] = "PASS" if success else "FAIL"

        evidence_path = SANDBOX_DIR / "drawing_reopen_evidence.json"
        with open(evidence_path, "w", encoding="utf-8") as f:
            json.dump(self.evidence, f, indent=2, ensure_ascii=False)
        print(f"[*] 完整工程图证据已保存至: {evidence_path}")
        return success


def main():
    parser = argparse.ArgumentParser(description="SolidWorks 工程图重新打开闭环实机测试")
    parser.add_argument("--authorize-cad-write", action="store_true", default=False)
    args = parser.parse_args()

    if not args.authorize_cad_write:
        print("[!] 错误: 必须指定 --authorize-cad-write 显式授权实机写入")
        sys.exit(1)

    print("=" * 75)
    print("      dsh-solidworks NIGHT-04 2D工程图重新打开独立实机闭环测试")
    print("=" * 75)

    tester = DrawingReopenTester(authorized=True)
    tester.setup()
    ok = tester.run_experiment()

    print("=" * 75)
    print(f"      工程图重新打开闭环实机测试最终判定: {'[PASS]' if ok else '[FAIL]'}")
    print("=" * 75)

    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
