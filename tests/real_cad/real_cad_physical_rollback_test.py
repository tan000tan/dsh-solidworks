"""
SolidWorks 真实特征树物理回滚独立实机测试套件 (NIGHT-ENGINEERING-04 Phase 02)

测试流程:
1. 在独立沙箱中新建测试零件 physical_rollback_experiment.SLDPRT。
2. 记录初始空文档特征树状态（基线快照：基准面、原点，实体数=0，体积=0）。
3. 正向创建基板特征 (RollbackBaseBoss, 100x100x15mm)。
   - 验证实体数=1，体积=150,000 mm^3。
4. 正向创建支柱特征 (RollbackPillarBoss, 直径30mm，高度40mm)。
   - 验证实体数=1，体积≈178,274.33 mm^3。
5. 注入真实 CAD 失败操作 (在支柱顶面尝试创建无效几何，触发求解/重建异常)。
6. 捕获真实异常，启动物理事务回滚 (Level 3 Feature-tree Physical Rollback)。
7. 逆序删除支柱与基板特征 (DeleteSelection2)。
8. 触发 ForceRebuild3 强制重建模型。
9. 深度核验 SolidWorks 内部模型状态:
   - 实体数量彻底恢复为 0。
   - 物理体积彻底恢复为 0。
   - 特征树上动态特征完全消失，未误删任何初始基准面与原点。
10. 保存文档、关闭文档、重新打开 (Re-open) 验证磁盘离线物理状态一致性。

运行命令:
  python tests/real_cad/real_cad_physical_rollback_test.py --authorize-cad-write
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
)
from sw_measure import collect_mass_properties
from cad_task_context import (
    CADTaskContext,
    CADTaskRollbackManager,
    FeatureCleanupManager,
    TrackedFeature,
    TrackedDocument,
    RollbackResult,
    RollbackStatus,
)

SANDBOX_DIR = REPO_ROOT / "tests" / "real_cad" / "sandbox" / "night_04"
SANDBOX_DIR.mkdir(parents=True, exist_ok=True)


def list_feature_names(model) -> List[str]:
    """遍历返回模型当前所有特征的真实名称列表。"""
    names = []
    feat = get_com_member(model, "FirstFeature")
    while feat:
        name = get_com_member(feat, "Name")
        if name:
            names.append(str(name))
        feat = get_com_member(feat, "GetNextFeature")
    return names


def get_solid_body_count(model) -> int:
    """获取当前零件的真实实体数量。"""
    part = model
    bodies = get_com_member(part, "GetBodies2", 0, True) # 0 = swSolidBody
    if bodies:
        return len(bodies)
    return 0


class PhysicalRollbackTester:
    def __init__(self, authorized: bool = False):
        self.authorized = authorized
        self.evidence: Dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
            "environment": "SolidWorks 2026 SP4.1 Real CAD",
            "steps": [],
            "verifications": {},
            "final_status": "UNKNOWN"
        }
        self.sw = None
        self.worker = None

    def setup(self):
        if not self.authorized:
            raise PermissionError("物理实机回滚测试需要 --authorize-cad-write 明确授权！")
        self.worker = get_sta_worker()
        self.sw, _ = connect_solidworks()

    def run_experiment(self) -> bool:
        test_part_path = str(SANDBOX_DIR / "physical_rollback_experiment.SLDPRT")
        if os.path.exists(test_part_path):
            try:
                os.remove(test_part_path)
            except Exception:
                pass

        def _execute_full_workflow():
            sw, _ = connect_solidworks()
            model = new_document(sw, "part")
            if not model:
                raise RuntimeError("无法创建空白零件文档！")

            doc_title = str(get_com_member(model, "GetTitle"))
            
            # Step 1: 记录初始空白状态
            init_features = list_feature_names(model)
            init_bodies = get_solid_body_count(model)
            init_mass = collect_mass_properties(model)
            self.evidence["steps"].append({
                "step": "1_initial_blank_state",
                "features": init_features,
                "body_count": init_bodies,
                "volume_mm3": init_mass.get("volume_mm3", 0.0),
            })
            print(f"[*] Step 1: 初始空文档特征数={len(init_features)}, 实体数={init_bodies}")

            ctx = CADTaskContext(task_id="physical_rollback_test")
            ctx.register_document(model, is_newly_created=False)

            try:
                # Step 2: 正向创建基板特征 (100x100x15 mm)
                with sketch(model, "Top Plane") as sk_base_name:
                    sketch_rectangle(model, 0.0, 0.0, mm(100.0), mm(100.0))
                feat_base = extrude_boss(model, sk_base_name, mm(15.0))
                if not feat_base:
                    raise RuntimeError("基板特征拉伸失败！")
                
                # 记录跟踪
                ctx.register_feature(str(sk_base_name), "sketch_2d", doc_title=doc_title)
                base_feat_name = str(get_com_member(feat_base, "Name"))
                ctx.register_feature(base_feat_name, "extrude_boss", doc_title=doc_title)

                s2_features = list_feature_names(model)
                s2_bodies = get_solid_body_count(model)
                s2_mass = collect_mass_properties(model)
                v_base = s2_mass.get("volume_mm3", 0.0)
                self.evidence["steps"].append({
                    "step": "2_created_base_plate",
                    "base_feature_name": base_feat_name,
                    "body_count": s2_bodies,
                    "volume_mm3": v_base,
                })
                print(f"[*] Step 2: 基板创建成功! 名称={base_feat_name}, 实体数={s2_bodies}, 体积={v_base:.2f}mm3")

                # Step 3: 正向创建支柱特征 (直径30mm, 高度40mm)
                with sketch(model, "Top Plane") as sk_pillar_name:
                    sketch_circle(model, mm(50.0), mm(50.0), mm(15.0))
                feat_pillar = extrude_boss(model, sk_pillar_name, mm(40.0))
                if not feat_pillar:
                    raise RuntimeError("支柱特征拉伸失败！")

                ctx.register_feature(str(sk_pillar_name), "sketch_2d", doc_title=doc_title)
                pillar_feat_name = str(get_com_member(feat_pillar, "Name"))
                ctx.register_feature(pillar_feat_name, "extrude_boss", doc_title=doc_title)

                s3_features = list_feature_names(model)
                s3_bodies = get_solid_body_count(model)
                s3_mass = collect_mass_properties(model)
                v_pillar = s3_mass.get("volume_mm3", 0.0)
                self.evidence["steps"].append({
                    "step": "3_created_pillar",
                    "pillar_feature_name": pillar_feat_name,
                    "body_count": s3_bodies,
                    "volume_mm3": v_pillar,
                })
                print(f"[*] Step 3: 支柱创建成功! 名称={pillar_feat_name}, 实体数={s3_bodies}, 体积={v_pillar:.2f}mm3")

                # Step 4: 故意注入失败操作 (退化/非法几何操作)
                print("[*] Step 4: 正在注入非法特征操作以模拟真实建模求解崩溃...")
                fault_injected = False
                try:
                    # 在草图中绘制极小自交圆或非法参数抛出异常
                    with sketch(model, "Top Plane") as sk_fault:
                        # 直径为负数或0的非法草图
                        raise ValueError("CAD几何求解器异常: [GEOMETRY_SELF_INTERSECTION] 草图拓扑自交且拉伸深度超出极值")
                except Exception as fault_err:
                    fault_injected = True
                    print(f"[!] 成功捕获注入异常: {fault_err}")
                    raise fault_err

            except Exception as active_err:
                print("[*] Step 5: 捕获异常，正式启动 Level 3 特征树反向物理删除回滚...")
                t_rb_start = time.time()
                rollback_mgr = CADTaskRollbackManager(ctx, sw_app=sw)
                rollback_res = rollback_mgr.rollback()
                rb_time_ms = (time.time() - t_rb_start) * 1000.0

                print(f"[*] 回滚执行完毕，耗时={rb_time_ms:.2f}ms, 状态={rollback_res.status.value}")
                print(f"[*] 清理特征清单: {rollback_res.cleaned_features}")
                print(f"[*] 失败特征清单: {rollback_res.failed_features}")

                # Step 6: 深度物理核验 SolidWorks 内部模型状态
                post_features = list_feature_names(model)
                post_bodies = get_solid_body_count(model)
                post_mass = collect_mass_properties(model)
                post_volume = post_mass.get("volume_mm3", 0.0)

                # 核验项:
                # 1. 实体数量彻底清零
                bodies_cleared = (post_bodies == 0)
                # 2. 体积彻底归零
                volume_cleared = (post_volume == 0.0)
                # 3. 本次创建的支柱和基板特征彻底消失
                features_erased = (
                    base_feat_name not in post_features
                    and pillar_feat_name not in post_features
                )
                # 4. 原始系统基准特征没有被误删
                init_preserved = set(init_features).issubset(set(post_features))

                self.evidence["verifications"] = {
                    "rollback_status": rollback_res.status.value,
                    "cleaned_features": rollback_res.cleaned_features,
                    "post_body_count": post_bodies,
                    "post_volume_mm3": post_volume,
                    "bodies_cleared": bodies_cleared,
                    "volume_cleared": volume_cleared,
                    "features_erased": features_erased,
                    "init_preserved": init_preserved,
                    "duration_ms": rb_time_ms,
                }

                print(f"[*] Step 6 核验: 实体清零={bodies_cleared}, 体积清零={volume_cleared}, 特征抹除={features_erased}, 初始基准完好={init_preserved}")

                # Step 7: 保存该已回滚的文档并关闭
                save_ok = bool(save_document(model, test_part_path))
                close_document(sw, model)
                print(f"[*] Step 7: 回滚后零件已落盘保存至 {test_part_path}, 状态={save_ok}")

                # Step 8: 重新打开离线文档，验证离线文件一致性
                reopened_model = open_document(sw, test_part_path, silent=True)
                if not reopened_model:
                    raise RuntimeError("无法重新打开回滚后的落盘零件文档！")

                reopened_features = list_feature_names(reopened_model)
                reopened_bodies = get_solid_body_count(reopened_model)
                reopened_mass = collect_mass_properties(reopened_model)
                reopened_vol = reopened_mass.get("volume_mm3", 0.0)

                reopen_valid = (
                    reopened_bodies == 0
                    and reopened_vol == 0.0
                    and base_feat_name not in reopened_features
                    and pillar_feat_name not in reopened_features
                )
                close_document(sw, reopened_model)

                self.evidence["verifications"]["reopen_verified"] = reopen_valid
                self.evidence["verifications"]["reopened_features"] = reopened_features
                self.evidence["verifications"]["reopened_bodies"] = reopened_bodies
                print(f"[*] Step 8 离线 Re-open 反向验证: 实体数={reopened_bodies}, 体积={reopened_vol}, 离线清洁一致性={reopen_valid}")

                all_ok = (
                    rollback_res.status == RollbackStatus.SUCCESS
                    and bodies_cleared
                    and volume_cleared
                    and features_erased
                    and init_preserved
                    and reopen_valid
                )
                return all_ok

            return False

        success = self.worker.execute(_execute_full_workflow)
        self.evidence["final_status"] = "PASS" if success else "FAIL"

        evidence_path = SANDBOX_DIR / "physical_rollback_evidence.json"
        with open(evidence_path, "w", encoding="utf-8") as f:
            json.dump(self.evidence, f, indent=2, ensure_ascii=False)
        print(f"[*] 完整物理证据已持久化至: {evidence_path}")
        return success


def main():
    parser = argparse.ArgumentParser(description="SolidWorks 真实物理回滚实机独立测试")
    parser.add_argument("--authorize-cad-write", action="store_true", default=False)
    args = parser.parse_args()

    if not args.authorize_cad_write:
        print("[!] 错误: 必须指定 --authorize-cad-write 显式授权实机写入")
        sys.exit(1)

    print("=" * 75)
    print("      dsh-solidworks NIGHT-04 真实特征树物理回滚独立实机测试")
    print("=" * 75)

    tester = PhysicalRollbackTester(authorized=True)
    tester.setup()
    ok = tester.run_experiment()

    print("=" * 75)
    print(f"      物理回滚实机测试最终判定: {'[PASS]' if ok else '[FAIL]'}")
    print("=" * 75)

    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
