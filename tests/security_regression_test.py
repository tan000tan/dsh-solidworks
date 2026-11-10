"""
防回归安全验证套件 (DEF-SEC-01 & DEF-SEC-02)

验证目标：
1. 坚决禁止全局无差别关闭文档 (CloseAllDocuments 永久封禁)。
2. 模拟多个打开文档混合场景 (用户重要资产与测试沙箱文档)。
3. 模拟活动文档焦点切换 (ActiveDoc 切换到用户文档时严禁误关)。
4. 模拟未保存修改 (GetSaveFlag 为 True 时未显式授权严禁静默丢弃)。
5. 模拟异常退出与清理过程中的文档安全隔离。
6. 验证外部/非沙箱文档拒绝关闭 (PermissionError)。
7. 验证 FastMCP solidworks_close_documents 在 close_all=True 时直接阻断并返回 PermissionError 错误响应。
"""
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENDOR_SCRIPTS = os.path.join(PROJECT_ROOT, "vendor", "solidworks-automation-skill", "scripts")
MCP_SERVER_DIR = os.path.join(PROJECT_ROOT, "vendor", "solidworks-automation-skill", "mcp-server")

if VENDOR_SCRIPTS not in sys.path:
    sys.path.insert(0, VENDOR_SCRIPTS)
if MCP_SERVER_DIR not in sys.path:
    sys.path.insert(0, MCP_SERVER_DIR)

from sw_connect import (
    close_document,
    close_all_documents,
    register_owned_document,
    is_document_owned,
    _SESSION_OWNED_DOCUMENTS,
)


class MockSolidWorksDoc:
    def __init__(self, title, path, is_dirty=False):
        self._title = title
        self._path = path
        self._is_dirty = is_dirty

    def GetTitle(self):
        return self._title

    def GetPathName(self):
        return self._path

    def GetSaveFlag(self):
        return self._is_dirty


class MockSolidWorksApp:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.closed_titles = []
        self.ActiveDoc = self.docs[0] if self.docs else None

    def GetDocuments(self):
        return list(self.docs)

    def CloseDoc(self, title):
        self.closed_titles.append(title)
        self.docs = [d for d in self.docs if d.GetTitle() != title and os.path.splitext(d.GetTitle())[0] != title]
        if self.ActiveDoc and (self.ActiveDoc.GetTitle() == title or os.path.splitext(self.ActiveDoc.GetTitle())[0] == title):
            self.ActiveDoc = self.docs[0] if self.docs else None

    def CloseAllDocuments(self, save):
        raise AssertionError("SECURITY VIOLATION: CloseAllDocuments must NEVER be called!")


class SecurityRegressionTest(unittest.TestCase):
    def setUp(self):
        _SESSION_OWNED_DOCUMENTS.clear()
        self.sandbox_dir = os.path.normcase(os.path.abspath(r"C:\SafeSandbox\tests"))
        self.user_dir = os.path.normcase(os.path.abspath(r"D:\CustomerProjects\Engine"))
        self.env_patcher = patch.dict(os.environ, {"DSH_ALLOWED_ROOTS": json.dumps([self.sandbox_dir])})
        self.env_patcher.start()
        self.test_doc = MockSolidWorksDoc("test_part.SLDPRT", os.path.join(self.sandbox_dir, "test_part.SLDPRT"), is_dirty=False)
        self.user_doc1 = MockSolidWorksDoc("commercial_turbine.SLDPRT", os.path.join(self.user_dir, "commercial_turbine.SLDPRT"), is_dirty=True)
        self.user_doc2 = MockSolidWorksDoc("gearbox_assembly.SLDASM", os.path.join(self.user_dir, "gearbox_assembly.SLDASM"), is_dirty=False)
        register_owned_document(self.test_doc)
        self.mock_sw = MockSolidWorksApp([self.user_doc1, self.test_doc, self.user_doc2])

    def tearDown(self):
        self.env_patcher.stop()
        _SESSION_OWNED_DOCUMENTS.clear()

    def test_sec_01_close_all_documents_permanently_forbidden(self):
        """SEC-01: 验证任何针对 close_all_documents 的调用均直接触发 PermissionError 阻断"""
        with self.assertRaises(PermissionError) as ctx:
            close_all_documents(self.mock_sw, True)
        self.assertIn("permanently forbidden", str(ctx.exception))
        self.assertEqual(len(self.mock_sw.closed_titles), 0, "不应有任何文档被关闭")

    def test_sec_02_refuse_closing_unowned_user_document(self):
        """SEC-02: 验证严禁关闭未被本会话登记且处于沙箱外的用户文档"""
        # 尝试直接按标题关闭用户文档
        with self.assertRaises(PermissionError) as ctx:
            close_document(self.mock_sw, "commercial_turbine.SLDPRT", allowed_roots=[self.sandbox_dir])
        self.assertIn("安全边界拦截", str(ctx.exception))
        self.assertEqual(len(self.mock_sw.closed_titles), 0)

        # 尝试传入用户文档 COM 对象关闭
        with self.assertRaises(PermissionError) as ctx:
            close_document(self.mock_sw, self.user_doc2, allowed_roots=[self.sandbox_dir])
        self.assertIn("安全边界拦截", str(ctx.exception))
        self.assertEqual(len(self.mock_sw.closed_titles), 0)

    def test_sec_03_active_document_switch_protection(self):
        """SEC-03: 模拟用户切换活动窗口至商业文档，验证自动化绝不误关当前 ActiveDoc"""
        # 用户将焦点切到了商业涡轮模型
        self.mock_sw.ActiveDoc = self.user_doc1
        self.assertEqual(self.mock_sw.ActiveDoc.GetTitle(), "commercial_turbine.SLDPRT")

        # 自动化若盲目关闭 None 或空字符串，必须直接拒绝且返回 False
        res1 = close_document(self.mock_sw, None)
        self.assertFalse(res1)
        res2 = close_document(self.mock_sw, "")
        self.assertFalse(res2)
        res3 = close_document(self.mock_sw, "   ")
        self.assertFalse(res3)
        self.assertEqual(len(self.mock_sw.closed_titles), 0)

    def test_sec_04_unsaved_dirty_document_protection(self):
        """SEC-04: 模拟测试文档包含未保存修改，未显式指定 force_discard 时拒绝关闭"""
        dirty_test_doc = MockSolidWorksDoc("dirty_test.SLDPRT", os.path.join(self.sandbox_dir, "dirty_test.SLDPRT"), is_dirty=True)
        register_owned_document(dirty_test_doc)
        self.mock_sw.docs.append(dirty_test_doc)

        with self.assertRaises(ValueError) as ctx:
            close_document(self.mock_sw, dirty_test_doc, force_discard=False, allowed_roots=[self.sandbox_dir])
        self.assertIn("包含未保存的修改", str(ctx.exception))
        self.assertEqual(len(self.mock_sw.closed_titles), 0)

        # 显式传入 force_discard=True 允许丢弃测试草稿
        success = close_document(self.mock_sw, dirty_test_doc, force_discard=True, allowed_roots=[self.sandbox_dir])
        self.assertTrue(success)
        self.assertIn("dirty_test.SLDPRT", self.mock_sw.closed_titles)

    def test_sec_05_safe_close_owned_sandbox_document(self):
        """SEC-05: 验证沙箱内已登记且干净的测试文档可被精准关闭，不影响其它任何用户文档"""
        initial_open_count = len(self.mock_sw.GetDocuments())
        success = close_document(self.mock_sw, self.test_doc, allowed_roots=[self.sandbox_dir])
        self.assertTrue(success)

        # 校验：仅测试文档被关闭
        self.assertEqual(self.mock_sw.closed_titles, ["test_part.SLDPRT"])
        remaining_titles = [d.GetTitle() for d in self.mock_sw.GetDocuments()]
        self.assertIn("commercial_turbine.SLDPRT", remaining_titles)
        self.assertIn("gearbox_assembly.SLDASM", remaining_titles)
        self.assertNotIn("test_part.SLDPRT", remaining_titles)
        self.assertEqual(len(remaining_titles), initial_open_count - 1)

    def test_sec_06_mcp_server_close_all_rejection(self):
        """SEC-06: 验证 FastMCP solidworks_close_documents 在 close_all=True 时阻断并返回错误响应"""
        from server import solidworks_close_documents, SolidWorksCloseDocumentsInput

        params = SolidWorksCloseDocumentsInput(close_all=True)
        resp_str = solidworks_close_documents(params)
        data = json.loads(resp_str)
        self.assertEqual(data.get("status"), "error")
        self.assertEqual(data.get("error_type"), "PermissionError")
        self.assertIn("permanently forbidden", data.get("message", ""))


    def test_sec_07_activedoc_fallback_strictly_forbidden(self):
        """SEC-07: 验证未显式提供 document_path 或 title 时绝不自动回退到 ActiveDoc，强制报错拦截"""
        from server import solidworks_close_documents, SolidWorksCloseDocumentsInput

        params = SolidWorksCloseDocumentsInput()
        resp_str = solidworks_close_documents(params)
        data = json.loads(resp_str)
        self.assertEqual(data.get("status"), "error")
        self.assertEqual(data.get("error_type"), "ValueError")
        self.assertIn("Operating on ActiveDoc by default is strictly forbidden", data.get("message", ""))

    def test_sec_08_force_discard_injection_rejected(self):
        """SEC-08: 验证 MCP 输入 Schema 不允许注入 force_discard 参数，彻底封死丢弃未保存修改通道"""
        from server import SolidWorksCloseDocumentsInput
        import pydantic

        # 尝试通过 kwargs 注入非法 force_discard 字段
        with self.assertRaises((pydantic.ValidationError, TypeError)):
            SolidWorksCloseDocumentsInput(force_discard=True)

    def test_sec_09_unregistered_sandbox_path_rejected(self):
        """SEC-09: 验证即使文件物理路径位于 allowed_roots，若未由当前会话显式登记，亦严禁关闭外部文件"""
        # 模拟位于沙箱目录但未被本会话创建或登记的文件
        unregistered_doc = MockSolidWorksDoc("user_existing_part.SLDPRT", os.path.join(self.sandbox_dir, "user_existing_part.SLDPRT"), is_dirty=False)
        self.mock_sw.docs.append(unregistered_doc)

        with self.assertRaises(PermissionError) as ctx:
            close_document(self.mock_sw, unregistered_doc, allowed_roots=[self.sandbox_dir])
        self.assertIn("未由当前自动化任务创建", str(ctx.exception))
        self.assertNotIn("user_existing_part.SLDPRT", self.mock_sw.closed_titles)


    def test_sec_10_active_model_required_blocks_unowned_document(self):
        """SEC-10: 验证 _active_model_required 严禁对未登记所有权的活动文档进行操作"""
        from server import _active_model_required
        unowned_doc = MockSolidWorksDoc("user_confidential.sldprt", r"C:\ConfidentialCorporateData\user_confidential.sldprt")
        self.mock_sw.ActiveDoc = unowned_doc

        with patch("server.connect_solidworks", return_value=(self.mock_sw, unowned_doc)):
            with self.assertRaises(PermissionError) as ctx:
                _active_model_required(must_be_owned=True)
            self.assertIn("DEF-SEC-01", str(ctx.exception))
            self.assertIn("not owned by the current automation session", str(ctx.exception))

    def test_sec_11_mutating_mcp_tools_block_unowned_active_document(self):
        """SEC-11: 验证 MCP 变异工具（如修改尺寸）面对未授权 ActiveDoc 时严格拒绝执行"""
        from server import solidworks_modify_dimension_safe, SolidWorksSafeDimensionUpdateInput
        unowned_doc = MockSolidWorksDoc("user_confidential.sldprt", r"C:\ConfidentialCorporateData\user_confidential.sldprt")
        self.mock_sw.ActiveDoc = unowned_doc

        with patch("server.connect_solidworks", return_value=(self.mock_sw, unowned_doc)):
            inp = SolidWorksSafeDimensionUpdateInput(updates={"D1@Sketch1": 50.0})
            resp_str = solidworks_modify_dimension_safe(inp)
            data = json.loads(resp_str)
            self.assertEqual(data.get("status"), "error")
            self.assertEqual(data.get("error_type"), "PermissionError")
            self.assertIn("DEF-SEC-01", data.get("message", ""))

    def test_sec_12_mutating_mcp_tools_allow_owned_document(self):
        """SEC-12: 验证经显式登记在 allowed_roots 的会话所有权文档正常通过安全校验"""
        from server import _active_model_required
        owned_path = os.path.join(self.sandbox_dir, "owned_model.sldprt")
        owned_doc = MockSolidWorksDoc("owned_model.sldprt", owned_path)
        self.mock_sw.ActiveDoc = owned_doc
        register_owned_document(owned_doc)
        self.assertTrue(is_document_owned(owned_doc))

        with patch("server.connect_solidworks", return_value=(self.mock_sw, owned_doc)):
            sw, model = _active_model_required(must_be_owned=True)
            self.assertEqual(model, owned_doc)


if __name__ == "__main__":
    unittest.main()
