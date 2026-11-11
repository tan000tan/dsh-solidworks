# 第一阶段：桌面 ZIP 实体与结构取证报告 (`ZIP_ENTITY_AUDIT.md`)

## 1. 桌面 ZIP 物理属性核验

| 核验项 | 取证结果 |
| :--- | :--- |
| **绝对路径** | `C:\Users\Khalil\Desktop\dsh-independent-review.zip` |
| **首次取证读取状态 (`2026-11-06T15:25:12+08:00`)** | `EXISTS` (`True`) — 已由 Python `zipfile` 完整读取并校验全部 22 个条目 |
| **当前复核状态 (`2026-11-06T15:52:00+08:00`)** | `REMOVED_FROM_DESKTOP` (`False`) — 用户在 15:25 至 15:52 之间清理/移除了桌面上的该 ZIP 文件；源目录 `INSPECTION_TRANSFER_PACKAGE` 全部 22 个文件仍在盘且完好无损。遵循只读最高约束，不重新在桌面创建该 ZIP |
| **压缩包字节大小** | `516,988` bytes |
| **解压后总字节数** | `1,885,829` bytes |
| **最后修改时间 (MTime)** | `2026-11-06T15:12:54.600745` |
| **ZIP 整体 SHA-256** | `2233ddd170f4828688aa0efc8f466673517396cb5370daa5cdef0826aa3271b3` |
| **CRC-32 完整性测试 (`testzip()`)** | `None` (全部 22 个条目 CRC 校验 100% 通过，零损坏) |

## 2. ZIP 条目统计与分类说明（严格区分文件条目与目录条目）

- **ZIP 总条目数 (`len(infolist())`)**：`22`
- **文件条目数 (`is_dir() == False`)**：`22`
- **显式目录条目数 (`is_dir() == True`)**：`0`（Python `zipfile` 打包时仅写入了文件相对路径，未写入独立的空目录项）
- **路径中包含的逻辑一级子目录数**：`6`（`01_真实环境基线及原始采集日志`、`02_完整工具能力清单`、`03_176_项测试的编号清单和原始日志`、`04_MST-AGU-2026_全部_SolidWorks_原生模型文件`、`05_cad_quality_inspector`、`06_07_MASTER_ISSUE_DATABASE`）
- **重名/重复路径条目数**：`0`
- **与 `FILE_INVENTORY.md` 差异说明**：
  1. `FILE_INVENTORY.md` 正文列出了 6 个子目录下的 **21 个数据/物证文件**，并声明缺失 2 个原始日志文件（`environment_probe_raw.log` 与 `test_execution_raw.log`）。
  2. `FILE_INVENTORY.md` 自身作为第 22 个文件位于 ZIP 根目录，因此 ZIP 内部实际包含 `21 + 1 = 22` 个文件条目。
  3. 此前若将“6 个逻辑目录 + 22 个文件”混称为“28 个条目”，属于概念混淆；实际 ZIP Central Directory 中仅有 **22 个文件条目**，**0 个目录条目**。

## 3. 全部 22 个文件条目明细表

| 序号 | 相对路径 (`relative_path`) | 原始大小 (Bytes) | SHA-256 | 与外部源文件比对 |
| :--- | :--- | ---: | :--- | :--- |
| 1 | `FILE_INVENTORY.md` | 14,747 | `3aea3eefb8649aefb328dd890bcae0e504f72fdac169cf89884cb021509ea866` | `MATCH` |
| 2 | `01_真实环境基线及原始采集日志/01_REAL_ENVIRONMENT_BASELINE.md` | 5,599 | `0b1fd3402d464cbdcae93ac14c4fcf3a01a50e1850d584b96d3b10fb5e7795da` | `MATCH` |
| 3 | `02_完整工具能力清单/02_SOLIDWORKS_FULL_CAPABILITY_MATRIX.md` | 17,996 | `0879c10e6e3ddcc4262727d88526fd35596e614741314f8af3dcc18a8c1eb681` | `MATCH` |
| 4 | `02_完整工具能力清单/TOOL_CAPABILITY_MATRIX.csv` | 1,270 | `bcaf7072c531ec36f2e9c48cc0addac82f0ff02d55501d27b975a9b3c1efc704` | `MATCH` |
| 5 | `03_176_项测试的编号清单和原始日志/03_REAL_USER_TEST_REPORT.md` | 10,144 | `77b5611842eebfb067f7388e50babcbfb162f5b28001beacc2f913f562f33baf` | `MATCH` |
| 6 | `03_176_项测试的编号清单和原始日志/04_ABUSE_AND_STRESS_TEST_REPORT.md` | 8,527 | `4c4953a36a84031242e29aaad2b63280b50f599df4904b52e972712179a9f7a4` | `MATCH` |
| 7 | `03_176_项测试的编号清单和原始日志/05_ENVIRONMENT_COMPATIBILITY_REPORT.md` | 5,604 | `7bf73e0d37c38525a35a7407bb61facf60a9f8cf7b083f56c81bd2a559186c30` | `MATCH` |
| 8 | `03_176_项测试的编号清单和原始日志/07_COMPLEX_MODEL_EXECUTION_REPORT.md` | 7,521 | `01aa325d100c052f99e7b89fd152680f3dcd9583db5227aa5d9dafa0a61e9fad` | `MATCH` |
| 9 | `03_176_项测试的编号清单和原始日志/17_TEST_AND_VALIDATION_REPORT.md` | 7,092 | `e879b48662c90a218f59544888d46315ad5058b6b46471d6ac29379f4321f59a` | `MATCH` |
| 10 | `03_176_项测试的编号清单和原始日志/TEST_RESULT_SUMMARY.csv` | 1,596 | `9c85474fb2f945927d9a26534035ce1f6406efa26856ac3d519be64f97f38527` | `MATCH` |
| 11 | `04_MST-AGU-2026_全部_SolidWorks_原生模型文件/mst_assembly.SLDASM` | 75,770 | `b0f9e44c7a587e690dbf96d817832839b0f927295572c47ce9d07dee932339e4` | `MATCH` |
| 12 | `04_MST-AGU-2026_全部_SolidWorks_原生模型文件/mst_assembly.step` | 108,278 | `aa5f47305a0bf4c0e95ec67d633479feb1e048546833e77ea9a32e821ec5f7f4` | `MATCH` |
| 13 | `04_MST-AGU-2026_全部_SolidWorks_原生模型文件/mst_base.SLDPRT` | 72,057 | `474d4e4ad2222cb5e40f468e147fa42be2f920d67597d006d7fd2b0fb3bef6bc` | `MATCH` |
| 14 | `04_MST-AGU-2026_全部_SolidWorks_原生模型文件/mst_drawing.SLDDRW` | 66,431 | `a52b925ca31a10aa64a69122f491f1ddbc31d3070ae8669243300b6ee1e9d40e` | `MATCH` |
| 15 | `04_MST-AGU-2026_全部_SolidWorks_原生模型文件/mst_drawing.pdf` | 44,748 | `f57f3430e0fc7b8dc089f772079d93ba767fa5885f756153cdd82710e5d23d08` | `MATCH` |
| 16 | `04_MST-AGU-2026_全部_SolidWorks_原生模型文件/mst_gear.SLDPRT` | 102,919 | `96d71c07a8ca11040e5f61a79a63f50798c349c12119e5ad6ce372676f616207` | `MATCH` |
| 17 | `04_MST-AGU-2026_全部_SolidWorks_原生模型文件/mst_shaft.SLDPRT` | 87,939 | `8110d47640e2f80aa71aedc2b3e17e9caeea35db170016e00f103b479f524a56` | `MATCH` |
| 18 | `04_MST-AGU-2026_全部_SolidWorks_原生模型文件/mst_shaft.STL` | 10,884 | `09595db22d8ef3a6083b9cfadbcde79f926fb44d30fc555ed3158960ebed5bbc` | `MATCH` |
| 19 | `05_cad_quality_inspector/cad_quality_inspector.py` | 9,518 | `1955218caaac11275bab62f8f5e2b4d5f8e453e9d902e1662a2b8dd07acb8d74` | `MISMATCH` |
| 20 | `05_cad_quality_inspector/mst_execution_metrics.json` | 1,767 | `c33b2ba137bccfa40e6bdbb4601809b28ddc3e52777d621cbf291e6a981259f1` | `MATCH` |
| 21 | `06_07_MASTER_ISSUE_DATABASE/07_MASTER_ISSUE_DATABASE.json` | 746,582 | `988c925ed898750857e592228397e356928e706ae25798c67bbb7b02c6070244` | `MATCH` |
| 22 | `06_07_MASTER_ISSUE_DATABASE/MASTER_DEFECT_DATABASE.csv` | 478,840 | `72d00a2862c485609cdfc365ebd27fc2bfccdfd6fff12b967feae16b66453d99` | `MATCH` |
