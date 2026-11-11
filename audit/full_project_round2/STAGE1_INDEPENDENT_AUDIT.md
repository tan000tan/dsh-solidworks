# 第一阶段独立追溯审计报告：基础架构与审计准备

> **报告编号：** `AUDIT-R2-02-STAGE1-INDEPENDENT-AUDIT`  
> **审计对象：** dsh-solidworks 第一阶段（基础架构、MCP 通信、安全门禁与缺陷闭环）  
> **归档目录：** `audit/full_project_round2/`  
> **审计性质：** 独立第三方追溯复核  

---

## 一、第一阶段原始目标与范围追溯

第一阶段（Phase 1）核心目标是构建坚固、安全、合规的插件基础架构，为 DSH（DeepSeek Harness）与 SolidWorks 之间的自动化交互奠定通信和安全底座。其原始范围包含：

1. **项目骨架与协议通信：** 建立基于 Node.js 的 DSH 插件宿主，通过 stdio 管道拉起 Python FastMCP 服务端，实现双向 JSON-RPC 通信与工具发现。
2. **三级安全策略控制 (Policy Engine)：** 实现只读 (`read-only`)、标准 (`standard`) 和完全 (`full`) 三级权限模式，定义严格的工具风险等级表 (`RISK_TABLE`)，阻止未授权写入与高危系统操作。
3. **路径沙箱与穿越防御：** 实现物理真实路径解析 (`realpath`)、祖先目录回溯遍历校验、Windows 目录联接 (Junction Point) 逃逸防护、DOS 保留设备名与 UNC 路径拦截（Fail-Closed 原则）。
4. **历史缺陷闭环治理：** 彻底修复初期发现的 DEF-01、DEF-02、DEF-03、DEF-04 四大阻断性缺陷，并固化自动化防回归测试。

---

## 二、基础架构与通信机制审查

### 2.1 架构分层与通信通道
- **宿主层 (`lib/index.js`, `lib/policy.js`, `lib/discover.js`)：** 作为 DSH Agent 的前置受信任层，拦截所有外部工具调用，执行安全策略匹配与参数规范化改写。
- **通信中介 (`tests/probe-server.mjs`, `lib/index.js:makeClient()`)：** 采用标准 JSON-RPC 2.0 协议 over stdio，支持请求超时中断 (`timeoutSeconds`)、客户端强制取消 (`AbortSignal`) 与心跳检测。
- **服务端 (`vendor/.../server.py`)：** 采用 FastMCP 框架，对外暴露 71 个原子与高级建模工具，底层调度 STA 单线程工作进程 (`sw_connect.py`) 与 SolidWorks COM 接口交互。

### 2.2 通信鲁棒性与异常隔离
- **超时与悬挂防护：** 当底层 COM 操作阻塞或 SolidWorks 弹出模态对话框时，Node.js 宿主具备 30 秒硬超时中断机制，防止 DSH Agent 宿主主线程发生死锁（见 `tests/mcp.test.js:81`）。
- **进程生命周期：** 插件关闭时通过 `close()` 释放管道并发送关闭信号，具备幂等性（见 `tests/mcp.test.js:100`）。

---

## 三、安全策略与沙箱防护深度对抗审查

审计团队对 `lib/policy.js` 实施了对抗性安全测试，核查结果如下：

### 3.1 工具权限分类与默认拒绝 (Fail-Closed)
- **显式分类全覆盖：** 全量 71 个 MCP 工具均在 `RISK_TABLE` 中显式分配为 `READ`、`WRITE` 或 `HIGH`，不存在任何遗漏（见 `tests/package.test.js:121`）。
- **未知工具默认归入 HIGH：** 若外部注入未声明工具，策略引擎强制归入 `HIGH` 风险并拒绝在常规模式下调用（见 `tests/policy.test.js:21`）。
- **只读模式绝对防写：** 在 `read-only` 模式下，所有写入工具和高危工具均被彻底拦截，仅暴露 19 个只读查询工具。

### 3.2 路径安全与边界逃逸防御
- **路径穿越防御 (`..` 攻击)：** 输入 `allowed_dir/../../Windows/System32` 等相对路径穿越尝试，均被物理解析拦截并报错拒绝（`tests/policy.test.js:120`）。
- **Windows Junction（软链接/联接点）逃逸：** 若攻击者在受信任工作区内创建指向系统核心盘的 Junction，策略引擎通过深度祖先回溯 (`fs.realpathSync`) 探测到真实物理路径越界，并实施强制拦截（`tests/policy.test.js:176`）。
- **DOS 设备与 UNC 远程泄露：** 对 `CON`, `PRN`, `AUX`, `NUL` 等 Windows 保留名称，以及 `\\attacker-host\share` 形式的 UNC 路径实施无条件物理拒绝，阻断潜在的 SMB NTLM 哈希窃取风险（`tests/policy.test.js:248`）。

---

## 四、历史缺陷 (DEF-01 ~ DEF-04) 专项闭环穿透核查

本阶段审计重点逐行核对历史 4 大缺陷的修复代码与测试证据：

| 缺陷 ID | 原始缺陷性质 | 修复代码位置 | 验证测试用例 | 证据等级 | 当前核验状态 |
|:---|:---|:---|:---|:---:|:---:|
| **DEF-01** | `lib/discover.js` 忽略本地 `.venv`，导致独立环境用户报 `PYTHON_NOT_FOUND` | `lib/discover.js:38-72`（加入项目根目录 `.venv` 探测，优先级高于全局 PATH） | `tests/mcp.test.js:121`, `128`, `137` | **E2** | **PASS（彻底根治，3项回归测试全绿）** |
| **DEF-02** | 4 个关键工具未录入 `lib/policy.js` 风险表，导致标准模式下被误判为未知高危而无法调用 | `lib/policy.js:10-52`（补齐 `solidworks_identify_dimensions`, `solidworks_inspect_dimension_impact`, `solidworks_compile_feature_graph`, `solidworks_modify_dimension_safe`） | `tests/package.test.js:121-133`（严格断言 19 read, 26 write, 26 high） | **E2** | **PASS（全量 71 项无缝覆盖）** |
| **DEF-03** | `lib/index.js` 内部常量硬编码为 `0.1.0`，与 `package.json` (`0.2.0`) 版本不一致 | `lib/index.js:33`（更新常量为 `0.2.0`） | `tests/mcp.test.js:113`（三文件版本一致性断言） | **E2** | **PASS（三方版本完全对齐）** |
| **DEF-04** | 服务端工具名为 `solidworks_pack_and_go_tool`，前端清单为 `solidworks_pack_and_go`，造成命名失配 | `vendor/.../server.py:6571`（移除 `_tool` 后缀，保持前后端命名完全一致） | `tests/mcp.test.js:149`（工具名称与清单一致性单测） | **E2** | **PASS（前后端统一）** |

---

## 五、遗留技术债务与改进项核查

1. **`server.py` 上帝文件规模过大 (DEF-07)：**
   - 当前 FastMCP 服务端文件 `server.py` 膨胀至 7600+ 行，集成了工具注册、参数校验、异常包装与大量内联代码，可维护性较差，应在后续阶段重构为模块化路由分发。
2. **审计日志轮转机制缺失 (DEF-08)：**
   - 当前审计日志以单文件追加写入，长期运行可能存在无限制膨胀风险，需在产品化阶段增加基于大小与日期的切片轮转策略。

---

## 六、第一阶段独立审计最终裁决

| 审查维度 | 核心标准要求 | 实际实现与证据状态 | 状态裁决 |
|:---|:---|:---|:---:|
| **架构完整性** | 模块解耦、通信稳定、协议合规 | Node.js 宿主与 Python FastMCP 通信顺畅，全套单测无报错 | **PASS** |
| **安全门禁机制** | 权限分级完整，沙箱与防逃逸有效 | 27 项安全策略测试全部通过，物理路径防穿越严格闭环 | **PASS** |
| **历史缺陷修复** | DEF-01 至 DEF-04 彻底根除 | 源码已落地修复，测试套件针对性覆盖，无回归现象 | **PASS** |
| **打包物料规范** | 无字节码残留，路径敏感信息脱敏 | 12 项 package 单测全部通过，脱敏合规 | **PASS** |

### 最终裁决：
**ACCEPTED（合格验收）**  
第一阶段基础架构扎实，通信可靠，安全门禁逻辑完备且经过严格回归测试。历史发现的四大阻断性缺陷已全部关闭且具备完备防回归测试。第一阶段能力可作为后续阶段信赖的坚实底座。
