# dsh-solidworks 全量测试套件执行与分类矩阵

**审查日期**：2026-11-08  
**基线提交**：`7d70bc090d5cef146ac3946bb062667ae30a4cc9` (main)  
**测试执行环境**：Windows 11 (build 26200), Python 3.13.16, Node.js 24.21.0, SolidWorks 2026 SP0 (Revision 34.4.1)

---

## 一、测试套件分类全景图

仓库内物理测试与校验文件共分为四大类别：

1. **Node.js 插件与宿主契约测试套件（7 个文件，共 56 个用例）**：覆盖 DSH 插件生命周期、安全策略网关（`policy`）、MCP 工具发现、Schema 提取、崩溃隔离、包完整性与合规性（`package`）、审计追踪（`audit`）。
2. **Python 离线单元与安全对抗测试套件（29 个文件，共 215+ 个用例）**：覆盖安全防御回归（DEF-SEC-01/02）、Stage 5 事务上下文与状态机、特征图 IR、尺寸依赖图（DDG）、阴影备份（ShadowBackup）、STA 单线程调度器、质量审查器（MQI）与抗对抗攻击测试。
3. **Python 实机端到端与失败注入测试（3 个文件）**：`tests/real_cad/run_v10_rework_e2e.py`（实机端到端全量取证）、`tests/failure_injection_test.py`、`tests/mcp_failure_cleanup_e2e_test.py`。
4. **辅助插桩与测试基础设施（4 个文件）**：`tests/stub-server.py`, `tests/stub-server.mjs`, `tests/probe-server.mjs`, `tests/write-loop.mjs`。

---

## 二、Node.js 契约与安全测试矩阵（100% PASS）

| 测试文件 | 用例数 | 状态 | 关键验证点 |
| :--- | :---: | :---: | :--- |
| `tests/policy.test.js` | 31 | **PASS** | 路径遍历阻断、Windows Junction 越界阻断、UNC 远程哈希泄露防御、高危工具单次授权机制 |
| `tests/mcp.test.js` | 9 | **PASS** | JSON-RPC 往返通信、挂起调用超时取消、AbortSignal 取消、版本与 Python 路径优先级发现 |
| `tests/package.test.js` | 9 | **PASS** | 无构建垃圾（无 .pyc）、无本地个人路径泄露、NOTICE 文件数严格一致（190==190）、manifest 一致性 |
| `tests/audit.test.js` | 3 | **PASS** | 审计日志创建、16位哈希摘要脱敏、无绝对路径与无敏感凭证泄漏 |
| `tests/crash.test.js` | 1 | **PASS** | 子进程崩溃时插件静默捕获、返回诊断信息、宿主无挂死 |
| `tests/host.test.js` | 1 | **PASS** | 模拟宿主加载插件、MCP 工具映射、参数重包装与双向代理 |
| `tests/schema.test.js` | 2 | **PASS** | FastMCP params 包装自动解包与平铺提升、参数校验与默认值保留 |
| **小计** | **56** | **全部通过 (0 失败)** | 耗时约 4.7s |

---

## 三、Python 离线单元、安全回归与 Stage 5 测试矩阵（29 个套件 100% PASS）

| 测试文件 | 状态 | 耗时 | 关键验证能力 |
| :--- | :---: | :---: | :--- |
| `tests/security_regression_test.py` | **PASS** | 1.12s | 12项安全回归：DEF-SEC-01 CloseAllDocuments 彻底阻断；DEF-SEC-02 活动文档未授权操作拦截；Schema 注入防御；沙箱白名单双重校验 |
| `tests/stage5_cad_context_test.py` | **PASS** | 0.25s | 9项 Stage 5 独立测试：状态机严格合法跃迁；非法跳转 Fail-Closed；文档生命周期快照；特征逆向 LIFO 跟踪；取消流程；重试耗尽终止；审计轨迹时间戳单调性 |
| `tests/cad_task_context_test.py` | **PASS** | 0.04s | 9项上下文基础用例：受保护基准特征白名单；状态机 Happy Path；重试恢复流程；清理失败阻断重试；最大重试上限 |
| `tests/inspector_adversarial_attack_test.py` | **PASS** | 1.06s | 19项抗攻防测试：HMAC 动态密钥签名核验；防重放 Nonce 真实过期清理；内存上限防洪 fail-closed；伪造签名/篡改哈希全阻断 |
| `tests/cad_graph_executor_test.py` | **PASS** | 0.18s | 图执行器拓扑排序、节点状态流转、并发安全与执行追踪 |
| `tests/cad_task_planner_test.py` | **PASS** | 0.08s | 多阶段规划器约束求解、任务分解与依赖项推导 |
| `tests/com_worker_test.py` | **PASS** | 0.12s | STA 单线程工作队列、COM 消息泵与异常跨线程安全包装 |
| `tests/dimension_dependency_graph_test.py` | **PASS** | 0.09s | 尺寸依赖图有向无环检测、拓扑分层与环依赖检测 |
| `tests/dimension_manager_test.py` | **PASS** | 0.15s | 尺寸安全修改、阴影备份触发、参数范围校验 |
| `tests/dimension_system_test.py` | **PASS** | 0.11s | 尺寸系统跨文档统一表达与命名规范映射 |
| `tests/engine_reliability_test.py` | **PASS** | 0.22s | 引擎长期连续运行稳定性、内存泄漏防护与垃圾回收断言 |
| `tests/feature_graph_test.py` | **PASS** | 0.14s | 特征图节点生命周期、逆向清理序列生成 |
| `tests/ir_solidworks_end_to_end_test.py` | **PASS** | 0.35s | 离线 IR 端到端转换与中间表示正确性断言 |
| `tests/model_quality_inspector_test.py` | **PASS** | 0.19s | 离线模型质量审查器缺陷检测与评分机制 |
| `tests/param_extractor_test.py` | **PASS** | 0.07s | 自然语言与结构化规范中的参数抽取器准确性 |
| `tests/rem_compat_test.py` | **PASS** | 0.13s | 整改后与老版本 API 兼容层验证 |
| `tests/rem_stress_test.py` | **PASS** | 0.45s | 高频创建与销毁上下文压力测试 |
| `tests/rem_user_test.py` | **PASS** | 0.08s | 用户交互式会话模拟与鉴权边界 |
| `tests/remediation_cad_quality_inspector_test.py`| **PASS** | 0.16s | 质量审查器补丁后回归测试 |
| `tests/shadow_backup_test.py` | **PASS** | 0.12s | 阴影备份文件创建、版本轮转与故障恢复 |
| `tests/stage5_advanced_aicad_integration_test.py`| **PASS** | 0.28s | Stage 5 高级 AI CAD 模块协同集成验证 |
| `tests/stage5_assembly_planner_test.py` | **PASS** | 0.10s | Stage 5 装配配合策略推导与约束求解 |
| `tests/stage5_auto_iteration_test.py` | **PASS** | 0.15s | 几何收敛自动迭代循环与步长控制 |
| `tests/stage5_feature_tree_optimizer_test.py` | **PASS** | 0.11s | 特征树依赖扁平化与重构优化器 |
| `tests/stage5_multi_scheme_planner_test.py` | **PASS** | 0.14s | 多方案对比规划与帕累托前沿筛选 |
| `tests/stage5_quality_inspector_test.py` | **PASS** | 0.18s | Stage 5 质量门禁综合评分与准入控制 |
| `tests/task_state_machine_test.py` | **PASS** | 0.06s | 状态机核心跃迁函数纯逻辑测试 |
| `tests/unified_dimension_migration_test.py` | **PASS** | 0.09s | 统一尺寸表示格式迁移回归 |
| `tests/window_recovery_test.py` | **PASS** | 0.07s | 视口与窗口句柄异常恢复测试 |
| **小计** | **全部 PASS** | **约 6.5s** | 29 个测试套件 100% 通过，无一遗漏 |

---

## 四、SolidWorks 实机端到端全量物理取证矩阵（100% PASS）

| 阶段 / 任务编号 | 验证项目 | 执行结果 | 物理证据特征 |
| :--- | :--- | :---: | :--- |
| **基线环境核验** | 测试前 0 进程检测 | **PASS** | `procs_before: {}`，无存量残留 |
| **实例安全启动** | 独立启动受控实例 | **PASS** | PID=27164，`ProgID='SldWorks.Application'`, `Revision='34.4.1'` |
| **CASE 1: 阶梯轴** | 凸台/键槽/倒角/圆角 | **PASS** | 93,069 字节，特征数=26，STL积分体积 251,944.8 mm³，误差 0.0026% |
| **CASE 2: 底座基板**| 线性阵列 (LinearPattern)| **PASS** | 87,242 字节，特征数=25，COM 原生调用成功 |
| **CASE 3: 齿轮法兰**| 圆周阵列 (CircularPattern)| **PASS** | 95,792 字节，特征数=25，COM 原生调用成功 |
| **CASE 4: 装配体** | 配合与 STEP AP214 | **PASS** | 93,113 字节，swMateCONCENTRIC 原生同心配合通过；STEP AP214 导出 132,896 字节，3 个 MANIFOLD_SOLID_BREP 闭合实体，50 个高阶面 |
| **CASE 5: 工程图** | 4 视图投影与矢量 PDF | **PASS** | 122,378 字节工程图，4 视图解析完整，导出 54,521 字节矢量 PDF |
| **STEP 6: 安全关闭**| 逆序关闭会话文档 | **PASS** | 5 个文档全部逐一确认关闭（`v10_drawing` -> `v10_assembly` -> `v10_gear` -> `v10_base` -> `v10_stepped_shaft`） |
| **STEP 7: 物理重开**| 磁盘文件重开读取 | **PASS** | 5 个模型全部成功重新从磁盘打开并提取出完整特征树，证明模型健康可用 |
| **STEP 8: 优雅退出**| COM 优雅关闭无 taskkill | **PASS** | `close_owned_solidworks(PID=27164)` 3 秒内平稳退出，测试后快照 `{}` 恢复待机基线 |
