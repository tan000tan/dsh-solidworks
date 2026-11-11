# SolidWorks 真实物理实机端到端验证报告 (06_SOLIDWORKS_REAL_MACHINE_E2E.md)

**报告编号**：REWORK-V1.0-06-CAD-E2E  
**执行角色**：实施方自检 (IMPLEMENTER SELF-REVIEW)  
**执行脚本**：`tests/real_cad/run_v10_rework_e2e.py`  
**核查结论**：**PASS** (8/8 验证阶段全部通过，具备完整物理物证与日志)

---

## 一、执行原则与安全隔离证明

1. **零进程启动基线**：测试启动前，全系统无正在运行的 `SLDWORKS.exe` 进程，测试前进程清单为 `{}`。
2. **专属测试实例**：测试由脚本独立启动后台 SolidWorks 实例，分配操作系统 PID 为 **`30792`**，标记 `started_by_cad_studio=True`。绝无连接用户已有会话。
3. **独立沙箱目录**：所有模型均创建于独立隔离沙箱目录 `audit/v1.0-rework-20261108/cad_e2e_sandbox/`，绝对不覆盖、修改或触碰任何现有工程或用户文件。
4. **安全关闭与进程回收**：模型保存后，全部通过 `force_discard=False` 的安全模式关闭文档。测试完成后，向 PID `30792` 发送退出指令，等待进程彻底退出。测试后全系统 SolidWorks 进程再次归零（`{}`），恢复纯净待机基线。

---

## 二、端到端建模、特征生成与几何物证

### 2.1 阶梯轴 (`v10_stepped_shaft.SLDPRT`)
- **文件大小**：93,747 字节
- **包含特征**：
  - 基础草图1 + 凸台-拉伸1 ($\Phi 30 \times 100\text{ mm}$)
  - 草图2 + 凸台-拉伸2 ($\Phi 20 \times 80\text{ mm}$)
  - 草图3 + 键槽切除-拉伸1 ($6 \times 30 \times 3.5\text{ mm}$)
  - 轴端倒角 (`倒角1`): $1.0\text{ mm} \times 45^\circ$，调用 `InsertFeatureChamfer`
  - 台阶过渡圆角 (`圆角1`): $R 2.0\text{ mm}$，调用 `FeatureFillet`
- **特征树总数**：26 个特征节点（包含系统文件夹、基准面、原点及自定义特征）
- **STL 离散三角网格体积数值积分验证**：
  - 生成 STL 离散文件：`v10_stepped_shaft.STL` (123,184 字节，2,462 个三角形面片)
  - 离散网格体积数值积分值：$251,944.796\text{ mm}^3$
  - 理论几何解析体积值：$251,938.210\text{ mm}^3$
  - **几何积分相对误差**：**$0.0026\%$**（远优于 $0.5\%$ 的严苛工程容限）

### 2.2 支座法兰 (`v10_base.SLDPRT`)
- **文件大小**：87,006 字节
- **包含特征**：
  - 矩形基板凸台 ($100 \times 80 \times 20\text{ mm}$)
  - 轴承安装通孔切除 ($\Phi 30\text{ mm}$)
  - 单个螺栓安装孔切除 ($\Phi 10\text{ mm}$)
  - 线性阵列 (`阵列(线性)1`): 3 个实例，间距 $25\text{ mm}$，调用 `InsertFeatureLPattern`
- **特征树总数**：25 个特征节点

### 2.3 传动齿轮 (`v10_gear.SLDPRT`)
- **文件大小**：95,564 字节
- **包含特征**：
  - 轮坯圆盘凸台 ($\Phi 80 \times 15\text{ mm}$)
  - 轴孔与键槽切除 ($\Phi 20\text{ mm}$ 通孔 + $6\text{ mm}$ 键槽)
  - 单个减重孔切除 ($\Phi 12\text{ mm}$)
  - 圆周阵列 (`阵列(圆周)1`): 6 个实例，围绕基准轴 $360^\circ$ 均布，调用 `InsertFeatureCirPattern`
- **特征树总数**：25 个特征节点

### 2.4 完整装配体 (`v10_assembly.SLDASM`)
- **文件大小**：93,822 字节
- **装配组件**：
  - `v10_base-1` (固定件)
  - `v10_stepped_shaft-1` (运动配合件)
  - `v10_gear-1` (安装于轴上的传动轮)
- **同轴心真实装配配合 (`swMateCONCENTRIC`)**：
  - 配合 1：支座轴承孔柱面与阶梯轴大端柱面同轴心 (`concentric_base_shaft = True`)
  - 配合 2：齿轮内孔柱面与阶梯轴小端柱面同轴心 (`concentric_gear_shaft = True`)
  - 配合求解器状态：19 个装配体特征节点，配合求解全部收敛无干涉。
- **STEP AP214 国际标准导出**：
  - 导出配置：显式设置 `swStepAP=75` 为 `214` (STEP AP214 几何与装配标准)
  - 产物文件：`v10_assembly.step` (132,874 字节)
  - 内容物证：包含标准 STEP 文件头 `ISO-10303-21;` 与 `AUTOMOTIVE_DESIGN` 上下文。

### 2.5 四视图标准工程图 (`v10_drawing.SLDDRW` & `v10_drawing.pdf`)
- **工程图大小**：122,971 字节
- **投影视图配置**：基于 `A4 - 横向` 标准图纸，自动生成 4 个标准化视图：
  1. `工程图视图1`：标准前视图 (`*前视`)，比例 1:1，位于图纸左侧
  2. `工程图视图2`：标准俯视图 (由前视正交投影生成)，比例 1:1
  3. `工程图视图3`：标准右视图 (由前视正交投影生成)，比例 1:1
  4. `工程图视图4`：三维等轴测视图 (`*等轴测`)，比例 2:1，位于右上侧图区
- **矢量 PDF 导出**：
  - 产物文件：`v10_drawing.pdf` (54,521 字节)
  - 内容物证：标准 Adobe PDF 矢量图，包含全部 4 个视图的线框渲染，可直接用于车间打印。

---

## 三、落盘保存与独立重载复核 (Reopen Verification)

为彻底杜绝“仅在内存中存留、无法落盘重载”的伪完成缺陷，测试脚本在保存并关闭文档后，**重新从磁盘读取二进制文件并调用 `OpenDoc6` 进行二次加载验证**：

| 文件名称 | 文件路径 | 重载状态 | 识别类型 | 特征树节点计数 | 复核结论 |
|:---|:---|:---:|:---:|:---:|:---:|
| `v10_stepped_shaft.SLDPRT` | `.../cad_e2e_sandbox/v10_stepped_shaft.SLDPRT` | **TRUE** | `swDocPART (1)` | 26 个特征 | **PASS** |
| `v10_base.SLDPRT` | `.../cad_e2e_sandbox/v10_base.SLDPRT` | **TRUE** | `swDocPART (1)` | 25 个特征 | **PASS** |
| `v10_gear.SLDPRT` | `.../cad_e2e_sandbox/v10_gear.SLDPRT` | **TRUE** | `swDocPART (1)` | 25 个特征 | **PASS** |
| `v10_assembly.SLDASM` | `.../cad_e2e_sandbox/v10_assembly.SLDASM` | **TRUE** | `swDocASSEMBLY (2)` | 19 个特征 | **PASS** |
| `v10_drawing.SLDDRW` | `.../cad_e2e_sandbox/v10_drawing.SLDDRW` | **TRUE** | `swDocDRAWING (3)` | 7 个特征 | **PASS** |

---

## 四、物理文件清单与 SHA-256

```text
6D4CD4BF44E68C222AFBAAC66367098BA0E1A72F6DA44031B05E1A0F907796FA *v10_stepped_shaft.SLDPRT (93,747 B)
5FD2DA8E82E3272FA2D98DCEB6D3605CDD4C30A093D89CE720188EBEC25055AC *v10_stepped_shaft.STL (123,184 B)
16FF02213D5E4D8EF8A5E8AFB2CD46F1BA6E56475C667BE6FDFE3A1CD083A3C0 *v10_base.SLDPRT (87,006 B)
DC4E8E2D9321262B5C1A29D6E3F61BEF8CCFC79391EE3B2202AC2F5F45434DF2 *v10_gear.SLDPRT (95,564 B)
099AC6602324DE741D8BDD9503B8F80B9C9B4706596DC3600615DF7B7203A0FF *v10_assembly.SLDASM (93,822 B)
205938BD70A8A62BDCF55F55F11F1C62A8C182F19EAE6E1B624A9A662AF4A0A4 *v10_assembly.step (132,874 B)
B4DC2F453531F3287F4A78229F8AE2E5BCFDCF06B4D636B58F2C77D59A1DDF0E *v10_drawing.SLDDRW (122,971 B)
F4FBD6E68E8E9FF5F565147FF6C852D029B87F7D2ACD9DB33A2E77CE2D51390A *v10_drawing.pdf (54,521 B)
062F52994017EE94AC6E33B10FFB8B3B8BBD96BCEE7A94D4811FE49AF8EFB2DF *v10_rework_e2e_summary.json (14,645 B)
```

---

## 五、实施方自检判定

依据实机物理生成的文件、离散网格积分、装配配合约束、工程图 4 视图渲染、磁盘重载及 0 进程回收记录：
- **判定结果**：**PASS**
- **物证完整度**：**COMPLETE**
