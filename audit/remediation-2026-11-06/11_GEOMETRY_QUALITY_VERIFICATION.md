# CAD 几何质量检查器防自比对与评分机制核验报告

**核验脚本**: `docs/stage5_advanced_ai_cad/scripts/cad_quality_inspector.py`  
**镜像副本**: `audit/remediation-2026-11-06/cad_quality_inspector_remediated.py`  
**自动化测试**: `tests/remediation_cad_quality_inspector_test.py` (8/8 通过)

---

## 一、整改缺陷与机制增强

针对独立审查发现的 `cad_quality_inspector.py` 的漏洞，完成以下三大增强机制：

1. **强健的自比对与引用同一对象拦截**:
   检测 `if measured is theoretical:` 或实测值被调用方冒充为理论值，直接扣除 50 分，评级强制标记为 `NOT_VERIFIED`。
2. **缺失理论值封顶保护**:
   当调用方未提供独立理论值时（`theoretical is None`），系统禁止自动代入实测值，得分封顶 75 分，状态固定为 `NOT_VERIFIED`，`is_acceptable` 强制为 `False`。
3. **全局子维度 FAILED 联锁保护**:
   只要草图约束 (`topology_score`) 或重建耗时 (`stability_score`) 出现 `FAILED` 状态，即使总分超过 80 分，`is_acceptable` 也必须强制判定为 `False`，彻底杜绝高分带病合格漏洞。
4. **属性键名归一化兼容**:
   自动在 `volume`、`volume_mm3`、`surface_area`、`surface_area_mm2` 之间规范化解析，杜绝因键名差异导致的漏检。

---

## 二、测试用例验证结果

在 `tests/remediation_cad_quality_inspector_test.py` 中 8 项专项测试全部通过：
- `test_01_self_comparison_detection`: 自比对精准拦截 (得分 50.0, NOT_VERIFIED, is_acceptable=False)
- `test_02_missing_theoretical_capped_score`: 缺少理论值封顶 (得分 <= 75.0, NOT_VERIFIED)
- `test_03_zero_volume_guard`: 体积为 0 分母保护正常拦截
- `test_04_dimension_deviation_deduction`: 尺寸超差梯度扣分机制正常
- `test_05_micro_point_deviation_rejection`: 微观采样点超差拦截正常
- `test_06_volume_key_normalization`: `volume` 与 `volume_mm3` 键名归一化解析正常
- `test_07_valid_independent_theoretical_pass`: 独立理论值高精度吻合正常评为 100 分 VERIFIED
- `test_08_failed_status_when_volume_deviates`: 体积超差 5% 时状态明确标记为 FAILED
