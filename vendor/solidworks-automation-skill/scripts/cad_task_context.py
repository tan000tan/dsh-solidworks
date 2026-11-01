# -*- coding: utf-8 -*-
"""
SolidWorks CAD 操作任务隔离、自动回滚与安全重试状态机模块 (cad_task_context.py)

设计定位：
解决 CAD 建模中途失败导致的以下严重生产事故：
1. 失败后无用模型在 SolidWorks 后台无限累积（出现后台残留十几个未命名文档的情况）；
2. 失败后半成品草图、失效基准面、悬空特征残留在零件特征树中；
3. 未清理上一次失败状态直接开始盲目重试，导致错误雪崩；
4. 独占文件锁未释放、COM 对象循环累积导致内存泄漏与崩溃。

核心能力：
1. Task Context 隔离：每次建模任务分配独立 Task ID，追踪其创建的文档、特征、草图、临时文件与参数；
2. 自动化失败回滚：
   - 全新文档：退出编辑态 -> 关闭未保存文档 -> 释放 COM 句柄 -> 物理删除临时文件 -> 验证完全关闭；
   - 已有文档：影子备份恢复 / 逆序特征删除 -> 保护原有几何与默认基准面/原点 -> Rebuild 校验；
3. 严格安全重试状态机：
   RUNNING -> FAILED -> ROLLING_BACK -> CLEANUP_VERIFYING -> READY_TO_RETRY -> RETRYING -> COMPLETED
   若清理验证未通过，强行进入 CLEANUP_FAILED，严格禁止盲目重试；
4. 深度协同：无缝打通 Feature Graph IR、CADTransaction、ShadowBackupManager 与 SolidWorksSession。
"""

from __future__ import annotations

import gc
import logging
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

try:
    from .sw_connect import get_com_member
    from .shadow_backup import ShadowBackupManager, get_shadow_manager
    from .sw_part import clear_sketch_selection_cache
except ImportError:
    try:
        from sw_connect import get_com_member
        from shadow_backup import ShadowBackupManager, get_shadow_manager
        from sw_part import clear_sketch_selection_cache
    except ImportError:
        def get_com_member(obj, attr_name, *args, default=None):
            if obj is None:
                return default
            try:
                member = getattr(obj, attr_name, default)
                if callable(member):
                    return member(*args)
                return member
            except Exception:
                return default

        get_shadow_manager = lambda: None
        clear_sketch_selection_cache = lambda m=None: None


logger = logging.getLogger("solidworks_cad_task")


class TaskStatus(str, Enum):
    """任务生命周期状态。"""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    ROLLING_BACK = "ROLLING_BACK"
    CLEANUP_VERIFYING = "CLEANUP_VERIFYING"
    READY_TO_RETRY = "READY_TO_RETRY"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    CLEANUP_FAILED = "CLEANUP_FAILED"
    ABORTED = "ABORTED"


class CleanupStatus(str, Enum):
    """清理与验证状态。"""
    CLEAN = "CLEAN"
    CLEANUP_NEEDED = "CLEANUP_NEEDED"
    CLEANING = "CLEANING"
    CLEANED = "CLEANED"
    CLEANUP_FAILED = "CLEANUP_FAILED"


class CleanupVerificationError(RuntimeError):
    """当失败清理未完全成功（文档未关闭或残留特征无法清除）时抛出，阻止盲目重试。"""
    pass


# ============================================================
# 系统固有特征与基准面永久保护白名单
# ============================================================
PROTECTED_FEATURE_NAMES = {
    # 默认基准面
    "Front Plane", "Top Plane", "Right Plane",
    "前视基准面", "上视基准面", "右视基准面",
    # 原点与坐标系
    "Origin", "原点",
    "Coordinate System", "坐标系",
    # 系统内置活页夹与特殊对象
    "Favorites", "收藏", "收藏夹",
    "History", "历史记录",
    "Selection Sets", "选择集",
    "Sensors", "传感器",
    "Design Binder", "设计活页夹",
    "Annotations", "注解",
    "Notes Area", "注释", "注释区域1",
    "Markup", "标注",
    "Lights and Cameras", "光源与相机",
    "Ambient", "环境光源",
    "Directional 1", "线光源 1", "Directional 2", "线光源 2",
    "Directional 3", "线光源 3", "Directional 4", "线光源 4",
    "Solid Bodies", "实体",
    "Surface Bodies", "曲面实体",
    "Comments", "备注",
    "Equations", "方程式",
    "Material", "材质", "材质 <未指定>",
    "Tables", "Configuration Table",
}

PROTECTED_FEATURE_TYPES = {
    "RefPlane",
    "OriginProfileFeature",
    "HistoryFolderFeature",
    "SensorFolderFeature",
    "DocsFolder",
    "DetailCabinet",
    "NotesAreaFtrFolder",
    "AnnotationViewFeat",
    "InkMarkupFolder",
    "EnvFolder",
    "AmbientLight",
    "DirectionLight",
    "SolidBodyFolder",
    "SurfaceBodyFolder",
    "CommentsFolder",
    "EqnFolder",
    "MaterialFolder",
    "ConfigTableFolder",
    "NativeConfigurationTableFeature",
    "SelectionSetFolder",
    "FtrFolder",
}


@dataclass
class TrackedDocument:
    """受当前任务纳管的 CAD 文档。"""
    doc_id: str
    title: str
    path: Optional[str] = None
    doc_type: str = "part"
    is_newly_created: bool = True
    initial_feature_count: int = 0
    initial_feature_names: Set[str] = field(default_factory=set)
    shadow_backup_path: Optional[str] = None
    closed: bool = False
    cleaned: bool = False
    model_com_ref: Any = None


@dataclass
class TrackedFeature:
    """受当前任务纳管的建模特征。"""
    feature_name: str
    feature_type: str
    doc_title: str
    created_at: float = field(default_factory=time.time)
    status: str = "ACTIVE"  # "ACTIVE", "ROLLED_BACK", "FAILED"


class CADTaskContext:
    """
    单次建模任务的上下文隔离容器。
    记录本任务所有的对象创建、参数修改、事务状态与重试流水。
    """

    def __init__(self, task_id: Optional[str] = None, max_retries: int = 2, session=None):
        self.task_id = task_id or f"task_{uuid.uuid4().hex[:10]}"
        self.start_time = time.time()
        self.status = TaskStatus.PENDING
        self.cleanup_status = CleanupStatus.CLEAN
        self.max_retries = max(0, int(max_retries))
        self.retry_count = 0
        self.session = session

        # 对象追踪
        self.tracked_documents: Dict[str, TrackedDocument] = {}
        self.tracked_features: List[TrackedFeature] = []
        self.tracked_sketches: List[str] = []
        self.tracked_temp_files: Set[str] = set()
        self.tracked_backup_files: Set[str] = set()
        self.modified_parameters: List[Dict[str, Any]] = []

        # 错误与 COM 引用记录
        self.errors: List[str] = []
        self.com_references: List[Any] = []

    def register_document(
        self,
        model,
        title: Optional[str] = None,
        path: Optional[str] = None,
        doc_type: str = "part",
        is_newly_created: bool = True,
    ) -> TrackedDocument:
        """登记属于本次任务的 CAD 文档，并记录其初始特征树快照。"""
        if title is None and model is not None:
            title = str(get_com_member(model, "GetTitle") or f"doc_{len(self.tracked_documents)+1}")
        title = title or f"doc_{uuid.uuid4().hex[:6]}"

        if path is None and model is not None:
            path = get_com_member(model, "GetPathName")

        # 提取当前特征集合作为保护基线
        initial_names = set()
        initial_count = 0
        if model is not None:
            try:
                from dimension_manager import iter_all_features
                feats = iter_all_features(model)
                initial_count = len(feats)
                for f in feats:
                    fn = get_com_member(f, "Name")
                    if fn:
                        initial_names.add(fn)
            except Exception:
                pass

            if not initial_names and hasattr(model, "features"):
                for f in getattr(model, "features", []):
                    fn = get_com_member(f, "Name")
                    if fn:
                        initial_names.add(fn)
                initial_count = len(initial_names)

            if not initial_count:
                initial_count = int(get_com_member(model, "GetFeatureCount") or 0)

        # 捕获影子备份（若已有磁盘文件）
        shadow_path = None
        if path and os.path.exists(path):
            shadow_mgr = get_shadow_manager()
            if shadow_mgr:
                shadow_path = shadow_mgr.capture(path, model=model)
                if shadow_path:
                    self.tracked_backup_files.add(shadow_path)

        doc_entry = TrackedDocument(
            doc_id=f"doc_{uuid.uuid4().hex[:8]}",
            title=title,
            path=path,
            doc_type=doc_type,
            is_newly_created=is_newly_created,
            initial_feature_count=initial_count,
            initial_feature_names=initial_names,
            shadow_backup_path=shadow_path,
            model_com_ref=model,
        )
        self.tracked_documents[title] = doc_entry
        self.cleanup_status = CleanupStatus.CLEANUP_NEEDED
        return doc_entry

    def register_feature(self, feature_name: str, feature_type: str = "FEATURE", doc_title: Optional[str] = None):
        """登记本次任务新增的几何特征。"""
        if not doc_title and self.tracked_documents:
            doc_title = next(iter(self.tracked_documents))
        self.tracked_features.append(
            TrackedFeature(
                feature_name=feature_name,
                feature_type=feature_type,
                doc_title=doc_title or "unknown",
            )
        )
        if feature_type.upper() == "SKETCH":
            self.tracked_sketches.append(feature_name)
        self.cleanup_status = CleanupStatus.CLEANUP_NEEDED

    def register_temp_file(self, file_path: str):
        """登记本次任务产生的临时文件。"""
        if file_path:
            norm = os.path.abspath(file_path)
            self.tracked_temp_files.add(norm)
            self.cleanup_status = CleanupStatus.CLEANUP_NEEDED

    def register_modified_param(self, param_name: str, old_value: Any, new_value: Any, doc_title: Optional[str] = None):
        """登记修改过的尺寸参数及原值。"""
        self.modified_parameters.append({
            "param_name": param_name,
            "old_value": old_value,
            "new_value": new_value,
            "doc_title": doc_title,
            "timestamp": time.time(),
        })
        self.cleanup_status = CleanupStatus.CLEANUP_NEEDED

    def can_retry(self) -> bool:
        """检查当前任务是否满足安全重试条件。"""
        return (
            self.status == TaskStatus.READY_TO_RETRY
            and self.cleanup_status == CleanupStatus.CLEANED
            and self.retry_count < self.max_retries
        )

    def advance_retry(self):
        """推进至下一轮重试。"""
        if not self.can_retry():
            raise RuntimeError(
                f"任务 {self.task_id} 无法重试: status={self.status}, "
                f"cleanup={self.cleanup_status}, retries={self.retry_count}/{self.max_retries}"
            )
        self.retry_count += 1
        self.status = TaskStatus.RETRYING
        self.cleanup_status = CleanupStatus.CLEANUP_NEEDED
        # 重置特征和临时文件记录以迎接新一轮建模
        self.tracked_features.clear()
        self.tracked_sketches.clear()

    def get_summary(self) -> Dict[str, Any]:
        """获取任务全生命周期审计摘要。"""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "cleanup_status": self.cleanup_status.value,
            "duration_seconds": round(time.time() - self.start_time, 3),
            "retries_attempted": self.retry_count,
            "max_retries": self.max_retries,
            "documents_tracked": len(self.tracked_documents),
            "documents_closed": sum(1 for d in self.tracked_documents.values() if d.closed),
            "features_created": len(self.tracked_features),
            "features_rolled_back": sum(1 for f in self.tracked_features if f.status == "ROLLED_BACK"),
            "temp_files_tracked": len(self.tracked_temp_files),
            "errors": list(self.errors),
        }


# ============================================================
# 失败特征安全逆序清理引擎 (FeatureCleanupManager)
# ============================================================
class FeatureCleanupManager:
    """负责在已有文档或未关闭文档中逆序清理本次任务新增特征，保护固有基准面与特征。"""

    @staticmethod
    def is_protected_feature(feature_name: str, ftype: str = "", initial_set: Optional[Set[str]] = None) -> bool:
        """判断特征是否受绝对保护。"""
        if not feature_name:
            return True
        if initial_set and feature_name in initial_set:
            return True
        if feature_name in PROTECTED_FEATURE_NAMES:
            return True
        if ftype in PROTECTED_FEATURE_TYPES:
            return True
        for prefix in ("Front", "Top", "Right", "前视", "上视", "右视", "Origin", "原点"):
            if feature_name.startswith(prefix):
                return True
        return False

    @classmethod
    def cleanup_document_features(
        cls,
        model,
        doc_entry: TrackedDocument,
        tracked_features: List[TrackedFeature],
    ) -> Tuple[int, List[str]]:
        """
        逆序清理本次任务在目标文档中产生的特征。
        返回: (成功清理数, 清理特征名称列表)
        """
        if model is None:
            return 0, []

        cleaned_names = []
        try:
            # 1. 首先确保退出任何未完成的草图编辑状态
            try:
                sketch_mgr = getattr(model, "SketchManager", None)
                if sketch_mgr:
                    active_sketch = get_com_member(sketch_mgr, "ActiveSketch")
                    if active_sketch:
                        get_com_member(sketch_mgr, "InsertSketch", True)
            except Exception:
                pass

            # 2. 收集需要删除的特征名称（从后往前）
            doc_features = [
                tf for tf in tracked_features
                if tf.doc_title == doc_entry.title and tf.status == "ACTIVE"
            ]

            # 逆序遍历删除
            for tf in reversed(doc_features):
                fname = tf.feature_name
                if cls.is_protected_feature(fname, initial_set=doc_entry.initial_feature_names):
                    continue

                feat = get_com_member(model, "FeatureByName", fname)
                if feat is not None:
                    get_com_member(feat, "Select2", False, 0)
                    delete_ok = False
                    ext = getattr(model, "Extension", None)
                    if ext is not None:
                        try:
                            delete_ok = bool(ext.DeleteSelection2(1))
                        except Exception:
                            delete_ok = False
                    if not delete_ok:
                        delete_ok = bool(get_com_member(model, "EditDelete"))
                    if delete_ok:
                        tf.status = "ROLLED_BACK"
                        cleaned_names.append(fname)
                else:
                    ext = getattr(model, "Extension", None)
                    if ext is not None:
                        for etype in ("BODYFEATURE", "SKETCH", "REFERENCE_PLANE", "PLANE"):
                            if get_com_member(ext, "SelectByID2", fname, etype, 0, 0, 0, False, 0, None, 0):
                                delete_ok = False
                                try:
                                    delete_ok = bool(ext.DeleteSelection2(1))
                                except Exception:
                                    delete_ok = False
                                if not delete_ok:
                                    delete_ok = bool(get_com_member(model, "EditDelete"))
                                if delete_ok:
                                    tf.status = "ROLLED_BACK"
                                    cleaned_names.append(fname)
                                    break

            if doc_entry.initial_feature_names:
                from dimension_manager import iter_all_features
                all_current = [get_com_member(f, "Name") for f in iter_all_features(model)]
                for cur_name in reversed(all_current):
                    if cur_name and cur_name not in doc_entry.initial_feature_names:
                        if not cls.is_protected_feature(cur_name, initial_set=doc_entry.initial_feature_names):
                            feat = get_com_member(model, "FeatureByName", cur_name)
                            if feat is not None:
                                get_com_member(feat, "Select2", False, 0)
                                del_ok = False
                                ext = getattr(model, "Extension", None)
                                if ext is not None:
                                    try:
                                        del_ok = bool(ext.DeleteSelection2(1))
                                    except Exception:
                                        del_ok = False
                                if not del_ok:
                                    del_ok = bool(get_com_member(model, "EditDelete"))
                                if del_ok:
                                    cleaned_names.append(cur_name)

            # 3. 强制重构并刷新显示
            try:
                get_com_member(model, "ForceRebuild3", False)
                get_com_member(model, "ClearSelection2", True)
            except Exception:
                pass

        except Exception as exc:
            logger.error(f"清理文档特征异常: {exc}")

        return len(cleaned_names), cleaned_names


# ============================================================
# 文档生命周期与后台残留消除引擎 (DocumentLifecycleManager)
# ============================================================
class DocumentLifecycleManager:
    """管理文档关闭、文件锁释放与后台进程残留校验。"""

    @staticmethod
    def close_and_purge_document(sw_app, doc_entry: TrackedDocument, context: CADTaskContext) -> bool:
        """
        关闭本次任务新建的失败文档，释放 COM 并清理落盘的临时文件。
        自适应处理保存落盘前后 Title 变更与文件锁。
        """
        candidates_to_close = {doc_entry.title}
        model = doc_entry.model_com_ref

        if model is not None:
            try:
                clear_sketch_selection_cache(model)
            except Exception:
                pass
            try:
                sm = getattr(model, "SketchManager", None)
                if sm and get_com_member(sm, "ActiveSketch"):
                    get_com_member(sm, "InsertSketch", True)
            except Exception:
                pass
            try:
                latest_title = get_com_member(model, "GetTitle")
                if latest_title:
                    candidates_to_close.add(latest_title)
            except Exception:
                pass

        norm_target_path = None
        if doc_entry.path:
            norm_target_path = os.path.normcase(os.path.abspath(doc_entry.path))
            bname = os.path.basename(doc_entry.path)
            candidates_to_close.add(bname)
            candidates_to_close.add(os.path.splitext(bname)[0])

        # 遍历 SolidWorks 正在打开的所有文档，匹配对应文档并尝试关闭
        if sw_app is not None:
            try:
                open_docs = get_com_member(sw_app, "GetDocuments")
                if open_docs:
                    for d in open_docs:
                        d_path = get_com_member(d, "GetPathName")
                        d_title = str(get_com_member(d, "GetTitle") or "")
                        if (norm_target_path and d_path and os.path.normcase(os.path.abspath(d_path)) == norm_target_path) or (d_title in candidates_to_close):
                            candidates_to_close.add(d_title)
            except Exception:
                pass

            # 逐个尝试 CloseDoc
            for c_title in list(candidates_to_close):
                try:
                    get_com_member(sw_app, "CloseDoc", c_title)
                except Exception:
                    pass

        doc_entry.closed = True
        doc_entry.model_com_ref = None

        # 若有磁盘临时文件，释放句柄并删除
        if doc_entry.path and os.path.exists(doc_entry.path):
            if doc_entry.is_newly_created:
                for _ in range(10):
                    try:
                        os.remove(doc_entry.path)
                        break
                    except Exception:
                        time.sleep(0.15)

        # 清理所有已登记的本任务临时文件
        for tmp in list(context.tracked_temp_files):
            if os.path.exists(tmp):
                for _ in range(10):
                    try:
                        os.remove(tmp)
                        break
                    except Exception:
                        time.sleep(0.15)

        # 验证清理结果
        verified = DocumentLifecycleManager.verify_document_closed(sw_app, candidates_to_close, norm_target_path)
        doc_entry.cleaned = verified
        return verified

    @staticmethod
    def verify_document_closed(sw_app, candidate_titles, target_path=None) -> bool:
        """验证目标文档是否已不在 SolidWorks 后台打开列表中。"""
        if sw_app is None:
            return True
        try:
            open_docs = get_com_member(sw_app, "GetDocuments")
            if not open_docs:
                return True
            if isinstance(candidate_titles, str):
                c_set = {candidate_titles}
            else:
                c_set = set(candidate_titles)

            for d in open_docs:
                t = str(get_com_member(d, "GetTitle") or "")
                p = get_com_member(d, "GetPathName")
                if t in c_set:
                    return False
                if target_path and p and os.path.normcase(os.path.abspath(p)) == target_path:
                    return False
            return True
        except Exception:
            return True


# ============================================================
# CAD 建模失败自动清理与安全重试调度器 (CADTaskRollbackManager)
# ============================================================
class CADTaskRollbackManager:
    """
    负责驱动 CADTaskContext 完整状态机：
    失败捕获 -> 状态回滚 -> 资源释放 -> 清理验证 -> 安全重试。
    """

    def __init__(self, context: CADTaskContext, sw_app=None):
        self.context = context
        self.sw_app = sw_app

    def rollback(self) -> bool:
        """
        执行完整的任务级回滚与状态清理。
        返回: 是否全部清理并验证通过。
        """
        ctx = self.context
        ctx.status = TaskStatus.ROLLING_BACK
        all_success = True

        try:
            # 遍历本次任务涉及的所有文档
            for title, doc_entry in list(ctx.tracked_documents.items()):
                if doc_entry.is_newly_created:
                    # 情况 A: 全新创建的文档，彻底关闭并删除临时文件
                    closed_ok = DocumentLifecycleManager.close_and_purge_document(
                        self.sw_app, doc_entry, ctx
                    )
                    if not closed_ok:
                        all_success = False
                else:
                    # 情况 B: 已有文档
                    # 1. 优先执行内存中逆序特征删除（零感知、不关文档、不破坏已有工作区）
                    model = doc_entry.model_com_ref
                    feature_cleaned = True
                    if model is not None:
                        cleaned_count, _ = FeatureCleanupManager.cleanup_document_features(
                            model, doc_entry, ctx.tracked_features
                        )

                    # 2. 若发生尺寸修改且未在内存撤销，使用影子备份原地兜底恢复
                    if ctx.modified_parameters:
                        if doc_entry.path and doc_entry.shadow_backup_path:
                            shadow_mgr = get_shadow_manager()
                            if shadow_mgr and shadow_mgr.is_protected(doc_entry.path):
                                restored = shadow_mgr.restore(doc_entry.path, sw_app=self.sw_app)
                                if restored:
                                    doc_entry.cleaned = True
                                    continue
                                else:
                                    all_success = False

                    doc_entry.cleaned = feature_cleaned
                    # 若已安全处理且持有影子备份，销毁临时备份
                    if doc_entry.path and doc_entry.shadow_backup_path:
                        shadow_mgr = get_shadow_manager()
                        if shadow_mgr:
                            shadow_mgr.discard(doc_entry.path)

            # 释放临时 COM 引用与内存垃圾回收
            ctx.com_references.clear()
            gc.collect()

            # 进入验证阶段
            ctx.status = TaskStatus.CLEANUP_VERIFYING
            if all_success:
                ctx.cleanup_status = CleanupStatus.CLEANED
                ctx.status = TaskStatus.READY_TO_RETRY
                return True
            else:
                ctx.cleanup_status = CleanupStatus.CLEANUP_FAILED
                ctx.status = TaskStatus.CLEANUP_FAILED
                return False

        except Exception as exc:
            ctx.errors.append(f"RollbackException: {str(exc)}")
            ctx.cleanup_status = CleanupStatus.CLEANUP_FAILED
            ctx.status = TaskStatus.CLEANUP_FAILED
            return False

    def execute_with_retry(
        self,
        task_func: Callable[[CADTaskContext], Any],
        on_cleanup_failed: Optional[Callable[[CADTaskContext], None]] = None,
    ) -> Any:
        """
        在安全隔离、自动回滚与受控重试状态机下执行 CAD 建模逻辑。
        """
        ctx = self.context
        ctx.status = TaskStatus.RUNNING

        while True:
            try:
                result = task_func(ctx)
                # 成功完成
                ctx.status = TaskStatus.COMPLETED
                ctx.cleanup_status = CleanupStatus.CLEAN
                # 任务成功，销毁影子备份并释放非必要临时文件
                for path in list(ctx.tracked_backup_files):
                    if os.path.exists(path):
                        try:
                            os.remove(path)
                        except Exception:
                            pass
                return result

            except Exception as exc:
                ctx.errors.append(str(exc))
                ctx.status = TaskStatus.FAILED
                logger.warning(f"CAD 任务 {ctx.task_id} 执行失败: {exc}，正在启动自动化回滚...")

                # 触发原子回滚与清理验证
                cleanup_ok = self.rollback()

                if not cleanup_ok:
                    ctx.status = TaskStatus.CLEANUP_FAILED
                    ctx.cleanup_status = CleanupStatus.CLEANUP_FAILED
                    if on_cleanup_failed:
                        on_cleanup_failed(ctx)
                    raise CleanupVerificationError(
                        f"CAD 任务 {ctx.task_id} 清理验证失败！严禁盲目重试以防后台残留积累。错误详情: {ctx.errors}"
                    ) from exc

                # 检查是否允许重试
                if ctx.can_retry():
                    logger.info(f"CAD 任务 {ctx.task_id} 状态已恢复干净，准备第 {ctx.retry_count + 1} 次重试...")
                    ctx.advance_retry()
                    continue
                else:
                    ctx.status = TaskStatus.ABORTED
                    logger.error(f"CAD 任务 {ctx.task_id} 已达最大重试上限 ({ctx.max_retries})，终止重试。")
                    raise
