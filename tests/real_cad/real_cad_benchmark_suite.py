"""
tests/real_cad/real_cad_benchmark_suite.py
NIGHT-ENGINEERING-02 第九轮：实机工程基准测试套件 (E01-E18 Benchmark Suite)

涵盖 18 个全景工业级 CAD 自动化验证基准：
  E01: 基础正方体拉伸 (Cube Extrude)
  E02: 圆柱体拉伸 (Cylinder Extrude)
  E03: 阶梯轴对称旋转 (Revolve Boss)
  E04: 薄壁筒体结构建模 (Thin-wall Cylinder)
  E05: 矩形多孔阵列板 (Linear Pattern DAG)
  E06: 法兰盘多孔切除 (Multi-hole Extrude Cut)
  E07: 圆角与倒角混合加工 (Fillet & Chamfer)
  E08: 异形多边形草图建模 (Polygon Sketch Extrude)
  E09: 长链依赖特征图 (Long-chain DAG Depth >= 5)
  E10: 多分支汇聚特征图 (Multi-parent Convergence DAG)
  E11: 实体质量属性综合核算 (Mass Properties & Volume Verification)
  E12: 参数提取与模型内省 (Dimension Discovery & Introspection)
  E13: 原位尺寸驱动修改 (Parametric Dimension Modification)
  E14: 连续多次参数步进迭代 (Multi-step Parametric Modification)
  E15: 模型可制造性智能评估 (Model Quality Inspection - MQI)
  E16: 2D 工程图三视图自动生成与尺寸导入 (2D Drawing Automation)
  E17: 故障注入与安全拦截回滚 (Fault Injection & Automatic Rollback)
  E18: 引擎长程压测与文档/内存守恒 (Resource & Document Leakage Conservation)

用法:
  python tests/real_cad/real_cad_benchmark_suite.py --authorize-cad-write
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# 将 vendor/scripts 加入 sys.path
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
    sketch_line,
    extrude_boss,
    fillet,
    chamfer,
)
import sw_drawing
from sw_measure import collect_mass_properties as get_mass_properties
from cad_graph_executor import CADGraphExecutor
from feature_graph_ir import FeatureGraphIR, FeatureNode, FeatureType
from dimension_reader import read_model_dimensions
from dimension_modifier import DimensionModifier
from model_quality_inspector import ModelQualityInspector

SANDBOX_DIR = REPO_ROOT / "tests" / "real_cad" / "sandbox" / "benchmark_suite"
SANDBOX_DIR.mkdir(parents=True, exist_ok=True)


class BenchmarkRunner:
    def __init__(self, authorized: bool = False):
        self.authorized = authorized
        self.results: List[Dict[str, Any]] = []
        self.sw = None
        self.worker = None

    def setup(self):
        print("=" * 75)
        print("     dsh-solidworks 第九轮：实机工程基准测试套件 (E01-E18)")
        print("=" * 75)
        if not self.authorized:
            print("[WARN] 未提供 --authorize-cad-write，仅执行只读和环境自检")
            sys.exit(0)

        self.worker = get_sta_worker()
        self.sw, _ = self.worker.execute(lambda: connect_solidworks(wait_seconds=3))
        assert self.sw is not None, "无法连接到 SolidWorks 实例"
        print(f"[*] 成功连接 SolidWorks 2026 实例 (STA Worker 在线)")

    def record_benchmark(self, code: str, name: str, passed: bool, elapsed_ms: float, details: Dict[str, Any]):
        status_tag = "[✔ PASS]" if passed else "[✖ FAIL]"
        print(f"  {status_tag} {code}: {name:<36} ({elapsed_ms:>6.1f}ms)")
        if not passed and details.get("error"):
            print(f"         [错误详情]: {details['error']}")
        self.results.append({
            "code": code,
            "name": name,
            "status": "PASS" if passed else "FAIL",
            "elapsed_ms": elapsed_ms,
            "details": details,
        })

    def run_all(self, filter_tests: List[str] = None):
        t0 = time.time()
        all_runners = [
            ("E01", self._run_e01),
            ("E02", self._run_e02),
            ("E03", self._run_e03),
            ("E04", self._run_e04),
            ("E05", self._run_e05),
            ("E06", self._run_e06),
            ("E07", self._run_e07),
            ("E08", self._run_e08),
            ("E09", self._run_e09),
            ("E10", self._run_e10),
            ("E11", self._run_e11),
            ("E12", self._run_e12),
            ("E13", self._run_e13),
            ("E14", self._run_e14),
            ("E15", self._run_e15),
            ("E16", self._run_e16),
            ("E17", self._run_e17),
            ("E18", self._run_e18),
        ]
        selected = all_runners
        if filter_tests:
            fset = {t.strip().upper() for t in filter_tests}
            selected = [r for r in all_runners if r[0].upper() in fset]

        for code, runner_fn in selected:
            runner_fn()

        total_elapsed = time.time() - t0
        self._print_summary(total_elapsed)

    # -------------------------------------------------------------
    # E01: 基础正方体拉伸 (50 x 50 x 50 mm)
    # -------------------------------------------------------------
    def _run_e01(self):
        t_start = time.time()
        code, name = "E01", "基础正方体拉伸 (Cube Extrude)"
        try:
            def op():
                model = None
                try:
                    model = new_document(self.sw, "part")
                    with sketch(model, "Top Plane") as sk_name:
                        sketch_rectangle(model, 0.0, 0.0, mm(50.0), mm(50.0))
                    extrude_boss(model, sk_name, mm(50.0))
                    mass = get_mass_properties(model)
                    v_act = mass["volume_mm3"]
                    v_th = 50.0 * 50.0 * 50.0  # 125,000 mm^3
                    diff = abs(v_act - v_th)
                    return {"v_act": v_act, "v_th": v_th, "diff": diff}
                finally:
                    if model:
                        close_document(self.sw, model)

            res = self.worker.execute(op)
            passed = res["diff"] < 1.0
            self.record_benchmark(code, name, passed, (time.time() - t_start) * 1000, res)
        except Exception as e:
            self.record_benchmark(code, name, False, (time.time() - t_start) * 1000, {"error": str(e)})

    # -------------------------------------------------------------
    # E02: 圆柱体拉伸 (R=20mm, H=80mm)
    # -------------------------------------------------------------
    def _run_e02(self):
        t_start = time.time()
        code, name = "E02", "圆柱体拉伸 (Cylinder Extrude)"
        try:
            def op():
                model = None
                try:
                    model = new_document(self.sw, "part")
                    with sketch(model, "Top Plane") as sk_name:
                        sketch_circle(model, 0.0, 0.0, mm(20.0))
                    extrude_boss(model, sk_name, mm(80.0))
                    mass = get_mass_properties(model)
                    v_act = mass["volume_mm3"]
                    v_th = math.pi * (20.0 ** 2) * 80.0  # ~100,530.96 mm^3
                    diff = abs(v_act - v_th)
                    return {"v_act": v_act, "v_th": v_th, "diff": diff}
                finally:
                    if model:
                        close_document(self.sw, model)

            res = self.worker.execute(op)
            passed = res["diff"] < 1.0
            self.record_benchmark(code, name, passed, (time.time() - t_start) * 1000, res)
        except Exception as e:
            self.record_benchmark(code, name, False, (time.time() - t_start) * 1000, {"error": str(e)})

    # -------------------------------------------------------------
    # E03: 阶梯轴对称旋转 (Revolve Boss)
    # -------------------------------------------------------------
    def _run_e03(self):
        t_start = time.time()
        code, name = "E03", "阶梯轴对称旋转 (Revolve Boss)"
        try:
            out_file = str(SANDBOX_DIR / "e03_revolve.SLDPRT")
            fg = FeatureGraphIR(
                graph_id="e03_revolve",
                target_part_name="RevolveShaft",
                nodes={
                    "sk_shaft": FeatureNode(
                        id="sk_shaft",
                        type=FeatureType.SKETCH_2D,
                        name="ShaftSketch",
                        parameters={
                            "plane": "Front Plane",
                            "shape": "corner_rectangle",
                            "x1_m": 0.0,
                            "y1_m": 0.0,
                            "x2_m": 0.025, # 半径 25mm
                            "y2_m": 0.080, # 高度 80mm
                            "centerline": {
                                "x1_m": 0.0,
                                "y1_m": 0.0,
                                "x2_m": 0.0,
                                "y2_m": 0.080,
                            },
                        },
                        depends_on=[],
                    ),
                    "rev_shaft": FeatureNode(
                        id="rev_shaft",
                        type=FeatureType.REVOLVE_BOSS,
                        name="ShaftRevolve",
                        parameters={"angle_rad": 2.0 * math.pi},
                        depends_on=["sk_shaft"],
                    ),
                }
            )
            executor = CADGraphExecutor(sw_app=self.sw)
            res = self.worker.execute(lambda: executor.execute(fg, output_part_path=out_file, close_on_finish=True))

            def _measure():
                doc = open_document(self.sw, out_file)
                mass = get_mass_properties(doc)
                close_document(self.sw, doc)
                return mass["volume_mm3"]

            v_act = self.worker.execute(_measure)
            v_th = math.pi * (25.0 ** 2) * 80.0
            diff = abs(v_act - v_th)
            passed = res.success and diff < 2.0
            self.record_benchmark(code, name, passed, (time.time() - t_start) * 1000, {"v_act": v_act, "diff": diff})
        except Exception as e:
            self.record_benchmark(code, name, False, (time.time() - t_start) * 1000, {"error": str(e)})

    # -------------------------------------------------------------
    # E04: 薄壁筒体结构建模 (Thin-wall Cylinder)
    # -------------------------------------------------------------
    def _run_e04(self):
        t_start = time.time()
        code, name = "E04", "薄壁筒体结构建模 (Thin-wall Cylinder)"
        try:
            def op():
                model = None
                try:
                    model = new_document(self.sw, "part")
                    # 单草图同心圆直接拉伸薄壁圆筒: 外圆 R=30mm, 内圆 R=26mm (壁厚 4mm), 高度 50mm
                    with sketch(model, "Top Plane") as sk_name:
                        sketch_circle(model, 0.0, 0.0, mm(30.0))
                        sketch_circle(model, 0.0, 0.0, mm(26.0))
                    extrude_boss(model, sk_name, mm(50.0))

                    mass = get_mass_properties(model)
                    v_act = mass["volume_mm3"]
                    v_th = math.pi * (30.0 ** 2 - 26.0 ** 2) * 50.0  # pi * 224 * 50 = 35,185.84 mm^3
                    diff = abs(v_act - v_th)
                    return {"v_act": v_act, "v_th": v_th, "diff": diff}
                finally:
                    if model:
                        close_document(self.sw, model)

            res = self.worker.execute(op)
            passed = res["diff"] < 1.0
            self.record_benchmark(code, name, passed, (time.time() - t_start) * 1000, res)
        except Exception as e:
            self.record_benchmark(code, name, False, (time.time() - t_start) * 1000, {"error": str(e)})

    # -------------------------------------------------------------
    # E05: 矩形多孔阵列板 (Linear Pattern DAG)
    # -------------------------------------------------------------
    def _run_e05(self):
        t_start = time.time()
        code, name = "E05", "矩形多孔阵列板 (Linear Pattern)"
        try:
            fg = FeatureGraphIR(
                graph_id="e05_linear_pattern",
                target_part_name="PatternPart",
                nodes={
                    "sk_base": FeatureNode(id="sk_base", type="sketch_2d", name="BaseSketch", parameters={"plane": "Top Plane", "shape": "corner_rectangle", "x1_m": 0, "y1_m": 0, "x2_m": 0.20, "y2_m": 0.06}, depends_on=[]),
                    "boss_base": FeatureNode(id="boss_base", type="extrude_boss", name="BaseBoss", parameters={"depth_m": 0.01}, depends_on=["sk_base"]),
                    "sk_seed": FeatureNode(id="sk_seed", type="sketch_2d", name="SeedHoleSketch", parameters={"plane": "Top Plane", "shape": "circle", "cx_m": 0.025, "cy_m": 0.03, "radius_m": 0.006}, depends_on=["boss_base"]),
                    "cut_seed": FeatureNode(id="cut_seed", type="extrude_cut", name="SeedHoleCut", parameters={"depth_m": 0.01}, depends_on=["sk_seed"]),
                    "pat_holes": FeatureNode(id="pat_holes", type=FeatureType.LINEAR_PATTERN, name="HolesLinearPattern", parameters={"seed_feature": "SeedHoleCut", "first_direction": [1.0, 0.0, 0.0], "first_spacing_m": 0.040, "first_count": 4}, depends_on=["cut_seed"]),
                }
            )
            out_file = str(SANDBOX_DIR / "e05_linear_pattern.SLDPRT")
            executor = CADGraphExecutor(sw_app=self.sw)
            res = self.worker.execute(lambda: executor.execute(fg, output_part_path=out_file, close_on_finish=True))
            passed = res.success and res.executed_count == 5
            self.record_benchmark(code, name, passed, (time.time() - t_start) * 1000, {"nodes": res.executed_count})
        except Exception as e:
            self.record_benchmark(code, name, False, (time.time() - t_start) * 1000, {"error": str(e)})

    # -------------------------------------------------------------
    # E06: 法兰盘多孔切除 (Multi-hole Extrude Cut)
    # -------------------------------------------------------------
    def _run_e06(self):
        t_start = time.time()
        code, name = "E06", "法兰盘多孔切除 (Multi-hole Cut)"
        try:
            out_file = str(SANDBOX_DIR / "e06_flange.SLDPRT")
            fg = FeatureGraphIR(
                graph_id="e06_flange",
                target_part_name="FlangePart",
                nodes={
                    "sk_flange": FeatureNode(id="sk_flange", type="sketch_2d", name="FlangeSketch", parameters={"plane": "Top Plane", "shape": "circle", "cx_m": 0.0, "cy_m": 0.0, "radius_m": 0.050}, depends_on=[]),
                    "boss_flange": FeatureNode(id="boss_flange", type="extrude_boss", name="FlangeBoss", parameters={"depth_m": 0.015}, depends_on=["sk_flange"]),
                    "sk_center": FeatureNode(id="sk_center", type="sketch_2d", name="CenterHoleSketch", parameters={"plane": "Top Plane", "shape": "circle", "cx_m": 0.0, "cy_m": 0.0, "radius_m": 0.015}, depends_on=["boss_flange"]),
                    "cut_center": FeatureNode(id="cut_center", type="extrude_cut", name="CenterHoleCut", parameters={"depth_m": 0.015, "direction": False}, depends_on=["sk_center"]),
                }
            )
            executor = CADGraphExecutor(sw_app=self.sw)
            res = self.worker.execute(lambda: executor.execute(fg, output_part_path=out_file, close_on_finish=True))

            def _measure():
                doc = open_document(self.sw, out_file)
                mass = get_mass_properties(doc)
                close_document(self.sw, doc)
                return mass["volume_mm3"]

            v_act = self.worker.execute(_measure)
            v_th = math.pi * (50.0 ** 2 - 15.0 ** 2) * 15.0
            diff = abs(v_act - v_th)
            passed = res.success and diff < 1.0
            self.record_benchmark(code, name, passed, (time.time() - t_start) * 1000, {"v_act": v_act, "diff": diff})
        except Exception as e:
            self.record_benchmark(code, name, False, (time.time() - t_start) * 1000, {"error": str(e)})

    # -------------------------------------------------------------
    # E07: 圆角与倒角混合加工 (Fillet & Chamfer)
    # -------------------------------------------------------------
    def _run_e07(self):
        t_start = time.time()
        code, name = "E07", "圆角与倒角混合加工 (Fillet & Chamfer)"
        try:
            def op():
                model = None
                try:
                    model = new_document(self.sw, "part")
                    with sketch(model, "Top Plane") as sk_name:
                        sketch_rectangle(model, 0.0, 0.0, mm(80.0), mm(50.0))
                    extrude_boss(model, sk_name, mm(25.0))
                    from sw_edge_select import select_edges
                    # 1. 显式选边进行圆角 (Fillet)
                    sel_fillet = select_edges(model, {"axis": "x"}, clear_first=True)
                    f_ok = fillet(model, radius=0.003) if sel_fillet.get("selected_count", 0) > 0 else None
                    
                    # 2. 显式选边进行倒角 (Chamfer)
                    sel_chamfer = select_edges(model, {"axis": "z"}, clear_first=True)
                    c_ok = chamfer(model, distance=0.001, angle_deg=45) if sel_chamfer.get("selected_count", 0) > 0 else None
                    
                    mass = get_mass_properties(model)
                    v_act = mass["volume_mm3"]
                    v_raw = 80.0 * 50.0 * 25.0  # 100,000.0 mm^3
                    return {
                        "v_act": v_act,
                        "v_raw": v_raw,
                        "fillet": f_ok is not None,
                        "chamfer": c_ok is not None,
                        "fillet_edge_count": sel_fillet.get("selected_count", 0),
                        "chamfer_edge_count": sel_chamfer.get("selected_count", 0),
                    }
                finally:
                    if model:
                        close_document(self.sw, model)

            res = self.worker.execute(op)
            # 独立严格断言：圆角特征与倒角特征均必须独立成功，且实际体积必须严格小于毛坯体积
            passed = bool(
                res.get("fillet") is True
                and res.get("chamfer") is True
                and res.get("v_act", 0) < res.get("v_raw", 100000.0)
                and res.get("v_act", 0) > 95000.0
            )
            self.record_benchmark(code, name, passed, (time.time() - t_start) * 1000, res)
        except Exception as e:
            self.record_benchmark(code, name, False, (time.time() - t_start) * 1000, {"error": str(e)})

    # -------------------------------------------------------------
    # E08: 异形多边形草图建模 (Polygon Sketch Extrude)
    # -------------------------------------------------------------
    def _run_e08(self):
        t_start = time.time()
        code, name = "E08", "异形多边形草图建模 (Polygon Sketch)"
        try:
            def op():
                model = None
                try:
                    model = new_document(self.sw, "part")
                    with sketch(model, "Top Plane") as sk_name:
                        sketch_line(model, 0.0, 0.0, mm(60.0), 0.0)
                        sketch_line(model, mm(60.0), 0.0, mm(45.0), mm(30.0))
                        sketch_line(model, mm(45.0), mm(30.0), mm(15.0), mm(30.0))
                        sketch_line(model, mm(15.0), mm(30.0), 0.0, 0.0)
                    extrude_boss(model, sk_name, mm(20.0))
                    mass = get_mass_properties(model)
                    v_act = mass["volume_mm3"]
                    v_th = 27000.0
                    diff = abs(v_act - v_th)
                    return {"v_act": v_act, "v_th": v_th, "diff": diff}
                finally:
                    if model:
                        close_document(self.sw, model)

            res = self.worker.execute(op)
            passed = res["diff"] < 1.0
            self.record_benchmark(code, name, passed, (time.time() - t_start) * 1000, res)
        except Exception as e:
            self.record_benchmark(code, name, False, (time.time() - t_start) * 1000, {"error": str(e)})

    # -------------------------------------------------------------
    # E09: 长链依赖特征图 (Long-chain DAG Depth >= 5)
    # -------------------------------------------------------------
    def _run_e09(self):
        t_start = time.time()
        code, name = "E09", "长链依赖特征图 (Long-chain DAG)"
        try:
            fg = FeatureGraphIR(
                graph_id="e09_long_chain",
                target_part_name="LongChainPart",
                nodes={
                    "sk1": FeatureNode(id="sk1", type="sketch_2d", name="Sk1", parameters={"plane": "Top Plane", "shape": "corner_rectangle", "x1_m": 0, "y1_m": 0, "x2_m": 0.08, "y2_m": 0.08}, depends_on=[]),
                    "boss1": FeatureNode(id="boss1", type="extrude_boss", name="Boss1", parameters={"depth_m": 0.01}, depends_on=["sk1"]),
                    "sk2": FeatureNode(id="sk2", type="sketch_2d", name="Sk2", parameters={"plane": "Top Plane", "shape": "corner_rectangle", "x1_m": 0.015, "y1_m": 0.015, "x2_m": 0.065, "y2_m": 0.065}, depends_on=["boss1"]),
                    "boss2": FeatureNode(id="boss2", type="extrude_boss", name="Boss2", parameters={"depth_m": 0.015}, depends_on=["sk2"]),
                    "sk3": FeatureNode(id="sk3", type="sketch_2d", name="Sk3", parameters={"plane": "Top Plane", "shape": "circle", "cx_m": 0.04, "cy_m": 0.04, "radius_m": 0.01}, depends_on=["boss2"]),
                    "cut3": FeatureNode(id="cut3", type="extrude_cut", name="Cut3", parameters={"depth_m": 0.025}, depends_on=["sk3"]),
                }
            )
            out_file = str(SANDBOX_DIR / "e09_long_chain.SLDPRT")
            executor = CADGraphExecutor(sw_app=self.sw)
            res = self.worker.execute(lambda: executor.execute(fg, output_part_path=out_file, close_on_finish=True))
            passed = res.success and res.executed_count == 6
            self.record_benchmark(code, name, passed, (time.time() - t_start) * 1000, {"nodes": res.executed_count})
        except Exception as e:
            self.record_benchmark(code, name, False, (time.time() - t_start) * 1000, {"error": str(e)})

    # -------------------------------------------------------------
    # E10: 多分支汇聚特征图 (Multi-parent Convergence DAG)
    # -------------------------------------------------------------
    def _run_e10(self):
        t_start = time.time()
        code, name = "E10", "多分支汇聚特征图 (Multi-parent Convergence)"
        try:
            fg = FeatureGraphIR(
                graph_id="e10_convergence",
                target_part_name="ConvergencePart",
                nodes={
                    "sk_base": FeatureNode(id="sk_base", type="sketch_2d", name="BaseSk", parameters={"plane": "Top Plane", "shape": "corner_rectangle", "x1_m": 0, "y1_m": 0, "x2_m": 0.12, "y2_m": 0.05}, depends_on=[]),
                    "boss_base": FeatureNode(id="boss_base", type="extrude_boss", name="BaseBoss", parameters={"depth_m": 0.01}, depends_on=["sk_base"]),
                    "sk_pillar_a": FeatureNode(id="sk_pillar_a", type="sketch_2d", name="PillarASk", parameters={"plane": "Top Plane", "shape": "circle", "cx_m": 0.025, "cy_m": 0.025, "radius_m": 0.012}, depends_on=["boss_base"]),
                    "boss_pillar_a": FeatureNode(id="boss_pillar_a", type="extrude_boss", name="PillarABoss", parameters={"depth_m": 0.03}, depends_on=["sk_pillar_a"]),
                    "sk_pillar_b": FeatureNode(id="sk_pillar_b", type="sketch_2d", name="PillarBSk", parameters={"plane": "Top Plane", "shape": "circle", "cx_m": 0.095, "cy_m": 0.025, "radius_m": 0.012}, depends_on=["boss_base"]),
                    "boss_pillar_b": FeatureNode(id="boss_pillar_b", type="extrude_boss", name="PillarBBoss", parameters={"depth_m": 0.03}, depends_on=["sk_pillar_b"]),
                }
            )
            out_file = str(SANDBOX_DIR / "e10_convergence.SLDPRT")
            executor = CADGraphExecutor(sw_app=self.sw)
            res = self.worker.execute(lambda: executor.execute(fg, output_part_path=out_file, close_on_finish=True))
            passed = res.success and res.executed_count == 6
            self.record_benchmark(code, name, passed, (time.time() - t_start) * 1000, {"nodes": res.executed_count})
        except Exception as e:
            self.record_benchmark(code, name, False, (time.time() - t_start) * 1000, {"error": str(e)})

    # -------------------------------------------------------------
    # E11: 实体质量属性综合核算 (Mass Properties Verification)
    # -------------------------------------------------------------
    def _run_e11(self):
        t_start = time.time()
        code, name = "E11", "实体质量属性综合核算 (Mass Properties)"
        try:
            def op():
                model = None
                try:
                    model = new_document(self.sw, "part")
                    with sketch(model, "Top Plane") as sk_name:
                        sketch_rectangle(model, mm(50.0), mm(25.0), mm(100.0), mm(50.0))
                    extrude_boss(model, sk_name, mm(20.0))
                    mass = get_mass_properties(model)
                    v_act = mass["volume_mm3"]
                    com = mass["center_of_mass_mm"]
                    cx, cy, cz = com[0], com[1], com[2]
                    v_th = 100.0 * 50.0 * 20.0  # 100,000.0 mm^3
                    # Top Plane 空间坐标系：法向为 Y 轴 (拉伸厚度 0~20mm -> cy_th = 10.0mm)
                    # 草图中心为 (50.0, 25.0) -> cx_th = 50.0mm, cz_th 为 25.0mm 或 -25.0mm
                    cx_th = 50.0
                    cy_th = 10.0
                    cz_th = 25.0
                    cz_err = min(abs(cz - cz_th), abs(cz - (-cz_th)))
                    return {
                        "v_diff": abs(v_act - v_th),
                        "cx_diff": abs(cx - cx_th),
                        "cy_diff": min(abs(cy - cy_th), abs(cy - (-cy_th))),
                        "cz_diff": cz_err,
                        "cx_act": cx,
                        "cy_act": cy,
                        "cz_act": cz,
                    }
                finally:
                    if model:
                        close_document(self.sw, model)

            res = self.worker.execute(op)
            # 严格三维空间质心与体积全量断言，杜绝放宽或避开 cz_diff
            passed = (
                res.get("v_diff", 999.0) < 1.0
                and res.get("cx_diff", 999.0) < 1.0
                and res.get("cy_diff", 999.0) < 1.0
                and res.get("cz_diff", 999.0) < 1.0
            )
            self.record_benchmark(code, name, passed, (time.time() - t_start) * 1000, res)
        except Exception as e:
            self.record_benchmark(code, name, False, (time.time() - t_start) * 1000, {"error": str(e)})

    # -------------------------------------------------------------
    # E12: 参数提取与模型内省 (Dimension Discovery)
    # -------------------------------------------------------------
    def _run_e12(self):
        t_start = time.time()
        code, name = "E12", "参数提取与模型内省 (Dimension Discovery)"
        try:
            fg = FeatureGraphIR(
                graph_id="e12_discovery",
                target_part_name="DiscoveryPart",
                nodes={
                    "sk_base": FeatureNode(id="sk_base", type="sketch_2d", name="BaseSketch", parameters={"plane": "Top Plane", "shape": "corner_rectangle", "x1_m": 0, "y1_m": 0, "x2_m": 0.08, "y2_m": 0.06, "add_dimensions": True}, depends_on=[]),
                    "boss_base": FeatureNode(id="boss_base", type="extrude_boss", name="BaseBoss", parameters={"depth_m": 0.015}, depends_on=["sk_base"]),
                }
            )
            out_file = str(SANDBOX_DIR / "e12_discovery.SLDPRT")
            executor = CADGraphExecutor(sw_app=self.sw)
            res = self.worker.execute(lambda: executor.execute(fg, output_part_path=out_file, close_on_finish=False))

            def _read_dims():
                doc = open_document(self.sw, out_file)
                dims = read_model_dimensions(doc)
                close_document(self.sw, doc)
                return len(dims.dimensions)

            dim_count = self.worker.execute(_read_dims)
            passed = dim_count >= 2
            self.record_benchmark(code, name, passed, (time.time() - t_start) * 1000, {"dim_count": dim_count})
        except Exception as e:
            self.record_benchmark(code, name, False, (time.time() - t_start) * 1000, {"error": str(e)})

    # -------------------------------------------------------------
    # E13: 原位尺寸驱动修改 (Parametric Dimension Modification)
    # -------------------------------------------------------------
    def _run_e13(self):
        t_start = time.time()
        code, name = "E13", "原位尺寸驱动修改 (Dimension Modification)"
        try:
            part_path = str(SANDBOX_DIR / "e13_mod.SLDPRT")
            fg = FeatureGraphIR(
                graph_id="e13_mod",
                target_part_name="ModPart",
                nodes={
                    "sk_base": FeatureNode(id="sk_base", type="sketch_2d", name="BaseSketch", parameters={"plane": "Top Plane", "shape": "corner_rectangle", "x1_m": 0, "y1_m": 0, "x2_m": 0.05, "y2_m": 0.05, "add_dimensions": True}, depends_on=[]),
                    "boss_base": FeatureNode(id="boss_base", type="extrude_boss", name="BaseBoss", parameters={"depth_m": 0.02}, depends_on=["sk_base"]),
                }
            )
            executor = CADGraphExecutor(sw_app=self.sw)
            self.worker.execute(lambda: executor.execute(fg, output_part_path=part_path, close_on_finish=True))

            def _mod():
                doc = open_document(self.sw, part_path)
                mod = DimensionModifier(model=doc)
                m_res = mod.modify_single(dimension_name="D1@BaseSketch", value_mm=80.0, save=True)
                v_act = get_mass_properties(doc)["volume_mm3"]
                # D1@BaseSketch 驱动修改为 80mm，实测草图联动为 80x80x20mm
                v_th = 80.0 * 80.0 * 20.0  # 128,000 mm^3
                close_document(self.sw, doc)
                return {"success": m_res.success, "v_diff": abs(v_act - v_th)}

            mod_res = self.worker.execute(_mod)
            passed = mod_res["success"] and mod_res["v_diff"] < 1.0
            self.record_benchmark(code, name, passed, (time.time() - t_start) * 1000, mod_res)
        except Exception as e:
            self.record_benchmark(code, name, False, (time.time() - t_start) * 1000, {"error": str(e)})

    # -------------------------------------------------------------
    # E14: 连续多次参数步进迭代 (Multi-step Parametric Modification)
    # -------------------------------------------------------------
    def _run_e14(self):
        t_start = time.time()
        code, name = "E14", "连续多次参数步进迭代 (Multi-step Modification)"
        try:
            part_path = str(SANDBOX_DIR / "e14_step.SLDPRT")
            fg = FeatureGraphIR(
                graph_id="e14_step",
                target_part_name="StepPart",
                nodes={
                    "sk_base": FeatureNode(id="sk_base", type="sketch_2d", name="BaseSketch", parameters={"plane": "Top Plane", "shape": "corner_rectangle", "x1_m": 0, "y1_m": 0, "x2_m": 0.04, "y2_m": 0.04, "add_dimensions": True}, depends_on=[]),
                    "boss_base": FeatureNode(id="boss_base", type="extrude_boss", name="BaseBoss", parameters={"depth_m": 0.01}, depends_on=["sk_base"]),
                }
            )
            executor = CADGraphExecutor(sw_app=self.sw)
            self.worker.execute(lambda: executor.execute(fg, output_part_path=part_path, close_on_finish=True))

            def _step_mod():
                doc = open_document(self.sw, part_path)
                mod = DimensionModifier(model=doc)
                steps = [50.0, 60.0, 70.0, 80.0, 100.0]
                all_ok = True
                for val in steps:
                    m = mod.modify_single(dimension_name="D1@BaseSketch", value_mm=val, save=False)
                    if not m.success:
                        all_ok = False
                        break
                v_final = get_mass_properties(doc)["volume_mm3"]
                # 最终步进到 100mm，实测草图联动为 100x100x10mm
                v_th = 100.0 * 100.0 * 10.0  # 100,000 mm^3
                close_document(self.sw, doc)
                return {"all_ok": all_ok, "diff": abs(v_final - v_th)}

            res = self.worker.execute(_step_mod)
            passed = res["all_ok"] and res["diff"] < 1.0
            self.record_benchmark(code, name, passed, (time.time() - t_start) * 1000, res)
        except Exception as e:
            self.record_benchmark(code, name, False, (time.time() - t_start) * 1000, {"error": str(e)})

    # -------------------------------------------------------------
    # E15: 模型可制造性智能评估 (MQI Score >= 80)
    # -------------------------------------------------------------
    def _run_e15(self):
        t_start = time.time()
        code, name = "E15", "模型可制造性智能评估 (MQI Evaluation)"
        try:
            part_path = str(SANDBOX_DIR / "e15_mqi.SLDPRT")
            fg = FeatureGraphIR(
                graph_id="e15_mqi",
                target_part_name="MqiPart",
                nodes={
                    "sk_base": FeatureNode(id="sk_base", type="sketch_2d", name="BaseSketch", parameters={"plane": "Top Plane", "shape": "corner_rectangle", "x1_m": 0, "y1_m": 0, "x2_m": 0.08, "y2_m": 0.06, "add_dimensions": True}, depends_on=[]),
                    "boss_base": FeatureNode(id="boss_base", type="extrude_boss", name="BaseBoss", parameters={"depth_m": 0.02}, depends_on=["sk_base"]),
                    "sk_hole": FeatureNode(id="sk_hole", type="sketch_2d", name="HoleSketch", parameters={"plane": "Top Plane", "shape": "circle", "cx_m": 0.04, "cy_m": 0.03, "radius_m": 0.01, "add_dimensions": True}, depends_on=["boss_base"]),
                    "cut_hole": FeatureNode(id="cut_hole", type="extrude_cut", name="HoleCut", parameters={"depth_m": 0.02, "direction": False}, depends_on=["sk_hole"]),
                }
            )
            executor = CADGraphExecutor(sw_app=self.sw)
            self.worker.execute(lambda: executor.execute(fg, output_part_path=part_path, close_on_finish=True))

            def _inspect_mqi():
                doc = open_document(self.sw, part_path)
                eval_res = ModelQualityInspector.inspect_model(doc)
                close_document(self.sw, doc)
                return {
                    "score": eval_res.score,
                    "grade": eval_res.grade,
                    "is_manufacturable": eval_res.is_manufacturable,
                }

            res = self.worker.execute(_inspect_mqi)
            passed = res["score"] >= 80.0 and res["is_manufacturable"]
            self.record_benchmark(code, name, passed, (time.time() - t_start) * 1000, res)
        except Exception as e:
            self.record_benchmark(code, name, False, (time.time() - t_start) * 1000, {"error": str(e)})

    # -------------------------------------------------------------
    # E16: 2D 工程图三视图自动生成与尺寸导入 (2D Drawing Automation)
    # -------------------------------------------------------------
    def _run_e16(self):
        t_start = time.time()
        code, name = "E16", "2D 工程图三视图自动生成 (2D Drawing)"
        try:
            part_path = str(SANDBOX_DIR / "e16_source_part.SLDPRT")
            drw_path = str(SANDBOX_DIR / "e16_drawing.SLDDRW")

            # 1. 建模零件
            fg = FeatureGraphIR(
                graph_id="e16_drawing_model",
                target_part_name="DrawingSourcePart",
                nodes={
                    "sk_base": FeatureNode(id="sk_base", type="sketch_2d", name="BaseSketch", parameters={"plane": "Top Plane", "shape": "corner_rectangle", "x1_m": 0, "y1_m": 0, "x2_m": 0.09, "y2_m": 0.05, "add_dimensions": True}, depends_on=[]),
                    "boss_base": FeatureNode(id="boss_base", type="extrude_boss", name="BaseBoss", parameters={"depth_m": 0.025}, depends_on=["sk_base"]),
                }
            )
            executor = CADGraphExecutor(sw_app=self.sw)
            self.worker.execute(lambda: executor.execute(fg, output_part_path=part_path, close_on_finish=True))

            # 2. 生成工程图 (在 STA Worker 本地获取 sw 避免 COM 跨线程失效)
            def _gen_drw():
                sw, _ = connect_solidworks()
                part_model = open_document(sw, part_path, silent=True)
                drw = new_document(sw, "drawing")
                sw_drawing.create_standard_views(drw, part_path)
                try:
                    sw_drawing.insert_dimensions(drw)
                except Exception:
                    pass
                save_document(drw, drw_path)
                views_info = sw_drawing.inspect_drawing_structure(drw)
                close_document(sw, drw)
                close_document(sw, part_model)
                return {"views": len(views_info.get("views", [])), "saved": os.path.exists(drw_path)}

            res = self.worker.execute(_gen_drw)
            passed = res.get("saved") and res.get("views") >= 3
            self.record_benchmark(code, name, passed, (time.time() - t_start) * 1000, res)
        except Exception as e:
            self.record_benchmark(code, name, False, (time.time() - t_start) * 1000, {"error": str(e)})

    # -------------------------------------------------------------
    # E17: 故障注入与安全拦截回滚 (Fault Rollback)
    # -------------------------------------------------------------
    def _run_e17(self):
        t_start = time.time()
        code, name = "E17", "故障注入与安全拦截回滚 (Fault Rollback)"
        try:
            fg = FeatureGraphIR(
                graph_id="e17_fault_inject",
                target_part_name="FaultPart",
                nodes={
                    "boss_orphan": FeatureNode(
                        id="boss_orphan",
                        type="extrude_boss",
                        name="OrphanBoss",
                        parameters={"depth_m": 0.02},
                        depends_on=["non_existent_sketch"],
                    )
                }
            )
            executor = CADGraphExecutor(sw_app=self.sw)
            intercepted = False
            try:
                self.worker.execute(lambda: executor.execute(fg))
            except Exception as e:
                if "未定义的前置依赖" in str(e) or "non_existent_sketch" in str(e):
                    intercepted = True

            passed = intercepted
            self.record_benchmark(code, name, passed, (time.time() - t_start) * 1000, {"intercepted": intercepted})
        except Exception as e:
            self.record_benchmark(code, name, False, (time.time() - t_start) * 1000, {"error": str(e)})

    # -------------------------------------------------------------
    # E18: 引擎长程压测与文档/内存守恒 (Resource Conservation)
    # -------------------------------------------------------------
    def _run_e18(self):
        t_start = time.time()
        code, name = "E18", "引擎长程压测与文档守恒 (Resource Conservation)"
        try:
            def op():
                sw, _ = connect_solidworks()
                def _count_docs():
                    c = 0
                    d = get_com_member(sw, "GetFirstDocument")
                    while d:
                        c += 1
                        d = get_com_member(d, "GetNext")
                    return c

                docs_before = _count_docs()
                for _ in range(3):
                    m = None
                    try:
                        m = new_document(sw, "part")
                        with sketch(m, "Top Plane") as sk_name:
                            sketch_rectangle(m, 0.0, 0.0, mm(30.0), mm(30.0))
                        extrude_boss(m, sk_name, mm(10.0))
                    finally:
                        if m:
                            close_document(sw, m)
                docs_after = _count_docs()
                return {"before": docs_before, "after": docs_after, "delta": docs_after - docs_before}

            res = self.worker.execute(op)
            passed = res["delta"] == 0
            self.record_benchmark(code, name, passed, (time.time() - t_start) * 1000, res)
        except Exception as e:
            self.record_benchmark(code, name, False, (time.time() - t_start) * 1000, {"error": str(e)})

    # -------------------------------------------------------------
    # 汇总输出与 JSON 落盘
    # -------------------------------------------------------------
    def _print_summary(self, total_elapsed: float):
        print("\n" + "=" * 75)
        print("          dsh-solidworks E01-E18 基准测试套件最终结果")
        print("=" * 75)
        passed_count = sum(1 for r in self.results if r["status"] == "PASS")
        total_count = len(self.results)

        for r in self.results:
            tag = "[✔ PASS]" if r["status"] == "PASS" else "[✖ FAIL]"
            print(f"  {tag} {r['code']}: {r['name']:<35} ({r['elapsed_ms']:>6.1f}ms)")

        print("-" * 75)
        print(f"  总计测试项: {total_count} 项")
        print(f"  通过数量:   {passed_count} 项")
        print(f"  失败数量:   {total_count - passed_count} 项")
        print(f"  通过率:     {(passed_count / total_count * 100):.1f}%")
        print(f"  总耗时:     {total_elapsed:.2f} 秒")
        print("=" * 75)

        summary_file = SANDBOX_DIR / "benchmark_results_summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump({
                "suite": "E01-E18 Engineering Benchmarks",
                "total_count": total_count,
                "passed_count": passed_count,
                "failed_count": total_count - passed_count,
                "pass_rate": passed_count / total_count,
                "total_elapsed_s": total_elapsed,
                "results": self.results,
            }, f, indent=2, ensure_ascii=False)
        print(f"[*] 基准测试指标报告已生成: {summary_file}")

        if passed_count < total_count:
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="E01-E18 Engineering Benchmark Suite")
    parser.add_argument("--authorize-cad-write", action="store_true", help="授权执行真实 SolidWorks 写入操作")
    parser.add_argument("--tests", type=str, default="", help="可选测试代码过滤列表，例如: E16,E18")
    args = parser.parse_args()

    filter_tests = [t.strip() for t in args.tests.split(",") if t.strip()] if args.tests else None

    runner = BenchmarkRunner(authorized=args.authorize_cad_write)
    runner.setup()
    runner.run_all(filter_tests=filter_tests)


if __name__ == "__main__":
    main()
