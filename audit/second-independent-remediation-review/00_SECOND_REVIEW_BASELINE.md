# 第二轮独立整改验收基线与环境冻结报告 (00_SECOND_REVIEW_BASELINE.md)

**审计人员**: 第三方独立整改验收专家组  
**审计启动时间**: 2026-11-06T16:58:00+08:00  
**审计定位**: 纯只读独立复核，独立于整改实施方，绝不修改任何项目文件与 CAD 实体  
**当前 Git 状态**:
- 分支: `main`
- HEAD 提交哈希: `7d70bc090d5cef146ac3946bb062667ae30a4cc9`
- 提交信息: `release: finalize v0.2.0`

---

## 一、原始独立审查证据包 (7 份交付物) 完整性复核

独立核验证明：整改方在整改过程中**100% 遵守了最高约束，未篡改、覆盖或修改原始审查交付物中的任何一个字节**：

| 文件名称 | 相对路径 | 字节大小 | 独立计算 SHA-256 | 复核结论 |
| :--- | :--- | ---: | :--- | :--- |
| `ZIP_ENTITY_AUDIT.md` | `audit/final-independent-review/INDEPENDENT_FORENSIC_AUDIT/ZIP_ENTITY_AUDIT.md` | 6,215 | `e3311813131ce21093a557045c9f150718d34c03e90c1581dd09fcf12aa0e6c9` | **MATCH (未改动)** |
| `EVIDENCE_HASH_AUDIT.csv` | `audit/final-independent-review/INDEPENDENT_FORENSIC_AUDIT/EVIDENCE_HASH_AUDIT.csv` | 9,554 | `896a7f2e567c2e799eef707118ff35ab0289406c3790edbd859057b0cec47f77` | **MATCH (未改动)** |
| `JSON_INTEGRITY_AUDIT.md` | `audit/final-independent-review/INDEPENDENT_FORENSIC_AUDIT/JSON_INTEGRITY_AUDIT.md` | 29,020 | `8aab7cd40004a6539f45816c87bdf6977ad5eda156b99b371ebc06f874e051d3` | **MATCH (未改动)** |
| `TEST_EVIDENCE_TRACEABILITY.csv` | `audit/final-independent-review/INDEPENDENT_FORENSIC_AUDIT/TEST_EVIDENCE_TRACEABILITY.csv` | 6,361 | `4615b5d70e59bde932b609f190674d6e4f2d67c643c870e9615dc2a4fbe752a3` | **MATCH (未改动)** |
| `CLAIM_EVIDENCE_TRACEABILITY.csv` | `audit/final-independent-review/INDEPENDENT_FORENSIC_AUDIT/CLAIM_EVIDENCE_TRACEABILITY.csv` | 6,511 | `fd0e45ddce53714112a9148c39df8e2dd48113475d33f64006835ed57cdf5f6a` | **MATCH (未改动)** |
| `BINARY_EVIDENCE_AUDIT.md` | `audit/final-independent-review/INDEPENDENT_FORENSIC_AUDIT/BINARY_EVIDENCE_AUDIT.md` | 9,932 | `1a20daf91c9e3db212d1d56610ca5fdb775b8844cbf4c121ffc30a17c290ec26` | **MATCH (未改动)** |
| `INDEPENDENT_EVIDENCE_VERDICT.md` | `audit/final-independent-review/INDEPENDENT_FORENSIC_AUDIT/INDEPENDENT_EVIDENCE_VERDICT.md` | 6,560 | `95c9cd581dee9d38bd81dab62656faf9a0fcb78ab3e996e1104d5e66bf81ea68` | **MATCH (未改动)** |

---

## 二、整改交付物清单与遗留文件审计发现

1. **已登记交付物**: 整改清单 `REMEDIATION_SHA256_MANIFEST.csv` 中登记的 28 项文件全部真实存在，文件大小与 SHA-256 校验码 100% 吻合。
2. **清单外遗留文件**: 审计发现整改目录存在 5 项未在 manifest 中登记的脚本与中间产物：
   - `cad_test_sandbox/run_all_remediation_cad.py` (CAD 实机构建主脚本)
   - `cad_test_sandbox/test_diag_drw.SLDDRW` (工程图调试临时文件)
   - `cad_test_sandbox/test_diag_drw.pdf` (工程图调试临时 PDF)
   - `cad_test_sandbox/test_diag_part.SLDPRT` (工程图调试临时零件)
   - `generate_remediation_reports.py` (报告自动生成脚本)
   该 5 项文件已作为审计事实记录入 `01_SHA256_INDEPENDENT_VERIFICATION.csv`。

---

## 三、宿主执行环境基线

- **操作系统**: Windows 11 Pro (10.0.26200 AMD64)
- **CAD 核心**: SolidWorks 2026 SP4.1 (ProgID: `SldWorks.Application.34`, 物理进程 PID: 4312)
- **Python 运行时**: Python 3.13.16 64-bit (`D:\SWCAD-MCP\Python313\python.exe`)
- **Node.js 运行时**: Node.js v22.12.0
