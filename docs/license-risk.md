# 许可证与来源风险清单（v0.1.0）

日期：2026-10-30。范围：`dsh-solidworks` 产品包（本仓库根目录，含 `package.json` 的那一层）。
标记：**已证实**＝本轮直接查过文件；**合理推断**＝有证据但缺一环；**待确认**＝本地无证据，需线上或法律复核。

## 1. 包内到底分发了什么

| 内容 | 文件数 | 许可证 | 版权行 | 状态 |
| --- | ---: | --- | --- | --- |
| `lib/` `bin/` `tests/` `docs/`、`cordis.patch.yml`、`dsh-plugin.json`、两个 README | 31 | AGPL-3.0-only | `Copyright (C) 2026 the dsh-solidworks contributors`（`NOTICE` L2） | **已证实**：本包自写，不来自任何上游 |
| `vendor/solidworks-automation-skill/` | 174 | MIT | `(c) 2026 SolidWorks Automation Skill Contributors`（`vendor/.../LICENSE` L3） | **已证实**：与 `d8b9547` 逐文件 SHA-256 相同 |
| `LICENSE` | 1 | AGPL-3.0 全文 | 标准文本 | **已证实** |
| 合计 | 208（tgz） | — | — | — |

一致性：`package.json` `license: "AGPL-3.0-only"`、`dsh-plugin.json` `license: "AGPL-3.0-only"`、
`LICENSE` 全文、`README` §10、`NOTICE` 第 1–3 行**四处一致**（**已证实**）。

## 2. 与 AGPL 上游仓库的关系（最关键的一项）

对比对象：本地保存的 AGPL 仓库 `dsh-solidworks` 工作副本 @ `8af9bef`（AGPL-3.0，128 文件，
内含从 `eyfel/mcp-server-solidworks` 同步的 `mcp-server-solidworks-main/`）。

本轮重做的证据（**已证实**，SHA-256 全量比对）：

- 本包 208 个工作树文件 vs 上游 128 个文件：**内容完全相同的只有 `LICENSE`**（标准 AGPL 文本，不是代码）。
- 本包主服务器 `vendor/.../mcp-server/server.py`（3065 条有效行）vs 上游 `adapters/claude/server.py`（1976 条）：
  共享行 21 条，Jaccard **0.0058**；21 条全是 `import json`、`try:`、`)` 这类碎片，无一行业务逻辑。
- 结论（**已证实到代码层面**）：本包不含上游 AGPL 仓库的源代码。`NOTICE` 第 4 节据此写成"no source code"。

**仍然存在的待确认项**：MIT 引擎 `solidworks-automation-skill` 自身是否可能派生自 AGPL 的
`eyfel/mcp-server-solidworks`。本地无法证否，因为：

- 本机没有 `eyfel/mcp-server-solidworks` 的原始仓库，只有 AGPL 仓库里的**一份副本**（`adapters/` 目录结构已被改造）；
- 上游仓库的 Git 历史、作者、NOTICE 需要线上核对，而 `github.com` 当前解析到 `198.18.0.162`（不可达）。

判断材料（**合理推断，不足以定性**）：两者文件布局、行数（3065 vs 1976）、工具命名与实现风格差异明显；
共享行仅碎片。若真要定性，需要：① 线上比对 `eyfel/mcp-server-solidworks` 的 `server.py`；
② 查 `solidworks-automation-skill` 的提交历史是否有 "copied from eyfel" 之类记录。**列为法律复核项。**

## 3. 运行时依赖（不分发，但决定用户义务）

`NOTICE` 第 2 节已列必需项；以下是**完整**清单，含可选族与本轮实测的本机安装状态（**已证实**，Python 3.13.16）：

| 包 | 用途 | 许可证 | 本机 | 分发？ | 义务 |
| --- | --- | --- | --- | --- | --- |
| `mcp` | 服务器框架（必需） | MIT | ✅ | 否 | 无 |
| `pydantic` | 参数模型（必需） | MIT | ✅ 2.14.1 | 否 | 无 |
| `pywin32` | COM（SolidWorks 工具必需） | PSF-2.0 | ✅ | 否 | 无 |
| `comtypes` | COM 类型库（可选路径） | MIT | ✅ | 否 | 无 |
| `jsonschema` | DFM/FEA 参数校验 | MIT | ✅ | 否 | 无 |
| `uvicorn` | HTTP 传输（默认不启用） | BSD-3-Clause | ✅ | 否 | 无 |
| `Pillow` | 返回截图/预览 | MIT-CMU | ❌ | 否 | 无 |
| `ezdxf` | DXF 读写 | MIT | ❌ | 否 | 无 |
| `numpy` `matplotlib` | DFM/FEA 计算与出图 | BSD-3 / PSF-based | ❌ | 否 | 无 |
| `OCP`（pythonocc-core） | OCP/高级曲面后端 | **LGPL-3.0** | ❌ | 否 | 仅分发时需满足 LGPL（动态链接/可替换） |
| `PySide6` | 桌面 UI（本包不用） | **LGPL-3.0** | ❌ | 否 | 同上 |
| `PyMuPDF`（`fitz`） | PDF 预览 | **AGPL-3.0** | ❌ | 否 | 若未来**随包分发**会强制整体 AGPL——本包已是 AGPL，无冲突；若改许可证则必须移除 |
| `trimesh` | 3D 打印检查 | MIT | ❌ | 否 | 无 |

要点：**这些包一个都没进 tarball**（`npm pack` 只含 208 个文件，全在 `lib/bin/tests/docs/vendor`）。
用户自己 `pip install` 属于用户行为，不构成我们的分发。若将来做"一键装环境"的安装器，义务会变成真实的——
**那时必须重新审这张表**（尤其 LGPL 的 OCP/PySide6 和 AGPL 的 PyMuPDF）。

## 4. 第三方资源

- 图标 `docs/assets/icon.png`：本轮用 System.Drawing 程序生成（几何图形），**未使用第三方素材**（**已证实**：无外部下载记录）。
- 无字体、无模型、无数据集、无网络 API。插件运行时只连本地 stdio 子进程（**已证实**：`lib/mcp.js` 只有 `spawn`，无 HTTP 客户端）。

## 5. 风险清单与处置

| # | 风险 | 等级 | 现状 | 处置 |
| --- | --- | --- | --- | --- |
| R1 | MIT 引擎可能派生自 AGPL 上游 | 中 | **待确认**（§2） | 上线前线上比对 + 查提交历史；若确认派生，则整包 AGPL 仍自洽，但 `NOTICE` 第 4 节措辞要改成"引擎可能派生，见 PROVENANCE" |
| R2 | 用户装 PyMuPDF 后与插件同进程使用 | 低 | AGPL + AGPL 兼容 | 无需动作；在 README 提到"可选依赖许可证自行确认"即可（已在 NOTICE §2 提示） |
| R3 | 将来打包 Python 环境 | 中 | 未发生 | 一旦发生必须随包附 LGPL/AGPL 文本并提供替换方式 |
| R4 | `README`/`NOTICE` 数字漂移（曾出现 83 vs 174） | 低 | 本轮已修 | `tests/package.test.js` 已断言 vendor 锚点存在、LICENSE/NOTICE 内容；可再加一条"NOTICE 里的文件数与 vendor 实际文件数一致" |
| R5 | 市场要求"完整源代码"或 SPDX 清单 | 低 | 源码即包内，AGPL 已满足 | 投稿时在 PR 描述附 `LICENSE`/`NOTICE`/`PROVENANCE.md` 链接 |

## 6. 不能由本文件下结论的事

- 上述分析是**技术比对**，不是法律意见。R1 的定性、以及"MIT 子树放进 AGPL 包"的兼容性结论，
  最终需要律师或有授权的人确认；本文件只提供可复核的文件、哈希与行级证据。
- 未做：与 `solidworks-automation-skill` 上游仓库的**线上**逐文件比对（网络不可达）。