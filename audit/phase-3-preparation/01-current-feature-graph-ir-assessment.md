# Feature Graph IR 现状评估报告

## 一、现有 Feature Graph IR 架构深度审查

在 `dsh-solidworks-plugin` 仓库中，特征拓扑依赖图中间表示（Feature Graph Intermediate Representation, 下称 Feature Graph IR）的核心实现文件位于：
[vendor/solidworks-automation-skill/scripts/feature_graph_ir.py](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/vendor/solidworks-automation-skill/scripts/feature_graph_ir.py)。

该模块设计定位为“自然语言意图规划与底层 CAD API 执行之间的结构化 DAG 编译器”，其核心代码架构如下：

### 1. 核心数据结构与抽象
- **`FeatureType` (枚举)**：定义了 9 种特征节点类型：
  - `REFERENCE_PLANE`（参考基准面）
  - `SKETCH_2D`（2D 草图）
  - `EXTRUDE_BOSS`（拉伸凸台）
  - `EXTRUDE_CUT`（拉伸切除）
  - `REVOLVE_BOSS`（旋转凸台）
  - `REVOLVE_CUT`（旋转切除）
  - `FILLET`（圆角）
  - `CHAMFER`（倒角）
  - `HOLE_WIZARD`（异型孔向导）
- **`NodeStatus` (枚举)**：
  - `PENDING`、`RUNNING`、`SUCCEEDED`、`FAILED`、`ROLLED_BACK`、`SKIPPED`
- **`FeatureNode` (Pydantic 模型)**：
  - `id: str`：节点唯一标识符（例如 `node_sketch_base`）
  - `type: FeatureType`：特征类型
  - `name: str`：SolidWorks 对应特征名称（例如 `Sketch1`, `Boss-Extrude1`）
  - `parameters: Dict[str, Any]`：松散字典，存储几何与尺寸参数
  - `depends_on: List[str]`：前置依赖节点 ID 列表
  - `status: NodeStatus`：执行状态
  - `created_cad_entity: Optional[str]`：底层创建的实际 CAD 特征名称
- **`FeatureGraphIR` (Pydantic 模型)**：
  - `graph_id: str`：图唯一标识
  - `target_part_name: str`：目标零件名称
  - `nodes: Dict[str, FeatureNode]`：节点字典表
  - `metadata: Dict[str, Any]`：图级元数据

### 2. 拓扑与容错算法
- **Kahn 算法拓扑排序 (`topological_sort`)**：
  构建邻接表与入度表，通过 FIFO 队列（结合节点 ID 稳定排序）计算全局时序。
  当排序后节点数小于总节点数时，精准抛出 `CyclicDependencyError` 阻止执行。
- **悬挂依赖静态检测 (`validate_dag`)**：
  遍历所有节点及其 `depends_on` 列表，若存在未注册的前置 ID，抛出 `UndefinedDependencyError`。
- **局域回滚与故障波及子树计算 (`get_reverse_rollback_subgraph`, `evaluate_failure_and_rollback`)**：
  构建反向依赖图（`u -> v` 表示 `v` 依赖 `u`），当节点 `N` 故障时，利用 BFS 算法求得所有下游受波及节点集合，区分出：
  - 需逆序物理删除的已创建实体（`entities_to_delete_reversed`）；
  - 直接跳过的未执行下游节点（`nodes_skipped`）；
  - 完全独立且执行成功的无依赖节点（`nodes_retained`）。

---

## 二、真实调用链穿透审计：代码存在 vs 真实闭环

经全工程源码深度检索（`server.py`、`cad_task_context.py`、`tests/`、`dimension_manager.py`），本评估发现了**系统设计中最为关键的一个技术断层**：

### 1. 生产环境的“伪接入”状态
在 MCP 服务入口 [vendor/solidworks-automation-skill/mcp-server/server.py](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/vendor/solidworks-automation-skill/mcp-server/server.py#L2045-L2080)，注册了先锋工具 `solidworks_compile_feature_graph`：
```python
@mcp.tool(name="solidworks_compile_feature_graph")
def solidworks_compile_feature_graph(params: FeatureGraphCompileInput) -> str:
    graph = compile_feature_graph_from_dict(params.graph)
    plan = graph.compile_execution_plan()
    return _result({"status": "success", "execution_plan": plan})
```
**严重断层事实**：
1. `solidworks_compile_feature_graph` 被标记为 `readOnlyHint: True`，它**仅在内存中完成了 JSON 校验与拓扑排序**，将有向图转换为扁平的 `execution_plan` 列表。
2. 整个 MCP Server 中**不存在任何生产级工具调用 CAD 执行器去消费这个 `execution_plan`**！
3. `cad_task_context.py` 中的 `CADTaskRollbackManager` 拥有成熟的物理清理能力，但与 `feature_graph_ir.py` 的 `evaluate_failure_and_rollback` 完全处于孤岛状态，二者从未发生运行时数据交换。

### 2. 真实的端到端执行被“锁在测试用例中”
真正的执行逻辑仅存在于 [tests/ir_solidworks_end_to_end_test.py](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/tests/ir_solidworks_end_to_end_test.py#L51-L123) 中的私有辅助函数 `execute_ir_plan_on_live_solidworks`：
- 该函数遍历 `execution_plan`，根据 `feature_type` 硬编码分支（仅支持草图矩形/圆、拉伸凸台、拉伸切除）；
- 驱动 STA Worker 调用 `sw_part.py` 的物理 API 完成建模；
- **该模块未被打包到 `scripts/` 作为公共执行引擎，外部 AI 和 MCP 协议完全无法触达此能力！**

---

## 三、Feature Graph IR 12 维能力全景盘点

| 序号 | 建模/系统能力 | 现状判定 | 详细技术现状分析 | 阶段三改进建议 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | **DAG 拓扑数据结构** | **已实现 (完整)** | 基于 Pydantic，支持节点属性、前置依赖、JSON 序列化与反序列化。 | 补充强类型 Schema，细化每类特征专属参数。 |
| 2 | **时序依赖排序与死锁检测** | **已实现 (完整)** | Kahn 算法经过单元测试，支持环路死锁排查与稳定排序。 | 保持现有算法，增加复杂多父多子分支测试。 |
| 3 | **局域回滚与故障波及子树** | **已实现 (算法层)** | `evaluate_failure_and_rollback` 算法逻辑正确，能区分回滚/跳过/保留。 | 接入 `CADTaskContext` 与 `FeatureCleanupManager`。 |
| 4 | **执行计划编译 (Execution Plan)** | **已实现 (静态)** | 能将 DAG 节点映射为 MCP 工具名与调用参数字典。 | 增强对中间状态传递（如引用的实体句柄）的支持。 |
| 5 | **CAD 物理执行器 (CAD Executor)** | **未接入 (仅测试存在)** | 仅在 `tests/ir_solidworks_end_to_end_test.py` 内部有专用解释器，生产环境缺失。 | **阶段三 P0 阻断项**：抽象出独立的 `CADGraphExecutor` 核心模块并暴露 MCP 工具。 |
| 6 | **草图几何与基准面支持** | **仅部分实现** | 仅支持绝对坐标下的矩形与圆，仅支持原生 Front/Top/Right 等命名基准面。 | 扩充多边形、槽口、样条曲线，支持基于实体表面（Face）建立草图。 |
| 7 | **草图几何约束 (Relations)** | **未接入 IR** | `sw_part.py` 中有 `add_sketch_relation`，但 IR 未建模约束节点，无法表达共线、同心、相切。 | 在 IR 增加 Sketch Constraint 抽象，支持意图级参数约束。 |
| 8 | **尺寸参数与表达式管理** | **未联动 (技术孤岛)** | `dimension_manager.py` 可安全修改尺寸，但未与 IR 节点的 `parameters` 打通，无法自动更新下游。 | 将 `dimension_manager` 与 IR 节点双向绑定，引入方程驱动。 |
| 9 | **拓扑命名与父子几何引用** | **未实现 (硬编码名)** | 依赖字符串名称（如 `Sketch1`、`Front Plane`），无拓扑持久命名（TNP 隐患极大）。 | 引入声明式拓扑选择器（Selector DSL）与拓扑指纹。 |
| 10 | **特征生命周期与健康自愈** | **仅框架存在** | `NodeStatus` 有枚举，但执行期无动态更新回写机制，失败后无法就地重试修复。 | 建立 `Plan -> Execute -> Validate -> Repair` 运行时状态机。 |
| 11 | **复杂三维特征 (扫描/放样/阵列)** | **未接入 IR** | `sw_part.py` 虽有 `linear_pattern`、`circular_pattern`、`shell`，但 IR 未注册此类节点。 | 扩充 `FeatureType` 枚举与对应参数模型。 |
| 12 | **MCP 工具链标准化交付** | **仅单向编译** | 仅有 `solidworks_compile_feature_graph`，无 `solidworks_execute_feature_graph`，无法一键生成。 | 新增执行工具，返回完整执行追踪链路与几何体质量属性。 |

---

## 四、核心结论与评估总结

1. **理论基石扎实**：现有 `feature_graph_ir.py` 在有向无环图建模、死锁检测、拓扑时序确定性和故障逆向影响推导方面架构清晰，无代码级致命缺陷，**拓扑编译器核心算法完全可以直接复用**。
2. **生产断层明显**：现有代码只完成了“上游图表达”和“离线拓扑排序”，CAD 物理执行、动态参数同步、拓扑选择器与特征树自愈完全处于“断轨”状态。
3. **阶段三关键落地点**：必须研发通用的 `CADGraphExecutor`，将 Feature Graph IR 与 `cad_task_context`、`sw_part.py`、`dimension_manager.py` 彻底打通，形成闭环。
