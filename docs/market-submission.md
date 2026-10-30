# 投稿到 awesome-dsh-plugin 的准备材料

> 本文件只是**草案 + 核对表**。所有需要联网的确认项都标了「待确认」——本机
> `api.github.com`、`raw.githubusercontent.com`、`awesome-dsh-plugin.com` 都被解析到内网地址
> 并被拒绝（`web_fetch` 报 "non-public address"），因此**没有**引用官方 contributing.md 的原文。
> 下面的字段结构来自本机安装的 `dshmarket@1.66.44` 的 `src/registry.ts`（**已证实**），
> 分类与审核口径需以官方指南为准（**待确认**）。

## 1. 收录条件核对

| 条件 | 依据 | 当前状态 |
|---|---|---|
| 包里有 `dsh.bundle.patch` 指向的 `cordis.patch.yml` | dshmarket README（**已证实**） | ✅ 有，且被宿主接受（verification.md E3） |
| 能按标准方式安装并被宿主加载 | 实测（E6/E7）；2026-10-30 复核 | ✅ 安装 + 加载 + 真实调用已验证（2026-10-29 隔离 profile）。2026-10-30 复核：`dsh plugin add <ascii 路径 tgz>` 仍成功、`--dump-config` 正确出现 `- id: dsh-solidworks`，但**重建实例的首次启动**受离线环境限制（拉不到 `@deepseek-ai/*` bundle），见 verification.md E17 说明 |
| 对已装 profile 再 `add`/`remove` 不会弄坏 profile | 实测（2026-10-30） | ⚠️ **有坑**：`dsh plugin add/remove` 会按 `dependencies` 重算，把仅在 `dsh.profile.bundles` 里声明的 `@deepseek-ai/*` 剪掉，导致该 profile 后续启动报 `152 plugins failed to import`。规避：装插件后若 profile 起不来，`dsh rescue --from-default-profile <同名模板>` 重建，或改用桌面端市场安装（桌面 profile 由插件管理器维护，不受影响） |
| 公开 GitHub 仓库 | 市场只从精选列表分发 | ⚠️ 本地仓库已建立：`git init` + 首次提交 `6f311b7`（203 文件，0.1.0 全部内容）。**尚未推送/公开**——推送需要授权 |
| 仓库年龄 ≥ N 天 | README 提到有阈值，具体天数未核对 | **待确认** |
| GitHub topic `dsh-plugin` | README 提到 | **待确认**（需线上改 topic，未授权不动） |
| SPDX 许可证字段 | registry 里有 license | ✅ `AGPL-3.0-only`，LICENSE 全文在包内 |
| `capabilities` 声明 | registry 字段 | ⚠️ 见第 3 节，需要按真实能力写 |
| 无安装期脚本 | 市场默认不跑 `postinstall` | ✅ 插件没有任何 install/postinstall 脚本 |
| 包体大小 | 未见硬限制 | 202 个文件；约 0.61 MiB（tgz）/ 2.2 MB（解包） |

## 2. 投稿 YAML 草案

字段名取自 `dshmarket` 的 registry 解析代码（`name / owner / url / category / description / npm / tarball / install / added / capabilities`）。
`description` 是 i18n 记录；`category` 允许字符串或数组。

```yaml
name: dsh-solidworks
owner: tan000tan
url: https://github.com/tan000tan/dsh-solidworks
category: [cad, automation, windows]
description:
  en: Drive a local SolidWorks install from DSH chat — 66 tools for parts, sketches, mates, drawings, exports and FEA, with a read-only mode by default.
  zh: 在本机 SolidWorks 上通过对话建模——66 个工具覆盖零件、草图、配合、工程图、导出与 FEA，默认只读模式。
# 二选一：npm 包名，或可下载的 tgz 地址（市场安装时用它）
npm: dsh-solidworks
# tarball: https://github.com/tan000tan/dsh-solidworks/releases/download/v0.1.0/dsh-solidworks-0.1.0.tgz
install: dsh plugin --profile <profile> add dsh-solidworks
added: 2026-10-29
capabilities:
  - tools.register      # 在 dsh.tools/v1alpha1 命名空间发布工具
  - process.spawn       # 启动 venv 里的 Python MCP 服务器
  - fs.read             # 读取配置里的 serverScript / 探测 Python
  - fs.write            # 可选：写审计日志（默认关闭）
```

## 3. capabilities / 红线自查

投审时大概率会被问「插件能不能绕开审批直接改文件」。本插件的实际边界（**已证实**，见 verification.md）：

- 工具注册是**闸门**而不是装饰：`read-only` 只注册 16 个只读工具 + 2 个元工具；`standard` 加 26 个写工具；
  24 个高风险工具必须 `mode: full` 或写进 `allow`，且仍需一次性确认（`solidworks_confirm`）。
- 路径闸门：写类工具的目标路径必须落在 `allowedRoots`（默认会话 cwd）里，否则直接拒绝。
- 审计：每次工具调用记一行 JSONL（工具名、风险等级、参数哈希、结果、耗时），默认写到 DSH home 下的
  `dsh-solidworks/audit.jsonl`，可用 `auditLog: null` 关掉。
- 不联网：插件本身只连本地 stdio 子进程，没有任何外部 API 调用。

## 4. 投稿前必须由用户执行/确认的步骤

1. 把本地仓库推到 `tan000tan/dsh-solidworks`（或你选定的新仓库）并设为公开。
   —— 本地 `git init` + 首次提交已完成（`6f311b7`，`main` 分支）；**`git remote add` + `push` 需要授权**。
   建议同时打 tag `v0.1.0`，让 Release 与 `package.json` 版本对齐。
2. 决定发布通道：`npm publish dsh-solidworks`，或打到 GitHub Release 并用 `tarball` 字段。
3. 线上仓库加 topic `dsh-plugin`；确认仓库年龄是否满足阈值。
4. 用官方 contributing 模板核对分类名（`cad` / `automation` 是否是官方词表内的值，**待确认**）。
5. 向 `awesome-dsh-plugin/awesome-dsh-plugin` 提 PR，修改 `plugins.json`（**不手工改 README**）。
6. 提审前重跑一遍 `docs/verification.md` 的全部命令，把结果贴进 PR 描述。

## 5. 已知会被审核问到、需要提前回答的问题

| 问题 | 回答 |
|---|---|
| 需要联网吗？ | 不需要。子进程走 stdio，纯本地。 |
| 需要用户装什么？ | Windows + SolidWorks（2024/2026 实测）、Python 3.10+ 且装了 `mcp`（`pip install mcp`）。插件不替你装。 |
| 会不会动用户已有的 CAD 文件？ | 只在你指定的 `allowedRoots` 内写；保存/导出/删除类工具默认不注册。 |
| AGPL 会不会污染用户？ | 插件以独立进程方式运行，宿主通过 stdio 调用；插件本身 AGPL-3.0，源码随包分发。法律结论请自行复核，见 PROVENANCE.md 第 5 节。 |
| 为什么不用现成的 MCP 服务器目录？ | 市场只装 cordis 插件包（README 已证实），MCP 目录装不进来。 |