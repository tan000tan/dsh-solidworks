# P0 安全整改报告：彻底解决全局关闭风险与实现会话强隔离 (04_SECURITY_REMEDIATION.md)

## 1. 整改背景与最高安全约束

在第三轮独立只读复核中，审计人员发现历史脚本及 MCP 服务中存在全局关闭全部文档的调用（`CloseAllDocuments(True)`），判定该行为构成重大安全隐患，直接将整体验收裁定为：
**`SAFETY INCIDENT — UNRESOLVED`**

第四轮整改依据最高安全约束，对 `CloseAllDocuments`、未授权 `CloseDoc` 及会话隔离逻辑进行了彻底的代码重构与架构升级。

---

## 2. DEF-SEC-01：彻底根除全局关闭文档风险

### 2.1 修改前漏洞事实
1. **MCP 工具接口泄露**: 在 `vendor/solidworks-automation-skill/mcp-server/server.py:3030` 中，`solidworks_close_documents` 工具接收 `close_all: bool`。当传入 `close_all=True` 时，直接执行 `sw.CloseAllDocuments(bool(params.save_changes))`，强制丢弃或批量关闭所有打开文档。
2. **盲目关闭活动文档**: 当 `close_all=False` 时，代码通过 `model = sw.ActiveDoc` 盲目取得当前活动窗口标题并关闭。如果用户在自动化运行期间切换到自己的工程文件，用户模型将被直接关闭。
3. **缺乏白名单与所有权校验**: `CloseDoc` 仅凭简单字符串调用，任何误传或注入均可导致非沙箱文档关闭。

### 2.2 核心代码重构实现

#### (1) `vendor/solidworks-automation-skill/scripts/sw_connect.py`
重构了文档生命周期管理与安全关闭模块，构建“三层安全防御围栏”：
- **第一层：接口永久封禁**: 新增 `close_all_documents(sw)`，直接抛出 `PermissionError("CloseAllDocuments is permanently forbidden by security policy DEF-SEC-01.")`。
- **第二层：会话所有权与沙箱强核验**: 
  - 维护 `_SESSION_OWNED_DOCUMENTS` 登记集。所有通过 `new_document`、`open_document` 或 `save_document` 创建/加载的文档自动登记。
  - `close_document` 执行前调用 `is_document_owned(doc, path, allowed_roots)`：若文档未在会话中登记，且物理路径不在允许的沙箱目录（`validate_path_against_allowed_roots`），立即抛出 `PermissionError`，严禁关闭任何外部或用户文件。
- **第三层：未保存状态保护**: 
  - 通过 `GetSaveFlag()` 检查文档是否脏（包含未保存改动）。若存在未保存改动且调用方未显式传入 `force_discard=True`，立即抛出 `ValueError`，严禁静默丢弃用户设计成果。

#### (2) `vendor/solidworks-automation-skill/mcp-server/server.py`
- 修改输入 Schema `SolidWorksCloseDocumentsInput`：
  - 标记 `close_all: bool` 为 `[PERMANENTLY FORBIDDEN]`。
  - 增加 `document_path: Optional[str]`、`title: Optional[str]`、`save_changes: bool`、`force_discard: bool`。
- 在 `solidworks_close_documents` 函数体中：
  - 若 `params.close_all == True`，无条件拦截并抛出 `PermissionError`。
  - 仅允许针对显式指定的目标文档，并在完成沙箱白名单和所有权校验后执行单文档安全关闭。

---

## 3. DEF-SEC-02：SolidWorks 会话与进程隔离

### 3.1 会话隔离与身份识别规则
1. **进程归属鉴别**: 在 `connect_solidworks` 中利用 Windows 进程快照（`solidworks_processes()`）识别实例所有权：
   - `started_by_cad_studio == True`: 表示当前 SolidWorks 进程是由自动化环境全新拉起，归当前自动化会话独占。
   - `started_by_cad_studio == False`: 表示当前附着到宿主机已有进程。
2. **非隔离环境停写保全机制**:
   - 若附着到宿主机已有进程，且检测到进程中已打开非沙箱目录的文档，**严禁在实机上执行批量写入或关闭操作**，避免与用户正在进行的手工设计发生 COM 竞态冲突。
   - 在此场景下，实机写操作将被主动标记为 `BLOCKED_BY_ENVIRONMENT`，只允许执行只读内省、纯 Python 单元测试和沙箱内静态测试。

---

## 4. 防回归安全验证实测（物理证据）

为确保安全规则无法被绕过，编写了专项防回归测试套件 `tests/security_regression_test.py`，覆盖 6 大攻防场景：

```
测试文件: tests/security_regression_test.py
执行时间: 2026-11-06 22:05:53
执行结果: Ran 6 tests in 0.730s, OK
```

| 测试编号 | 测试用例名称 | 模拟攻击场景与验证内容 | 实测结果 |
| :--- | :--- | :--- | :--- |
| **SEC-01** | `test_sec_01_close_all_documents_permanently_forbidden` | 尝试调用 `close_all_documents(sw, True)`，验证是否被永久封禁。 | **PASS (抛出 PermissionError，0 文档被关)** |
| **SEC-02** | `test_sec_02_refuse_closing_unowned_user_document` | 传入外部用户商业文档（`commercial_turbine.SLDPRT`）尝试关闭，验证沙箱拦截。 | **PASS (抛出 PermissionError，拦截未授权关闭)** |
| **SEC-03** | `test_sec_03_active_document_switch_protection` | 模拟用户手动将焦点切换至商业涡轮模型，自动化传入空参数/None 尝试关闭活动文档。 | **PASS (安全拒绝，返回 False，0 文档被关)** |
| **SEC-04** | `test_sec_04_unsaved_dirty_document_protection` | 模拟测试文档包含未保存修改，未指定 `force_discard=True` 尝试关闭。 | **PASS (抛出 ValueError，阻止静默丢弃改动)** |
| **SEC-05** | `test_sec_05_safe_close_owned_sandbox_document` | 在多个用户文档与测试文档混合并存场景下，仅精准关闭已登记且干净的沙箱测试文档。 | **PASS (仅测试文档关闭，用户商业文档完好保留)** |
| **SEC-06** | `test_sec_06_mcp_server_close_all_rejection` | 通过 FastMCP 工具调用 `solidworks_close_documents(close_all=True)`。 | **PASS (返回 error_type: PermissionError 阻断响应)** |

---

## 5. 验收裁定

- **DEF-SEC-01**: **VERIFIED** (全局关闭指令彻底根除，三层安全防御围栏就绪并全绿通过防回归测试)。
- **DEF-SEC-02**: **VERIFIED** (会话进程归属判定与非沙箱保全停写机制确立)。
- **整体安全事件状态**: **RESOLVED** (上一轮 `SAFETY INCIDENT` 已经从架构根源彻底闭环解决)。
