# -*- coding: utf-8 -*-
"""
tests/release_swarm_regression_test.py

RELEASE-SWARM-01 回归测试：覆盖本轮整改的 6 条缺陷。
不依赖 SolidWorks / COM（全部使用替身对象），可在任意 Python 3 环境运行。

覆盖：
  BUG-001  open_document 复用分支必须登记所有权
  BUG-002  镜像选择集顺序：特征 mark=1 → 基准面 mark=2
  BUG-016  save_document 不得用子串包含放行未授权文档
  BUG-017  回滚的 closed 必须来自 verify 结果
  BUG-015  create_basic_part 必须先 rebuild 再 save（结构性）
  BUG-018  批量导出必须对已打开但未登记的文档拒绝（结构性）
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VENDOR = REPO_ROOT / "vendor" / "solidworks-automation-skill"
SCRIPTS = VENDOR / "scripts"
SERVER = VENDOR / "mcp-server" / "server.py"
sys.path.insert(0, str(SCRIPTS))

import sw_connect  # noqa: E402
import sw_part  # noqa: E402
import cad_task_context as ctxmod  # noqa: E402


class FakeModel:
    """最小 IModelDoc2 替身：只提供被测代码路径需要的成员。"""

    def __init__(self, title="零件1", path=""):
        self._title = title
        self._path = path
        self.selection = []

    def GetTitle(self):
        return self._title

    def GetPathName(self):
        return self._path

    def ClearSelection2(self, _):
        self.selection.clear()


class FakeExtension:
    def __init__(self, model):
        self.model = model

    def SelectByID2(self, name, etype, x, y, z, append, mark, callout, flags):
        self.model.selection.append((str(name), str(etype), bool(append), int(mark)))
        return True


class FakeMirrorManager:
    def __init__(self):
        self.calls = 0

    def InsertMirrorFeature2(self, *args):
        self.calls += 1
        return object()   # 非空即视为成功


class FakeMirrorModel(FakeModel):
    def __init__(self):
        super().__init__("零件1", "")
        self.Extension = FakeExtension(self)
        self.FeatureManager = FakeMirrorManager()

    def FeatureByName(self, _name):
        return None       # 强制走 _select_by_id 分支，从而可观测 mark/append


class SwarmRegressionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.environ["DSH_ALLOWED_ROOTS"] = self.tmp.name
        sw_connect._SESSION_OWNED_DOCUMENTS.clear()
        self.addCleanup(sw_connect._SESSION_OWNED_DOCUMENTS.clear)

    # ---------------- BUG-001 ----------------
    def test_open_reuse_registers_ownership(self):
        target = Path(self.tmp.name) / "reuse.SLDPRT"
        target.write_bytes(b"stub")

        existing = FakeModel("reuse.SLDPRT", str(target))

        class FakeSw:
            def GetOpenDocumentByName(self, _path):
                return existing

        sw_connect.open_document(FakeSw(), str(target))

        self.assertTrue(
            sw_connect.is_document_owned(existing),
            "BUG-001 回归：复用已打开文档后必须登记所有权，否则下游 DEF-SEC-01",
        )

    # ---------------- BUG-016 ----------------
    def test_save_refuses_title_containing_owned_key(self):
        sw_connect._SESSION_OWNED_DOCUMENTS.add("零件1")
        model = FakeModel("零件10", "")       # 标题包含“零件1”，旧实现会放行
        out = Path(self.tmp.name) / "x.SLDPRT"

        with self.assertRaises(PermissionError):
            sw_connect.save_document(model, str(out))

    # ---------------- BUG-002 ----------------
    def test_mirror_selects_feature_before_plane(self):
        model = FakeMirrorModel()
        sw_part.mirror_feature(model, "凸台-拉伸1", "Front Plane")

        marks = [(etype, append, mark) for (_n, etype, append, mark) in model.selection]
        self.assertTrue(marks, "未发生任何选择调用")

        feat = next((i for i, m in enumerate(marks) if m[0] == "BODYFEATURE"), None)
        plane = next((i for i, m in enumerate(marks) if m[0] == "PLANE"), None)
        self.assertIsNotNone(feat, "未选择被镜像特征")
        self.assertIsNotNone(plane, "未选择镜像基准面")
        self.assertLess(feat, plane, "BUG-002 回归：必须先选被镜像特征，再选基准面")
        self.assertEqual(marks[feat][2], 1, "被镜像特征的 mark 必须为 1")
        self.assertEqual(marks[plane][2], 2, "镜像基准面的 mark 必须为 2")
        self.assertFalse(marks[feat][1], "首个选择不应 append")
        self.assertTrue(marks[plane][1], "基准面选择应 append")

    # ---------------- BUG-017 ----------------
    def test_rollback_closed_reflects_verification(self):
        doc = FakeModel("FailedPart", "")

        class FakeSw:
            """CloseDoc 无效：文档仍留在打开列表中，verify 应返回 False。"""

            def GetDocuments(self):
                return [doc]

            def CloseDoc(self, _title):
                return True

        entry = ctxmod.TrackedDocument(doc_id="d1", title="FailedPart", path=None,
                                       is_newly_created=True, model_com_ref=None)
        context = ctxmod.CADTaskContext(task_id="regression-bug017", session=None)

        verified = ctxmod.DocumentLifecycleManager.close_and_purge_document(FakeSw(), entry, context)

        self.assertFalse(verified, "verify 未通过时应返回 False")
        self.assertFalse(
            entry.closed,
            "BUG-017 回归：closed 必须来自 verify 结果，不能无条件置 True",
        )

    # ---------------- BUG-015（结构性） ----------------
    def test_create_basic_part_rebuilds_before_save(self):
        src = SERVER.read_text(encoding="utf-8", errors="replace")
        start = src.index("def solidworks_create_basic_part")
        end = src.index("@mcp.tool", start)
        body = src[start:end]

        i_rebuild = body.find("ForceRebuild3")
        i_save = body.find("save_document(model, params.output_path)")
        self.assertGreater(i_rebuild, -1, "未找到 ForceRebuild3")
        self.assertGreater(i_save, -1, "未找到 save_document")
        self.assertLess(
            i_rebuild, i_save,
            "BUG-015 回归：必须先 rebuild 再 save，否则文档保存后重新变脏",
        )

    # ---------------- BUG-018（结构性） ----------------
    def test_batch_export_checks_ownership(self):
        src = SERVER.read_text(encoding="utf-8", errors="replace")
        start = src.index("def solidworks_batch_export_files")
        end = src.index("@mcp.tool", start)
        body = src[start:end]

        self.assertIn("is_document_owned", body,
                      "BUG-018 回归：批量导出必须校验已打开文档的所有权")
        self.assertIn("GetOpenDocumentByName", body,
                      "BUG-018 回归：需要按路径判断文档是否已打开")


if __name__ == "__main__":
    unittest.main(verbosity=2)
