> 英文版：[SUPPORT.md](../SUPPORT.md)

# 获取支持

本页说明如何在不浪费时间的前提下获取 `dsh-solidworks` 的帮助。项目由一个人
利用业余时间维护，所以最快的路径通常是一份已经带上了维护者会追问的证据的报告。

## 提问之前

按顺序走完下面五步。大多数问题在其中一步就有答案。

1. 读 [INSTALL.md](../INSTALL.md)。它覆盖安装步骤、Python 探测顺序、镜像与可选
   包的开关，以及 setup 刻意从不触碰的东西。
2. 跑只读体检并保留输出：`node bin/dsh-solidworks.js doctor --json`。它会报告
   Python、COM 依赖、服务器脚本与 SolidWorks 安装情况；`--json` 模式下不写任何
   报告文件。
3. 在 [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) 里搜确切的错误码或错误信息。
   `POLICY_MODE`、`CONFIRMATION_REQUIRED`、`APPROVAL_CHANNEL_UNAVAILABLE` 或
   `PYTHON_INVALID` 这类码都有特定含义和特定修法。
4. 搜索已有 Issue，包括已关闭的。已关闭的 Issue 里常常有绕法，重复报告通常很快
   会被关掉。
5. 如果都解决不了，用下面匹配的模板开 Issue，并附上"需要提供什么"里列出的信息。

```bash
node bin/dsh-solidworks.js doctor --json
node bin/dsh-solidworks.js list-tools --mode read-only
```

## 去哪里问

Issue 跟踪器是唯一的支持渠道。这里没有聊天服务器、没有邮件列表，也没有公开的
维护者邮箱，所以不必去找。安全报告不走公开跟踪器——请使用
[SECURITY.md](../SECURITY.md) 里的流程。

| 模板 | 什么时候用 | 必须提供的证据 |
| --- | --- | --- |
| [缺陷报告](https://github.com/tan000tan/dsh-solidworks/blob/main/.github/ISSUE_TEMPLATE/01-bug-report.yml) | 某个工具或运行时在你能说清的模式下行为异常 | 插件版本、DSH 版本、模式、工具名、确切错误、预期与实际、步骤 |
| [安装问题](https://github.com/tan000tan/dsh-solidworks/blob/main/.github/ISSUE_TEMPLATE/02-installation-problem.yml) | setup、Python 探测、COM 注册或 DSH 注册失败 | 完整的 `doctor --json` 输出、确切错误、你用的 Python 路径 |
| [真实 SolidWorks 验证](https://github.com/tan000tan/dsh-solidworks/blob/main/.github/ISSUE_TEMPLATE/03-real-solidworks-validation.yml) | 你在真实 SolidWorks 会话里跑过工具，想把结果记录下来 | SolidWorks 版本、SP 与版本类型、模式、工具与结果、文档描述 |
| [功能请求](https://github.com/tan000tan/dsh-solidworks/blob/main/.github/ISSUE_TEMPLATE/04-feature-request.yml) | 工具面缺少你需要的东西 | 你想完成的工作流、卡在哪里、可选的方案建议 |

拿不准该用哪个，就用缺陷报告模板并说明你想做什么；维护者可以改标签。

## 需要提供什么

| 字段 | 要提供的内容 |
| --- | --- |
| 插件版本 | 来自 `package.json` 或 DSH 插件列表；0.3.2 是当前发布版 |
| DSH 版本 | 宿主版本，例如 DSH 关于页面上的 rc 版本号 |
| 操作系统 | Windows 10 或 11 及内部版本号；只支持 x64 Windows |
| Python | 版本与路径，以 `doctor` 报告为准；说明是否使用插件本地 `.venv` |
| Node.js | `node -v` 的输出；最低要求 22.12 |
| SolidWorks | 版本、SP 与版本类型；Windows 加 2026 SP4.1 是已验证组合 |
| 策略模式 | 配置的 `read-only`、`standard` 或 `full` |
| 工具名 | 确切注册名，例如 `solidworks_health_check` 或 `solidworks_update_dimension` |
| 验证级别 | 真实 SolidWorks 会话、mock 或自动化测试、仅 MCP 层，或未验证 |
| 预期与实际 | 你期望什么、实际发生了什么，各一句话 |
| 复现步骤 | 能复现问题的最短有序步骤 |
| 日志 | doctor 输出、stderr 或审计行，已去掉路径与用户名 |

## 隐私红线

不要把下列任何内容上传或粘贴进 Issue：

- 许可密钥、激活码、令牌、密码或会话 cookie。
- 私有的、客户的或雇主的 CAD 文件、图纸、BOM，或会暴露零件名、尺寸、客户的
  截图。请用文字描述文档——"一个带一次拉伸和两个孔的简单支架"。
- 未脱敏的绝对路径、用户名、机器名或域名。
- 完整的 DSH profile 或 `cordis.patch.yml`；其中可能包含个人设置与无关配置。
- 来自你无权分享的机器的日志。

拿不准就脱敏。缺一个细节的报告很容易追问；泄露出去的客户图纸无法收回。

## 响应预期

- 只有一位维护者，业余时间，没有 SLA，也不承诺响应或修复时间。
- 安全问题请走 [SECURITY.md](../SECURITY.md) 描述的私密渠道，不要走公开 Issue。
- 无法复现、与已有报告重复、或超出下面范围的问题可能会被关闭。带新证据重新
  打开已关闭的 Issue 是正常的，不代表拒绝你本人。
- 为了保持工具面精简，功能请求可能被拒绝。即便答案是不，清楚的工作流描述也
  仍然有帮助。
- 不必反复顶帖；维护者有时间时会读每一个 Issue。

## 不在支持范围

下列内容不在支持范围内，相关请求会得到指回本页的回复：

- Linux 与 macOS。插件通过 Windows 上的 COM 驱动 SolidWorks；其他平台不支持。
- 破解版、未授权或未激活的 SolidWorks。
- SolidWorks 官方支持。本项目不是 Dassault Systèmes；SolidWorks 的缺陷与许可
  问题请联系厂商。
- 远程桌面代操作或替你做建模。报告应当包含复现，而不是要求操作你的机器。
- 定制建模咨询、设计评审签字或 DFM 批准。DFM 与评审工具只报告它们算出的结果，
  不构成工程签字。
- 对 SolidWorks 2020–2025 超出初步分诊范围的兼容性承诺。这些版本标称支持但未
  验证，仓库里也没有版本门控。
- 与插件无关的 Python、Node.js 或 DSH 环境问题。请到各自上游项目解决；本插件
  只支持 `npm run setup` 创建出来的环境。

## 相关文档

| 文档 | 为什么读它 |
| --- | --- |
| [README.md](../README.md) | 功能面、模式以及这个项目是什么 |
| [INSTALL.md](../INSTALL.md) | 安装、升级与卸载细节 |
| [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) | 错误码与其修法 |
| [docs/USER_GUIDE.md](USER_GUIDE.md) | 日常使用、模式与工具分组 |
| [docs/ADVANCED-CONFIG.md](ADVANCED-CONFIG.md) | 配置键，包括 `allowedRoots` 与 `auditLog` |
| [docs/FEATURE_MATRIX.md](FEATURE_MATRIX.md) | 逐工具状态，包括未验证的工具 |
| [docs/verification.md](verification.md) | 兼容性声明背后的证据记录 |
| [SECURITY.md](../SECURITY.md) | 上报漏洞的方式与威胁模型 |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | 想直接发修复而不是发报告时看这里 |