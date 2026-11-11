# 阶梯轴、阵列与复杂特征特征树深度独立审计报告 (05_FEATURE_TREE_AUDIT.md)

**审计对象**:
1. `audit/remediation-2026-11-06/cad_test_sandbox/remediated_stepped_shaft.SLDPRT` (94,948 字节)
2. `audit/remediation-2026-11-06/cad_test_sandbox/remediated_linear_base.SLDPRT` (66,060 字节)
3. `audit/remediation-2026-11-06/cad_test_sandbox/remediated_circular_gear.SLDPRT` (74,463 字节)
**本项最终裁定**: **`PARTIALLY VERIFIED` (部分验证，原生高级特征全军覆没)**

---

## 一、阶梯轴尺寸与特征树失真剖析 (Defect C)

### 1. 报告声称与实际物理尺寸对比
整改方在报告 `07_FEATURE_TREE_VERIFICATION.md` 中声称：
> “凸台-拉伸1: 深度=100mm, 直径=d50；凸台-拉伸2: 深度=80mm, 直径=d30，因果依赖链完整，总长 180mm。”

**独立物理实测结果揭露严重虚标**：
对 `remediated_stepped_shaft.STL` 网格和 `run_all_remediation_cad.py` 源码逆向解析：
- **实际构建代码**：
  - `草图1` (Front Plane): 半径 25mm (直径 50mm) -> 拉伸 60mm (Z 从 0 到 60mm)
  - `草图2` (同为 Front Plane!): 半径 18mm (直径 36mm) -> 拉伸 100mm (Z 从 0 到 100mm)
  - `草图3` (Top Plane): 截面切除深度 4mm，长度 25mm
- **实际空间几何形态**：
  第二段拉伸并没有建立在第一段的端面上，而是从同一个基准面（Front Plane）以同心圆向同一方向拉伸！导致 0~60mm 的小圆柱被完全包裹在大圆柱内部，只有 60~100mm 的 40mm 突出在外！
- **STL 实体包围盒实测**：
  - X: `[0.00, 50.00]` (跨度 50.00mm)
  - Y: `[0.06, 49.94]` (跨度 49.88mm)
  - Z: `[0.00, 100.00]` (跨度 **100.00mm**，绝非声称的 180mm！)

---

## 二、原生高级特征专项核验清单

依据任务书最高要求：**单独核验原生线性阵列 LPattern、圆周阵列 CirPattern、镜像特征、倒角、圆角；不能把草图画多个圆误认为原生阵列；若原生阵列未实现，明确列为未通过项。**

| 高级特征类型 | 原生 SolidWorks 特征类型 | 对应零件 | 实测特征树是否存在该节点 | 独立审计结论 |
| :--- | :--- | :--- | :---: | :--- |
| **原生线性阵列** | `LPattern` | `remediated_linear_base.SLDPRT` | **无** (`has_lpattern: false`) | **UNIMPLEMENTED (未实现)** |
| **原生圆周阵列** | `CirPattern` | `remediated_circular_gear.SLDPRT` | **无** (`has_cirpattern: false`) | **UNIMPLEMENTED (未实现)** |
| **原生镜像特征** | `MirrorSolid` / `MirrorFeature` | 所有零件 | **无** | **UNIMPLEMENTED (未实现)** |
| **原生倒角特征** | `Chamfer` | `remediated_stepped_shaft.SLDPRT` | **无** | **UNIMPLEMENTED (未实现)** |
| **原生圆角特征** | `Fillet` | `remediated_stepped_shaft.SLDPRT` | **无** | **UNIMPLEMENTED (未实现)** |

### 事实裁定：
整改方在底层虽然实现了基础的草图拉伸与切除，但在复杂特征树层面，**原生阵列（线性/圆周）、镜像、倒角与圆角等 5 大关键工程特征全部未能在实机模型中成功生成**。依据“若原生阵列目前尚未实现，明确列为未通过项，不得因为其他建模功能成功而整体判定通过”的准则，本项判定为 **`PARTIALLY VERIFIED`**。
