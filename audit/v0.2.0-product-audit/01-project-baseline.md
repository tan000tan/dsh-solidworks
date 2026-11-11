# dsh-solidworks-plugin v0.2.0 项目真实基线全景审计报告

> **报告编号**：`01-project-baseline`  
> **审计日期**：2026-11-02  
> **基线版本**：`v0.2.0`  
> **基线 Commit**：`7d70bc090d5cef146ac3946bb062667ae30a4cc9` (Short: `7d70bc0`)  
> **基线 Tag**：`v0.2.0` (Annotated Tag Object: `0c3ce9e2ab946462050bb91c9ad587f9f3305cd5`)  
> **仓库根目录**：[`D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin`](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin)  
> **GitHub 远端**：`https://github.com/tan000tan/dsh-solidworks`  
> **审计原则**：只读审计、保持怀疑、逐项求证、保留分歧、拒绝自我证明

---

## 一、Git 版本库与工作区真实状态核查

### 1.1 分支与 HEAD 指针
- **当前分支**：`main`
- **HEAD 状态**：严格指向 Commit `7d70bc0`
- **提交信息**：`release: finalize v0.2.0`
- **提交作者/提交者**：`tan <18460474916@163.com>`
- **提交时间**：`Sun Nov 1 21:47:44 2026 +0800`
- **变动规模**：53 个文件变更，+13,745 行，-5,032 行

### 1.2 Tag 对象核对
- **Tag 名称**：`v0.2.0`
- **Tag 类型**：Annotated Tag
- **Tag Object**：`0c3ce9e2ab946462050bb91c9ad587f9f3305cd5`
- **指向目标**：Commit `7d70bc090d5cef146ac3946bb062667ae30a4cc9`
- **历史 Tag**：`v0.1.0`（first public package）

### 1.3 工作区文件清单与纯净度分析
通过 `git status` 与 `git ls-files` 物理核实：
- **已跟踪文件（Tracked Files）**：共 371 个文件，暂存区完全干净（0 cached diffs，0 unstaged changes）。
- **未跟踪文件与目录（Untracked Files）**：
  1. [`dsh-mcp-config.json`](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/dsh-mcp-config.json)：本机专属 MCP 客户端生成配置文件（**严禁泄露与提交**）；
  2. [`dsh-solidworks-v0.2.0-git-release-report.md`](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/dsh-solidworks-v0.2.0-git-release-report.md)：上一轮本地 Git 封版执行记录；
  3. 6 个过程性归档目录（历史遗留与资产备份）：
     - `技术审计/`（历史研究、设计报告、排期与分析文档）
     - `测试代码/`（历史探索性脚本、沙箱基准目录 `sandbox_benchmark/`）
     - `项目备份/`（开发过程中阶段性备份快照）
     - `项目文档/`（历史过程性文档）
     - `项目脚本/`（市场 PR 生成、辅助分析工具）
     - `验收报告/`（历史阶段验收报告）
  4. 本地环境私有目录（已被 `.gitignore` 排除）：
     - `.venv/`（Python 3.13 虚拟环境）
     - `.dsh/`（DSH 运行时缓存）
     - `node_modules/`（若有）

---

## 二、项目元数据与核心配置审查

### 2.1 package.json 审查
- **包标识与版本**：`"name": "dsh-solidworks"`, `"version": "0.2.0"`
- **开源许可证**：`"license": "AGPL-3.0-only"`
- **模块规范**：`"type": "module"`（ES Modules），入口 `"main": "lib/index.js"`
- **CLI 接入**：`"bin": { "dsh-solidworks": "./bin/dsh-solidworks.js" }`
- **Node.js 引擎约束**：`"engines": { "node": ">=22.12" }`
- **npm 外部依赖**：**0 外部依赖**（`dependencies` 为空，纯 Node.js 内置模块驱动）
- **打包白名单 (`files`)**：
  包含 `lib`, `bin`, `scripts`, `tests`, `vendor`, `docs`, `requirements.txt`, `requirements-optional.txt`, `cordis.patch.yml`, `dsh-plugin.json`, `LICENSE`, `NOTICE`, `PROVENANCE.md`, `README.md`, `README.zh.md`, `CHANGELOG.md`。
- **打包排除防护**：根目录与 `tests/` 目录均部署 `.npmignore`，强力排除 `__pycache__` 与 `*.pyc`，实测 `npm pack --dry-run` 清单共 240 个文件（740 kB）。

### 2.2 dsh-plugin.json 审查
- **Manifest 规范版本**：`0.15`
- **插件 ID**：`dsh-solidworks.solidworks`
- **Facets**：`host` 指向 `lib/index.js`，`apiVersion: "v1alpha1"`
- **权限声明 (`permissions`)**：
  1. `dsh-solidworks.process.spawn` (subprocess): 启动 Python stdio MCP server 与环境探测；
  2. `dsh-solidworks.fs.read` (filesystem-read): 启动前校验服务端脚本路径；
  3. `dsh-solidworks.fs.write` (dsh-home): 写入审计日志 `auditLog`。
- **声明工具列表 (`x-tool-namespaces.tools`)**：共列出 68 个工具项。

### 2.3 cordis.patch.yml 审查
- 声明了在 Cordis/DSH 宿主环境中的默认加载配置：
  - `mode: "read-only"`（默认零信任只读）
  - `allowedRoots: []`
  - `grantTtlMs: 300000`
  - `pythonPath: null`（依赖自动发现）

---

## 三、代码结构与技术资产盘点

### 3.1 核心代码分层与文件清单

| 层次 | 物理路径 | 文件数 | 关键文件 / 职责 |
|---|---|:---:|---|
| **DSH 宿主适配层 (JS)** | `lib/` | 7 | `index.js` (插件入口/生命周期), `policy.js` (三级门禁/路径加固), `discover.js` (Python探测), `mcp.js` (Stdio客户端), `schema.js` (参数展开) |
| **CLI 入口 (JS)** | `bin/` | 1 | `dsh-solidworks.js` (提供 doctor, selftest, list-tools 等子命令) |
| **安装与诊断运维 (JS)** | `scripts/` | 5 | `setup.js` (一键安装), `doctor.js` (8维诊断), `upgrade.js`, `uninstall.js`, `generate_mcp_config.js` |
| **自动化测试套件 (JS+Py)** | `tests/` | 22 | 7 个 JS 宿主与策略测试；15 个 Python 单元与 CAD 实机测试 |
| **MCP 服务端引擎 (Py)** | `vendor/.../mcp-server/` | 1 | `server.py` (FastMCP 服务端，7,653 行，聚合 65 个核心 CAD 工具实现) |
| **CAD 核心逻辑库 (Py)** | `vendor/.../scripts/` | 65 | `sw_connect.py` (COM/STA调度), `cad_task_context.py` (事务/回滚), `dimension_manager.py` (尺寸管理), `feature_graph_ir.py` (DAG编译器), `shadow_backup.py` (影子备份) 等 |
| **文档与交付物料** | `docs/` | 17 | `FEATURE_MATRIX.md`, `USER_GUIDE.md`, `TROUBLESHOOTING.md`, `market-submission.md` 等 |

---

## 四、历史遗留审计与重大静态分歧发现

在只读基线分析中，通过对抗式交叉比对代码、清单和测试，发现了以下 **4 项不容忽视的静态分歧与代码隐患**：

### 4.1 【分歧 1】`lib/index.js` 内部版本号硬编码落后
- **事实**：`package.json` 与 `dsh-plugin.json` 已经定版升级为 `"0.2.0"`，但在 [`lib/index.js:33`](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/lib/index.js#L33) 中：
  ```javascript
  const PLUGIN_VERSION = '0.1.0';
  ```
- **影响**：向 DSH 宿主报告状态（`solidworks_status`）以及向 MCP 服务端握手（`client.initialize({ clientVersion: PLUGIN_VERSION })`）时，输出的版本号仍然是 `0.1.0`，造成产品版本号表现不一致。

### 4.2 【分歧 2】4 个新增 CAD 工具未收录入 `lib/policy.js` 风险表
- **事实**：`server.py` 中在 v0.2.0 新增并暴露了 4 个重要工具：
  1. `solidworks_compile_feature_graph`（特征图拓扑编译）
  2. `solidworks_identify_dimensions`（尺寸枚举与识别）
  3. `solidworks_inspect_dimension_impact`（尺寸拓扑影响分析）
  4. `solidworks_modify_dimension_safe`（自愈式安全尺寸修改）
- **缺失**：[`lib/policy.js`](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/lib/policy.js#L34-L106) 的 `RISK_TABLE` 仍保持 66 项，**未收录上述 4 个工具**；
- **连锁反应**：
  1. 运行 `node tests/probe-server.mjs --python ...` 时，该诊断测试直接失败退出（Exit 3，报 `NOT IN TABLE`）；
  2. 根据零信任安全策略，未收录工具全部降级走正则启发式或默认判定为 `HIGH` 风险。导致本应属于只读分析的 `solidworks_identify_dimensions` 与 `solidworks_inspect_dimension_impact` 在默认 `read-only` 模式下被直接扣留（withheld），普通用户在只读模式下完全无法调用！

### 4.3 【分歧 3】Python 探测逻辑（`lib/discover.js` vs `scripts/doctor.js`）严重脱节
- **事实**：
  - [`scripts/doctor.js:69-96`](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/scripts/doctor.js#L69-L96) 专门实现了探测 `.venv/` 与解析 `.venv/pyvenv.cfg` 的逻辑，因此在终端运行 `npm run doctor` 时能精准检测出 `D:\SWCAD-MCP\Python313\python.exe` 并绿灯通过；
  - 但 DSH 运行时实际调用的 [`lib/discover.js`](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/lib/discover.js) **完全没有探测项目根目录 `.venv` 的代码**！它仅探测 `C:\Python3x`、系统 PATH、`LOCALAPPDATA` 以及 `py` 启动器；
- **用户风险**：普通用户若通过 `npm run setup` 安装到本地 `.venv`，`npm run doctor` 会显示 PASS，但若在 DSH 中未手动填写 `pythonPath`，DSH 启动时将报错 `PYTHON_NOT_FOUND`！

### 4.4 【分歧 4】工具命名不一致（`solidworks_pack_and_go`）
- `dsh-plugin.json` 与 `lib/policy.js` 中声明的工具名为：`solidworks_pack_and_go`；
- `vendor/.../server.py` 中通过 `@mcp.tool()` 注册的实际函数名为：`solidworks_pack_and_go_tool`；
- 这导致该工具在 MCP 握手映射时无法正确对应策略表中该条目。

---

## 五、项目原始目标与六阶段路线图基准

对照历史技术规划（`技术审计/版本演进与发布路线图.md` 及相关档案），项目原始目标规划了六阶段演进：

1. **阶段一：独立验收与封版（v0.2.0 当前节点）**
   - 目标：夯实双层安全门禁（Fail-Closed）、常驻 STA 线程调度（`DesktopPinnedStaWorker`）、解决 CAD 建模中途崩溃回滚与特征逆序清理、达成 npm 干净打包与自动化测试 100% 绿灯。
2. **阶段二：稳定性与用户体验完善（v0.2.1 ~ v0.2.5）**
   - 目标：解决版本漂移、对齐 Python 探测、补齐策略表、完善 Windows 便捷启动与图形化报错反馈。
3. **阶段三：AI 建模能力升级（v0.3.0）**
   - 目标：Feature Graph IR 拓扑编译器无缝接入、全生命周期参数化尺寸联动、影子快照物理恢复。
4. **阶段四：CAD 业务范围扩展（v0.4.0）**
   - 目标：装配体双/多零件配合求解、工程图 A4 自动出图与尺寸标注、干涉碰撞检测。
5. **阶段五：产品化与 DSH 生态建设（v0.5.0 ~ v0.6.0）**
   - 目标：官方市场顶级推荐、零依赖绿色运行时嵌入、多模态图纸逆向提取。
6. **阶段六：高级 AI CAD 能力（v1.0.0）**
   - 目标：2D 蓝图三视图逆向 3D 实体、钣金智能展开、Toolbox 紧固件库自动化装配。

---

## 六、基线审计结论

项目基线客观事实清晰、版本指针与 Tag 严格吻合，代码具备高度扎实的工程积淀（尤其是 COM 穿透与任务回滚机制）。但**在接口契约对齐、运行时环境自发现、元数据一致性方面存在数项客观存在的明显断层**。这些断层将在后续各角色审计中进一步量化和评估。
