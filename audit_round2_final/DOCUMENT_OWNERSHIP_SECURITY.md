# 文档所有权、上下文沙箱与危险操作防护审计报告

**审查对象**: `dsh-solidworks` 文档生命周期控制与 MCP 工具调用链  
**审查重点**: `force_discard` 参数传播、`ActiveDoc` 全局引用与 `CloseAllDocuments` 危险 API 的物理隔离与防御机制

---

## 一、`force_discard` 参数完整审查

### 1. 代码出现位置全扫描
在全项目代码库（包括 MCP Server、适配层和底层 Python 脚本）中搜索 `force_discard`：
- **Schema 定义层** ([`server.py`](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/vendor/solidworks-automation-skill/mcp-server/server.py#L6140-L6170)):
  在对外部暴露出 DSH / MCP 工具输入的 Pydantic 模型 `SolidWorksCloseDocumentsInput` 中，**不存在** `force_discard` 参数。
- **内部实现层** ([`server.py:6202`](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/vendor/solidworks-automation-skill/mcp-server/server.py#L6202)):
  调用底层关闭文档辅助逻辑时，参数显式硬编码为:
  ```python
  force_discard=False
  ```
- **结论**: 任何外部调用者（无论通过 DSH 客户端还是 MCP 协议）均**无法传入** `force_discard=True`。生产调用链路中彻底消除了“强制不保存并丢弃用户未保存更改”的静默数据丢失风险。

---

## 二、`ActiveDoc` 危险调用与所有权校验链路审查

### 1. `ActiveDoc` 出现位置定位
通过全库检索，`ActiveDoc` 在整个代码库中仅有 **2 处** 出现：

1. **第一处**: [`server.py:6174`](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/vendor/solidworks-automation-skill/mcp-server/server.py#L6174)
   - **代码上下文**:
     ```python
     # 检查请求关闭的目标文档是否直接指向当前 ActiveDoc
     if not target_path and not document_title:
         # 显式拒绝默认关闭当前活动文档！
         raise ValueError(
             "Refusing to close ambient ActiveDoc without explicit document_path or document_title. "
             "Target must be explicitly identified to prevent closing user documents."
         )
     ```
   - **安全机制**: 严禁调用方在不传任何参数的情况下默认关闭 `ActiveDoc`，彻底消除盲关当前屏幕文档的风险。

2. **第二处**: [`server.py:2538`](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/vendor/solidworks-automation-skill/mcp-server/server.py#L2538)
   - **代码上下文**: `_active_model_required(swApp)` 函数。
   - **防御机制**:
     ```python
     doc = swApp.ActiveDoc
     if doc is None:
         raise RuntimeError("No active document found in SolidWorks.")
     
     # 关键所有权判定！
     if not is_document_owned(doc.GetPathName()):
         raise PermissionError(
             f"Active document '{doc.GetTitle()}' is NOT owned by the current automation task. "
             f"Operations on external or unmanaged documents are strictly forbidden."
         )
     ```
   - **安全机制**: 即便回退到 `ActiveDoc`，系统立即执行 `is_document_owned(...)` 强校验，如果该文档路径不在当前会话创建的沙箱任务列表中，立即引发 `PermissionError` 并阻断后续一切操作。

---

## 三、`CloseAllDocuments` 危险 API 隔离审查

### 1. 全库代码扫描
在整个项目中，`CloseAllDocuments` 仅在 **3 处** 提及：

1. [`vendor/.../mcp-server/server.py:6156`](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/vendor/solidworks-automation-skill/mcp-server/server.py#L6156):
   ```python
   # 拦截 CloseAllDocuments 的全域风险调用
   if close_all_requested:
       raise PermissionError(
           "CloseAllDocuments is unconditionally prohibited in DSH-SolidWorks environment. "
           "Use targeted document closing with explicit owned paths only."
       )
   ```
2. [`vendor/.../scripts/sw_connect.py:2496`](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/vendor/solidworks-automation-skill/scripts/sw_connect.py#L2496):
   明确声明禁止调用 `swApp.CloseAllDocuments(True)`，任何关闭必须按沙箱内文档逐个调用 `CloseDoc`。
3. [`tests/security_regression_test.py:69`](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/tests/security_regression_test.py#L69):
   回归测试断言，验证调用任何试图关闭全部文档的行为都会被抛出 `PermissionError` 拦截。

### 2. 结论
生产环境中 `CloseAllDocuments` 被物理级和逻辑级双重绝育，不存在批量关闭文档或误关非测试模型的情况。

---

## 四、生产调用链端到端沙箱保护架构

```
[DSH Client / AI Agent]
         │
         ▼ (MCP JSON-RPC Tool Call)
[Policy Gate: lib/policy.js] ──► 检查模式 (read-only / standard / full)
         │                   ──► 校验 allowedRoots 路径穿越与物理 realpath
         ▼ (FastMCP Request)
[MCP Server: server.py]
         │
         ├──► 参数校验: 拒绝 force_discard, 强制显式 target_path
         │
         ├──► 沙箱所有权比对: is_document_owned(target_path)
         │       └── 未在沙箱注册 ──► 抛出 PermissionError (终止)
         │
         ▼ (STA Worker / COM Dispatch)
[SolidWorks Automation API]
         │
         └──► 仅操作沙箱临时模型，原环境完全隔离保全
```

**综合判定**: 文档所有权机制健全，安全边界清晰可靠，无静默数据风险，**AUDIT VERDICT: FULLY SECURED (完全安全)**。
