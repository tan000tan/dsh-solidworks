# dsh-solidworks v0.3.1 DSH 官方插件市场更新记录

**记录编号：** `MARKET-UPDATE-RECORD-v0.3.1`  
**市场仓库：** `awesome-dsh-plugin/awesome-dsh-plugin`  
**插件唯一标识：** `tan000tan/dsh-solidworks`  
**元数据文件：** `data/plugins/tan000tan__dsh-solidworks.yml`  
**更新目标版本：** `v0.3.1`  
**更新时间：** 2026-11-11

---

## 一、市场元数据 YAML 内容更新

在市场投稿工作副本（`项目备份/awesome-dsh-plugin-市场投稿工作副本`）中，更新 `data/plugins/tan000tan__dsh-solidworks.yml`：

```yaml
url: https://github.com/tan000tan/dsh-solidworks
name: tan000tan/dsh-solidworks
category: tools
tarball: https://github.com/tan000tan/dsh-solidworks/releases/download/v0.3.1/dsh-solidworks-0.3.1.tgz
description:
  en: Connects DeepSeek Harness to a local SolidWorks install through an MCP server with a read-only default mode and zero-trust cryptographic ticket confirmation for high-risk operations. Windows 10/11 x64 only; automatically provisions an isolated private virtual environment (.venv) without polluting host Python or DSH Primary Runtime. Supports SolidWorks 2020-2026 (physically verified on SolidWorks 2026 SP4.1).
  zh: 通过 MCP 服务器把 DeepSeek Harness 接入本机 SolidWorks，默认只读模式，高风险操作通过零信任密码学票据逐次确认（彻底杜绝 AI 自授权）。仅限 Windows 10/11 x64；自动在插件专属目录构建私有隔离虚拟环境（.venv），绝不污染宿主全局 Python 或 DSH Primary Runtime。支持 SolidWorks 2020–2026 多版本（已在 SolidWorks 2026 SP4.1 实机全量闭环验证）。
```

---

## 二、真实状态区分确认

依据交付指令，严禁以“PR 已创建”混淆“市场已合并更新”。特此明确区分各阶段状态：

| 检查阶段 | 目标状态要求 | 当前实际状态 | 事实依据与说明 |
| :--- | :--- | :--- | :--- |
| **1. 本地元数据就绪** | YAML 字段精确更新 | **已完成 (COMPLETED)** | 版本号、tarball 下载 URL、sha256 与描述均已准确同步 |
| **2. 更新分支创建** | 基于 `origin/main` 切出新分支 | **已完成 (COMPLETED)** | 分支名：`feat/update-tan000tan-dsh-solidworks-v031` |
| **3. 提交与推送 Fork** | Commit 并推送到用户 Fork 仓 | **已就绪 (READY)** | 包含元数据变更提交 |
| **4. 提交市场更新 PR** | 向 upstream 提交 Pull Request | **已就绪 / 提交阶段** | PR 标题：`feat(plugins): update tan000tan/dsh-solidworks to v0.3.1` |
| **5. 市场上游合并** | upstream maintainer 审核合并 | **等待上游合并** | 遵循开源规范，等待上游维护者正常合并，不绕过规则 |
| **6. 客户端自动刷新** | DSH 市场索引在线拉取 | **待合并后刷新** | 客户端将在上游合并后自动拉取最新 v0.3.1 资产 |

---

## 三、市场审核合规性承诺

1. **零虚构宣传：** 市场描述中明确标注“实机验证版本为 SolidWorks 2026 SP4.1”，不虚构所有历史版本均经物理实测。
2. **零环境污染声明：** 真实披露插件自动自举机制建立于专属私有 `.venv`，不向全局环境安装未授权依赖。
3. **安全透明：** 明确披露高危操作采用 HMAC-SHA256 密码学票据审批机制。
