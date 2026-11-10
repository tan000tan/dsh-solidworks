# STAGE 04 独立审计前只读环境基线核对报告
# AUDIT_ENVIRONMENT_BASELINE.md

**审计项目：** `dsh-solidworks` DSH 插件  
**审计阶段：** STAGE 04 — CAD 核心建模能力 (Core CAD Modeling)  
**审计性质：** 第三方独立技术审计（只读基线盘点）  
**审计时间戳：** 2026-11-06T00:54:00Z  
**审计状态：** **BASELINE VERIFIED (环境就绪，无后台文档污染，只读审计开启)**

---

## 一、审计环境原则与只读声明

根据《STAGE4-INDEPENDENT-AUDIT-01》任务书第二条与第十六条规定，本审计阶段为**严格只读模式**：
- 严禁修改任何生产代码与配置；
- 严禁修改用户已有零件与工程图；
- 严禁执行 Git reset、Git clean、删除文件或清理历史产物；
- 严格核实物理事实，不采信未经核实的声明性文字。

---

## 二、代码仓库与 Git 工作区真实物理状态

通过底层 Git 只读指令对代码仓库进行现场核验：

| 检查项 | 实测物理数据 | 独立审计核验结论 |
| :--- | :--- | :--- |
| **Git 仓库根目录** | `<WORKSPACE_ROOT>/dsh-solidworks-plugin` | 路径统一，工作区结构完整 |
| **Git 当前分支** | `main` | 处于主干跟踪分支 |
| **HEAD Commit Hash** | `7d70bc090d5cef146ac3946bb062667ae30a4cc9` | 确认历史提交锚点 |
| **未提交追踪修改 (Modified)** | 16 个核心配置与库文件（包含 `NOTICE`, `dsh-plugin.json`, `lib/policy.js`, `scripts/sw_connect.py` 等） | 保持现场，严禁任何破坏性还原 |
| **未跟踪目录与产物 (Untracked)** | 包含 `docs/stage4_core_cad/`, `tests/real_cad/`, `audit/`, `vendor/...` | 确认为前期交付文档与实机物证目录，只读保护 |
| **项目版本声明** | `v0.2.0`（`package.json`, `dsh-plugin.json`, `lib/index.js` 统一） | 三方契约版本严格一致 |

---

## 三、宿主运行时与桌面 CAD 进程状态

| 运行时 / 进程 | 版本与物理参数 | 审计核验结论 |
| :--- | :--- | :--- |
| **Node.js 运行时** | `v24.21.0` (x64) | 宿主插件环境健康 |
| **Python 运行时** | `Python 3.13.16` (`<PYTHON_RUNTIME>/python.exe`) | FastMCP 服务端底层引擎正常 |
| **SolidWorks 进程** | `SLDWORKS.exe` (PID: 11784) | 进程长期在线，前台响应正常 |
| **SolidWorks 内存开销** | 工作集内存: `484.6 MB` / 句柄数: `2252` | 资源开销处于正常稳态区间 |
| **活动打开文档数** | `0` (Titles: `set()`) | **干净基线！** 无后台残留僵尸文档 |
| **磁盘驱动器剩余空间** | D 盘已用 `439.31 GB`，剩余 `184.25 GB` | 磁盘存储充裕，满足审计需要 |

---

## 四、MCP 契约与工具注册状态

- **MCP 工具声明清册**：
  - `dsh-plugin.json` 声明：73 项工具（71 项 FastMCP CAD 工具 + 2 项 Node.js 特权元工具：`solidworks_status`, `solidworks_confirm`）；
  - `lib/policy.js` 风险矩阵：73 项工具全量映射（包含 HIGH / WRITE / READ 三级安全策略）；
- **离线契约自动化测试基线**：
  - 执行 `npm.cmd test`，全部 4 套测试套件 **68/68 PASS**（`policy.test.js` 27 项、`mcp.test.js` 13 项、`schema.test.js` 16 项、`package.test.js` 12 项）；
  - 路径脱敏校验：100% 通过，无开发机私有绝对路径泄漏。

---

## 五、第四阶段物理产物与物证目录盘点

核查 `docs/stage4_core_cad/` 与 `tests/real_cad/sandbox/`，确认以下前置物证物理存在：
1. `docs/stage4_core_cad/STAGE4_BASELINE_AUDIT.md` (已落盘)
2. `docs/stage4_core_cad/STAGE4_TECHNICAL_DESIGN.md` (已落盘)
3. `docs/stage4_core_cad/STAGE4_IMPLEMENTATION_REPORT.md` (已落盘)
4. `docs/stage4_core_cad/STAGE4_MODEL_EXPERIMENTS.md` (已落盘)
5. `docs/stage4_core_cad/STAGE4_VERIFICATION_REPORT.md` (已落盘)
6. `docs/stage4_core_cad/STAGE4_DSH_E2E_REPORT.md` (已落盘)
7. `docs/stage4_core_cad/STAGE4_STABILITY_REPORT.md` (已落盘)
8. `docs/stage4_core_cad/STAGE4_ADVERSARIAL_REVIEW.md` (已落盘)
9. `docs/stage4_core_cad/STAGE4_FILE_CHANGE_LEDGER.md` (已落盘)
10. `docs/stage4_core_cad/STAGE4_FINAL_ACCEPTANCE.md` (已落盘)
11. `tests/real_cad/sandbox/stage4_core/stage4_benchmark_evidence.json` (SHA-256 锁定)
12. 7 个物理零件文件：`model_a_base_plate.SLDPRT` ~ `model_g_comprehensive.SLDPRT` 均在沙箱就绪。

**只读基线核查结论：** 审计环境健康完备，各项参数与物理文件真实存在，未发现虚构或环境缺失，准予正式展开独立对抗式审计。
