# 缺陷与风险登记册 (Defect & Risk Register)

> **报告编号**：`06-defect-risk-register`  
> **审查版本**：v0.2.0 (Commit: `7d70bc0`)  
> **分类标准**：严格区分“当前版本承诺缺陷”、“用户体验与上架阻塞”与“未来路线图愿景”。拒绝将远期特性缺失夸大为 P0。  
> **等级定义**：  
> - **P0 (严重问题)**：导致用户资产损失、系统性崩溃、核心流程完全阻断或存在高危安全漏洞；  
> - **P1 (重要问题)**：主要功能不可靠、关键体验存在严重断层、发布物料契约违背或影响正式上架；  
> - **P2 (一般问题)**：局部接口缺陷、死路径、缺乏自动化门禁或技术债务累积；  
> - **P3 (改进建议)**：体验润色、代码重构、性能观测或长远架构增强。

---

## 一、全量缺陷与风险总览表

| Issue ID | 缺陷标题 | 所属模块 | 风险等级 | 是否影响发布 | 推荐解决版本 |
|:---:|---|---|:---:|:---:|:---:|
| **DEF-01** | 普通用户环境自发现断层：强制手动编辑 YAML 且 discover 忽略 .venv | `lib/discover.js` / 安装流程 | **P1** | **是 (影响大众体验)** | **v0.2.1** |
| **DEF-02** | 4 个先锋工具未收录进 policy.js 风险表，导致标准模式下成为死路径 | `lib/policy.js` | **P1** | **是 (影响功能完整性)** | **v0.2.1** |
| **DEF-03** | `lib/index.js:33` 内部硬编码版本号落后（依然显示 0.1.0） | `lib/index.js` | **P1** | **是 (影响市场一致性)** | **v0.2.1** |
| **DEF-04** | Pack and Go 工具前后端命名失配（`_tool` 后缀） | `server.py` / `dsh-plugin.json` | **P2** | **否** | **v0.2.1** |
| **DEF-05** | 默认只读模式拒绝建模时缺乏用户友好的中文化引导向导 | `lib/index.js` / Policy 反馈 | **P2** | **否** | **v0.2.1** |
| **DEF-06** | `package.json` 的 npm test 遗漏 Python 离线测试与 probe 诊断门禁 | `package.json` / 测试套件 | **P2** | **否** | **v0.2.1** |
| **DEF-07** | `mcp-server/server.py` 达到 7,653 行，呈现上帝文件技术债务 | `mcp-server/server.py` | **P2** | **否 (技术债务)** | **v0.3.0** |
| **DEF-08** | 审计日志文件 `config.auditLog` 缺乏大小切片与自动轮转机制 | `lib/index.js` (audit) | **P2** | **否** | **v0.2.2** |
| **DEF-09** | JavaScript 宿主层缺乏 TypeScript `.d.ts` 类型定义声明 | `lib/` 宿主层 | **P3** | **否** | **v0.3.0** |
| **DEF-10** | 长耗时 COM 操作（复杂模型重建）缺乏心跳事件机制 | `sw_connect.py` / Worker | **P3** | **否** | **v0.3.0** |

---

## 二、缺陷深度分析卡片 (P1 & P2 详述)

### 【DEF-01】普通用户环境自发现断层：强制手动编辑 YAML 且 discover 忽略 .venv
- **所属模块**：`lib/discover.js` / 安装与配置向导
- **对应功能**：Python 运行时自动探测与宿主加载
- **发现视角**：客户与大众用户、DSH 官方市场审核者
- **问题描述**：
  - `scripts/doctor.js` 能识别本地 `.venv`，但运行时核心 `lib/discover.js` 仅检查 `C:\Python3x`、系统 PATH 与 `py` 启动器，**完全不检查项目根目录的 `.venv`**；
  - 若 Python 未加入系统 PATH，用户即使运行了 `npm run setup`，DSH 加载依然报错 `PYTHON_NOT_FOUND`；
  - 用户必须手工打开深层隐藏目录下的 `cordis.patch.yml` 并手写 Python 绝对路径。
- **复现条件**：在一台干净机器上，将 Python 安装在非系统盘（如 `D:\SWCAD-MCP\Python313`）且不加入 PATH，从市场安装插件。
- **用户影响**：普通小白用户 100% 无法启动插件，直接流失。
- **风险等级**：**P1 (重要问题)**
- **是否影响发布**：**影响大众发布**（开发者预览可暂时通过指南规避）。
- **推荐修复方式**：
  1. 在 `lib/discover.js` 中增加扫描 `path.join(pluginRoot, '.venv')` 及其 `pyvenv.cfg`；
  2. 提供开箱即用内置便携 Python（Embedded Portable Python）。
- **推荐版本**：**v0.2.1**

---

### 【DEF-02】4 个先锋工具未收录进 policy.js 风险表，导致标准模式下成为死路径
- **所属模块**：[`lib/policy.js`](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/lib/policy.js#L34-L106) / `RISK_TABLE`
- **对应功能**：Feature Graph 编译与全生命周期尺寸管理（`solidworks_compile_feature_graph`, `solidworks_identify_dimensions`, `solidworks_inspect_dimension_impact`, `solidworks_modify_dimension_safe`）
- **发现视角**：架构师与代码质量审查者、QA 工程师、第三方开发者
- **问题描述**：
  - `server.py` 在 v0.2.0 新增了这 4 个工具，但在 `lib/policy.js` 中未收录；
  - 导致这 4 个工具触发未知工具防御机制，默认归入 `HIGH` 风险；
  - 在日常的 `standard` 模式下直接被过滤扣留，根本不会发布给 DSH 宿主，成为“代码已实现、上层无法访问”的死路径；
  - 运行 `node tests/probe-server.mjs` 诊断脚本直接报 Exit Code 3 失败。
- **复现条件**：运行 `node tests/probe-server.mjs --python ...`。
- **用户影响**：AI 无法使用这 4 个高级工具，参数驱动修改能力在前端无法生效。
- **风险等级**：**P1 (重要问题)**
- **是否影响发布**：**影响完整发布**。
- **推荐修复方式**：
  在 `lib/policy.js` 的 `RISK_TABLE` 中补充这 4 个条目：
  - `solidworks_identify_dimensions: READ`
  - `solidworks_inspect_dimension_impact: READ`
  - `solidworks_compile_feature_graph: WRITE`
  - `solidworks_modify_dimension_safe: WRITE`
- **推荐版本**：**v0.2.1**

---

### 【DEF-03】`lib/index.js:33` 内部硬编码版本号落后（依然显示 0.1.0）
- **所属模块**：[`lib/index.js:33`](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/lib/index.js#L33)
- **对应功能**：版本状态自检（`solidworks_status`）与 MCP 初始化握手
- **发现视角**：DSH 官方市场审核者、基线审查
- **问题描述**：
  ```javascript
  const PLUGIN_VERSION = '0.1.0';
  ```
  `package.json` 与 `dsh-plugin.json` 均已更新为 `0.2.0`，但该常量未同步。
- **用户影响**：用户运行 `solidworks_status` 时看到插件版本报告为 `0.1.0`，造成版本混乱。
- **风险等级**：**P1 (重要问题)**
- **是否影响发布**：**影响市场元数据一致性**。
- **推荐修复方式**：
  修改为从 `package.json` 动态读取或手动纠正为 `const PLUGIN_VERSION = '0.2.0';`。
- **推荐版本**：**v0.2.1**

---

### 【DEF-04】Pack and Go 工具前后端命名失配（`_tool` 后缀）
- **所属模块**：`vendor/.../server.py:6571`
- **对应功能**：`solidworks_pack_and_go`
- **发现视角**：架构师、基线比对
- **问题描述**：
  前台与清单注册名为 `solidworks_pack_and_go`，后台注册名为 `solidworks_pack_and_go_tool`，造成名称失配。
- **风险等级**：**P2 (一般问题)**
- **是否影响发布**：否（非常用核心工具）。
- **推荐修复方式**：后台对齐前台命名，移除 `_tool` 后缀或做双向别名兼容。
- **推荐版本**：**v0.2.1**

---

### 【DEF-05】默认只读模式拒绝建模时缺乏用户友好的中文化引导向导
- **所属模块**：`lib/index.js: makeExecutor()`
- **对应功能**：操作被拒绝反馈（`status: 'refused'`）
- **发现视角**：客户与大众用户、产品经理
- **问题描述**：
  当用户初次使用要求 AI 画零件时，返回的是英文技术错误码：
  `{ status: 'refused', code: 'POLICY_MODE', message: 'solidworks_create_basic_part is disabled by policy (mode=read-only)' }`
  缺乏“您当前处于只读保护模式，如需建模，请将配置文件中的 mode 改为 standard”的温馨中文指引。
- **风险等级**：**P2 (一般问题)**
- **推荐修复方式**：在返回的 `message` 中追加新手引导文案与切换建议。
- **推荐版本**：**v0.2.1**

---

### 【DEF-06】`package.json` 的 npm test 遗漏 Python 离线测试与 probe 诊断门禁
- **所属模块**：`package.json` 的 `scripts.test`
- **对应功能**：持续集成与测试自动化
- **发现视角**：QA 工程师
- **问题描述**：
  `npm test` 仅执行 4 个 JS 脚本，未能联动执行 35 个 Python 离线单元测试和 `probe-server.mjs`。
- **风险等级**：**P2 (一般问题)**
- **推荐修复方式**：将 Python 离线单元测试扩充进 `npm test` 命令。
- **推荐版本**：**v0.2.1**
