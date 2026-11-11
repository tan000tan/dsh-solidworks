# 第二阶段独立追溯审计报告：AI 自主建模基础

> **报告编号：** `AUDIT-R2-03-STAGE2-INDEPENDENT-AUDIT`  
> **审计对象：** dsh-solidworks 第二阶段（AI 自主建模基础、FeatureGraph IR、参数管理与依赖分析）  
> **归档目录：** `audit/full_project_round2/`  
> **审计性质：** 独立第三方追溯复核  

---

## 一、第二阶段原始目标与需求范围回顾

第二阶段（Phase 2）的核心目标是解决 AI Agent 从非结构化设计意图向确定性 CAD 建模指令转化的结构化表达问题。其原始需求范围包括：

1. **用户设计意图解析与参数提取：** 结构化提取自然语言中的几何特征、核心尺寸、对称性要求与基准面引用。
2. **FeatureGraph IR（特征图中间表示）：** 采用 DAG（有向无环图）对零件建模的特征时序、依赖关系与父子引用进行形式化建模。
3. **确定性拓扑排序与环路检测：** 采用 Kahn 算法进行建模时序确定性计算，并在编译期检测依赖死锁与悬挂依赖。
4. **逆向依赖分析与回滚子图推导：** 当下游某一特征构建失败时，能够自动逆向推导出必须物理撤销的受影响特征子树。
5. **安全尺寸与参数化管理系统：** 实现参数名称解析、尺寸依赖关系图（Dependency Graph）与尺寸修改影响域预测。

---

## 二、FeatureGraph IR 与拓扑调度引擎审计

审计团队对 `vendor/solidworks-automation-skill/scripts/feature_graph_ir.py` 实施了源码级穿透与静态分析：

### 2.1 数据模型设计 (Pydantic DAG)
- **节点规范 (`FeatureNode`)：** 包含 `feature_id`, `feature_type`, `params`, `depends_on`, `selector`, `parent_feature_id` 等核心元数据，具备完整的 Pydantic 字段类型约束与默认值安全初始化。
- **图容器 (`FeatureGraphIR`)：** 封装完整建模拓扑，支持 JSON 序列化/反序列化（`model_dump_json`, `model_validate_json`），保证 DSH 宿主与 Agent 间通信的高保真传递。

### 2.2 Kahn 拓扑排序与循环依赖检测
- **确定性时序排序：** `FeatureGraphIR.topological_sort()` 实现了标准 Kahn 算法。对多节点依赖关系能够给出严格确定、可重现的时序执行队列。
- **循环依赖检测 (Deadlock Detection)：** 当输入存在 A -> B -> C -> A 的循环闭环时，能够准确抛出 `CyclicDependencyError` 并明确定位闭环节点路径（见 `tests/feature_graph_ir_test.py`）。
- **悬挂依赖拦截 (Dangling References)：** 若特征节点依赖未在图中定义的特征 ID，编译期抛出 `UndefinedDependencyError` 阻断执行。

### 2.3 故障逆向依赖回滚子图推导
- **逆向影响域查找：** `get_reverse_rollback_subgraph(failed_feature_id)` 实现了沿 DAG 边的逆向拓扑遍历（BFS/DFS），能够精确计算出因 `failed_feature_id` 失败而必须级联撤销的所有直接和间接下游特征集合。
- **理论完整度：** 算法在内存数据结构层面达到严密性，能够输出包含回滚时序（逆拓扑序）的节点列表。

---

## 三、参数化与安全尺寸管理体系审计

审计团队核查了 `dimension_manager.py`、`dimension_ir.py`、`dimension_modifier.py` 等模块：

### 3.1 尺寸定义与提取能力
- **参数模型规范 (`DimensionSpec`)：** 支持定义尺寸名称、标称值、公差带与所属特征/草图。
- **尺寸依赖追踪 (`DimensionDependencyGraph`)：** 构建方程式驱动尺寸（Equation-driven）与几何驱动尺寸的关系网，支持正向传播计算。
- **影响域分析 (`InspectDimensionImpact`)：** 修改某一关键尺寸（如孔径或拉伸深度）前，能够静态枚举受其驱动的关联尺寸与下游特征。

### 3.2 安全尺寸修改策略
- **修改前校验：** 拦截超出几何合法范围（如负值尺寸、过大圆角值）的越界输入。
- **修改后强制重建：** 通过 COM 接口触发 `EditDimension4` 与 `ForceRebuild3`，检验几何是否存在拓扑畸变。

---

## 四、第二阶段真实边界与关键局限性（严峻真相）

历史第二阶段结项报告对自主建模能力表达较为乐观，本次审计揭示其存在以下真实边界：

1. **缺失端到端物理调度器（假象澄清）：**
   - 第二阶段向 MCP 暴露的 `solidworks_compile_feature_graph` 仅执行了**内存拓扑排序并返回排序后的 JSON 列表**，**完全没有调用 SolidWorks COM 执行任何真实物理建模**；
   - 历史测试脚本 `ir_solidworks_end_to_end_test.py` 虽然跑通了实机测试，但其执行代码 `execute_ir_plan_on_live_solidworks` **完全硬编码在测试脚本中，未集成至生产代码库**。普通 DSH 用户无法直接通过 MCP 指令完成图建模。
2. **拓扑选择器 (Selector DSL) 未完全成熟：**
   - 第二阶段 IR 虽然设计了 `selector` 字段，但在物理层无法自动解析“圆柱上顶面”、“孔内壁”等抽象语义选择器，依然高度依赖草图基准面的固定名称。
3. **意图提取依赖模板匹配：**
   - `cad_task_planner.py` 的意图解析主要依赖预设的特征模板与关键词正则表达式匹配，面对开放域模糊设计需求时自适应泛化能力有限。

---

## 五、证据分级与量化验证矩阵

| 需求项 | 核心代码实现文件 | 自动化测试脚本 | 证据等级 | 审计判定 |
|:---|:---|:---|:---:|:---:|
| **FeatureGraph IR 数据结构** | `feature_graph_ir.py:20-180` | `tests/feature_graph_ir_test.py` | **E2** | **PASS** |
| **Kahn 拓扑排序与循环死锁检测** | `feature_graph_ir.py:182-260` | `tests/feature_graph_ir_test.py` | **E2** | **PASS** |
| **逆向回滚子图推导** | `feature_graph_ir.py:262-340` | `tests/feature_graph_ir_test.py` | **E2** | **PASS** |
| **尺寸依赖关系图** | `dimension_dependency_graph.py` | `tests/dimension_dependency_graph_test.py` | **E2** | **PASS** |
| **安全尺寸修改与影响分析** | `dimension_modifier.py`, `dimension_manager.py` | `tests/dimension_system_test.py` | **E3** | **PASS** |
| **MCP 端到端实机特征图物理执行** | 第二阶段生产代码**未实现**（仅编译工具暴露） | 历史仅测试文件内部私有函数 | **E1/E2** | **PARTIAL（物理执行顺延第四阶段）** |

---

## 六、第二阶段独立审计最终裁决

### 裁决结论：
**ACCEPTED WITH CONDITIONS（有条件合格验收）**

### 条件说明与准入限制：
1. **核准资产：** 第二阶段建立的 `FeatureGraphIR` 数据规范、拓扑排序算法、逆向依赖分析和安全尺寸系统是扎实可靠的软件资产，具有充分的离线与模拟测试覆盖，可被后续阶段安全继承使用；
2. **能力边界锁定：** 第二阶段**不具备**端到端自主物理建模交付能力。所有上层应用必须明确第二阶段提供的只是“编译与分析能力”，真正的物理调度与执行必须依赖第四阶段开发的 `CADGraphExecutor`。
