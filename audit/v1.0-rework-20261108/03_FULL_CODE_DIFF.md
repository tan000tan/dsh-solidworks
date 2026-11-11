# 全量代码修改 Diff 审查报告 (03_FULL_CODE_DIFF.md)

**报告编号**：REWORK-V1.0-03-CODE-DIFF  
**执行角色**：实施方自检 (IMPLEMENTER SELF-REVIEW)  
**审计基线**：Git HEAD `7d70bc090d5cef146ac3946bb062667ae30a4cc9`  
**核查结论**：全部变更均为安全加固与测试对齐，无未受控的外部修改

---

## 一、核心安全整改 Diff

### 1.1 `vendor/solidworks-automation-skill/mcp-server/server.py`
彻底从公开 MCP 接口移除 `force_discard` 字段，杜绝盲关活动文档：
```diff
--- a/vendor/solidworks-automation-skill/mcp-server/server.py
+++ b/vendor/solidworks-automation-skill/mcp-server/server.py
@@ -194,7 +194,6 @@ class SolidWorksCloseDocumentsInput(BaseModel):
     """Input schema for solidworks_close_documents tool."""
     document_path: Optional[str] = Field(None, description="Path of document to close.")
     title: Optional[str] = Field(None, description="Title of document to close.")
-    force_discard: bool = Field(False, description="Whether to discard unsaved changes (requires confirmation).")
     reason: str = Field("Session cleanup", description="Audit reason for closing.")
 
@@ -829,13 +828,15 @@ def solidworks_close_documents(
     
+    # 严格禁止自动 Fallback 到 sw.ActiveDoc，防止误关用户前台活动文档
+    if not input_data.document_path and not input_data.title:
+        raise ValueError(
+            "Operating on ActiveDoc by default is strictly forbidden to protect user data."
+        )
+    
     target = None
     if input_data.document_path:
         target = sw.GetOpenDocumentByName(input_data.document_path)
     elif input_data.title:
         target = sw.GetOpenDocumentByName(input_data.title)
-    if not target:
-        target = getattr(sw, "ActiveDoc", None)
-        
     if not target:
         return [types.TextContent(type="text", text="No matching document found to close.")]
 
-    success, msg = close_document(sw, target, force_discard=input_data.force_discard)
+    # 严格限制：公共 MCP 接口绝不允许丢弃未保存修改
+    success, msg = close_document(sw, target, force_discard=False)
```

---

### 1.2 `vendor/solidworks-automation-skill/scripts/sw_connect.py`
强所有权校验：仅当文档显式在 `_SESSION_OWNED_DOCUMENTS` 登记时才允许操作：
```diff
--- a/vendor/solidworks-automation-skill/scripts/sw_connect.py
+++ b/vendor/solidworks-automation-skill/scripts/sw_connect.py
@@ -37,13 +37,18 @@ def is_document_owned(doc, allowed_roots: list = None) -> bool:
     """Check whether a document is owned by the current automation session."""
     if doc is None:
         return False
         
     doc_path = ""
     try:
         doc_path = doc.GetPathName()
     except Exception:
         pass
         
+    # 严格所有权策略：必须已在当前会话的注册表 _SESSION_OWNED_DOCUMENTS 中
+    # 仅路径在白名单内不足以证明属于当前会话（防止命中外部用户存放在同目录下的工作文件）
+    is_registered = (doc in _SESSION_OWNED_DOCUMENTS) or (doc_path and doc_path in _SESSION_OWNED_DOCUMENTS)
+    if not is_registered:
+        return False
+
     if allowed_roots:
```

---

### 1.3 `docs/stage5_advanced_ai_cad/scripts/cad_quality_inspector.py`
128-bit 高熵 Nonce、线程安全锁与过期清理：
```diff
--- a/docs/stage5_advanced_ai_cad/scripts/cad_quality_inspector.py
+++ b/docs/stage5_advanced_ai_cad/scripts/cad_quality_inspector.py
@@ -15,14 +15,22 @@ import time
 import copy
+import threading
 from typing import Any, Dict, List, Optional
 from pydantic import BaseModel, Field
 
 import secrets
 
+MAX_CONSUMED_NONCES = 10000
+_NONCE_LOCK = threading.Lock()
+_CONSUMED_NONCES: Dict[str, float] = {}  # mapping: nonce -> expires_at
+
+def _purge_expired_nonces(now: float) -> None:
+    expired_keys = [k for k, exp in _CONSUMED_NONCES.items() if exp < now]
+    for k in expired_keys:
+        del _CONSUMED_NONCES[k]
+    if len(_CONSUMED_NONCES) >= MAX_CONSUMED_NONCES:
+        sorted_keys = sorted(_CONSUMED_NONCES.keys(), key=lambda k: _CONSUMED_NONCES[k])
+        for k in sorted_keys[: max(1, len(sorted_keys) // 10)]:
+            del _CONSUMED_NONCES[k]
+
@@ -67,2 +75,2 @@ def issue_benchmark_credential(...):
-    n = nonce or f"nonce_{int(now*1000)}_{secrets.token_hex(4)}"
+    n = nonce or f"nonce_{int(now*1000)}_{secrets.token_hex(16)}"
@@ -111,5 +122,5 @@ def verify_benchmark_credential(...):
-    if cred.nonce in _CONSUMED_NONCES:
-        return False, f"Replay attack intercepted: nonce '{cred.nonce}' was already used"
-    _CONSUMED_NONCES.add(cred.nonce)
+    with _NONCE_LOCK:
+        _purge_expired_nonces(now)
+        if cred.nonce in _CONSUMED_NONCES:
+            return False, f"Replay attack intercepted: nonce '{cred.nonce}' was already used"
+        _CONSUMED_NONCES[cred.nonce] = cred.expires_at
```
