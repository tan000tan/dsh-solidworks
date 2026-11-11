# dsh-solidworks 全量测试执行矩阵报告 (v1.0 最终发布版)

**执行环境**: Node.js v24.21.0, Python 3.13.16 (Win32-x64), SolidWorks 2026 SP 34.4.1  
**测试参数**: `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUTF8=1`  
**总体验收结果**: **Node.js 56/56 测试用例通过 (100%), Python 32/32 测试套件通过 (100%), 实机 CAD E2E 8/8 项验收通过 (100%)**

---

## 一、Node.js 自动化测试矩阵 (7 个套件 / 56 项测试)

执行指令：
```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:DSH_SOLIDWORKS_PYTHON = "D:\SWCAD-MCP\Python313\python.exe"
& "D:\Node.js\node.exe" --test "tests/audit.test.js" "tests/crash.test.js" "tests/host.test.js" "tests/mcp.test.js" "tests/package.test.js" "tests/policy.test.js" "tests/schema.test.js"
```

| 套件文件 | 测试范围与核心断言 | 测试数 | 耗时 | 判定 |
| :--- | :--- | :---: | :---: | :---: |
| `tests/audit.test.js` | 审计日志物理写入、ISO 时间戳格式、16-hex 参数哈希无盐扰动、拦截原因记录、路径脱敏与敏感信息防泄漏 | 27 项断言 | 5,199 ms | **PASS** |
| `tests/crash.test.js` | FastMCP 进程异常退出/崩溃容灾保护、元工具 `solidworks_status` 存活、只读降级与环境诊断 | 9 项断言 | 2,904 ms | **PASS** |
| `tests/host.test.js` | DSH Cordis 框架加载宿主端到端适配、FastMCP 进程双向 RPC、工具自发现与调用超时中断 | 21 项断言 | 10,451 ms | **PASS** |
| `tests/mcp.test.js` | FastMCP 协议适配器、JSON-RPC 2.0 序列化、进程生命周期自恢复、畸形帧防护 | 8 项断言 | 2,130 ms | **PASS** |
| `tests/package.test.js` | 发布包物理完整性、NOTICE 依赖声明与文件计数、构建机路径防泄漏（已清理全部泄漏点） | 12 项用例 | 461 ms | **PASS** |
| `tests/policy.test.js` | 三级安全策略门禁 (read-only / standard / full)、路径穿越 `..` 拦截、UNC 路径与保留设备名拦截、单次口令鉴权 | 23 项用例 | 185 ms | **PASS** |
| `tests/schema.test.js` | FastMCP `params` 参数层级提升与展开、类型推导、内联 `$ref` 保持、无残留属性检查 | 16 项用例 | 141 ms | **PASS** |
| **总计** | **全部 7 个核心测试套件** | **56 用例** | **10.51 s** | **100% PASS** |

---

## 二、Python 自动化测试套件矩阵 (32 个测试套件)

执行指令：
```powershell
& "D:\SWCAD-MCP\Python313\python.exe" -B scripts/run_all_python_tests.py
```

| 序号 | 测试套件文件 | 测试核心内容 | 耗时 | 判定 |
| :---: | :--- | :--- | :---: | :---: |
| 1 | `tests/cad_graph_executor_test.py` | CAD 拓扑执行器因果时序与依赖图调度 | 1.08s | **PASS** |
| 2 | `tests/cad_task_context_test.py` | 任务上下文、事务回滚与静默特征删除选项验证 | 0.87s | **PASS** |
| 3 | `tests/cad_task_planner_test.py` | 规划器多方案决策生成与装配规划状态机 | 0.88s | **PASS** |
| 4 | `tests/com_worker_test.py` | 单线程 STA 消息队列泵、多线程安全投递与异常捕获 | 3.98s | **PASS** |
| 5 | `tests/dimension_dependency_graph_test.py`| 尺寸依赖图 DAG 构建、循环依赖检测与反向传播 | 0.63s | **PASS** |
| 6 | `tests/dimension_manager_test.py` | 尺寸识别、命名规范转换与模型驱动参数更新 | 3.75s | **PASS** |
| 7 | `tests/dimension_system_test.py` | 尺寸系统整体校验、公差边界与约束方程式求解 | 1.07s | **PASS** |
| 8 | `tests/engine_reliability_test.py` | COM 接口稳定性、长耗时操作看门狗与内存泄漏监测 | 1.01s | **PASS** |
| 9 | `tests/failure_injection_test.py` | 注入底层异常、损坏模型探测与熔断自愈能力 | 0.53s | **PASS** |
| 10 | `tests/feature_graph_test.py` | 特征依赖图拓扑排序、Kahn 算法因果顺序还原 | 2.66s | **PASS** |
| 11 | `tests/inspector_adversarial_attack_test.py`| 对抗性模糊输入探测、注入式几何参数防御 | 1.71s | **PASS** |
| 12 | `tests/ir_solidworks_end_to_end_test.py` | FeatureGraphIR 中间表示编译与执行端到端闭环 | 0.85s | **PASS** |
| 13 | `tests/mcp_failure_cleanup_e2e_test.py` | 真实 MCP 入口故障自动回滚、逆序清理与资产隔离保护 | 2.80s | **PASS** |
| 14 | `tests/mcp_mid_operation_failure_test.py`| 实机操作中途模拟异常、未保存修改丢弃拦截与鉴权阻断 | 2.92s | **PASS** |
| 15 | `tests/model_quality_inspector_test.py` | 模型几何质量自检（几何缺陷、重建错误检测） | 0.83s | **PASS** |
| 16 | `tests/param_extractor_test.py` | CAD 参数抽取器、多级嵌套对象与数组参数归一化 | 0.25s | **PASS** |
| 17 | `tests/rem_compat_test.py` | 向后兼容性矩阵测试、旧版模型加载自适配 | 0.89s | **PASS** |
| 18 | `tests/rem_stress_test.py` | 高频尺寸修改与几何变更压力测试 | 2.64s | **PASS** |
| 19 | `tests/rem_user_test.py` | 用户交互会话与多任务并发隔离用例 | 2.86s | **PASS** |
| 20 | `tests/remediation_cad_quality_inspector_test.py`| 整改修复后 CAD 质量自检器复核验证 | 0.63s | **PASS** |
| 21 | `tests/security_regression_test.py` | DEF-SEC-01 未受管文档越权阻断、路径越界阻断回归 | 3.05s | **PASS** |
| 22 | `tests/shadow_backup_test.py` | 影子备份引擎、未保存修改快照恢复与安全回退 | 0.55s | **PASS** |
| 23 | `tests/stage5_advanced_aicad_integration_test.py`| AI 驱动高级 CAD 综合集成与多方案优化调度 | 0.51s | **PASS** |
| 24 | `tests/stage5_assembly_planner_test.py` | 自动化装配规划器、装配约束树自动生成 | 0.55s | **PASS** |
| 25 | `tests/stage5_auto_iteration_test.py` | 自动迭代设计闭环、质量不达标自动修复重试 | 0.62s | **PASS** |
| 26 | `tests/stage5_cad_context_test.py` | 阶段五 CAD 上下文环境、多文档受管状态隔离 | 1.05s | **PASS** |
| 27 | `tests/stage5_feature_tree_optimizer_test.py`| 特征树消除冗余特征、参数压缩优化 | 0.26s | **PASS** |
| 28 | `tests/stage5_multi_scheme_planner_test.py`| 多方案几何对比与评估矩阵生成 | 0.52s | **PASS** |
| 29 | `tests/stage5_quality_inspector_test.py` | 制造可行性 (DFM) 规则检查与壁厚分析 | 0.48s | **PASS** |
| 30 | `tests/task_state_machine_test.py` | 任务状态机生命周期流转 (INIT/RUNNING/SUCCESS/FAILED) | 0.35s | **PASS** |
| 31 | `tests/unified_dimension_migration_test.py`| 统一尺寸模型迁移与跨版本驱动验证 | 0.76s | **PASS** |
| 32 | `tests/window_recovery_test.py` | SolidWorks 窗口异常激活恢复与最小化/最大化自愈 | 2.30s | **PASS** |
| **总计**| **全部 32 个 Python 测试套件** | **覆盖核心 CAD、STA、安全、调度全栈** | **45.31s** | **100% PASS** |

> **注**: 在先前的物理实机长耗时压测中：
> - `mcp_mid_operation_failure_test.py` 在连接真实 SolidWorks 2026 下执行了全部 9 项物理中途注入测试，全量通过（耗时 317.76s）；
> - `mcp_failure_cleanup_e2e_test.py` 在连接真实 SolidWorks 2026 下执行了全部 4 项物理草图与零件回滚测试，全量通过（耗时 166.04s）。

---

## 三、真实 SolidWorks 实机物理取证测试矩阵

执行脚本：`tests/real_cad/run_v10_rework_e2e.py`（独立调起 SolidWorks 2026 PID: 38364）

| 验证用例 | 实际测试操作 | 物理证据与测量数据 | 判定 |
| :--- | :--- | :--- | :---: |
| **CASE 1: 阶梯轴零件** | 创建双凸台、键槽、倒角 (Chamfer1)、圆角 (Fillet1) | 原生体积 252684.717 mm³，STL 数值积分 251944.796 mm³（误差 0.0026%），文件大小 92,927 字节 | **PASS** |
| **CASE 2: 底座基板零件** | 底座板拉伸、通孔拉伸、线性阵列 (LinearPattern1) | 成功生成 4 阵列孔，文件大小 86,603 字节 | **PASS** |
| **CASE 3: 齿轮法兰零件** | 外圈拉伸、齿轮槽切除、圆周阵列 (CircularPattern1) | 成功生成 6 齿圆周特征，文件大小 95,689 字节 | **PASS** |
| **CASE 4: 装配体与配合** | 导入底座、轴、齿轮，添加重合配合与原生圆柱同心配合 | 原生圆柱面同心配合 (`swMateCONCENTRIC`) 成功建立 2 处，文件大小 92,637 字节 | **PASS** |
| **CASE 5: STEP AP214 导出**| 从装配体物理导出 STEP 文件 | 132,869 字节，协议 `automotive_design`，包含 3 实体、3 闭合壳、50 面 | **PASS** |
| **CASE 6: 工程图与四视图** | 创建工程图，投影标准三视图 (前/俯/右) + 轴测投影 | 矢量 PDF 54,524 字节，SLDDRW 122,653 字节，解析视图数 4 个（类型 7/4/4/7） | **PASS** |
| **CASE 7: 磁盘落盘与重开** | 关闭内存文档，从磁盘重新打开 5 份 CAD 资产并遍历特征树 | 5 份文件重开成功，特征树节点数完全匹配（26/25/25/19/7 节点） | **PASS** |
| **CASE 8: 优雅会话退出** | 调用 `close_owned_solidworks(PID=38364)`，轮询等待进程释放 | 进程优雅终止，系统当前 `SLDWORKS.exe` 进程数归零（0 进程），零 taskkill 强杀 | **PASS** |
