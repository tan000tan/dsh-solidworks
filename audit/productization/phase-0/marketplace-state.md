# 阶段 0 审计：官方插件市场状态与条目审查报告 (marketplace-state.md)

**审计编号：** `AUDIT-PHASE0-MARKETPLACE-STATE-20261111`  
**审计目标：** 审查 DeepSeek Harness 官方插件市场仓库（`awesome-dsh-plugin`）中 `tan000tan/dsh-solidworks` 条目的收录、PR 状态、下载指向与平台限制声明。

---

## 一、官方市场仓库与 PR 收录核查

1. **上游主仓库：** `https://github.com/awesome-dsh-plugin/awesome-dsh-plugin`
2. **投稿 PR 编号：** `#14130`
3. **PR 标题：** `feat(plugins): update tan000tan/dsh-solidworks to v0.3.0`
4. **线上合并状态：**
   - 状态：`closed`
   - 合并标志：`merged: true`
   - 合并提交时间：`2026-11-11T03:25:29Z` (北京时间 11:25)
   - 目标主分支：`main`

---

## 二、官方市场条目配置文件核查

经只读拉取上游主分支中的文件：`data/plugins/tan000tan__dsh-solidworks.yml`：

```yaml
url: https://github.com/tan000tan/dsh-solidworks
name: tan000tan/dsh-solidworks
category: tools
tarball: https://github.com/tan000tan/dsh-solidworks/releases/download/v0.3.0/dsh-solidworks-0.3.0.tgz
description:
  en: 'Connects DeepSeek Harness to a local SolidWorks install through an MCP server, with a read-only default mode and per-call confirmation for high-risk operations. Windows 10/11 x64 only; needs Python 3.10+ x64 and a local SolidWorks desktop (README: 2020-2026, verified on 2026) started at least once; npm run setup builds a local .venv with the Python packages and registers the pywin32 COM components. On start, if the Python interpreter it finds lacks mcp or pywin32, it runs pip install for them automatically in that interpreter (Tsinghua PyPI mirror, pypi.org as a second index) unless pythonPath is set.'
  zh: '通过 MCP 服务器把 DeepSeek Harness 接入本机 SolidWorks，默认只读模式，高风险操作逐次确认。仅 Windows 10/11 x64；需 Python 3.10+ x64，且本机已安装并至少启动过一次 SolidWorks 桌面版（README 标称 2020–2026，实机仅验证 2026）；npm run setup 会建本地 .venv 装好 Python 依赖并注册 pywin32 的 COM 组件。启动时如果找到的 Python 解释器缺少 mcp 或 pywin32，会自动在该解释器里 pip 安装（清华 PyPI 镜像，pypi.org 作为第二个源），配置了 pythonPath 则不会。'
```

---

## 三、市场条目关键技术要点核实

1. **分发包定位：**
   - 明确指向官方 GitHub Release v0.3.0 下载包：`dsh-solidworks-0.3.0.tgz`；
2. **运行平台约束：**
   - 明确声明：“仅 Windows 10/11 x64；需 Python 3.10+ x64，且本机已安装并至少启动过一次 SolidWorks 桌面版”；
3. **版本验证边界：**
   - 诚实载明：“README 标称 2020–2026，实机仅验证 2026”；
4. **依赖自动化准备：**
   - 声明了清华 PyPI 镜像与自动 pip 安装机制。

---

## 四、核查结论与风险标识

- **市场条目一致性：PASS**。市场条目内容与当前代码库能力吻合，且准确声明了仅实机验证 2026 及需预装 Python 3.10+ 的前置限制。
- **真实安装风险标识：BLOCKED / NOT TESTED**。虽然市场已收录且文件指向无误，但普通用户在真实 DSH 客户端中点击安装该 tarball 的体验尚未经过纯净物理机端到端验收。
