# 既有清理与验收报告真实性审计：已删除目录逐项深度审查报告 (deleted-directory-review.md)

**审计编号：** `AUDIT-PREFLIGHT-DELETED-DIR-20261111`  
**审计目的：** 逐一追溯 16 个目录删除前的内容、Git 跟踪状态、备份位置、对系统架构的影响及可恢复方案。

---

## 1. 逐项深度审查明细

### 目录 1–3: pytest 测试运行缓存 (`mcp-server-solidworks-main\.pytest_cache\*`)
- **完整路径：**
  - `mcp-server-solidworks-main\.pytest_cache\v\cache`
  - `mcp-server-solidworks-main\.pytest_cache\v`
  - `mcp-server-solidworks-main\.pytest_cache`
- **删除前内容：** 包含 `lastfailed` (记录上次失败用例)、`nodeids` (用例索引) 以及 `CACHEDIR.TAG`。
- **Git 跟踪状态：** 项目根目录 `.gitignore` 第 23–24 行声明 `.pytest_cache/` 与 `**/.pytest_cache/`，从未被 Git 跟踪。
- **是否有备份：** 运行时缓存无需静态备份，重新运行 pytest 时会自动由 Python pytest 引擎重新生成。
- **架构影响：** 零影响。删除后运行测试会自动新建干净缓存。
- **核查判定：** **PASS**。

---

### 目录 4: 旧版构建产物输出目录 (`dist`)
- **完整路径：** `<WORKSPACE_ROOT>\dist`
- **删除前内容：** 包含上一阶段遗留的两个旧版本安装包：
  1. `dsh-solidworks-0.1.0.tgz` (约 641 KB)
  2. `dsh-solidworks-0.2.0.tgz` (约 1,353 KB)
- **Git 跟踪状态：** 项目根目录 `.gitignore` 第 2 行声明 `*.tgz`，此目录下的 tarball 从未被 Git 跟踪。
- **备份位置与真实哈希：**
  - **备份 A (项目根目录)：**
    - `dsh-solidworks-0.1.0.tgz`: 641,457 字节，SHA-256: `9C8746061415C394E25AF18CCCC900078D9D257D5E75F7559FA4889FACA2A1F3`
    - `dsh-solidworks-0.2.0.tgz`: 1,353,150 字节，SHA-256: `12DD5073A2CEC8862B361B31DD3303A7808E8636B9E6066D49408ACBCCAE6FB5`
  - **备份 B (历史审计归档目录)：**
    - `audit\v1.0-round2-closure-20261109\dist\dsh-solidworks-0.2.0.tgz`，SHA-256 与上述备份 A 100% 严密吻合。
- **是否影响构建/测试：** 当前 v0.3.0 正式交付包已规范归档至 `v0.3.0-final-release-candidate/` 专用目录，清理 `dist` 不影响任何当前自动化脚本与测试。
- **是否影响历史审计：** 历史验收报告与存证直接引用根目录及 audit 备份，存证链完好无损。
- **可恢复性：** 完全可恢复。复制根目录下的两个 tgz 至新建的 `dist/` 即可。当前依据冻结原则不执行恢复。
- **核查判定：** **PASS**。

---

### 目录 5: 历史独立审查证据空目录 (`audit\final-independent-review\evidence`)
- **完整路径：** `<WORKSPACE_ROOT>\audit\final-independent-review\evidence`
- **删除前内容：** 0 文件、0 子目录，物理大小 0 字节。
- **Git 跟踪状态：** Git 不跟踪纯空目录，未被跟踪。
- **备份与恢复：** 无文件需要备份，可由 `mkdir` 重建。
- **核查判定：** **PASS**。

---

### 目录 6–9: 历史终验测试留存空目录 (`audit\v1.0-final-acceptance\*`)
- **完整路径：**
  - `audit\v1.0-final-acceptance\cad_sandbox`
  - `audit\v1.0-final-acceptance\evidence`
  - `audit\v1.0-final-acceptance\logs`
  - `audit\v1.0-final-acceptance\test-results`
- **删除前内容：** 4 个目录均为 0 文件、0 字节的纯空占位符。
- **业务背景：** 在历史 v0.2.0 阶段进行过一次验收，测试完成并将有效证据移至报告后遗留的空叶子节点。
- **核查判定：** **PASS**。

---

### 目录 10–13: 通宵工程测试空目录 (`docs\overnight\*`)
- **完整路径：**
  - `docs\overnight\backups`
  - `docs\overnight\checkpoints`
  - `docs\overnight\evidence`
  - `docs\overnight\scripts`
- **删除前内容：** 4 个纯空子目录（0 字节）。
- **业务背景：** 历史自动化长周期工程脚本留存的空框架目录。真实文档均保留在 `docs/overnight/` 根目录下的 Markdown 文件中，未受任何影响。
- **核查判定：** **PASS**。

---

### 目录 14: 任务状态机空目录 (`state\jobs`)
- **完整路径：** `<WORKSPACE_ROOT>\state\jobs`
- **删除前内容：** 纯空目录（0 字节）。
- **Git 跟踪状态：** `.gitignore` 第 19 行显式忽略 `state/`。
- **核查判定：** **PASS**。

---

### 目录 15: v0.3.0 测试沙箱标记空目录 (`temp_evidence_v030\sandbox_safe`)
- **完整路径：** `<WORKSPACE_ROOT>\temp_evidence_v030\sandbox_safe`
- **删除前内容：** 纯空目录（0 字节）。
- **业务背景：** 策略对抗测试中作为安全沙箱路径占位符使用，测试清理后变为空目录。
- **核查判定：** **PASS**。

---

### 目录 16: 纯空状态根目录 (`state`)
- **完整路径：** `<WORKSPACE_ROOT>\state`
- **删除前内容：** 在其子目录 `state\jobs` 被清除后，成为纯空目录。
- **核查判定：** **PASS**。

---

## 2. 结论

16 个被删除目录的真实状态、文件数与空间占用与清理报告完全一致。未发现任何误删有效源代码、文档或有效测试证据的情况。
