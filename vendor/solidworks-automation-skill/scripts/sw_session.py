"""
SolidWorks 友好会话 API

本模块在底层 COM helper 之上提供更顺手的门面接口，适合脚本和 AI 代理快速组合
“打开/新建/保存/导出/关闭”等常见流程。底层函数仍保留在 sw_connect.py、
sw_part.py、sw_export.py 等模块中，便于精细控制。
"""
from pathlib import Path
import os

try:
    from .sw_connect import close_owned_solidworks, connect_solidworks, get_com_member, new_document, open_document, save_document
    from .sw_export import export_to_dxf, export_to_iges, export_to_pdf, export_to_stl, export_to_step
    from .shadow_backup import get_shadow_manager
    from .cad_task_context import CADTaskContext, CADTaskRollbackManager, FeatureCleanupManager, DocumentLifecycleManager
except ImportError:
    from sw_connect import close_owned_solidworks, connect_solidworks, get_com_member, new_document, open_document, save_document
    from sw_export import export_to_dxf, export_to_iges, export_to_pdf, export_to_stl, export_to_step
    try:
        from shadow_backup import get_shadow_manager
    except ImportError:
        get_shadow_manager = lambda: None
    try:
        from cad_task_context import CADTaskContext, CADTaskRollbackManager, FeatureCleanupManager, DocumentLifecycleManager
    except ImportError:
        CADTaskContext = None
        CADTaskRollbackManager = None
        FeatureCleanupManager = None
        DocumentLifecycleManager = None
    from sw_connect import close_owned_solidworks, connect_solidworks, get_com_member, new_document, open_document, save_document
    from sw_export import export_to_dxf, export_to_iges, export_to_pdf, export_to_stl, export_to_step


EXPORTERS = {
    ".step": export_to_step,
    ".stp": export_to_step,
    ".stl": export_to_stl,
    ".iges": export_to_iges,
    ".igs": export_to_iges,
    ".pdf": export_to_pdf,
    ".dxf": export_to_dxf,
    ".dwg": export_to_dxf,
}


class CADSessionState:
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED_IDLE = "CONNECTED_IDLE"
    EXECUTING = "EXECUTING"
    WAITING_USER = "WAITING_USER"
    ERROR = "ERROR"
    RECOVERING = "RECOVERING"


def apply_ui_suppression(sw):
    """
    配置 SolidWorks 用户偏好设置，抑制阻断脚本执行的非必要模态弹窗与调试器中断。
    """
    if not sw:
        return
    try:
        # swStopDebuggingOnErrors (11): COM 或宏异常时停止弹出 VBA 调试器中断自动化
        sw.SetUserPreferenceToggle(11, True)
    except Exception:
        pass
    try:
        # swDisplayPreReleaseNotification (14): 禁用预发布版本提示弹窗
        sw.SetUserPreferenceToggle(14, False)
    except Exception:
        pass


class CADTransaction:
    """
    SolidWorks 几何建模事务上下文管理器。

    核心保证：
    1. 快照捕获：进入时抓取物理影子快照（若文档已有落盘路径），并记录当前特征计数（FeatureCount）。
    2. 性能与防闪烁：执行期间可选择性冻结特征树刷新（FeatureManager.EnableFeatureTree = False）。
    3. 异常回滚：若事务内部发生异常未 commit，优先采用影子快照文件级秒级还原；无路径时循环 EditUndo。
    4. 提交清理：正常提交时销毁影子快照；在 finally 块中保证特征树重新启用与选择集清空。
    """

    def __init__(self, session, model=None, name="CADTransaction", auto_rebuild=True, freeze_ui=True, enable_shadow_backup=True, task_context=None):
        self.session = session
        self.model = model
        self.name = name
        self.auto_rebuild = auto_rebuild
        self.freeze_ui = freeze_ui
        self.enable_shadow_backup = enable_shadow_backup
        self.task_context = task_context or (getattr(session, "active_task_context", None) if session else None)
        self.committed = False
        self.initial_feature_count = 0
        self.initial_doc_title = None
        self.doc_path = None
        self.shadow_mgr = get_shadow_manager() if enable_shadow_backup else None

    def __enter__(self):
        if self.model is None and self.session:
            self.model = self.session.active_doc
        if self.model:
            try:
                self.initial_doc_title = get_com_member(self.model, "GetTitle")
                self.initial_feature_count = int(get_com_member(self.model, "GetFeatureCount") or 0)
                self.doc_path = get_com_member(self.model, "GetPathName")
                if self.doc_path and self.shadow_mgr:
                    self.shadow_mgr.capture(self.doc_path, model=self.model)
            except Exception:
                pass
            if self.freeze_ui:
                try:
                    feat_mgr = getattr(self.model, "FeatureManager", None)
                    if feat_mgr and hasattr(feat_mgr, "EnableFeatureTree"):
                        feat_mgr.EnableFeatureTree = False
                except Exception:
                    pass
        if self.session:
            self.session.state = CADSessionState.EXECUTING
        return self

    def commit(self):
        self.committed = True
        if self.doc_path and self.shadow_mgr:
            try:
                self.shadow_mgr.discard(self.doc_path)
            except Exception:
                pass

    def rollback(self):
        """回滚本事务期间产生的新特征、修改或未命名脏文档。优先影子还原，其次 EditUndo。"""
        if not self.model:
            return

        # 1. 优先尝试文件级影子快照还原（解决尺寸修改不增减特征数导致无法 Undo 的缺陷）
        if self.doc_path and self.shadow_mgr and self.shadow_mgr.is_protected(self.doc_path):
            try:
                sw_app = getattr(self.session, "sw", None)
                if self.shadow_mgr.restore(self.doc_path, sw_app=sw_app):
                    return
            except Exception:
                pass

        # 2. 次级回退：特征树差值循环 EditUndo
        try:
            curr_count = int(get_com_member(self.model, "GetFeatureCount") or 0)
            diff = curr_count - self.initial_feature_count
            if diff > 0:
                for _ in range(diff):
                    try:
                        self.model.EditUndo()
                    except Exception:
                        break
        except Exception:
            pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None and not self.committed:
                self.rollback()
                if self.session:
                    self.session.state = CADSessionState.ERROR
            else:
                if self.committed and self.auto_rebuild and self.model:
                    try:
                        self.model.EditRebuild3()
                    except Exception:
                        pass
                if self.session:
                    self.session.state = CADSessionState.CONNECTED_IDLE
        finally:
            if self.model and self.freeze_ui:
                try:
                    feat_mgr = getattr(self.model, "FeatureManager", None)
                    if feat_mgr and hasattr(feat_mgr, "EnableFeatureTree"):
                        feat_mgr.EnableFeatureTree = True
                except Exception:
                    pass
            if self.model:
                try:
                    self.model.ClearSelection2(True)
                except Exception:
                    pass
        return False


class SolidWorksSession:
    """
    SolidWorks 自动化会话。

    示例:
        session = SolidWorksSession()
        model = session.new_part()
        session.save(model, r"C:\\temp\\part.sldprt")
        session.export(model, r"C:\\temp\\part.step")
    """

    def __init__(self, version=None, wait_seconds=5, visible=True, *, max_documents=8):
        """
        初始化并连接 SolidWorks。

        参数:
            version: SolidWorks 年份，当前验收目标为 2026；None 表示自动连接默认 ProgID。
            wait_seconds: 新启动实例后的等待秒数。
            visible: 新启动实例是否显示窗口。
        """
        self.state = CADSessionState.CONNECTING
        self.sw, self.model, self.connection_info = connect_solidworks(
            version=version,
            wait_seconds=wait_seconds,
            visible=visible,
            return_metadata=True,
        )
        self.max_documents = int(max_documents)
        if self.max_documents < 1:
            raise ValueError("文档预算必须大于零")
        self._owned_documents = []
        apply_ui_suppression(self.sw)
        self.state = CADSessionState.CONNECTED_IDLE

    @property
    def is_modal_dialog_active(self):
        """检测 SolidWorks 是否有活动的阻塞式模态对话框。"""
        try:
            return bool(get_com_member(self.sw, "CommandInProgress"))
        except Exception:
            return False

    def transaction(self, name="CADTransaction", model=None, auto_rebuild=True, freeze_ui=True):
        """返回受控 CADTransaction 上下文管理器。"""
        return CADTransaction(self, model=model or self.model, name=name, auto_rebuild=auto_rebuild, freeze_ui=freeze_ui)

    def __enter__(self):
        """@brief 进入受控会话，自动清理仅针对本轮登记的文档。"""
        return self

    def __exit__(self, *_):
        """@brief 结束时清理自有文档；共享实例与用户文档保持打开。"""
        self.close_owned_documents()
        self.quit_owned_instance()

    def _documents(self):
        """@brief 读取当前文档，读取失败不得猜测没有用户文档。"""
        return list(get_com_member(self.sw, "GetDocuments") or [])

    def _remember(self, model):
        """@brief 仅登记本轮真正创建或新打开的文档对象。"""
        if model is not None and not any(item is model for item in self._owned_documents):
            self._owned_documents.append(model)
        return model

    def close_owned_documents(self):
        """@brief 清理本轮文档；失效代理不按旧标题猜测关闭别的文档。"""
        for model in list(reversed(self._owned_documents)):
            try:
                self.close(model=model)
            except Exception:
                # 依赖文档可能已被 SolidWorks 卸载；禁止重用陈旧标题。
                pass
        self._owned_documents.clear()

    @property
    def active_doc(self):
        """返回当前活动文档并同步到 session.model。"""
        self.model = self.sw.ActiveDoc
        return self.model

    def new(self, doc_type="part", template_path=None):
        """
        新建文档。

        参数:
            doc_type: "part"、"assembly"、"drawing" 或常见扩展名。
            template_path: 指定模板路径；None 表示自动查找模板。
        """
        self.model = new_document(self.sw, doc_type=doc_type, template_path=template_path, max_documents=self.max_documents)
        self._remember(self.model)
        return self.model

    def new_part(self, template_path=None):
        """新建零件文档。"""
        return self.new("part", template_path=template_path)

    def new_assembly(self, template_path=None):
        """新建装配体文档。"""
        return self.new("assembly", template_path=template_path)

    def new_drawing(self, template_path=None):
        """新建工程图文档。"""
        return self.new("drawing", template_path=template_path)

    def open(self, file_path, read_only=False, silent=False, raise_on_error=True):
        """
        打开文档。

        参数:
            file_path: SolidWorks 文件或中间格式文件路径。
            read_only: 是否只读打开。
            silent: 是否静默打开。
            raise_on_error: 打开失败时是否抛出异常。
        """
        before = {os.path.normcase(str(get_com_member(doc, "GetPathName") or "")) for doc in self._documents()}
        requested = os.path.normcase(os.path.abspath(os.path.expandvars(str(file_path))))
        if requested not in before and len(self._documents()) >= self.max_documents:
            raise RuntimeError("打开文档数已达会话预算")
        self.model = open_document(
            self.sw,
            file_path,
            read_only=read_only,
            silent=silent,
            raise_on_error=raise_on_error,
        )
        if requested not in before:
            self._remember(self.model)
        return self.model

    def save(self, model=None, file_path=None):
        """
        保存文档。

        参数:
            model: 指定文档；None 表示当前活动文档。
            file_path: 另存为路径；None 表示保存到当前位置。
        """
        model = model if model is not None else self.model
        if model is None:
            raise RuntimeError("当前没有可保存的活动文档")
        return save_document(model, file_path=file_path)

    def export(self, model=None, output_path=None, format_ext=None, **kwargs):
        """
        按输出扩展名导出文档。

        参数:
            model: 指定文档；None 表示当前活动文档。
            output_path: 输出文件路径。
            format_ext: 显式格式扩展名；None 表示从 output_path 推断。
            **kwargs: 传给具体导出函数的附加参数，例如 STL quality。
        """
        model = model if model is not None else self.model
        if model is None:
            raise RuntimeError("当前没有可导出的活动文档")
        if not output_path:
            raise ValueError("必须提供 output_path")

        output = Path(os.path.expandvars(str(output_path))).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        ext = (format_ext or output.suffix).lower()
        if not ext.startswith("."):
            ext = f".{ext}"

        exporter = EXPORTERS.get(ext)
        if exporter is None:
            raise ValueError(f"暂不支持导出格式: {ext}")
        return exporter(model, str(output), **kwargs)

    def close(self, model=None, title=None):
        """
        关闭文档。

        参数:
            model: 指定文档；None 表示按 title 或当前活动文档关闭。
            title: 文档标题；适合关闭已知标题的文档。
        """
        if title is None:
            model = model if model is not None else self.model
            if model is None:
                return False
            title = get_com_member(model, "GetTitle")
        is_current_model = False
        if self.model:
            try:
                is_current_model = get_com_member(self.model, "GetTitle") == title
            except Exception:
                is_current_model = True
        if model is not None:
            try:
                from .sw_part import clear_sketch_selection_cache
            except ImportError:
                from sw_part import clear_sketch_selection_cache
            clear_sketch_selection_cache(model)
        self.sw.CloseDoc(title)
        self._owned_documents = [item for item in self._owned_documents if item is not model]
        if is_current_model:
            self.model = self.sw.ActiveDoc
        return True

    def quit_owned_instance(self):
        """退出本会话启动的实例；附着到用户实例时不执行任何关闭操作。"""
        if self._documents():
            return False
        return close_owned_solidworks(
            self.sw,
            bool(self.connection_info.get("started_by_cad_studio")),
            self.connection_info.get("process_id"),
        )


def session(version=None, wait_seconds=5, visible=True):
    """
    创建 SolidWorksSession 的便捷函数。

    参数同 SolidWorksSession。
    """
    return SolidWorksSession(version=version, wait_seconds=wait_seconds, visible=visible)
