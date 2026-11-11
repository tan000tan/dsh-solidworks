# 装配体配合特征深度独立审计报告 (06_ASSEMBLY_MATE_AUDIT.md)

**审计对象**: `audit/remediation-2026-11-06/cad_test_sandbox/remediated_assembly.SLDASM` (66,282 字节)  
**复核方法**: 真实 SolidWorks 2026 COM `MateGroup` 配合树遍历与关系反解  
**本项最终裁定**: **`PARTIALLY VERIFIED` (部分验证，缺失关键同轴约束)**

---

## 一、装配体组件树核实

通过 COM 接口核验 `remediated_assembly.SLDASM` 的实际组成：
- 组件 1: `remediated_linear_base-1` (底板零件，固定状态，作为世界坐标基准)
- 组件 2: `remediated_stepped_shaft-1` (阶梯轴零件，浮动状态)
- 组件 3: `remediated_circular_gear-1` (齿轮零件，浮动状态)
组件数量为 3，组件文件链接有效，无丢失零部件引用。

---

## 二、配合特征树 (MateGroup) 真实配合项审计

依据任务书最高要求：**重点确认是否同时满足合理的重合配合和同轴配合；如果只有一个重合配合，不得直接认定完整装配验收通过。**

在真实 SolidWorks COM 中遍历配合树节点，提取配合清单如下：

| 配合编号 | 配合名称 | 配合几何类型 | 引用实体 1 | 引用实体 2 | 状态 | 独立审计结论 |
| :---: | :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | `重合1` | **重合 (Coincident)** | `上视基准面@remediated_linear_base-1` | `前视基准面@remediated_stepped_shaft-1` | 求解正常 | **FOUND (平面重合)** |
| **2** | `重合2` | **重合 (Coincident)** | `上视基准面@remediated_stepped_shaft-1` | `前视基准面@remediated_circular_gear-1` | 求解正常 | **FOUND (平面重合)** |
| **--** | **同轴配合** | **同轴 (Concentric)** | **无** | **无** | **缺失** | **MISSING (严重缺失)** |

### 审计深度发现：
1. **配合总数夸大**: 整改方在 `ISS_DATABASE_REMEDIATED.json` 的 `ISS-REM-004` 中声明“验证配合数 >= 4 且无冲突”，但实测数据显示 `mate_count` 仅为 2。
2. **缺乏同轴约束**: 现有的两个配合均为基准面之间的重合配合（PLANE <-> PLANE）。轴与孔之间**完全没有施加同轴配合（Concentric Mate）**，导致轴与齿轮在径向自由度上完全未受约束，在实际机械工程中属于欠约束不合格装配体。
3. 按照“如果只有一个重合配合，不得直接认定完整装配验收通过”的严格判定准则，本项不能认定为完整通过。
