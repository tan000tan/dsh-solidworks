# -*- coding: utf-8 -*-
"""
SolidWorks 影子副本备份与原子恢复管理器 (Shadow Backup Manager)

为解决 CADTransaction 仅依赖内存 EditUndo 导致的以下问题：
1. 参数/尺寸修改不会增加 FeatureCount，EditUndo 无法触发与撤销；
2. 复杂多步操作失败时，SolidWorks 内部 Undo 栈可能断裂或残留半成品；
3. 循环 Undo 可能向前误伤用户此前手动建立的几何特征。

机制：
- 事务开始前自动抓取活动文档磁盘文件的物理只读影子副本；
- 事务异常退出且未 commit 时，自动关闭脏文档并以影子副本原地覆盖还原；
- 事务成功 commit 时，安全销毁影子副本，零存储开销。
"""

import os
import shutil
import tempfile
import time
import uuid
from typing import Dict, Optional


class ShadowBackupManager:
    """管理 CAD 文档的物理影子快照与故障自动回滚。"""

    def __init__(self, backup_dir: Optional[str] = None):
        if backup_dir:
            self.backup_dir = os.path.abspath(backup_dir)
        else:
            self.backup_dir = os.path.join(tempfile.gettempdir(), "dsh_cad_shadow_backups")
        os.makedirs(self.backup_dir, exist_ok=True)
        # 记录映射：original_path -> backup_path
        self._active_backups: Dict[str, str] = {}

    def capture(self, doc_path: str, model=None) -> Optional[str]:
        """
        为指定 CAD 文档创建只读物理影子快照。

        参数:
            doc_path: 文档完整物理路径
            model: IModelDoc2 对象（可选，若提供且文档已修改但未落盘，可尝试 SaveCopyAs）

        返回:
            备份文件路径，若文档尚未保存到磁盘则返回 None
        """
        if not doc_path or not isinstance(doc_path, str):
            return None
        doc_path = os.path.abspath(doc_path)
        if not os.path.exists(doc_path) or not os.path.isfile(doc_path):
            return None

        try:
            filename = os.path.basename(doc_path)
            token = uuid.uuid4().hex[:8]
            timestamp = int(time.time() * 1000)
            backup_filename = f"shadow_{timestamp}_{token}_{filename}.bak"
            backup_path = os.path.join(self.backup_dir, backup_filename)

            # 复制磁盘文件并保留元数据
            shutil.copy2(doc_path, backup_path)
            self._active_backups[doc_path] = backup_path
            return backup_path
        except Exception:
            return None

    def restore(self, doc_path: str, sw_app=None, reopen: bool = True) -> bool:
        """
        将目标文档从最近的影子快照中原地无损还原。

        参数:
            doc_path: 目标文档物理路径
            sw_app: ISldWorks COM 对象（可选，若提供则在覆盖前先关闭可能被独占的文档，并在覆盖后重新打开）
            reopen: 还原后是否重新在 SolidWorks 中加载该文档

        返回:
            bool 是否恢复成功
        """
        if not doc_path or not isinstance(doc_path, str):
            return False
        doc_path = os.path.abspath(doc_path)
        backup_path = self._active_backups.get(doc_path)
        if not backup_path or not os.path.exists(backup_path):
            return False

        try:
            doc_title = os.path.basename(doc_path)
            # 1. 若提供了 sw_app，安全关闭当前文档以解除文件独占锁
            if sw_app is not None:
                try:
                    # 尝试通过 Title 关闭文档，不保存更改 (Save=False)
                    sw_app.CloseDoc(doc_title)
                except Exception:
                    pass

            # 2. 原地覆盖恢复
            shutil.copy2(backup_path, doc_path)

            # 3. 若需要，重新在 SolidWorks 中打开恢复后的干净文档
            if sw_app is not None and reopen:
                try:
                    from scripts.sw_connect import open_document
                    open_document(sw_app, doc_path, silent=False)
                except Exception:
                    pass

            # 4. 清理备份文件
            try:
                os.remove(backup_path)
            except Exception:
                pass
            self._active_backups.pop(doc_path, None)
            return True
        except Exception:
            return False

    def discard(self, doc_path: str) -> bool:
        """
        事务成功提交，安全销毁影子备份。
        """
        if not doc_path or not isinstance(doc_path, str):
            return False
        doc_path = os.path.abspath(doc_path)
        backup_path = self._active_backups.pop(doc_path, None)
        if backup_path and os.path.exists(backup_path):
            try:
                os.remove(backup_path)
                return True
            except Exception:
                return False
        return False

    def is_protected(self, doc_path: str) -> bool:
        """检查指定文档当前是否有活跃的影子备份。"""
        if not doc_path:
            return False
        doc_path = os.path.abspath(doc_path)
        return doc_path in self._active_backups

    def cleanup_all(self) -> None:
        """清理所有未决备份。"""
        for doc_path, backup_path in list(self._active_backups.items()):
            if backup_path and os.path.exists(backup_path):
                try:
                    os.remove(backup_path)
                except Exception:
                    pass
        self._active_backups.clear()


_GLOBAL_SHADOW_MANAGER: Optional[ShadowBackupManager] = None


def get_shadow_manager() -> ShadowBackupManager:
    """获取全局影子备份管理器单例。"""
    global _GLOBAL_SHADOW_MANAGER
    if _GLOBAL_SHADOW_MANAGER is None:
        _GLOBAL_SHADOW_MANAGER = ShadowBackupManager()
    return _GLOBAL_SHADOW_MANAGER


class shadow_backup_scope:
    """独立影子备份上下文管理器。"""

    def __init__(self, doc_path: str, sw_app=None, manager: Optional[ShadowBackupManager] = None):
        self.doc_path = doc_path
        self.sw_app = sw_app
        self.manager = manager or get_shadow_manager()
        self.committed = False

    def commit(self):
        self.committed = True

    def __enter__(self):
        if self.doc_path:
            self.manager.capture(self.doc_path)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None or not self.committed:
            if self.doc_path:
                self.manager.restore(self.doc_path, sw_app=self.sw_app)
        else:
            if self.doc_path:
                self.manager.discard(self.doc_path)
        return False
