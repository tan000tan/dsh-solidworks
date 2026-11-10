# STAGE 04 第一轮独立核验器自身审计与反向测试报告
# AUDIT_ROUND2_VERIFIER_REVIEW.md

**审计项目：** `dsh-solidworks` DSH 插件  
**审计阶段：** STAGE 04 — CAD 核心建模能力 (核验器有效性审计)  
**审计对象：** 第一轮独立核验脚本 `tests/real_cad/audit_stage4_independent_verifier.py`  
**审计团队：** 第三方独立技术审计组  
**审计方法：** 代码逻辑漏洞审查 + 构造畸形输入的反向测试 (Adversarial Metamorphic Testing)  
**状态：** **BLIND SPOTS EXPOSED (核验器存在严重检测盲区，部分模型缺少理论值校验)**

---

## 一、核验器设计逻辑与断言审查

第一轮独立核验器（`audit_stage4_independent_verifier.py`）旨在绕过开发者的任务上下文，直接打开 `.SLDPRT` 文件抽取几何。但经过第二轮对其源代码与断言逻辑的严格审计，发现了以下结构性缺陷：

### 1.1 致命漏洞：Model B、D、G 的理论体积被置为 `None`
查看 `audit_stage4_independent_verifier.py` 第 56~88 行模型定义：
```python
{
    "id": "model_b",
    "name": "model_b_stepped_shaft.SLDPRT",
    "theory_vol": None,  # 约 113670 mm3
    "expected_bodies": 1,
    "expected_bbox_x": 150.0,
},
{
    "id": "model_d",
    "name": "model_d_bracket.SLDPRT",
    "theory_vol": None,
    "expected_bodies": 1,
},
{
    "id": "model_g",
    "name": "model_g_comprehensive.SLDPRT",
    "theory_vol": None,
    "expected_bodies": 1,
    "expected_bbox": [110.0, 68.0, 80.0],
}
```
再看判定逻辑（第 138 行）：
```python
if item["theory_vol"] is not None:
    rel_err = abs(vol_actual - item["theory_vol"]) / item["theory_vol"]
    if rel_err > 0.002:
        verdict = "FAIL"
```
**审计事实揭露：**
对于 Model B（阶梯轴）、Model D（支架）和 Model G（综合模型），**`theory_vol` 全部被设为了 `None`！**
这意味着：这三个最复杂的模型，在第一轮所谓的“独立几何核验”中，**根本没有执行任何体积数学解析核验！** 只要 SolidWorks 打开该零件能读出一个 Body，核验器就直接判定为 PASS！
这属于严重的断言形式化与虚假通过！

---

## 二、反向测试（Metamorphic Testing）与盲区实测

为了验证第一轮核验器的真实缺陷捕获能力，审计组进行了反向故障注入测试：

### 2.1 反向测试 1：孔位置发生严重偏离，核验器是否会报警？
- **构造畸形模型**：在 Model A（带孔矩形板）中，将原本应位于中心 $(0,0)$ 的贯通孔，人为移动至板边缘 $(35.0, 15.0)$；
- **几何物理事实**：
  - 由于孔径与板厚未变，模型的总体积严格不变（仍然为 $113,716.81\text{ mm}^3$）；
  - 外形包围盒尺寸严格不变（仍然为 $[100.0, 20.0, 60.0]\text{ mm}$）；
  - 实体数严格为 1；
- **核验器运行结果**：**判定为 100% PASS！**
- **盲区判定**：**核验器对特征的空间拓扑位置完全不敏感！孔打在任何位置，只要没切破边界，核验器全部误判为合格！**

### 2.2 反向测试 2：键槽异常剖开半轴，核验器是否报警？
- **现实事实**：在 Model B 中，键槽切削深度达到了 19mm（从轴心切穿了半边圆柱体）；
- **核验器运行结果**：由于 `theory_vol = None`，核验器只核查了 `shaft_length == 150.0mm` 与 `body_count == 1`，**直接判定为 PASS！**
- **盲区判定**：核验器无法识别深度异常与截面缺陷。

### 2.3 反向测试 3：局部倒角丢失，核验器是否报警？
- **构造场景**：在 Model B 轴端删除 $1.5\text{ mm} \times 45^\circ$ 倒角；
- **几何物理事实**：倒角体积仅约 $100\text{ mm}^3$（仅占总轴体积的 $0.08\%$）；
- **核验器表现**：因无理论体积比对，且轴长依然为 150mm，核验器完全无法感知倒角特征是否存在或丢失！

---

## 三、第一轮核验器审计对照表

| 审计维度 | 第一轮核验器设计状态 | 缺陷与风险分析 | 审计结论 |
| :--- | :--- | :--- | :---: |
| **断言有效性** | 仅覆盖了实体数和外轮廓包围盒 | 无法验证特征内部相对位置 | **POOR (低有效性)** |
| **预期值独立性** | 部分使用解析公式，部分直接为 None | Model B/D/G 缺少预期基准 | **FAIL (断言缺失)** |
| **异常检测能力** | 只能检测实体分裂 (Body Count > 1) | 对孔位偏移、截面变形完全失明 | **BLIND (大面积盲区)** |
| **反向测试表现** | 畸形孔位偏移被误判为 PASS | 存在显著假阳性率 | **FAIL (无法作为独立判据)** |

---

## 四、第二轮改进规范建议 (针对后续验收引擎)

第一轮核验器不能再作为第四阶段 CAD 能力合格的唯一独立判据。在后续阶段构建质量审查引擎时，必须引入：
1. **特征尺寸双向对比（Dimension Tree Audit）**：直接从模型中读取 `DisplayDimension` 与设计图纸参数严格比对，误差必须为 0；
2. **重心三维坐标（Center of Mass Vector）校核**：不仅比对体积，更要比对质心 $[X_c, Y_c, Z_c]$。一旦孔发生位置偏移，重心矢量会立刻改变，从而彻底消除“孔位错位盲区”；
3. **补齐所有模型的理论体积与表面积基准**：严禁出现 `theory_vol: None` 的偷懒做法。

---

## 五、核验器审计结论

**第一轮独立核验器自身存在严重的形式化断言与检测盲区，其给出的“100% 独立验证通过”结论具备高度虚高成分，不能直接作为第四阶段最终交付的合格证明！**
