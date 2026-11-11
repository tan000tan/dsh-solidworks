# 整改阶段 0：环境与证据冻结基线报告 (`00_REMEDIATION_BASELINE.md`)

- **生成时间**：2026-11-06T16:18:00+08:00
- **Git 分支**：`main`
- **最新 Commit**：`7d70bc0 release: finalize v0.2.0`
- **未提交文件数**：`65` 项（全部为未跟踪的 audit 产物，无既有源码被污染）

## 1. 独立审查原始证据 7 份交付物完整性冻结

| 文件名 | 存在性 | 字节大小 | 冻结 SHA-256 |
| :--- | :--- | ---: | :--- |
| `ZIP_ENTITY_AUDIT.md` | `EXISTS` | `6,215` | `e3311813131ce21093a557045c9f150718d34c03e90c1581dd09fcf12aa0e6c9` |
| `EVIDENCE_HASH_AUDIT.csv` | `EXISTS` | `9,554` | `896a7f2e567c2e799eef707118ff35ab0289406c3790edbd859057b0cec47f77` |
| `JSON_INTEGRITY_AUDIT.md` | `EXISTS` | `29,020` | `8aab7cd40004a6539f45816c87bdf6977ad5eda156b99b371ebc06f874e051d3` |
| `TEST_EVIDENCE_TRACEABILITY.csv` | `EXISTS` | `6,361` | `4615b5d70e59bde932b609f190674d6e4f2d67c643c870e9615dc2a4fbe752a3` |
| `CLAIM_EVIDENCE_TRACEABILITY.csv` | `EXISTS` | `6,511` | `fd0e45ddce53714112a9148c39df8e2dd48113475d33f64006835ed57cdf5f6a` |
| `BINARY_EVIDENCE_AUDIT.md` | `EXISTS` | `9,932` | `1a20daf91c9e3db212d1d56610ca5fdb775b8844cbf4c121ffc30a17c290ec26` |
| `INDEPENDENT_EVIDENCE_VERDICT.md` | `EXISTS` | `6,560` | `95c9cd581dee9d38bd81dab62656faf9a0fcb78ab3e996e1104d5e66bf81ea68` |

## 2. 原始阶段七 CAD 模型文件冻结（严禁覆盖或修改）

| 文件名 | 存在性 | 字节大小 | 冻结 SHA-256 |
| :--- | :--- | ---: | :--- |
| `mst_shaft.SLDPRT` | `EXISTS` | `87,939` | `8110d47640e2f80aa71aedc2b3e17e9caeea35db170016e00f103b479f524a56` |
| `mst_base.SLDPRT` | `EXISTS` | `72,057` | `474d4e4ad2222cb5e40f468e147fa42be2f920d67597d006d7fd2b0fb3bef6bc` |
| `mst_gear.SLDPRT` | `EXISTS` | `102,919` | `96d71c07a8ca11040e5f61a79a63f50798c349c12119e5ad6ce372676f616207` |
| `mst_assembly.SLDASM` | `EXISTS` | `75,770` | `b0f9e44c7a587e690dbf96d817832839b0f927295572c47ce9d07dee932339e4` |
| `mst_drawing.SLDDRW` | `EXISTS` | `66,431` | `a52b925ca31a10aa64a69122f491f1ddbc31d3070ae8669243300b6ee1e9d40e` |
| `mst_assembly.step` | `EXISTS` | `108,278` | `aa5f47305a0bf4c0e95ec67d633479feb1e048546833e77ea9a32e821ec5f7f4` |
| `mst_shaft.STL` | `EXISTS` | `10,884` | `09595db22d8ef3a6083b9cfadbcde79f926fb44d30fc555ed3158960ebed5bbc` |
| `mst_drawing.pdf` | `EXISTS` | `44,748` | `f57f3430e0fc7b8dc089f772079d93ba767fa5885f756153cdd82710e5d23d08` |
| `mst_execution_metrics.json` | `EXISTS` | `1,767` | `c33b2ba137bccfa40e6bdbb4601809b28ddc3e52777d621cbf291e6a981259f1` |

## 3. SolidWorks 2026 运行环境状态

- **COM 连接状态**：`DISCONNECTED`
- **SolidWorks PID**：`None`
- **当前打开文档数**：`0`
- **当前活动文档**：`None`

## 4. MCP 工具注册基线

- **已注册工具总数**：`0`
- **工具清单**：``
