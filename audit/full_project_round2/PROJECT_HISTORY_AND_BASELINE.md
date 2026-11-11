# dsh-solidworks 项目历史演进与系统基线追溯报告

> **报告编号：** `AUDIT-R2-01-PROJECT-HISTORY-AND-BASELINE`  
> **审查基线：** Commit `7d70bc0` (v0.2.0) 至当前工作区 HEAD  
> **审计性质：** 独立第三方全项目追溯审计  
> **归档目录：** `audit/full_project_round2/`  

---

## 一、项目演进全景与阶段目标定义

`dsh-solidworks`（DeepSeek Harness SolidWorks 插件）旨在为 DeepSeek Harness (DSH) 宿主提供安全、受控、高可靠的 SolidWorks CAD 自主建模与自动化工程能力。项目生命周期规划为六个阶段：

| 阶段代号 | 阶段名称 | 核心目标与技术范围 | 历史状态声明 | 本次复核基准 |
|:---|:---|:---|:---:|:---:|
| **第一阶段 (Phase 1)** | 基础架构与审计准备 | 建立 Node.js 宿主与 Python FastMCP 服务端通信、三级权限安全策略（read/write/high）、路径规范化沙箱与 DEF-01~04 缺陷闭环 | 封版 (v0.1.0) | 严格复核封版物料与安全门禁有效性 |
| **第二阶段 (Phase 2)** | AI 自主建模基础 | 建立 FeatureGraph IR 数据结构、Kahn 拓扑排序、逆向依赖分析、安全尺寸管理体系（`dimension_manager.py`）与 v0.2.0 准备 | 封版 (v0.2.0) | 复核 IR 规范性、依赖解析边界与尺寸修改能力 |
| **第三阶段 (Phase 3)** | 扩展 CAD 能力与技术准备 | 探索多实体、基础装配配合、工程图、跨文档操作，产出 7 份技术准备报告与架构选型 | 阶段性结项 | 复核真实代码实现与预研文档界限，防止概念夸大 |
| **第四阶段 (Phase 4)** | 核心 CAD 建模与产品能力 | 落地 `CADGraphExecutor` 执行器、7 个典型模型全套实机建模、事务与逆序回滚、参数化重构、73 项工具接入 DSH | 声称 ACCEPTED | 全面对抗式穿透复核，揭示未完成项与虚假假象 |
| **第五阶段 (Phase 5)** | 高级 AI CAD 研发 | 多方案自动规划比较、自动迭代修改、复杂特征树优化、装配智能规划、综合质量优化 | 正式启动 | 在隔离依赖下并行推进研发 |
| **第六阶段 (Phase 6)** | 全项目回归修复与正式封装 | 全套件对抗回归、缺陷闭环收敛、正式封装上架发布 | 规划中 | 以后续审计通过为准入条件 |

---

## 二、Git 演进历史与关键提交树追溯

通过对项目 Git 历史提交树的深度穿透追溯，确定了以下不可篡改的关键版本基线节点：

```
* 7d70bc0 (tag: v0.2.0) release: finalize v0.2.0
* 911ccb1 Merge remote-tracking branch 'origin/main' into main
* 9c34a22 (tag: v0.1.0) release: finalize v0.1.0 readiness
* bbf94d7 docs: align tarball numbers with the 208-file package
* 2c7837d release: github publish guide, submission yml, licence risk list, release notes
* 3065260 docs: refresh tarball counts to the shipped 204 files
* 73fc59d tests: one command runs all seven suites (DSH_SOLIDWORKS_PYTHON fallback)
* 13e5972 docs: mode surface measured, write loop ready, startup-failure rationale
* fe17a7a verification: Chinese/space path evidence (E21)
* 1cc2909 verification: prove the audit trail and the upgrade path
* 6adbf7c packaging: self-consistent, cache-free tarball
* 6f311b7 v0.1.0: policy-gated SolidWorks plugin for DSH
* d4c7fde 更新 README.md
* 8c0eb34 docs: README 美化（徽章+emoji 结构，保留全部技术内容）
* 8af9bef dsh-solidworks（自本机仓库同步）
```

### 关键节点历史定位：
1. **Commit `8af9bef` ~ `6f311b7`（初创至 v0.1.0-alpha）**：
   - 建立了 Node.js 插件骨架：`dsh-plugin.json`、`lib/index.js`、`lib/policy.js`、`lib/discover.js`；
   - 确立了 FastMCP 71 个工具和 Node 本地 2 个元工具的映射结构；
   - 引入了 `tests/policy.test.js` 和 `tests/mcp.test.js` 门禁。
2. **Commit `9c34a22`（v0.1.0 正式封版）**：
   - 打上 `v0.1.0` 标签；
   - 完成打包测试 `tests/package.test.js`，锁定 204 个发布文件基准。
3. **Commit `7d70bc0`（v0.2.0 正式封版）**：
   - 打上 `v0.2.0` 标签；
   - 彻底修复历史缺陷 DEF-01（`.venv` 优先探测）、DEF-02（4 个工具录入风险表）、DEF-03（版本号硬编码对齐为 `0.2.0`）、DEF-04（Pack and Go 命名对齐）；
   - 正式冻结 v0.2.0 归档材料于 `audit/v0.2.0-product-audit/`。
4. **v0.2.0 之后演进（Phase 3 准备与 Phase 4 核心建模开发）**：
   - 工作区新增了 `vendor/solidworks-automation-skill/scripts/cad_graph_executor.py`、`cad_task_planner.py`、`model_quality_inspector.py`、`model_rebuilder.py` 等 14 个核心 Python 模块；
   - 新增了 9 个离线与集成测试套件；
   - 在 `docs/stage4_core_cad/` 中沉淀了第四阶段相关设计报告、实验记录与两轮审计报告。

---

## 三、真实运行环境与宿主基线核验

审计团队对当前运行环境进行了无篡改的物理探测：

### 3.1 宿主系统与运行时
- **操作系统：** Windows 11 专业版 x64 (Build 22631 / PowerShell 5.1)
- **Node.js 运行时：** `v24.21.0` (x64)
- **Python 运行时：** `3.13.16` (64-bit, `<PYTHON_HOME>\python.exe`)
- **Node 测试框架：** Node.js 内置 Test Runner (`node:test`)
- **Python COM 桥接：** `pywin32` (win32com.client, pythoncom)

### 3.2 SolidWorks 真实版本彻底核实
- **执行程序物理路径：** `<SOLIDWORKS_INSTALL_DIR>\SOLIDWORKS\SLDWORKS.exe`
- **进程文件版本 (FileVersion)：** `34.4.1.1011`
- **产品版本 (ProductVersion)：** `34.4.1.1011`
- **真实工程判定：** 主版本号 `34` 严格对应 **SolidWorks 2026**，次版本号 `4.1` 对应 **SP4.1**。
- **历史报告偏差根因：**
  在第四阶段历史基准测试脚本 `stage4_benchmark_full_suite.py` 第 807 行，开发者硬编码了静态字符串 `"cad_engine": "SolidWorks 2024"`。历史审计报告未经反射验证直接采信了该硬编码字段，导致第一轮审计报告中大量声称“测试环境为 SolidWorks 2024”。本次审计彻底推翻历史陈述，确立系统真实底层为 **SolidWorks 2026 SP4.1**。

---

## 四、全量代码资产与目录布局基线盘点

当前仓库代码资产结构清晰划分为以下四大域：

```
dsh-solidworks-plugin/
├── lib/                               # Node.js 宿主与策略安全层 (Phase 1 封版资产)
│   ├── index.js                       # 插件主入口、MCP 客户端会话管理、Meta 工具
│   ├── policy.js                      # 风险策略引擎、沙箱根目录校验、3 级权限
│   └── discover.js                    # Python 环境与 FastMCP 服务端发现定位
├── vendor/solidworks-automation-skill/ # 核心自动化技能引擎 (Python)
│   ├── mcp-server/server.py           # FastMCP 服务端主入口 (暴露 71 个核心工具)
│   └── scripts/                       # 底层 SolidWorks API 封装与核心图引擎
│       ├── sw_connect.py              # STA 单线程 COM 连接器与生命周期管理
│       ├── sw_part.py                 # 基础零件特征封装 (拉伸、切除、旋转、镜像等)
│       ├── sw_sketch.py               # 2D/3D 草图几何图元与标注封装
│       ├── feature_graph_ir.py        # FeatureGraph IR 数据模型与拓扑验证
│       ├── cad_graph_executor.py      # CAD 拓扑图调度物理执行器 (Phase 4 核心)
│       ├── cad_task_planner.py        # 任务规划器与意图翻译
│       ├── dimension_manager.py       # 尺寸管理器与参数映射
│       ├── model_quality_inspector.py # 质量检查器 (质量属性、几何核验)
│       └── model_rebuilder.py         # 模型重建与强制更新
├── tests/                             # 自动化验证套件
│   ├── policy.test.js                 # 策略引擎 27 项安全单测 (全绿)
│   ├── mcp.test.js                    # MCP 通信与缺陷回归 13 项单测 (全绿)
│   ├── schema.test.js                 # 参数解包与 Schema 转换单测 (全绿)
│   └── package.test.js                # 封装契约、脱敏与清单一致性 12 项单测 (全绿)
├── audit/                             # 独立审计物料库
│   ├── v0.2.0-product-audit/          # v0.2.0 历史封版审计资产 (只读保留)
│   ├── phase-3-preparation/           # 第三阶段技术准备研究报告 (只读保留)
│   └── full_project_round2/           # 本次全项目第二轮追溯审计交付目录
└── docs/                              # 工程与架构规范
    ├── stage4_core_cad/               # 第四阶段核心建模审计与实施文档
    └── stage5_advanced_ai_cad/        # 第五阶段高级 AI CAD 并行研发目录
```

---

## 五、基线一致性审查裁决

1. **宿主层与策略层一致性：** `package.json`、`dsh-plugin.json`、`lib/index.js` 的版本标识与工具清单严格对齐为 73 项（71 MCP + 2 Meta），离线自动化门禁 68/68 项保持 100% PASS。
2. **环境真实性纠正：** 正式纠正宿主 SolidWorks 版本为 2026 SP4.1，推翻“SolidWorks 2024”的错误历史陈述。
3. **基线隔离有效性：** 历史审计目录完整保留，当前审计与后续第五阶段研发严格分立于独立目录，不互相污染。
