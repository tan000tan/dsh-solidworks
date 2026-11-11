# 危险 API 与调用链全量扫描报告 (04_DANGEROUS_API_AUDIT.md)

**执行时间**：2026-11-08 00:31 CST  
**扫描范围**：`vendor/solidworks-automation-skill/`, `lib/`, `tests/`, `docs/stage5_advanced_ai_cad/`  

---

## 一、危险 API 扫描结果与调用链全景

### 1. `CloseAllDocuments` 扫描
- **扫描结果**：在历史脚本（如旧审计交付物）中存在历史出现；
- **活跃生产代码状态**：在当前活跃代码（`server.py`, `sw_connect.py`, `cad_task_context.py`）中，**原 `sw.CloseAllDocuments(True)` 已被完全封禁**；
- **防御性桩函数**：`sw_connect.py:1231` 保留 `def close_all_documents`，调用时永久抛出 `PermissionError`；`server.py:3033` 传入 `close_all=True` 亦永久抛出 `PermissionError`。该项已基本达标。

### 2. `force_discard` 暴露调用链（重大 P0 漏洞）
- **漏洞调用链**：
  ```text
  外部 MCP JSON-RPC 请求 {"name": "solidworks_close_documents", "arguments": {"force_discard": true}}
      ↓
  server.py:3018 SolidWorksCloseDocumentsInput.force_discard: bool = False
      ↓
  server.py:3071 close_document(sw, target, force_discard=params.force_discard)
      ↓
  sw_connect.py:1186 if is_dirty and not force_discard: raise ValueError(...)
  [因 force_discard 为 True，脏检查被完全跳过！]
      ↓
  sw_connect.py:1198 get_com_member(sw, "CloseDoc", title_to_close)
      ↓
  SolidWorks 关闭文档并丢弃未保存修改！
  ```
- **危害定性**：彻底击穿单文档未保存脏保护防线。

### 3. `ActiveDoc` 回退调用链（重大 P0 漏洞）
- **漏洞调用链**：
  ```text
  外部 MCP 请求关闭未指定 target 的文档 {"name": "solidworks_close_documents", "arguments": {}}
      ↓
  server.py:3055 if not target: target_model = getattr(sw, "ActiveDoc", None); target = target_model
      ↓
  sw_connect.py:1138 close_document(sw, target=sw.ActiveDoc)
  ```
- **危害定性**：违反“禁止假设当前活动文档就是测试文档”的铁律，用户正在编辑的文档会被直接选为关闭目标。

### 4. `is_document_owned` 沙箱路径与所有权混淆（P0 隐患）
- **源码分析**：`sw_connect.py:129` 中，如果文档物理路径位于 `DSH_ALLOWED_ROOTS`（通常包含工作区），`validate_path_against_allowed_roots` 返回 `True`，导致 `is_document_owned` 判定为 `True`。
- **危害定性**：用户在工作区中打开的原型文件会被自动化框架误当成自己创建的文件进行关闭。必须要求文档既在沙箱内，又显式登记在 `_SESSION_OWNED_DOCUMENTS` 登记集中。

### 5. `BENCHMARK_SECRET` 硬编码与签发权缺乏边界（P1 漏洞）
- **源码分析**：`cad_quality_inspector.py:16` 明文硬编码 `BENCHMARK_SECRET = "SWCAD_BENCHMARK_SIGNING_KEY_SECURE_2026"`。
- **危害定性**：任何代码可直接调用公有函数签发有效凭据，无法证明真实独立性。
