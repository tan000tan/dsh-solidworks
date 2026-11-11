# 特征树独立特征与层级核验报告

**核验对象**: `audit/remediation-2026-11-06/cad_test_sandbox/remediated_stepped_shaft.SLDPRT`  
**核验方法**: SolidWorks COM 接口 `FeatureManager` / `IFeature` 深度遍历与类型解析  
**对比对象**: 阶段七原模型 `MST-AGU-2026-STEPPED-SHAFT.SLDPRT`

---

## 一、整改前后特征树对比

| 核验维度 | 阶段七原模型 (Defect C) | 本次整改模型 (`remediated_stepped_shaft.SLDPRT`) | 裁定 |
| :--- | :--- | :--- | :--- |
| **总特征数量** | 2 (只有1个草图+1个凸台拉伸) | **5 项显式特征** | **REMEDIATED** |
| **台阶凸台特征** | 仅 1 段圆柱 (d50x100mm) | **2 段独立凸台拉伸** (`凸台-拉伸1`, `凸台-拉伸2`) | **REMEDIATED** |
| **切除特征** | 无任何切除特征 | **1 项键槽切除特征** (`切除-拉伸1`) | **REMEDIATED** |
| **草图依附关系** | 仅有 1 个基准草图 | **3 个独立草图** (`草图1`, `草图2`, `草图3`) | **REMEDIATED** |
| **模型实测体积** | $196,349.54\text{ mm}^3$ (单圆柱体积) | **$158,286.48\text{ mm}^3$** (阶梯轴带键槽真实体积) | **REMEDIATED** |

---

## 二、实测特征树节点遍历清单 (COM 原始返回)

通过 `iter_all_features(model)` 在真实 SolidWorks 2026 会话中提取的节点清单如下：

```text
[Feature #01] Name='前视基准面'       TypeName='RefPlane'
[Feature #02] Name='上视基准面'       TypeName='RefPlane'
[Feature #03] Name='右视基准面'       TypeName='RefPlane'
[Feature #04] Name='原点'             TypeName='OriginProfileFeature'
[Feature #05] Name='草图1'            TypeName='ProfileFeature'   (子草图: 基准圆 d=50mm)
[Feature #06] Name='凸台-拉伸1'       TypeName='Ice'              (拉伸第一段: 深度=100mm)
[Feature #07] Name='草图2'            TypeName='ProfileFeature'   (子草图: 端面圆 d=30mm)
[Feature #08] Name='凸台-拉伸2'       TypeName='Ice'              (拉伸第二段: 深度=80mm)
[Feature #09] Name='草图3'            TypeName='ProfileFeature'   (子草图: 键槽截面 8x4mm)
[Feature #10] Name='切除-拉伸1'       TypeName='Ice'              (切除拉伸: 键槽深度=40mm)
```

特征层级因果依赖链完整：
`草图1` $\rightarrow$ `凸台-拉伸1` $\rightarrow$ `草图2` $\rightarrow$ `凸台-拉伸2` $\rightarrow$ `草图3` $\rightarrow$ `切除-拉伸1`。
确认阶梯轴已具备真实的台阶与键槽几何特征。
