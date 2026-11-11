# dsh-solidworks-plugin 阶段三技术准备与架构选型终审总报告

## 一、任务背景与执行准则

本项目 `dsh-solidworks-plugin` 在圆满完成阶段一（v0.2.0 独立验收与本地封版）和阶段二（v0.2.1 稳定性与自发现维护修复）后，正式进入：
**阶段三：AI 建模能力升级**。

按照任务书部署，本任务为阶段三的**技术准备、现状穿透评估与架构选型任务**。在执行全程中，严格遵守只读分析、不修改业务源码、不推翻既有封版、不调用或关闭 SolidWorks 物理进程的铁律。

已在目录 `audit/phase-3-preparation/` 交付全部 7 份专题支撑研究报告：
1. [01-current-feature-graph-ir-assessment.md](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/audit/phase-3-preparation/01-current-feature-graph-ir-assessment.md)
2. [02-current-ai-modeling-pipeline.md](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/audit/phase-3-preparation/02-current-ai-modeling-pipeline.md)
3. [03-open-source-technology-research.md](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/audit/phase-3-preparation/03-open-source-technology-research.md)
4. [04-solidworks-api-reuse-analysis.md](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/audit/phase-3-preparation/04-solidworks-api-reuse-analysis.md)
5. [05-phase-3-architecture-proposal.md](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/audit/phase-3-preparation/05-phase-3-architecture-proposal.md)
6. [06-phase-3-development-roadmap.md](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/audit/phase-3-preparation/06-phase-3-development-roadmap.md)
7. [07-phase-3-acceptance-tests.md](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/audit/phase-3-preparation/07-phase-3-acceptance-tests.md)

本总报告直接、全面、透彻地回答任务书第十一节提出的 10 大核心问题。

---

## 二、直面回答 10 大核心问题

### 1. 现有 Feature Graph IR 到底实现了什么，没实现什么，哪些只是假象？

- **真正实现的内容（坚实资产）**：
  - 基于 Pydantic 的 DAG 拓扑数据结构（`FeatureNode`, `FeatureGraphIR`），支持 JSON 序列化；
  - 基于 Kahn 算法的拓扑时序确定性排序与循环闭环依赖（死锁）静态检测；
  - 悬挂依赖未定义检测（`UndefinedDependencyError`）；
  - 故障逆向依赖子树推导算法（`get_reverse_rollback_subgraph`, `evaluate_failure_and_rollback`）。
- **完全没有实现的内容（能力空白）**：
  - 生产级物理执行器（`CADGraphExecutor`）：生产代码中完全没有消费图计划并驱动 SolidWorks 建模的逻辑；
  - 声明式拓扑选择器（Selector DSL）：无法在不知道面名称的前提下语义化选择实体顶面或圆弧边；
  - 草图约束语义（Coincident, Tangent 等）在 IR 中未建立模型；
  - 全局参数驱动与尺寸方程系统联动。
- **“只是假象”的部分（严峻真相）**：
  - **“MCP 工具已支持特征图编译”的假象**：`server.py` 暴露的 `solidworks_compile_feature_graph` 仅仅是将字典在内存中排了个序，并返回 JSON 列表，**它根本没有去调用 SolidWorks 执行任何建模**！
  - **“端到端驱动已打通”的假象**：测试套件中的 `ir_solidworks_end_to_end_test.py` 确实跑通了真实 SolidWorks 建模，但其核心执行代码 `execute_ir_plan_on_live_solidworks` **完全硬编码在测试脚本中，从未封装进生产库，AI 和 MCP 根本无法调用**。

---

### 2. 现有的代码能不能直接支撑自然语言到 SolidWorks 建模的完整链路？

**明确回答：绝对不能！**
目前如果让 AI 去执行“帮我建一个带中心孔的 L 型支架”，链路会在两处发生不可逾越的阻断：
1. AI 即使通过先锋工具生成了 Feature Graph 执行计划，也没有任何生产级 MCP 工具能把这个计划送进 SolidWorks 物理执行；
2. 如果 AI 退化为调用原子级工具（先画草图，再拉伸，再选面），它在第三步必须传入一个被切除面的名称；由于没有拓扑选择器，AI 根本不知道 SolidWorks 内部动态生成的面是叫 `Face1`、`Face4` 还是别的代号，必然导致参数匹配失败或特征丢失。

---

### 3. 如果不能，从自然语言到真实 SolidWorks 之间到底缺了哪几层？

从自然语言需求到 SolidWorks 真实零件，系统当前缺失了关键的 **3 大中间层**：
1. **缺失“语义拓扑选择层 (Topology Selector)”**：缺乏将 AI 的几何意图（例如“在最高的那个平面上开孔”）转换为 SolidWorks 实体句柄的拓扑解析器；
2. **缺失“图级物理执行引擎 (CADGraphExecutor)”**：缺乏在后台通过 STA Worker 一口气消费拓扑执行计划并安全事务性驱动 COM 的执行器；
3. **缺失“几何自愈与闭环诊断层 (Auto-Repair Loop)”**：当 COM 抛出几何破损或自相交异常时，缺乏结构化反思与局域自愈机制，只会整件崩溃或被动清理。

---

### 4. CadQuery、build123d、FreeCAD 等开源项目到底能不能用，怎么用，用哪些部分？

- **能不能直接用来做几何求解内核？绝对不能！**
  - CadQuery / build123d / FreeCAD 底层均使用 OpenCASCADE (OCCT) 内核，而 SolidWorks 使用专有的 Parasolid 内核；
  - 试图在 Python 中算好几何体再塞给 SolidWorks 会完全破坏 SolidWorks 的“特征树历史可编辑性”，丢失建模历史，违背工业 CAD 插件核心定位。
- **怎么用，用哪些部分？深度借鉴其优秀设计模式：**
  - **吸收 CadQuery 的 Selector DSL**：将 `>Z`（最高面）、`|Z`（竖直边）等极简选择器语法移植到本项目中，极大简化 LLM 表达几何引用的难度；
  - **吸收 build123d 的 Builder 上下文模型**：用于优化 `CADTaskContext` 的草图与特征事务封装；
  - **吸收 FreeCAD 的草图几何约束模型**：将草图表示由离散几何升级为“图元 + 关系约束”。

---

### 5. SolidWorks 官方 API 到底有哪些可以直接复用，有哪些项目里重复实现了？

- **可直接复用且必须接入的高价值官方接口**：
  - `IModelDoc2.GetEquationMgr`：官方方程管理器，直接实现全局变量与尺寸联动驱动；
  - `IFeatureManager.FeatureExtrusion3` / `FeatureCut4`：工业级拉伸与切除；
  - `IFeatureManager.FeatureFillet3` / `InsertFeatureChamfer`：原生平滑圆角倒角；
  - `IFeature.GetErrorCode2`：提取底层特征树故障码，为自愈提供依据。
- **项目里存在重复实现与冗余的部分**：
  - `sw_part.py`、`advanced_geometry.py` 与 `sw_sketch_quality.py` 各自编写了类似的草图选取与轮廓遍历代码，应在阶段三统一抽象到 `sw_topology_resolver.py`；
  - `dimension_manager.py` 与 `sw_document_data.py` 中均存在尺寸读写包装，应统一归并。

---

### 6. 阶段三应该采用什么样的总体架构？

阶段三推荐采用 **“分层解耦、图驱动执行、双重安全防护”** 的统一技术架构：
1. **意图层**：LLM 消费 Pydantic JSON Schema，生成规范的 Feature Graph IR；
2. **编译层**：`FeatureGraphCompiler` 静态校验 DAG、Kahn 拓扑排序、环路死锁排查；
3. **规划层**：`FeaturePlanner` 解析坐标系与声明式拓扑选择器（Selector DSL）；
4. **执行层**：`CADGraphExecutor` 调度 STA Worker 顺序调用 SolidWorks COM；
5. **防护层**：执行全程受 `CADTaskContext` 事务与 `ShadowBackupManager` 影子备份守护，支持局域逆向依赖子树回滚；
6. **自验与自愈层**：`GeometryValidator` 采集双精度质量属性并捕获错误码，提供结构化自愈建议。

---

### 7. 阶段三应该分几个步骤开发，每个步骤的产出和验收标准是什么？

严格划分为三个开发批次（P0 -> P1 -> P2）：
- **P0 批次：基础闭环与执行引擎（工期 2-3 天）**
  - *产出*：`cad_graph_executor.py` 生产模块、`solidworks_execute_feature_graph` MCP 工具、强类型参数 Schema；
  - *验收标准*：端到端建模通过，发生异常时 100% 自动安全清理，无未命名文档残留。
- **P1 批次：核心建模能力与工业可用性（工期 3-4 天）**
  - *产出*：`topology_selector.py`（选择器 DSL）、二维草图约束映射、圆角/倒角/阵列/异型孔向导、`IEquationMgr` 尺寸方程驱动；
  - *验收标准*：成功构建典型复杂机械零件，修改全局参数后模型无损自动重算。
- **P2 批次：自愈增强与标准件模板生态（工期 2-3 天）**
  - *产出*：报错诊断自愈闭环、局域逆向回滚引擎、8 大典型机械标准件 Prompt/IR 模板库；
  - *验收标准*：对抗性故障注入测试自愈成功率 100%，自然语言建模一次性通过率 $\ge 95\%$。

---

### 8. 阶段三需要哪些真实的 SolidWorks 验收测试用例？

设计了 **8 大典型真实 CAD 验收测试任务**，严禁 Mock，直接打在本地真实 SolidWorks 2026 上：
1. **TC-01（标准 L 型支架）**：多特征顺序构建，双精度体积误差 $\le 0.001\%$；
2. **TC-02（轴承套环）**：回转与同心切除，验证同轴度；
3. **TC-03（盲孔切除）**：声明式选择器 `>Z & #PLANE` 动态命中顶面；
4. **TC-04（尺寸方程驱动）**：修改单一变量，全树联动更新无拓扑报错；
5. **TC-05（批量圆角倒角）**：边选择器 `|Z` 批量选中竖直边光滑倒圆角；
6. **TC-06（工业法兰盘）**：异型孔向导与 $360^\circ$ 环形阵列孔系；
7. **TC-07（故障注入与自愈）**：注入过大圆角几何冲突，验证局域精准回滚与参数修正重试；
8. **TC-08（持久化与重开审计）**：保存为 `.SLDPRT`，关闭重开后特征树完好无损、无悬挂错误。

---

### 9. 阶段三有没有可能在不破坏现有架构的前提下平滑升级？

**完全可以，且必须平滑升级！**
1. **保护已有封版基线**：v0.2.0 Commit `7d70bc0` 和 Tag `v0.2.0` 保持纯洁，阶段三开发基于新分支推进；
2. **MCP 工具向前兼容**：现有 65 个原子 MCP 工具的调用契约、风险级别与实现逻辑保持 100% 不变；
3. **增量外挂模式**：阶段三的核心成果体现为新增高级工具 `solidworks_execute_feature_graph` 与底层支撑模块（`cad_graph_executor.py`, `topology_selector.py`），对原有上层系统完全属于非破坏性增强。

---

### 10. 你给出的阶段三推荐路线图是什么，预期需要多少工作量，最大风险在哪里？

- **推荐路线图**：
  采用 **“先通物理链路 (P0)，再拓几何语义 (P1)，后固自愈生态 (P2)”** 的精益节奏，整体预计分为 3 个阶段迭代推进。
- **工作量评估**：
  核心开发代码量约 1200 - 1500 行高质量 Python 源码，测试代码约 800 行，开发与真实 SolidWorks 回归调试周期预计为 **7 - 10 个工作日**。
- **最大技术风险识别与应对**：
  1. **最大风险：拓扑命名失效（TNP）导致实体表面选择错位**。
     *应对策略*：坚决实施 `topology_selector.py`，采用几何法向量与点积极值动态匹配，绝不依赖 SolidWorks 内部脆弱的默认面名称。
  2. **次大风险：复杂特征重建失败导致 COM 弹窗阻塞**。
     *应对策略*：在连接层强制注入 `AutoRebuild=True` 和 `UserControl=False`，所有异常严格收口在 Python 层通过错误码解析，严禁阻塞交互。

---

## 三、最终评审结论

本评估报告确认：
1. `dsh-solidworks-plugin` 拥有优良的底层安全回滚体系与拓扑图论基础；
2. 阶段三的核心技术瓶颈已经彻底穿透并查清；
3. 开源选型方案界限分明（思想借鉴 CadQuery 选择器，内核坚定复用 SolidWorks 原生 API）；
4. 阶段三已具备进入正式实施的技术方案与验收闭环标准。
