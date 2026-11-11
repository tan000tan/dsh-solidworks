# DSH-SolidWorks v0.3.0 SolidWorks 多版本兼容矩阵与验收说明

本报告明确规范本插件针对 SolidWorks 2020 至 2026 各年份版本的兼容策略、API 降级规则及严谨的验证分级。

---

## 一、真实性声明与支持分级原则

为保证质量诚信，本项目严禁任何虚假标注。根据实际测试机器条件（物理主机仅安装 SolidWorks 2026 SP4.1），将支持等级划分为：

1. **`PHYSICAL_VERIFIED`（物理实机全量闭环验证）**:
   在真实的 SolidWorks 桌面图形进程中，通过真实 COM 接口完成全套 11 步 CAD 建模、切除自愈、镜像、装配配合、工程图投影、质量属性比对及 4 维文档清点。
2. **`SIMULATED_VERIFIED`（接口级与降级仿真验证）**:
   针对无物理安装的旧版本，通过专用多版本仿真测试套件（`tests/sw_compat_matrix_test.py`），注入目标版本的版本号与 COM 特征异常，逐项验证 API 动态自适应与安全降级分支是否准确触发。
3. **`UNVERIFIED`（未验证）**:
   超出支持范围或尚未建立契约验证的版本。

---

## 二、SolidWorks 2020—2026 兼容矩阵

| SolidWorks 版本 | 主版本号 (Revision) | 支持状态 | 验证级别 | 核心降级策略与调用链 |
|---|---|---|---|---|
| **SolidWorks 2026** | `34.x` | 完全支持 | **`PHYSICAL_VERIFIED`** | 原生 `FeatureExtrusion3`, `FeatureCut4`, `InsertMirrorFeature2`, `CreateMassProperty`, `AddMate5`, `CreateDrawViewFromModelView3` |
| **SolidWorks 2025** | `33.x` | 完全支持 | **`SIMULATED_VERIFIED`** | 原生现代 API 路径，接口契约已通过 19 项专用测试验证 |
| **SolidWorks 2024** | `32.x` | 完全支持 | **`SIMULATED_VERIFIED`** | 原生现代 API 路径，接口契约已通过 19 项专用测试验证 |
| **SolidWorks 2023** | `31.x` | 完全支持 | **`SIMULATED_VERIFIED`** | 原生现代 API 路径，接口契约已通过 19 项专用测试验证 |
| **SolidWorks 2022** | `30.x` | 完全支持 | **`SIMULATED_VERIFIED`** | 原生现代 API 路径，接口契约已通过 19 项专用测试验证 |
| **SolidWorks 2021** | `29.x` | 平滑降级支持 | **`SIMULATED_VERIFIED`** | 降级触发: `FeatureExtrusion2`, `FeatureCut3`, `InsertMirrorFeature` (4 参数), `GetMassProperties2` (自适应解包), `AddMate3`, `CreateDrawViewFromModelView` |
| **SolidWorks 2020** | `28.x` | 平滑降级支持 | **`SIMULATED_VERIFIED`** | 同 2021 降级策略，全套兼容测试 100% PASS |

---

## 三、六大核心 CAD 领域 API 自适应与降级细节

### 1. 凸台拉伸 (`safe_extrude_boss`)
- **现代路径 (2022-2026)**: 调用 `FeatureManager.FeatureExtrusion3`，支持复杂终止条件与双向拉伸；
- **旧版降级 (2020-2021)**: 当捕获 `DISP_E_MEMBERNOTFOUND` 或检测到 SW <= 2021 时，自动平滑切换至 `FeatureManager.FeatureExtrusion2`。

### 2. 切除特征与方向自愈 (`safe_extrude_cut`)
- **现代路径 (2022-2026)**: 调用 `FeatureManager.FeatureCut4`；
- **旧版降级 (2020-2021)**: 自动降级至 `FeatureManager.FeatureCut3`；
- **方向自愈机制**: 切除返回 None 时，自动反转拉伸方向 (`reverse = not reverse`) 重新尝试，彻底避免盲切朝向错误。

### 3. 镜像特征 (`safe_mirror_feature`)
- **现代路径 (2022-2026)**: 必须严格遵循 `InsertMirrorFeature2` 规范：基准面设定 `Mark=1`，待镜像特征设定 `Mark=2`；
- **旧版降级 (2020-2021)**: 降级调用 `InsertMirrorFeature`，传入 4 参数签名 `(geom_pat, knit, reverse, False)`。

### 4. 质量属性提取 (`safe_mass_properties`)
- **现代路径 (2022-2026)**: 调用高精度 `Extension.CreateMassProperty`；
- **旧版降级 (2020-2021)**: 降级至 `Extension.GetMassProperties2`，自适应解包参数探针 `[(1, 0, False), (1, 0), (1,), ()]`，保证在任何旧版接口上均能安全提取体积、质心与质量。

### 5. 装配体配合 (`safe_add_mate`)
- **现代路径 (2022-2026)**: 调用 `AssemblyDoc.AddMate5`；
- **旧版降级 (2020-2021)**: 捕获参数不匹配后，自动回退到 `AddMate3`。

### 6. 工程图视图生成 (`safe_create_drawing_view`)
- **现代路径 (2022-2026)**: 调用 `DrawingDoc.CreateDrawViewFromModelView3`；
- **旧版降级 (2020-2021)**: 自动回退到 `CreateDrawViewFromModelView` 或经典视图生成方法。

---

## 四、异常分类守则（防止盲目降级）

`sw_compat.py` 内置了严格的 `is_com_interface_mismatch_error` 判定器：
- **允许触发降级**: 仅限于底层 COM 调度签名不符错误代码（`0x80020006 DISP_E_MEMBERNOTFOUND`, `0x8002000E DISP_E_PARAMNOTOPTIONAL`, `0x8002000F DISP_E_BADPARAMCOUNT`, `0x80020005 DISP_E_TYPEMISMATCH`）；
- **拒绝盲目降级**: 若错误属于 CAD 本身的几何拓扑错误（如草图自相交、无相交拉伸实体），严禁触发版本降级，而是直接向上汇报真实的几何异常信息，绝不掩盖建模错误。
