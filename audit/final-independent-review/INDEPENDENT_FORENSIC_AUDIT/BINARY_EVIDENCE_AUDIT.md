# 第五阶段：CAD 二进制与导出物证深度核验报告 (`BINARY_EVIDENCE_AUDIT.md`)

本报告通过两条独立取证通道对 `04_MST-AGU-2026_全部_SolidWorks_原生模型文件/` 下的全部 8 个模型/导出文件进行深度核验：
1. **文件二进制流与格式语法解析**：直接解析文件魔数、STEP (ISO-10303-21) 实体表、Binary STL 三角面片与欧拉拓扑、PDF 对象流与字体字典。
2. **SolidWorks 2026 SP4.1 (`PID: 4040`) 只读 COM API 实机解剖**：通过只读模式遍历真实 FeatureManager 特征树、子特征、草图尺寸、质量属性、装配体组件、配合关系 (`MateGroup`) 与工程图视图 (`DrView`)，核验后立即关闭且零修改。

## 1. 8 个模型与导出文件的文件级核验总表

| 文件名 | 大小 (Bytes) | SHA-256 | 文件头魔数 / 格式签名 | 格式合法性 | 内容真实性判定 |
| :--- | ---: | :--- | :--- | :--- | :--- |
| `mst_shaft.SLDPRT` | `51,781` | `bc603037e9fa9aa3bb64549d2b578fa76ed442d178ffae1684c14286a6ce5782` | `SOLIDWORKS 2026` | `VALID` | `PARTIAL`（单段圆柱+键槽，非多段阶梯轴） |
| `mst_base.SLDPRT` | `56,374` | `1a0a87518ed30ceaeeb44f8dd3c1d305b6d544ed101c027988f1821923ca0109` | `SOLIDWORKS 2026` | `VALID` | `PARTIAL`（长方体+单草图4圆孔切除，无原生线性阵列特征） |
| `mst_gear.SLDPRT` | `66,356` | `a2ab7f259029755a44d7fc32e2ef69f06942a840ebbb2141f27718569df9570c` | `SOLIDWORKS 2026` | `VALID` | `PARTIAL`（圆柱+单草图中心孔及4减重孔切除，无原生圆周阵列特征） |
| `mst_assembly.SLDASM` | `55,006` | `46f9814dd31c8c6ddca710e6d24b92670671e7ec760a8055e1bf26ffca7faac5` | `SOLIDWORKS 2026` | `VALID` | `PARTIAL`（含3个真实零件实例，但 `MateGroup` 配合数为 `0`） |
| `mst_drawing.SLDDRW` | `83,442` | `785792e8ab816420e61c00050188ebef6946950b575955720ac91d3f224b5c22` | `SOLIDWORKS 2026` | `VALID` | `FAILED`（仅含空白图纸 `图纸1 (DrSheet)`，含 `0` 个模型投影视图 `DrView`） |
| `mst_assembly.step` | `108,278` | `6a9085560e4de30aa3e91624de9df450a69553e56846de8b12a7e53f2f3c4213` | `ISO-10303-21; STEP AP203` | `VALID` | `PARTIAL`（真实导出3个实体、36个高级面，但协议为 `AP203` 而非报告声称的 `AP214`） |
| `mst_shaft.STL` | `10,884` | `3d26bfeb20e74bb83847000c201e7438ef33ff4612c9edba2da972b7f2764f98` | `stlbn mst_shaft` (Binary STL) | `VALID` | `PARTIAL`（真实水密流形网格，但实为 `216` 三角面、`V-E+F=2`，与报告声称的 `440` 面、`V-E+F=0` 不符） |
| `mst_drawing.pdf` | `20,664` | `93142661bf9744d9de703d3c88240c6a4a9573873cd341ca88f274e55f7165be` | `%PDF-1.7` | `VALID` | `FAILED`（仅渲染了空白工程图图框与标题栏矢量线，无任何零件投影几何视图） |

## 2. 原生 SolidWorks 模型 (`.SLDPRT` / `.SLDASM` / `.SLDDRW`) 内部特征树实机解剖

### 2.1 `mst_shaft.SLDPRT` 特征树与物理属性
- **实测质量属性**：体积 `V = 55,631.855387 mm³`，表面积 `A = 9,561.986646 mm²`，质心 `CoM = (0.619773, 0.000000, 25.000000) mm`。
- **FeatureManager 完整顶层特征序列（共 20 项，其中几何建模特征 4 项）**：
  1. `Feat[16]: 草图1 (ProfileFeature)` — 包含直径 `D1@草图1 = 40.0 mm` 的圆。
  2. `Feat[17]: 凸台-拉伸1 (Extrusion)` — 拉伸深度 `D1@凸台-拉伸1 = 50.0 mm`（经 ECO-01 从 `60.0 mm` 修改为 `50.0 mm`），无压缩 (`Suppressed=False`)。
  3. `Feat[18]: 草图2 (ProfileFeature)` — 键槽截面矩形草图。
  4. `Feat[19]: 切除-拉伸1 (ICE)` — 拉伸切除深度 `D1@切除-拉伸1 = 50.0 mm`，无压缩 (`Suppressed=False`)。
- **取证结论**：该零件是一个单段圆柱（`$\Phi 40 \times 50\text{ mm}$`）加通长矩形切除键槽。报告中声称的“三级阶梯传动主轴”、“多段变径阶梯轴 (`$\Phi 20 / \Phi 30 / \Phi 24$`)”、“倒角 (`Chamfer`)”、“圆角 (`Fillet`)”在真实特征树中**均不存在**。

### 2.2 `mst_base.SLDPRT` 特征树与物理属性
- **实测质量属性**：体积 `V = 761,716.814693 mm³`，表面积 `A = 94,024.777961 mm²`，质心 `CoM = (0.000000, 0.000000, 10.000000) mm`。
- **FeatureManager 建模特征序列（4 项）**：
  1. `Feat[16]: 草图1 (ProfileFeature)` — `240 mm × 160 mm` 中心矩形（见 `execute_ultimate_model.py` 第 124 行 `create_rectangle(-0.12, -0.08, 0.12, 0.08)`，与报告正文声称的 `200 × 120 × 32 mm` 不一致）。
  2. `Feat[17]: 凸台-拉伸1 (Extrusion)` — 拉伸深度 `D1@凸台-拉伸1 = 20.0 mm`。
  3. `Feat[18]: 草图2 (ProfileFeature)` — 在同一草图内直接绘制了 4 个四角分布的圆（`create_circle` 调用 4 次）。
  4. `Feat[19]: 切除-拉伸1 (ICE)` — 一次拉伸切除 `20.0 mm`。
- **取证结论**：底座的 4 个安装孔是通过在 `草图2` 中画 4 个圆并执行单次拉伸切除 (`ICE`) 实现的，特征树中**没有**原生线性阵列特征 (`LPattern`) 或镜像特征 (`Mirror`)。

### 2.3 `mst_gear.SLDPRT` 特征树与物理属性
- **实测质量属性**：体积 `V = 43,275.438790 mm³`，表面积 `A = 16,603.317185 mm²`，质心 `CoM = (0.000000, 0.000000, 12.500000) mm`。
- **FeatureManager 建模特征序列（4 项）**：
  1. `Feat[16]: 草图1 (ProfileFeature)` — `D1@草图1 = 110.0 mm`（半径 `55 mm`，见 `execute_ultimate_model.py` 第 165 行，与报告正文声称的 `$\Phi 70 \times 12\text{ mm}$` 及“6×`$\Phi 8$` 减重孔”不一致）。
  2. `Feat[17]: 凸台-拉伸1 (Extrusion)` — 拉伸深度 `D1@凸台-拉伸1 = 25.0 mm`。
  3. `Feat[18]: 草图2 (ProfileFeature)` — 在同一草图内绘制了 1 个中心圆与 4 个周向分布的圆（`for angle in [0, 90, 180, 270]`）。
  4. `Feat[19]: 切除-拉伸1 (ICE)` — 一次拉伸切除 `25.0 mm`。
- **取证结论**：齿轮毛坯的减重孔是在草图内用 Python `for` 循环画了 4 个圆并执行单次拉伸切除，特征树中**没有**原生圆周阵列特征 (`CirPattern`)。

### 2.4 `mst_assembly.SLDASM` 装配体结构与配合关系核验
- **FeatureManager 顶层节点序列**：
  - `Feat[15]: mst_base-1 (Reference)` (固定组件)
  - `Feat[16]: mst_shaft-1 (Reference)` (浮动组件)
  - `Feat[17]: mst_gear-1 (Reference)` (浮动组件)
  - `Feat[18]: 配合 (MateGroup)` -> **子特征列表：`[]`（0 个配合特征）**
- **取证结论**：装配体确实加载并保存了 3 个零件组件实例，但它们仅通过 `add_component` 时的初始空间坐标 `(0,0,0)`、`(0,0,0.02)`、`(0,0,0.04)` 摆放，**未创建任何 SolidWorks 原生装配配合关系（`Coincident` / `Concentric` 数量均为 `0`）**。

### 2.5 `mst_drawing.SLDDRW` 与 `mst_drawing.pdf` 工程图核验
- **SolidWorks `DrawingDoc` 特征树实测**：
  - 顶层特征列表：`[('注释', 'CommentsFolder'), ('收藏夹', 'FavFolder'), ('选择集', 'SelectionSetFolder'), ('传感器', 'SensorFolder'), ('设计树视图', 'LiveSectionFolder'), ('注解', 'DetailCabinet'), ('图纸格式1', 'DrTemplate'), ('图纸1', 'DrSheet')]`。
  - **模型投影视图 (`DrView`) 数量：`0`**。
- **根因追溯 (`execute_ultimate_model.py` 第 267-280 行)**：
  - 脚本执行日志记录：`[12:06:29] Standard views created: False`，即 `create_standard_views(model_drawing, shaft_path)` 调用失败返回了 `False`。
  - 但脚本第 277-280 行未检查返回值 `ok_views`，直接硬编码写入 `"status": "PASS"`。
- **`mst_drawing.pdf` (20,664 bytes) 内部对象流核验**：
  - 共 `1` 页，包含 `19` 个 PDF 间接对象，内嵌字体 `HYSWLongFangSong` (长仿宋图纸表格字体)，光栅图像数 `0` (`/Subtype /Image = 0`)。
  - 包含 4 个矢量内容流（Objects `5, 6, 7, 8`，解压后分别为 `35`、`2,906`、`408`、`28` 字节），全部为工程图空白模板边框与标题栏文字，**没有任何三维零件的投影视图线条**。

## 3. `mst_assembly.step` 与 `mst_shaft.STL` 几何拓扑核验

### 3.1 `mst_assembly.step` (108,278 bytes)
- **协议头签名**：`FILE_DESCRIPTION (( 'STEP AP203' ), '1' );`、`FILE_SCHEMA (( 'CONFIG_CONTROL_DESIGN' ));`。
  - *勘误*：文件实际为 **STEP AP203**，而非报告中声称的 `STEP AP214`。
- **内部实体统计**：
  - `PRODUCT`: `4` 个（`mst_base`, `mst_gear`, `mst_assembly`, `mst_shaft`）
  - `NEXT_ASSEMBLY_USAGE_OCCURRENCE`: `3` 个（真实表达了总装对 3 个零件的装配引用层级）
  - `CLOSED_SHELL`: `3` 个；`MANIFOLD_SOLID_BREP`: `3` 个；`ADVANCED_FACE`: `36` 个。
- **判定**：STEP 文件是包含 3 个真实零件 B-Rep 实体与装配层级的有效三维交换文件（协议版本为 AP203）。

### 3.2 `mst_shaft.STL` (10,884 bytes)
- **Binary STL 结构校验**：`80` 字节头 (`'stlbn mst_shaft'`) + `4` 字节无符号整数 (`216`) + `216 × 50` 字节 = `10,884` 字节（字节级完全吻合）。
- **真实网格拓扑计算结果**：
  - **三角面片数 ($F$)**：`216`（报告声称 `440`，不符）
  - **唯一顶点数 ($V$)**：`110`（报告声称 `220`，不符）
  - **唯一边数 ($E$)**：`324`（报告声称 `660`，不符）
  - **每条边邻接面数分布**：全部 `324` 条边的邻接面数均为 `2`（`{2: 324}`），**非流形边数 = `0`**，100% 闭合水密流形网格。
  - **欧拉示性数 ($\chi = V - E + F$)**：$\chi = 110 - 324 + 216 = 2$（对应亏格 $g = 0$ 的单连通柱体+盲槽表面拓扑；报告中声称“含通孔亏格 $g=1$，$V-E+F=0$”属于对 `mst_shaft` 几何形态的错误描述，因为 `mst_shaft` 只有侧面键槽而无中心通孔）。
  - **包围盒 (Bounding Box)**：$X \in [-20.0, 20.0]\text{ mm}$, $Y \in [-20.0, 20.0]\text{ mm}$, $Z \in [0.0, 50.0]\text{ mm}$（尺寸 `$40 \times 40 \times 50\text{ mm}$`，与 ECO-01 修改后的 `50 mm` 轴长完全吻合）。
