# 第四轮审计交付物 15：运行环境与已知局限性说明 (ENVIRONMENT & LIMITATIONS)

## 一、运行环境基准 (Runtime Environment Baseline)

第四轮全量整改与独立验收测试在以下完全受控的物理/系统环境下执行：

| 软硬件层级 | 配置规格与版本 | 路径与标识 |
| :--- | :--- | :--- |
| **操作系统** | Windows 11 专业版 64 位 (Build 10.0.26200) | AMD64 架构 |
| **Node.js 运行时** | v24.21.0 (npm v10.8.2) | `D:\Node.js\node.exe` |
| **Python 运行时** | Python 3.13.16 64-bit | `D:\SWCAD-MCP\Python313\python.exe` (执行时均强制使用 `-B` 内存模式) |
| **CAD 核心宿主** | **SolidWorks 2026 SP04.1** | 版本号: `34.4.1.0028` |
| **COM 注册信息** | ProgID: `SldWorks.Application.34` | CLSID: `{666aaee2-7a21-40fc-b768-2078840a88c3}` |
| **关键 Python 库** | pywin32 (308+), pydantic (2.10+), fastmcp | 原生 Windows OLE 动态分发 |
| **测试隔离沙箱** | 本轮独占沙箱目录 | `audit/fourth-remediation-2026-11-06/cad_test_sandbox/` |

---

## 二、已知环境局限性与工程边界说明 (Known Limitations)

为遵循“诚实披露、绝不掩饰”的工程原则，以下列出当前版本客观存在的环境依赖与技术边界：

### 1. STA 单线程单元与线程宿主依赖 (STA Apartment Affinity)
- **现象与机理**：SolidWorks COM API 为典型的 STA（Single-Threaded Apartment）架构。在 Windows 非默认桌面、服务会话或多线程并发环境下，跨线程直接调用 COM 接口会触发 pywin32 动态分发未解析异常（`<unknown>.Member`）。
- **应对方案**：项目已实现 `DesktopPinnedStaWorker`（单例 STA 专用工作线程），所有针对 SolidWorks 的 COM 操作均必须路由至 `worker.execute(...)` 中执行。独立复核人员运行实机脚本时须遵循此调用规范。

### 2. 工程图视图投影视图模型内存驻留约束 (Drawing Model In-Session Requirement)
- **现象与机理**：在 SolidWorks 2026 中调用 `Create3rdAngleViews2` 或 `CreateDrawViewFromModelView3` 从模型创建图纸视图时，源零件（`.SLDPRT`）或装配体（`.SLDASM`）若处于未在当前会话中加载的状态，API 可能因文件独占锁或内存图元未就绪返回 `False`。
- **应对方案**：生成工程图时，脚本保持源模型在会话内存中打开，待工程图完全生成并保存后，再通过逆序逐一精准关闭。

### 3. Windows 会话与窗口站切换偶发瞬态锁定 (Window Station Transient Delay)
- **现象与机理**：当 Windows 处于用户注销、锁屏或快速用户切换期间，Windows 内核会临时关闭当前 Window Station，此时启动依赖 GUI 交互的自动化子进程可能遇到 `CreateDesktop: DLL Initialization Failed`。
- **应对方案**：此属于 Windows 操作系统会话安全机制，在用户登录状态稳定后即可自愈，不会影响代码本身的功能逻辑与数据持久化。

### 4. 严苛的沙箱外部文件保护约束 (Sandbox Boundary Strictness)
- **现象与机理**：为彻底防止第三轮的 `CloseAllDocuments(True)` 事故复发，当前安全引擎实施“无差别白名单拦截”。任何未在 `_SESSION_OWNED_DOCUMENTS` 登记或未在 `allowed_roots`（允许目录）下的文件，调用 `close_document` 均会被强制抛出 `PermissionError`。
- **工程价值**：此举从根本上杜绝了自动化脚本误触或破坏用户真实工程模型的可能性，虽对测试脚本的注册严密性提出了更高要求，但为最高优先级安全保障所必需。

---

## 三、第三方独立审查只读复现指引 (Independent Verification Guide)

独立审查人员（如第三方审计专家或 ChatGPT）可直接执行以下完全只读的复核指令，检验本轮整改成果：

```powershell
# 1. 切换至项目根目录
cd "D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin"

# 2. 执行 Node.js 策略与协议测试 (68 项全部通过)
npm.cmd test

# 3. 执行 Python 安全防线回归测试 (6 项全部通过)
D:\SWCAD-MCP\Python313\python.exe -B tests/security_regression_test.py

# 4. 执行对抗性攻击测试 (15 项全部通过)
D:\SWCAD-MCP\Python313\python.exe -B tests/inspector_adversarial_attack_test.py

# 5. 执行环境兼容性测试 (18 项全部通过，含无条件 M09)
D:\SWCAD-MCP\Python313\python.exe -B tests/rem_compat_test.py

# 6. 验证第四轮实机物证文件存在性与大小
Get-ChildItem -Path "audit/fourth-remediation-2026-11-06/cad_test_sandbox" | Select-Object Name, Length
```
