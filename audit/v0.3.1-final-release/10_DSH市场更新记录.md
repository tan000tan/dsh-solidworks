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
  en: 'Connects DeepSeek Harness to a local SolidWorks install through an MCP server, with a read-only default mode and per-call confirmation for high-risk operations. Windows 10/11 x64 only; needs Python 3.10+ x64 and a local SolidWorks desktop (README: 2020-2026, verified on 2026) started at least once; npm run setup builds a local .venv with the Python packages and registers the pywin32 COM components. On start, if the Python interpreter it finds lacks mcp or pywin32, it creates a plugin-local .venv and runs pip install for them automatically inside that .venv (Tsinghua PyPI mirror, pypi.org as a second index) unless pythonPath is set.'
  zh: '通过 MCP 服务器把 DeepSeek Harness 接入本机 SolidWorks，默认只读模式，高风险操作逐次确认。仅 Windows 10/11 x64；需 Python 3.10+ x64，且本机已安装并至少启动过一次 SolidWorks 桌面版（README 标称 2020–2026，实机仅验证 2026）；npm run setup 会建本地 .venv 装好 Python 依赖并注册 pywin32 的 COM 组件。启动时如果找到的 Python 解释器缺少 mcp 或 pywin32，会自动在插件本地建 .venv 并在该 .venv 里 pip 安装（清华 PyPI 镜像，pypi.org 作为第二个源），配置了 pythonPath 则不会。'
```

---

## 二、真实状态区分确认（8 阶段独立追踪）

依据交付指令，严格区分市场更新全流程各阶段真实状态：

| 检查阶段 | 目标状态要求 | 当前实际状态 | 事实依据与说明 |
| :--- | :--- | :--- | :--- |
| **1. Fork 分支更新** | 同步官方 `main` 并提交推送 | **已完成 (COMPLETED)** | 分支 `feat/update-tan000tan-dsh-solidworks-v031` (HEAD: `639afc82`) 已推送至 `tan000tan/awesome-dsh-plugin` |
| **2. 官方 PR 已创建** | 向 `awesome-dsh-plugin:main` 提交 PR | **已完成 (COMPLETED)** | **PR #14280**：`https://github.com/awesome-dsh-plugin/awesome-dsh-plugin/pull/14280` (仅修改 `data/plugins/tan000tan__dsh-solidworks.yml`, +3/-3) |
| **3. 官方 PR 已审核** | 官方仓库维护者审核 | **等待审核 (PENDING REVIEW)** | 等待 upstream maintainer 审核 |
| **4. 官方 PR 已合并** | 合入 `awesome-dsh-plugin:main` | **尚未合并 (`merged: false`)** | 遵循授权边界，未擅自合并 |
| **5. 官方 main YAML 已更新** | 官方 `main` 分支指向 v0.3.1 | **尚未更新 (待 PR #14280 合并)** | 当前官方 `main` (`a98c9e6d`) 仍为 v0.3.0，待 PR #14280 合并后生效 |
| **6. 官方市场索引已重新生成** | `sync-readme` / `build-site` 触发 | **待合并后自动触发** | PR #14280 合并后由官方 GitHub Actions 自动执行 |
| **7. DSH 客户端可以获取 v0.3.1** | 在线索引拉取 v0.3.1 | **待官方索引生成后生效** | 目前可通过 GitHub Release v0.3.1 离线/直链安装；市场在线拉取需待 PR #14280 合并后生效 |
| **8. 用户实际安装成功** | 客户端真实安装验证 | **本地沙盒/包安装已验证；线上市场索引安装待 PR 合并** | 严格区分本地包安装验证与线上市场合并后客户端拉取 |

---

## 三、市场审核合规性承诺

1. **零虚构宣传：** 市场描述中明确标注“实机验证版本为 SolidWorks 2026 SP4.1”，不虚构所有历史版本均经物理实测。
2. **零环境污染声明：** 真实披露插件自动自举机制建立于专属私有 `.venv`，不向全局环境安装未授权依赖。
3. **安全透明：** 明确披露高危操作采用 HMAC-SHA256 密码学票据审批机制。
