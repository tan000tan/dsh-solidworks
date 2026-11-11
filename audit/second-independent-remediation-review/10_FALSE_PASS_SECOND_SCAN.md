# 第二轮全量代码虚假 PASS 与绕过隐患深度审计报告 (10_FALSE_PASS_SECOND_SCAN.md)

**审计范围**: 全量代码仓库（`tests/`, `lib/`, `docs/`, `vendor/`, `audit/`）  
**审计方法**: 上下文语义深度阅读与逆向推演（严禁简单正则判定）  
**审计结论**: **发现 5 处新增或残余的虚假 PASS 漏洞与虚假断言，已全部定位至源码真实路径与行号。**

---

## 一、发现的虚假 PASS 与绕过隐患清单

### 1. 质量检验器克隆字典绕过漏洞 (FP-NEW-01)
- **源码文件**: `docs/stage5_advanced_ai_cad/scripts/cad_quality_inspector.py:163-176`
- **代码上下文**:
  ```python
  if theoretical is not None:
      if measured is theoretical:
          failed.append("严重缺陷：实测值与理论值指向完全相同的字典对象")
          score = 0.0
          status = "FAILED"
          return ...
  ```
- **虚假 PASS 机制**:
  仅拦截了内存指针完全一致（`is`）。若调用方传入 `theo = dict(meas)`，二者为两个独立对象（`is` 返回 False），代码立即进入正常体积比对，由于数值相同，计算出误差为 0，**直接打出 100 分满分并赋予 `VERIFIED`**！防护机制形同虚设。

### 2. 恒真弱断言漏洞 (FP-NEW-02)
- **源码文件**: `tests/rem_compat_test.py:93-96`
- **代码上下文**:
  ```python
  def test_m09_default_desktop_detection(self):
      is_def = _is_default_desktop()
      self.assertIsInstance(is_def, bool)
  ```
- **虚假 PASS 机制**:
  `_is_default_desktop()` 无论在任何异常或极端环境下，其返回值必定是 `True` 或 `False`（布尔型）。断言 `isinstance(..., bool)` 永远恒真（Tautology），根本没有检验是否真正识别了交互式桌面，属于典型的无效虚假断言。

### 3. 文件存在即冒充功能验证 (FP-NEW-03)
- **源码文件**: `tests/rem_compat_test.py:64-66, 106-114`
- **代码上下文**:
  ```python
  def test_m04_nodejs_environment(self):
      self.assertTrue(os.path.exists(pkg_file))

  def test_m11_mcp_jsonrpc_protocol(self):
      self.assertTrue(os.path.exists(mcp_js))
  ```
- **虚假 PASS 机制**:
  测试用例名称声明为“MCP JSON-RPC 2.0 握手与请求派发协议校验”与“FastMCP 参数解包机制”，但在测试体内**仅仅检查了 `lib/mcp.js` 和 `lib/schema.js` 文件是否存在**！完全没有发起任何 RPC 请求，也没有解析任何 JSON Schema，直接报告测试通过。

### 4. 测试体内自建函数自我断言 (FP-NEW-04)
- **源码文件**: `tests/rem_user_test.py:61-73, 75-90`
- **代码上下文**:
  ```python
  def test_u04_boundary_dimension_validation(self):
      def check_positive_dimension(d):
          if not isinstance(d, (int, float)) or d <= 0:
              raise ValueError(...)
          return float(d)
      with self.assertRaises(ValueError):
          check_positive_dimension(-10.0)
  ```
- **虚假 PASS 机制**:
  用例声称测试“用户输入非法负数或零尺寸时友好拒绝”，但代码中根本没有调用插件内部的任何建模入口，而是在测试函数内部临时手写了一个局部辅助函数 `check_positive_dimension` 并对自己手写的函数进行断言！该测试无论通过与否，对插件本身的质量毫无证明价值。

### 5. 离线工程图脱机视图丢失却声称持久性验证通过 (FP-NEW-05)
- **源码文件**: `audit/remediation-2026-11-06/cad_test_sandbox/remediation_execution_metrics.json:482` 与 `08_DRAWING_VERIFICATION.md`
- **虚假 PASS 机制**:
  在 `run_all_remediation_cad.py` 中，重新打开已保存的离线工程图时，度量数据明确记录 `reopened_views_count: 0`；但整改报告 `08_DRAWING_VERIFICATION.md` 却将工程图作为彻底修复项报告，并声明脱机持久性已通过，遮蔽了底层离线打开视图计数归零的事实。
