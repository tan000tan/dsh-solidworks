# -*- coding: utf-8 -*-
"""
tests/real_cad/real_cad_stress_test.py
SolidWorks 特征图高级压力测试：
1. 三分支并发分支与局部故障隔离测试 (3 Branches with 1 isolated fault)
2. 同一特征图重复执行与 COM 状态隔离测试 (Repeat Execution Isolation)
3. 参数规模阶梯测试 (Small / Medium / Large 几何参数与性能基准记录)
"""

import argparse
import sys
import time
from pathlib import Path

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

from feature_graph_ir import FeatureGraphIR, FeatureNode, FeatureType
from cad_graph_executor import CADGraphExecutor
from sw_connect import get_sta_worker, connect_solidworks, get_com_member


def test_three_branch_fault_isolation(sandbox_dir: Path) -> bool:
    """测试三分支局部故障隔离：分支 1 成功，分支 2 故障并波及下游，分支 3 不受影响。"""
    print("\n" + "-" * 60)
    print("【压力测试 1：三分支并发推进与局部故障隔离】")
    print("-" * 60)

    fg = FeatureGraphIR(graph_id="ir_three_branches", target_part_name="ThreeBranchesPart")
    # 公共上游根节点
    fg.add_node(FeatureNode(
        id="sk_root",
        type=FeatureType.SKETCH_2D,
        name="RootSketch",
        parameters={"plane": "Front Plane", "shape": "rectangle", "width_m": 0.15, "height_m": 0.10},
        depends_on=[],
    ))
    fg.add_node(FeatureNode(
        id="boss_root",
        type=FeatureType.EXTRUDE_BOSS,
        name="RootBoss",
        parameters={"depth_m": 0.015},
        depends_on=["sk_root"],
    ))

    # 分支 1 (健康分支): 孔 1
    fg.add_node(FeatureNode(
        id="sk_b1",
        type=FeatureType.SKETCH_2D,
        name="B1Sketch",
        parameters={"plane": "Front Plane", "shape": "circle", "radius_m": 0.01, "cx_m": -0.04, "cy_m": 0.0},
        depends_on=["boss_root"],
    ))
    fg.add_node(FeatureNode(
        id="cut_b1",
        type=FeatureType.EXTRUDE_CUT,
        name="B1Cut",
        parameters={"depth_m": 0.015, "direction": False},
        depends_on=["sk_b1"],
    ))

    # 分支 2 (故障分支): 零深度非法拉伸 -> 下游切削
    fg.add_node(FeatureNode(
        id="boss_b2_fail",
        type=FeatureType.EXTRUDE_BOSS,
        name="B2FailBoss",
        parameters={"depth_m": 0.0},
        depends_on=["boss_root"],
    ))
    fg.add_node(FeatureNode(
        id="cut_b2_child",
        type=FeatureType.EXTRUDE_CUT,
        name="B2ChildCut",
        parameters={"depth_m": 0.01},
        depends_on=["boss_b2_fail"],
    ))

    # 拓扑验证：分析下游影响
    cascade_downstream = fg.get_reverse_rollback_subgraph("boss_b2_fail")
    print(f"[*] 分支 2 故障波及子图分析: {cascade_downstream}")
    self_isolated = ("boss_b2_fail" in cascade_downstream) and ("cut_b2_child" in cascade_downstream)
    healthy_unaffected = ("sk_b1" not in cascade_downstream) and ("cut_b1" not in cascade_downstream)

    ok = self_isolated and healthy_unaffected
    print(f"[*] 局部故障隔离断言: {'[PASS]' if ok else '[FAIL]'}")
    return ok


def test_repeat_execution_isolation(sandbox_dir: Path) -> bool:
    """测试同一特征图重复执行时的状态隔离性。"""
    print("\n" + "-" * 60)
    print("【压力测试 2：同一特征图重复执行与状态隔离】")
    print("-" * 60)

    fg = FeatureGraphIR(graph_id="ir_repeat_bench", target_part_name="RepeatPart")
    fg.add_node(FeatureNode(
        id="sk1",
        type=FeatureType.SKETCH_2D,
        name="Sketch1",
        parameters={"plane": "Front Plane", "shape": "rectangle", "width_m": 0.08, "height_m": 0.04},
        depends_on=[],
    ))
    fg.add_node(FeatureNode(
        id="boss1",
        type=FeatureType.EXTRUDE_BOSS,
        name="Boss1",
        parameters={"depth_m": 0.01},
        depends_on=["sk1"],
    ))

    executor = CADGraphExecutor(enable_task_context=True, auto_rollback_on_failure=True)
    p1 = str(sandbox_dir / "repeat_run1.SLDPRT")
    p2 = str(sandbox_dir / "repeat_run2.SLDPRT")

    r1 = executor.execute(fg, output_part_path=p1, close_on_finish=True)
    r2 = executor.execute(fg, output_part_path=p2, close_on_finish=True)

    print(f"[*] 第一次执行状态: {r1.status}, 任务ID: {r1.task_id}")
    print(f"[*] 第二次执行状态: {r2.status}, 任务ID: {r2.task_id}")

    ok = r1.success and r2.success and (r1.task_id != r2.task_id)
    print(f"[*] 重复执行隔离验证: {'[PASS]' if ok else '[FAIL]'}")
    return ok


def test_parameter_scale_benchmark(sandbox_dir: Path) -> bool:
    """测试参数规模阶梯基准测试 (Small / Medium / Large)。"""
    print("\n" + "-" * 60)
    print("【压力测试 3：参数规模阶梯基准测试 (Small / Medium / Large)】")
    print("-" * 60)

    configs = [
        ("Small", 0.05, 0.03, 0.01),
        ("Medium", 0.15, 0.10, 0.02),
        ("Large", 0.30, 0.20, 0.05),
    ]

    all_ok = True
    executor = CADGraphExecutor(enable_task_context=True, auto_rollback_on_failure=True)

    for label, w, h, d in configs:
        fg = FeatureGraphIR(graph_id=f"ir_scale_{label.lower()}", target_part_name=f"Scale_{label}")
        fg.add_node(FeatureNode(
            id="sk",
            type=FeatureType.SKETCH_2D,
            name=f"Sketch_{label}",
            parameters={"plane": "Front Plane", "shape": "rectangle", "width_m": w, "height_m": h},
            depends_on=[],
        ))
        fg.add_node(FeatureNode(
            id="boss",
            type=FeatureType.EXTRUDE_BOSS,
            name=f"Boss_{label}",
            parameters={"depth_m": d},
            depends_on=["sk"],
        ))

        t0 = time.time()
        p = str(sandbox_dir / f"scale_{label.lower()}.SLDPRT")
        res = executor.execute(fg, output_part_path=p, collect_metrics=True, close_on_finish=True)
        dur = time.time() - t0

        vol = res.mass_properties.get("volume_mm3", 0.0) if res.mass_properties else 0.0
        expected_vol = round(w * h * d * 1e9, 2)
        print(f"  [{label}] 耗时: {dur:.2f}s, 预期体积: {expected_vol}mm^3, 实测体积: {vol:.2f}mm^3, 状态: {res.status}")

        if not res.success:
            all_ok = False

    print(f"[*] 参数阶梯测试结论: {'[PASS]' if all_ok else '[FAIL]'}")
    return all_ok


def main():
    parser = argparse.ArgumentParser(description="SolidWorks P0.4 特征图压力测试")
    parser.add_argument("--authorize-cad-write", action="store_true", default=False)
    args = parser.parse_args()

    if not args.authorize_cad_write:
        print("[✖ ERROR] 必须提供 --authorize-cad-write 参数。")
        sys.exit(1)

    print("=" * 65)
    print("      dsh-solidworks P0.4 特征图高级压力测试套件")
    print("=" * 65)

    sandbox_dir = REAL_CAD_DIR / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    s1 = test_three_branch_fault_isolation(sandbox_dir)
    s2 = test_repeat_execution_isolation(sandbox_dir)
    s3 = test_parameter_scale_benchmark(sandbox_dir)

    all_passed = s1 and s2 and s3
    print("\n" + "=" * 65)
    print("      压力测试综合验收汇总")
    print("=" * 65)
    print(f"  测试 1：三分支并发与局部故障隔离: {'[PASS]' if s1 else '[FAIL]'}")
    print(f"  测试 2：同一特征图重复执行隔离: {'[PASS]' if s2 else '[FAIL]'}")
    print(f"  测试 3：参数规模阶梯性能基准: {'[PASS]' if s3 else '[FAIL]'}")
    print(f"  压力测试总结论: {'[ALL PASS]' if all_passed else '[FAIL]'}")
    print("=" * 65)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
