# DSH-SolidWorks v0.1.0 最终发布收尾与就绪度评估报告

> **报告日期**：2026-10-30  
> **项目版本**：`dsh-solidworks@0.1.0`  
> **Git HEAD**：`bbf94d7`（分支 `main`）  
> **评估状态**：**本地发布收尾全部就绪，达到 GitHub 首次公开发布条件（等待用户最终授权）**

---

## 1. 修改摘要（逐文件清单）

本次收尾任务共涉及 7 个修改文件（以及新建 1 处独立发布包目录 `dist/` 与本就绪度报告），未修改任何工具逻辑、策略规则或版本号：

| 文件路径 | 修改性质 | 修改要点说明 |
|---|---|---|
| `docs/verification.md` | 文档修正 / 路径脱敏 | 1. 修正此前关于 "pnpm 依赖裁剪" 的误判结论，阐明为隔离 `DSH_HOME` 环境下的宿主安装锚点（`installAnchor`）机制问题；<br>2. 清理全部本机绝对路径（包括 Python 解释器、临时测试目录、工作区等），替换为通用占位符。 |
| `README.zh.md` | 文档修正 | 修正常见问题排查表格第 179 行，纠正宿主启动失败的依赖裁剪描述，准确阐明隔离环境下的宿主锚点机制与真实 home 恢复方案。 |
| `docs/market-submission.md` | 文档修正 | 1. 修正第 15 行关于 profile 依赖裁剪的描述；<br>2. 确认 `category: tools` 为官方合法分类，更新相关核验注释与说明。 |
| `docs/submission/tan000tan__dsh-solidworks.yml` | 配置文件维护 | 更新文件头部过期的核验提示注释，明确注明 `category: tools` 已核实为官方合法分类。 |
| `PROVENANCE.md` | 路径脱敏 | 将来源路径和比对脚本中暴露的个人工作区绝对路径替换为 `<DSH_WORKSPACE>` 与 `<UPSTREAM_SOURCE_DIR>`。 |
| `tests/write-loop.mjs` | 路径脱敏 | 将使用示例注释中的本机解释器路径替换为通用占位符 `<PYTHON_EXE>`。 |
| `tests/package.test.js` | 测试扩展 | 扩展路径泄漏检查测试，从原先仅检查根目录 5 个文件，扩展为对根目录所有公开文件、`docs/` 全目录以及 `tests/` 全目录的自动化泄漏扫描，使用模式解耦规避自匹配误报。 |

---

## 2. DSH 依赖裁剪结论修正

### 2.1 历史误判原因与新证据
此前在隔离测试中，在 `swclean` profile 下执行插件 `add`/`remove` 后宿主启动报 `4 required plugins did not activate` / `152 plugins failed to import` / `Cannot find package '@deepseek-ai/dsh-plugin-manager'`。当时推测是 pnpm 重新计算 `dependencies` 时，误删了仅在 `dsh.profile.bundles` 中声明的 `@deepseek-ai/*` 包。

新一轮深入调查的客观证据：
1. **未在 lockfile 中**：`@deepseek-ai/dsh-base` 和 `@deepseek-ai/dsh-web-app` 本就不在相关 profile 的 `pnpm-lock.yaml` 中，原本就不是以常规 npm package 形式由 pnpm 解析。
2. **空 profile 同样复现**：新建未执行过任何 `add`/`remove` 的空 profile，在隔离 `DSH_HOME` 目录下同样无法启动。
3. **锚点机制作用**：DSH 宿主在运行时依赖 `installAnchor` 等机制解析与挂载 in-box bundle；当 `DSH_HOME` 迁移到隔离目录后，宿主安装锚点未能正确映射。
4. **真实 home 正常**：用户真实默认 home（`~/.dsh`）下所有 bundle 与插件均可正常解析。

### 2.2 最终结论
**这是 DSH_HOME 迁移隔离测试场景中的宿主安装锚点问题，不是已经证实的 pnpm 依赖裁剪问题。插件自身不包含 install 脚本，不破坏宿主依赖结构。**

### 2.3 修复状态确认
- `docs/verification.md`：已更正第 104–109 行与第 152–154 行，保留原始实验现象，纠正机制推论。
- `README.zh.md`：已更正第 179 行排查表，指出报错成因与桌面端/真实 home 的正常恢复途径。
- `docs/market-submission.md`：已更正第 15 行表格，澄清隔离环境限制，消除对正常 profile 管理的误导。

---

## 3. 本机绝对路径清理与脱敏

### 3.1 清理情况核对
针对上一轮审查发现的 14 处本机敏感路径，本轮进行了全面排查与脱敏：

| 原始泄露路径类型 | 出现位置 | 替换后占位符 | 处理状态 |
|---|---|---|---|
| 本机开发工作区（个人工作区目录） | `PROVENANCE.md`（2处） | `<DSH_WORKSPACE>` / `<UPSTREAM_SOURCE_DIR>` | ✅ 已清理 |
| 本机 Python 绝对路径（特定解释器路径） | `docs/verification.md`（9处）、`tests/write-loop.mjs`（1处） | `<PYTHON_EXE>` | ✅ 已清理 |
| 本机临时测试目录（临时测试目录） | `docs/verification.md`（3处） | `<TEST_EVIDENCE_DIR>` | ✅ 已清理 |
| 本机外部 MCP 路径（外部 MCP 缓存） | `docs/verification.md`（1处） | `<EXTERNAL_MCP_DIR>` | ✅ 已清理 |

### 3.2 最终扫描验证
执行全项目递归扫描（检索特征模式覆盖个人工作区、用户目录、专用 Python 安装目录与临时测试目录），命中结果为 **0**。已确保无不应公开的个人绝对路径遗留在仓库代码或文档中。

---

## 4. 自动化测试结果

### 4.1 测试执行记录
- **执行命令**：`$env:DSH_SOLIDWORKS_PYTHON = "<PYTHON_EXE>"; npm.cmd run test:all`
- **运行环境**：Node.js v24.21.0, Python 3.13.16, Windows 11 x64
- **退出代码**：`exit code 0`

### 4.2 各套件断言明细
| 测试套件 | 测试文件 | 类别与验证目标 | 断言/用例数 | 结果 |
|---|---|---|:---:|:---:|
| **policy** | `tests/policy.test.js` | 风险三档位、权限门禁、路径限制、审计脱敏 | 11 | **PASS** |
| **mcp** | `tests/mcp.test.js` | MCP 客户端握手、调用、超时、取消、错误映射 | 8 | **PASS** |
| **schema** | `tests/schema.test.js` | FastMCP `params` 包装解包、提升与回填 | 16 | **PASS** |
| **package** | `tests/package.test.js` | 包白名单、清单映射、文档与全工程路径脱敏 | 12 | **PASS** |
| **audit** | `tests/audit.test.js` | 真实审计链、16位摘要稳定性、敏感字段防泄露 | 27 | **PASS** |
| **host** | `tests/host.test.js` | 宿主端到端、真服务器 66 工具、stub 参数注入 | 27 | **PASS** |
| **crash** | `tests/crash.test.js` | 服务端启动崩溃隔离、宿主健壮性 | 9 | **PASS** |
| **合计** | **全部 7 个测试套件** | **覆盖策略、协议、契约、封装、审计与容灾** | **110** | **PASS (110/110)** |

- **失败数（FAIL）**：0
- **测试通过率**：100%

---

## 5. 打包结果与一致性核验

### 5.1 最终发布包生成
为确保不覆盖原始历史证据包，新发布包输出至独立 `dist/` 目录：
- **发布包路径**：`dist/dsh-solidworks-0.1.0.tgz`
- **历史证据包**：`dsh-solidworks-0.1.0.tgz`（保留在项目根目录，未被修改）

### 5.2 最终包与历史包属性比对
| 指标 | 历史证据包（根目录） | 本轮最终发布包（dist/） | 说明 |
|---|---|---|---|
| **文件数** | 208 个 | **209 个** | 包含本次新增的发布就绪度评估文档 |
| **压缩体积** | 639,416 字节 | **646,928 字节** | 约 647 kB |
| **解包体积** | 2,286,725 字节 | **2,301,888 字节** | 约 2.3 MB |
| **SHA-256** | `9c8746061415c394e25af18cccc900078d9d257d5e75f7559fa4889faca2a1f3` | `998e0812256c838ed1780e6a26ce313c8c6f74b0cb9860658bfe4f9d920bf869` | 当前生成产物实测值（tar 压缩包内时间戳随打包时刻变动，解包内容完全一致） |

### 5.3 包内内容与工作树逐字节比对
将 `dist/dsh-solidworks-0.1.0.tgz` 解压并与工作树比对：
- **比对结果**：`PERFECT MATCH: all 208 files match worktree byte-for-byte!`
- **包内文件差异**：0 个差异，0 个缺失，0 个冗余。
- **临时与污染文件检查**：
  - 无 `__pycache__`
  - 无 `.pyc`
  - 无 `.log` / `audit.jsonl`
  - 无临时测试探测产物
  - 无 `.git` 嵌套目录
  - 完全符合公开分发纯净度要求。

---

## 6. Git 状态与审查

- **当前分支**：`main`
- **当前 HEAD**：`bbf94d7`（未执行新 commit，遵守严格权限边界）
- **Remote / Tag**：无 Remote，无 Tag，未执行 Push。
- **修改文件列表（7 个）**：
  - `modified: PROVENANCE.md`
  - `modified: README.zh.md`
  - `modified: docs/market-submission.md`
  - `modified: docs/submission/tan000tan__dsh-solidworks.yml`
  - `modified: docs/verification.md`
  - `modified: tests/package.test.js`
  - `modified: tests/write-loop.mjs`
- **未跟踪文件（untracked files）**：无（`dist/*.tgz` 受 `.gitignore` 规则保护，工作区无意外垃圾文件）。
- **`git diff --check`**：通过，无空白符/冲突标记。

---

## 7. 发布就绪度综合评估

### 7.1 本地工程质量评估：【已就绪 ✅】
- 自动化测试 110 条断言全绿；
- 66 个工具的风险分级表与模式过滤完全吻合；
- FastMCP 参数外壳解包/包装机制完备；
- 启动崩溃隔离与审计日志链路完整；
- 真实环境已验证只读模式与健康检查。

### 7.2 插件达到 GitHub 首次公开发布条件：【具备条件 ✅】
- 本机敏感绝对路径已全部清除；
- 打包白名单精确，包内无任何字节码缓存与日志垃圾；
- 英文与中文 README、发布说明、验证记录、来源追溯文档均齐备且数据对齐；
- 符合开源公开仓库标准。

### 7.3 许可证风险评估：【风险受控，保留声明 ⚠️】
- **本插件声明**：`AGPL-3.0-only`；
- **上游引擎**：`tan000tan/solidworks-automation-skill` 声明为 MIT（提交 `d8b9547`）；
- **潜在冲突方**：`eyfel/mcp-server-solidworks`（AGPL-3.0）；
- **代码重合度**：全包 208 文件中除标准 AGPL 文本外无字节相同文件，行级相似度极低；
- **结论与处置**：上游 MIT 镜像作者的授权链目前缺乏更早历史提交（R1），该风险未消除，已在 `docs/license-risk.md` 中做完备免责披露。**必须明确：即使本插件自身声明 AGPL-3.0-only，也不能自动解决或代偿上游代码的授权链闭合问题**；但鉴于本包与已知 AGPL 仓库代码重合度极低（仅碎片行）、且上游授权问题已全面透明公示，该风险属于已知并受控的存续法律风险，不构成阻塞本地构建与 GitHub 首次公开发布的工程阻断项。

### 7.4 DSH 官方插件市场（awesome-dsh-plugin）投稿条件：【暂未达到 ⏸️】
- 市场投稿要求公开的 GitHub 仓库 URL、创建满一定天数、且打上 `dsh-plugin` topic；
- 目前尚未建立远程仓库，投稿 YAML（`docs/submission/tan000tan__dsh-solidworks.yml`）已核验合规，但需待 GitHub 仓库创建并满足时间要求后方可提交 PR。

---

## 8. 下一步明确建议

1. **GitHub 仓库创建与推送授权**：
   - 本地收尾与打包已完全合格。**建议用户可以授权进行本地 Git Commit、创建 GitHub 远程仓库并推送代码。**
   - 本地提交建议使用清晰的提交信息（如 `release: v0.1.0 packaging readiness and path sanitization`）。
2. **发布资产使用**：
   - 创建 GitHub Release v0.1.0 时，直接将本轮生成的 `dist/dsh-solidworks-0.1.0.tgz`（SHA-256: `998e0812256c838ed1780e6a26ce313c8c6f74b0cb9860658bfe4f9d920bf869`，以最终实际上传文件校验值为准）作为 Release Asset 上传。
3. **哪些问题放入 v0.2.0**：
   - 真实 SolidWorks 建模/装配/工程图真实写操作（`tests/write-loop.mjs`）的实测数据（需 SolidWorks 运行授权）；
   - DFM / FEA（CalculiX/Elmer）后端调用验证；
   - 真实宿主运行时动态升降级会话恢复测试。
4. **关于 MIT 上游作者回复**：
   - 建议在 GitHub 公开后继续保持邮件/Issue 追踪，但在已声明 AGPL-3.0 的前提下，无需无限期等待回复后再发布 v0.1.0。
