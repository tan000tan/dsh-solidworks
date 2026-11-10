# -*- coding: utf-8 -*-
"""
SolidWorks 尺寸参数识别、修改与依赖更新安全管理模块 (dimension_manager.py)

设计定位：
作为 dsh-solidworks-plugin 统一尺寸参数管理门面 (Unified Façade & Delegation Architecture)：
1. 识别 (identify_dimensions)：依托新一代 DimensionReader 提取高保真 DimensionModelIR，并提供向后兼容字典；
2. 影响面评估 (inspect_dimension_impact)：依托 DimensionDependencyGraph (DDG) 深度分析波及特征链与循环依赖；
3. 安全修改与自愈回滚 (modify_dimensions_safe)：
   - 结合 DimensionModifier 与 ShadowBackupManager 形成参数级与文件级双保险事务；
   - 严格就地写入 SetSystemValue3，绝对禁止通过删除重构模型冒充原位修改；
   - 遇几何自交或重构错误自动无损还原，杜绝脏化模型；
4. 深度导出新一代 P1 核心体系类，实现 100% 向后兼容与前向演进。
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

try:
    from .sw_connect import get_com_member, save_document
    from .shadow_backup import ShadowBackupManager
    from .sw_document_data import update_dimension_mm
    from .dimension_ir import DimensionIRNode, DimensionModelIR, DimensionType, DimensionRole
    from .dimension_reader import read_model_dimensions, walk_all_features
    from .dimension_dependency_graph import DimensionDependencyGraph, DDGImpactReport
    from .dimension_modifier import DimensionModifier, ModificationResult
    from .model_rebuilder import ModelRebuilder
    from .dimension_validator import DimensionValidator
except ImportError:
    from sw_connect import get_com_member, save_document
    from shadow_backup import ShadowBackupManager
    from sw_document_data import update_dimension_mm
    from dimension_ir import DimensionIRNode, DimensionModelIR, DimensionType, DimensionRole
    from dimension_reader import read_model_dimensions, walk_all_features
    from dimension_dependency_graph import DimensionDependencyGraph, DDGImpactReport
    from dimension_modifier import DimensionModifier, ModificationResult
    from model_rebuilder import ModelRebuilder
    from dimension_validator import DimensionValidator


logger = logging.getLogger("solidworks_dimension_manager")

__all__ = [
    "DimensionUpdateError",
    "identify_dimensions",
    "inspect_dimension_impact",
    "modify_dimensions_safe",
    "update_dimension_mm",
    "iter_all_features",
    "DimensionIRNode",
    "DimensionModelIR",
    "DimensionType",
    "DimensionRole",
    "DimensionDependencyGraph",
    "DDGImpactReport",
    "DimensionModifier",
    "ModificationResult",
    "ModelRebuilder",
    "DimensionValidator",
]


class DimensionUpdateError(RuntimeError):
    """当尺寸修改或模型重构失败时抛出的结构化异常。"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.details = details or {}


def _iter_feature_chain(start_feature, next_method_name: str = "GetNextFeature"):
    """安全遍历特征链，防御循环死锁。"""
    curr = start_feature
    visited = 0
    while curr is not None and visited < 4096:
        yield curr
        visited += 1
        try:
            curr = get_com_member(curr, next_method_name)
        except Exception:
            break


def iter_all_features(model) -> List[Any]:
    """递归遍历模型所有顶层特征及其子特征（如拉伸下的草图）。"""
    features: List[Any] = []
    seen_names = set()

    def walk(feat):
        if feat is None:
            return
        name = str(get_com_member(feat, "Name") or "")
        feat_type = str(get_com_member(feat, "GetTypeName2") or "")
        key = (name, feat_type)
        if key not in seen_names:
            seen_names.add(key)
            features.append(feat)

        # 遍历子特征
        try:
            sub = get_com_member(feat, "GetFirstSubFeature")
        except Exception:
            sub = None
        for child in _iter_feature_chain(sub, "GetNextSubFeature"):
            walk(child)

    top_feature = get_com_member(model, "FirstFeature")
    for feat in _iter_feature_chain(top_feature, "GetNextFeature"):
        walk(feat)

    return features


def _read_dim_value_mm(dim) -> float:
    """安全读取尺寸数值并换算为毫米。"""
    try:
        val_m = float(get_com_member(dim, "SystemValue") or 0.0)
        return round(val_m * 1000.0, 6)
    except Exception:
        return 0.0


def _identify_dimensions_legacy(model) -> Dict[str, Any]:
    """底座向后兼容遍历引擎，确保非标准 COM / Mock 测试 100% 稳定运行。"""
    all_features = iter_all_features(model)
    dimension_list: List[Dict[str, Any]] = []
    dimension_map: Dict[str, Dict[str, Any]] = {}

    for feat in all_features:
        feat_name = str(get_com_member(feat, "Name") or "")
        feat_type = str(get_com_member(feat, "GetTypeName2") or "")

        try:
            disp_dim = get_com_member(feat, "GetFirstDisplayDimension")
        except Exception:
            disp_dim = None

        while disp_dim is not None:
            try:
                dim = get_com_member(disp_dim, "GetDimension2", 0)
                if dim is None:
                    dim = get_com_member(disp_dim, "GetDimension")
            except Exception:
                dim = None

            if dim is not None:
                dim_full_name = str(get_com_member(dim, "FullName") or "")
                if not dim_full_name:
                    dim_full_name = f"{get_com_member(dim, 'Name')}@{feat_name}"

                val_mm = _read_dim_value_mm(dim)
                driven_state = bool(get_com_member(dim, "DrivenState") or 0)

                dim_info = {
                    "full_name": dim_full_name,
                    "name": str(get_com_member(dim, "Name") or dim_full_name),
                    "feature_name": feat_name,
                    "feature_type": feat_type,
                    "value_mm": val_mm,
                    "is_driven": driven_state,
                }
                if dim_full_name not in dimension_map:
                    dimension_map[dim_full_name] = dim_info
                    dimension_list.append(dim_info)

            try:
                disp_dim = get_com_member(feat, "GetNextDisplayDimension", disp_dim)
            except Exception:
                break

    return {
        "status": "success",
        "count": len(dimension_list),
        "dimensions": dimension_list,
        "dimension_map": dimension_map,
    }


def identify_dimensions(model) -> Dict[str, Any]:
    """
    枚举当前活动模型中的所有尺寸参数（包括草图尺寸与特征尺寸）。
    优先依托新一代 DimensionReader 提取高保真 DimensionModelIR，并转换为标准向后兼容字典。
    """
    if model is None:
        return {"status": "error", "count": 0, "dimensions": [], "dimension_map": {}}

    try:
        model_ir = read_model_dimensions(model)
        dim_list: List[Dict[str, Any]] = []
        dim_map: Dict[str, Dict[str, Any]] = {}

        for name, node in model_ir.dimensions.items():
            info = {
                "full_name": node.dimension_name,
                "name": node.dimension_name.split("@")[0] if "@" in node.dimension_name else node.dimension_name,
                "feature_name": node.feature_name,
                "feature_type": node.feature_type,
                "value_mm": round(node.system_value * 1000.0, 6),
                "is_driven": node.is_driven,
                "dim_type": node.dim_type.value,
            }
            dim_list.append(info)
            dim_map[node.dimension_name] = info

        return {
            "status": "success",
            "count": len(dim_list),
            "dimensions": dim_list,
            "dimension_map": dim_map,
            "model_ir": model_ir,
            "ir_available": True,
        }
    except Exception as exc:
        logger.debug(f"新版 DimensionReader 读取降级至兼容引擎: {exc}")
        return _identify_dimensions_legacy(model)


def inspect_dimension_impact(model, dimension_name: str) -> Dict[str, Any]:
    """
    评估指定尺寸被修改时，其在特征树中可能产生影响的下游特征链与依赖网络。
    结合特征拓扑与 DimensionDependencyGraph 提供高阶影响域分析。
    """
    clean_dim = dimension_name.strip()
    target_feat_name = ""
    if "@" in clean_dim:
        target_feat_name = clean_dim.split("@", 1)[1]

    all_features = iter_all_features(model)
    feature_names = [str(get_com_member(f, "Name") or "") for f in all_features]

    if target_feat_name and target_feat_name in feature_names:
        idx = feature_names.index(target_feat_name)
        downstream_features = feature_names[idx + 1 :]
    else:
        idx = -1
        downstream_features = []

    result: Dict[str, Any] = {
        "dimension": clean_dim,
        "owner_feature": target_feat_name or "Unknown",
        "owner_feature_index": idx,
        "total_features": len(feature_names),
        "potential_impacted_features": downstream_features,
        "impact_count": len(downstream_features),
    }

    # 尝试利用 DDG 丰富更精细的拓扑影响域信息
    try:
        ddg = DimensionDependencyGraph(model_title=str(get_com_member(model, "GetTitle") or "Part"))
        for i, fname in enumerate(feature_names):
            ddg.add_feature(fname)
            if i > 0:
                ddg.add_dependency(feature_names[i - 1], fname, relation_type="feature_hierarchy")
        if target_feat_name:
            ddg.add_dependency(clean_dim, target_feat_name, relation_type="sketch_to_feature")
            report = ddg.analyze_modification_impact({clean_dim: 0.0})
            result["ddg_supported"] = True
            result["has_cycles"] = report.has_cycles
            result["topological_rebuild_order"] = report.topological_rebuild_order
    except Exception:
        result["ddg_supported"] = False

    return result


def modify_dimensions_safe(
    model,
    updates: Dict[str, float],
    *,
    sw=None,
    doc_path: Optional[str] = None,
    auto_rollback: bool = True,
    rebuild: bool = True,
    save: bool = False,
    configuration_mode: str = "current",
) -> Dict[str, Any]:
    """
    安全事务性修改一组尺寸参数。

    安全保护机制：
    1. 在修改开始前，若提供 doc_path 且文件存在，自动调用 ShadowBackupManager 创建独立影子副本；
    2. 记录修改前实际回读值；
    3. 调用 update_dimension_mm 更新每个尺寸；
    4. 执行 EditRebuild3 触发重构；
    5. 若重构失败或抛出异常，且 auto_rollback=True，自动还原影子副本；
    6. 若重构成功，销毁影子副本并按需保存。
    """
    if not updates:
        raise ValueError("updates 字典不能为空")

    backup_mgr = ShadowBackupManager()
    has_backup = False
    backup_path = None

    if doc_path and os.path.exists(doc_path) and auto_rollback:
        try:
            backup_path = backup_mgr.capture(doc_path)
            has_backup = True
        except Exception as e:
            logger.warning(f"未能创建影子备份: {e}，将无备份继续执行")

    applied_results = []
    before_state: Dict[str, float] = {}
    after_state: Dict[str, float] = {}

    try:
        for dim_name, new_val in updates.items():
            if new_val <= 0:
                raise ValueError(f"尺寸 '{dim_name}' 的新数值必须大于 0, 当前为: {new_val}")

            res = update_dimension_mm(
                model,
                dim_name,
                float(new_val),
                configuration_mode=configuration_mode,
                rebuild=False,  # 统一在所有尺寸应用后执行重构
                save=False,
            )
            applied_results.append(res)
            before_val = res.get("before_mm", {}).get("current", 0.0)
            before_state[dim_name] = before_val

        # 所有尺寸写入完成后，触发统一几何重构
        rebuild_success = True
        if rebuild:
            try:
                get_com_member(model, "ForceRebuild3", False)
            except Exception:
                pass
            rebuild_code = get_com_member(model, "EditRebuild3")
            rebuild_success = bool(rebuild_code)
            if not rebuild_success:
                raise DimensionUpdateError(
                    f"尺寸更新后模型 EditRebuild3 重建失败，可能产生了几何自交或拓扑破损。"
                )

        # 回读更新后的实际值
        for dim_name in updates.keys():
            dim_obj = get_com_member(model, "Parameter", dim_name)
            if dim_obj is not None:
                after_state[dim_name] = _read_dim_value_mm(dim_obj)
            else:
                after_state[dim_name] = updates[dim_name]

        # 检查是否需要落盘保存
        save_success = False
        if save and rebuild_success:
            save_success = bool(save_document(model, doc_path))

        # 成功，丢弃影子备份
        if has_backup and doc_path:
            backup_mgr.discard(doc_path)

        return {
            "status": "success",
            "rebuild_success": rebuild_success,
            "save_success": save_success,
            "modified_count": len(updates),
            "before_values_mm": before_state,
            "after_values_mm": after_state,
            "applied_details": applied_results,
            "architecture": "unified_p1_façade",
        }

    except Exception as exc:
        # 异常自愈回滚分支
        rollback_performed = False
        rollback_message = ""
        if has_backup and doc_path and auto_rollback:
            try:
                # 若模型有文档名，先尝试通过 SolidWorks Application 关闭当前脏文档避免 Windows 独占文件句柄锁冲突
                doc_title = str(get_com_member(model, "GetTitle") or "")
                app = sw
                if app is None:
                    try:
                        from .sw_connect import get_sta_worker
                        app = get_sta_worker().execute(lambda: __import__("win32com.client").client.GetActiveObject("SldWorks.Application"))
                    except Exception:
                        app = None

                if app and doc_title:
                    try:
                        app.CloseDoc(doc_title)
                    except Exception:
                        pass

                backup_mgr.restore(doc_path)
                rollback_performed = True
                rollback_message = f"由于更新失败，已自动从影子备份无损还原文件: {doc_path}"

                # 恢复干净模型后，自动重新在 SolidWorks 中加载该文档
                if app and os.path.exists(doc_path):
                    try:
                        from .sw_connect import open_document
                        open_document(app, doc_path)
                    except Exception:
                        pass
            except Exception as r_err:
                rollback_message = f"回滚影子备份失败: {r_err}"

        raise DimensionUpdateError(
            f"修改尺寸参数失败: {exc}. {rollback_message}",
            details={
                "updates": updates,
                "before_values": before_state,
                "rollback_performed": rollback_performed,
                "error": str(exc),
            },
        ) from exc
