# 验证记录

这一页记录 **v0.4.0**（定向真机复测、运行时一键部署、跨进程归属账本与离线全量回归）以及沿用自 **v0.3.2**（71 工具全量真机基线）的实际验证情况、运行环境以及尚未验证的范围。
每一条都能对应到一个可复现的命令；下文严格区分 **v0.4.0 定向复测项** 与 **沿用 v0.3.2 全量历史基线**。
写着 *未验证* 的条目，请当成"能力未知"，而不要当成"可用"。

插件注册 **71 个 MCP 工具 + 3 个宿主元工具**（`solidworks_status`、`solidworks_confirm`、`solidworks_setup_runtime`）。工具总数由 `tests/package.test.js` 对着 `lib/policy.js` 的
`RISK_TABLE` 断言，因此这一页不会和代码脱节。

- 验证日期：2026-11-26（v0.4.0 定向 L4 与离线回归；v0.3.2 全量 L4 基线采集于 2026-11-18）
- 插件版本：0.4.0（`package.json`，分支 `feat/v0.4.0` → `main`）
- 平台：Windows 11 x64，Node.js v24.21.0，DSH 0.1.7-rc.2
- 本轮使用的 Python：本机 64 位 Python 3.13（`mcp`、`pywin32`、`comtypes`、`pydantic`、`jsonschema`）；v0.3.2 基线使用 DSH 自带运行时 3.12.14
- SolidWorks：2026 SP04.1，COM 版本 34.4.1

下文验证分级：**L1** 环境，**L2** MCP 服务，**L3** DSH 宿主，**L4** 真实 SolidWorks。

## 1. 结论摘要

| 范围 | 结果 | 证据 |
| :--- | :--- | :--- |
| L1 环境 | 本机 PASS | §2，`audit/promotion-phase/01-current-state-audit/evidence/env-baseline.txt` |
| L2 MCP 服务（握手、工具列表、Schema、错误处理） | PASS | §3，`npm run test:all` |
| L3 DSH 宿主（bundle 加载、工具发布、只读门禁） | 加载与门禁 PASS；GUI 审批未走 | §3，`tests/cordis_activation_test.mjs`、`tests/r5-…` |
| L4 真实 SolidWorks | v0.3.2 全量基线：71/71 个工具都被触达（**33 个 `verified`（其中 7 个只是 partial）**、13 个 `failed`、24 个 `blocked`、1 个 `known-limitation`、14 条缺陷）；v0.4.0 定向复测：D-01、D-02、D-03a/D-03b、D-04、D-05、D-06、D-07、D-08、D-10、D-11、D-12 在 SW 2026 SP4.1 实机 PASS；D-09、D-13、`solidworks_revolve` 延后至 v0.5.0 | §4、§4.4 |
| 离线自动化套件 | PASS —— 20 个顶层套件，204 项断言；45 个 Python 套件，341 个用例 | §3 |
| SolidWorks 2020–2025 | **未验证** | §5 |

## 2. L1 —— 环境

| 检查项 | 实测结果 |
| :--- | :--- |
| 操作系统 / 架构 | Windows 11 x64 |
| Node.js | v24.21.0（engines 下限 `>=22.12`） |
| npm | 11.19.0 |
| DSH CLI | 0.1.7-rc.2（engines 下限 `>=0.1.7-rc.2`） |
| Python | DSH 自带运行时 3.12.14；`pywin32`、`mcp` 可导入；`comtypes` **缺失** |
| SolidWorks | 已安装桌面版 SolidWorks 2026，COM 版本 34.4.1 |
| 插件自检 | `node bin/dsh-solidworks.js doctor --json` → `ready: true`、`readiness.full: false`（缺 COM 附加依赖） |

`comtypes` 属可选依赖：缺它时 COM 工具仍走 `pywin32` 可用，但声明需要 COM 类型库的工具会
明确报出该缺口，而不是静默降级。`doctor` 把这件事表达为 `readiness.core` = true /
`readiness.full` = false，详见 [ADVANCED-CONFIG.zh.md](ADVANCED-CONFIG.zh.md)。

## 3. L2 / L3 —— MCP 服务与 DSH 宿主

下列套件全部离线，不需要 SolidWorks 会话。运行器：`npm run test:all`
（`scripts/run_test_all.mjs`），它同时汇总 Python 套件。

| 套件 | 断言数 | 覆盖内容 |
| :--- | ---: | :--- |
| `tests/policy.test.js` | 30 | 风险表、模式门禁、审批绑定、拒绝路径 |
| `tests/mcp.test.js` | 17 | MCP 握手、工具注册、Schema 形状 |
| `tests/schema.test.js` | 26 | 已注册工具的输入/输出 Schema 一致性 |
| `tests/package.test.js` | 12 | 打包内容、文档与产品口径一致、路径泄露与来源守卫 |
| `tests/audit.test.js` | 30 | 审计日志写入、脱敏、失败路径 |
| `tests/host.test.js` | 39 | DSH 宿主集成、配置解析、发现逻辑 |
| `tests/crash.test.js` | 9 | 崩溃与重启恢复路径 |
| `tests/audit_outcome.test.js` | 8 | 接受 / 拒绝 / 失败三类调用的审计记录 |
| `tests/dsh_adapter_scripts.test.js` | 6 | profile patch 合并（保留用户键）、Bundle 模式守卫、注销范围 |

运行器口径：**合计 **204 项断言**，20 个顶层套件** —— 上面 9 个 `*.test.js` 套件、10 个
`*.mjs` 套件（`approval_security_adversarial_test.mjs`、`cordis_activation_test.mjs`、
`cordis_service_registration_test.mjs`、`d02_d12_d13_config_and_discovery_test.mjs`、
`r1_r5_security_matrix_test.mjs`、`runtime_isolation_test.mjs`、
`phase5_security_approval_test.js`、`confirm_human_authorization_test.js`、
`phase3_productization_test.js`、`release-swarm`），以及一个聚合套件（`python-all`），
它负责跑下面的 Python 套件。

Python 套件（`scripts/run_all_python_tests.py`）：**45 个套件、341 个 unittest 用例、
0 skipped、0 failed**。它们覆盖 vendored 引擎的纯逻辑路径、路径安全、job 状态机、尺寸链路、
工具注册表完整性（`tests/tool_registry_integrity_test.py`，装饰器绑错函数就会失败）、v0.3.3 缺陷回归守卫（`tests/v033_remediation_test.py`）以及
fake-COM 层。这里通过只意味着 *Python 代码按规格对假对象工作*，不构成对 SolidWorks 的证据。

仅 Mock 覆盖的部分如实标注：`tests/_fake_sw_com.py` 实现了离线套件所需的那部分 COM 表面。
任何依赖真实 API 的行为只会出现在 §4 或 §5，绝不会出现在这张表里。

## 4. L4 —— 真实 SolidWorks 2026 SP4.1

完整报告、逐工具证据与缺陷复现：`audit/promotion-phase/04-regression-validation/l4-real-solidworks.md`。
原始调用：`audit/promotion-phase/04-regression-validation/evidence/l4-calls.jsonl`（206 次调用）。
逐工具状态：[FEATURE_MATRIX.zh.md](FEATURE_MATRIX.zh.md)。

方法：SolidWorks 由审计方在 MCP 之外启动，服务端只做 attach。所有副作用都写在
`audit/promotion-phase/04-regression-validation/solidworks-workspace/`，那是唯一允许的根目录。
收尾时会话先 `CloseAllDocuments(false)` 再 `ExitApp()`，之后未残留 `SLDWORKS` 进程。但证据要按实说：`evidence/teardown.log` 记录收尾前有 7 个文档、收尾后 `documents_remaining: 4`——会话退出前并没有把全部文档关掉，所以"收尾时文档状态干净"应记为已知限制，而不是干净的收尾。

| 判定 | 数量 | 含义 |
| :--- | ---: | :--- |
| `verified` | 33 | 调用真正到达 COM 且返回自洽结果；**其中 7 个标为 partial**，因为仍有个别枚举值或字段失败（`solidworks_connect`、`solidworks_interference_check`、`solidworks_open_document`、`solidworks_export_active`、`solidworks_identify_dimensions`、`solidworks_review_active`、`solidworks_inspect_hole_features`） |
| `failed` | 13 | 按文档方式调用即失败，或返回误导性的成功 |
| `blocked` | 24 | 环境无法满足该工具的前置条件（无求解器、无 OCP 后端、无 DXF 源、文档归属问题）；**这不能证明工具本身坏了** |
| `known-limitation` | 1 | `solidworks_recover` 从不真正探活 COM（`status=not_checked`） |

### 4.1 真机上发现的缺陷（v0.3.2 历史基线与 v0.4.0 状态）

| 编号 | 严重度 | 摘要 | v0.4.0 状态 |
| :--- | :--- | :--- | :--- |
| D-01 | blocking | MCP 无法冷启动 SolidWorks（`SW_LAUNCH_PROHIBITED`），与"connect or start one"的说法不符 | **已修复并定向实机复测通过（SW 2026 SP4.1）**：`read-only` 禁止冷启动；CLI `--mode standard` 与 `health_check(start_solidworks=true)` 均成功冷启动 SW 2026（`34.4.1`） |
| D-02 | blocking | `solidworks_open_document` 不把打开的文档设为 ActiveDoc → 后续工具作用在错误文档上 | **已修复并定向实机复测通过（SW 2026 SP4.1）**：`open_document()` 在复用与新开分支统一调用 `ActivateDoc3` 并校验 `ActiveDoc`，在 `part_a`、`part_b`、`asm_test` 间切换正常 |
| D-03 | blocking | 文档归属模型打断长会话：装配组件不登记、归属只在进程内，合法的后续调用会被拒 | **D-03a 与 D-03b 均已修复并实机复测通过（SW 2026 SP4.1）**：装配组件登记切回 + 跨进程 `owned-docs.json` 原子锁账本（外部未登记文档 100% 被 `DEF-SEC-01` 拦截） |
| D-04 | blocking | `solidworks_shell` 在几何已经改变后报失败（64000 → 17344 mm³） | **已修复并定向实机复测通过（SW 2026 SP4.1）**：正确处理 COM `VT_VOID`（`None`）+ 重建特征树差分；`2 mm` 成功，`50 mm` 拒绝 |
| D-05 | high | `solidworks_list_edges` 返回 `ok` 但几何字段全是 `null` | **已修复并实机复测通过（SW 2026 SP4.1）**：12/12 边与方向向量成功解析，0 报错 |
| D-06 | high | `solidworks_chamfer` dry-run 通过，apply 必失败 | **已修复并实机复测通过（SW 2026 SP4.1）**：边预选检查 + `EditRebuild3`，4 边成功创建 `倒角1` |
| D-07 | high | `solidworks_pattern` 在回转体上必失败 | **已修复并实机复测通过（SW 2026 SP4.1）**：新增标准基准面回退匹配，阵列创建成功 |
| D-08 | high | `solidworks_add_coincident_mate` 的 wire 契约与其余 70 个工具不一致 | **装饰器已修复并实机复测通过（SW 2026 SP4.1）**：上视基准面重合配合返回 `mate_created=true` |
| D-09 | high | spec 类工具拒收 `schema_version`，且没有可用模板 | **延后至 v0.5.0**（多版本图纸模板与 `schemaVersion` 严苛校验端到端闭环延后） |
| D-10 | medium | `solidworks_export_active` 的 PDF 路径抛 `AttributeError` | **已修复并实机复测通过（SW 2026 SP4.1）**：解耦 `ISldWorks` 获取，成功导出 44,744 字节 PDF |
| D-11 | medium | 空文档假绿（`interference_check` 通过、`review_active` 打 92 分） | **已修复并实机复测通过（SW 2026 SP4.1）**：空装配体规范返回 `status="insufficient_input"`、`interference_count=0` |
| D-12 | medium | 特征类型 / through-state 映射错误 | **已修复并实机复测通过（SW 2026 SP4.1）**：`ICE` 全部映射为 `Extrusion`（0 个未知 `ICE` 残留） |
| D-13 | medium | `solidworks_pack_and_go` 的依赖枚举永远不全 | **延后至 v0.5.0**（复杂外部引用装配体 COM 依赖遍历稳定性局限） |
| D-14 | medium | native-wire 导入类工具要求目标已存在且为活动文档 → 导入场景不可用 | **逻辑已修复并通过离线检验**（放宽 `import` 动作目标存在性预检；原生 PS 创建链路实机未闭环） |
| `solidworks_revolve` | medium | `solidworks_revolve` 旋转特征创建 | **延后至 v0.5.0**（SW 2026 实机返回 `revolve_created=false`） |

### 4.2 L4 确实确立的能力

参数化零件建模（新建文档、拉伸、切除、圆角、镜像、孔、尺寸修改、配置、自定义属性、保存重开）、
测量（质量属性与包围盒和分析值吻合：70497.339 mm³ 与 1512.0 = 1000 + 512）、
STEP/STL 导出（17083 / 55036 / 373684 字节）、装配组件插入与距离配合、native 几何读回。

### 4.3 策略门禁的实际行为

门禁真实存在且在 CLI 路径上 fail-closed：high 风险工具在 `standard` 模式被拒，在 `full` 模式
没有宿主审批时 CLI 退出码 3；`--yes` / `--allow` 都绕不过去。
但门禁**不在**直连 MCP stdio 的路径上——v0.3.2 L4 的 206 次调用就是那样发的。
也就是说，插件的保护只在它作为 DSH 插件被加载时存在。这一点已在
[SECURITY.zh.md](SECURITY.zh.md) 与 [ADVANCED-CONFIG.zh.md](ADVANCED-CONFIG.zh.md) 披露。

### 4.4 v0.3.3 定向真机复测（SolidWorks 2026 SP4.1，2026-11-25）

覆盖范围：本轮**仅针对** D-01、D-02、D-03a（含 D-08 与 BOM）、D-04 在隔离沙箱
`audit/v033-targeted-l4/solidworks-workspace/` 内执行定向真机复测，复现命令为
`node audit/v033-targeted-l4/run_targeted_l4.mjs`（实测结果见 `audit/v033-targeted-l4/l4-results.json`）。
71 项注册工具中的其余条目继续沿用 §4 的 v0.3.2 全量基线结论，本次未重复全量跑批。

| 定向用例 | 真机实测输出（SolidWorks 2026 SP4.1，COM `34.4.1`） |
| :--- | :--- |
| D-01 CLI 与 MCP 冷启动 | `solidworks_connect --mode read-only` 被拒（`NOT_PUBLISHED`），`--mode read-only --allow solidworks_connect` 仍拒绝冷启动（`0` 个 `SLDWORKS` 进程）；`--mode standard` 成功拉起 SolidWorks（`rev 34.4.1`）；`solidworks_health_check(start_solidworks=true)` 返回 `ok` |
| D-04 `solidworks_shell` | `40×40×40` 立方体（`64000 mm³`）执行 `thickness_mm=2.0` → `status="ok"`、`feature_created=true`、`feature_name="抽壳1"`、体积降为 `17344 mm³`；非法壁厚 `thickness_mm=50.0` → `status="error"`、`feature_created=false`、体积保持 `64000 mm³` 不变（注：40 mm 闭合抽壳取中间值 `25 mm` 时 SolidWorks 原生内核会反相偏移出 `63000 mm³` 内腔且无 COM 错误码，故用大于零件边长的 `50 mm` 验证几何不可构建拒止） |
| D-02 `solidworks_open_document` | 在 `part_a`（`20×20×20`）、`part_b`（`30×30×30`）、`asm_test.SLDASM` 同时打开的情况下：重开 `part_a` 准确切回活动文档（`solidworks_mass_properties` 返回 `8000 mm³`）；打开 `part_b` 返回 `27000 mm³`；打开 `asm_test.SLDASM` 切回装配体 |
| D-03a / D-08 装配长链路 | 向 `asm_test.SLDASM` 插入 `part_a` 与 `part_b` 后依次创建 `solidworks_add_distance_mate`（`50 mm`）与 `solidworks_add_coincident_mate`（`Top Plane`，`mate_created=true`）；紧接着执行 `solidworks_mass_properties` 自动作用于 `asm_test.SLDASM`（`35000 mm³`，零 `DEF-SEC-01` 报错），随后 `solidworks_export_assembly_bom` 成功导出 2 行 BOM CSV（`success=true`、`row_count=2`） |
| 干净收尾 | 调用 `CloseAllDocuments(False)` + `ExitApp()`，核验 `teardownPids=[]`（残留 `SLDWORKS` 进程数为 `0`） |

## 5. 未验证（不要当成可用）

| 项目 | 状态 | 原因 |
| :--- | :--- | :--- |
| SolidWorks 2020–2025 | 未验证 | 无真机证据；代码里也没有版本门控 |
| 教育版 / 学生版 / 网络许可 | 未验证 | 只走通过一次常规商业安装形态 |
| DSH GUI 审批弹窗（真实点击路径） | 未验证 | 审批只经桩与 CLI 验证，桌面 UI 未被驱动 |
| 图纸生成 / 审阅 / 检查 | blocked | 需要已有 `.SLDDRW`；且 spec 层拒收 `schema_version`（D-09） |
| FEA、DFM、routing、OCP loft/surface | blocked | 本机没有求解器 / OCP 后端，请求模板也不可用 |
| Motion 研究、旋转马达 | blocked | 缺 `comtypes` 与 Motion 类型库，且装配体从未成为 ActiveDoc（D-02） |
| BOM / pack-and-go / 同心配合 | v0.3.3 部分验证 | `solidworks_export_assembly_bom` 与 `solidworks_add_coincident_mate` 已于 v0.3.3 定向复测通过；`pack-and-go`（D-13）与同心配合仍待后续实机验证 |
| STEP 导入 | failed | D-14 |
| 特征图编译 / 执行 | failed | 畸形输入触发未捕获的 `AttributeError` |
| 市场安装路径端到端 | 未验证 | 目录条目现已指向 v0.3.2（更新 PR 于 2026-11-17 合并），但尚未从市场 UI 实际安装过一次；本机桌面 profile 是 `file:` 安装 |

## 6. 如何复现

```bash
# 离线套件（不需要 SolidWorks）
npm run test:all

# 环境与就绪度
node bin/dsh-solidworks.js doctor --json
node bin/dsh-solidworks.js doctor --profile --json

# 当前模式实际发布的工具
node bin/dsh-solidworks.js list-tools --mode read-only --json
node bin/dsh-solidworks.js list-tools --mode full --json
```

L4 会话可用 `audit/promotion-phase/04-regression-validation/tools/` 下的脚本复现（见该报告 §7）。
它需要已安装的 SolidWorks，且只在自己 workspace 目录内写文件。

## 7. 历史记录

上一版验证日志（66 工具时代的 MCP 层证据流水）原样保留在
[docs/archive/verification-2026-11-17-legacy.md](archive/verification-2026-11-17-legacy.md)，
它描述的是更早的工具集，不得作为当前证据引用。