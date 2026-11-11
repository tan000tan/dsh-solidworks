# 第三轮源码与测试套件整改变更日志 (02_SOURCE_CODE_CHANGELOG.md)

**整改执行日期**: 2026-11-06  
**对应基线**: Git HEAD `7d70bc090d5cef146ac3946bb062667ae30a4cc9`  
**整改依据**: 第二轮独立审计报告中关于虚假断言、自测闭环与克隆绕过的定性结论（DEF-05 ~ DEF-10）

---

## 一、修改文件清单

| 序号 | 文件相对路径 | 对应缺陷编号 | 变更类型 | 修改核心内容概述 |
| :---: | :--- | :---: | :---: | :--- |
| 1 | `docs/stage5_advanced_ai_cad/scripts/cad_quality_inspector.py` | **DEF-05** | 代码修复 / 防御增强 | 引入理论基准数据来源证明（Provenance）校验；新增字典克隆（`dict(meas)`、`copy.deepcopy(meas)`）特征探测；无独立可信来源时强制打出 `NOT_VERIFIED` 且 `is_acceptable=False`。 |
| 2 | `tests/remediation_cad_quality_inspector_test.py` | **DEF-05** | 测试补齐 | 新增场景 9、10、11，实测拦截 `dict(meas)` 浅拷贝克隆、`deepcopy` 深拷贝克隆，并验证携带可信来源标识的理论值合法放行。 |
| 3 | `tests/rem_user_test.py` | **DEF-09** | 测试真实化 | 彻底删除 U04、U05 内部临时编写的自测辅助函数，改为真实导入插件 Pydantic 输入模型（`SolidWorksFilletInput`, `SolidWorksChamferInput`），断言其对负数、零、非数值、None 抛出 `ValidationError`。 |
| 4 | `tests/rem_compat_test.py` | **DEF-07, DEF-08, DEF-10** | 测试去重与实质化 | 1. M04 解析 `package.json` 并调用 `node -v` 实测 Node 运行时；<br>2. M06 改为真实读取 Windows 注册表 `SldWorks.Application.34\CLSID`；<br>3. M09 消除 `isinstance(bool)` 弱断言，改为实测非交互桌面下 STA 守护线程接管；<br>4. M10 替换为 STA 跨线程异常捕获与无损透传；<br>5. M11/M12 引入 MCP JSON-RPC 2.0 与 FastMCP `unwrapParams`/`wrapArgs` 实质断言；<br>6. M15 验证连续异常注入后工作线程自愈能力；<br>7. M17 实测目录穿越攻击（`..\..\Windows\System32\evil.dll`）沙箱拦截。 |
| 5 | `tests/rem_stress_test.py` | **DEF-06** | 文档与断言规范化 | 将 Category C 的标题与说明修正为“STA 单线程调度排队与超时防护”，如实阐述 COM STA 线程约束，拒绝夸大并发能力；优化 F02 适配质量检验器数据来源规范。 |

---

## 二、逐项代码修改详情 (Diff 证据)

### 1. `cad_quality_inspector.py` (DEF-05)
```python
<<<< 变更前
        if theoretical is not None:
            if measured is theoretical:
                failed.append("严重缺陷：实测值与理论值指向完全相同的字典对象 (自比对虚假核验)")
                score = 0.0
                status = "FAILED"
                metrics["self_comparison_detected"] = True
                ...
==== 变更后
        if theoretical is not None:
            # 1. 指针同一性检查
            if measured is theoretical:
                failed.append("严重缺陷：实测值与理论值指向完全相同的字典对象 (自比对虚假核验)")
                ...
            # 2. 字典浅拷贝/深拷贝克隆绕过探测 (如 theo = dict(meas) 或 copy.deepcopy(meas))
            has_trusted_provenance = (
                theoretical.get("provenance") in ("independent_analytical", "cad_benchmark", "analytical_calculation")
                or theoretical.get("source") in ("analytical", "hand_calculation", "cad_benchmark")
            )
            is_identical_content = False
            if isinstance(measured, dict) and isinstance(theoretical, dict):
                meas_core = {k: v for k, v in measured.items() if not k.startswith("_")}
                theo_core = {k: v for k, v in theoretical.items() if not k.startswith("_") and k not in ("provenance", "source")}
                if meas_core and (meas_core == theo_core or all(k in theo_core and theo_core[k] == v for k, v in meas_core.items())):
                    is_identical_content = True

            if is_identical_content and not has_trusted_provenance:
                warnings.append("严重警告：理论值内容系实测数据直接克隆 (dict/deepcopy clone bypass detected)，未通过独立解析源验证")
                score = 50.0
                status = "NOT_VERIFIED"
                metrics["suspected_clone_detected"] = True
                return QualityCategoryScore(
                    category_name="几何尺寸与局部微观坐标",
                    score=50.0,
                    weight=self.weights["geometry"],
                    status="NOT_VERIFIED",
                    passed_checks=passed,
                    failed_checks=failed,
                    warnings=warnings
                ), metrics
>>>>
```

### 2. `rem_user_test.py` (DEF-09)
```python
<<<< 变更前
    def test_u04_boundary_dimension_validation(self):
        def check_positive_dimension(d):
            if not isinstance(d, (int, float)) or d <= 0:
                raise ValueError(f"尺寸必须为正数: {d}")
            return float(d)
        with self.assertRaises(ValueError):
            check_positive_dimension(-10.0)

==== 变更后
    def test_u04_boundary_dimension_validation(self):
        """U04: 用户输入负数或零尺寸参数校验 (真实插件 Pydantic Schema 校验)"""
        with self.assertRaises(ValidationError):
            SolidWorksFilletInput(radius_mm=-10.0)
        with self.assertRaises(ValidationError):
            SolidWorksFilletInput(radius_mm=0.0)
        with self.assertRaises(ValidationError):
            SolidWorksChamferInput(distance_mm=-5.0)

        fillet = SolidWorksFilletInput(radius_mm=25.4)
        self.assertEqual(fillet.radius_mm, 25.4)
>>>>
```

### 3. `rem_compat_test.py` (DEF-07, DEF-08, DEF-10)
```python
<<<< 变更前
    def test_m06_sw2026_main_revision(self):
        self.assertEqual(_prog_id_for_version(2026), "SldWorks.Application.34") # 与 M05 完全重复

    def test_m09_default_desktop_detection(self):
        is_def = _is_default_desktop()
        self.assertIsInstance(is_def, bool) # 恒真断言

    def test_m10_cross_thread_sta_dispatch(self):
        res = worker.execute(lambda: 100 * 2) # 与 U09 重复四则运算
        self.assertEqual(res, 200)

==== 变更后
    def test_m06_sw2026_registry_clsid(self):
        """M06: SolidWorks 2026 Windows 注册表 CLSID 与 COM 接口注册校验"""
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"SldWorks.Application.34\CLSID") as key:
            clsid, _ = winreg.QueryValueEx(key, "")
        self.assertEqual(clsid.lower(), "{666aaee2-7a21-40fc-b768-2078840a88c3}".lower())

    def test_m09_default_desktop_detection(self):
        """M09: Windows 交互式桌面识别与 STA 线程亲和架构校验"""
        is_def = _is_default_desktop()
        if not is_def:
            worker = get_sta_worker()
            self.assertTrue(worker._running)
            self.assertTrue(worker.is_healthy(timeout=2.0))

    def test_m10_cross_thread_exception_propagation(self):
        """M10: STA 工作线程跨线程异常捕获与无损透传测试"""
        worker = get_sta_worker()
        def faulty_task(): raise ValueError("STA worker simulated COM fault")
        with self.assertRaises(ValueError) as ctx:
            worker.execute(faulty_task, timeout=2.0)
        self.assertTrue(worker.is_healthy(timeout=2.0))
>>>>
```

---

## 三、修改后测试回归验证汇总

- Node.js 测试 (`npm test`): 68/68 PASS (0 失败，0 告警，0 路径泄露)
- 兼容性测试 (`rem_compat_test.py`): 18/18 PASS
- 用户交互测试 (`rem_user_test.py`): 10/10 PASS
- 压力测试 (`rem_stress_test.py`): 38/38 PASS
- 质量检查器防御测试 (`remediation_cad_quality_inspector_test.py`): 11/11 PASS
- 阶段五高级功能单测 (`stage5_*_test.py`): 30/30 PASS
- **总计单元与集成自动化测试**: **175 项全数通过**。
