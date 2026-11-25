> 英文版：[SECURITY.md](../SECURITY.md)

# 安全策略

本文说明 `dsh-solidworks` 防什么、不防什么，实际实现了哪些控制，以及发现问题
后如何上报。文中每一条都应能对着源码核对；如果本文与代码不一致，以代码为准，
并把这处不一致当成文档缺陷。

## 受支持的版本

| 版本 | 安全支持 | 说明 |
| --- | --- | --- |
| 0.3.2 | 支持——修复进入此版本 | 当前发布版；下面的控制与限制都针对它 |
| 0.3.1、0.3.0 | 不作承诺 | 较旧的发布版；不承诺回合修复 |
| 早于 0.3.0 | 不支持 | 请先升级到 0.3.2 |

## 如何上报漏洞

请使用 GitHub 的私密漏洞报告：在 GitHub 打开本仓库，进入 **Security**，选择
**Report a vulnerability**（私密漏洞报告）。这样在准备修复期间，细节不会公开。

如果你的 GitHub 设置或本仓库没有这个入口，请**不要**把可利用细节、私有 CAD
文件、许可密钥或令牌贴进公开 Issue。此时请开一个普通 Issue，只说明你有一个与
安全相关的发现、希望要一个私密渠道；维护者会回复一个可以传递细节的方式。

一份有用的报告包含：插件版本、DSH 版本、Windows 版本、SolidWorks 版本与 SP、
配置的模式、工具名、问题是在真实会话还是对着 mock 看到的、预期与实际行为，以及
最小复现。请先对路径、用户名和业务数据脱敏。请只针对自己的安装做测试——不要
对其他人的机器或 CAD 文件发起攻击。

维护者是单人业余维护，因此不承诺固定的响应时间。见下面的披露政策。

## 威胁模型与边界

本插件的设计目标是：在本地桌面工具的范围内，阻止 AI 代理执行人类并不想要的
CAD 操作。它不是为了抵御已经控制了这台机器的攻击者。

信任假设：

- 本机及其 SolidWorks 安装是可信的，包括 Python 运行时和 `npm run setup` 执行
  的 COM 注册。
- 插件以调用者的用户身份运行，拥有相同的文件与 COM 权限。
- DSH 审批提示前的人才是决策者；插件不能代替他做这个决定。
- DSH 宿主是可信的。无论本插件如何，它都能启动进程、读取文件。

| 在本项目范围内 | 不在本项目范围内 |
| --- | --- |
| 工具调用在配置模式之外被发布或执行 | 同一台机器上的本地管理员 / root 级攻击者 |
| HIGH 风险工具未经宿主审批就执行，或插件给自己审批 | SolidWorks 本身、其 COM API 或其许可系统的失陷 |
| 文件访问逃出配置的 `allowedRoots` 列表 | 用户绕过 `npm run setup` 自行安装的恶意 Python 包 |
| 审批通道缺失时策略逻辑 fail open | AI 模型对"哪个操作更合适"的判断 |
| 审计输出声称发生了并未发生的事 | 通过超大或超慢的 CAD 操作制造拒绝服务 |

有三条边界值得直说，因为它们很容易被误解：

- 插件不对 SolidWorks 进程做沙箱。一次建模调用以用户 SolidWorks 会话的全部权限
  运行。
- 策略层在插件内部。通过 `npm run mcp-config` 可以生成的 Direct-MCP 配置连到
  Python 服务器的客户端，其调用路径上没有插件的策略、审批与审计代码。该配置
  在文档里被明确定位为仅用于调试。
- 一次审批绑定工具名、参数摘要和会话，并带时限。它是对某一次具体调用的
  "人类点击"，不是代码审查，也无法判断生成的几何是不是用户想要的那个。

## 实际实现的安全控制

| 控制 | 作用 | 所在位置 |
| --- | --- | --- |
| 三种策略模式：`read-only`、`standard`、`full` | `read-only` 只发布 71 个工具中的 19 个只读工具；`standard` 发布 45 个；`full` 发布全部 71 个。被扣下的工具不出现在工具列表里，而不是调用时才拒绝 | `lib/policy.js` |
| 三级风险表：READ、WRITE、HIGH | 不在表里的工具故意默认为 HIGH，这样新加但未分类的工具会被按危险处理 | `lib/policy.js:21-23`、`lib/policy.js:126-131` |
| HIGH 风险工具需要 DSH 宿主审批 | 授权绑定工具名、参数摘要与会话，并带 TTL；没有审批通道时调用以 `APPROVAL_CHANNEL_UNAVAILABLE` 失败，而不是继续执行 | `lib/index.js`、`lib/policy.js` |
| 禁止自我审批 | `solidworks_confirm` 是 DSH 宿主侧的元工具、不属于 71 个服务器工具，它始终返回 `SELF_APPROVAL_PROHIBITED`；CLI 没有 approve / reject 命令，所以工具或脚本无法给自己授权 | `lib/index.js:334`、`lib/index.js:341` |
| 路径白名单 `allowedRoots` | 列表非空时，指向列表之外的路径参数会被拒绝；列表为空时退回会话工作目录 | `lib/policy.js:454` |
| 可选审计日志 | 配置 `auditLog` 后，策略判定、审批与调用以 JSONL 追加；文件不可写时插件在内存里保留最多 1000 条，在 stderr 报错，并通过 `solidworks_status`（同样是宿主侧元工具）暴露失败计数 | `lib/policy.js:150` |

下面这些拒绝码是报告里应当原样引用的，它们稳定到可以在源码和排错指南里检索：

```text
POLICY_MODE
CONFIRMATION_REQUIRED
APPROVAL_CHANNEL_UNAVAILABLE
PATH_OUTSIDE_ALLOWED_ROOTS
SELF_APPROVAL_PROHIBITED
```

## 已知限制与非目标

- SolidWorks 进程没有沙箱。策略放行的一次调用可以使用该 SolidWorks 会话能做的
  任何文件、注册表或 COM 操作。
- 插件不审计每一次 API 调用。它只在配置了 `auditLog` 时记录插件层面的策略事件与
  工具调用；SolidWorks 自身的 COM 活动以及 Python 服务器内部做的事不在该日志里。
- 它无法阻止错误几何。一个格式正确但结果不是用户想要的调用，按设计会被放行；
  重要文档请在副本上操作。
- 策略与审批层只对经过插件的调用生效。Direct-MCP 配置会绕过它们，详见
  [docs/ADVANCED-CONFIG.md](ADVANCED-CONFIG.md)。
- 影子备份只覆盖改尺寸路径。其他编辑不会自动获得影子副本。
- 审批是带时限的一次点击，不是意图校验。人可能批准一个并非本意的操作，插件
  无法发现。
- 本仓库里不存在发布签名或签名校验代码。安装与升级信任的是 npm 包和固定版本的
  vendor 快照；Python 服务器启动前没有密码学校验。
- 本地管理员级攻击者不在防御范围内：他可以替换插件文件、Python 运行时或审计
  日志本身。
- SolidWorks 2020–2025 标称支持但未验证；真机验证过的组合只有 Windows 加
  SolidWorks 2026 SP4.1。这个缺口导致的错误见
  [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md)。Linux 与 macOS 完全不支持。

## 依赖与供应链说明

- Python 依赖由 `npm run setup`（以及 `npm run upgrade` 时的复查）从 PyPI 安装。
  setup 脚本默认使用镜像——清华源，并以 `pypi.org` 兜底；`--official` 可关掉
  镜像。安装依赖是项目唯一的网络访问；插件与 MCP 服务器其他时候都通过 stdio
  在本机运行。
- 插件本身没有 npm 运行时依赖。它跑在 DSH 宿主自带的运行时上，这也是要求
  Node.js 22.12+ 与 DSH 0.1.7-rc.2+ 的原因。
- `vendor/solidworks-automation-skill/` 是 MIT 许可上游项目 commit `d8b9547`
  （193 个文件）的快照，并在其上应用了本地安全补丁；MIT 许可文本与来源记录在
  [NOTICE](../NOTICE)。请把它当第三方代码对待：vendor 的改动按 vendor 改动审查。
- 仓库不跟踪任何编译好的二进制——没有 `.exe`、`.dll` 或 `.pyd`。SolidWorks 本身
  从不随包分发；插件只使用机器上已存在的 SolidWorks 安装。
- 如果你从市场或 git 检出安装插件，任何报告里值得记录的两个值就是插件版本与
  DSH 版本。

## 披露政策

- 请先私下报告，给维护者留出修复时间，再公开细节。
- 本项目没有漏洞赏金，也没有任何形式的报酬。
- 没有 SLA，不承诺响应或修复时间。维护者只有一人、利用业余时间，报告可能会
  搁置一段时间。
- 维护者会争取确认报告、在当前发布线里准备修复，并在修复发布时于变更日志或
  GitHub 安全公告里给出简短说明。如你需要，可以署名致谢。
- 如果报告最终属于已有文档写明的限制（例如"审批只是一次点击而非审查"），会
  得到解释而不是修复。

## 相关文档

| 文档 | 为什么读它 |
| --- | --- |
| [README.md](../README.md) | 功能面、模式表与当前验证状态 |
| [INSTALL.md](../INSTALL.md) | setup 会写什么，以及它刻意从不触碰什么 |
| [docs/ADVANCED-CONFIG.md](ADVANCED-CONFIG.md) | 全部策略、审批与审计配置键 |
| [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) | 每个拒绝码在实践中意味着什么 |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | 哪些改动会被接受，包括对策略层的改动 |
| [SUPPORT.md](../SUPPORT.md) | 非安全类问题去哪里问 |
| [NOTICE](../NOTICE) | vendor 快照的第三方来源 |
| [LICENSE](../LICENSE) | 本项目的 AGPL-3.0-only 条款 |