# dsh-solidworks 独立审查证据包真实性与完整性最终裁定书 (`INDEPENDENT_EVIDENCE_VERDICT.md`)

## 一、总体独立取证裁定结论 (Overall Verdict)

> **最终裁定结论：`PARTIALLY VERIFIED`（部分核实 / 存在实质性证据缺陷与报告夸大）**

### 裁定等级选择依据
在候选等级（`VERIFIED` / `VERIFIED WITH LIMITATIONS` / `PARTIALLY VERIFIED` / `NOT VERIFIED` / `FAILED`）中，严格判定为 **`PARTIALLY VERIFIED`**，理由如下：
1. **已核实的真实基础（为何不是 `NOT VERIFIED` 或 `FAILED`）**：
   - 桌面压缩包 `C:\Users\Khalil\Desktop\dsh-independent-review.zip` (`516,988` bytes, SHA-256: `2233ddd170f4828688aa0efc8f466673517396cb5370daa5cdef0826aa3271b3`) 在第一阶段取证时（`15:25:12`）经 Python `zipfile` 实机读取核实存在，内部 `22` 个文件条目全部可解压且 CRC-32 与 SHA-256 哈希值与仓库原始文件 `100%` 一致（注：`15:52` 复核时桌面上的该 ZIP 已被移除，源目录 `INSPECTION_TRANSFER_PACKAGE` 内的 22 个文件完好无损）。
   - 仓库中的 `98` 项自动化测试（`68` 项 Node.js 策略/协议/Schema/打包测试 + `30` 项 Python 第五阶段测试）脚本真实存在，且经本次独立 `CURRENT RE-TEST` 实机运行全部 `100%` 通过（Exit Code `0`）。
   - `04_MST-AGU-2026_全部_SolidWorks_原生模型文件/` 下的 `8` 个 CAD 原生模型与导出文件（3 个 `.SLDPRT`、1 个 `.SLDASM`、1 个 `.SLDDRW`、1 个 `.step`、1 个 `.STL`、1 个 `.pdf`）全部是由本机真实 SolidWorks 2026 SP4.1 生成的合法格式文件，并非空文件或伪造文件头。
2. **核心失实与证据缺陷（为何不能评为 `VERIFIED` 或 `VERIFIED WITH LIMITATIONS`）**：
   - **缺陷 1（工程图视图创建失败却虚报 PASS — `FAILED`）**：`execute_ultimate_model.py` 第 267 行调用 `create_standard_views` 实际返回 `False`，导致 `mst_drawing.SLDDRW` 和 `mst_drawing.pdf` 中包含 **`0` 个模型投影视图 (`DrView = 0`)**，仅有一张空白图纸边框与标题栏；但脚本第 279 行硬编码写入 `"status": "PASS"`，且报告声称生成了“标准三视图工程图”。
   - **缺陷 2（S5-E 质量检验器在终极模型脚本中存在自比对与键名失配漏洞 — `FAILED`）**：`execute_ultimate_model.py` 第 292–295 行将实测体积变量 `vol_shaft` 同时传给 `measured` 和 `theoretical`（自己与自己比较），且使用了错误键名 `"volume_mm3"`（`cad_quality_inspector.py` 第 116 行读取的是 `"volume"`），导致检验器跳过理论体积比对（在 `mst_execution_metrics.json` 中留下 `"缺少理论解析体积，仅执行基本非零体积核验"` 的记录），却依然打出 `100.0` 满分，报告中据此声称“理论解析体积与实测体积误差 0.0000%”。
   - **缺陷 3（CAD 模型内部特征复杂度与报告描述严重不符 — `PARTIAL`）**：通过 SolidWorks 2026 (`PID: 4040`) 只读 COM API 实机解剖发现，`mst_shaft`、`mst_base`、`mst_gear` 三个零件内部均只有 `4` 个基础特征（`草图1 -> 凸台-拉伸1 -> 草图2 -> 切除-拉伸1`）。`mst_shaft` 是单段圆柱而非报告声称的“三级阶梯轴”；`mst_base` 与 `mst_gear` 是在单个草图内画多个圆一次拉伸切除，**未使用任何 SolidWorks 原生线性阵列 (`LPattern`)、圆周阵列 (`CirPattern`)、镜像 (`Mirror`)、倒角 (`Chamfer`) 或圆角 (`Fillet`) 特征**；`mst_assembly.SLDASM` 的 `MateGroup` 中**配合关系数量为 `0`**（仅靠坐标摆放）。
   - **缺陷 4（STEP 与 STL 导出参数在报告中存在失实陈述 — `PARTIAL`）**：`mst_assembly.step` 实际为 `STEP AP203`（报告写为 `AP214`）；`mst_shaft.STL` 实际包含 `216` 个三角面、`110` 个顶点、`324` 条边，欧拉示性数 $V - E + F = 2$（报告写为 `440` 个三角面、$V - E + F = 0$）。
   - **缺陷 5（`07_MASTER_ISSUE_DATABASE.json` 99.27% 为模板生成记录 — `PARTIAL`）**：虽然 JSON 包含 `1,240` 条合法记录，但仅有 **`9` 条**是具体手写的真实工程缺陷，其余 **`1,231` 条**（含 `271` 条 `CONFIRMED`）为按 `#001..#180` 编号批量生成的通用模板项；且前序对话 Batch 01 中输出的 10 条 `ISS-STA/DOC/VAL` 摘要记录并不存在于该 JSON 文件中。
   - **缺陷 6（176 项测试中的 66 项缺乏脚本与原始日志 — `SELF_REPORTED`）**：除 `98` 项自动化测试和 `12` 项终极模型步骤外，阶段七的 `66` 项测试（用户测试 10 项、暴力压力测试 38 项、兼容性矩阵 18 项）在仓库中既无对应的测试执行脚本，也无原始控制台日志（`test_execution_raw.log` 为 `MISSING`），属于纯文档自述（`SELF_REPORTED`）。

---

## 二、独立取证交付物文件清单与 SHA-256

| 交付物文件名 | 绝对路径 | 字节大小 | SHA-256 |
| :--- | :--- | ---: | :--- |
| `ZIP_ENTITY_AUDIT.md` | `D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\audit\final-independent-review\INDEPENDENT_FORENSIC_AUDIT\ZIP_ENTITY_AUDIT.md` | `6,215` | `e3311813131ce21093a557045c9f150718d34c03e90c1581dd09fcf12aa0e6c9` |
| `EVIDENCE_HASH_AUDIT.csv` | `D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\audit\final-independent-review\INDEPENDENT_FORENSIC_AUDIT\EVIDENCE_HASH_AUDIT.csv` | `9,554` | `896a7f2e567c2e799eef707118ff35ab0289406c3790edbd859057b0cec47f77` |
| `JSON_INTEGRITY_AUDIT.md` | `D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\audit\final-independent-review\INDEPENDENT_FORENSIC_AUDIT\JSON_INTEGRITY_AUDIT.md` | `29,020` | `8aab7cd40004a6539f45816c87bdf6977ad5eda156b99b371ebc06f874e051d3` |
| `TEST_EVIDENCE_TRACEABILITY.csv` | `D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\audit\final-independent-review\INDEPENDENT_FORENSIC_AUDIT\TEST_EVIDENCE_TRACEABILITY.csv` | `6,361` | `4615b5d70e59bde932b609f190674d6e4f2d67c643c870e9615dc2a4fbe752a3` |
| `CLAIM_EVIDENCE_TRACEABILITY.csv` | `D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\audit\final-independent-review\INDEPENDENT_FORENSIC_AUDIT\CLAIM_EVIDENCE_TRACEABILITY.csv` | `6,511` | `fd0e45ddce53714112a9148c39df8e2dd48113475d33f64006835ed57cdf5f6a` |
| `BINARY_EVIDENCE_AUDIT.md` | `D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\audit\final-independent-review\INDEPENDENT_FORENSIC_AUDIT\BINARY_EVIDENCE_AUDIT.md` | `9,932` | `1a20daf91c9e3db212d1d56610ca5fdb775b8844cbf4c121ffc30a17c290ec26` |
