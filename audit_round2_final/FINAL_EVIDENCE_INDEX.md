# 最终独立验收原始证据索引清单 (FINAL_EVIDENCE_INDEX)

**项目名称**: `dsh-solidworks`  
**基线版本**: `v0.2.0`  
**核验日期**: 2026-11-10  
**审计人员**: 独立核验工程师（Antigravity AI Agent）

---

## 一、主交付物索引

| 序号 | 交付物文件名 | 物理绝对路径 | 主要职能与核心结论 |
| :---: | :--- | :--- | :--- |
| 1 | `FINAL_ACCEPTANCE_REPORT.md` | `audit_round2_final/FINAL_ACCEPTANCE_REPORT.md` | 最终验收总体报告与正式发布裁定 |
| 2 | `FINAL_EVIDENCE_INDEX.md` | `audit_round2_final/FINAL_EVIDENCE_INDEX.md` | 本文档，所有原始证据与日志的索引索引总览 |
| 3 | `FINAL_TEST_RECONCILIATION.csv` | `audit_round2_final/FINAL_TEST_RECONCILIATION.csv` | 73 个物理测试文件、592 个测试用例、76 份日志逐项对账表 |
| 4 | `FINAL_FAIL_CLASSIFICATION.csv` | `audit_round2_final/FINAL_FAIL_CLASSIFICATION.csv` | 18 个 FAIL 用例的逐项分类、安全拦截成因与证据链 |
| 5 | `FINAL_PID_LIFECYCLE.md` | `audit_round2_final/FINAL_PID_LIFECYCLE.md` | SolidWorks 进程 PID 生命周期核验、排版纠错与退出码 1 底层机理分析 |
| 6 | `FINAL_PATCH_REVIEW.md` | `audit_round2_final/FINAL_PATCH_REVIEW.md` | 742.2 KB 源码补丁 35 个文件的逐一分类与行级变更审查 |
| 7 | `FINAL_CREDENTIAL_SECURITY_REVIEW.md` | `audit_round2_final/FINAL_CREDENTIAL_SECURITY_REVIEW.md` | Python 凭据安全机制（文件锁、Nonce 持久化、权威控制）10 问实证报告 |
| 8 | `FINAL_RELEASE_MANIFEST.md` | `audit_round2_final/FINAL_RELEASE_MANIFEST.md` | 发布包文件清单、大小、SHA-256、452 文件扫描报告 |
| 9 | `FINAL_RELEASE_RECORD.md` | `audit_round2_final/FINAL_RELEASE_RECORD.md` | Git Commit、Tag、Push、GitHub Release 与 DSH 市场提交全流程执行记录 |

---

## 二、原始日志库索引 (`RAW_TEST_LOGS/`)

目录路径: `audit_round2_final/RAW_TEST_LOGS/`  
文件总数: **76 份原始日志**

### 1. 综合与端到端实机验证日志 (3 份)
- `e2e_solidworks_raw_round2.log` (11,850 字节): 实机端到端执行流水线原始日志（PID 23440 完整生命周期闭环证据）。
- `node_test_all.log` (6,420 字节): Node.js 全套 7 个测试套件执行原始输出（114/114 断言全部 PASS）。
- `sha256_verification.log` (2,850 字节): 独立算法复核发布包 SHA-256 摘要与成员扫描日志。

### 2. 73 份单测试文件专属日志
- `tests_policy.test.js.log` ~ `tests_crash.test.js.log` (7 份): Node.js 核心能力与安全策略日志。
- `tests_python_credential_security_test.py.log` (1 份): Python 凭据 8 项负面安全攻击测试日志。
- `mcp-server-solidworks-main_...` (11 份): 适配器层与编译器单元测试日志。
- `tests_cad_graph_executor_test.py.log` ~ `tests_unified_dimension_migration_test.py.log` (36 份): Python 核心架构、求解器、上下文测试日志。
- `tests_real_cad_...` (18 份): 实机 CAD 功能与 Fail-Closed 安全拦截执行日志。

---

## 三、源码与二进制交付物索引

1. **候选发布安装包**:
   - 路径: `dsh-solidworks-0.2.0.tgz` 及 `dist/dsh-solidworks-0.2.0.tgz`
   - 大小: `1,353,150 字节`
   - SHA-256: `12dd5073a2cec8862b361b31dd3303a7808e8636b9e6066d49408acbccae6fb5`
2. **完整源码补丁**:
   - 路径: `audit_round2_final/FINAL_SOURCE_DIFF.patch`
   - 大小: `742,190 字节` (UTF-16 LE)
   - 包含文件数: 35 个修改文件
3. **市场投稿清单**:
   - 路径: `docs/submission/tan000tan__dsh-solidworks.yml`
   - 规范状态: 符合 `awesome-dsh-plugin` 官方白名单。
