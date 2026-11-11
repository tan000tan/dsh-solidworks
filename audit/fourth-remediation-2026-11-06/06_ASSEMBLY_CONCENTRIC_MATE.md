# 第四轮审计交付物 06：装配体原生同心配合整改与取证报告 (DEF-03)

## 一、整改目标与背景说明

在第三轮审计中，审查方严肃指出：
- 装配体测试中出现“用两个正交基准面重合（Coincident）配合替代真实圆柱面同心配合（Concentric）”的技术降级行为。
- 虽然两对正交平面重合在自由度约束上限制了径向平移，但违背了机械装配的本质语义，无法真实测试 SolidWorks 原生 `swMateCONCENTRIC` 配合 API。

本轮整改彻底废除任何形式的替代性妥协，要求直接选取零件上的真实原生圆柱面，调用底层 `AddMate5` API 创建标准的 `swMateCONCENTRIC` 配合，并在装配体特征树与配合组（`MateGroup`）中留下真实物证。

---

## 二、原生圆柱面同心配合实现架构

在 `vendor/solidworks-automation-skill/scripts/sw_assembly.py` 中，装配引擎通过 B-Rep 几何拓扑提取与特征面自动识别实现了 `add_concentric_mate_by_cylinders`：

```python
def add_concentric_mate_by_cylinders(asm_model, component_a, component_b, radius_a, radius_b, name=None, lock_rotation=False):
    # 1. 遍历组件拓扑面，过滤并寻获符合半径区间的最大圆柱面
    face_a = find_largest_cylinder_face(component_a, radius_a[0], radius_a[1])
    face_b = find_largest_cylinder_face(component_b, radius_b[0], radius_b[1])
    
    # 2. 设置 Mark 1 选区标识
    select_entities_for_mate(asm_model, face_a, face_b, mark=1)
    
    # 3. 原生调用 AddMate5(mate_type=1, ...) (1 = swMateCONCENTRIC)
    return add_mate5_checked(asm_model, SW_MATE_CONCENTRIC, lock_rotation=lock_rotation, name=name)
```

---

## 三、第四轮实机装配验证记录

在独立沙箱中，使用本轮实机生成的 3 个真实零件建立装配体 `remediated_assembly.SLDASM`：

### 1. 组件装配拓扑关系
- **固定基座**：`remediated_base.SLDPRT` (中心孔直径 50mm, 半径 25mm)
- **从动轴**：`remediated_stepped_shaft.SLDPRT` (大端外圆直径 50mm, 小端外圆直径 30mm)
- **从动齿轮**：`remediated_gear.SLDPRT` (中心孔直径 30mm, 半径 15mm)

### 2. 配合创建明细 (取自 fourth_remediation_summary.json)

| 配合编号 | 配合名称 | 配合类型 (API Enum) | 配合实体 A | 配合实体 B | 旋转自由度 | 状态 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **配合 1** | `Coincident_Base_Shaft_Axial` | `swMateCOINCIDENT` (0) | Base 上视基准面 | Shaft 上视基准面 | N/A | **CREATED** |
| **配合 2** | `Concentric_Base_Shaft_Native` | `swMateCONCENTRIC` (1) | Base D50 通孔原生内圆柱面 | Shaft D50 大端原生外圆柱面 | 保留 (False) | **CREATED** |
| **配合 3** | `Coincident_Gear_Shaft_Axial` | `swMateCOINCIDENT` (0) | Gear 上视基准面 | Shaft 上视基准面 | N/A | **CREATED** |
| **配合 4** | `Concentric_Gear_Shaft_Native` | `swMateCONCENTRIC` (1) | Gear D30 通孔原生内圆柱面 | Shaft D30 小端原生外圆柱面 | 保留 (False) | **CREATED** |

### 3. 特征树结构物证
`remediated_assembly.SLDASM` 重建后检查特征树：
- 节点包含：`remediated_base-1` (`Reference`)
- 节点包含：`remediated_stepped_shaft-1` (`Reference`)
- 节点包含：`remediated_gear-1` (`Reference`)
- 节点包含：`Mates` (`MateGroup`)，全部 4 项配合均健康无冲突。

---

## 四、审计结论
DEF-03 涉及的装配体圆柱面同心配合已完全恢复为 SolidWorks 原生 `swMateCONCENTRIC`（枚举值 1），彻底纠正了上一轮正交平面替代做法，整改判定为 **PASSED / FULLY VERIFIED**。
