# -*- coding: utf-8 -*-
"""
tests/window_recovery_test.py

针对 TASK-03: 修复 solidworks_recover 窗口误关闭风险与白名单安全识别的完整单元测试。
"""

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MCP_SERVER_DIR = os.path.join(REPO_ROOT, "vendor", "solidworks-automation-skill", "mcp-server")
if MCP_SERVER_DIR not in sys.path:
    sys.path.insert(0, MCP_SERVER_DIR)

from server import is_safe_to_dismiss


class TestWindowRecoverySafety(unittest.TestCase):

    def test_protected_user_windows_in_chinese(self):
        """测试中文系统下用户正在编辑的关键工作界面绝对禁止关闭。"""
        cases = [
            ("另存为", "#32770"),
            ("SOLIDWORKS 系统选项", "#32770"),
            ("方程式管理器", "#32770"),
            ("打开", "#32770"),
            ("自定义", "#32770"),
            ("文档属性 - 单位", "#32770"),
            ("配置属性", "#32770"),
            ("特征编辑", "#32770"),
        ]
        for title, cls in cases:
            safe, reason = is_safe_to_dismiss(title, cls)
            self.assertFalse(safe, f"窗口 '{title}' 不应被允许关闭!")
            self.assertIn("保护白名单", reason)

    def test_protected_user_windows_in_english(self):
        """测试英文系统下用户关键工作界面绝对禁止关闭。"""
        cases = [
            ("Save As", "#32770"),
            ("SOLIDWORKS System Options", "#32770"),
            ("Equations", "#32770"),
            ("Open", "#32770"),
            ("Customize", "#32770"),
            ("Document Properties", "#32770"),
            ("Configuration Properties", "#32770"),
            ("Edit Feature", "#32770"),
        ]
        for title, cls in cases:
            safe, reason = is_safe_to_dismiss(title, cls)
            self.assertFalse(safe, f"窗口 '{title}' 不应被允许关闭!")
            self.assertIn("保护白名单", reason)

    def test_blocking_modal_error_windows(self):
        """测试真正阻断自动化的错误提示、模板丢失、警告弹窗允许被安全关闭。"""
        cases = [
            ("SolidWorks 错误", "#32770"),
            ("SOLIDWORKS 警告", "#32770"),
            ("未找到默认模板", "#32770"),
            ("SOLIDWORKS Default Template Warning", "#32770"),
            ("重建模型错误", "#32770"),
            ("Rebuild Error", "#32770"),
            ("文件已存在，是否覆盖？", "#32770"),
            ("Overwrite Confirmation", "#32770"),
        ]
        for title, cls in cases:
            safe, reason = is_safe_to_dismiss(title, cls)
            self.assertTrue(safe, f"阻断弹窗 '{title}' 应该被允许安全关闭!")
            self.assertIn("允许安全关闭", reason)

    def test_non_dialog_class_name(self):
        """测试非标准对话框窗口类（如主窗口 SldWorks）绝不被关闭。"""
        safe, reason = is_safe_to_dismiss("SOLIDWORKS 2026", "Afx:00007FF6C6BD0000:8:0000000000010003:0000000000000000")
        self.assertFalse(safe)
        self.assertIn("非标准对话框", reason)

    def test_unknown_title_fail_closed(self):
        """测试未知或空白标题的窗口默认 Fail-Closed，安全保留不关闭。"""
        safe, reason = is_safe_to_dismiss("Some Random Window Title", "#32770")
        self.assertFalse(safe)
        self.assertIn("默认安全保留", reason)

        safe_empty, reason_empty = is_safe_to_dismiss("", "#32770")
        self.assertFalse(safe_empty)
        self.assertIn("无标题窗口", reason_empty)


if __name__ == "__main__":
    unittest.main()
