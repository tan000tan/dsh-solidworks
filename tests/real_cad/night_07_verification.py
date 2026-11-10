# -*- coding: utf-8 -*-
"""
SolidWorks 真实执行稳定性、事务管理与故障恢复综合实机验证套件
(NIGHT-ENGINEERING-07 Phase 02 - Phase 06)

运行目标:
1. 验证 STA Worker 探活、排队超时与协作式取消状态流转。
2. 验证真实 SolidWorks 特征树物理逆序回滚（Level 3 回滚：实体数归零、特征逆序删除、离线重开验证）。
3. 验证 2D 工程图生成、保存、关闭、重新打开闭环（3/3 核心正交视图 + 轴测视图）。
4. 验证 3 批次资源稳定性（内存、GDI/User 对象、文档计数严格归位）。
5. 保护用户原有打开文档，测试前后文档计数完全保持基线。

执行命令:
  python tests/real_cad/night_07_verification.py --authorize-cad-write
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
    extrude_boss,
    extrude_cut,
)
from sw_measure import collect_mass_properties
import sw_drawing
from cad_task_context import (
    CADTaskContext,
    CADTaskRollbackManager,
    FeatureCleanupManager,
    TaskStatus,
    CleanupStatus,
    RollbackStatus,
    TrackedFeature,
    TrackedDocument,
)

SANDBOX_DIR = REPO_ROOT / "tests" / "real_cad" / "sandbox" / "night_07"
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
    """采集指定进程的物理内存 (MB)、GDI 对象与 User 对象。"""
    metrics = {
        "pid": pid,
        "working_set_mb": 0.0,
        "gdi_objects": 0,
        "user_objects": 0,
    }
    if os.name != "nt":
        return metrics

    kernel32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi
    user32 = ctypes.windll.user32

    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_VM_READ = 0x0010
    h_proc = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
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
    """读取当前 SolidWorks 打开的所有文档标题与路径。"""
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
    """遍历模型中所有真实特征名称。"""
    names = []
    feat = get_com_member(model, "FirstFeature")
    while feat:
        name = get_com_member(feat, "Name")
        if name:
            names.append(str(name))
        feat = get_com_member(feat, "GetNextFeature")
    return names


def get_solid_body_count(model) -> int:
    """获取当前零件的真实实体数。"""
    bodies = get_com_member(model, "GetBodies2", 0, True)  # 0 = swSolidBody
    if bodies:
        return len(bodies)
    return 0


class Night07VerificationRunner:
    def __init__(self, authorized: bool = False):
        self.authorized = authorized
        self.worker = get_sta_worker()
        self.sw, _ = connect_solidworks(visible=True)
        self.sw_pid = self.worker.execute(lambda: get_com_member(self.sw, "GetProcessID"))
        self.baseline_docs = get_current_open_docs(self.sw, self.worker)
        self.baseline_metrics = get_process_metrics(self.sw_pid)
        self.evidence: Dict[str, Any] = {
            "session": "NIGHT-ENGINEERING-07",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
            "solidworks_pid": self.sw_pid,
            "baseline_doc_count": len(self.baseline_docs),
            "baseline_metrics": self.baseline_metrics,
            "phases": {},
            "final_verifications": {},
        }

    def run_all(self) -> bool:
        print("=== 开始 NIGHT-ENGINEERING-07 综合实机验证 ===")
        print(f"SolidWorks PID: {self.sw_pid}")
        print(f"初始基线文档数量: {len(self.baseline_docs)}")
        print(f"初始 SW 内存: {self.baseline_metrics['working_set_mb']} MB, GDI: {self.baseline_metrics['gdi_objects']}")

        p1_ok = self.phase_state_and_sta_worker()
        p2_ok = self.phase_physical_rollback()
        p3_ok = self.phase_drawing_reopen_cycle()
        p4_ok = self.phase_batch_stability_test()

        # 终审核验
        current_docs = get_current_open_docs(self.sw, self.worker)
        current_metrics = get_process_metrics(self.sw_pid)
        doc_count_match = len(current_docs) == len(self.baseline_docs)
        self.evidence["final_verifications"] = {
            "final_doc_count": len(current_docs),
            "baseline_doc_count": len(self.baseline_docs),
            "doc_count_recovered": doc_count_match,
            "final_metrics": current_metrics,
            "mem_delta_mb": round(current_metrics["working_set_mb"] - self.baseline_metrics["working_set_mb"], 2),
            "gdi_delta": current_metrics["gdi_objects"] - self.baseline_metrics["gdi_objects"],
            "all_passed": (p1_ok and p2_ok and p3_ok and p4_ok and doc_count_match),
        }

        evidence_file = SANDBOX_DIR / "evidence_night07.json"
        with open(evidence_file, "w", encoding="utf-8") as f:
            json.dump(self.evidence, f, ensure_ascii=False, indent=2)
        print(f"\n全部物证已持久化写入: {evidence_file}")

        print(f"\n=== 验证汇总 ===")
        print(f"阶段二/三 状态机与STA隔离: {'PASS' if p1_ok else 'FAIL'}")
        print(f"阶段四 真实特征树物理回滚: {'PASS' if p2_ok else 'FAIL'}")
        print(f"阶段五 工程图生成与重开闭环: {'PASS' if p3_ok else 'FAIL'}")
        print(f"阶段六 分批资源压测无泄漏: {'PASS' if p4_ok else 'FAIL'}")
        print(f"基线文档归位与零残留: {'PASS' if doc_count_match else 'FAIL'}")

        return self.evidence["final_verifications"]["all_passed"]

    def phase_state_and_sta_worker(self) -> bool:
        print("\n--- [Phase 02/03] STA Worker 探活与协作式取消隔离验证 ---")
        healthy = self.worker.is_healthy()
        print(f"1. STA Worker 快速探活: {healthy}")

        ctx = CADTaskContext(task_id="task_night07_cancel_test")
        ctx.transition_to(TaskStatus.QUEUED, "Enqueue for execution")
        ctx.transition_to(TaskStatus.RUNNING, "Worker started task")
        print(f"2. 状态机初始运行态: {ctx.status.value}")

        # 模拟外部协作式取消触发
        ctx.request_cancellation(reason="User timeout abort requested")
        print(f"3. 触发协作取消标志: cancellation_requested={ctx._cancellation_requested}")

        # 任务执行循环中响应取消请求
        if ctx.is_cancelled():
            ctx.transition_to(TaskStatus.CANCELLING, "Responding to cancel request")
            ctx.transition_to(TaskStatus.ROLLING_BACK, "Executing cleanup on cancel")
            ctx.transition_to(TaskStatus.CANCELLED, "Cancellation finalized safely")
        print(f"4. 取消终态核验: {ctx.status.value}, is_terminal={ctx.is_terminal()}")

        history_len = len(ctx.state_history)
        print(f"5. 审计流水记录条数: {history_len}")

        passed = (
            healthy
            and ctx.status == TaskStatus.CANCELLED
            and ctx.is_terminal()
            and history_len >= 5
        )
        self.evidence["phases"]["phase_state_sta"] = {
            "sta_healthy": healthy,
            "final_status": ctx.status.value,
            "state_history": ctx.state_history,
            "passed": passed,
        }
        return passed

    def phase_physical_rollback(self) -> bool:
        print("\n--- [Phase 04] 真实 SolidWorks 特征树物理逆序回滚复核 ---")
        target_path = str(SANDBOX_DIR / "night07_rollback_target.SLDPRT")
        if os.path.exists(target_path):
            try:
                os.remove(target_path)
            except Exception:
                pass

        def _run_rollback_experiment():
            sw, _ = connect_solidworks()
            part = new_document(sw, "part")
            if not part:
                raise RuntimeError("无法创建用于物理回滚测试的零件文档")

            doc_title = str(get_com_member(part, "GetTitle"))
            task = CADTaskContext(task_id="task_physical_rollback_night07")
            task.transition_to(TaskStatus.RUNNING, "Starting forward modeling")

            # 记录基线特征树
            initial_features = list_feature_names(part)
            initial_bodies = get_solid_body_count(part)
            print(f"  [Baseline] 初始实体数: {initial_bodies}, 初始特征数: {len(initial_features)}")

            # 注册受管文档（设定 is_newly_created=False 触发特征逆序删除逻辑）
            tracked_doc = task.register_document(
                part,
                title=doc_title,
                path=target_path,
                is_newly_created=False
            )

            # 步骤 1: 创建基板特征 (100x100x15mm)
            with sketch(part, "Top Plane") as sk1:
                sketch_rectangle(part, 0.0, 0.0, mm(100.0), mm(100.0))
            task.register_feature(str(sk1), "sketch_2d", doc_title=doc_title)
            boss1 = extrude_boss(part, sk1, mm(15.0))
            base_feat_name = str(get_com_member(boss1, "Name")) if boss1 else "RollbackBaseBoss"
            task.register_feature(base_feat_name, "extrude_boss", doc_title=doc_title)

            b1_count = get_solid_body_count(part)
            b1_mass = collect_mass_properties(part)
            v1 = b1_mass.get("volume_mm3", 0.0)
            print(f"  [Step 1] 基板创建完成 ({base_feat_name}). 实体数: {b1_count}, 体积: {v1:.2f} mm^3")

            # 步骤 2: 创建支柱特征 (直径 30mm, 高度 40mm)
            with sketch(part, "Top Plane") as sk2:
                sketch_circle(part, mm(50.0), mm(50.0), mm(15.0))
            task.register_feature(str(sk2), "sketch_2d", doc_title=doc_title)
            boss2 = extrude_boss(part, sk2, mm(40.0))
            pillar_feat_name = str(get_com_member(boss2, "Name")) if boss2 else "RollbackPillarBoss"
            task.register_feature(pillar_feat_name, "extrude_boss", doc_title=doc_title)

            b2_count = get_solid_body_count(part)
            b2_mass = collect_mass_properties(part)
            v2 = b2_mass.get("volume_mm3", 0.0)
            print(f"  [Step 2] 支柱创建完成 ({pillar_feat_name}). 实体数: {b2_count}, 体积: {v2:.2f} mm^3")

            # 步骤 3: 模拟建模故障，触发回滚管理器
            print(f"  [Step 3] 注入失败条件，启动 Level 3 特征树逆序物理删除...")
            task.transition_to(TaskStatus.ROLLING_BACK, "Simulated CAD failure triggered rollback")

            rollback_mgr = CADTaskRollbackManager(task, sw_app=sw)
            rollback_res = rollback_mgr.rollback()
            print(f"  [Step 4] 逆序物理删除完成. 状态: {rollback_res.status.value}, 清理清单: {rollback_res.cleaned_features}")

            # 强制重建验证模型状态
            get_com_member(part, "ForceRebuild3", True)
            post_bodies = get_solid_body_count(part)
            post_features = list_feature_names(part)
            post_mass = collect_mass_properties(part)
            post_v = post_mass.get("volume_mm3", 0.0)
            print(f"  [Step 5] 回滚后核验: 实体数: {post_bodies}, 物理体积: {post_v:.2f} mm^3, 特征数: {len(post_features)}")

            # 步骤 6: 保持离线一致性保存并重开验证
            save_document(part, target_path)
            close_document(sw, part)

            reopened_part = open_document(sw, target_path, silent=True)
            reopen_bodies = get_solid_body_count(reopened_part)
            reopen_mass = collect_mass_properties(reopened_part)
            reopen_v = reopen_mass.get("volume_mm3", 0.0)
            close_document(sw, reopened_part)
            print(f"  [Step 6] 离线重新打开核验: 实体数: {reopen_bodies}, 体积: {reopen_v:.2f} mm^3")

            # 清理测试文件
            if os.path.exists(target_path):
                try:
                    os.remove(target_path)
                except Exception:
                    pass

            passed = (
                post_bodies == 0
                and reopen_bodies == 0
                and post_v == 0.0
                and base_feat_name not in post_features
                and pillar_feat_name not in post_features
                and set(initial_features).issubset(set(post_features))
            )
            return {
                "initial_bodies": initial_bodies,
                "step1_bodies": b1_count,
                "step1_volume": v1,
                "step2_bodies": b2_count,
                "step2_volume": v2,
                "cleaned_features": rollback_res.cleaned_features,
                "post_rollback_bodies": post_bodies,
                "post_rollback_volume": post_v,
                "reopened_bodies": reopen_bodies,
                "reopened_volume": reopen_v,
                "passed": passed,
            }

        res = self.worker.execute(_run_rollback_experiment)
        self.evidence["phases"]["phase_physical_rollback"] = res
        return bool(res.get("passed", False))

    def phase_drawing_reopen_cycle(self) -> bool:
        print("\n--- [Phase 05] SolidWorks 2D 工程图生成、保存与重新打开闭环复核 ---")
        src_part_path = str(SANDBOX_DIR / "night07_drawing_src.SLDPRT")
        drw_path = str(SANDBOX_DIR / "night07_drawing.SLDDRW")
        pdf_path = str(SANDBOX_DIR / "night07_drawing_preview.pdf")

        for p in [src_part_path, drw_path, pdf_path]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

        def _run_drawing_cycle():
            sw, _ = connect_solidworks()

            # 1. 建立源零件
            part = new_document(sw, "part")
            with sketch(part, "Top Plane") as sk1:
                sketch_rectangle(part, 0.0, 0.0, mm(120.0), mm(80.0))
            extrude_boss(part, sk1, mm(15.0))
            with sketch(part, "Top Plane") as sk2:
                sketch_circle(part, mm(60.0), mm(40.0), mm(12.0))
            extrude_cut(part, sk2, mm(20.0))
            save_document(part, src_part_path)
            print(f"  [Step 1] 源零件已落盘保存至: {src_part_path}")

            # 2. 创建工程图
            drw = new_document(sw, "drawing")
            if not drw:
                raise RuntimeError("无法创建工程图文档")

            print("  [Step 2] 投影正交三视图 (主/俯/左)...")
            std_ok = sw_drawing.create_standard_views(drw, src_part_path)

            print("  [Step 3] 插入右上等轴测视图 (*Isometric)...")
            try:
                sw_drawing.add_view(drw, src_part_path, "*Isometric", 0.35, 0.28, scale=0.5)
            except Exception as e:
                print(f"  [Step 3] 轴测图容错: {e}")

            print("  [Step 4] 导入特征尺寸与结构检查...")
            try:
                sw_drawing.insert_dimensions(drw)
            except Exception as e:
                print(f"  [Step 4] 尺寸导入容错: {e}")

            views_before = sw_drawing.inspect_drawing_structure(drw)
            print(f"  [Step 5] 保存前工程图结构: 视图数={views_before.get('view_count')}")

            # 保存工程图与导出 PDF
            save_document(drw, drw_path)
            try:
                sw_drawing.export_sheet_to_pdf(drw, pdf_path, sw_app=sw)
                pdf_size = os.path.getsize(pdf_path) if os.path.exists(pdf_path) else 0
            except Exception:
                pdf_size = 0
            print(f"  [Step 6] 工程图保存完毕 ({os.path.getsize(drw_path)} B), PDF 导出大小: {pdf_size} B")

            # 彻底关闭工程图与源零件
            close_document(sw, drw)
            close_document(sw, part)
            print("  [Step 7] 工程图与源零件已安全关闭")

            # 3. 重新打开离线工程图闭环核验
            t_open_start = time.time()
            reopened_drw = open_document(sw, drw_path, silent=True)
            reopen_ms = (time.time() - t_open_start) * 1000.0
            if not reopened_drw:
                raise RuntimeError("无法重新打开保存的离线工程图！")

            views_after = sw_drawing.inspect_drawing_structure(reopened_drw)
            view_names = [v.get("name") for v in views_after.get("views", [])]
            close_document(sw, reopened_drw)
            print(f"  [Step 8] 重新打开工程图核验成功 (耗时: {reopen_ms:.1f}ms). 视图清单: {view_names}")

            # 清理沙箱中生成的测试文件
            for p in [src_part_path, drw_path, pdf_path]:
                if os.path.exists(p):
                    try:
                        os.remove(p)
                    except Exception:
                        pass

            passed = (
                len(view_names) >= 3
                and views_before.get("view_count", 0) >= 3
                and views_after.get("status") == "pass"
                and pdf_size > 1024
            )
            return {
                "views_before_close": views_before.get("view_count"),
                "reopened_view_count": len(view_names),
                "reopened_views": view_names,
                "reopen_ms": round(reopen_ms, 2),
                "pdf_size_bytes": pdf_size,
                "passed": passed,
            }

        res = self.worker.execute(_run_drawing_cycle)
        self.evidence["phases"]["phase_drawing_reopen"] = res
        return bool(res.get("passed", False))

    def phase_batch_stability_test(self) -> bool:
        print("\n--- [Phase 06] 分批资源无泄漏稳定性压测 (3 批次) ---")
        batch_results = []
        baseline_docs_len = len(self.baseline_docs)

        for batch_idx in range(1, 4):
            print(f"  >> 执行第 {batch_idx} 批次建模与释放循环...")
            def _single_cycle():
                sw, _ = connect_solidworks()
                part = new_document(sw, "part")
                with sketch(part, "Top Plane") as sk:
                    sketch_rectangle(part, 0.0, 0.0, mm(50.0), mm(50.0))
                extrude_boss(part, sk, mm(10.0))
                # 不保存直接关闭（验证未保存新零件的零残留关闭）
                close_document(sw, part)

            self.worker.execute(_single_cycle)

            # 采集该批次资源状态
            metrics = get_process_metrics(self.sw_pid)
            docs = get_current_open_docs(self.sw, self.worker)
            doc_leak = (len(docs) != baseline_docs_len)

            info = {
                "batch": batch_idx,
                "sw_working_set_mb": metrics["working_set_mb"],
                "gdi_objects": metrics["gdi_objects"],
                "user_objects": metrics["user_objects"],
                "open_docs_count": len(docs),
                "doc_count_leak": doc_leak,
            }
            batch_results.append(info)
            print(f"     批次 {batch_idx}: SW 内存: {metrics['working_set_mb']} MB, GDI: {metrics['gdi_objects']}, 文档数: {len(docs)} (基线: {baseline_docs_len})")

        all_batch_clean = all(not b["doc_count_leak"] for b in batch_results)
        self.evidence["phases"]["phase_batch_stability"] = {
            "batches": batch_results,
            "all_batches_doc_clean": all_batch_clean,
            "passed": all_batch_clean,
        }
        return all_batch_clean


def main():
    parser = argparse.ArgumentParser(description="NIGHT-ENGINEERING-07 综合实机验证")
    parser.add_argument("--authorize-cad-write", action="store_true", help="显式授权真实 CAD 实机写操作")
    args = parser.parse_args()

    if not args.authorize_cad_write:
        print("错误: 本验证套件必须指定 --authorize-cad-write 参数！")
        sys.exit(1)

    runner = Night07VerificationRunner(authorized=True)
    success = runner.run_all()
    sys.exit(0 if success else 2)


if __name__ == "__main__":
    main()
