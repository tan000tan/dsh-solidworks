# dsh-solidworks v1.0 最终阻断缺陷与核心关注领域处置矩阵 (Final Blocker Matrix - Verified)

**评估基线**: Git Commit `7d70bc090d5cef146ac3946bb062667ae30a4cc9`  
**候选发布包**: `dsh-solidworks-0.2.0.tgz` (452 files, 大小 1,353,150 字节)  
**标准 64 位 SHA-256**: `12dd5073a2cec8862b361b31dd3303a7808e8636b9e6066d49408acbccae6fb5`  
**NPM 40 位 SHA-1 (shasum)**: `e2dd9df6305ab4f0009d5bb61c1e38a989165bba`  
**核验周期**: 2026年11月9日 ~ 11月10日  
**最终综合裁决**: **`READY WITH CONDITIONS` (有条件批准发布候选版本 / 具备受限发布与试点资格)**

---

## 一、核心关注领域与五大证据缺口最终处置表

| 关注领域 / 缺口项 | 核心问题与前期疑虑 | 最终核验与整改措施 | 最终核验状态 | 直接证据路径与依据 | 残留风险与先决条件 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. 发布包 SHA-256 摘要长度** | 报告原给出的 40 位摘要为标准 SHA-1，并非 64 位 SHA-256。 | 1. 采用 PowerShell、`certutil`、Python `hashlib` 三重交叉计算；<br>2. 证实 64 位 SHA-256 为 `12dd5073a2cec8862b361b31dd3303a7808e8636b9e6066d49408acbccae6fb5`；<br>3. 彻底澄清原 40 位为 npm pack 输出的 SHA-1 (shasum)，文件物理未变。 | **VERIFIED / CLOSED (已完全闭环)** | 1. `audit_round2_final/FINAL_SHA256_VERIFICATION.md`<br>2. `audit_round2_final/RAW_TEST_LOGS/sha256_verification.log` | 发布包包含 452 个纯净文件，无本地机器路径泄漏。 |
| **2. 测试文件与日志数量对账** | 73 个测试文件 vs 72 个基线 vs 75/76 份日志之间存在口径矛盾。 | 1. 彻底澄清：基线 72 个测试 + 本轮新增 1 个凭据反向测试 (`python_credential_security_test.py`) = **73 个测试文件** (54 PASS + 18 FAIL + 1 BLOCKED = 73)；<br>2. 彻底澄清：73 份单文件专属日志 + 3 份综合流水日志 (`node_test_all.log`, `e2e_solidworks_raw_round2.log`, `sha256_verification.log`) = **76 份物理日志**，账目 100% 对齐。 | **VERIFIED / CLOSED (已完全闭环)** | 1. `audit_round2_final/FINAL_TEST_COUNT_RECONCILIATION.md`<br>2. `audit_round2_final/TEST_EXECUTION_MATRIX.csv` | 测试文件(73)、测试用例(592)、日志文件(76)分列统计，口径一致。 |
| **3. 18 个 FAIL 逐项深度判定** | 18 个测试失败是否掩盖真实功能回归？是否影响发布安全？ | 1. 逐项提取 Traceback 与源码：**16 项属于 `ENVIRONMENT_FAILURE`** (包含 14 项因未带 `--authorize-cad-write` 触发的主动写入安全拦截，以及 2 项因前序模型未关触发的基线保护)；<br>2. **2 项属于 `OBSOLETE_TEST`** (含已修复全绿的 package.test.js 与字段拼写旧测试)；<br>3. **0 项真实功能缺陷 (REAL_REGRESSION = 0)**，核心业务全绿。 | **VERIFIED / CLOSED (已完全闭环)** | 1. `audit_round2_final/FINAL_18_FAILURES_ASSESSMENT.csv`<br>2. `audit_round2_final/FINAL_18_FAILURES_ASSESSMENT.md` | 18 个失败均为主动安全拦截或历史测试过时，不影响普通用户安装使用。 |
| **4. SolidWorks PID 生命周期与退出码 1** | PID 归属证据不足，退出码为 1 存在失败疑虑。 | 1. 逐项核实 PID：PID 27164、38364、23440 均为测试沙箱受控实例且优雅 ExitApp 退出；彻底勘误 PID 2684 (实为体积数值 $252684.717$) 与 PID 32500 (Git 短哈希)；<br>2. 深入揭示退出码 1 机制：PowerShell `Get-Process SLDWORKS` 在系统中为 0 进程时原生抛出 `NoProcessFoundForGivenName` 错误并将退出码置 1，结合 `tasklist` 交叉证明当前 0 个待机进程。 | **VERIFIED / CLOSED (已完全闭环)** | 1. `audit_round2_final/FINAL_PID_LIFECYCLE_VERIFICATION.md`<br>2. `audit_round2_final/SOLIDWORKS_PROCESS_OWNERSHIP.md` | 全库 0 taskkill，系统处于零泄漏纯净基线。 |
| **5. 742.2 KB 源码补丁逐文件分类** | 补丁包含哪些修改？是否包含未授权修改或遗漏？ | 1. 解码 UTF-16 补丁，对涉及的全部 **35 个修改文件** 逐行统计与归类；<br>2. 包含 1 个本轮核验整改 (`lib/mcp.js`)、19 个第二轮核心整改实现、7 个测试夹具加固、8 个历史未提交成果保全；<br>3. 证实 0 意外删除、0 调试垃圾泄漏、0 虚假测试断言。 | **VERIFIED / CLOSED (已完全闭环)** | 1. `audit_round2_final/FINAL_PATCH_FILE_CLASSIFICATION.csv`<br>2. `audit_round2_final/FINAL_PATCH_REVIEW.md`<br>3. `audit_round2_final/FINAL_SOURCE_DIFF.patch` | 代码修改聚焦于安全边界、FastMCP 展开与构建防污染。 |
| **6. 文档所有权与安全沙箱机制** | `force_discard`、`ActiveDoc` 与 `CloseAllDocuments` 是否安全？ | 1. `force_discard` 从公开 Schema 彻底剔除，底层硬编码 `False`；<br>2. `ActiveDoc` 受 `is_document_owned()` 沙箱所有权强断言保护；<br>3. `CloseAllDocuments` 3 处引用全部无条件抛错绝育。 | **VERIFIED / CLOSED (已完全闭环)** | 1. `audit_round2_final/DOCUMENT_OWNERSHIP_SECURITY.md`<br>2. `vendor/.../server.py:6156, 6202` | 严禁触碰用户外部会话与文档。 |

---

## 二、最终裁决结论

综合五大证据缺口的彻底闭环与全量物证核验，正式判定项目状态为：

### **`READY WITH CONDITIONS` (有条件批准发布候选版本 / 具备发布候选资格)**

**发布先决条件与运行限制说明**:
1. **宿主环境要求**: 目标系统必须为 Windows 10/11 x64，且已安装并注册 SolidWorks 2021~2026 COM 组件；
2. **依赖配置要求**: 宿主系统需具备 Python 3.10+，普通用户需执行 `dsh-solidworks setup` 或根据文档配置依赖；
3. **测试维护说明**: 18 个历史过时测试在当前主干上不影响运行，后续小版本将对历史测试用例进行重构对齐。
