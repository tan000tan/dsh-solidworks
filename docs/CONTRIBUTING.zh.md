> 英文版：[CONTRIBUTING.md](../CONTRIBUTING.md)

# 为 dsh-solidworks 贡献

感谢你愿意贡献。这个项目由单人维护、体量很小，所以下面的规则主要围绕两件
事：让每一条声明都站得住脚，以及让审查负担保持在可承受的范围内。开 PR 之前
请先读一遍。

## 这个项目是什么 —— 以及不是什么

`dsh-solidworks` 把 DeepSeek Harness（DSH）接到本机的 SolidWorks 桌面版。
仓库里有两部分：一个 DSH 插件，通过 `dsh-mcp-client` 契约注册 CAD 工具并执行
策略层（模式、风险等级、路径白名单、宿主审批、可选审计日志）；以及
`vendor/solidworks-automation-skill/` 下的 Python MCP 服务器，真正在 Windows 上
执行 COM 调用。全部通过 stdio 在本机运行；项目里唯一的网络访问是
`npm run setup` 执行的 pip 安装。

| 这个仓库是 | 这个仓库不是 |
| --- | --- |
| 一个 DSH 插件加一个本地 stdio MCP 服务器 | 一个 CAD 内核或几何引擎 |
| 一层包在 SolidWorks COM 调用外面的策略、审批与审计 | SolidWorks 进程的沙箱 |
| 一个在安装时从 PyPI 拉取 Python 依赖的安装器 | SolidWorks 或编译好的 CAD 二进制的分发者 |
| 一套可用工具面随配置模式变化的工具集 | SolidWorks 图形界面的替代品 |

每一个几何操作都通过 SolidWorks 自己的 API 交给 SolidWorks 完成。几何结果不对，
通常是 SolidWorks 的行为或调用顺序的问题，本仓库并不会重新计算。如果你想改变
圆角或扫掠的计算方式，那属于 SolidWorks，不属于这里。

## 贡献方式

有五类贡献是真正有用的。请挑你能真正验证的那一类。

### 1. 报告可复现的缺陷

使用 [缺陷报告模板](../.github/ISSUE_TEMPLATE/01-bug-report.yml)。只有当报告写明
用了哪个插件版本、哪个 DSH 版本、哪种模式、调用了哪个工具名，以及确切的错误
文本（例如 `POLICY_MODE`、`CONFIRMATION_REQUIRED` 或
`APPROVAL_CHANNEL_UNAVAILABLE`）时，它才可处理。请说明问题是在真实 SolidWorks
会话里看到的，还是对着 mock 看到的；模板会明确询问，维护者依赖这个回答。

### 2. 提交真实 SolidWorks 验证报告

使用 [验证报告模板](../.github/ISSUE_TEMPLATE/03-real-solidworks-validation.yml)。
对未在真机上跑过的版本来说，这是最有价值的贡献：目前真机验证过的组合只有
Windows 加 SolidWorks 2026 SP4.1。SolidWorks 2020–2025 只标称兼容，代码里没有
版本门控，也没有验证过。报告"某个工具在你的版本上失败"是有用的证据，不是抱怨，
也是兼容性表格唯一能扩大的方式。

### 3. 改进文档

文档修正很受欢迎，审查成本也低。两个条件：英文文件与对应的中文文件在同一个 PR
里改；每一条声明都能追溯到代码或 [docs/verification.md](verification.md)。新增的
每一个相对链接都必须在仓库里能打开——坏链接会被当作缺陷处理。如果文档里的错误
码已经和代码不一致，那是缺陷报告，不是文风问题。

### 4. 增加或修复测试

`npm test` 跑四个离线 Node 套件（policy、MCP、schema、package）。
`npm run test:all` 会加上与 Python 相关的套件，并把每一项报告为 PASS、FAIL、
BLOCKED 或 SKIPPED。新测试默认要保持离线：任何测试都不得要求运行中的
SolidWorks 或网络。使用 mock COM 对象的测试是受欢迎的，但必须在命名和注释里
标明是 mock，绝不能描述成真实 SolidWorks 验证。新工具至少需要一个注册与发布
测试；工具注册表本身由 `tests/tool_registry_integrity_test.py` 守护。

### 5. 提交代码

先开 Issue 说明范围——改什么、不改什么、打算怎么验证。只做一件事的小 PR 比大
PR 审查得快。触碰策略层、风险分级或审批路径的改动会被看得更细，因为用户正是
依赖这些部分来阻止自己没要求的写操作。拿不准一个改动是否在范围内，先问再写。

## 开发环境准备

需要 Node.js 22.12 或更高版本；Python 那一半需要 Python 3.10+（64 位）。
`npm run setup` 会创建插件本地的 `.venv`，并从 PyPI 安装 Python 依赖；它不碰
系统 Python、注册表、PATH 或环境变量，也从不请求管理员权限。

```bash
git clone https://github.com/tan000tan/dsh-solidworks.git
cd dsh-solidworks
npm run setup
npm test
npm run test:all
node bin/dsh-solidworks.js doctor
```

如果你只改 JavaScript 或 Markdown，干净克隆后直接 `npm test` 就能跑；
只有 Python 服务器和 `npm run test:all` 需要先 `npm run setup`。

| 命令 | 作用 | 需要 Python |
| --- | --- | --- |
| `npm run setup` | 创建插件本地 `.venv`、安装 Python 依赖、把插件注册进 DSH profile | 是 |
| `npm test` | 跑四个离线 Node 套件（policy、MCP、schema、package） | 否 |
| `npm run test:all` | 跑完整套件列表，包括 Python 与审批路径相关套件 | 是 |
| `node bin/dsh-solidworks.js doctor` | 只读体检；`--json` 只打印、不写报告文件 | 否 |

`.venv` 目录属于插件本地，可能有几百 MB。要清掉它，先跑
`npm run uninstall -- --dry-run`，再跑 `npm run uninstall -- --yes`；卸载白名单会
删除 `.venv`、`dsh-mcp-config.json` 和 `diagnostic-report.*`，同时保留你的 CAD
文件和配置备份。不要提交 `.venv`、`node_modules`、`dsh-mcp-config.json`，也不要
提交在自己机器上生成的报告文件。`npm run mcp-config` 生成的 Direct-MCP 配置是
调试用的，会绕过插件策略层，所以同样不该出现在 PR 里。

注册表测试是 Python 测试，不是 Node 测试，这样运行：

```bash
# Windows 目录结构；前提是 setup 创建了插件本地 venv
.venv/Scripts/python.exe -B tests/tool_registry_integrity_test.py
```

## 编码规则

这些是可核查的规则，不是偏好。破坏其中一条的 PR 会被退回。

1. **绝不把 mock 结果当成真实 SolidWorks 验证。** 下面列了四种验证级别，请用
   真实的那一种。
2. **新工具要注册到所有地方。** 新工具必须在同一个 PR 里更新
   `docs/locale/en.json`、`docs/locale/zh.json`、`dsh-plugin.json`（工具数量、
   命名空间与摘要文字）以及 [docs/FEATURE_MATRIX.md](FEATURE_MATRIX.md)。
   只出现在一处的工具是缺陷。
3. **风险等级只能升，不能降。** 不要为了消掉审批提示而降低某个工具的分级。
   未知工具故意默认为 HIGH；这个默认值是安全决策，不是疏漏。
4. **`read-only` 绝不能发布写工具。** 是否发布由策略层决定，不由文档决定。
   默认模式下 71 个工具里只有 19 个被发布；写工具出现在这个列表里是策略缺陷。
5. **每个工具名都要有测试，或者在
   [docs/FEATURE_MATRIX.md](FEATURE_MATRIX.md) 里明确标注 `unverified`。**
   "未验证"是一个诚实的状态，不是失败——事后悄悄把它升级成已验证才是失败。
6. **同一个 PR 里改两种语言。** 英文文件与中文文件必须保持相同的章节顺序、
   表格形状和链接集合。
7. **推送前跑检查。** `npm test` 与 `tests/tool_registry_integrity_test.py` 必须
   通过。如果某个 Python 套件在你的机器上报告 BLOCKED 或 SKIPPED，在 PR 里说明，
   不要隐藏，也不要写成通过。
8. **提交的日志里不要有个人数据。** 从 doctor 输出、审计 JSONL、截图和测试夹具
   里去掉用户名、绝对路径、机器名、许可密钥和令牌。

## 提交与 PR 约定

| 事项 | 约定 |
| --- | --- |
| 提交标题 | 祈使句、简短：`add shell tool test`，而不是 `Added the test`。 |
| 范围 | 一个 PR 只做一件事。不要顺手重构或重新排版。 |
| 验证级别 | 在 PR 正文里写明 `automated`、`mock`、`real-SolidWorks` 或 `unverified` 之一。 |
| 证据 | 贴出或链接能支撑该声明的测试输出、`doctor --json` 片段或审计行。先脱敏。 |
| 文档 | 中英文一起改；工具改动还要更新 locale 文件与功能矩阵。 |
| CI | 仓库没有 `.github/workflows`，所以请在本地跑套件并贴出结果。 |

请始终一致地使用这几个级别——审查者首先看的就是它：

| 级别 | 含义 | 需要附上的证据 |
| --- | --- | --- |
| `automated` | 本仓库的自动化测试覆盖了该路径，不涉及 SolidWorks | 测试文件名与通过的运行结果 |
| `mock` | 对着 mock 的 COM 对象或假 MCP 客户端跑过 | mock 测试路径，并明确标注是 mock |
| `real-SolidWorks` | 在 Windows 上对着真实 SolidWorks 会话跑过 | SolidWorks 版本、SP、版本类型、文档描述、工具与结果 |
| `unverified` | 没有任何地方验证过 | 直说，不要事后改写成"测过了" |

## 审查与合并

这是单人、业余时间维护的项目。不承诺响应时间，也不承诺合并时间。维护者可能
要求补充证据、要求拆分 PR，也可能拒绝一个把工具面扩大却没有清楚验证路径的改动。
审查意见针对改动本身，不针对你。PR 长时间没人理，在 Issue 里礼貌提醒一下是可以的。

## 贡献的许可

项目采用 AGPL-3.0-only 许可（见 [LICENSE](../LICENSE)）。提交 PR 即表示你同意
你的贡献以相同条款授权。仓库里没有单独的贡献者许可协议（CLA）文件。

`vendor/solidworks-automation-skill/` 是 MIT 许可上游项目的快照（commit
`d8b9547`，193 个文件），并带有本地安全补丁；见 [NOTICE](../NOTICE) 以及该目录
内的 MIT 许可文本。`vendor/` 里的改动必须在 PR 中说明上游来源与改动理由，并
保留 MIT 声明。不要把许可证不明或不兼容的代码粘贴进仓库。

## 会被拒绝的内容

- 伪造的验证：没有哪次运行产生过的截图、日志或声明。
- 夸大的兼容性：在只有 Windows 加 SolidWorks 2026 SP4.1 真机验证过的情况下，
  把 2020–2025 说成已验证，或声称支持 Linux/macOS。
- 绕过审批：降低风险等级、允许自我审批、在 `read-only` 模式下发布写工具，或
  让审批路径 fail open。
- 删除或削弱审计日志、它的失败计数器，或"日志文件不可写时把审计条目留在内存"
  这个降级行为。
- 提交二进制产物。仓库不跟踪任何 `.exe`、`.dll` 或 `.pyd` 文件，这是有意的。
- 文档里的营销话术或无法验证的承诺。
- 把无关改动混在一起的 PR，或只改一种语言的 PR。
- 任何形式的密钥、个人数据或专有 CAD 文件。

## 相关文档

| 文档 | 为什么读它 |
| --- | --- |
| [README.md](../README.md) | 插件做什么、工具数量与当前验证状态 |
| [INSTALL.md](../INSTALL.md) | 安装、升级、卸载行为，包括 setup 从不触碰什么 |
| [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) | 错误码以及真正适用的修法 |
| [docs/ADVANCED-CONFIG.md](ADVANCED-CONFIG.md) | 每一个配置键、模式语义与审计日志行为 |
| [docs/FEATURE_MATRIX.md](FEATURE_MATRIX.md) | 逐工具状态，包括哪些工具未验证 |
| [docs/verification.md](verification.md) | 证据记录；只有被列出的证据才算数 |
| [SECURITY.md](../SECURITY.md) | 威胁模型、已实现的控制与漏洞上报方式 |
| [SUPPORT.md](../SUPPORT.md) | 去哪里提问、要带什么、什么不在支持范围 |