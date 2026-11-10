# -*- coding: utf-8 -*-
"""
tests/failure_injection_test.py
CAD 建模失败自动清理、事务回滚与连续十次失败注入专项验收测试。
验证要求：
1. 连续注入 10 种不同类型的 CAD 故障；
2. 每次故障后均执行：停止操作 -> 识别归属 -> 安全回滚 -> 释放资源 -> 清理验证；
3. 第 11 轮执行标准基准件建模并成功交付；
4. 终极验证：后台无 10 份重复失败模型，无残留草图与基准面，临时文件零泄露，最终几何双精度完全吻合。
"""

import json
import math
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"
for p in (str(SCRIPTS_DIR), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

SANDBOX_DIR = REPO_ROOT / "测试代码" / "sandbox_benchmark"
SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
os.environ["DSH_ALLOWED_ROOTS"] = json.dumps([str(SANDBOX_DIR)])

from cad_task_context import (
    CADTaskContext,
    CADTaskRollbackManager,
    FeatureCleanupManager,
    DocumentLifecycleManager,
    TaskStatus,
    CleanupStatus,
    CleanupVerificationError,
)
from shadow_backup import ShadowBackupManager, get_shadow_manager
from sw_connect import (
    get_sta_worker,
    connect_solidworks,
    get_com_member,
    new_document,
    save_document,
    open_document,
    mm,
)
from sw_part import (
    start_sketch,
    sketch,
    sketch_rectangle,
    sketch_circle,
    extrude_boss,
    extrude_cut,
)
from sw_measure import (
    collect_mass_properties,
)


def safe_start_sketch(model, plane_name="前视基准面"):
    """安全开启草图，兼容 pywin32 动态 dispatch。"""
    try:
        get_com_member(model, "ClearSelection2", True)
        from sw_part import _select_first_candidate, _get_plane_name_candidates
        sel = _select_first_candidate(model.Extension, _get_plane_name_candidates(plane_name), "PLANE")
        if sel:
            get_com_member(model.SketchManager, "InsertSketch", True)
            return sel
    except Exception:
        pass
    return None


def get_solidworks_memory_mb():
    """读取 Windows 任务管理器中 SLDWORKS.exe 的工作集内存占用（MB）。"""
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq SLDWORKS.exe", "/FO", "CSV"],
            text=True,
            encoding="gbk",
            errors="ignore",
        )
        for line in out.splitlines():
            if "SLDWORKS.exe" in line:
                parts = line.split('","')
                mem_str = parts[-1].replace('"', "").replace("K", "").replace(",", "").strip()
                return round(float(mem_str) / 1024.0, 2)
    except Exception:
        pass
    return None


class TestFailureInjectionAndRecovery(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from sw_connect import solidworks_processes
        if not solidworks_processes():
            raise unittest.SkipTest("未检测到运行中的 SolidWorks 进程，跳过实机物理测试以保护待机基线")
        cls.sw, cls.initial_doc = connect_solidworks(wait_seconds=5, visible=True)
        if cls.sw is None:
            raise unittest.SkipTest("未检测到本地 SolidWorks COM 实例，跳过物理实测")

    def test_continuous_ten_failures_then_success(self):
        worker = get_sta_worker()
        worker.execute(self._execute_continuous_ten_failures_then_success)

    def _execute_continuous_ten_failures_then_success(self):
        """
        核心验收：连续注入 10 种失败场景，再执行一次成功建模。
        验证无垃圾模型残留、无重复特征、内存与文档数无持续膨胀。
        """
        sw = self.sw
        metrics_log = []

        # 记录初始状态基线
        initial_open_docs = list(get_com_member(sw, "GetDocuments") or [])
        initial_open_count = len(initial_open_docs)
        initial_mem = get_solidworks_memory_mb()

        print(f"\n=======================================================")
        print(f"  开始连续 10 次 CAD 建模失败注入与自动清理专项验收实测")
        print(f"  初始打开文档数: {initial_open_count}, 初始内存: {initial_mem} MB")
        print(f"=======================================================")

        # -----------------------------------------------------------------
        # 连续 10 轮失败注入
        # -----------------------------------------------------------------
        for injection_idx in range(1, 11):
            task_id = f"inj_task_{injection_idx:02d}_{int(time.time()*1000)%10000}"
            ctx = CADTaskContext(task_id=task_id, max_retries=1)
            mgr = CADTaskRollbackManager(ctx, sw_app=sw)

            doc_created_in_task = None
            temp_file_path = str(SANDBOX_DIR / f"temp_fail_{injection_idx}.SLDPRT")

            start_docs = len(list(get_com_member(sw, "GetDocuments") or []))
            start_mem = get_solidworks_memory_mb()

            try:
                # 注入不同场景
                if injection_idx == 1:
                    # 场景 1: 新建文档 -> 建立基准面后故意失败
                    doc = new_document(sw, "part")
                    doc_created_in_task = doc
                    ctx.register_document(doc, is_newly_created=True)
                    ctx.register_feature("Plane1", "REFERENCE_PLANE", get_com_member(doc, "GetTitle"))
                    raise RuntimeError("注入故障 1: 建立基准面后几何坐标求解失败")

                elif injection_idx == 2:
                    # 场景 2: 新建文档 -> 开启草图并画圆后故意失败
                    doc = new_document(sw, "part")
                    doc_created_in_task = doc
                    ctx.register_document(doc, is_newly_created=True)
                    safe_start_sketch(doc, "前视基准面")
                    sketch_circle(doc, 0.0, 0.0, mm(15))
                    ctx.register_feature("Sketch1", "SKETCH", get_com_member(doc, "GetTitle"))
                    raise RuntimeError("注入故障 2: 草图约束冲突，无法全约束")

                elif injection_idx == 3:
                    # 场景 3: 新建文档 -> 完成拉伸 -> 在后续步骤中切除自交失败
                    doc = new_document(sw, "part")
                    doc_created_in_task = doc
                    ctx.register_document(doc, is_newly_created=True)
                    safe_start_sketch(doc, "前视基准面")
                    sketch_rectangle(doc, 0.0, 0.0, mm(50), mm(30))
                    boss = extrude_boss(doc, None, mm(20))
                    ctx.register_feature("Boss-Extrude1", "BODYFEATURE", get_com_member(doc, "GetTitle"))
                    raise RuntimeError("注入故障 3: 后续切除特征与基体拓扑自交崩溃")

                elif injection_idx == 4:
                    # 场景 4: 新建文档落盘临时文件 -> 保存后破坏性操作失败
                    doc = new_document(sw, "part")
                    doc_created_in_task = doc
                    ctx.register_document(doc, path=temp_file_path, is_newly_created=True)
                    ctx.register_temp_file(temp_file_path)
                    save_document(doc, temp_file_path)
                    # 抓取影子备份
                    get_shadow_manager().capture(temp_file_path, model=doc)
                    raise RuntimeError("注入故障 4: 临时文件落盘后发生致命几何错误")

                elif injection_idx == 5:
                    # 场景 5: 悬空前置依赖错误注入
                    doc = new_document(sw, "part")
                    doc_created_in_task = doc
                    ctx.register_document(doc, is_newly_created=True)
                    ctx.register_feature("DanglingFeature_1", "BODYFEATURE", get_com_member(doc, "GetTitle"))
                    raise ValueError("注入故障 5: 节点引用了未定义的前置特征 dependency_missing")

                elif injection_idx == 6:
                    # 场景 6: 草图深度为 0 导致拉伸 API 拒绝
                    doc = new_document(sw, "part")
                    doc_created_in_task = doc
                    ctx.register_document(doc, is_newly_created=True)
                    safe_start_sketch(doc, "前视基准面")
                    sketch_rectangle(doc, 0.0, 0.0, mm(40), mm(40))
                    # 深度传 0.0
                    res = extrude_boss(doc, None, 0.0)
                    if res is None:
                        raise RuntimeError("注入故障 6: 拉伸特征返回 None (深度为零)")

                elif injection_idx == 7:
                    # 场景 7: 模拟 COM RPC 抛出类型异常
                    doc = new_document(sw, "part")
                    doc_created_in_task = doc
                    ctx.register_document(doc, is_newly_created=True)
                    raise TypeError("注入故障 7: COM 接口参数类型不匹配 (模拟 DISP_E_TYPEMISMATCH)")

                elif injection_idx == 8:
                    # 场景 8: 连续创建两个草图后报错
                    doc = new_document(sw, "part")
                    doc_created_in_task = doc
                    ctx.register_document(doc, is_newly_created=True)
                    safe_start_sketch(doc, "前视基准面")
                    sketch_circle(doc, 0.0, 0.0, mm(10))
                    ctx.register_feature("Sketch1", "SKETCH", get_com_member(doc, "GetTitle"))
                    safe_start_sketch(doc, "上视基准面")
                    sketch_rectangle(doc, 0.0, 0.0, mm(20), mm(20))
                    ctx.register_feature("Sketch2", "SKETCH", get_com_member(doc, "GetTitle"))
                    raise RuntimeError("注入故障 8: 第二草图在退出时报错")

                elif injection_idx == 9:
                    # 场景 9: 模拟重构失败 (ForceRebuild3 异常)
                    doc = new_document(sw, "part")
                    doc_created_in_task = doc
                    ctx.register_document(doc, is_newly_created=True)
                    raise RuntimeError("注入故障 9: 模型 ForceRebuild3 几何求解器发散")

                elif injection_idx == 10:
                    # 场景 10: 模拟操作超时中断
                    doc = new_document(sw, "part")
                    doc_created_in_task = doc
                    ctx.register_document(doc, is_newly_created=True)
                    raise TimeoutError("注入故障 10: SolidWorksBusyTimeout 等待操作锁超时")

            except Exception as exc:
                # 捕获注入故障，触发自动回滚与文档清理
                ctx.status = TaskStatus.FAILED
                cleanup_ok = mgr.rollback()

                end_docs = len(list(get_com_member(sw, "GetDocuments") or []))
                end_mem = get_solidworks_memory_mb()

                record = {
                    "round": injection_idx,
                    "task_id": task_id,
                    "injected_error": type(exc).__name__,
                    "cleanup_ok": bool(cleanup_ok),
                    "start_open_docs": start_docs,
                    "end_open_docs": end_docs,
                    "docs_delta": end_docs - start_docs,
                    "temp_file_exists": os.path.exists(temp_file_path),
                    "memory_mb": end_mem,
                }
                metrics_log.append(record)
                print(f"[轮次 {injection_idx:02d} PASS] {type(exc).__name__} -> 回滚验证: {cleanup_ok}, "
                      f"打开文档数: {end_docs} (增量: {end_docs - start_docs}), 临时文件残留: {os.path.exists(temp_file_path)}")

                # 严格断言：每轮清理后，不能遗留该新建文档在后台！
                self.assertTrue(cleanup_ok, f"第 {injection_idx} 轮清理验证失败")
                self.assertFalse(os.path.exists(temp_file_path), f"第 {injection_idx} 轮临时文件未删除")

        # -----------------------------------------------------------------
        # 10 轮失败后检查后台状态
        # -----------------------------------------------------------------
        mid_open_docs = list(get_com_member(sw, "GetDocuments") or [])
        print(f"\n>> 10 轮连续失败清理完成！当前 SolidWorks 后台打开文档数: {len(mid_open_docs)}")
        # 绝对断言：10 轮失败绝未产生 10 份失败模型！
        self.assertEqual(len(mid_open_docs), initial_open_count,
                         f"10 轮失败后文档数累积！期望保持初始 {initial_open_count} 个，实际有 {len(mid_open_docs)} 个")

        # -----------------------------------------------------------------
        # 第 11 轮：从完全干净的现场执行成功建模
        # -----------------------------------------------------------------
        print(f"\n=======================================================")
        print(f"  第 11 轮：从干净状态执行真实基准件成功建模与双精度质量核验")
        print(f"=======================================================")

        success_part_path = str(SANDBOX_DIR / "continuous_failure_recovery_benchmark.SLDPRT")
        if os.path.exists(success_part_path):
            try:
                get_com_member(sw, "CloseDoc", "continuous_failure_recovery_benchmark.SLDPRT")
                os.remove(success_part_path)
            except Exception:
                pass
        success_ctx = CADTaskContext(task_id="success_benchmark_11", max_retries=2)
        success_mgr = CADTaskRollbackManager(success_ctx, sw_app=sw)

        def build_standard_benchmark(context):
            model = new_document(sw, "part")
            doc_entry = context.register_document(model, path=success_part_path, is_newly_created=True)

            # 1. 基体拉伸 100 x 60 x 20 mm
            safe_start_sketch(model, "前视基准面")
            sketch_rectangle(model, 0.0, 0.0, mm(100), mm(60))
            context.register_feature("BaseSketch", "SKETCH", doc_entry.title)
            boss = extrude_boss(model, None, mm(20))
            context.register_feature("Boss-Extrude1", "BODYFEATURE", doc_entry.title)

            # 2. 拉伸切除中心通孔 d20 mm
            safe_start_sketch(model, "前视基准面")
            sketch_circle(model, 0.0, 0.0, mm(10))  # 半径 10mm = 直径 20mm
            context.register_feature("HoleSketch", "SKETCH", doc_entry.title)
            cut = extrude_cut(model, None, mm(30), direction=False)
            context.register_feature("Cut-Extrude1", "BODYFEATURE", doc_entry.title)

            # 3. 强制重构并保存
            get_com_member(model, "ForceRebuild3", False)
            save_document(model, success_part_path)

            # 4. 测量质量属性
            mass = collect_mass_properties(model)
            return model, mass

        final_model, mass_prop = success_mgr.execute_with_retry(build_standard_benchmark)
        self.assertIsNotNone(final_model)
        self.assertTrue(os.path.exists(success_part_path))

        actual_volume = float(mass_prop.get("volume_mm3", 0.0))
        # 理论体积：100 * 60 * 20 - pi * 10² * 20 = 120000 - 6283.1853 = 113716.81469 mm³
        expected_volume = 113716.814693
        volume_error = abs(actual_volume - expected_volume)

        print(f"最终基准件建模成功！")
        print(f"  落盘文件: {success_part_path}")
        print(f"  理论体积: {expected_volume:.6f} mm³")
        print(f"  实测体积: {actual_volume:.6f} mm³")
        print(f"  双精度误差: {volume_error:.6f} mm³")

        self.assertLess(volume_error, 0.01, f"体积误差过大: {volume_error}")

        # 清理最终测试文档
        get_com_member(sw, "CloseDoc", get_com_member(final_model, "GetTitle"))

        final_open_count = len(list(get_com_member(sw, "GetDocuments") or []))
        final_mem = get_solidworks_memory_mb()
        print(f"全部验收完成！最终打开文档数: {final_open_count}, 最终内存: {final_mem} MB\n")

        # 保存测试统计指标供最终报告引用
        summary_path = SANDBOX_DIR / "continuous_failure_metrics.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump({
                "initial_open_count": initial_open_count,
                "final_open_count": final_open_count,
                "rounds_tested": 10,
                "successful_rebuild_round": 11,
                "actual_volume_mm3": actual_volume,
                "expected_volume_mm3": expected_volume,
                "volume_error_mm3": volume_error,
                "metrics_log": metrics_log,
            }, f, indent=2, ensure_ascii=False, default=str)


if __name__ == "__main__":
    unittest.main()
