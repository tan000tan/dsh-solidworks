# P0 级安全缺陷与文档生命周期整改详情 (04_P0_SECURITY_REMEDIATION.md)

**报告编号**：REWORK-V1.0-04-P0-SECURITY  
**执行角色**：实施方自检 (IMPLEMENTER SELF-REVIEW)  
**核查结论**：**PASS**（全部 4 项 P0 安全缺陷均已实现工程级彻底根治）

---

## 一、P0-04 全仓库危险调用链溯源审查

全仓库搜索高危指令（`CloseAllDocuments`, `CloseDoc`, `CloseDocument`, `ExitApp`, `ActiveDoc`, `SaveAs`, `force_discard`）并追踪其调用防护：

### 1.1 `CloseAllDocuments` 封禁核验
- **搜索结果**：全量代码中共有 7 处匹配。
- **调用点性质**：
  - `server.py:3044`：主动抛出 `PermissionError` 拒绝执行；
  - `sw_connect.py:1237`：`close_all_documents` 强制抛出 `PermissionError`；
  - `security_regression_test.py`：测试 Mock 断言，一旦被调用直接抛出致命异常。
- **裁定**：无任何活跃的 `CloseAllDocuments` 调用，永久封禁落实到位。

### 1.2 `force_discard` 外部注入通道封死核验
- **搜索结果**：全量代码中共有 15 处匹配。
- **Schema 层面**：`SolidWorksCloseDocumentsInput` 彻底移除了 `force_discard` 字段，外部 JSON-RPC 传参直接被 Pydantic 校验拦截 (`Extra inputs are not permitted`)。
- **调用层面**：`solidworks_close_documents` 服务端内部硬编码传参 `force_discard=False`，绝不丢弃未保存修改。

### 1.3 `ActiveDoc` 兜底关闭风险根除核验
- **搜索结果**：全量代码中共有 34 处匹配。
- **关闭接口**：`server.py` 的 `solidworks_close_documents` 删除了 `getattr(sw, "ActiveDoc", None)`，未显式传 `document_path` 或 `title` 时直接拦截报错。
- **建模接口**：建模操作必须针对已显式打开或新建的文档，未指定时给出清晰指引，不盲目操作用户后台未注册文档。

### 1.4 文档所有权判定 (`is_document_owned`)
- 必须同时满足：
  1. 文档对象或路径在 `_SESSION_OWNED_DOCUMENTS` 登记集内；
  2. 路径位于沙箱白名单 `allowed_roots` 内。
- 外部未注册文件哪怕存放在工作区，也绝对无法被关闭或修改。
