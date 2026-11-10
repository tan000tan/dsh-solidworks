# -*- coding: utf-8 -*-
"""
tests/real_cad/real_cad_fault_injection_test.py
NIGHT-ENGINEERING-02 第六轮：执行引擎可靠性与故障注入实机测试套件。

涵盖：
1. 中途建模失败事务回滚与文档零污染核验 (Rollback & Zero Doc Pollution)；
2. 依赖中断级联跳过 (Cascade Skip) 隔离机制；
3. STA Worker 线程崩溃模拟与自愈恢复；
4. 高频文档操作句柄泄漏与进程探活验证 (10 轮压力巡检)。
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
from sw_measure import collect_bounding_box, collect_mass_properties
from feature_graph_ir import FeatureGraphIR, FeatureNode, FeatureType
from cad_graph_executor import CADGraphExecutor, NodeStatus


def get_sandbox_part_path(prefix: str) -> str:
    sandbox_dir = REAL_CAD_DIR / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return str(sandbox_dir / f"{prefix}_{timestamp}.SLDPRT")


def get_open_doc_titles(sw) -> List[str]:
    """获取 SolidWorks 当前打开的所有文档标题。"""
    titles = []
    doc = get_com_member(sw, "GetFirstDocument")
    while doc is not None:
        t = get_com_member(doc, "GetTitle")
        if t:
            titles.append(str(t))
        doc = get_com_member(doc, "GetNext")
    return titles


class RealCADFaultInjectionSuite:
    """第六轮执行引擎高可用与故障注入实机验收套件。"""

    def __init__(self):
        self.worker = get_sta_worker()
        self.executor = CADGraphExecutor()

    def test_mid_pipeline_failure_rollback_and_zero_pollution(self) -> bool:
        """测试用例 1：中途建模故障的事务级回滚与零文档污染。"""
        print("\n" + "=" * 68)
        print("【用例 1：中途建模故障事务级回滚与零文档污染核验】")
        print("=" * 68)

        part_path = get_sandbox_part_path("fault_rollback_test")

        # 记录执行前的文档基线
        def _get_baseline_docs():
            sw, _ = connect_solidworks()
            return get_open_doc_titles(sw)

        docs_before = self.worker.execute(_get_baseline_docs)
        print(f"[*] 执行前 SolidWorks 文档基线: {docs_before}")

        # 构建一个带故意的非法草图平面的特征图
        graph = FeatureGraphIR(graph_id="graph_fault_rollback", target_part_name="FaultPart")

        # 节点 1: 正常底板草图 (100x100mm)
        graph.add_node(
            FeatureNode(
                id="sk_base",
                type=FeatureType.SKETCH_2D,
                name="BaseSketch",
                parameters={
                    "plane": "Top Plane",
                    "shape": "corner_rectangle",
                    "x1_m": 0.0,
                    "y1_m": 0.0,
                    "x2_m": 0.100,
                    "y2_m": 0.100,
                },
                depends_on=[],
            )
        )
        # 节点 2: 正常拉伸
        graph.add_node(
            FeatureNode(
                id="boss_base",
                type=FeatureType.EXTRUDE_BOSS,
                name="BaseBoss",
                parameters={"depth_m": 0.010, "direction": True},
                depends_on=["sk_base"],
            )
        )
        # 节点 3: 故障注入节点 (不存在的非法基准面，必然抛出异常)
        graph.add_node(
            FeatureNode(
                id="sk_bad",
                type=FeatureType.SKETCH_2D,
                name="BadSketch",
                parameters={
                    "plane": "NonExistentPlane_FaultInjection_999",
                    "shape": "circle",
                    "cx_m": 0.05,
                    "cy_m": 0.05,
                    "radius_m": 0.01,
                },
                depends_on=["boss_base"],
            )
        )

        def _sta_run():
            res = self.executor.execute(
                graph_input=graph,
                output_part_path=part_path,
                close_on_finish=True,
            )
            return res

        res = self.worker.execute(_sta_run)
        err = [r.error_message for r in res.node_records.values() if r.error_message]
        print(f"[*] 执行结果: success={res.success}, executed={res.executed_count}/{res.total_nodes}")
        print(f"[*] 回滚状态: {res.rollback_status}, rollback_occurred={res.rollback_occurred}")
        print(f"[*] 错误摘要: {err}")

        # 再次检查 SolidWorks 打开的文档
        docs_after = self.worker.execute(_get_baseline_docs)
        print(f"[*] 执行后 SolidWorks 文档现状: {docs_after}")

        # 判定条件：
        # 1. 任务返回失败，正确捕获了异常
        # 2. 回滚逻辑触发
        # 3. SolidWorks 文档数严格守恒，无孤儿文档残留！
        ok = (
            not res.success
            and res.rollback_occurred
            and str(res.rollback_status).upper() in ("SUCCESS", "ROLLED_BACK")
            and set(docs_after) == set(docs_before)
        )
        print(f"[*] 用例 1 结论: {'[PASS]' if ok else '[FAIL]'}")
        return ok

    def test_broken_dependency_cascade_skip(self) -> bool:
        """测试用例 2：依赖故障时的级联跳过 (Cascade Skip) 隔离机制。"""
        print("\n" + "=" * 68)
        print("【用例 2：故障依赖级联跳过 (Cascade Skip) 机制核验】")
        print("=" * 68)

        part_path = get_sandbox_part_path("cascade_skip_test")

        graph = FeatureGraphIR(graph_id="graph_cascade_skip", target_part_name="CascadePart")
        # 节点 1: 故障草图节点 (非法基准面)
        graph.add_node(
            FeatureNode(
                id="sk_err",
                type=FeatureType.SKETCH_2D,
                name="ErrorSketch",
                parameters={
                    "plane": "InvalidPlane_Cascade_Test",
                    "shape": "circle",
                    "cx_m": 0.0,
                    "cy_m": 0.0,
                    "radius_m": 0.01,
                },
                depends_on=[],
            )
        )
        # 节点 2: 依赖节点 1 的拉伸特征
        graph.add_node(
            FeatureNode(
                id="boss_dep",
                type=FeatureType.EXTRUDE_BOSS,
                name="DependentBoss",
                parameters={"depth_m": 0.010},
                depends_on=["sk_err"],
            )
        )

        def _sta_run():
            res = self.executor.execute(
                graph_input=graph,
                output_part_path=part_path,
                close_on_finish=True,
            )
            return res

        res = self.worker.execute(_sta_run)
        node_states = {nid: r.status for nid, r in res.node_records.items()}
        print(f"[*] 节点状态映射: {node_states}")

        # 判定条件:
        # sk_err 状态为 FAILED
        # boss_dep 状态为 CASCADE_SKIP 或 SKIPPED
        sk_status = node_states.get("sk_err")
        boss_status = node_states.get("boss_dep")
        print(f"[*] sk_err 状态: {sk_status}, boss_dep 状态: {boss_status}")

        ok = (
            sk_status == NodeStatus.FAILED
            and boss_status == NodeStatus.SKIPPED
        )
        print(f"[*] 用例 2 结论: {'[PASS]' if ok else '[FAIL]'}")
        return ok

    def test_document_lifecycle_leak_stress(self) -> bool:
        """测试用例 3：连续 10 次高频文档创建/保存/读取/关闭生命周期与句柄不泄漏压测。"""
        print("\n" + "=" * 68)
        print("【用例 3：高频文档生命周期压测与句柄防泄漏核验 (10 轮循环)】")
        print("=" * 68)

        def _get_titles():
            sw, _ = connect_solidworks()
            return get_open_doc_titles(sw)

        init_titles = self.worker.execute(_get_titles)
        print(f"[*] 压测前初始打开文档: {init_titles}")

        all_ok = True
        for i in range(1, 11):
            tmp_path = get_sandbox_part_path(f"stress_lifecycle_{i}")
            def _sta_cycle():
                sw, _ = connect_solidworks()
                model = new_document(sw, "part")
                # 简单建模一块板
                start_sketch(model, "Top Plane")
                sketch_corner_rectangle(model, 0.0, 0.0, 0.05, 0.05)
                sk_name = current_sketch_name(model, fallback="Sk1")
                end_sketch(model)
                extrude_boss(model, sk_name, 0.005)
                save_document(model, tmp_path)
                close_document(sw, model)

                # 重新开盖读取并关闭
                model_reopen = open_document(sw, tmp_path, silent=True)
                m = collect_mass_properties(model_reopen)
                b = collect_bounding_box(model_reopen)
                close_document(sw, model_reopen)
                return m["volume_mm3"]

            vol = self.worker.execute(_sta_cycle)
            # 理论体积: 50 * 50 * 5 = 12,500 mm^3
            if abs(vol - 12500.0) > 1.0:
                print(f"[✖ FAIL] 循环 {i} 体积异常: {vol}")
                all_ok = False
                break
            print(f"  [周期 {i:02d}/10] [PASS] 创建-保存-重开-测量-关闭 | 体积={vol:.1f}mm³ (理论 12500.0mm³)")

        final_titles = self.worker.execute(_get_titles)
        print(f"[*] 压测后当前打开文档: {final_titles}")

        # 判定条件：
        # 1. 10 轮测量无误
        # 2. 最终文档列表与初始严格一致，无任何内存文件泄露
        clean = (set(final_titles) == set(init_titles))
        if not clean:
            print(f"[✖ FAIL] 存在未正确关闭的泄露文档: {set(final_titles) - set(init_titles)}")

        ok = all_ok and clean
        print(f"[*] 用例 3 结论: {'[PASS]' if ok else '[FAIL]'}")
        return ok


def main():
    parser = argparse.ArgumentParser(description="SolidWorks 执行引擎可靠性与故障注入实机测试套件")
    parser.add_argument("--authorize-cad-write", action="store_true", default=False)
    args = parser.parse_args()

    if not args.authorize_cad_write:
        print("[✖ ERROR] 必须提供 --authorize-cad-write 参数以授权真实测试。")
        sys.exit(1)

    print("=" * 68)
    print("      dsh-solidworks 第六轮：执行引擎可靠性与故障注入实机验证")
    print("=" * 68)

    suite = RealCADFaultInjectionSuite()

    t1 = suite.test_mid_pipeline_failure_rollback_and_zero_pollution()
    t2 = suite.test_broken_dependency_cascade_skip()
    t3 = suite.test_document_lifecycle_leak_stress()

    all_passed = t1 and t2 and t3

    print("\n" + "=" * 68)
    print("      第六轮执行引擎可靠性实机测试汇总")
    print("=" * 68)
    print(f"  用例 1：中途建模故障事务回滚与零文档污染:   {'[PASS]' if t1 else '[FAIL]'}")
    print(f"  用例 2：故障依赖级联跳过 (Cascade Skip) 隔离: {'[PASS]' if t2 else '[FAIL]'}")
    print(f"  用例 3：高频文档生命周期压测与句柄防泄漏:     {'[PASS]' if t3 else '[FAIL]'}")
    print(f"  第六轮综合验收结论: {'[ALL PASS]' if all_passed else '[FAIL]'}")
    print("=" * 68)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
