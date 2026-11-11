# 开源 CAD 与参数化建模技术选型调研报告

## 一、调研背景与选型目标

在阶段三（AI 建模能力升级）中，为了避免从零发明几何表达规范与选择器语法，我们对业界主流的开源参数化 CAD 框架与代码建模工具进行了深度技术调研。
核心评估指标包括：
1. **架构契合度**：能否与 SolidWorks 原生特征树及 COM API 形成协同；
2. **AI 友好度**：LLM 是否擅长理解并生成该体系的代码或描述；
3. **拓扑命名解决能力**：能否稳健解决特征引用的断链问题（Topological Naming Problem）；
4. **许可证合规性**：是否允许商业与插件集成，有无传染性风险；
5. **落地可行性**：是直接集成、适配二次开发，还是仅借鉴设计模式。

---

## 二、主流开源技术全景对比与技术透视

### 1. CadQuery (CQ)
- **项目定位**：基于 Python 的参数化 Code-as-CAD 框架，底层依赖 OpenCASCADE (OCCT)。
- **开源许可证**：**Apache 2.0**（商业极度友好，无代码传染性）。
- **核心技术亮点**：
  1. **Workplane（工作平面）抽象**：通过 `cq.Workplane("XY")` 轻松定义二维绘图参考系，并在三维形体生成后，通过 `.faces(">Z").workplane()` 链式在已有实体的任意面上继续建构。
  2. **声明式选择器 (Selectors DSL)**：
     CadQuery 发明了一套极度强大的字符串过滤选择器：
     - 方向选择器：`>Z`（Z 轴最大面）、`<X`（X 轴最小面）、`|Z`（平行于 Z 轴的面）；
     - 几何类型选择器：`#PLANE`（平面）、`%CIRCLE`（圆形面/边）；
     - 邻近选择器：`>Z[-1]`（从高到低倒数第一个）。
     **这一语法对 LLM 极其友好**，AI 不需要知道底层拓扑面的具体索引（如 `Face14`），只需声明“在最高的表面开孔”即可。
- **局限性与禁忌**：
  - **绝不能替换 SolidWorks**：CadQuery 的底层是 OCCT B-Rep 几何内核，而 SolidWorks 的底层是专有 Parasolid 内核。二者的几何描述、布尔运算、拓扑定义完全不同，且 CadQuery 无法生成原生的 SolidWorks 特征树与 `.sldprt` 文件。

### 2. build123d
- **项目定位**：CadQuery 核心贡献者重新设计的新一代 Python CAD 框架，提供纯对象模型（Direct API）与上下文管理器模式（Algebraic / Builder API）。
- **开源许可证**：**Apache 2.0**（商业友好）。
- **核心技术亮点**：
  1. **明确的上下文模式**：通过 `with BuildPart(): with BuildSketch(): ...` 组织代码，与树状的机械特征工程极为契合。
  2. **强类型几何拓扑模型**：拥有明确的 `Vertex`、`Edge`、`Wire`、`Face`、`Solid` 对象，拓扑关系清晰。
  3. **增强的选择器与对齐系统**：引入了 `Align.CENTER`、`Location` 与轴对齐概念，几何计算非常严谨。
- **局限性**：
  同样强依赖 OCCT 内核与 `pythonocc-core`，体量庞大，无法直接作为 SolidWorks 物理后端的替代品。

### 3. FreeCAD & PartDesign 模块
- **项目定位**：全功能开源三维参数化建模软件，基于 C++ / Python。
- **开源许可证**：**LGPL-2.1+**（有一定许可证约束，需谨慎处理动态链接与源码分发）。
- **核心技术亮点**：
  1. **特征依赖 DAG**：FreeCAD 的 `App::DocumentObject` 体系与 SolidWorks 的特征树极为相似，支持父子依赖计算与增量重构。
  2. **草图约束求解器 (PlanarGCS)**：将草图表示为几何基元（点、线段、圆弧）和几何约束方程（重合、水平、垂直、相切、距离、角度），由求解器求解欠约束/过约束。
  3. **拓扑命名问题 (TNP) 解决方案**：FreeCAD v0.21+（由 RealThunder 分支演进）通过引入 Element Map（元素映射拓扑哈希指纹），解决了特征修改后边/面重新编号的断链问题。
- **局限性**：
  FreeCAD 是庞大的桌面级 C++ 应用程序，将其核心求解器或完整代码剥离并内嵌到轻量级 MCP 插件中极不现实，且存在 LGPL 许可证合规成本。

---

## 三、开源框架横向对比矩阵

| 评估维度 | CadQuery | build123d | FreeCAD (PartDesign) | SolidWorks 原生 API |
| :--- | :--- | :--- | :--- | :--- |
| **底层几何内核** | OCCT (OpenCASCADE) | OCCT (OpenCASCADE) | OCCT (OpenCASCADE) | **Parasolid (专有)** |
| **许可证类型** | Apache 2.0 | Apache 2.0 | LGPL 2.1+ | 商业专有 (SDK 无额外版税) |
| **几何选择器表现** | **卓越 (`>Z`, `\|X`)** | 良好 (对象属性选择) | 中等 (依赖拓扑名称) | 基础 (依赖名称/坐标拾取) |
| **工作平面与坐标系** | 链式 Workplane 极简 | 强类型 Location 上下文 | Placement 复杂矩阵 | 原生基准面与面引用 |
| **草图约束表达** | 偏向隐式几何生成 | 偏向显式定位对齐 | **卓越 (显式数学约束)** | **卓越 (原生 2D 约束求解)** |
| **原生特征树保留** | 无 (纯几何 Step/B-Rep) | 无 (纯几何 Step/B-Rep) | 支持 (FreeCAD 树) | **支持 (完整原生特征树)** |
| **在本项目中的定位** | **借鉴选择器与平面抽象** | **借鉴构建器设计模式** | **借鉴约束数据模型** | **唯一的物理执行与交付内核** |

---

## 四、阶段三技术复用与自研边界决策

基于上述调研，我们对阶段三各模块的开源复用策略作出明确裁决：

### 1. 坚决排除的方案（红线）
- ❌ **不得引入 CadQuery / OCCT 作为三维运算替代内核**：
  试图在 Python 中用 OCCT 算好几何体再导成 STEP 塞给 SolidWorks，会完全摧毁 SolidWorks 的“特征可编辑性”（丢失草图、拉伸、倒角等特征历史，变成无法二次编辑的死实体），违背工业级 CAD 插件的核心使命。
- ❌ **不得直接依赖大型 C++ 外部框架（如 FreeCAD 源码）**：
  避免引入臃肿庞大的二进制依赖，保持插件轻量（纯 Python + Node.js 架构）。

### 2. 深度借鉴与思想吸收（模式移植）
- 💡 **吸收 CadQuery 的 Selector DSL 思想**：
  在 `Feature Graph IR` 中设计轻量级**声明式选择器**。例如在圆角特征中，AI 只需指定 `edges_selector: ">Z & #CIRCLE"`，由本地插件在 SolidWorks 模型中遍历当前实体的边并计算法向量，动态选中对应的 COM 边对象。这能从根本上消除因拓扑面/边重编号导致的建模失败。
- 💡 **吸收 build123d 的 Builder 上下文生命周期**：
  借鉴其上下文管理思想，将 SolidWorks 的 `start_sketch` / `end_sketch` 与 `CADTaskContext` 结合，确保任何草图创建都在严格的异常捕获与自动清理保护下进行。
- 💡 **吸收 FreeCAD 的草图约束语义**：
  在 IR 中将草图定义从“单纯画线”升级为“几何图元 + 拓扑约束（Coincident, Tangent, Perpendicular, Equal）”，直接调用 SolidWorks 原生的 `AddRelation` 接口。

### 3. 自主实现的模块
- 🛠️ **SolidWorks 拓扑实体解析器 (`sw_topology_resolver.py`)**：
  自主编写基于 SolidWorks `IModelDoc2.Extension.SelectByID2` 与 `IFace2`/`IEdge` 几何属性匹配的高精选择器。
- 🛠️ **CADGraphExecutor 物理执行引擎**：
  自主实现消费 `FeatureGraphIR` 并与 `CADTaskRollbackManager` 深度协同的物理调度器。
