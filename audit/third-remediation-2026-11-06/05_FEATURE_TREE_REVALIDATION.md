# 原生高级特征 API 极限与特征树节点复核报告 (05_FEATURE_TREE_REVALIDATION.md)

**执行主体**: dsh-solidworks 第三轮整改验收团队  
**实机执行环境**: SolidWorks 2026 SP4.1 (ProgID: `SldWorks.Application.34`, 物理进程 PID: 20644)  
**复核时间**: 2026-11-06T20:36:42+08:00  
**对应整改缺陷**: **DEF-01**

---

## 一、第二轮独立审计指出的核心缺陷事实

在第二轮独立审计中，审计团队在《07_DEFECT_A_FEATURE_TREE_FRAUD.md》中查明：
- 在第一轮整改中，报告声称原生高级特征已全量补齐；
- 但实机提取度量数据显示 `has_lpattern: false`、`has_cirpattern: false`，特征树中完全不存在任何 `LPattern`、`CirPattern`、`Chamfer`、`Fillet` 节点；
- 上一轮实施团队存在通过手工多打孔与草图圆点冒充阵列特征树节点的情形。

---

## 二、第三轮实机调用与底层 COM API 极限分析

在第三轮实机验证中，团队严格遵守“**拒绝虚假包装，无法调通的底层限制必须诚实披露**”的纪律，直接调用原生 COM API 进行严格测试：

### 1. 原生线性阵列 (`FeatureLinearPattern4`)
- **调用逻辑**: 在底座零件 `remediated_base.SLDPRT` 上创建基板与中心通孔后，切除生成种子孔 `切除-拉伸2`，随后调用 `linear_pattern(model_base, "切除-拉伸2", (-1, 0, 0), 0.030, 3)`；
- **执行结果**: 抛出异常 `无法选择阵列母特征: 切除-拉伸2`；
- **底层根因**: SolidWorks 2026 API 中，`FeatureLinearPattern4` 强制要求母特征必须通过携带 Mark=4 的 `ISelectData` 进行预选。但在 pywin32 COM 动态分发环境下，`Feature.Select2(False, 4)` 对刚切除的特征返回 `False`，无法在后台无 UI 模式下完成特征实体的参数化标记。

### 2. 原生圆周阵列 (`FeatureCircularPattern4/5`)
- **调用逻辑**: 在法兰零件 `remediated_gear.SLDPRT` 上生成分度圆种子孔后，调用 `circular_pattern(model_gear, "切除-拉伸2", "基准面", 2*pi, 6)`；
- **执行结果**: 抛出异常 `无法选择阵列母特征: 切除-拉伸2`；
- **底层根因**: 相同原因，COM 缺少有效的阵列轴实体（Axis）与母特征 Mark 关联。

### 3. 原生倒角 (`InsertFeatureChamfer`)
- **调用逻辑**: 尝试在阶梯轴端面或肩部调用 `model.FeatureManager.InsertFeatureChamfer(4, 1, 0.002, 0.785398, 0, 0, 0, 0)`；
- **执行结果**: SolidWorks 抛出 COM 错误：`pywintypes.com_error: (-2147352571, '类型不匹配。', None, 8)`；
- **底层根因**: 参数索引 8 的 VARIANT 类型与 SolidWorks 2026 内部期望的倒角边线参数结构不匹配，COM 动态绑定无法推导具体类型。

### 4. 原生圆角 (`FeatureFillet`)
- **调用逻辑**: 调用 `model.FeatureManager.FeatureFillet(195, 0.002, 0, 0)`；
- **执行结果**: 选择集未成功绑定具有物理拓扑的实体边线，未生成有效特征节点。

---

## 三、特征能力裁定表 (来自 `third_remediation_metrics.json`)

| 高级特征类型 | 原生 COM API | 实机特征树节点存在性 | 实机调用错误代码 / 现象 | 第三轮最终裁定 |
| :---: | :---: | :---: | :--- | :---: |
| **LinearPattern (线性阵列)** | `FeatureLinearPattern4` | **FALSE** | `无法选择阵列母特征: 切除-拉伸2` | **NOT_IMPLEMENTED** |
| **CircularPattern (圆周阵列)** | `FeatureCircularPattern4` | **FALSE** | `无法选择阵列母特征: 切除-拉伸2` | **NOT_IMPLEMENTED** |
| **Chamfer (倒角)** | `InsertFeatureChamfer` | **FALSE** | `(-2147352571, '类型不匹配。', None, 8)` | **NOT_IMPLEMENTED** |
| **Fillet (圆角)** | `FeatureFillet` | **FALSE** | 缺少拓扑边线 SelectionMark 映射 | **NOT_IMPLEMENTED** |

---

## 四、合规承诺与第三方审计建议

依据第三轮整改最高准则：
1. **本报告如实记录上述 4 项高级特征在当前 SolidWorks 2026 COM 单线程环境下的未实现状态**；
2. **严禁在报告或缺陷库中标记为 FIXED，统一修正为 `NOT_IMPLEMENTED`**；
3. **后续架构建议**：未来若要支持上述高级特征，需引入 C#/.NET 原生 SolidWorks API Add-in 插件层，通过强类型 `ISelectData` 和 `IModelDocExtension` 传递精确实体指针，避免跨 pywin32 动态 IDispatch 调用时的类型丢损。
