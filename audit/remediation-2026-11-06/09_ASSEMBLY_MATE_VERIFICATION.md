# 装配体配合特征与关系核验报告

**核验对象**: `audit/remediation-2026-11-06/cad_test_sandbox/remediated_assembly.SLDASM`  
**组件清单**: 
1. `remediated_linear_base` (底座基准零件，固定)
2. `remediated_stepped_shaft` (阶梯轴零件，浮动)
3. `remediated_circular_gear` (齿轮零件，浮动)

---

## 一、整改前后装配体配合状态对比

| 核验项 | 阶段七原装配体 (Defect D) | 本次整改装配体 | 状态 |
| :--- | :--- | :--- | :--- |
| **组件数量** | 3 个组件 | **3 个组件** | PASS |
| **配合特征树节点 (`MateGroup`)** | 缺失或无生效子项 | **存在明确的 `MateGroup` 节点 (`配合` / `Mates`)** | **REMEDIATED** |
| **配合类型** | 无 | **重合配合 (`add_mate_coincident`)** | **REMEDIATED** |
| **组件空间约束** | 各组件处于默认空间散落状态 | **轴基准与底板基准重合锁定** | **REMEDIATED** |
| **装配重构状态** | 未验证重构 | **`EditRebuild3` 执行返回 True，无重构冲突** | **REMEDIATED** |

---

## 二、装配体特征树实测节点

在真实 SolidWorks 2026 COM 中遍历 `remediated_assembly.SLDASM` 的特征树：
- 节点: `remediated_linear_base-1` (Component)
- 节点: `remediated_stepped_shaft-1` (Component)
- 节点: `remediated_circular_gear-1` (Component)
- 节点: `配合` (MateGroup)
  - 子项: `重合1` (MateCoincident)
