# 阶段 0 审计：基准版本与环境现状核查报告 (baseline.md)

**审计编号：** `AUDIT-PHASE0-BASELINE-20261111`  
**审计目标：** 冻结当前真实技术基准，区分 GitHub Release、插件市场 PR、市场条目与真实端到端安装的边界，保护原始成果。

---

## 一、代码基准版本核查

1. **GitHub 仓库地址：** `https://github.com/tan000tan/dsh-solidworks`
2. **默认分支（Default Branch）：** `main` (最新提交: `9cd64db`)
3. **本地当前工作分支：** `feat/v0.3.0-phase1-6`
4. **本地当前 HEAD Commit：** `1eb2bdf63f9bb3207e8df46927708e16d3f1ee5e`
5. **Git Tag 状态：** 本地与远程仓库均存在 Tag `v0.3.0`，精准指向 Commit `1eb2bdf`。
6. **基准演进关系：**
   - 上一正式发布基线：`v0.2.0` (Commit: `de6829d`)
   - v0.3.0 专项研发分支：`feat/v0.3.0-phase1-6`
   - 本地分支较 `main` 领先 1 个提交（包含多版本兼容层改造、Windows 安装包构建与完整性交付物）。

---

## 二、状态四维度严格区分确认

依据阶段 0 核心准则：“必须区分：GitHub Release 是否存在、插件市场条目是否已经合并、插件是否能够从市场安装、安装后是否能够正常运行。不能把其中一个状态当成其他状态的证据。”

| 状态维度 | 当前客观状态 | 验证方法与证据来源 | 结论与判定 |
|---|---|---|---|
| **1. GitHub Release 是否存在** | **已存在 (PUBLISHED)** | GitHub API (`/releases/tags/v0.3.0`) 实测返回 HTTP 200，发布时间 `2026-11-11T02:24:42Z`。包含 3 项正式资产。 | **PASS** |
| **2. 插件市场 PR 是否合并** | **已合并 (MERGED)** | GitHub API (`awesome-dsh-plugin/pulls/14130`) 实测返回 `state: closed, merged: true`，合并于 `2026-11-11T03:25:29Z`。 | **PASS** |
| **3. 是否能从 DSH 官方市场在线安装** | **未实机在线测试 (NOT TESTED)** | 仅在本地沙箱测试了离线包解压脚本，未在隔离纯净机启动 DSH GUI 客户端从远程市场拉取安装。 | **NOT TESTED** |
| **4. 安装后是否能正常运行 CAD** | **本地运行正常，市场在线待测 (PARTIAL)** | 本地 SolidWorks 2026 SP4.1 运行正常且通过 11 步 CAD 建模闭环；但跨机器真实市场安装场景尚未实测。 | **PARTIAL** |

---

## 三、基准冻结结论

当前 v0.3.0 版本的核心代码与分发文件在 Commit `1eb2bdf` 上保持完整。**禁止在未经用户明确批准的情况下擅自重置分支、修改基准 Commit 或变更远程 Release**。
