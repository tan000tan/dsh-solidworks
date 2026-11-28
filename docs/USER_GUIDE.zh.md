# dsh-solidworks 用户指南（v0.3.2）

本指南面向第一次使用本插件的 SolidWorks 用户，只描述仓库源码中真实存在的行为：不承诺源码里没有的能力，也不把"未验证"写成"已验证"。文末列出编写时核对过的源码位置。

适用版本：插件 0.3.2；Windows 10 / 11 x64；DSH `>=0.1.7-rc.2`；Node `>=22.12`；Python 3.10+ x64。

## 1. 这个插件做什么

`dsh-solidworks` 是 DeepSeek Harness（DSH）的插件。它在本机启动一个 Python MCP 服务（`vendor/solidworks-automation-skill/mcp-server/server.py`），通过 COM 连接本机安装的 SolidWorks，并把这个服务提供的工具发布给 DSH 里的 AI 助手。当前注册 74 个 CAD 工具；DSH 宿主侧另有 2 个元工具（`solidworks_status`、`solidworks_confirm`），合计 73 个。

| 能做什么 | 不能做什么 |
| --- | --- |
| 只读查看 SolidWorks 当前文档的质量属性、包围盒、尺寸清单 | 不检测、也不限制 SolidWorks 版本：代码里没有版本门控或版本探测 |
| 在 `standard` 模式下新建零件、草图拉伸、修改尺寸、打开文档 | 不做 GUI 点击，也不录制/回放宏；只走 COM API |
| 在 `full` 模式下保存、导出、关闭文档，每次由 DSH 宿主弹出人类审批 | `read-only` 下写类与高危工具不会出现在工具列表里，不是"调用报错"而是"没有这个工具" |
| 尺寸修改路径带影子备份，异常时优先用影子文件还原 | 不是"每次几何修改都自动备份"；草图、特征等其他路径没有通用回滚 |
| 生成工程图、批量导出等（高危，需 `full`） | 不能绕过审批；`solidworks_confirm` 自确认接口恒被拒绝 |
| 用 `doctor` / `list-tools` 自检运行环境与当前模式下发布哪些工具 | 本机没装 SolidWorks 时拿不到任何 CAD 工具，插件会降级为只发布 `solidworks_status` |

## 2. 前置条件

- Windows 10 或 Windows 11，x64。
- DSH `>=0.1.7-rc.2`。
- Node.js `>=22.12`。
- Python 3.10+（x64）。安装时勾选 "Add python.exe to PATH" 会省事，但不是必须——DSH 自带 runtime 与 DSH 插件设置里的 `pythonPath` 都可以用（见 TROUBLESHOOTING 第 2 节）。
- SolidWorks 已安装，且**至少手动启动过一次**。COM 注册通常在首次启动时完成；从未启动过的机器上，插件无法创建 SolidWorks 实例。
- 授权：标称支持 SolidWorks 2020–2026。本项目实机只在 SolidWorks 2026 SP4.1（Windows 11 x64）上验证过，其他版本未验证。专业版/教育版之间的授权差异也未验证；历史记录中出现过教育版授权过期导致的 `MK_E_UNAVAILABLE`（该字符串在当前代码里已无硬编码，属于运行时 COM 报错）。
- 磁盘：插件会在仓库目录内创建 `.venv`，需要几百 MB 空间。

## 3. 第一次使用

### 3.1 安装依赖

在仓库目录执行：

```bash
npm run setup
```

它做的事：探测 Python 3.10+，在仓库内创建/复用 `.venv`，用 pip 安装 `requirements.txt`（`mcp`、`pydantic`、`pywin32`、`comtypes`、`jsonschema`），如果 `win32com` 导入失败则调用 `pywin32_postinstall.py -install -silent` 注册 COM，最后如果检测到 DSH 桌面 profile，就把插件条目写进该 profile 的 `cordis.patch.yml`。

它不做的事：不修改系统 Python、不修改 PATH、不改 PowerShell 执行策略、不静默写 `dsh-mcp-config.json`。唯一可能产生的注册表写入就是上面那次 pywin32 COM 注册（具体键位见 [INSTALL.zh.md](INSTALL.zh.md#setup-绝不会做的事)）。默认使用清华源并附加官方源备用；`--aliyun` 切阿里云源；`--official` / `--no-mirror` 不用镜像；`--tsinghua` 会被当作默认分支处理（源码里没有独立的清华分支）。首选源失败后会自动切官方源重试一次。

### 3.2 体检

```bash
npm run doctor
node bin/dsh-solidworks.js doctor --json
```

`npm run doctor` 跑 12 个维度并写出 `diagnostic-report.json` / `diagnostic-report.md`；`doctor --json` 只输出结构化结果（`plugin`、`host`、`python`、`server`、`solidworks`、`ready`、`nextSteps`），不写文件，可以随时跑。两者都只读，不需要 SolidWorks 处于运行中。

### 3.3 在 DSH 里启用插件

在 DSH 的插件列表/插件设置里启用 `dsh-solidworks`（由市场安装的插件位于 profile 的 `node_modules` 下）。安装或修改 `cordis.patch.yml` 之后必须**完全退出并重启 DSH** 才生效——只刷新页面不够。

启用后先问一句："调用 `solidworks_status` 看看插件状态。" 返回里应有 `policy.mode`、`connection.running`、已注册工具数。如果 `connection.running` 为 `false`，先看 `connection.error` 与 `connection.stderr`（最后 10 行），再按 TROUBLESHOOTING 处理。

### 3.4 第一次只读对话示例

默认模式是 `read-only`，此时只能做只读操作。先在 SolidWorks 里手动打开一个零件，然后在 DSH 里输入：

> 先调用 `solidworks_health_check` 确认 SolidWorks 连接正常，再用 `solidworks_mass_properties` 告诉我当前零件的质量和体积。

助手应依次调用 `solidworks_health_check` 与 `solidworks_mass_properties`。这两个工具在风险表里都是 `read` 级，`read-only` 下可用。若想同时看外形尺寸，可加 `solidworks_bounding_box`；想看可改的尺寸名，用 `solidworks_identify_dimensions`。

## 4. 从只读到建模

建模需要把策略模式从 `read-only` 改成 `standard`。这是**改配置 + 重启**，不是在对话里说一句"切到 standard"就行：

1. 在 DSH 的插件设置里把 `mode` 改成 `standard`；或直接编辑 profile 的 `cordis.patch.yml`，把 `config.mode` 从 `read-only` 改为 `standard`。
2. 完全退出 DSH 并重新启动。
3. 用 `solidworks_status` 确认 `policy.mode` 已是 `standard`；也可以用 `npm run list-tools -- --mode standard` 在命令行预览该模式下会发布哪些工具。

`read-only` 下写类工具（`solidworks_open_document`、`solidworks_new_document`、`solidworks_create_basic_part`、`solidworks_sketch_and_extrude`、`solidworks_update_dimension` 等）根本不会注册；`standard` 下它们会出现，但保存/导出/关闭这类 `high` 级工具仍然不可用。

第一次建模对话示例：

> 新建一个 60 × 40 × 20 mm 的长方体零件，然后告诉我它的体积。

助手通常会先用 `solidworks_new_document` 建文档，再用 `solidworks_create_basic_part`（或 `solidworks_sketch_and_extrude`）建几何，最后可能需要 `solidworks_update_dimension` 调尺寸。文件还没保存——保存属于 `high` 级，见第 5 节。

## 5. 高风险操作与确认

`full` 模式才允许保存、导出、关闭：`solidworks_save_document`、`solidworks_export_active`、`solidworks_batch_export_files`、`solidworks_close_documents`、`solidworks_pack_and_go` 等，以及 `solidworks_modify_dimension_safe`、`solidworks_execute_feature_graph`、`cadstudio_run_fea` 这类高危工具。

每一次高危调用都会在 DSH 宿主里弹出交互式人类审批；审批按"工具名 + 参数摘要"绑定，不能预先批发。宿主里没有可用的审批通道时，调用会失败关闭，返回 `APPROVAL_CHANNEL_UNAVAILABLE`（"Failing closed"）——这是设计行为，不是 bug。

`solidworks_confirm` 已禁用自确认：它永远返回 `status: refused`、`code: SELF_APPROVAL_PROHIBITED`。AI 不能自己给自己发授权，命令行也没有 `approve` / `reject` 子命令（已移除，返回 `APPROVAL_CLI_REMOVED`）。导出的目标路径还必须落在允许的根目录内（`allowedRoots`，默认为会话工作目录），否则报 `Access denied: ... is outside allowed roots (DSH_ALLOWED_ROOTS)`。

## 6. 三个典型工作流

**A. 读模型属性（`read-only`）**：在 SolidWorks 里手动打开零件 → `solidworks_health_check` → `solidworks_mass_properties`（质量、体积、重心）→ 需要时 `solidworks_bounding_box`、`solidworks_identify_dimensions`。全程不改文档。注意 `solidworks_open_document` 是写级工具，`read-only` 下不可用，所以这一步必须人工打开。

**B. 改尺寸（`standard`）**：`solidworks_open_document` 打开零件（或人工打开）→ `solidworks_identify_dimensions` 找到尺寸名 → `solidworks_update_dimension` 改值 → 重建后读取新尺寸复核。这条路径带影子备份（`ShadowBackupManager` 只被尺寸管理相关代码使用），异常时可尝试还原；它**不**覆盖草图、特征等其他修改。

**C. 导出 PDF 或 STEP（`full` + 人类审批）**：先 `solidworks_save_document` 存盘，再 `solidworks_export_active` 指定 `output_path` 与 `export_format`（如 `pdf` / `step`）。每次保存与导出都会弹审批；输出目录必须在 `allowedRoots` 内。

## 7. 出问题时怎么办

先看 `docs/TROUBLESHOOTING.zh.md`。三条最常见的判断：

1. **DSH 里工具很少或只有 `solidworks_status`**：多数是 Python 依赖探测失败导致插件降级，不是权限问题。跑 `node bin/dsh-solidworks.js doctor --json`：健康的报告里有 `python.version` 与 `python.comDeps`；`python.state` 字段**只在探测失败时**出现。
2. **建模工具"消失"**：先看 `policy.mode`。`read-only` 下不发布写类/高危工具，这是预期行为；要建模就按第 4 节改成 `standard` 并重启。
3. **连接不上 SolidWorks**：先手动启动 SolidWorks、关掉模态对话框，再重试 `solidworks_health_check`；仍失败看 TROUBLESHOOTING 第 8 节（COM）。

## 8. 已知限制

1. 仅支持 Windows（win32 x64）；不支持 macOS / Linux。
2. SolidWorks 标称 2020–2026，但本项目只在 SolidWorks 2026 SP4.1（Windows 11 x64）实机验证过，其他版本未验证。
3. 默认 `read-only`，多数建模、保存、导出工具不可用；必须改配置并重启 DSH 才能建模。
4. 备份只覆盖尺寸修改路径，没有通用回滚；"所有修改都能回滚"不成立。
5. 没有 GUI 自动化，也没有宏录制/回放，只通过 COM API 操作。
6. 专业版/教育版授权差异未验证；教育版授权过期时可能遇到 `MK_E_UNAVAILABLE`。
7. 每个工具的实机覆盖情况见 `docs/FEATURE_MATRIX.md`：v0.3.2 的真机走查里，74 个工具中 33 个 verified（7 个只验证了主路径）、13 个 failed、24 个因前置不满足 blocked。矩阵由运行日志重新生成，不要在别处复制这些数字。

## 9. 反馈入口

到 GitHub Issues 提交，按问题类型选模板：

- `Bug report (tools / runtime)` —— 工具行为、运行时错误。
- `Installation problem` —— 安装、依赖、Python 环境问题。
- `Real SolidWorks validation report` —— 在某版本 SolidWorks 上的实机验证结果。
- `Feature request` —— 新功能请求。

提交前请附上 `node bin/dsh-solidworks.js doctor --json` 的输出（可对路径做脱敏）与 `solidworks_status` 的返回。

## 10. 源码依据

- `lib/policy.js:21-23` —— 风险分级常量 READ / WRITE / HIGH。
- `lib/policy.js:28-106` —— 逐工具风险表（`solidworks_health_check`、`solidworks_mass_properties`、`solidworks_open_document`、`solidworks_update_dimension`、`solidworks_save_document`、`solidworks_export_active` 等）。
- `lib/policy.js:125-133` —— 未知工具默认按 HIGH 处理。
- `lib/policy.js:200`、`212-213` —— 默认模式 `read-only`，模式只接受 `read-only | standard | full`。
- `lib/policy.js:321-329` —— `read-only` 只发布 READ，`standard` 排除 HIGH。
- `lib/policy.js:430-441` —— 模式拒绝返回 `POLICY_MODE` 及提示文案。
- `lib/index.js:49-59` —— `mode`、`toolTimeoutMs`（300000）、`startTimeoutMs`（60000）、`pythonPath` 等配置项。
- `lib/index.js:293-345` —— `solidworks_status` 与恒被拒绝的 `solidworks_confirm`（`SELF_APPROVAL_PROHIBITED`）。
- `lib/index.js:493-507` —— 按策略过滤后注册工具并打印 published/withheld 数量。
- `lib/index.js:554-575` —— 无宿主审批通道时失败关闭（`APPROVAL_CHANNEL_UNAVAILABLE`）。
- `lib/index.js:241-243` —— `solidworks_status` 的连接诊断字段（`running` / `error` / `stderr`）。
- `lib/discover.js:283-287` —— `pythonPath` 优先且失败即返回 `PYTHON_INVALID`，不回退。
- `lib/discover.js:323` —— Python 依赖缺失时的报错文案（含"加载期默认禁止自动联网安装依赖"）。
- `scripts/setup.js:308-320` —— 镜像选择逻辑（默认清华 + 官方备用；`--aliyun`；`--official`/`--no-mirror`）。
- `scripts/setup.js:381-430` —— 仅在 `win32com` 导入失败时执行 `pywin32_postinstall.py -install`。
- `scripts/setup.js:432-445` —— 不静默写 MCP 直连配置；写 DSH profile patch。
- `scripts/doctor.js:367-407` —— `SOLIDWORKS_VERSION_TIER` 只是解析固定的版本字符串并打印矩阵，不是运行时版本探测。
- `scripts/uninstall.js:24-25` —— `--dry-run` 与 `--yes`。
- `vendor/solidworks-automation-skill/mcp-server/server.py:8448` —— 受支持的 MCP 协议版本集合（与 SolidWorks 版本无关）。
- `vendor/solidworks-automation-skill/mcp-server/server.py:3976-3977` —— `read-only` 下禁止 `start_solidworks=True`。
- `vendor/solidworks-automation-skill/mcp-server/server.py:4653` 等 —— 路径越界报错 `Access denied: ... outside allowed roots (DSH_ALLOWED_ROOTS)`。
- `vendor/solidworks-automation-skill/scripts/shadow_backup.py:24` —— `ShadowBackupManager`（仅尺寸修改路径使用）。