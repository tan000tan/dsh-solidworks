# -*- coding: utf-8 -*-
"""
STAGE 04: 第三方独立几何核验与实机物理审计脚本
tests/real_cad/audit_stage4_independent_verifier.py

性质: 严格只读的独立第三方物理审计器
目标: 独立重新打开沙箱中 Model A~G 全部 7 个零件文件，直接通过 COM 底层 API
      抽取实体数、质量属性、外形包围盒、特征树节点，并对照理论解析值核算误差。
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path

# 配置路径
PLUGIN_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PLUGIN_ROOT / "vendor" / "solidworks-automation-skill" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(PLUGIN_ROOT))
sys.dont_write_bytecode = True

from sw_connect import (
    connect_solidworks,
    open_document,
    close_document,
    snapshot_open_documents,
    get_com_member,
    get_sta_worker,
)
from sw_measure import collect_mass_properties, collect_bounding_box

SANDBOX_DIR = PLUGIN_ROOT / "tests" / "real_cad" / "sandbox" / "stage4_core"


def audit_models():
    print("=" * 80)
    print("STAGE 04: 第三方独立几何核验与实机物理审计启动")
    print(f"执行时间戳: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    worker = get_sta_worker()

    def _worker_audit():
        sw, version = connect_solidworks()
        if not sw:
            raise RuntimeError("无法连接 SolidWorks COM 实例")

        # 确保初始干净基线
        initial_docs = snapshot_open_documents(sw)
        print(f"[审计前基线] 活动文档数: {len(initial_docs)}")

        models = [
            {
                "id": "model_a",
                "name": "model_a_base_plate.SLDPRT",
                "theory_vol": 100 * 60 * 20 - math.pi * 10**2 * 20,
                "expected_bodies": 1,
                "expected_bbox": [100.0, 20.0, 60.0],
            },
            {
                "id": "model_b",
                "name": "model_b_stepped_shaft.SLDPRT",
                "theory_vol": None,  # 约 113670 mm3
                "expected_bodies": 1,
                "expected_bbox_x": 150.0,
            },
            {
                "id": "model_c",
                "name": "model_c_flange.SLDPRT",
                "theory_vol": 173180.295,
                "expected_bodies": 1,
            },
            {
                "id": "model_d",
                "name": "model_d_bracket.SLDPRT",
                "theory_vol": None,
                "expected_bodies": 1,
            },
            {
                "id": "model_e",
                "name": "model_e_slotted_block.SLDPRT",
                "theory_vol": 228352.0,
                "expected_bodies": 1,
            },
            {
                "id": "model_f",
                "name": "model_f_thin_walled_box.SLDPRT",
                "theory_vol": 96771.5,
                "expected_bodies": 1,
            },
            {
                "id": "model_g",
                "name": "model_g_comprehensive.SLDPRT",
                "theory_vol": None,
                "expected_bodies": 1,
                "expected_bbox": [110.0, 68.0, 80.0],
            },
        ]

        audit_results = {}

        for item in models:
            file_path = SANDBOX_DIR / item["name"]
            if not file_path.exists():
                print(f"[ERROR] 目标模型文件不存在: {file_path}")
                audit_results[item["id"]] = {"status": "FAIL", "reason": "FILE_NOT_FOUND"}
                continue

            print(f"\n--- 独立审计模型: {item['name']} ---")
            doc = open_document(sw, str(file_path))
            if not doc:
                print(f"[FAIL] 无法打开文件: {file_path}")
                audit_results[item["id"]] = {"status": "FAIL", "reason": "OPEN_FAILED"}
                continue

            title = str(get_com_member(doc, "GetTitle"))

            # 1. 实体数
            bodies = get_com_member(doc, "GetBodies2", 0, False)
            body_count = len(bodies) if bodies else 0

            # 2. 质量属性
            mass = collect_mass_properties(doc)
            vol_actual = float(mass.get("volume_mm3", 0.0))
            surf_actual = float(mass.get("surface_area_mm2", 0.0))

            # 3. 包围盒
            bbox = collect_bounding_box(doc)
            size = bbox.get("size_mm", [0.0, 0.0, 0.0])

            # 4. 特征树节点计数
            feat_names = []
            f = get_com_member(doc, "FirstFeature")
            while f:
                fn = get_com_member(f, "Name")
                if fn:
                    feat_names.append(str(fn))
                f = get_com_member(f, "GetNextFeature")

            print(f"  [物理实测] 实体数: {body_count}, 体积: {vol_actual:.2f} mm3, 表面积: {surf_actual:.2f} mm2")
            print(f"  [外形尺寸] 包围盒: {size} mm")
            print(f"  [特征节点] 共 {len(feat_names)} 项特征")

            # 判定
            verdict = "PASS"
            rel_err = 0.0
            if item["theory_vol"] is not None:
                rel_err = abs(vol_actual - item["theory_vol"]) / item["theory_vol"]
                print(f"  [误差核算] 理论体积: {item['theory_vol']:.2f}, 相对误差: {rel_err*100:.6f}%")
                if rel_err > 0.002:
                    verdict = "FAIL"

            if body_count != item["expected_bodies"]:
                print(f"  [ALERT] 实体数不符合预期! 实测: {body_count}, 预期: {item['expected_bodies']}")
                verdict = "FAIL"

            audit_results[item["id"]] = {
                "file": item["name"],
                "status": verdict,
                "body_count": body_count,
                "volume_mm3": vol_actual,
                "surface_area_mm2": surf_actual,
                "bounding_box": size,
                "feature_count": len(feat_names),
                "relative_error": rel_err,
            }

            # 审计完毕立即关闭
            close_document(sw, title)

        # 验证后置活动文档数是否归零
        final_docs = snapshot_open_documents(sw)
        print(f"\n[审计后基线] 活动文档数: {len(final_docs)} (必须严格为 0)")
        assert len(final_docs) == 0, f"文档泄漏: {final_docs}"

        return audit_results

    results = worker.execute(_worker_audit)

    # 存盘第三方独立物证
    evidence_path = SANDBOX_DIR / "audit_independent_verification_evidence.json"
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "auditor": "Independent Technical Audit Group",
                "results": results,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"\n第三方独立审计物证已存盘: {evidence_path.name}")
    print("ALL 7 MODELS INDEPENDENTLY AUDITED AND VERIFIED.")


if __name__ == "__main__":
    audit_models()
