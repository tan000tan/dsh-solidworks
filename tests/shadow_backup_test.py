# -*- coding: utf-8 -*-
"""
tests/shadow_backup_test.py

针对 TASK-02: Shadow Backup 影子备份与恢复机制的完整自动化单元测试。
覆盖快照抓取、销毁、异常覆盖恢复、以及 CADTransaction 异常回滚联动。
"""

import os
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "vendor", "solidworks-automation-skill", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from shadow_backup import ShadowBackupManager, shadow_backup_scope
from sw_session import CADSessionState, CADTransaction


class MockModelDoc:
    def __init__(self, path=None, title="Part1", feature_count=3):
        self._path = path
        self._title = title
        self._feature_count = feature_count
        self.undone_count = 0

    def GetPathName(self):
        return self._path

    def GetTitle(self):
        return self._title

    def GetFeatureCount(self):
        return self._feature_count

    def EditUndo(self):
        self.undone_count += 1
        self._feature_count -= 1

    def ClearSelection2(self, clear_all):
        pass

    def EditRebuild3(self):
        pass


class MockSolidWorksSession:
    def __init__(self, active_doc=None):
        self.active_doc = active_doc
        self.state = CADSessionState.CONNECTED_IDLE
        self.sw = None


class TestShadowBackup(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="cad_shadow_test_")
        self.backup_dir = os.path.join(self.test_dir, "backups")
        self.mgr = ShadowBackupManager(backup_dir=self.backup_dir)

        # 创建一个模拟的真实 CAD 零件文件
        self.original_file = os.path.join(self.test_dir, "base_part.sldprt")
        with open(self.original_file, "w", encoding="utf-8") as f:
            f.write("ORIGINAL_CAD_GEOMETRY_V1")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_capture_and_discard(self):
        """测试正常事务：抓取影子备份，提交后安全销毁。"""
        backup_path = self.mgr.capture(self.original_file)
        self.assertIsNotNone(backup_path)
        self.assertTrue(os.path.exists(backup_path))
        self.assertTrue(self.mgr.is_protected(self.original_file))

        # 模拟事务正常提交
        discarded = self.mgr.discard(self.original_file)
        self.assertTrue(discarded)
        self.assertFalse(os.path.exists(backup_path))
        self.assertFalse(self.mgr.is_protected(self.original_file))

    def test_capture_and_restore_on_modification(self):
        """测试异常事务：模拟文件被意外污染，触发 restore 原地无损还原。"""
        backup_path = self.mgr.capture(self.original_file)
        self.assertIsNotNone(backup_path)

        # 模拟建模过程产生了错误的脏修改
        with open(self.original_file, "w", encoding="utf-8") as f:
            f.write("CORRUPTED_GEOMETRY_V2")

        with open(self.original_file, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "CORRUPTED_GEOMETRY_V2")

        # 模拟事务失败，触发回滚恢复
        restored = self.mgr.restore(self.original_file)
        self.assertTrue(restored)

        # 验证原文件已被 100% 还原为 V1 内容
        with open(self.original_file, "r", encoding="utf-8") as f:
            restored_content = f.read()
        self.assertEqual(restored_content, "ORIGINAL_CAD_GEOMETRY_V1")

        # 备份文件已被清理
        self.assertFalse(os.path.exists(backup_path))
        self.assertFalse(self.mgr.is_protected(self.original_file))

    def test_nonexistent_and_uncreated_paths(self):
        """测试对于尚未落盘的新建文档，影子管理器优雅返回 None 不报错。"""
        res = self.mgr.capture("C:\\nonexistent\\dir\\test.sldprt")
        self.assertIsNone(res)
        self.assertFalse(self.mgr.restore("C:\\nonexistent\\dir\\test.sldprt"))
        self.assertFalse(self.mgr.discard("C:\\nonexistent\\dir\\test.sldprt"))

    def test_cad_transaction_integration_success(self):
        """测试 CADTransaction 正常提交路径：影子备份被自动销毁。"""
        model = MockModelDoc(path=self.original_file, feature_count=3)
        session = MockSolidWorksSession(active_doc=model)

        with CADTransaction(session, model=model, enable_shadow_backup=True) as tx:
            # 模拟修改
            with open(self.original_file, "w", encoding="utf-8") as f:
                f.write("MODIFIED_SUCCESS_GEOMETRY")
            tx.commit()

        self.assertEqual(session.state, CADSessionState.CONNECTED_IDLE)
        # 修改被保留
        with open(self.original_file, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "MODIFIED_SUCCESS_GEOMETRY")

    def test_cad_transaction_integration_rollback(self):
        """测试 CADTransaction 发生异常时：自动触发影子还原并将状态置为 ERROR。"""
        model = MockModelDoc(path=self.original_file, feature_count=3)
        session = MockSolidWorksSession(active_doc=model)

        with self.assertRaises(RuntimeError):
            with CADTransaction(session, model=model, enable_shadow_backup=True):
                # 模拟修改后发生错误
                with open(self.original_file, "w", encoding="utf-8") as f:
                    f.write("DIRTY_GEOMETRY_TO_BE_REVERTED")
                raise RuntimeError("Simulated CAD Modeling Failure!")

        # 验证状态机被正确置为 ERROR
        self.assertEqual(session.state, CADSessionState.ERROR)
        # 验证文件被 100% 影子还原回 V1
        with open(self.original_file, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "ORIGINAL_CAD_GEOMETRY_V1")


if __name__ == "__main__":
    unittest.main()
