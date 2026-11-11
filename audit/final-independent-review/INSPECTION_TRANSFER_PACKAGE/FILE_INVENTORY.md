# 独立审查资料清单与实物物证清单 (FILE_INVENTORY)
## dsh-solidworks 六组核心审计物证与数据全景索引

**审计时间**：2026-11-06  
**项目仓库**：`dsh-solidworks` (Commit: `7d70bc090d5cef146ac3946bb062667ae30a4cc9`)  
**独立审查包目录**：`audit/final-independent-review/INSPECTION_TRANSFER_PACKAGE/`  
**审计原则**：
1. 原始文件完全保持只读，未对原项目文件进行任何修改、重命名、移动或删除；
2. 严禁伪造任何缺失证据，实事求是标注每一项资料状态；
3. 标注真实的物理绝对路径、文件大小（字节）和 SHA-256 哈希值。

---

### 一、六组核心资料检查与收录总览

| 资料分组编号与名称 | 分组状态 | 收录文件数 | 缺失文件数 | 核心现状与缺口说明 |
|:---|:---:|:---:|:---:|:---|
| **1. 真实环境基线及原始采集日志** | **INCOMPLETE** | 1 | 1 | 基线报告完备；独立的原始硬件探针/采集终端输出 `.log` 文件缺失（当时采集直接整合写入报告中） |
| **2. 完整工具能力清单** | **FOUND** | 2 | 0 | 包含 12 核心工具 8 级状态 CSV 与 75 领域全景普查报告，数据齐全 |
| **3. 176 项测试的编号清单和原始日志**| **INCOMPLETE** | 6 | 1 | 测试编号、套件分布与分项报告完整；缺少全局集中式的 176 项单文件合并原始终端输出日志 |
| **4. MST-AGU-2026 全部 SolidWorks 模型**| **FOUND** | 8 | 0 | 3 零件 + 1 装配体 + 1 工程图底图 + STEP + STL + 矢量 PDF 物理文件完好 |
| **5. cad_quality_inspector & metrics** | **FOUND** | 2 | 0 | 质量检验源码与实机度量 JSON 数据完备存在 |
| **6. 07_MASTER_ISSUE_DATABASE.json** | **FOUND** | 2 | 0 | 1,240 项缺陷结构化主数据库 JSON 与 CSV 对照表齐全 |

---

### 二、详细物证清单与 SHA-256 哈希对照表

#### 第一组：真实环境基线及原始采集日志 (状态: INCOMPLETE)
- **现状说明**：真实环境的硬件配置、操作系统版本、SolidWorks 进程 PID、Revision 与依赖版本均已详细记录在 `01_REAL_ENVIRONMENT_BASELINE.md` 中。但在项目仓库中，未发现单独落盘的原始探针日志文件（如 `baseline_probe.log`），当时探针命令的控制台输出直接被格式化写入了 Markdown 报告。

| 文件名称 | 状态 | 原始绝对路径 | 文件大小 (Bytes) | SHA-256 哈希值 | 独立审查包副本路径 |
|:---|:---:|:---|:---:|:---|:---|
| `01_REAL_ENVIRONMENT_BASELINE.md` | **FOUND** | `D:/Agent工作区/DeepSeek Harness工作区/dsh-solidworks-plugin/audit/final-independent-review/stage7-extreme-real-world-validation/01_REAL_ENVIRONMENT_BASELINE.md` | 5,599 | `0b1fd3402d464cbdcae93ac14c4fcf3a01a50e1850d584b96d3b10fb5e7795da` | `01_真实环境基线及原始采集日志/01_REAL_ENVIRONMENT_BASELINE.md` |
| `baseline_probe.log` | **MISSING** | `D:/Agent工作区/DeepSeek Harness工作区/dsh-solidworks-plugin/audit/final-independent-review/stage7-extreme-real-world-validation/baseline_probe.log` | 0 | `N/A (FILE NOT FOUND)` | `N/A (未生成独立原始文件)` |

---

#### 第二组：完整工具能力清单 (状态: FOUND)
- **现状说明**：提供机器可读的 `TOOL_CAPABILITY_MATRIX.csv`（界定原生支持、API可访、插件实现、MCP暴露、DSH发现、实机执行等 8 级状态），以及涵盖 75 个机械 CAD 领域分级普查的 `02_SOLIDWORKS_FULL_CAPABILITY_MATRIX.md`。

| 文件名称 | 状态 | 原始绝对路径 | 文件大小 (Bytes) | SHA-256 哈希值 | 独立审查包副本路径 |
|:---|:---:|:---|:---:|:---|:---|
| `TOOL_CAPABILITY_MATRIX.csv` | **FOUND** | `D:/Agent工作区/DeepSeek Harness工作区/dsh-solidworks-plugin/audit/final-independent-review/FINAL_REVIEW_PACKAGE/TOOL_CAPABILITY_MATRIX.csv` | 1,270 | `bcaf7072c531ec36f2e9c48cc0addac82f0ff02d55501d27b975a9b3c1efc704` | `02_完整工具能力清单/TOOL_CAPABILITY_MATRIX.csv` |
| `02_SOLIDWORKS_FULL_CAPABILITY_MATRIX.md` | **FOUND** | `D:/Agent工作区/DeepSeek Harness工作区/dsh-solidworks-plugin/audit/final-independent-review/stage7-extreme-real-world-validation/02_SOLIDWORKS_FULL_CAPABILITY_MATRIX.md` | 17,996 | `0879c10e6e3ddcc4262727d88526fd35596e614741314f8af3dcc18a8c1eb681` | `02_完整工具能力清单/02_SOLIDWORKS_FULL_CAPABILITY_MATRIX.md` |

---

#### 第三组：176 项测试的编号清单和原始日志 (状态: INCOMPLETE)
- **现状说明**：176 项测试在 `TEST_RESULT_SUMMARY.csv` 中有完整的套件划分（Node 门禁 68 项、Python 阶段 30 项、多角色口语 10 项、滥用压力 38 项、状态兼容 18 项、复杂实机 12 项），并且每一类测试均有专属的 Markdown 报告与原始脚本。然而，仓库内未单独保存一份集中式的 `test_execution_raw.log` 合并输出文本，测试在需要时通过自动化命令动态重现。

| 文件名称 | 状态 | 原始绝对路径 | 文件大小 (Bytes) | SHA-256 哈希值 | 独立审查包副本路径 |
|:---|:---:|:---|:---:|:---|:---|
| `TEST_RESULT_SUMMARY.csv` | **FOUND** | `D:/Agent工作区/DeepSeek Harness工作区/dsh-solidworks-plugin/audit/final-independent-review/FINAL_REVIEW_PACKAGE/TEST_RESULT_SUMMARY.csv` | 1,596 | `9c85474fb2f945927d9a26534035ce1f6406efa26856ac3d519be64f97f38527` | `03_176_项测试的编号清单和原始日志/TEST_RESULT_SUMMARY.csv` |
| `17_TEST_AND_VALIDATION_REPORT.md` | **FOUND** | `D:/Agent工作区/DeepSeek Harness工作区/dsh-solidworks-plugin/audit/final-independent-review/17_TEST_AND_VALIDATION_REPORT.md` | 7,092 | `e879b48662c90a218f59544888d46315ad5058b6b46471d6ac29379f4321f59a` | `03_176_项测试的编号清单和原始日志/17_TEST_AND_VALIDATION_REPORT.md` |
| `03_REAL_USER_TEST_REPORT.md` | **FOUND** | `D:/Agent工作区/DeepSeek Harness工作区/dsh-solidworks-plugin/audit/final-independent-review/stage7-extreme-real-world-validation/03_REAL_USER_TEST_REPORT.md` | 10,144 | `77b5611842eebfb067f7388e50babcbfb162f5b28001beacc2f913f562f33baf` | `03_176_项测试的编号清单和原始日志/03_REAL_USER_TEST_REPORT.md` |
| `04_ABUSE_AND_STRESS_TEST_REPORT.md` | **FOUND** | `D:/Agent工作区/DeepSeek Harness工作区/dsh-solidworks-plugin/audit/final-independent-review/stage7-extreme-real-world-validation/04_ABUSE_AND_STRESS_TEST_REPORT.md` | 8,527 | `4c4953a36a84031242e29aaad2b63280b50f599df4904b52e972712179a9f7a4` | `03_176_项测试的编号清单和原始日志/04_ABUSE_AND_STRESS_TEST_REPORT.md` |
| `05_ENVIRONMENT_COMPATIBILITY_REPORT.md` | **FOUND** | `D:/Agent工作区/DeepSeek Harness工作区/dsh-solidworks-plugin/audit/final-independent-review/stage7-extreme-real-world-validation/05_ENVIRONMENT_COMPATIBILITY_REPORT.md` | 5,604 | `7bf73e0d37c38525a35a7407bb61facf60a9f8cf7b083f56c81bd2a559186c30` | `03_176_项测试的编号清单和原始日志/05_ENVIRONMENT_COMPATIBILITY_REPORT.md` |
| `07_COMPLEX_MODEL_EXECUTION_REPORT.md` | **FOUND** | `D:/Agent工作区/DeepSeek Harness工作区/dsh-solidworks-plugin/audit/final-independent-review/stage7-extreme-real-world-validation/07_COMPLEX_MODEL_EXECUTION_REPORT.md` | 7,521 | `01aa325d100c052f99e7b89fd152680f3dcd9583db5227aa5d9dafa0a61e9fad` | `03_176_项测试的编号清单和原始日志/07_COMPLEX_MODEL_EXECUTION_REPORT.md` |
| `test_execution_raw.log` | **MISSING** | `D:/Agent工作区/DeepSeek Harness工作区/dsh-solidworks-plugin/test_execution_raw.log` | 0 | `N/A (FILE NOT FOUND)` | `N/A (未集中归档为一个单一log)` |

---

#### 第四组：MST-AGU-2026 全部 SolidWorks 原生模型文件 (状态: FOUND)
- **现状说明**：在真实 Windows 11 + SolidWorks 2026 SP4.1 原生环境生成的 3 个机械零件、1 个装配体、1 套工程图底图以及 3 种衍生工业交换标准格式（STEP AP214、3D打印 STL 网格、矢量 PDF）文件均完整落盘，尺寸与二进制内容完好。

| 文件名称 | 状态 | 原始绝对路径 | 文件大小 (Bytes) | SHA-256 哈希值 | 独立审查包副本路径 |
|:---|:---:|:---|:---:|:---|:---|
| `mst_shaft.SLDPRT` | **FOUND** | `D:/Agent工作区/DeepSeek Harness工作区/dsh-solidworks-plugin/audit/final-independent-review/stage7-extreme-real-world-validation/evidence/mst_shaft.SLDPRT` | 87,939 | `8110d47640e2f80aa71aedc2b3e17e9caeea35db170016e00f103b479f524a56` | `04_MST-AGU-2026_全部_SolidWorks_原生模型文件/mst_shaft.SLDPRT` |
| `mst_base.SLDPRT` | **FOUND** | `D:/Agent工作区/DeepSeek Harness工作区/dsh-solidworks-plugin/audit/final-independent-review/stage7-extreme-real-world-validation/evidence/mst_base.SLDPRT` | 72,057 | `474d4e4ad2222cb5e40f468e147fa42be2f920d67597d006d7fd2b0fb3bef6bc` | `04_MST-AGU-2026_全部_SolidWorks_原生模型文件/mst_base.SLDPRT` |
| `mst_gear.SLDPRT` | **FOUND** | `D:/Agent工作区/DeepSeek Harness工作区/dsh-solidworks-plugin/audit/final-independent-review/stage7-extreme-real-world-validation/evidence/mst_gear.SLDPRT` | 102,919 | `96d71c07a8ca11040e5f61a79a63f50798c349c12119e5ad6ce372676f616207` | `04_MST-AGU-2026_全部_SolidWorks_原生模型文件/mst_gear.SLDPRT` |
| `mst_assembly.SLDASM` | **FOUND** | `D:/Agent工作区/DeepSeek Harness工作区/dsh-solidworks-plugin/audit/final-independent-review/stage7-extreme-real-world-validation/evidence/mst_assembly.SLDASM` | 75,770 | `b0f9e44c7a587e690dbf96d817832839b0f927295572c47ce9d07dee932339e4` | `04_MST-AGU-2026_全部_SolidWorks_原生模型文件/mst_assembly.SLDASM` |
| `mst_drawing.SLDDRW` | **FOUND** | `D:/Agent工作区/DeepSeek Harness工作区/dsh-solidworks-plugin/audit/final-independent-review/stage7-extreme-real-world-validation/evidence/mst_drawing.SLDDRW` | 66,431 | `a52b925ca31a10aa64a69122f491f1ddbc31d3070ae8669243300b6ee1e9d40e` | `04_MST-AGU-2026_全部_SolidWorks_原生模型文件/mst_drawing.SLDDRW` |
| `mst_assembly.step` | **FOUND** | `D:/Agent工作区/DeepSeek Harness工作区/dsh-solidworks-plugin/audit/final-independent-review/stage7-extreme-real-world-validation/evidence/mst_assembly.step` | 108,278 | `aa5f47305a0bf4c0e95ec67d633479feb1e048546833e77ea9a32e821ec5f7f4` | `04_MST-AGU-2026_全部_SolidWorks_原生模型文件/mst_assembly.step` |
| `mst_shaft.STL` | **FOUND** | `D:/Agent工作区/DeepSeek Harness工作区/dsh-solidworks-plugin/audit/final-independent-review/stage7-extreme-real-world-validation/evidence/mst_shaft.STL` | 10,884 | `09595db22d8ef3a6083b9cfadbcde79f926fb44d30fc555ed3158960ebed5bbc` | `04_MST-AGU-2026_全部_SolidWorks_原生模型文件/mst_shaft.STL` |
| `mst_drawing.pdf` | **FOUND** | `D:/Agent工作区/DeepSeek Harness工作区/dsh-solidworks-plugin/audit/final-independent-review/stage7-extreme-real-world-validation/evidence/mst_drawing.pdf` | 44,748 | `f57f3430e0fc7b8dc089f772079d93ba767fa5885f756153cdd82710e5d23d08` | `04_MST-AGU-2026_全部_SolidWorks_原生模型文件/mst_drawing.pdf` |

---

#### 第五组：cad_quality_inspector.py 和 mst_execution_metrics.json (状态: FOUND)
- **现状说明**：质量检验模块源码与物理抽取的数据文件均完整存在。源码位于 `docs/stage5_advanced_ai_cad/scripts/cad_quality_inspector.py`，度量 JSON 位于实机证据目录中。

| 文件名称 | 状态 | 原始绝对路径 | 文件大小 (Bytes) | SHA-256 哈希值 | 独立审查包副本路径 |
|:---|:---:|:---|:---:|:---|:---|
| `cad_quality_inspector.py` | **FOUND** | `D:/Agent工作区/DeepSeek Harness工作区/dsh-solidworks-plugin/docs/stage5_advanced_ai_cad/scripts/cad_quality_inspector.py` | 9,518 | `1955218caaac11275bab62f8f5e2b4d5f8e453e9d902e1662a2b8dd07acb8d74` | `05_cad_quality_inspector/cad_quality_inspector.py` |
| `mst_execution_metrics.json` | **FOUND** | `D:/Agent工作区/DeepSeek Harness工作区/dsh-solidworks-plugin/audit/final-independent-review/stage7-extreme-real-world-validation/evidence/mst_execution_metrics.json` | 1,767 | `c33b2ba137bccfa40e6bdbb4601809b28ddc3e52777d621cbf291e6a981259f1` | `05_cad_quality_inspector/mst_execution_metrics.json` |

---

#### 第六组：07_MASTER_ISSUE_DATABASE.json (状态: FOUND)
- **现状说明**：包含整个项目生命周期中收录的 1,240 项缺陷、限制与优化项的全局 JSON 数据库完整存在，并附带有结构化的 CSV 格式对照文件。

| 文件名称 | 状态 | 原始绝对路径 | 文件大小 (Bytes) | SHA-256 哈希值 | 独立审查包副本路径 |
|:---|:---:|:---|:---:|:---|:---|
| `07_MASTER_ISSUE_DATABASE.json` | **FOUND** | `D:/Agent工作区/DeepSeek Harness工作区/dsh-solidworks-plugin/audit/final-independent-review/07_MASTER_ISSUE_DATABASE.json` | 746,582 | `988c925ed898750857e592228397e356928e706ae25798c67bbb7b02c6070244` | `06_07_MASTER_ISSUE_DATABASE/07_MASTER_ISSUE_DATABASE.json` |
| `MASTER_DEFECT_DATABASE.csv` | **FOUND** | `D:/Agent工作区/DeepSeek Harness工作区/dsh-solidworks-plugin/audit/final-independent-review/FINAL_REVIEW_PACKAGE/MASTER_DEFECT_DATABASE.csv` | 478,840 | `72d00a2862c485609cdfc365ebd27fc2bfccdfd6fff12b967feae16b66453d99` | `06_07_MASTER_ISSUE_DATABASE/MASTER_DEFECT_DATABASE.csv` |

---

### 三、独立审查包副本目录结构

全部找到的物理物证已完整复制至独立审查包目录（原文件绝对只读未改动）：
```
audit/final-independent-review/INSPECTION_TRANSFER_PACKAGE/
├── FILE_INVENTORY.md (本文件)
├── 01_真实环境基线及原始采集日志/
│   └── 01_REAL_ENVIRONMENT_BASELINE.md (5,599 Bytes)
├── 02_完整工具能力清单/
│   ├── TOOL_CAPABILITY_MATRIX.csv (1,270 Bytes)
│   └── 02_SOLIDWORKS_FULL_CAPABILITY_MATRIX.md (17,996 Bytes)
├── 03_176_项测试的编号清单和原始日志/
│   ├── TEST_RESULT_SUMMARY.csv (1,596 Bytes)
│   ├── 17_TEST_AND_VALIDATION_REPORT.md (7,092 Bytes)
│   ├── 03_REAL_USER_TEST_REPORT.md (10,144 Bytes)
│   ├── 04_ABUSE_AND_STRESS_TEST_REPORT.md (8,527 Bytes)
│   ├── 05_ENVIRONMENT_COMPATIBILITY_REPORT.md (5,604 Bytes)
│   └── 07_COMPLEX_MODEL_EXECUTION_REPORT.md (7,521 Bytes)
├── 04_MST-AGU-2026_全部_SolidWorks_原生模型文件/
│   ├── mst_shaft.SLDPRT (87,939 Bytes)
│   ├── mst_base.SLDPRT (72,057 Bytes)
│   ├── mst_gear.SLDPRT (102,919 Bytes)
│   ├── mst_assembly.SLDASM (75,770 Bytes)
│   ├── mst_drawing.SLDDRW (66,431 Bytes)
│   ├── mst_assembly.step (108,278 Bytes)
│   ├── mst_shaft.STL (10,884 Bytes)
│   └── mst_drawing.pdf (44,748 Bytes)
├── 05_cad_quality_inspector/
│   ├── cad_quality_inspector.py (9,518 Bytes)
│   └── mst_execution_metrics.json (1,767 Bytes)
└── 06_07_MASTER_ISSUE_DATABASE/
    ├── 07_MASTER_ISSUE_DATABASE.json (746,582 Bytes)
    └── MASTER_DEFECT_DATABASE.csv (478,840 Bytes)
```
