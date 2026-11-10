# STAGE 04 FeatureGraph、事务管理与故障恢复审计报告
# AUDIT_FEATUREGRAPH_TRANSACTION_RECOVERY.md

**审计项目：** `dsh-solidworks` DSH 插件  
**审计阶段：** STAGE 04 — CAD 核心建模能力 (图编排与事务恢复审计)  
**审计团队：** 第三方独立技术审计组  
**审计重点：** FeatureGraph 有向无环图 (DAG) 拓扑排序、环检测、中途失败阻断、Level 3 真实特征树逆序物理回滚  
**状态：** **AUDITED & PASS (物理回滚真实卸载特征树，模型干净复原，DAG 状态机运转正确)**

---

## 一、审计原则与真伪回滚鉴别

在 CAD 自动化系统中，必须坚决区分两种“假回滚”：
1. **纯内存伪回滚**：仅在 Python 内存字典中将 TaskStatus 置为 `FAILED`，而 SolidWorks 特征树中仍残留半拉子损坏特征；
2. **文档重载式偷换**：不执行特征级物理删除，而是靠“不保存直接关闭文档重新打开”来规避回滚。

本次审计要求：**必须验证在当前处于打开状态的活动模型中，特征树中已物理生成的特征被真实逐一卸载删除，且实体几何被物理擦除或复原**。

---

## 二、FeatureGraph IR 与图执行引擎审计

审查代码：`feature_graph_ir.py` 与 `cad_graph_executor.py`。

### 2.1 DAG 结构与拓扑排序核验
- **数据结构**：`FeatureGraphIR` 将建模任务抽象为包含 Node（特征节点）与 Edge（父子依赖边）的有向无环图；
- **算法审计**：
  - `cad_graph_executor.py` 使用基于入度统计的 Kahn 算法实现拓扑排序；
  - 环检测（Cycle Detection）：当图中存在相互循环依赖时（如草图 A 依赖特征 B，特征 B 依赖草图 A），能够主动抛出 `CyclicDependencyError`，避免递归死循环；
  - 阻断执行（Failure Blockade）：当上游某一节点执行失败时，下游所有直接或间接依赖该节点的子节点均被标记为 `BLOCKED`，未被盲目调度。

---

## 三、Level 3 真实特征树逆序物理回滚实测物证

审查 `phase4_cad_core_suite.py` 实验 3 与物理物证 `phase4_modeling_evidence.json`。

### 3.1 中途故障注入与物理回滚过程复核
- **前置特征序列（4 级链路）**：
  1. `Sketch1` (底座草图) $\to$ 2. `Boss-Extrude1` (底座实体拉伸，高 18mm) $\to$ 3. `Sketch2` (立柱草图，$\Phi 40\text{ mm}$) $\to$ 4. `Boss-Extrude2` (立柱实体拉伸，高 40mm)；
- **故障注入触发**：
  - 在第 5 步模拟端面特征切除产生严重相交失败，引发异常抛出；
- **事务引擎动作**：
  - 任务状态机：`RUNNING -> FAILED -> ROLLING_BACK`；
  - 调用 `CADTaskRollbackManager.rollback_task(task, part)`；
  - 逆序栈依次执行：
    ```
    Step 1: 删除特征 [Boss-Extrude2] -> ext.SelectByID2 + EditDelete 物理删除成功
    Step 2: 删除特征 [Sketch2]       -> ext.SelectByID2 + EditDelete 物理删除成功
    Step 3: 删除特征 [Boss-Extrude1] -> ext.SelectByID2 + EditDelete 物理删除成功
    Step 4: 删除特征 [Sketch1]       -> ext.SelectByID2 + EditDelete 物理删除成功
    ```
  - 状态机最终收敛：`ROLLING_BACK -> SUCCESS`。

### 3.2 真实几何物理清零核验
- **回滚前模型**：实体数 `1`，实测体积 `158,137.17 mm³`；
- **物理回滚后**：
  - 实体数：严格归零（`body_count == 0`）；
  - 实测体积：严格归零（`volume_mm3 == 0.00`）；
  - 特征树：无未删除孤立草图或悬空碎片；
  - 文档完整性：文档依然处于活动打开状态，未发生崩溃或句柄锁死。

---

## 四、事务与回滚审计发现与缺陷记录

1. **[DEFECT-TRANS-01 | MEDIUM] 混合手动特征的非受控回滚风险**：
   - 当前回滚机制依赖于 `task.register_feature()` 在内存中记录的操作流水。如果用户在 SolidWorks 界面上手动插入了非托管特征，回滚管理器由于未追踪该特征名称，可能无法将其纳入逆序卸载栈。
   - *建议*：在后续阶段引入“操作前特征树快照差异比较（Diff-based Rollback）”，以特征树绝对变化量作为回滚卸载基准。

---

## 五、FeatureGraph 与事务恢复审计裁定

审计核验表明：系统具备完备的 DAG 拓扑排序与依赖阻断逻辑，Level 3 特征树逆序物理回滚机制真实有效，彻底拒绝了内存假回滚，实测实体几何物理清零，模型状态干净复原，**FeatureGraph、事务和恢复审计判定：PASS**。
