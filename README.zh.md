[![Release](https://img.shields.io/badge/version-0.3.3-blue.svg)](https://github.com/tan000tan/dsh-solidworks/releases)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%203.0-green.svg)](LICENSE)
[![Platform: Windows x64](https://img.shields.io/badge/Platform-Windows%20x64-lightgrey.svg)](docs/INSTALL.zh.md)
[![SolidWorks: 2026 tested](https://img.shields.io/badge/SolidWorks-2026%20tested-brightgreen.svg)](docs/verification.zh.md)

# dsh-solidworks

> 一个 MCP 服务器 + DeepSeek Harness 插件，把 AI 助手接上你自己电脑上正在运行的 SolidWorks：它可以读取模型、测量模型，并在你选定的权限模式和你的确认之下创建和修改几何。

- 插件包：`dsh-solidworks`，AGPL-3.0-only
- 执行引擎：`solidworks-automation-skill` Python MCP 服务器（MIT，内嵌于 `vendor/`，见 `NOTICE`）
- 英文文档：[README.md](./README.md)

---

## 这是什么

`dsh-solidworks` 在本机启动一个 MCP 服务器，通过 COM API 驱动 SolidWorks。DeepSeek Harness（或任意标准 MCP 客户端）与该服务器通信，于是对话式 AI 可以处理已经打开的 CAD 文档，也可以替你打开文档再处理。

- **纯本地**：服务器运行在你的 Windows 机器上，控制的是同一台机器上的 SolidWorks，不涉及任何云端 CAD 服务。
- **不是 CAD 替代品**：它调用的是脚本本来也能调用的那些 SolidWorks 操作，限制也一样。
- **不是宏录制器**：每个动作都是一次显式的 MCP 工具调用，参数由调用方给出。
- **没有在所有 SolidWorks 版本上验证过**：见[当前状态](#当前状态)与 [docs/verification.zh.md](docs/verification.zh.md)。

## 能做什么

| 领域 | 已提供的工具能力 |
| :--- | :--- |
| 零件建模 | 新建文档、草图、拉伸、旋转、圆角、倒角、抽壳、线性/圆周阵列、镜像、孔特征 |
| 装配体 | 打开文档、添加并固定零部件、重合/距离/同轴配合、干涉检查 |
| 工程图与导出 | 生成工程图、审阅工程图、导出当前文档、批量导出、装配体 BOM、打包 |
| 检查 | 质量属性、包围盒、边线、原生几何检查、配置、运动算例检查 |
| 尺寸与属性 | 识别尺寸、尺寸影响分析、安全改尺寸、自定义属性、单位 |
| 复核流程 | 当前文档复核、排除已复核实体、STEP 导入、零部件替换 |
| 诊断 | 环境体检、插件状态、工具清单、策略与权限诊断 |

当前经 MCP 注册 **71 个工具**（DSH 侧另有 2 个宿主 meta 工具）。逐个工具的状态——已实现、已注册、自动化测试通过、真实 SolidWorks 通过、尚未验证——见 [docs/FEATURE_MATRIX.zh.md](docs/FEATURE_MATRIX.zh.md)。

上面的能力列表并不是同等成熟。沿用自 v0.3.2 的 71 工具全量真机走查基线里，**71 个工具中 33 个 `verified`（其中 7 个只验证了主路径）、13 个 `failed`、24 个 `blocked`**（缺前置条件，例如无 Motion 许可、目标不是 ActiveDoc）。在 v0.3.3 针对 SolidWorks 2026 SP4.1 的定向真机复测中，**D-01（冷启动门禁与 `connect`）、D-02（`open_document` 切换 `ActiveDoc`）、D-03a（装配组件归属与配合后续质量/BOM 链路）、D-04（`shell` 抽壳）以及 `solidworks_add_coincident_mate`（D-08）** 均已实机复测通过；`chamfer`、`revolve`、`pattern`、`list_edges`、`compile_feature_graph`、`design_spec_validate` 虽已注册，但真机上仍处于**失败**状态（留待 v0.4.0 处理）。依赖某个工具前先看矩阵里的 `Real SolidWorks` 列；返回成功只说明调用跑到结束，不代表几何一定正确。

## 运行要求

| 组件 | 要求 |
| :--- | :--- |
| 操作系统 | Windows 10 或 Windows 11，64 位 |
| SolidWorks | 桌面版已安装、至少手动启动过一次、许可证已激活 |
| DeepSeek Harness | `>=0.1.7-rc.2` |
| Node.js | `>=22.12` |
| Python | 3.10+ 64 位，或使用 DSH 自带的 Python 运行时 |

DeepSeek Harness 是宿主应用：插件运行在它里面，无法替你安装它。如果你是从 DSH 插件目录来到这里的，说明宿主已经装好；否则请先装好 DeepSeek Harness，并确认 `dsh --version` 输出 `>=0.1.7-rc.2` 再继续。

本项目只在 **SolidWorks 2026 SP4.1** 上做过真机验证。2020–2025 属于**标称兼容**：代码里没有版本门控，也没有这些版本的真机证据，见[当前状态](#当前状态)。

**兼容性自检（约 3 分钟）。** 在你自己的机器上：(1) 运行 `node bin/dsh-solidworks.js doctor --json`，确认 `solidworks.installed` 为 `true`；(2) 在 SolidWorks 里打开一个已知零件，依次调用 `solidworks_health_check` 与 `solidworks_mass_properties`；(3) 把返回的数字与 SolidWorks 里「评估 → 质量属性」显示的数值对照。三步都对得上，说明只读访问在你的版本上可用；第 2 步或第 3 步失败，就把你的版本当作未验证，而不是默认它能用。

## 安装

```cmd
npm run setup
npm run doctor
```

`npm run setup` 会在插件目录准备独立 `.venv` 与依赖，不改系统 Python；以 DSH Bundle 模式（`dsh.profile.bundles`）安装时，`setup` 会自动跳过向 `cordis.patch.yml` 写入重复条目。`npm run doctor` 输出 JSON 体检报告；当本机或 DSH 内置 Python 缺少 `mcp`/`pywin32` 时，插件与诊断会直接给出包含实际插件路径的一行可复制 `setup` 命令。之后在 DSH 里启用插件即可开始对话。

整条安装路径都在终端里完成，在已经装好 DSH、Node.js、SolidWorks 的机器上大约需要 10–15 分钟，并且要求你会复制粘贴命令。完整前置条件、setup 会创建什么、如何判断安装成功、如何卸载，见 [docs/INSTALL.zh.md](docs/INSTALL.zh.md)。不要先手工去调 Python 路径——最常见的问题就是解释器不匹配，`docs/INSTALL.zh.md` 里写了这种情况。

## 权限与安全

| 模式 | 行为 |
| :--- | :--- |
| `read-only`（默认） | 只发布读取与分析类工具（71 个中的 19 个）。创建/修改/保存/导出类工具不下发，无法调用。 |
| `standard` | 发布建模类工具；保存、关闭、导出等破坏性工具仍然不下发。 |
| `full` | 破坏性工具可调用，且每次高风险调用都需要宿主应用侧的人工确认。 |

- 默认是 `read-only`。切换模式是一次显式的配置修改，AI 助手无法给自己授权。
- 加参数不能绕过：策略检查与确认校验作用在真实调用上，由插件运行时执行。
- 自助确认已禁用。`solidworks_confirm` **确实注册了**，但它只是一个诊断占位，永远返回 `SELF_APPROVAL_PROHIBITED`；插件无法为自己的高风险调用授权。见 [SECURITY.md](SECURITY.md)。
- 策略门禁在插件运行时里，不在 MCP server 里。绕过 DSH 直连 server 的工具同时也会绕过这层门禁——见 [docs/verification.zh.md](docs/verification.zh.md) 第 4.3 节。
- 文件访问被限制在配置的根目录内，除非你主动放宽，否则不会写到目录之外。
- 它**不能**做到的事：不为 SolidWorks 本身做沙箱，不审计 SolidWorks 发出的每一次 API 调用，也无法阻止一次建模操作产出你并不想要的几何。请像对待任何自动化 CAD 修改一样对待 AI 驱动的修改——重要文件先复制。

## 当前状态

| 项目 | 状态 |
| :--- | :--- |
| 当前版本 | **v0.3.3**（`package.json`，在 v0.3.2 文档治理基线上完成 D-01/D-02/D-03a/D-04 与 DSH Bundle 引导修复） |
| DSH 插件目录 | 当前线上目录指向 **v0.3.2**（PR #16343 于 2026-11-17 合并）；v0.3.3 目录更新 PR 待发布后提交 |
| 真机验证 | Windows 11 x64 + SolidWorks 2026 SP4.1：含 v0.3.3 定向复测项（D-01/D-02/D-03a/D-04/重合配合/BOM）与沿用 v0.3.2 全量基线，见 [docs/verification.zh.md](docs/verification.zh.md) |
| SolidWorks 2020–2025 | **未验证**——仅为标称兼容，代码中无版本门控 |
| 自动化测试 | `npm run test:all`：204 项断言，覆盖 20 个套件，另有 45 个 Python 套件（341 个用例）；具体见 [docs/verification.zh.md](docs/verification.zh.md) |
| 工程图 / DFM / FEA / 运动 | 已注册工具，但真机验证深度不如零件建模 |
| Mock 覆盖 | fake-COM 层只覆盖策略、schema 与错误路径，不代表真实 SolidWorks 行为 |

关于这张表有两点要说明：在 v0.3.3 Release 与目录 PR 正式发布前，DSH 插件目录页仍指向 v0.3.2 且展示旧版 README；自动化测试的数字描述的是测试套件，不是 CAD 工具——测试通过只代表插件自身代码按设计运行，不代表某次 SolidWorks 操作一定成功。

## 已知限制

- 仅 Windows。没有 macOS/Linux 版本，因为 SolidWorks 本身没有。
- 真机覆盖集中在 SolidWorks 2026 SP4.1 和部分工具；未列出的工具状态是 `unverified`，不等于"能用"。
- 默认 `read-only`，所以新装好之后在改模式之前不能建模。
- 影子备份只覆盖改尺寸路径，不是每次几何修改都备份。
- 重建、出图这类长操作可能超过单次调用超时（默认 300 秒），需要重试。
- SolidWorks 的模态对话框会阻塞 COM 调用；插件会快速失败而不是一直挂住，但弹窗仍需你手动关掉。
- 教育版、学生版、网络许可版未做系统测试。
- 默认 `read-only` 发布的 19 项并不是同等健康：真机走查里 9 个是干净的 `verified`，3 个 `verified（部分）`，3 个 `failed`，4 个因前置不满足无法执行（blocked）。
- 返回成功不代表结果正确。`solidworks_list_edges` 会返回 `ok` 但几何字段全是 `null`（D-05），空装配体也能通过 `interference_check`（D-11）——工具说 `ok`，也可能什么都没做成。

## 文档

| 文档 | 内容 |
| :--- | :--- |
| [docs/INSTALL.zh.md](docs/INSTALL.zh.md) | 前置条件、安装、MCP 注册、成功判断、卸载与恢复 |
| [docs/ADVANCED-CONFIG.zh.md](docs/ADVANCED-CONFIG.zh.md) | `pythonPath`、本地 `.venv`、镜像源、超时、确认有效期、多 Profile |
| [docs/TROUBLESHOOTING.zh.md](docs/TROUBLESHOOTING.zh.md) | Python、pywin32/COM、网络、MCP 启动、SolidWorks 连接失败 |
| [docs/FEATURE_MATRIX.zh.md](docs/FEATURE_MATRIX.zh.md) | 逐工具的能力与验证矩阵 |
| [docs/verification.zh.md](docs/verification.zh.md) | 实际跑过什么、在哪些版本上跑、什么没跑 |
| [CHANGELOG.md](CHANGELOG.md) | 版本变更历史 |
| [README.md](README.md) | 英文 README，以及 `docs/*.md` 下的英文文档 |

## 反馈

- Bug：打开 <https://github.com/tan000tan/dsh-solidworks/issues/new/choose> 选 **Bug report**，附上插件版本、DSH 版本、SolidWorks 版本和准确的工具名。
- 安装失败：在同一入口选 **Installation problem** 模板，并粘贴 `doctor --json` 与 `doctor --profile --json` 的输出。
- 真机结果：选 **Real SolidWorks validation report** 模板——非 2026 SP4.1 版本的报告尤其有价值。
- 安全问题：不要开公开 issue，按 [SECURITY.md](SECURITY.md) 的方式报告。

## 许可证

- 插件宿主与胶水层：[AGPL-3.0-only](LICENSE)。
- `vendor/` 下内嵌的自动化引擎：MIT，见 [NOTICE](NOTICE)。