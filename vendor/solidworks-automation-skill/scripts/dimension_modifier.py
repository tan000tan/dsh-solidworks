# -*- coding: utf-8 -*-
"""
vendor/solidworks-automation-skill/scripts/dimension_modifier.py
SolidWorks 尺寸参数就地安全修改与事务回滚执行器 (Dimension Modifier)。

核心职责：
1. 实现对已有草图尺寸与特征参数的真正在线就地修改（严禁通过删除重构假冒修改）；
2. 捕获修改前实际物理状态并建立参数快照；
3. 严格调用 SolidWorks COM SetSystemValue3 进行米制系统值写入；
4. 依托 ModelRebuilder 进行几何重建与健康评估；
5. 遇故障自动触发自愈回滚（参数级快照恢复与文件级影子恢复双保险）。
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

try:
    from .sw_connect import get_com_member, save_document
    from .model_rebuilder import ModelRebuilder, RebuildReport
    from .shadow_backup import ShadowBackupManager
    from .sw_document_data import update_dimension_mm
except ImportError:
    from sw_connect import get_com_member, save_document
    from model_rebuilder import ModelRebuilder, RebuildReport
    from shadow_backup import ShadowBackupManager
    from sw_document_data import update_dimension_mm

logger = logging.getLogger("dimension_modifier")


class ModificationStatus(str):
    """兼顾向后兼容的状态字符串类型。"""
    def __eq__(self, other):
        if not isinstance(other, str):
            return False
        s = str(self)
        o = str(other)
        if s == o:
            return True
        if s in ("SUCCESS", "COMPLETED") and o in ("SUCCESS", "COMPLETED"):
            return True
        if s in ("ROLLBACK_SUCCESS", "ROLLED_BACK") and o in ("ROLLBACK_SUCCESS", "ROLLED_BACK"):
            return True
        return False

    def __hash__(self):
        return hash(str(self))


class ModificationDetail(BaseModel):
    """单个尺寸修改执行详情。"""
    dimension_name: str
    requested_value_mm: float
    before_value_mm: float
    after_value_mm: float
    success: bool
    status_code: int = 0
    error_message: Optional[str] = None


class ModificationResult(BaseModel):
    """全量尺寸修改事务执行报告。"""
    success: bool
    status: str = Field(..., description="SUCCESS, COMPLETED, ROLLBACK_SUCCESS, ROLLBACK_PARTIAL, ROLLBACK_FAILED, FAILED")
    modified_count: int = 0
    details: List[ModificationDetail] = Field(default_factory=list)
    rebuild_report: Optional[RebuildReport] = None
    rollback_occurred: bool = False
    rollback_message: Optional[str] = None
    saved_path: Optional[str] = None
    error_message: Optional[str] = None


class DimensionModifier:
    """参数化尺寸就地修改与事务管理执行器。"""

    def __init__(self, model, auto_rollback: bool = True):
        self.model = model
        self.auto_rollback = auto_rollback
        self.rebuilder = ModelRebuilder(model)

    def modify_single(
        self,
        dimension_name: str,
        value_mm: float,
        save: bool = False,
        doc_path: Optional[str] = None,
    ) -> ModificationResult:
        """快捷执行单个尺寸修改。"""
        return self.modify_batch(
            updates={dimension_name: value_mm},
            save=save,
            doc_path=doc_path,
        )

    def modify_batch(
        self,
        updates: Dict[str, float],
        save: bool = False,
        doc_path: Optional[str] = None,
        min_expected_bodies: int = 1,
    ) -> ModificationResult:
        """
        批量事务性就地修改多个尺寸参数。
        
        参数:
            updates: {尺寸全名: 新数值(mm)}
            save: 成功后是否落盘保存
            doc_path: 文档落盘路径（用于影子备份与落盘保存）
            min_expected_bodies: 最少预期实体数
        """
        if not updates:
            raise ValueError("updates 字典不能为空")

        # 1. 建立修改前快照与参数可编辑性验证
        before_snapshot: Dict[str, float] = {}
        dim_objects: Dict[str, Any] = {}

        for dim_name in updates.keys():
            dim_obj = get_com_member(self.model, "Parameter", dim_name)
            if dim_obj is None:
                return ModificationResult(
                    success=False,
                    status="FAILED",
                    error_message=f"模型中不存在指定名称的尺寸参数: '{dim_name}'",
                )
            
            # 读取当前物理数值
            try:
                curr_sys_val = float(get_com_member(dim_obj, "SystemValue") or 0.0)
                curr_mm = round(curr_sys_val * 1000.0, 4)
            except Exception:
                curr_mm = 0.0

            # 检查驱动状态 (SolidWorks swDimensionDrivenState_e: 1=Driven, 2=Driving)
            try:
                driven_code = int(get_com_member(dim_obj, "DrivenState") or 0)
                is_driven = (driven_code == 1)
                if is_driven:
                    return ModificationResult(
                        success=False,
                        status="FAILED",
                        error_message=f"尺寸 '{dim_name}' 属于从动参考尺寸 (DrivenState=1)，禁止就地写入修改。",
                    )
            except Exception:
                pass

            before_snapshot[dim_name] = curr_mm
            dim_objects[dim_name] = dim_obj

        # 2. 建立文件级影子备份（若提供了有效落盘路径）
        backup_mgr = ShadowBackupManager()
        has_backup = False
        target_path = doc_path or (str(get_com_member(self.model, "GetPathName") or "") if self.model else "")
        if target_path and os.path.exists(target_path) and self.auto_rollback:
            try:
                backup_mgr.capture(target_path)
                has_backup = True
            except Exception as b_err:
                logger.warning(f"无法创建磁盘影子备份: {b_err}")

        # 3. 逐个应用新系统值
        applied_details: List[ModificationDetail] = []
        try:
            for dim_name, new_val in updates.items():
                if new_val <= 0:
                    raise ValueError(f"尺寸 '{dim_name}' 的新数值必须大于 0，当前请求为: {new_val}")

                dim_obj = dim_objects[dim_name]
                val_m = float(new_val) / 1000.0
                
                # swSetValue_CurrentConfig = 1
                status_code = int(get_com_member(dim_obj, "SetSystemValue3", val_m, 1, None) or 0)
                if status_code != 0:
                    raise RuntimeError(f"SetSystemValue3 写入尺寸 '{dim_name}' 失败，返回状态码: {status_code}")

                applied_details.append(
                    ModificationDetail(
                        dimension_name=dim_name,
                        requested_value_mm=new_val,
                        before_value_mm=before_snapshot[dim_name],
                        after_value_mm=new_val,
                        success=True,
                        status_code=status_code,
                    )
                )

            # 4. 触发模型重建并核查几何健康
            rebuild_report = self.rebuilder.rebuild(force_all=True, min_expected_bodies=min_expected_bodies)
            if not rebuild_report.success:
                raise RuntimeError(f"尺寸修改后几何重构失败: {rebuild_report.error_message}")

            # 5. 回读验证更新后真实值
            for detail in applied_details:
                dim_obj = dim_objects[detail.dimension_name]
                try:
                    read_back_m = float(get_com_member(dim_obj, "SystemValue") or 0.0)
                    detail.after_value_mm = round(read_back_m * 1000.0, 4)
                except Exception:
                    pass

            # 6. 落盘保存
            saved_file = None
            if save and target_path:
                save_ok = bool(save_document(self.model, target_path))
                if save_ok:
                    saved_file = target_path

            # 成功完成，废弃影子备份
            if has_backup and target_path:
                backup_mgr.discard(target_path)

            return ModificationResult(
                success=True,
                status=ModificationStatus("SUCCESS"),
                modified_count=len(applied_details),
                details=applied_details,
                rebuild_report=rebuild_report,
                saved_path=saved_file,
            )

        except Exception as exc:
            # 7. 触发自愈回滚：先通过参数快照原位恢复，若失败且有影子文件则还原磁盘
            rollback_msg = []
            rb_status = "ROLLBACK_FAILED"
            recovered_dims = 0
            
            # 第一重恢复：参数逆向还原快照
            try:
                for dim_name, old_val in before_snapshot.items():
                    dim_obj = dim_objects.get(dim_name)
                    if dim_obj is not None:
                        old_m = float(old_val) / 1000.0
                        set_res = get_com_member(dim_obj, "SetSystemValue3", old_m, 1, None)
                        if set_res == 0:
                            recovered_dims += 1
                recovery_rebuild = self.rebuilder.rebuild(force_all=True, min_expected_bodies=min_expected_bodies)
                if recovery_rebuild.success and recovered_dims == len(before_snapshot):
                    rb_status = "ROLLBACK_SUCCESS"
                    rollback_msg.append("已成功通过参数内存快照逆向恢复至修改前几何状态。")
                elif recovered_dims > 0:
                    rb_status = "ROLLBACK_PARTIAL"
                    rollback_msg.append(f"参数快照部分逆向恢复({recovered_dims}/{len(before_snapshot)})，重建报告: {recovery_rebuild.error_message}")
                else:
                    rb_status = "ROLLBACK_FAILED"
                    rollback_msg.append(f"参数快照逆向恢复后重建仍有异常: {recovery_rebuild.error_message}")
            except Exception as p_err:
                rollback_msg.append(f"参数快照恢复异常: {p_err}")

            # 第二重恢复：若参数逆向恢复未完全成功且有物理备份
            if rb_status != "ROLLBACK_SUCCESS" and has_backup and target_path:
                try:
                    backup_mgr.restore(target_path)
                    rb_status = "ROLLBACK_SUCCESS"
                    rollback_msg.append(f"已通过影子副本恢复磁盘原件: {target_path}")
                except Exception as b_err:
                    rollback_msg.append(f"影子文件恢复失败: {b_err}")

            return ModificationResult(
                success=False,
                status=ModificationStatus(rb_status),
                modified_count=0,
                details=applied_details,
                rollback_occurred=True,
                rollback_message="; ".join(rollback_msg),
                error_message=str(exc),
            )
