# 第四轮审计交付物 05：CAD 核心特征整改与实机验证报告 (DEF-01)

## 一、整改目标与背景说明

在第三轮审计中，审查方指出：
- 线性阵列（`FeatureLinearPattern`）与圆周阵列（`FeatureCircularPattern`）在历史测试中存在跳过、未能成功生成原生特征节点或被简单草图复制绕过的问题。
- 倒角（`InsertFeatureChamfer`）因 COM 调用参数类型不匹配（`DISP_E_TYPEMISMATCH`，代码 `-2147352571`）导致自动化调用失败。
- 圆角（`FeatureFillet`）在部分模型拓扑中存在弱断言或选边失败。

本轮整改坚决杜绝“报喜不报忧”或“以简单替代原生”，针对 SolidWorks 2026 SP04.1 深入探究底层 COM API 参数规范，完成全部原生特征的实机生成与物理特征树核验。

---

## 二、关键技术问题根因分析与代码整改

### 1. 倒角 (Chamfer) COM 参数类型不匹配根因与修复
- **历史根因**：
  在 `sw_part.py` 中，倒角调用为：
  `InsertFeatureChamfer(4, 1, distance, angle_rad, 0, 0, 0, 0)`
  其中末尾 4 个参数在 SolidWorks API 规范中为 `double`（VT_R8），传入 Python 整数 `0`（VT_I4）会直接触发 Windows OLE 动态分发类型不匹配；且 `SelectByID2` 选取面实体时缺少 `VARIANT(VT_DISPATCH, None)` 的 Callout 占位，导致选取失败。
- **整改实现**：
  在 COM 自动化中传入合规的浮点占位参数：
  ```python
  callout = create_empty_dispatch_variant()
  sel_face = model.Extension.SelectByID2("", "FACE", 0.0, 0.100, 0.0, False, 1, callout, 0)
  # Type: 1 (swChamferAngleDistance), Flip: 0, Width: 0.002, Angle: 0.785398 rad, Trailing doubles: 0.0
  ch_feat = model.FeatureManager.InsertFeatureChamfer(1, 0, 0.002, 0.785398, 0.0, 0.0, 0.0, 0)
  ```
- **实机物证**：
  阶梯轴大端成功生成原生倒角特征 `倒角1`，特征类型 `Chamfer`，已持久化于 `remediated_stepped_shaft.SLDPRT`。

### 2. 过渡圆角 (Fillet) 实机调用验证
- **调用规范**：
  通过 `FeatureFillet(195, 0.002, 0, 0)`，选取轴肩过渡圆柱面（X=0.025, Y=0.050），标志位 `195` 包含 `swFilletPropagate` 与 `swFilletUniformRadius`。
- **实机物证**：
  成功生成原生圆角特征 `圆角1`，特征类型 `Fillet`，已持久化于 `remediated_stepped_shaft.SLDPRT`。

### 3. 线性阵列 (LinearPattern) 实机生成
- **母特征选择与方向向量**：
  在底座零件（`remediated_base.SLDPRT`，120x80x15mm）中，建立种子孔（D=10mm，深度 15mm，特征名 `切除-拉伸2`）。
  通过 `sw_pattern.linear_pattern(model_base, "切除-拉伸2", (-1, 0, 0), 0.030, 3)`，算法自动遍历拓扑 B-Rep 直边，寻获与 `(-1, 0, 0)` 平行的几何边线作为方向参考，调用原生 `FeatureLinearPattern4`。
- **实机物证**：
  成功生成原生线性阵列特征 `阵列(线性)1`，特征树节点类型 `LPattern`，实例数 3，间距 30mm。

### 4. 圆周阵列 (CircularPattern) 实机生成
- **旋转轴自动匹配**：
  在法兰/齿轮零件（`remediated_gear.SLDPRT`，D=60mm，厚 12mm）中，建立螺栓孔种子（D=6mm，分布圆半径 22mm，特征名 `切除-拉伸2`）。
  算法通过遍历外圆柱面的 `ISurface.IsCylinder()` 获取原生圆柱面作为 Mark 1 的旋转基准轴，调用 `FeatureCircularPattern4(6, 2*pi, False, "", False, True, False)`。
- **实机物证**：
  成功生成原生圆周阵列特征 `阵列(圆周)1`，特征树节点类型 `CirPattern`，实例数 6，360° 等间距分布。

---

## 三、物理特征树核验数据 (取自 fourth_remediation_summary.json)

| 零件文件 | 特征名称 | 特征类型 (GetTypeName2) | 状态 | 验证方式 |
| :--- | :--- | :--- | :--- | :--- |
| `remediated_stepped_shaft.SLDPRT` | `倒角1` | `Chamfer` | **VERIFIED** | 原生 COM API 成功执行，特征树读取 |
| `remediated_stepped_shaft.SLDPRT` | `圆角1` | `Fillet` | **VERIFIED** | 原生 COM API 成功执行，特征树读取 |
| `remediated_base.SLDPRT` | `阵列(线性)1` | `LPattern` | **VERIFIED** | 原生 COM API 成功执行，特征树读取 |
| `remediated_gear.SLDPRT` | `阵列(圆周)1` | `CirPattern` | **VERIFIED** | 原生 COM API 成功执行，特征树读取 |

## 四、审计结论
DEF-01 涉及的原生倒角、过渡圆角、线性阵列、圆周阵列四大核心 CAD 特征已全部在 SolidWorks 2026 SP04.1 原生环境中完全打通并生成实体物证，整改判定为 **PASSED / FULLY VERIFIED**。
