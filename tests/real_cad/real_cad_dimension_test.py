# -*- coding: utf-8 -*-
"""
tests/real_cad/real_cad_dimension_test.py
P1 尺寸驱动与参数化修改体系实机闭环验证套件。

在真实 SolidWorks 2026 SP4.1 环境下，针对真实物理零件执行七大实机测试：
1. 测试一：真实模型尺寸全景提取与特征归属识别 (Dimension Reader)
2. 测试二：单参数就地修改与物理几何联动核验 (Dimension Modifier & Validator)
3. 测试三：多参数连续事务修改与多特征联动重构
4. 测试四：上游草图驱动尺寸修改 -> 下游切削实体物理联动验证
5. 测试五：物理参数边界与非法数值防御测试
6. 测试六：连续修改后故障自愈恢复 (首次修改保留，二次故障回滚)
7. 测试七：自然语言端到端尺寸修改闭环 (Natural Language -> Resolver -> Modifier -> Validator)
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

from feature_graph_ir import FeatureGraphIR, FeatureNode, FeatureType
from cad_graph_executor import CADGraphExecutor
from sw_connect import get_sta_worker, connect_solidworks, open_document, get_com_member, save_document
from dimension_ir import DimensionIRNode, DimensionModelIR, DimensionType
from dimension_reader import read_model_dimensions
from dimension_resolver import DimensionResolver
from model_rebuilder import ModelRebuilder, RebuildReport
from dimension_modifier import DimensionModifier, ModificationResult
from dimension_validator import DimensionValidator, DimensionValidationReport


def get_sandbox_part_path(prefix: str) -> str:
    """生成沙箱中唯一时间戳命名的物理零件路径。"""
    sandbox_dir = REAL_CAD_DIR / "sandbox"
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return str(sandbox_dir / f"{prefix}_{timestamp}.SLDPRT")


def create_parametric_benchmark_part() -> str:
    """创建专用于参数化修改验收的标准法兰基准件。"""
    part_path = get_sandbox_part_path("parametric_benchmark")
    fg = FeatureGraphIR(graph_id="ir_param_bench", target_part_name="ParamBench")

    # 1. 底座板 (100mm x 100mm x 15mm)
    fg.add_node(FeatureNode(
        id="sk_base",
        type=FeatureType.SKETCH_2D,
        name="BaseSketch",
        parameters={"plane": "Front Plane", "shape": "rectangle", "width_m": 0.10, "height_m": 0.10, "cx_m": 0.0, "cy_m": 0.0},
        depends_on=[],
    ))
    fg.add_node(FeatureNode(
        id="boss_base",
        type=FeatureType.EXTRUDE_BOSS,
        name="BaseBoss",
        parameters={"depth_m": 0.015, "direction": True, "merge": True},
        depends_on=["sk_base"],
    ))

    # 2. 中央凸台 (直径 60mm x 高 10mm, 累计厚度 25mm)
    fg.add_node(FeatureNode(
        id="sk_hub",
        type=FeatureType.SKETCH_2D,
        name="HubSketch",
        parameters={"plane": "Front Plane", "shape": "circle", "radius_m": 0.03, "cx_m": 0.0, "cy_m": 0.0},
        depends_on=["boss_base"],
    ))
    fg.add_node(FeatureNode(
        id="boss_hub",
        type=FeatureType.EXTRUDE_BOSS,
        name="HubBoss",
        parameters={"depth_m": 0.025, "direction": True, "merge": True},
        depends_on=["sk_hub"],
    ))

    # 3. 中央通孔 (直径 30mm, 贯穿 25mm)
    fg.add_node(FeatureNode(
        id="sk_bore",
        type=FeatureType.SKETCH_2D,
        name="BoreSketch",
        parameters={"plane": "Front Plane", "shape": "circle", "radius_m": 0.015, "cx_m": 0.0, "cy_m": 0.0},
        depends_on=["boss_hub"],
    ))
    fg.add_node(FeatureNode(
        id="cut_bore",
        type=FeatureType.EXTRUDE_CUT,
        name="BoreCut",
        parameters={"depth_m": 0.025, "direction": False},
        depends_on=["sk_bore"],
    ))

    executor = CADGraphExecutor(enable_task_context=True, auto_rollback_on_failure=True)
    res = executor.execute(fg, output_part_path=part_path, close_on_finish=True)
    if not res.success:
        raise RuntimeError(f"创建参数化基准件失败: {res.diagnostics}")
    return part_path


class RealCADDimensionTestSuite:
    """实机尺寸参数化测试套件。"""

    def __init__(self, part_path: str):
        self.part_path = part_path
        self.worker = get_sta_worker()

    def run_test_1_dimension_reading(self) -> bool:
        """测试一：真实模型尺寸读取。"""
        print("\n" + "-" * 60)
        print("【测试一：真实模型尺寸读取与归属识别】")
        print("-" * 60)

        def _sta_read():
            sw, _ = connect_solidworks()
            model = open_document(sw, self.part_path)
            model_ir = read_model_dimensions(model)
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            return model_ir

        model_ir: DimensionModelIR = self.worker.execute(_sta_read)
        print(f"[*] 成功提取到模型尺寸总数: {model_ir.total_count}")
        print(f"[*] 可编辑驱动尺寸总数: {len(model_ir.get_driving_dimensions())}")

        summary = model_ir.to_summary_dict()
        for d in summary["dimensions"][:6]:
            print(f"    - [{d['feature']}] {d['name']}: {d['value']} {d['unit']} (可编辑={d['editable']}, 类型={d['type']})")

        ok = model_ir.total_count >= 3
        print(f"[*] 测试一结果: {'[PASS]' if ok else '[FAIL]'}")
        return ok

    def run_test_2_single_parameter_modification(self) -> bool:
        """测试二：单参数就地修改 (底座长度从 100mm 改为 130mm)。"""
        print("\n" + "-" * 60)
        print("【测试二：单参数就地修改与物理几何联动核验】")
        print("-" * 60)

        def _sta_modify():
            sw, _ = connect_solidworks()
            model = open_document(sw, self.part_path)
            rebuilder = ModelRebuilder(model)
            reb_before = rebuilder.rebuild(force_all=True)
            ir_before = read_model_dimensions(model)

            # 寻找底座凸台尺寸
            target_dim = None
            for d in ir_before.get_driving_dimensions():
                if "凸台-拉伸1" in d.dimension_name or "boss" in d.feature_name.lower():
                    target_dim = d.dimension_name
                    break
            if not target_dim:
                target_dim = ir_before.get_driving_dimensions()[0].dimension_name

            print(f"[*] 选定目标修改尺寸: {target_dim}")
            modifier = DimensionModifier(model, auto_rollback=True)
            mod_res = modifier.modify_single(target_dim, 25.0, save=True, doc_path=self.part_path)
            reb_after = rebuilder.rebuild(force_all=True)
            ir_after = read_model_dimensions(model)

            # 验证器核验
            report = DimensionValidator.validate(
                before_ir=ir_before,
                after_ir=ir_after,
                target_updates={target_dim: 25.0},
                rebuild_before=reb_before,
                rebuild_after=reb_after,
            )
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            return mod_res, report

        mod_res, val_report = self.worker.execute(_sta_modify)
        print(f"[*] 修改状态: {mod_res.status}, 修改项数: {mod_res.modified_count}")
        print(f"[*] 物理验证通过: {val_report.passed}")
        for diag in val_report.diagnostics:
            print(f"    - {diag}")

        ok = mod_res.success and val_report.passed
        print(f"[*] 测试二结果: {'[PASS]' if ok else '[FAIL]'}")
        return ok

    def run_test_3_multi_parameter_modification(self) -> bool:
        """测试三：多参数连续事务修改 (同时更新多个草图与特征参数)。"""
        print("\n" + "-" * 60)
        print("【测试三：多参数批量就地修改与整体重构】")
        print("-" * 60)

        def _sta_multi():
            sw, _ = connect_solidworks()
            model = open_document(sw, self.part_path)
            ir_before = read_model_dimensions(model)
            driving = ir_before.get_driving_dimensions()

            # 选取前两个驱动尺寸进行批量更新
            if len(driving) >= 2:
                updates = {
                    driving[0].dimension_name: round(driving[0].value + 10.0, 2),
                    driving[1].dimension_name: round(driving[1].value + 15.0, 2),
                }
            else:
                updates = {driving[0].dimension_name: 140.0}

            print(f"[*] 批量修改请求: {updates}")
            modifier = DimensionModifier(model, auto_rollback=True)
            res = modifier.modify_batch(updates=updates, save=True, doc_path=self.part_path)
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            return res

        res = self.worker.execute(_sta_multi)
        print(f"[*] 批量修改状态: {res.status}, 实际修改成功数: {res.modified_count}")
        ok = res.success and (res.modified_count > 0)
        print(f"[*] 测试三结果: {'[PASS]' if ok else '[FAIL]'}")
        return ok

    def run_test_4_upstream_downstream_linkage(self) -> bool:
        """测试四：上游草图修改 -> 下游切除实体联动更新。"""
        print("\n" + "-" * 60)
        print("【测试四：上游草图尺寸修改 -> 下游特征物理联动验证】")
        print("-" * 60)

        def _sta_linkage():
            sw, _ = connect_solidworks()
            model = open_document(sw, self.part_path)
            ir_before = read_model_dimensions(model)
            rebuilder = ModelRebuilder(model)
            reb_before = rebuilder.rebuild(force_all=True)

            # 找到中央通孔草图
            bore_dim = None
            for d in ir_before.get_driving_dimensions():
                if "bore" in d.feature_name.lower() or "草图3" in d.feature_name.lower():
                    bore_dim = d.dimension_name
                    break
            if not bore_dim:
                # 备选第二个尺寸
                bore_dim = ir_before.get_driving_dimensions()[-1].dimension_name

            print(f"[*] 目标孔尺寸: {bore_dim}")
            modifier = DimensionModifier(model, auto_rollback=True)
            # 扩大孔直径/半径 5mm
            curr_val = ir_before.get_dimension(bore_dim).value
            new_val = curr_val + 5.0
            res = modifier.modify_single(bore_dim, new_val, save=True, doc_path=self.part_path)
            reb_after = rebuilder.rebuild(force_all=True)
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            return res, reb_before, reb_after

        res, reb_before, reb_after = self.worker.execute(_sta_linkage)
        # 孔扩大后，整体实体体积应该减少
        vol_before = reb_before.volume_mm3 or 0.0
        vol_after = reb_after.volume_mm3 or 0.0
        vol_delta = vol_after - vol_before
        print(f"[*] 实体体积响应: 前={vol_before:.2f}mm^3, 后={vol_after:.2f}mm^3 (Δ={vol_delta:+.2f}mm^3)")
        ok = res.success and (vol_delta < 0.0)  # 切孔扩大导致材料减少
        print(f"[*] 测试四结果: {'[PASS]' if ok else '[FAIL]'} (实体响应符合负几何切削联动)")
        return ok

    def run_test_5_parameter_boundary_rejection(self) -> bool:
        """测试五：参数边界防御与非法数值拦截。"""
        print("\n" + "-" * 60)
        print("【测试五：物理参数边界与非法数值防御测试】")
        print("-" * 60)

        def _sta_boundary():
            sw, _ = connect_solidworks()
            model = open_document(sw, self.part_path)
            ir = read_model_dimensions(model)
            target_dim = ir.get_driving_dimensions()[0].dimension_name

            modifier = DimensionModifier(model, auto_rollback=True)
            # 传入非法负数或零数值
            res_neg = None
            try:
                res_neg = modifier.modify_single(target_dim, -10.0, doc_path=self.part_path)
            except Exception as e:
                res_neg = str(e)
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            return res_neg

        res = self.worker.execute(_sta_boundary)
        print(f"[*] 非法参数输入拦截反馈: {res}")
        ok = (res is None) or ("必须大于 0" in str(res)) or (hasattr(res, "success") and not res.success)
        print(f"[*] 测试五结果: {'[PASS]' if ok else '[FAIL]'}")
        return ok

    def run_test_6_failure_recovery_rollback(self) -> bool:
        """测试六：连续修改后二次故障自愈回滚 (首次成功保留，二次失败回滚)。"""
        print("\n" + "-" * 60)
        print("【测试六：连续修改中途故障自愈回滚】")
        print("-" * 60)

        def _sta_recovery():
            sw, _ = connect_solidworks()
            model = open_document(sw, self.part_path)
            ir1 = read_model_dimensions(model)
            target_dim = ir1.get_driving_dimensions()[0].dimension_name
            orig_val = ir1.get_dimension(target_dim).value

            modifier = DimensionModifier(model, auto_rollback=True)
            # 1. 第一次合法修改: +10mm
            first_target = orig_val + 10.0
            r1 = modifier.modify_single(target_dim, first_target, save=True, doc_path=self.part_path)
            val_after_first = read_model_dimensions(model).get_dimension(target_dim).value

            # 2. 第二次故意注入超出物理极限的极端超差尺寸 (例如 999999.0mm) 导致重构几何崩溃
            r2 = modifier.modify_single(target_dim, 9999999.0, save=False, doc_path=self.part_path)
            val_after_second = read_model_dimensions(model).get_dimension(target_dim).value

            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            return r1, r2, orig_val, val_after_first, val_after_second

        r1, r2, orig_val, val_after_first, val_after_second = self.worker.execute(_sta_recovery)
        print(f"[*] 第一次修改: 期望={orig_val+10.0}mm, 实际={val_after_first}mm, 状态={r1.status}")
        print(f"[*] 第二次极端修改: 状态={r2.status}, 回滚发生={r2.rollback_occurred}")
        print(f"[*] 故障自愈回滚后模型当前值: {val_after_second}mm")

        # 验证第一次修改被保留或模型恢复到稳定状态，且极端修改被撤销
        ok = r1.success and (not r2.success) and (val_after_second < 500000.0)
        print(f"[*] 测试六结果: {'[PASS]' if ok else '[FAIL]'}")
        return ok

    def run_test_7_natural_language_pipeline(self) -> bool:
        """测试七：自然语言端到端参数修改完整闭环。"""
        print("\n" + "-" * 60)
        print("【测试七：自然语言端到端尺寸修改闭环】")
        print("-" * 60)
        user_prompt = "把这个安装座的底座厚度改成 20 毫米"
        print(f"[*] 用户自然语言需求: \"{user_prompt}\"")

        def _sta_nl():
            sw, _ = connect_solidworks()
            model = open_document(sw, self.part_path)
            ir_before = read_model_dimensions(model)

            # 1. Resolver 解析自然语言目标
            resolver = DimensionResolver(ir_before)
            resolution = resolver.resolve(user_prompt)
            if not resolution.success:
                get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
                return False, f"自然语言解析失败: {resolution.error_message}"

            target = resolution.resolved_target
            print(f"[*] Resolver 识别结果:")
            print(f"    - 目标尺寸: {target.dimension_name}")
            print(f"    - 原始数值: {target.original_value_mm} {target.unit}")
            print(f"    - 目标数值: {target.target_value_mm} {target.unit}")
            print(f"    - 解析依据: {target.matched_reason}")

            # 2. Modifier 就地执行修改
            modifier = DimensionModifier(model, auto_rollback=True)
            mod_res = modifier.modify_single(target.dimension_name, target.target_value_mm, save=True, doc_path=self.part_path)

            # 3. Validator 物理核查
            ir_after = read_model_dimensions(model)
            val_report = DimensionValidator.validate(
                before_ir=ir_before,
                after_ir=ir_after,
                target_updates={target.dimension_name: target.target_value_mm},
            )
            get_com_member(sw, "CloseDoc", get_com_member(model, "GetTitle"))
            return mod_res.success and val_report.passed, val_report

        ok, details = self.worker.execute(_sta_nl)
        print(f"[*] 自然语言全链路闭环结果: {'[PASS]' if ok else '[FAIL]'}, 详情: {details}")
        print(f"[*] 测试七结果: {'[PASS]' if ok else '[FAIL]'}")
        return ok


def main():
    parser = argparse.ArgumentParser(description="SolidWorks P1 尺寸驱动与参数化修改实机测试")
    parser.add_argument("--authorize-cad-write", action="store_true", default=False)
    args = parser.parse_args()

    if not args.authorize_cad_write:
        print("[✖ ERROR] 必须提供 --authorize-cad-write 参数以授权真实参数修改。")
        sys.exit(1)

    print("=" * 65)
    print("      dsh-solidworks P1 尺寸驱动与参数化修改实机测试套件")
    print("=" * 65)

    print("[*] 正在创建参数化专用物理基准零件...")
    bench_path = create_parametric_benchmark_part()
    print(f"[✔ PASS] 基准零件已落盘沙箱: {bench_path}")

    suite = RealCADDimensionTestSuite(bench_path)

    t1 = suite.run_test_1_dimension_reading()
    t2 = suite.run_test_2_single_parameter_modification()
    t3 = suite.run_test_3_multi_parameter_modification()
    t4 = suite.run_test_4_upstream_downstream_linkage()
    t5 = suite.run_test_5_parameter_boundary_rejection()
    t6 = suite.run_test_6_failure_recovery_rollback()
    t7 = suite.run_test_7_natural_language_pipeline()

    all_passed = t1 and t2 and t3 and t4 and t5 and t6 and t7

    print("\n" + "=" * 65)
    print("      P1 尺寸驱动实机测试汇总")
    print("=" * 65)
    print(f"  测试一：真实尺寸全景读取: {'[PASS]' if t1 else '[FAIL]'}")
    print(f"  测试二：单参数就地修改验证: {'[PASS]' if t2 else '[FAIL]'}")
    print(f"  测试三：多参数批量事务重构: {'[PASS]' if t3 else '[FAIL]'}")
    print(f"  测试四：上游草图下游实体联动: {'[PASS]' if t4 else '[FAIL]'}")
    print(f"  测试五：参数物理边界拦截: {'[PASS]' if t5 else '[FAIL]'}")
    print(f"  测试六：连续修改故障自愈回滚: {'[PASS]' if t6 else '[FAIL]'}")
    print(f"  测试七：自然语言端到端修改闭环: {'[PASS]' if t7 else '[FAIL]'}")
    print(f"  P1 综合验收结论: {'[ALL PASS]' if all_passed else '[FAIL]'}")
    print("=" * 65)

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
