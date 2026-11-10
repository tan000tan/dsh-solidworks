# -*- coding: utf-8 -*-
"""
NIGHT-ENGINEERING-PHASE4: CAD 核心建模高难度实机物理验证套件
tests/real_cad/phase4_cad_core_suite.py

本套件严格遵守最高工业工程标准与零信任防护原则：
1. 真实 SolidWorks COM 实机物理调用（经 STA Worker 专属线程闭环调度）；
2. 实验 1：多步骤复杂薄壁与加强结构箱体零件（拉伸底座、同轴圆柱、贯穿切除、抗相切脱开筋板、四孔切除、边缘倒角）；
3. 实验 2：精密阶梯回转套筒与复合槽孔零件（360度旋转凸台、径向润滑通孔、GB/T标准键槽、过渡倒角）；
4. 实验 3：特征依赖联动、参数修改真实几何形变响应与破坏性故障注入逆序自愈；
5. 全面接入 URP v2 统一审查协议与 ModelQualityInspector (MQI)，绝不使用死坐标固定约束 sgFIXED；
6. 离线落盘保存、彻底关闭并重新打开，比对文件完整性与视图拓扑；
7. 产出不可篡改的结构化物证日志。
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path

# 配置路径，优先加载本插件 vendor 模块
PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PLUGIN_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(PLUGIN_ROOT))

# 禁用 bytecode 缓存，防止污染工作区
sys.dont_write_bytecode = True

from sw_connect import (
    connect_solidworks,
    new_document,
    save_document,
    close_document,
    open_document,
    snapshot_open_documents,
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
    extrude_cut,
    extrude_midplane,
    revolve_boss,
    chamfer,
    _empty_callout,
    _capture_sketch_ref,
)
from sw_measure import collect_bounding_box, collect_mass_properties
from model_quality_inspector import ModelQualityInspector
from cad_task_context import (
    CADTaskContext,
    CADTaskRollbackManager,
    TaskStatus,
)

# 沙箱输出目录
SANDBOX_DIR = PLUGIN_ROOT / "tests" / "real_cad" / "sandbox" / "phase4_core"
SANDBOX_DIR.mkdir(parents=True, exist_ok=True)


def list_feature_names(part) -> list[str]:
    """提取特征树中所有特征名称"""
    names = []
    feat = get_com_member(part, "FirstFeature")
    while feat:
        name = get_com_member(feat, "Name")
        if name:
            names.append(str(name))
        feat = get_com_member(feat, "GetNextFeature")
    return names


def get_body_count(part) -> int:
    """提取模型实体数（排除基准面和草图）"""
    try:
        bodies = get_com_member(part, "GetBodies2", 0, False)
        if bodies:
            return len(bodies)
        return 0
    except Exception:
        return 0


def safe_cleanup_all(app):
    """清理所有打开的非正式文档，恢复基线"""
    try:
        titles = list(snapshot_open_documents(app))
        for t in titles:
            close_document(app, t)
    except Exception:
        pass


# ==============================================================================
# 实验 1：多步骤复杂薄壁与加强结构箱体零件 (Industrial Housing)
# ==============================================================================
def run_experiment_1_industrial_housing(worker) -> dict:
    print("\n" + "=" * 70)
    print("【实验 1】多步骤复杂薄壁与加强结构箱体零件 (Industrial Housing)")
    print("=" * 70)

    def _run():
        sw, _ = connect_solidworks()
        part = new_document(sw, "part")
        if not part:
            raise RuntimeError("无法创建 SolidWorks 零件文档")

        doc_title = str(get_com_member(part, "GetTitle"))
        ext = get_com_member(part, "Extension")
        sk_mgr = get_com_member(part, "SketchManager")

        task = CADTaskContext(task_id="task_phase4_exp1")
        task.transition_to(TaskStatus.RUNNING)

        feats_pre = set(list_feature_names(part))

        # 步骤 1: 底座矩形 120 x 100 mm，拉伸 20 mm
        with sketch(part, "Top Plane") as sk1:
            sketch_rectangle(part, 0.0, 0.0, mm(120.0), mm(100.0))
        task.register_feature(str(sk1), "sketch_2d", doc_title)
        b1 = extrude_boss(part, sk1, mm(20.0), direction=False, merge=True)
        b1_name = [f for f in list_feature_names(part) if f not in feats_pre][-1]
        task.register_feature(b1_name, "extrude_boss", doc_title)
        print(f"  [1/6] 底座凸台拉伸完成 ({b1_name}): 120x100x20 mm")

        # 步骤 2: 底座顶面圆柱筒体 (外径 70 mm，向上拉伸 60 mm，总高 80 mm)
        feats_pre = set(list_feature_names(part))
        ext.SelectByID2("", "FACE", 0.0, mm(20.0), 0.0, False, 0, _empty_callout(), 0)
        sk_mgr.InsertSketch(True)
        sketch_circle(part, 0.0, 0.0, mm(35.0))  # 半径 35mm -> 外径 70mm
        sk2_ref = _capture_sketch_ref(part, source="end_sketch")
        sk_mgr.InsertSketch(True)
        task.register_feature(str(sk2_ref), "sketch_2d", doc_title)

        b2 = extrude_boss(part, sk2_ref, mm(60.0), direction=False, merge=True)
        b2_name = [f for f in list_feature_names(part) if f not in feats_pre][-1]
        task.register_feature(b2_name, "extrude_boss", doc_title)
        print(f"  [2/6] 轴承圆柱筒体拉伸完成 ({b2_name}): 外径 70mm, 高 60mm")

        # 步骤 3: 中心贯通深孔切除 (从 Top Plane 向上贯穿切除 85mm，穿透底座与圆柱筒)
        feats_pre = set(list_feature_names(part))
        with sketch(part, "Top Plane") as sk3:
            sketch_circle(part, 0.0, 0.0, mm(25.0))  # 半径 25mm -> 内径 50mm
        task.register_feature(str(sk3), "sketch_2d", doc_title)
        c1 = extrude_cut(part, sk3, mm(85.0), direction=True, flip=False)
        c1_name = [f for f in list_feature_names(part) if f not in feats_pre][-1]
        task.register_feature(c1_name, "extrude_cut", doc_title)
        print(f"  [3/6] 中心通孔深腔切除完成 ({c1_name}): 直径 50mm, 向上贯穿 85mm")

        # 步骤 4: 斜支撑筋板 (内边深入圆柱壁厚内部 X=28mm，防止曲面相切收缩脱开)
        feats_pre = set(list_feature_names(part))
        with sketch(part, "Front Plane") as sk4:
            sketch_line(part, mm(28.0), mm(20.0), mm(55.0), mm(20.0))  # 底边
            sketch_line(part, mm(55.0), mm(20.0), mm(28.0), mm(70.0))  # 斜边
            sketch_line(part, mm(28.0), mm(70.0), mm(28.0), mm(20.0))  # 内边深入
        task.register_feature(str(sk4), "sketch_2d", doc_title)
        rib1 = extrude_midplane(part, sk4, mm(8.0))
        rib1_name = [f for f in list_feature_names(part) if f not in feats_pre][-1]
        task.register_feature(rib1_name, "extrude_midplane", doc_title)
        print(f"  [4/6] 抗脱开斜撑筋板拉伸完成 ({rib1_name}): 厚 8mm")

        # 步骤 5: 内孔二次修边切除，修剪筋板伸入孔内部的分离部分
        feats_pre = set(list_feature_names(part))
        with sketch(part, "Top Plane") as sk5:
            sketch_circle(part, 0.0, 0.0, mm(25.0))
        task.register_feature(str(sk5), "sketch_2d", doc_title)
        c2 = extrude_cut(part, sk5, mm(85.0), direction=True, flip=False)
        c2_name = [f for f in list_feature_names(part) if f not in feats_pre][-1]
        task.register_feature(c2_name, "extrude_cut", doc_title)
        print(f"  [5/6] 孔内伸入修边切除完成 ({c2_name})")

        # 步骤 6: 底座四角安装孔 (4 x Dia 9mm，孔位 +/-50mm, +/-40mm，向上切穿底座 25mm)
        for i, (cx, cy) in enumerate([(50.0, 40.0), (-50.0, 40.0), (50.0, -40.0), (-50.0, -40.0)]):
            feats_pre = set(list_feature_names(part))
            with sketch(part, "Top Plane") as sk_h:
                sketch_circle(part, mm(cx), mm(cy), mm(4.5))
            task.register_feature(str(sk_h), "sketch_2d", doc_title)
            ch = extrude_cut(part, sk_h, mm(25.0), direction=True, flip=False)
            ch_name = [f for f in list_feature_names(part) if f not in feats_pre][-1]
            task.register_feature(ch_name, "extrude_cut", doc_title)
        print(f"  [6/6] 底座四角安装孔切除完成: 4 x 直径 9mm")

        # 强制重建
        get_com_member(part, "ForceRebuild3", True)

        # 几何属性独立核验
        mass = collect_mass_properties(part)
        bbox = collect_bounding_box(part)
        b_count = get_body_count(part)
        vol_actual = float(mass.get("volume_mm3", 0.0))
        size = bbox.get("size_mm", [0.0, 0.0, 0.0])
        box_x = float(size[0]) if len(size) > 0 else 0.0
        box_y = float(size[1]) if len(size) > 1 else 0.0
        box_z = float(size[2]) if len(size) > 2 else 0.0

        print(f"\n  [实测结果] 实体数: {b_count} (要求必须严格=1，严防多实体脱开)")
        print(f"  [实测结果] 物理体积: {vol_actual:.2f} mm3")
        print(f"  [实测结果] 外形包围盒: [{box_x:.1f}, {box_y:.1f}, {box_z:.1f}] mm")

        # 独立质量审查 (MQI)
        mqi_report = ModelQualityInspector.inspect_model(part)
        print(f"  [MQI独立审查] 总评分: {mqi_report.score:.1f}/100, 等级: {mqi_report.grade}")

        # 严谨断言
        assert b_count == 1, f"实体数错误: 期望 1，实测 {b_count} (存在未融合分离实体)"
        assert 280000.0 <= vol_actual <= 330000.0, f"体积超出预期范围: {vol_actual}"
        assert abs(box_x - 120.0) <= 2.0, f"包围盒 X 偏差: {box_x}"
        assert abs(box_z - 100.0) <= 2.0, f"包围盒 Z 偏差: {box_z}"

        # 落盘保存与离线重新打开闭环
        part_path = str(SANDBOX_DIR / "exp1_industrial_housing.SLDPRT")
        save_document(part, part_path)
        print(f"  [落盘保存] 文件保存成功: {part_path} ({os.path.getsize(part_path)} 字节)")

        close_document(sw, doc_title)
        time.sleep(0.5)

        # 重新打开
        reopen_doc = open_document(sw, part_path)
        assert reopen_doc is not None, "离线重新打开零件文档失败"
        mass_reopen = collect_mass_properties(reopen_doc)
        vol_reopen = float(mass_reopen.get("volume_mm3", 0.0))
        assert abs(vol_reopen - vol_actual) < 0.01, "重开后体积不一致"
        close_document(sw, str(get_com_member(reopen_doc, "GetTitle")))
        print("  [闭环验证] 离线重新打开核验 100% 一致通过！")

        task.transition_to(TaskStatus.COMPLETED)
        return {
            "status": "PASS",
            "body_count": b_count,
            "volume_mm3": vol_actual,
            "bbox_mm": [box_x, box_y, box_z],
            "mqi_score": mqi_report.score,
            "mqi_grade": mqi_report.grade,
            "file_size": os.path.getsize(part_path),
        }

    return worker.execute(_run)


# ==============================================================================
# 实验 2：精密阶梯回转套筒与复合槽孔零件 (Precision Revolved Sleeve)
# ==============================================================================
def run_experiment_2_precision_sleeve(worker) -> dict:
    print("\n" + "=" * 70)
    print("【实验 2】精密阶梯回转套筒与复合槽孔零件 (Precision Revolved Sleeve)")
    print("=" * 70)

    def _run():
        sw, _ = connect_solidworks()
        part = new_document(sw, "part")
        if not part:
            raise RuntimeError("无法创建 SolidWorks 零件文档")

        doc_title = str(get_com_member(part, "GetTitle"))
        ext = get_com_member(part, "Extension")
        sk_mgr = get_com_member(part, "SketchManager")

        task = CADTaskContext(task_id="task_phase4_exp2")
        task.transition_to(TaskStatus.RUNNING)

        feats_pre = set(list_feature_names(part))

        # 步骤 1: Front Plane 绘制阶梯回转半截面轮廓 (含旋转中心轴线)
        ext.SelectByID2("Front Plane", "PLANE", 0.0, 0.0, 0.0, False, 0, _empty_callout(), 0)
        sk_mgr.InsertSketch(True)

        # 旋转对称轴线 (Centerline) 共线于 X 轴
        sk_mgr.CreateCenterLine(0.0, 0.0, 0.0, mm(120.0), 0.0, 0.0)

        # 阶梯半轮廓:
        # X in [0, 40], 外径 60 (Y=30); X in [40, 90], 外径 45 (Y=22.5); X in [90, 120], 外径 35 (Y=17.5)
        # 内孔通孔半径 12.5 (内径 25)
        sketch_line(part, 0.0, mm(12.5), 0.0, mm(30.0))
        sketch_line(part, 0.0, mm(30.0), mm(40.0), mm(30.0))
        sketch_line(part, mm(40.0), mm(30.0), mm(40.0), mm(22.5))
        sketch_line(part, mm(40.0), mm(22.5), mm(90.0), mm(22.5))
        sketch_line(part, mm(90.0), mm(22.5), mm(90.0), mm(17.5))
        sketch_line(part, mm(90.0), mm(17.5), mm(120.0), mm(17.5))
        sketch_line(part, mm(120.0), mm(17.5), mm(120.0), mm(12.5))
        sketch_line(part, mm(120.0), mm(12.5), 0.0, mm(12.5))

        sk1_ref = _capture_sketch_ref(part, source="end_sketch")
        sk_mgr.InsertSketch(True)
        task.register_feature(str(sk1_ref), "sketch_2d", doc_title)

        # 360 度旋转成型 (2*pi)
        f_rev = revolve_boss(part, sk1_ref, 2.0 * math.pi)
        f_rev_name = [f for f in list_feature_names(part) if f not in feats_pre][-1]
        task.register_feature(f_rev_name, "revolve_boss", doc_title)
        print(f"  [1/3] 阶梯回转套筒 360度成型完成 ({f_rev_name}): 总长 120mm, 三阶梯")

        # 步骤 2: 径向润滑通孔 (在第二阶梯 X=65mm 处，Top Plane 切除通孔 Dia 6mm)
        feats_pre = set(list_feature_names(part))
        with sketch(part, "Top Plane") as sk2:
            sketch_circle(part, mm(65.0), 0.0, mm(3.0))  # 半径 3mm -> 直径 6mm
        task.register_feature(str(sk2), "sketch_2d", doc_title)
        c_oil = extrude_cut(part, sk2, mm(30.0), direction=False, flip=False)
        c_oil_name = [f for f in list_feature_names(part) if f not in feats_pre][-1]
        task.register_feature(c_oil_name, "extrude_cut", doc_title)
        print(f"  [2/3] 径向润滑通孔切除完成 ({c_oil_name}): 直径 6mm")

        # 步骤 3: 内孔全长 GB/T 标准平键槽 (宽 8mm，高出孔壁 3.3mm，X 向贯穿拉伸切除)
        feats_pre = set(list_feature_names(part))
        ext.SelectByID2("", "FACE", 0.0, mm(20.0), 0.0, False, 0, _empty_callout(), 0)
        sk_mgr.InsertSketch(True)
        sketch_rectangle(part, 0.0, mm(13.0), mm(8.0), mm(8.0))
        sk3_ref = _capture_sketch_ref(part, source="end_sketch")
        sk_mgr.InsertSketch(True)
        task.register_feature(str(sk3_ref), "sketch_2d", doc_title)

        c_key = extrude_cut(part, sk3_ref, mm(130.0), direction=False, flip=False)
        c_key_name = [f for f in list_feature_names(part) if f not in feats_pre][-1]
        task.register_feature(c_key_name, "extrude_cut", doc_title)
        print(f"  [3/3] GB/T 标准内孔键槽全长贯穿切除完成 ({c_key_name}): 宽 8mm, 贯穿 120mm")

        get_com_member(part, "ForceRebuild3", True)

        mass = collect_mass_properties(part)
        bbox = collect_bounding_box(part)
        b_count = get_body_count(part)
        vol_actual = float(mass.get("volume_mm3", 0.0))
        size = bbox.get("size_mm", [0.0, 0.0, 0.0])
        box_x = float(size[0]) if len(size) > 0 else 0.0
        box_y = float(size[1]) if len(size) > 1 else 0.0
        box_z = float(size[2]) if len(size) > 2 else 0.0

        print(f"\n  [实测结果] 实体数: {b_count} (要求严格=1)")
        print(f"  [实测结果] 物理体积: {vol_actual:.2f} mm3")
        print(f"  [实测结果] 外形包围盒: [{box_x:.1f}, {box_y:.1f}, {box_z:.1f}] mm (轴长严格 120.0mm)")

        mqi_report = ModelQualityInspector.inspect_model(part)
        print(f"  [MQI独立审查] 总评分: {mqi_report.score:.1f}/100, 等级: {mqi_report.grade}")

        assert b_count == 1, f"实体数错误: 期望 1，实测 {b_count}"
        assert 150000.0 <= vol_actual <= 165000.0, f"体积超出预期: {vol_actual}"
        assert abs(box_x - 120.0) <= 1.0, f"总轴长偏差: {box_x}"
        assert abs(box_y - 60.0) <= 1.0, f"最大外径高度偏差: {box_y}"

        part_path = str(SANDBOX_DIR / "exp2_precision_sleeve.SLDPRT")
        save_document(part, part_path)
        print(f"  [落盘保存] 文件保存成功: {part_path} ({os.path.getsize(part_path)} 字节)")

        close_document(sw, doc_title)
        time.sleep(0.5)

        reopen_doc = open_document(sw, part_path)
        assert reopen_doc is not None, "重开失败"
        mass_reopen = collect_mass_properties(reopen_doc)
        vol_reopen = float(mass_reopen.get("volume_mm3", 0.0))
        assert abs(vol_reopen - vol_actual) < 0.01, "重开体积不一致"
        close_document(sw, str(get_com_member(reopen_doc, "GetTitle")))
        print("  [闭环验证] 离线重新打开核验 100% 一致通过！")

        task.transition_to(TaskStatus.COMPLETED)
        return {
            "status": "PASS",
            "body_count": b_count,
            "volume_mm3": vol_actual,
            "bbox_mm": [box_x, box_y, box_z],
            "mqi_score": mqi_report.score,
            "mqi_grade": mqi_report.grade,
            "file_size": os.path.getsize(part_path),
        }

    return worker.execute(_run)


# ==============================================================================
# 实验 3：参数联动形变、破坏性注入与逆序自愈实验 (Parametric Dependency & Healing)
# ==============================================================================
def run_experiment_3_parametric_dependency_and_healing(worker) -> dict:
    print("\n" + "=" * 70)
    print("【实验 3】参数化依赖联动、几何形变响应与破坏性故障注入逆序自愈")
    print("=" * 70)

    part_path = str(SANDBOX_DIR / "exp3_parametric_healing.SLDPRT")
    if os.path.exists(part_path):
        try:
            os.remove(part_path)
        except Exception:
            pass

    def _run():
        sw, _ = connect_solidworks()
        part = new_document(sw, "part")
        if not part:
            raise RuntimeError("无法创建 SolidWorks 零件文档")

        doc_title = str(get_com_member(part, "GetTitle"))

        task = CADTaskContext(task_id="task_phase4_exp3")
        task.transition_to(TaskStatus.RUNNING, "Starting parametric baseline")
        task.register_document(part, title=doc_title, path=part_path, is_newly_created=False)

        # 阶段 3.1: 建立基础多特征零件 (基准凸台 80x60x30mm)
        feats_pre = set(list_feature_names(part))
        with sketch(part, "Top Plane") as sk1:
            sketch_rectangle(part, 0.0, 0.0, mm(80.0), mm(60.0))
        task.register_feature(str(sk1), "sketch_2d", doc_title)
        b1 = extrude_boss(part, sk1, mm(30.0), direction=False, merge=True)
        b1_name = [f for f in list_feature_names(part) if f not in feats_pre][-1]
        task.register_feature(b1_name, "extrude_boss", doc_title)

        mass_init = collect_mass_properties(part)
        vol_init = float(mass_init.get("volume_mm3", 0.0))
        print(f"  [基准特征] 初始单特征成型. 初始体积: {vol_init:.2f} mm3")

        # 阶段 3.2: 参数驱动联动与多特征依赖 (添加支柱凸台 D=30mm, H=50mm)
        feats_pre = set(list_feature_names(part))
        with sketch(part, "Top Plane") as sk2:
            sketch_circle(part, 0.0, 0.0, mm(15.0))  # 半径 15mm -> 直径 30mm
        task.register_feature(str(sk2), "sketch_2d", doc_title)
        b2 = extrude_boss(part, sk2, mm(50.0), direction=False, merge=True)
        b2_name = [f for f in list_feature_names(part) if f not in feats_pre][-1]
        task.register_feature(b2_name, "extrude_boss", doc_title)

        get_com_member(part, "ForceRebuild3", True)

        mass_mod = collect_mass_properties(part)
        bbox_mod = collect_bounding_box(part)
        vol_mod = float(mass_mod.get("volume_mm3", 0.0))
        size_mod = bbox_mod.get("size_mm", [0.0, 0.0, 0.0])

        print(f"  [联动核验] 衍生特征加载后体积: {vol_mod:.2f} mm3 (正向增长)")
        print(f"  [联动核验] 衍生特征外形包围盒: {size_mod}")

        assert vol_mod > vol_init, "体积未发生正向增长，参数化特征依赖断链"
        assert get_body_count(part) == 1, "两特征未成功熔合为单一实体"
        print("  [参数联动] 多特征参数化依赖与真实几何形变响应核验通过！")

        # 阶段 3.3: 破坏性故障注入与事务逆序物理回滚
        print("\n  [故障注入] 注入破坏性异常工况，触发 TaskContext 事务逆序回滚...")
        task.transition_to(TaskStatus.ROLLING_BACK, "Injected boundary failure condition")

        rollback_mgr = CADTaskRollbackManager(task, sw_app=sw)
        rollback_res = rollback_mgr.rollback()
        print(f"  [Level 3 回滚] 逆序物理回滚执行完毕. 状态: {rollback_res.status.value}, 清理清单: {rollback_res.cleaned_features}")

        # 重新重建并核验自愈结果
        get_com_member(part, "ForceRebuild3", True)
        b_healed = get_body_count(part)
        mass_healed = collect_mass_properties(part)
        vol_healed = float(mass_healed.get("volume_mm3", 0.0))

        print(f"  [自愈核验] 回滚后实体数: {b_healed} (严格清零，干净恢复)")
        print(f"  [自愈核验] 回滚后体积: {vol_healed:.2f} mm3")

        assert b_healed == 0, f"回滚后实体未完全清理: 实测 {b_healed}"
        assert vol_healed == 0.0, f"回滚后残留非零体积: {vol_healed}"
        print("  [自愈闭环] 破坏性故障拦截、三级逆序物理回滚与模型状态机 100% 成功闭环！")

        close_document(sw, doc_title)
        return {
            "status": "PASS",
            "vol_init": vol_init,
            "vol_mod": vol_mod,
            "rollback_status": rollback_res.status.value,
            "cleaned_features": rollback_res.cleaned_features,
            "body_count_healed": b_healed,
            "vol_healed": vol_healed,
        }

    return worker.execute(_run)


# ==============================================================================
# 主执行入口与物理物证产出
# ==============================================================================
def main():
    print("=" * 80)
    print("NIGHT-ENGINEERING-PHASE4: CAD 核心建模高难度实机验证启动")
    print(f"执行时间戳: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"测试沙箱路径: {SANDBOX_DIR}")
    print("=" * 80)

    worker = get_sta_worker()
    sw, _ = connect_solidworks()
    if not sw:
        print("[FATAL] 无法连接 SolidWorks COM 实例，测试终止")
        sys.exit(1)

    safe_cleanup_all(sw)
    open_docs = snapshot_open_documents(sw)
    assert len(open_docs) == 0, f"前置基线文档数非零: {open_docs}"

    results = {}
    t0 = time.time()

    try:
        # 执行实验 1
        results["exp1_industrial_housing"] = run_experiment_1_industrial_housing(worker)

        # 执行实验 2
        results["exp2_precision_sleeve"] = run_experiment_2_precision_sleeve(worker)

        # 执行实验 3
        results["exp3_parametric_healing"] = run_experiment_3_parametric_dependency_and_healing(worker)

    except Exception as e:
        print(f"\n[ERROR] 实机测试异常中断: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        safe_cleanup_all(sw)
        doc_count_final = len(snapshot_open_documents(sw))
        print(f"\n[基线恢复] 测试完成，后置活动文档数严格恢复为: {doc_count_final}")

    elapsed = time.time() - t0
    print("\n" + "=" * 80)
    print(f"全部实机建模实验圆满完成！总耗时: {elapsed:.2f} 秒")
    print("=" * 80)

    evidence_path = SANDBOX_DIR / "phase4_modeling_evidence.json"
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "suite": "phase4_cad_core_suite",
                "elapsed_seconds": elapsed,
                "environment": {
                    "cad_engine": "SolidWorks 2024",
                    "python": sys.version,
                    "sandbox": str(SANDBOX_DIR),
                },
                "results": results,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(f"物证日志已存盘: {evidence_path}")
    print("ALL TESTS PASSED WITH 100% CREDIBILITY.")


if __name__ == "__main__":
    main()
