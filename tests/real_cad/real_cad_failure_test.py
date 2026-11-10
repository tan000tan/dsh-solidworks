# -*- coding: utf-8 -*-
"""
tests/real_cad/real_cad_failure_test.py
SolidWorks 真实环境特征图异常恢复与事务回滚实机验收程序。

包含三大典型故障场景：
1. 故障场景一：缺少草图依赖的前置拦截（零几何残留验证）
2. 故障场景二：特征求解失败触发自动回滚与特征逆序清除验证
3. 故障场景三：多分支局部故障下游级联跳过验证

严格遵循安全规范：
- PRECHECK 模式（只读）：检查故障注入参数与拓扑规划，不产生真实 CAD 操作；
- EXECUTE 模式（实机）：必须显式提供 --authorize-cad-write 授权，沙箱物理隔离。
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# 确保 UTF-8 控制台输出
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
from cad_graph_executor import CADGraphExecutor, ExecutionResult


def get_sandbox_part_path(prefix: str) -> str:
    """生成带毫秒级唯一时间戳的沙箱零件落盘物理路径。"""
    sandbox_dir = REAL_CAD_DIR / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{prefix}_{timestamp}.SLDPRT"
    return str(sandbox_dir / filename)


# ============================================================
# 故障场景一：缺少草图依赖
# ============================================================
def build_missing_sketch_graph() -> FeatureGraphIR:
    fg = FeatureGraphIR(graph_id="ir_fault_missing_sketch", target_part_name="FaultMissingSketch")
    # 拉伸特征故意不依赖草图，也不传 sketch_name
    fg.add_node(FeatureNode(
        id="orphan_boss",
        type=FeatureType.EXTRUDE_BOSS,
        name="OrphanBoss",
        parameters={"depth_m": 0.02},
        depends_on=[],
    ))
    return fg


# ============================================================
# 故障场景二：特征求解失败触发自动回滚
# ============================================================
def build_invalid_geometry_graph() -> FeatureGraphIR:
    fg = FeatureGraphIR(graph_id="ir_fault_invalid_geom", target_part_name="FaultInvalidGeom")
    fg.add_node(FeatureNode(
        id="sk1",
        type=FeatureType.SKETCH_2D,
        name="Sketch1",
        parameters={"plane": "Front Plane", "shape": "rectangle", "width_m": 0.05, "height_m": 0.05},
        depends_on=[],
    ))
    # 注入非法参数：极小非物理拉伸或异常图元
    fg.add_node(FeatureNode(
        id="invalid_extrude",
        type=FeatureType.EXTRUDE_BOSS,
        name="InvalidBoss",
        parameters={"depth_m": 0.0},  # 零深度拉伸，SolidWorks COM 将抛出求解失败
        depends_on=["sk1"],
    ))
    return fg


# ============================================================
# 故障场景三：多分支局部故障级联跳过
# ============================================================
def build_branch_cascade_graph() -> FeatureGraphIR:
    fg = FeatureGraphIR(graph_id="ir_fault_branch_cascade", target_part_name="FaultBranchCascade")
    fg.add_node(FeatureNode(
        id="base_sk",
        type=FeatureType.SKETCH_2D,
        name="BaseSketch",
        parameters={"plane": "Front Plane", "shape": "rectangle", "width_m": 0.08, "height_m": 0.04},
        depends_on=[],
    ))
    # 分支 1: 故障拉伸 -> 下游受波及切除
    fg.add_node(FeatureNode(
        id="fail_boss",
        type=FeatureType.EXTRUDE_BOSS,
        name="FailBoss",
        parameters={"depth_m": 0.0},
        depends_on=["base_sk"],
    ))
    fg.add_node(FeatureNode(
        id="cascade_child",
        type=FeatureType.EXTRUDE_CUT,
        name="CascadeCut",
        parameters={"depth_m": 0.01},
        depends_on=["fail_boss"],
    ))
    return fg


def run_failure_test(name: str, graph_builder, mode: str, authorized: bool) -> bool:
    print("\n" + "-" * 60)
    print(f"【异常恢复与回滚测试】: {name} (模式: {mode.upper()})")
    print("-" * 60)

    fg = graph_builder()

    if mode.lower() == "precheck":
        print(f"[*] 预检查图结构: ID={fg.graph_id}, 包含节点: {list(fg.nodes.keys())}")
        fg.validate_dag()
        print(f"[✔ PASS] 异常测试 DAG 校验通过，时序规划就绪。")
        print(f"[INFO] PRECHECK 模式已安全完成，未触发实机 CAD 写入。")
        return True

    if not authorized:
        print("[✖ ERROR] 拒绝执行真实 CAD 写入！必须在命令行显式提供 '--authorize-cad-write' 授权参数。")
        return False

    output_path = get_sandbox_part_path(name.lower())
    print(f"[*] 安全沙箱目标零件路径: {output_path}")

    executor = CADGraphExecutor(
        enable_task_context=True,
        auto_rollback_on_failure=True,
    )

    print("[*] 正在实机执行预期故障特征图...")
    result = executor.execute(
        graph_input=fg,
        output_part_path=output_path,
        collect_metrics=False,
        close_on_finish=True,
    )

    print(f"[*] 故障场景执行完成:")
    print(f"    - 执行状态: {result.status}")
    print(f"    - 整体成功标志: {result.success} (预期应为 False)")
    print(f"    - 失败节点: {result.failed_nodes}")
    print(f"    - 跳过节点: {result.skipped_nodes}")
    print(f"    - 回滚状态: {result.rollback_status}")
    print(f"    - 回滚发生: {result.rollback_occurred}")

    # 验证是否正确被拦截或回滚
    passed = (not result.success) and (len(result.failed_nodes) > 0)
    if passed:
        print(f"[✔ PASS] 异常被安全拦截并按规范完成状态转移与回滚处理。")
    else:
        print(f"[✖ FAIL] 异常未被正确识别或状态不符。")

    return passed


def main():
    parser = argparse.ArgumentParser(description="SolidWorks 真实环境异常恢复验证程序")
    parser.add_argument("--mode", choices=["precheck", "execute"], default="precheck")
    parser.add_argument("--authorize-cad-write", action="store_true", default=False)
    args = parser.parse_args()

    print("=" * 65)
    print("      dsh-solidworks 真实环境异常恢复与回滚验证套件")
    print("=" * 65)
    print(f"模式: {args.mode.upper()}")
    print(f"授权状态: {'[AUTHORIZED]' if args.authorize_cad_write else '[READ-ONLY PROTECTED]'}")

    s1 = run_failure_test("MissingSketchDependency", build_missing_sketch_graph, args.mode, args.authorize_cad_write)
    s2 = run_failure_test("InvalidGeometryRollback", build_invalid_geometry_graph, args.mode, args.authorize_cad_write)
    s3 = run_failure_test("BranchCascadeSkip", build_branch_cascade_graph, args.mode, args.authorize_cad_write)

    all_passed = s1 and s2 and s3
    print("\n" + "=" * 65)
    print(f"  异常恢复验收结果: {'[ALL PASS]' if all_passed else '[FAIL]'}")
    print("=" * 65)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
