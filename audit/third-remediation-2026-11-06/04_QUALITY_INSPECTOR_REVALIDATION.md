# 质量检验器防御机制与数据溯源复核报告 (04_QUALITY_INSPECTOR_REVALIDATION.md)

**执行主体**: dsh-solidworks 第三轮整改验收团队  
**核心源码**: `docs/stage5_advanced_ai_cad/scripts/cad_quality_inspector.py`  
**专项单测**: `tests/remediation_cad_quality_inspector_test.py`  
**复核时间**: 2026-11-06T20:36:42+08:00  
**对应整改缺陷**: **DEF-05**

---

## 一、第二轮审计揭露的检验器漏洞

在第二轮独立审计中，审计官在《08_DEFECT_B_CAD_QUALITY_INSPECTOR.md》中指出了一个重大设计漏洞：
- 检验器在行 163 处仅使用了 `if measured is theoretical:` 判定自比对；
- 若调用者使用 `theo = dict(meas)` 或 `theo = copy.deepcopy(meas)`，因生成了新的 Python 字典对象，指针同一性判定失效；
- 此时检验器计算相对误差为 0.0，直接给出 100 分满分并标记为 `VERIFIED`，产生了“克隆数据冒充独立理论推导”的虚假验收隐患。

---

## 二、第三轮算法整改与防御加固

针对上述漏洞，在 `cad_quality_inspector.py` 中重构了几何核验逻辑：

1. **多重克隆探测机制**：
   不仅校验 `measured is theoretical` 指针同一性，同时比对键值字典内容 `meas_core == theo_core`；
2. **强制数据溯源（Data Provenance）凭证**：
   引入 `provenance` 与 `source` 白名单机制（仅认可 `independent_analytical`、`cad_benchmark`、`analytical_calculation` 等可信来源标识）。若键值完全相同且未附带独立解析凭证，判定为未经授权的自克隆；
3. **强制拦截与降级**：
   一旦命中克隆特征且无独立解析证据，系统强制：
   - 扣除几何项 50 分；
   - 标记维度状态为 `NOT_VERIFIED`；
   - 标记指标项 `suspected_clone_detected = True`；
   - 报告总体接受状态强制置为 `is_acceptable = False`。

---

## 三、单元测试全面回归证据

在 `tests/remediation_cad_quality_inspector_test.py` 中新增用例，覆盖全部 11 类边界场景：

| 用例编号 | 测试场景描述 | 输入数据结构 | 预期断言与防护响应 | 执行结果 |
| :---: | :--- | :--- | :--- | :---: |
| Test 01 | 独立理论来源完美吻合 | `meas` 与 `theo` 数值相同且 `independent_theoretical_source=True` | `is_acceptable=True`, `status=VERIFIED`, 得分 100 | **PASS** |
| Test 02 | 允许工程公差 (0.02% <= 0.05%) | `meas=55611.12`, `theo=55600.0` | `is_acceptable=True`, `status=VERIFIED`, 得分 100 | **PASS** |
| Test 03 | 尺寸超差拦截 (2.5% > 1.0%) | `meas=57000.0`, `theo=55600.0` | `is_acceptable=False`, `status=FAILED`, 得分 <= 60 | **PASS** |
| Test 04 | 理论值缺失防御 | `theo=None` | `is_acceptable=False`, `status=NOT_VERIFIED`, 得分 <= 60 | **PASS** |
| Test 05 | 键名兼容性 | 支持 `volume_mm3` 与 `volume` | 字段自适应提取无损 | **PASS** |
| Test 06 | 非法数值防御 | `volume <= 0` 或 `NaN` | `is_acceptable=False`, `status=FAILED`, 得分 0 | **PASS** |
| Test 07 | 原生自比对指针拦截 | `meas is theo` (同一对象) | `is_acceptable=False`, `self_comparison_detected=True` | **PASS** |
| Test 08 | 微观坐标采样超差 | 局部特征点偏移 > 0.005mm | `is_acceptable=False`, `status=FAILED` | **PASS** |
| **Test 09** | **字典浅拷贝克隆拦截 (DEF-05)** | `theo = dict(meas)` (新指针无来源) | `is_acceptable=False`, `status=NOT_VERIFIED`, `suspected_clone_detected=True` | **PASS** |
| **Test 10** | **字典深拷贝克隆拦截 (DEF-05)** | `theo = copy.deepcopy(meas)` | `is_acceptable=False`, `status=NOT_VERIFIED`, `suspected_clone_detected=True` | **PASS** |
| **Test 11** | **独立溯源凭证放行** | `theo={"volume": ..., "provenance": "analytical_calculation"}` | `is_acceptable=True`, `status=VERIFIED` | **PASS** |

**单测日志输出**: `audit/third-remediation-2026-11-06/test_execution_logs/remediation_cad_quality_inspector_test.log` (11 tests in 0.001s, OK).

---

## 四、真实阶梯轴实机物理评价数据

在 `run_third_remediation_cad.py` 中对物理生成的阶梯轴（`remediated_stepped_shaft.SLDPRT`）执行实测核验：
- **独立理论推导模型**：
  - 段 1 (D50 x L100mm): \( V_1 = \pi \times 25^2 \times 100 = 196349.5408 \text{ mm}^3 \)
  - 段 2 (D30 x L80mm): \( V_2 = \pi \times 15^2 \times 80 = 56548.6678 \text{ mm}^3 \)
  - 键槽切除 (30 x 8 x 4mm): \( V_{\text{cut}} = 960.0 \text{ mm}^3 \)
  - 理论总净体积: \( V_{\text{theo}} = 196349.5408 + 56548.6678 - 960.0 = 251938.21 \text{ mm}^3 \)
  - 溯源标识: `"provenance": "independent_analytical"`
- **SolidWorks 实测物理体积**: `251938.21 mm³`
- **相对误差**: `0.0000%`
- **评价结论**: 总体质量得分 `100.0`，判定状态 `VERIFIED`，`is_acceptable: True`。

---

## 五、最终判定

**整改状态**: **CLOSED / VERIFIED**  
质量检验器已彻底消除浅拷贝/深拷贝自克隆漏洞，具备对未经验证克隆数据的强力拦截与合法解析溯源放行能力。
