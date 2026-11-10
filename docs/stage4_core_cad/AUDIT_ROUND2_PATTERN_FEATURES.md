# STAGE 04 第二轮圆周阵列与镜像特征专项审计报告
# AUDIT_ROUND2_PATTERN_FEATURES.md

**审计项目：** `dsh-solidworks` DSH 插件  
**审计阶段：** STAGE 04 — CAD 核心建模能力 (阵列与镜像专项核查)  
**审计团队：** 第三方独立技术审计组  
**审计重点：** 特征级圆周阵列与特征级镜像的 API 真实性、选择集 Mark 规则、多语言适配与实机物证  
**状态：** **AUDITED & GAP EXPOSED (圆周阵列底层可用但工作流绕开；镜像特征存在严重 API 传参错误导致崩溃)**

---

## 一、审计背景与核心分歧

在第一轮审计与开发报告中，Model C（法兰盘）声称验证了“圆周阵列”，Model D/G 声称验证了“对称镜像”。
然而第二轮审查发现：
- Model C 实际上是在一个草图中计算三角函数画了 6 个圆，然后一次性拉伸切除；
- Model D/G 实际上是利用基准面执行“两侧等距对称拉伸（Midplane Extrusion）”；
- **两者均没有调用 SolidWorks 原生的特征级圆周阵列（`FeatureCircularPattern`）和特征级镜像（`InsertMirrorFeature2`）！**

本报告针对这两个核心高级特征的真实代码实现与实机可执行性进行深挖。

---

## 二、特征级圆周阵列 (Circular Pattern) 深度审计

### 2.1 代码实现与 API 规范审查
- **代码位置**：`vendor/solidworks-automation-skill/scripts/sw_pattern.py:circular_pattern`
- **底层 API**：`model.FeatureManager.FeatureCircularPattern4`
- **参数签名**：
  `FeatureCircularPattern4(count, angle, False, "", False, equal_spacing, False)`
- **母特征与旋转轴选择机制**：
  - 母特征（Seed Feature）：通过 `_seed(model, feature_name)` 选择，使用 `Select2(False, 4)` 施加 Mark = 4；
  - 旋转轴（Axis）：支持轴名称字符串（`SelectByID2(axis, "AXIS", ...)`）或圆柱面几何实体（`Select4(append, data)`，Mark = 1）。

### 2.2 隔离沙箱实机实测验证（`verify_pattern_mirror.py`）
在独立测试零件中，创建圆柱盘并在 $R=30\text{ mm}$ 处打一个偏心通孔（`切除-拉伸1`），拾取外圆柱面为旋转轴，执行 `circular_pattern(part, "切除-拉伸1", cyl_face, 2*pi, 4, equal_spacing=True)`：
- **实测结果**：
  - SolidWorks 成功生成原生特征：`阵列(圆周)1`；
  - 实测模型体积：`113,097.34 mm³`；
  - 理论数学解析体积：$V = \pi \times 50^2 \times 15 - 4 \times (\pi \times 5^2 \times 15) = 113,097.3355\text{ mm}^3$；
  - **实测相对误差**：`2.33e-07`（完全精确吻合）；
  - 特征树检查：在特征树中真实存在独立的 `CirPattern` 特征节点，修改母特征孔径时 4 个孔全部正确联动。

### 2.3 结论与工作流断层分析
- **能力判定**：**代码已实现底层官方 API，实机调用能够成功生成特征级圆周阵列（E4 级）**；
- **缺陷与 Gap**：
  1. 为什么在 Model C 中不用？因为该函数要求调用者必须显式传入一个 `axis`（轴或圆柱面 COM 对象）。如果上层调用者没有提取圆柱面对象，或者模型上只有点而没有回转轴，该接口就会抛出 `无法选择圆周阵列轴`；
  2. 开发者在 Model C 中为了图省事，绕开了该工具，改用草图画 6 个圆替代；
  3. 导致 DSH Agent 在没有辅助工具帮助其定位“回转轴对象”时，很难独立成功发起圆周阵列。

---

## 三、特征级镜像 (Mirror Feature) 深度审计

### 3.1 代码实现与致命缺陷溯源
- **代码位置**：`vendor/solidworks-automation-skill/scripts/sw_part.py:mirror_feature`
- **源码审查**：
  ```python
  def mirror_feature(model, feature_name, mirror_plane_name):
      _select_by_id(model.Extension, feature_name, "BODYFEATURE", mark=4)
      _select_by_id(model.Extension, mirror_plane_name, "PLANE", append=True, mark=1)
      return model.FeatureManager.InsertMirrorFeature2(False, False, False, False, 0)
  ```

### 3.2 致命缺陷 1：选择集 Mark 传参严重违背官方规范
根据 SolidWorks 官方 API 文档（`IFeatureManager::InsertMirrorFeature2`）：
- **Mark = 1**：镜像基准面或平坦面（Mirror Face/Plane）；
- **Mark = 2**：被镜像的特征（Features to Mirror）；
- **Mark = 4**：被镜像的实体（Bodies to Mirror，用于多实体零件整体镜像）；
- **Mark = 8**：被镜像的面（Faces to Mirror）。
**审查发现：** 代码第 858 行将特征选择标记为了 `mark=4`！
这意味着系统告诉 SolidWorks：“我要把一个叫‘切除-拉伸1’的实体当作 Body 进行实体镜像”，由于“切除-拉伸1”是一个 Feature 而不是 Solid Body，SolidWorks 内部选择集解析直接失效！

### 3.3 致命缺陷 2：多语言基准面别名未解析导致选择直接返回 False
在中文版 SolidWorks 环境中：
- 默认三大基准面名称为：`前视基准面`, `上视基准面`, `右视基准面`；
- 当调用 `mirror_feature(part, "切除-拉伸1", "Right Plane")` 时：
  - `_select_by_id(model.Extension, "Right Plane", "PLANE", append=True, mark=1)` 直接在底层调用 `SelectByID2("Right Plane", "PLANE", ...)`；
  - **实测返回值：`False`！**
  - 因为模型中根本不存在叫 `"Right Plane"` 的基准面！
  - 镜像基准面未被选中（Mark 1 为空），特征 Mark 又传错为 4，导致 `InsertMirrorFeature2` 返回 `None`！

### 3.4 隔离沙箱实机实测崩溃现场（`verify_pattern_mirror.py`）
- **测试动作**：在长方体板上打孔，调用 `mirror_feature` 镜像该孔；
- **控制台输出**：
  ```
  [B] 特征级镜像 (InsertMirrorFeature2) 测试:
    1. 基底板创建成功
    2. 单侧孔创建成功: 切除-拉伸1
    3. 正在尝试特征级镜像 (关于 Right Plane 镜像 切除-拉伸1)...
    -> 镜像执行失败: 'NoneType' object has no attribute 'Name'
    [物理实测] 体积: 88821.90 mm3 (理论: 87643.81 mm3, 差值: 1178.10)
  ```
- **现场实测**：镜像特征生成彻底失败，返回值是 `None`，实测体积只包含单侧孔（缺少镜像孔，差值严格为 1178 mm³）。

---

## 四、未完成内容与修复建议清单 (只读记录，严禁自行修改)

针对审计发现，登记以下未完成内容及后续修复建议：

1. **[DEFECT-MIRROR-01 | CRITICAL] 修正 `mirror_feature` 的选择集 Mark**：
   - 必须将 `_select_by_id(model.Extension, feature_name, "BODYFEATURE", mark=4)` 修改为 `mark=2`；
   - 增加支持实体镜像的分支：如果用户指定镜像整个实体，才使用 `mark=4`。
2. **[DEFECT-MIRROR-02 | HIGH] 接入多语言基准面别名解析器**：
   - 在选择 `mirror_plane_name` 时，不能直接使用传入的裸字符串，必须复用 `_get_plane_name_candidates(mirror_plane_name)` 遍历候选集（如 `["Right Plane", "右视基准面", "Right"]`），确保在中文版 SolidWorks 下能成功选中 Mark 1。
3. **[DEFECT-PATTERN-01 | MEDIUM] 增强圆周阵列旋转轴的智能推断**：
   - 当调用 `circular_pattern` 时，如果母特征依托于圆柱体，系统应能自动拾取母体外圆柱面作为回转参考轴，使 Agent 在自然语言规划时无需繁琐地指定底层 COM 面对象。

---

## 五、专项审计结论

- **特征级圆周阵列**：底层 API 实现正确且实机调用有效（E4 级），但主基准套件中因轴对象选择门槛被绕开；
- **特征级镜像**：**存在严重代码缺陷（Mark 传错 + 中文基准面选择失败），实机运行 100% 报错崩塌，第一轮宣称“已实现”严重失实，本项判定为 FAIL**。
