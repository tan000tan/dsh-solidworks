# 投稿到 awesome-dsh-plugin 的正式准备材料

> 本文档于 2026-10-30 结合 `awesome-dsh-plugin/awesome-dsh-plugin` 官方仓库的最新实际规范、CI 脚本（`check-submission.mjs`、`lib/entries.mjs`）以及近期合并的 PR 案例更新。所有收录要求、投稿机制和字段规范均已核实闭环。

---

## 1. 官方收录规范与投稿机制

### 投稿机制
- **单文件投稿**：仅在官方仓库的 `data/plugins/` 下添加单个 YAML 文件，命名规范为 `<owner>__<repo>.yml`。
  - 本项目对应的文件名为：`data/plugins/tan000tan__dsh-solidworks.yml`
- **严禁手工编辑两个 README**：
  - `README.md` 与 `README.zh.md` 由官方脚本 `scripts/generate-readme.mjs` 在 `main` 分支合入后自动生成。
  - 手工改动 README 会触发 CI `pr-check.yml` 严格比对报错。
- **单 PR 限制**：
  - 单个 PR 仅能提交 1 个插件条目（硬上限为 3 个，超出直接打回）。

### 官方字段白名单（ENTRY_KEYS）
仅允许声明以下键：`url`, `name`, `category`, `description`, `icon`, `tarball`。
声明任何额外字段（如 `sha256`, `license`, `npm` 等）均会导致 `validateEntries` 判定失败。

| 字段 | 类型 / 格式 | 约束与说明 | 本项目填写值 |
|---|---|---|---|
| `url` | 字符串 | 必须是 `https://github.com/owner/repo` 格式 | `https://github.com/tan000tan/dsh-solidworks` |
| `name` | 字符串 | 若包含 `/` 必须严格等于 repo 名 | `tan000tan/dsh-solidworks` |
| `category` | 枚举 | 必须属于官方 `CAT_IDS` 词表 | `tools` |
| `tarball` | 字符串（可选） | 必须是 GitHub Release 托管的 `.tgz` 或 `.tar.gz` 直链 | `https://github.com/tan000tan/dsh-solidworks/releases/download/v0.1.0/dsh-solidworks-0.1.0.tgz` |
| `description.en` | 字符串（必填） | 单行、无换行、以句号结尾、客观功能描述不夸大 | `Connects DeepSeek Harness to a local SolidWorks install through an MCP server, with a read-only default mode and per-call confirmation for high-risk operations.` |
| `description.zh` | 字符串（可选） | 单行、无换行、以句号结尾 | `通过 MCP 服务器把 DeepSeek Harness 接入本机 SolidWorks，默认只读模式，高风险操作逐次确认。` |

---

## 2. 仓库收录资格核查结果

| 条件 | 官方标准要求 | 本项目核查结果 | 状态 |
|---|---|---|---|
| **公开可见** | 仓库必须是 Public，且未归档 | `visibility: public`, `archived: false` | ✅ 达标 |
| **仓库年龄** | 创建时间 ≥ 1 天 (`MIN_AGE_DAYS = 1`) | 2026-10-25T13:30:05Z 创建，已满 5 天 | ✅ 达标 |
| **官方 Topic** | 必须包含 `dsh-plugin` | topics 列表已包含 `dsh-plugin` | ✅ 达标 |
| **安装 Manifest** | `package.json` 声明 `dsh.bundle`，根目录有 `cordis.patch.yml` | 根目录声明 `"bundle": { "patch": "./cordis.patch.yml" }`，patch 文件 722 字节存在 | ✅ 达标 |
| **真实可用代码** | 拒绝占位符或纯 README 仓库 | 完整 TypeScript 插件 + MCP 桥接，209 个文件，自动化测试套件全绿 | ✅ 达标 |
| **版本与发布** | 发布了正式 Release 与安装包 | Release `v0.1.0` 已发布，资产 `dsh-solidworks-0.1.0.tgz`（647,064 字节，SHA-256：`799247bef17371781907568e05eac2677e5d41a18d58fe79e67584bffaf2f8f1`）可正常下载 | ✅ 达标 |
| **许可证** | 开源许可证 | `AGPL-3.0-only`，LICENSE 文件齐全 | ✅ 达标 |

---

## 3. 关键风险与技术透明性披露

### 3.1 实机写操作尚未完成现场验收（客观事实）
- **现状**：插件已完成全部 MCP 协议交互、三档安全策略（Policy）、模式闸门（Gate）、路径鉴权（allowedRoots）、调用审计（Audit）和崩溃恢复（Crash）的自动化验证。但由于缺乏物理机真实 CAD 模型的破坏性联调环境，实机写操作尚未完成现场闭环验收。
- **安全保障**：插件在架构上严格执行「默认只读（read-only 仅注册 16 个只读工具）」和「高风险工具逐次确认（per-call confirmation）」机制，写操作必须经白名单路径（allowedRoots）鉴权，保障用户环境安全。

### 3.2 上游授权链与许可证（R1 风险）
- **现状**：vendor 引擎源于声明 MIT 的镜像仓库，但其上游原作者授权链尚未完全闭合。本项目采用 AGPL-3.0-only，但不能声称 AGPL-3.0 自动解决了上游代码授权链的问题。
- **透明声明**：项目中完整保留 `PROVENANCE.md` 和 `docs/license-risk.md`，并在 PR 审查说明中主动引用供维护者查阅。

---

## 4. 投稿 YAML 文件

目标路径：`data/plugins/tan000tan__dsh-solidworks.yml`

```yaml
url: https://github.com/tan000tan/dsh-solidworks
name: tan000tan/dsh-solidworks
category: tools
tarball: https://github.com/tan000tan/dsh-solidworks/releases/download/v0.1.0/dsh-solidworks-0.1.0.tgz
description:
  en: Connects DeepSeek Harness to a local SolidWorks install through an MCP server, with a read-only default mode and per-call confirmation for high-risk operations.
  zh: 通过 MCP 服务器把 DeepSeek Harness 接入本机 SolidWorks，默认只读模式，高风险操作逐次确认。
```

---

## 5. 建议的 PR 提交材料

### PR Title
```text
feat(plugins): add tan000tan/dsh-solidworks
```

### PR Body (英文)
```markdown
Adds `tan000tan/dsh-solidworks` to the **tools** category.

Connects DeepSeek Harness to a local SolidWorks installation via an MCP server with granular security tiering, path restriction, and audit logging.

- [x] I added **one file** at `data/plugins/tan000tan__dsh-solidworks.yml` — that single file is the whole submission. The READMEs are regenerated on `main` after merge, so this PR does not touch them.
- [x] My repo's `package.json` declares **`dsh.bundle`** (`./cordis.patch.yml`), not just `dsh.client`.
- [x] My repo is at least **1 day old** (created 2026-10-25).
- [x] `category` is one of the allowed values: `tools`.
- [x] Description accurately states what the plugin does without superlatives.
- [x] My repo has the `dsh-plugin` topic.

### Key Details & Review Notes
- **Repository**: https://github.com/tan000tan/dsh-solidworks (Public, tag `v0.1.0`)
- **Release Tarball**: https://github.com/tan000tan/dsh-solidworks/releases/download/v0.1.0/dsh-solidworks-0.1.0.tgz
  - SHA-256: `799247bef17371781907568e05eac2677e5d41a18d58fe79e67584bffaf2f8f1`
- **Security & Safety Design**:
  - 66 registered tools categorized into 16 read-only, 26 write, and 24 high-risk operations.
  - Three operation modes: default `read-only` (only 16 read-only inspection tools exposed), `standard` (adds write tools with path restriction to `allowedRoots`), and `full` (high-risk tools require per-call interactive confirmation via `solidworks_confirm`).
  - Pure local stdio MCP bridge; no external network requests or remote credentials required.
- **Test Coverage**:
  - 47/47 automated unit assertions passing in host test suite (`npm test`: policy, mcp, schema, package); full 110-assertion suite verified during v0.1.0 release pass with Python environment.
- **Transparency & Disclosures**:
  - Live write operations on physical CAD models have not completed full on-site hardware verification; the plugin intentionally enforces default read-only restrictions and confirmation gates to prevent accidental modifications.
  - Licensing: AGPL-3.0-only. An upstream licensing provenance question remains unresolved and is documented in PROVENANCE.md and docs/license-risk.md.
```

### PR Body (中文备用说明)
```markdown
将 `tan000tan/dsh-solidworks` 添加到 **tools** 分类。

通过 MCP 服务器将 DeepSeek Harness 接入本地 SolidWorks，提供细粒度三档安全分级、路径白名单约束与调用审计日志。

- [x] 仅在 `data/plugins/tan000tan__dsh-solidworks.yml` 新增单个文件，未修改两个 README。
- [x] 根目录 `package.json` 声明了 `dsh.bundle`（`./cordis.patch.yml`）。
- [x] 仓库创建于 2026-10-25，已满 5 天（满足 ≥ 1 天要求）。
- [x] `category: tools`，属于官方合法分类词表。
- [x] 功能描述属实，无营销修饰。
- [x] 仓库已打上 `dsh-plugin` topic。

### 审核要点与透明性披露
- 仓库地址：https://github.com/tan000tan/dsh-solidworks
- Release 安装包：https://github.com/tan000tan/dsh-solidworks/releases/download/v0.1.0/dsh-solidworks-0.1.0.tgz
- 校验哈希（SHA-256）：`799247bef17371781907568e05eac2677e5d41a18d58fe79e67584bffaf2f8f1`
- 工具体系：共 66 个工具（16 只读、26 写操作、24 高风险）。默认只读模式仅注册 16 个只读工具；写操作受 `allowedRoots` 白名单沙箱保护；高风险操作需通过 `solidworks_confirm` 逐次确认。
- 自动化测试：单元测试套件 47 项断言全部通过；发布期全量 110 项断言在具备 Python 环境下验证通过。
- 局限与风险说明：CAD 实机破坏性写操作尚未在物理机现场全量实测闭环，故以安全闸门保障用户环境；代码许可证采用 AGPL-3.0-only，上游授权来源链问题尚未完全闭合，详细风险记录见 `PROVENANCE.md` 和 `docs/license-risk.md`。
```
