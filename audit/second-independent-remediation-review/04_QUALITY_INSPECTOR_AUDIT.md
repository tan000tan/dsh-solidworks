# CAD 几何质量检查器防自比对与评分审计报告 (04_QUALITY_INSPECTOR_AUDIT.md)

**审计源码**: `docs/stage5_advanced_ai_cad/scripts/cad_quality_inspector.py` 及 `audit/remediation-2026-11-06/cad_quality_inspector_remediated.py`  
**专项单测**: `tests/remediation_cad_quality_inspector_test.py`  
**本项最终裁定**: **`PARTIALLY VERIFIED` (部分验证，存在关键防护漏洞)**

---

## 一、检查项逐项核验清单

| 检查维度 | 源码实现位置 | 检查结果与防护逻辑分析 | 独立审计结论 |
| :--- | :--- | :--- | :--- |
| **1. 同一字典对象检测** | `cad_quality_inspector.py:163` | `if measured is theoretical:` -> 扣 50 分，score=0.0, status='FAILED' | **PASS (有效防护)** |
| **2. 不同字典但内容克隆** | `cad_quality_inspector.py:202` | **致命漏洞**：仅检测了对象同一性 (`is`)。若 `theo = dict(meas)`，二者为不同对象，相对误差为 0，**直接判定优秀通过并给 100 分**！ | **FAIL (重大漏洞)** |
| **3. 理论值缺失处理** | `cad_quality_inspector.py:187` | `elif v_theo is None:` -> 扣 40 分，status='NOT_VERIFIED'，is_acceptable=False | **PASS (有效防护)** |
| **4. 理论值来源不独立** | `cad_quality_inspector.py:178` | `if not independent_theoretical_source:` -> 扣 15 分，出警告 | **PASS (有效防护)** |
| **5. 键名归一化解析** | `cad_quality_inspector.py:33` | `_extract_number` 支持 `volume` 与 `volume_mm3` 优先降级提取 | **PASS (有效防护)** |
| **6. 零分母防护** | `cad_quality_inspector.py:196` | `elif v_theo <= 0:` -> 扣 50 分，status='FAILED'，不进入除法 | **PASS (有效防护)** |
| **7. 负数与非法值** | `cad_quality_inspector.py:183` | `if v_meas is None or v_meas <= 0:` -> 拦截负数、零与 NaN | **PASS (有效防护)** |
| **8. 综合评分联锁** | `cad_quality_inspector.py:115` | `has_any_failed = any(...)` -> 任意子项失败强制 `is_acceptable=False` | **PASS (有效防护)** |

---

## 二、重大证据与逻辑缺陷深度剖析：克隆字典绕过

### 漏洞复现路径：
如果外部调用方或测试用例编写如下代码：
```python
# 两个完全不同的内存字典对象，但数据直接从 measured 复制
measured_data = {"volume": 158286.48, "body_count": 1}
theoretical_data = {"volume": measured_data["volume"]}  # 或 dict(measured_data)

report = inspector.inspect_quality("BypassModel", measured_data, theoretical_data)
```
### 执行结果追踪：
1. `measured is theoretical` 为 `False`（因为是两个独立字典对象），绕过了第 163 行的同一性检查；
2. 计算相对误差：`err_v = abs(158286.48 - 158286.48) / 158286.48 = 0.0`；
3. 进入第 212 行：`if err_v <= 0.0005:`，判定为“宏观体积误差吻合优秀”；
4. 综合得分：**100.0 分**；
5. 综合评级：**`VERIFIED`**；
6. 最终接受：**`is_acceptable = True`**！

### 审计结论：
整改方虽然修复了指针相同的情况（`is`），但**完全没有防御数值完全相同的克隆字典自比对**。只要调用方简单执行一次浅拷贝，质量检验器就会毫无察觉地将克隆数据判定为 100 分满分！在 `tests/remediation_cad_quality_inspector_test.py` 中，整改方编写的 8 个测试用例全部避开了该克隆场景，属于典型的**测试盲区与证据缺陷**。
