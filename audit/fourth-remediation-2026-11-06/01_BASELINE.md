# 第四轮全量整改与独立验收基线报告 (01_BASELINE.md)

## 1. 任务背景与审计基线

- **项目名称**: `dsh-solidworks` (SolidWorks CAD tools for DeepSeek Harness)
- **项目绝对路径**: `D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin`
- **执行时间**: 2026-11-06 21:55 (UTC+8)
- **基线 Git HEAD**: `7d70bc0` (`release: finalize v0.2.0`)
- **当前 Git 分支**: `main`
- **上轮审计裁定**: `SAFETY INCIDENT — UNRESOLVED` (第三轮独立证据取证复核最终裁定)
- **核心触发原因**: 
  1. 发现历史脚本与 MCP 工具中存在无差别全局关闭全部文档的危险调用 (`sw.CloseAllDocuments(True)`)，缺乏会话隔离与文档归属判定，对宿主 SolidWorks 实例及用户未保存文档构成重大安全隐患。
  2. Concentric Mate (DEF-03) 降级为平面重合 (`Concentric_Orthogonal_Lock`)，未形成原生圆柱面同心配合。
  3. 阶梯轴 CAD 解析实体体积与 STL 离散网格积分体积概念混淆。
  4. CAD 质量检查器 (DEF-05) 存在明文 `provenance` 伪造绕过漏洞。
  5. STEP 导出 (DEF-11) 物理文件头仍为 `AP203` (`CONFIG_CONTROL_DESIGN`) 而非 `AP214`。
  6. 兼容性测试 M09 (DEF-07) 在交互式桌面下条件分支跳过断言，存在空跑通过。

---

## 2. 软硬件与运行环境实机基线

通过执行 `node scripts/doctor.js` 与 Python 运行时内省，确认当前宿主系统配置：

| 维度 | 环境参数 | 状态 / 校验证据 |
| :--- | :--- | :--- |
| **操作系统** | Windows 10.0.26200 (x64) | 兼容 Windows Default 交互式桌面与 Win32 子系统 |
| **Node.js 运行时** | v24.21.0 | 符合 `package.json` 中的 `node: ">=22.12"` 引擎要求 |
| **Python 运行时** | Python 3.13.16 (64-bit) | `D:\SWCAD-MCP\Python313\python.exe` |
| **COM 与核心依赖** | pywin32, win32com, pythoncom, pydantic, mcp | 均已就绪且导入正常 |
| **SolidWorks 安装** | SolidWorks 2026 SP04.1 (Revision 34) | `D:\Solidwork\SOLIDWORKS\SLDWORKS.exe` (注册表 COM CLSID 已注册) |
| **SolidWorks 运行状态**| Standby (待机，后台无运行中进程) | 处于清洁待机状态，无用户交互冲突 |
| **沙箱工作区** | `测试代码\sandbox_benchmark` | 读写权限正常 |

---

## 3. Git 工作区与未暂存状态核验

在整改开始前，执行 `git status` 严格核实仓库状态，坚决遵守不执行任何 `git reset`、`git clean` 或删除未跟踪文件的安全纪律：

- **未暂存修改文件 (Modified)**:
  - `NOTICE`
  - `docs/USER_GUIDE.md`
  - `docs/verification.md`
  - `dsh-plugin.json`
  - `lib/discover.js`
  - `lib/index.js`
  - `lib/policy.js`
  - `tests/failure_injection_test.py`
  - `tests/mcp.test.js`
  - `tests/package.test.js`
  - `tests/probe-server.mjs`
  - `vendor/solidworks-automation-skill/mcp-server/server.py`
  - `vendor/solidworks-automation-skill/scripts/cad_task_context.py`
  - `vendor/solidworks-automation-skill/scripts/dimension_manager.py`
  - `vendor/solidworks-automation-skill/scripts/feature_graph_ir.py`
  - `vendor/solidworks-automation-skill/scripts/sw_connect.py`
- **未跟踪目录与关键资产 (Untracked)**:
  - `audit/` (包含往轮所有独立取证与整改交付包)
  - `docs/stage5_advanced_ai_cad/` (阶段五核心高阶脚本)
  - `tests/rem_*.py` 与 `tests/remediation_*.py` (整改专用测试套件)
  - `tests/real_cad/` (真实 CAD 测试套件)

所有用户既有修改均受到完整保护，未发生覆盖或重置。

---

## 4. 第三轮遗留资产与证据目录完整性核对

核验目录 `audit/third-remediation-2026-11-06/`：
- **报告文档 (14 份)**: 从 `00_THIRD_REMEDIATION_BASELINE.md` 到 `13_THIRD_REMEDIATION_FINAL_REPORT.md`，全部 14 份 Markdown 报告物理存在且只读保留。
- **缺陷数据库**: `ISSUE_DATABASE_THIRD_REMEDIATION.json` (大小 999,411 字节)，包含 1246 条缺陷记录。
- **校验清单**: `THIRD_REMEDIATION_SHA256_MANIFEST.csv` (31 项资产 SHA-256 清单物理核对一致)。
- **测试日志目录**: `test_execution_logs/` (包含 `npm_test_suite.log` 等 6 份原始执行日志)。
- **CAD 沙箱实体**: `cad_test_sandbox/` (包含 `remediated_stepped_shaft.STL`、`remediated_drawing.pdf`、`remediated_assembly.step` 等原生与衍生模型)。

---

## 5. 本轮（第四轮）整改执行原则

1. **安全第一**: 彻底根除 `CloseAllDocuments`、未授权 `CloseDoc` 及任何全量环境清空行为。
2. **拒绝伪装**: 原生特征、装配配合、文件导出与检查器防伪，必须具备真实代码与可复现物理证据；无法在当前环境无风险实现的功能，客观标示为 `NOT_IMPLEMENTED` 或 `BLOCKED_BY_ENVIRONMENT`。
3. **分层分级测试**: 明确切分 Node.js 测试、Python 逻辑测试、FastMCP 协议测试与 SolidWorks COM 实机测试，杜绝以纯 Python/Mock 冒充 CAD 实机验证。
4. **可追溯独立交付**: 全部整改报告、测试日志、安全调用图及物理哈希清单均写入 `audit/fourth-remediation-2026-11-06/`。
