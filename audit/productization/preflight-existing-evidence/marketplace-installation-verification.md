# 既有清理与验收报告真实性审计：市场安装与分发真实性审查报告 (marketplace-installation-verification.md)

**审计编号：** `AUDIT-PREFLIGHT-MARKETPLACE-20261111`  
**审计核心要求：** 查明市场 PR #14130 真实状态、市场条目指向版本、下载地址、下载哈希；核查是否从真实 DSH 市场客户端完成端到端安装与 SolidWorks 连接；严守“市场 PR 合并和 GitHub Release 存在，不能替代真实市场安装验证”的红线。

---

## 一、官方插件市场线上状态核查

1. **市场 PR #14130 真实状态：**
   - 目标仓库：`awesome-dsh-plugin/awesome-dsh-plugin`
   - PR 编号：`#14130`
   - 标题：`feat(plugins): update tan000tan/dsh-solidworks to v0.3.0`
   - 线上 API 实测数据：
     - `state`: `closed`
     - `merged`: `true`
     - `created_at`: `2026-11-11T02:26:17Z`
     - `updated_at`: `2026-11-11T03:25:29Z`
   - **核查结论：PR #14130 已于 2026-11-11 11:25:29 (UTC+8) 正式合并进入官方插件市场主分支**。
2. **市场条目当前指向版本：**
   - 官方市场文件路径：`data/plugins/tan000tan__dsh-solidworks.yml`
   - `name`: `tan000tan/dsh-solidworks`
   - 对应版本：`v0.3.0`
3. **实际在线下载地址：**
   - `tarball`: `https://github.com/tan000tan/dsh-solidworks/releases/download/v0.3.0/dsh-solidworks-0.3.0.tgz`
4. **下载文件大小与 SHA-256 哈希比对：**
   - GitHub Release Asset 大小：`7,652,536 字节`
   - 本地构建与交付物大小：`7,652,536 字节`
   - 真实 SHA-256 哈希：`85DAD498432DAEB063F806C41E64AAB1364DEE01D0AF494D4DC485B06E6962BC` (两端 100% 严密吻合)

---

## 二、普通用户视角：市场端到端实机安装核查

依据任务书最高原则：“**市场 PR 合并和 GitHub Release 存在，都不能替代真实市场安装验证。**”

| 核查维度 | 实际执行情况 | 原始证据状态 | 单项核查定级 |
|---|---|---|---|
| **从 DSH 市场客户端搜索并点击安装** | 目前仅在开发者本地沙箱环境中，通过脚本模拟离线解压安装及依赖部署；**尚未在隔离的纯净 Windows 客户机上，启动 DeepSeek Harness GUI 客户端直接从线上市场索引一键拉取并安装**。 | 缺少 DSH 市场 GUI 客户端端到端安装日志与全流程截图。 | **NOT TESTED** |
| **市场拉取后环境免配置自动初始化** | 当前版本通过本地 `install.bat` 或 `npm run setup` 能自动创建 `.venv` 并探测宿主 Python，但若目标普通用户完全未安装 Python 3.10+，启动将提示缺失，尚未内置完全独立的便携式 Python (Embeddable Python Runtime)。 | 存在提示代码，但未实现零预装全自动化免配置。 | **PARTIAL** |
| **安装后插件成功启动 (MCP)** | 在本地环境及隔离沙箱中，MCP Server 启动正常，73 项工具完整加载。 | `diagnostic-report.json` PASS | **PASS (本地/沙箱)**<br>**NOT TESTED (市场在线)** |
| **安装后完成 SolidWorks COM 连接** | 本机 SolidWorks 2026 SP4.1 响应正常，完成 11 步 CAD 闭环。 | `e2e_full_chain_cad_loop.json` PASS | **PASS (本地宿主)**<br>**NOT TESTED (跨机市场包)** |

---

## 三、综合核查结论与风险阻断

1. **当前定级：`PARTIAL / NOT TESTED`**
   - 线上分发资产与市场 PR 状态**真实可靠且已合并生效**；
   - 但**“从真实 DSH 市场在线端到端拉取安装并在纯净客户机运行”**这一步，尚未在物理隔离的干净虚拟机中实测。
2. **发布门禁建议：**
   - 绝不能将“市场 PR 已合并”等同于“普通用户在任何全新电脑上点击安装即 100% 成功”；
   - 必须等待阶段 1/阶段 4 在纯净测试虚拟机中完成真实在线拉取验证后，方可解除该项阻断。
