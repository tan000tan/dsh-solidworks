# SolidWorks 真实环境端到端验证测试套件指南

> 本目录为 `dsh-solidworks` 阶段三 P0.2 建立的 SolidWorks 真实实机验收测试程序集，提供一整套可复现、可诊断、完全物理隔离的 CAD 特征图建模验证环境。

---

## 一、目录结构与模块说明

```
tests/real_cad/
├── README.md                      # 本操作指南
├── geometry_verifier.py          # 真实几何结果、特征树、包围盒与质量属性物理断言器
├── real_cad_preflight.py         # 实机只读前置环境检查程序 (PRECHECK)
├── real_cad_graph_test.py        # 正向建模验收测试套件 (最小特征图 + 多节点特征图)
├── real_cad_failure_test.py      # 异常恢复与回滚测试套件 (3大故障场景)
└── sandbox/                      # 物理沙箱目录 (隔离生成零件，.gitignore 自动忽略)
```

---

## 二、测试用例设计与预期几何参数

### 1. 测试一：最小特征图 (MinimalGraph)
- **拓扑结构**：`BaseSketch (sketch_2d)` $\to$ `Boss-Extrude1 (extrude_boss)`
- **几何定义**：
  - 草图：前视基准面，中心矩形 $100\text{ mm} \times 50\text{ mm}$ ($0.1\text{ m} \times 0.05\text{ m}$)
  - 拉伸：单向盲孔拉伸深度 $20\text{ mm}$ ($0.02\text{ m}$)
- **预期几何与物理参数**：
  - 特征树：必须包含 `BaseSketch` 与 `Boss-Extrude1`，且无模型警告/错误；
  - 实体数量：实体数（Solid Bodies）严格等于 **1**；
  - 包围盒尺寸：$X = 100 \pm 0.5\text{ mm},\ Y = 50 \pm 0.5\text{ mm},\ Z = 20 \pm 0.5\text{ mm}$；
  - 理论体积：$0.1 \times 0.05 \times 0.02 = 1.0 \times 10^{-4}\text{ m}^3$（容差 $2\%$）；
  - 理论表面积：$0.016\text{ m}^2$（容差 $2\%$）。

### 2. 测试二：多节点特征图 (MultiNodeGraph)
- **拓扑结构**：`BaseSketch` $\to$ `Boss-Extrude1` $\to$ `HoleSketch` $\to$ `Cut-Extrude1`
- **几何定义**：
  - 在凸台实体基础上，在上视/前视基准面创建直径 $20\text{ mm}$ ($r = 0.01\text{ m}$) 的贯通切除圆孔；
  - 验证多级依赖传递、草图句柄继承与重构有效性。
- **预期几何与物理参数**：
  - 特征树：包含全部 4 个特征，且特征状态正常；
  - 实体数量：保持为 **1** 个连通实体；
  - 理论体积：$(0.1 \times 0.05 - \pi \times 0.01^2) \times 0.02 \approx 9.3717 \times 10^{-5}\text{ m}^3$；
  - 理论表面积：外表面积扣除两端圆面，加上内圆柱孔表面积。

### 3. 测试三：异常恢复与回滚测试 (FailureTests)
- **MissingSketchDependency**：拉伸特征缺少草图前置依赖，验证执行器抛出确定性异常并安全拦截；
- **InvalidGeometryRollback**：注入非法零深度几何拉伸，验证底层报错后，自动回滚清理已建草图，特征树恢复纯净；
- **BranchCascadeSkip**：多分支局部故障，验证故障下游子树被完全标记为 `SKIPPED`，健康分支不受波及。

---

## 三、安全模式与启动方法

测试程序严格区分 **PRECHECK（只读）** 与 **EXECUTE（真实写入）** 双重模式：

### 1. 运行环境预检查 (PRECHECK，只读安全)
仅验证 COM 链路、STA Worker 调度、桌面权限、沙箱可写性与已有文档快照，**绝不进行任何 CAD 写入**：
```powershell
$env:PYTHONDONTWRITEBYTECODE="1"
python tests/real_cad/real_cad_preflight.py
```

### 2. 运行建模套件预检查 (只读拓扑与参数断言)
```powershell
python tests/real_cad/real_cad_graph_test.py --mode precheck
python tests/real_cad/real_cad_failure_test.py --mode precheck
```

### 3. 首次实机端到端真实建模测试 (必须获得用户显式授权)
在用户与审核方明确授权后，方可添加 `--mode execute` 与 `--authorize-cad-write` 执行真实 CAD 建模：
```powershell
# 仅执行最小特征图建模
python tests/real_cad/real_cad_graph_test.py --mode execute --authorize-cad-write --test minimal

# 执行全部正向建模套件（测试一 + 测试二）
python tests/real_cad/real_cad_graph_test.py --mode execute --authorize-cad-write --test all

# 若需要在测试后保留 SolidWorks 窗口中的零件供人工视觉审查：
python tests/real_cad/real_cad_graph_test.py --mode execute --authorize-cad-write --retain
```

---

## 四、安全隔离与环境清理机制

1. **零触碰用户现有工程**：
   - 严禁调用 `sw.ActiveDoc`；
   - 统一由 `new_document(sw, "part")` 生成全新独立零件；
2. **沙箱物理路径约束**：
   - 所有测试文件强制存储于 `tests/real_cad/sandbox/`；
   - 文件名自动注入微秒级时间戳（例如 `ir_minimal_20261103_205600_123456.SLDPRT`），杜绝覆盖任何已有文件；
3. **精准销毁与异常保留**：
   - 测试通过后，仅按文档标题精准调用 `CloseDoc` 关闭本次测试创建的模型；
   - 若建模发生异常，**自动保留该沙箱文件**供工程师在 SolidWorks 中直接打开排查特征树报错原因。
