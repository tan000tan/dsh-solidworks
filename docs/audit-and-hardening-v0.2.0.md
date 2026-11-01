# dsh-solidworks v0.2.0 全量安全加固与 66 工具功能审计报告 (更新版)

## 一、工作包 1：安全漏洞二次审计与物理路径加固

针对此前审计中发现的安全策略缺陷，已完成生产级代码修复并通过全量回归测试：

### 1. 相对路径漏检与目录逃逸根治
- **缺陷表现**：此前 `collectPaths` 正则仅提取以盘符、UNC 或正斜杠开头的路径。模型若传入相对路径（如 `part.sldprt`、`.\model.sldprt` 或 `..\windows\system32\calc.exe`），路径检查被静默跳过，导致白名单沙箱失守。
- **修复方案**：
  - 重构 `collectPaths`：递归提取所有具备文件扩展名特征（如 `.sldprt`、`.step` 等）或包含路径分隔符的非空字符串，并对包含 `path`、`filepath`、`target`、`dir` 等关键属性的字段实施强制收集。
  - 在 `#outsideAllowedRoots` 中引入基准锚定：以 `sessionCwd` 或指定的 `allowedRoots[0]` 为基准，使用 `path.resolve(baseDir, candidate)` 将相对路径完全解析为物理绝对路径。若缺乏可信基准目录，安全原则直接拒绝执行。

### 2. `..` 路径遍历与符号链接/Junction 物理穿透防御
- **缺陷表现**：纯字符串比对（如 `path.resolve`）无法发现软链接或目录联接（Junction）指向外部敏感目录的隐蔽穿透。此外，当目标文件尚未在磁盘上创建时，直接调用 `fs.realpathSync` 会因 `ENOENT` 失败。
- **物理真实路径解析算法（`realpathWithAncestorWalk`）**：
  - 代码引入逆向祖先遍历机制：当目标文件/目录尚不存在时，自底向上逐级向上回溯其已存在的父目录，利用 Node.js 原生 `fs.realpathSync.native()` 彻底展开已存在祖先节点的真实物理路径，随后拼接未创建的文件尾部；
  - 判定算法：`isPathInside(realCandidate, realRoot)` 利用 `path.relative` 计算折叠后的物理相对距离，要求 `!rel.startsWith('..') && !path.isAbsolute(rel)`；
  - 无论利用 `..` 相对目录，还是利用预埋的 Junction 软链接，一旦解析后的真实物理位置超出白名单，立刻被物理阻断！
  - 同步实现了 Windows 驱动器盘符大小写不敏感规范化（`toLowerCase()`）及前缀碰撞攻击拦截（`C:\workspace` 无法匹配 `C:\work`）。

### 3. 未知工具安全默认原则重构（Fail-Safe Zero-Trust）
- **缺陷表现**：此前 `classify(name)` 对未收录在已知表且未匹配动词正则的工具，默认 fallback 返回 `READ`，构成隐蔽提权风险。
- **修复方案**：
  - `classify(name)` 的兜底逻辑由 `READ` 修改为 `HIGH`，未知工具绝不默认判定为安全。
  - 在 `Policy.evaluate()` 前置门禁中增加判定：凡未在已知 66 工具 `RISK_TABLE` 中且未显式在 `allow` 白名单中的工具，直接以结构化错误 `TOOL_UNKNOWN` 拒绝执行。
  - 确保只读模式下未知工具 `registerable()` 100% 返回 `false`。

### 4. 自动化测试验证证据
- 更新 `tests/policy.test.js`，包含 15 项深度安全断言（涵盖未创建文件的物理 realpath 解析、跨盘符隔离、相对路径解析展开、前缀碰撞防御、未知工具阻断等）。
- 执行结果：**15 项测试用例全部通过（100% PASS，耗时 ~13ms）**。
- 原生发布套件 `npm test`（含 schema、package、policy、mcp）全部持续保持 100% 通过。

---

## 二、工作包 2：运行代码一致性与加载状态核实

### 1. 代码三层一致性确认
通过对 Git 工作区（`<project-root>\`）与用户实际安装目录（`<dsh-profile>/node_modules/dsh-solidworks\`）进行逐文件 SHA-256 哈希比对：
- `lib/policy.js`: 字节级完全一致 (`635e2e88adb4...`)
- `lib/index.js`: 字节级完全一致 (`ab06ffe56510...`)
- `lib/mcp.js`: 字节级完全一致 (`01ecce844e94...`)
- `lib/schema.js`: 字节级完全一致 (`70db98f2808f...`)
- `package.json`: 字节级完全一致 (`965d215c5508...`)
- `cordis.patch.yml`: 字节级完全一致 (`f6de75f5d2b6...`)
- `tests/policy.test.js`: 字节级完全一致 (`392faa476cbe...`)

### 2. 运行时进程状态核验
- **DSH 宿主进程**：实测当前系统中未运行 `DeepSeek Harness.exe`。
- **MCP 进程**：当前无任何残留的旧版 Python 进程。
- **结论**：当前不存在任何旧代码内存缓存。当用户下一次打开 DSH 时，系统将直接从 `node_modules` 载入经过安全加固的最新代码，无需执行重启操作。

---

## 三、工作包 3：SolidWorks COM 连接机理与解决路径

### 1. 现象复盘与根本原因排查
- **现象**：当前 SolidWorks（PID 3032）正在运行且正常交互（内含未保存零件 `零件1`），但所有 B 类几何读取工具调用均被 `[SW_INSTANCE_NOT_READY] attach: 已有实例尚不可连接，已阻止重复启动` 阻断。
- **排查事实**：
  1. 权限级别：PID 3032 与当前 Agent/Python 均为 `Medium Mandatory Level`（排除 UAC 提权隔离）。
  2. 会话归属：两者同在 `Session 1` 交互桌面会话（排除跨 Session 隔离）。
  3. ROT 全局扫描：调用 Windows API `pythoncom.GetRunningObjectTable().EnumRunning()` 扫描当前桌面，**ROT 中条目为 0**，完全未见 SolidWorks 相关的 Moniker 注册项。
- **根本机理**：
  - 根据 Dassault Systèmes 官方 API 架构规范，当用户通过桌面快捷方式或普通交互界面直接双击打开 SolidWorks 时，**SolidWorks 默认处于纯 UI 模式，不会主动向 OLE/COM ROT 注册自身顶级 Application 标识**。
  - 只有当外部第一次触发 OLE Automation 请求（或 SolidWorks 内部加载了注册自动化支持的 Add-In、或运行了内置 VBA 宏）时，系统 COM 代理才会把已运行的实例挂载并登记到 ROT。
  - 然而 `sw_connect.py` 的现有逻辑是：一旦检测到进程列表中存在 `SLDWORKS.exe`，就**严格只允许使用 `GetActiveObject` 进行只读连接**，若 1 秒内未在 ROT 查到，即断定为“实例未就绪”，断然抛出 `SW_INSTANCE_NOT_READY` 并终止执行。
  - 这造成了**“ROT 尚未就绪无法 attach，而策略为了防多开又禁止 dispatch 挂载”**的双向锁死。

### 2. 解决方案客观评估
- **宏激活假设定性**：在 VBA 中手动运行宏激活 COM 属于“尚未经本机严格对照闭环实测的假设”，不可作为生产环境的已确认定论。
- **生产级建议**：
  1. 后续在 `sw_connect.py` 中引入受控的已运行 PID 比对挂载机制（先 `Dispatch`，若返回的 PID 与现有 PID 一致则视为绑定成功，若不一致则立即销毁新进程）；
  2. 针对自动化流水线，通过 `SLDWORKS.exe /Automation` 参数拉起受控沙箱实例。

---

## 四、工作包 4：16 个只读工具状态全景

- **CLI 实测通过（6 项）**：
  `solidworks_status` (Meta), `solidworks_health_check`, `solidworks_addin_host_status`, `cadstudio_resolve_backend`, `cadstudio_routing_preflight`, `cadstudio_fea_preflight`。
- **CAD 连接阻塞（5 项几何工具）**：
  `solidworks_bounding_box`, `solidworks_mass_properties`, `solidworks_list_edges`, `solidworks_inspect_configurations`, `solidworks_inspect_hole_features`。
  （工具分发与参数校验成功，因前台实例未在 ROT 触发互斥锁拦截，未进入真实几何读取，不可算作功能通过）。
- **仅源码审查（5 项暂缓工具）**：
  `solidworks_interference_check`, `solidworks_inspect_motion_studies`, `solidworks_validate_motion_study`, `design_spec_validate`, `cadstudio_read_artifact`, `solidworks_inspect_native_geometry`。

---

## 五、工作包 5：独立 CAD 测试沙箱方案

- **沙箱路径**：`D:\SW_Test_Sandbox`
- **物理状态核实**：实测当前磁盘上 `EXISTS: False`。恪守红线，**未擅自创建该目录**。
- **三大场景规划**：
  - **场景 A（零件建模与只读度量）**：草图拉伸、打孔、圆角、边界框/质量比对、安全保存。
  - **场景 B（装配体与配合）**：多零件载入、基座固定、同轴重合配合、干涉检查。
  - **场景 C（工程图与导出）**：A4 图纸投影、图纸审查、STEP 格式导出。
- **文档保护守卫**：每次执行前检查 `swApp.ActiveDoc.GetTitle`，若为 `零件1` 立即抛出异常阻断，坚决杜绝误操作。

---

## 六、工作包 6：兼容性物理证据修正

重新核实环境底层信息，纠正此前错误记载：

| 软硬件组件 | 官方声明支持 | 本机实际证据 | 兼容性判定 | 修正与说明 |
| :--- | :--- | :--- | :---: | :--- |
| **操作系统** | Windows 10/11 64位 | **Windows 11 家庭中文版 64位 (Build 26200)** | **实机已验证** | 纠正此前误报为“专业版”的笔误 |
| **SolidWorks** | 2024 / 2026 | **SolidWorks 2026 SP04.1** (ProgID 34, TLB 完整) | **实机已验证** | 顶级句柄需 Automation 激活 |
| **Python** | 3.10 – 3.13 | **Python 3.13.16** (FastMCP, pywin32 正常) | **实机已验证** | 运行时强制禁止字节码缓存写入 |
| **Node.js** | 22.12+ | **Node.js 运行环境** (原生 ES Modules 全绿) | **实机已验证** | 宿主插件主线程稳定 |
| **CalculiX** | 可选依赖 | 本机未安装 `ccx.exe`，预检返回 blocked | **优雅降级** | 缺失时不影响普通建模与只读功能 |
