# 阶段 0 审计：Agent 实际执行权限与外部凭据安全审查报告 (permissions-audit.md)

**审计编号：** `AUDIT-PHASE0-PERMISSIONS-20261111`  
**审计目的：** 按照《最高级别控制规则》第 1.4 条与《阶段 0》第 0.3 条指令，深入审查当前宿主机环境向 Agent 暴露的实际写权限与凭据，绝不假装“靠提示词实现了物理隔离”，如实向用户报告。

---

## 一、实际权限与凭证泄露风险逐项排查

### 1. Git 凭证管理器 (Git Credential Manager) 与 GitHub 访问令牌
- **审计发现：**
  - 在检查仓库脚本 `scripts/publish_v030_github_release.py` 及 `scripts/submit_v030_marketplace_pr.py` 时发现，脚本中使用了：
    ```python
    p = subprocess.Popen(
        ['git', 'credential', 'fill'],
        input='protocol=https\nhost=github.com\n\n'
    )
    ```
  - **技术事实：宿主机配置了全局 Git Credential Helper。只要在该终端内调用上述命令，即可无感提取宿主机当前保存的 GitHub Personal Access Token (PAT) 或 OAuth Token**。
- **潜在危害：**
  - 该 Token 在历史操作中曾被用于直接创建 GitHub Release、上传发布附件、Fork 市场仓库以及通过 GitHub API 提交 PR。
  - **严重警告：宿主机未在操作系统权限级别剥离该凭证。Agent 在技术层面上具备调用写权限命令的潜在物理能力！**

---

### 2. 本地 Git 仓库 Push 与 Tag 权限
- **远程配置：**
  - `origin: https://github.com/tan000tan/dsh-solidworks.git (push)`
- **技术事实：**
  - 如果 Agent 在终端执行 `git push origin ...` 或 `git tag ...`，将直接借助凭证管理器将写操作推送到远程公开仓库。

---

### 3. npm Registry 发布权限
- **检查：**
  - 当前包名为 `dsh-solidworks`，由于存在 `package.json` 中的私有标记，且用户未配置公开 npm token，目前无法直接执行全局 `npm publish`。

---

## 二、权限隔离评估与红线约束

依据任务书最高控制准则：
> “如果执行环境仍然向 Agent 提供发布凭据或写权限，必须如实报告。不能声称仅靠提示词已经实现了物理权限隔离。在无法确认权限隔离时，不得执行任何对外写操作。”

### 审计结论：
1. **物理隔离判定：`FAIL (未在 OS 层物理隔离)`**
   - 当前宿主机环境向执行终端暴露了 Git Credential 的读取能力与公开仓库的 Push 权限；
2. **强制工程封印锁定：`ACTIVE (强制只读保护)`**
   - Agent 必须在会话层绝对执行硬性阻断：
     - **严禁执行** `git push`、`git tag`、`git commit`；
     - **严禁执行** `scripts/publish_v030_github_release.py`；
     - **严禁执行** `scripts/submit_v030_marketplace_pr.py`；
     - **严禁调用** 任何提取 `git credential fill` 的外部脚本；
     - **严禁调用** 任何带有写参数的 GitHub REST/GraphQL API。
3. **安全建议：**
   - 建议用户在后续正式发布前，若需严格的物理隔离审计，可临时使用只读测试机或在非特权容器/受限用户账户中运行 Agent。
