# 角色审计报告 04：第三方开发者视角

> **审计视角**：准备向项目贡献代码的开源开发者、CAD 二次开发工程师、外部工具链集成者  
> **审查基准**：代码可维护性、模块抽象、类型安全、调试基础设施与可扩展性  
> **核心命题**：**一个新接手或外部开发者能否快速理解架构？未来 Feature Graph IR、复杂装配体和工程图能否在该架构上平滑扩展？**

---

## 一、代码工程质量与架构可读性审查

### 1.1 双语言架构栈与认知负担
- **Node.js 侧（桥接与策略层）**：约 1,500 行，模块划分极度清晰（`index.js`, `policy.js`, `discover.js`, `mcp.js`, `schema.js`），职责单一，且具备很高的异步防御质量。
- **Python 侧（引擎与 CAD 驱动层）**：约 12,000 行，虽然核心库抽离了 65 个脚本模块，但 [`vendor/.../server.py`](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/vendor/solidworks-automation-skill/mcp-server/server.py) **单文件体积高达 7,653 行**！
- **开发者痛点**：
  - 所有的 `@mcp.tool()` 装饰器函数与复杂的参数拼装、异常处理混合平铺在 `server.py` 中，形成了明显的“上帝文件”（God File）；
  - 新开发者想要添加一个新特征或工具，必须在 7,600 多行的单文件中查找和插入代码，极易引发 Git 冲突。

### 1.2 类型系统与接口契约
- **JavaScript 侧**：纯原生 ES Modules，**缺乏 TypeScript 定义文件 (`index.d.ts`)**。开发者在调用 `Policy`、`McpClient` 或消费工具参数时无法享受 IDE 智能补全和编译期静态检查；
- **Python 侧**：在参数输入层积极采用了 Pydantic 校验与类型注解，但在底层调用 `win32com.client.Dispatch` 与 SolidWorks COM 对象时，由于动态 COM 调度的特性，全部退化为弱类型 `Any`，缺乏 SolidWorks TypeLib 静态提示。

### 1.3 核心能力模块的可扩展性评估

```mermaid
flowchart TD
    subgraph S1["Feature Graph IR 拓扑扩展"]
        IR1["DAG 节点抽象 (FeatureNode)"] --> IR2["Kahn 拓扑排序算法"]
        IR2 --> IR3["【评价: 极佳 (A)】解耦彻底，支持跨 CAD 扩展"]
    end
    subgraph S2["装配体架构扩展"]
        ASM1["过程式脚本调用 (sw_assembly.py)"] --> ASM2["缺乏 AssemblySession 状态机"]
        ASM2 --> ASM3["【评价: 一般 (C)】多级子装配易产生状态混乱"]
    end
    subgraph S3["工程图架构扩展"]
        DRW1["单一工作流 (drawing_workflow)"] --> DRW2["缺乏图纸图层/尺寸标注对象化"]
        DRW2 --> DRW3["【评价: 较弱 (D)】扩展国标模板需重构"]
    end
```

1. **Feature Graph IR 扩展性：极佳 (Grade A)**
   - [`feature_graph_ir.py`](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/vendor/solidworks-automation-skill/scripts/feature_graph_ir.py) 设计得非常漂亮，采用了纯内存 DAG 数据结构与 Kahn 算法；
   - 依赖关系解耦彻底，第三方开发者可以非常轻松地引入新的特征节点类型（如扫掠、放样），并自动完成时序推导与无环拓扑校验。
2. **装配体与工程图扩展性：较弱 (Grade C/D)**
   - `sw_assembly.py` 与 `sw_drawing.py` 目前多为线性的过程式函数调用；
   - 缺乏全局的装配体组件树引用管理与工程图图纸空间抽象，未来若要支持大型装配体（100+ 零件）配合解算，必须进行面向对象的状态机重构。

### 1.4 本地调试、测试夹具与 CI 障碍
- **优秀夹具**：
  - 提供了 [`tests/stub-server.py`](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/tests/stub-server.py) 与 [`tests/stub-server.mjs`](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/tests/stub-server.mjs)，允许在无需启动任何 CAD 的情况下进行全量协议与策略回归；
  - 单元测试运行极快（JS 套件耗时仅 ~1.4s）。
- **严重阻碍**：
  - **真机测试不可移植**：真实 SolidWorks 测试严重依赖本地商业授权与 Windows 交互桌面，GitHub Actions 等云端 Linux CI 只能运行 Stub/Mock 测试，任何涉及 COM 的真实回归无法在公共开源流水线上跑通，导致外部开发者难以提交带有 CAD 铁证的 PR。

---

## 二、开发者建议清单

1. **重构拆分 `server.py`**：按业务领域（`routes/part.py`, `routes/assembly.py`, `routes/drawing.py`, `routes/inspect.py`）将 7,653 行单文件拆解为路由子模块；
2. **生成 TypeScript `.d.ts` 声明**：为 `lib/` 核心组件补齐类型导出，增强二次开发体验；
3. **固化 Mock 录制回放系统**：构建 COM 调用的录制与回放夹具，使无 SolidWorks 商业许可的外部贡献者也能在 Linux/macOS 环境下运行高逼真度集成测试。
