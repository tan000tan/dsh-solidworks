import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "vendor", "solidworks-automation-skill")))
import scripts.sw_connect as sw_connect


class TestOwnershipLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger_file = os.path.join(self.tmp.name, "owned-docs.json")
        self.prev_ledger = os.environ.get("DSH_OWNED_LEDGER_PATH")
        self.prev_roots = os.environ.get("DSH_ALLOWED_ROOTS")
        os.environ["DSH_OWNED_LEDGER_PATH"] = self.ledger_file
        os.environ["DSH_ALLOWED_ROOTS"] = self.tmp.name
        sw_connect._SESSION_OWNED_DOCUMENTS.clear()

    def tearDown(self):
        sw_connect._SESSION_OWNED_DOCUMENTS.clear()
        if self.prev_ledger is not None:
            os.environ["DSH_OWNED_LEDGER_PATH"] = self.prev_ledger
        else:
            os.environ.pop("DSH_OWNED_LEDGER_PATH", None)
        if self.prev_roots is not None:
            os.environ["DSH_ALLOWED_ROOTS"] = self.prev_roots
        else:
            os.environ.pop("DSH_ALLOWED_ROOTS", None)
        self.tmp.cleanup()

    def test_cross_process_ledger_persistence_and_hit(self):
        test_file = os.path.join(self.tmp.name, "box.sldprt")
        sw_connect.register_owned_document(test_file)

        # 验证文件已成功持久化写入 ledger
        self.assertTrue(os.path.exists(self.ledger_file), "owned-docs.json ledger must be created on disk")
        with open(self.ledger_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        records = [r["item"] for r in data.get("records", [])]
        abs_p, real_p = sw_connect._canonical_doc_path(test_file)
        self.assertTrue(abs_p in records or real_p in records)

        # 清除当前内存会话登记集，模拟跨进程或新进程环境
        sw_connect._SESSION_OWNED_DOCUMENTS.clear()
        self.assertEqual(len(sw_connect._SESSION_OWNED_DOCUMENTS), 0)

        # 跨进程持久账本必须能够命中
        self.assertTrue(sw_connect.is_document_owned(None, path=test_file))

    def test_unregistered_external_doc_remains_blocked(self):
        external_file = os.path.join(self.tmp.name, "outside_project.sldprt")
        sw_connect._SESSION_OWNED_DOCUMENTS.clear()
        self.assertFalse(sw_connect.is_document_owned(None, path=external_file))


if __name__ == "__main__":
    unittest.main()
