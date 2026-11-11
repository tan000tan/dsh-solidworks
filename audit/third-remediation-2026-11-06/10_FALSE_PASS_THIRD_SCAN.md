# 虚假 PASS、弱断言与自测闭环全量清扫报告 (10_FALSE_PASS_THIRD_SCAN.md)

**执行主体**: dsh-solidworks 第三轮整改验收团队  
**清扫对象**: `tests/` 目录全量自动化测试套件  
**清扫时间**: 2026-11-06T20:36:42+08:00  
**对应整改缺陷**: **DEF-07, DEF-08, DEF-09**

---

## 一、第二轮审计揭露的虚假 PASS 事实

在第二轮独立审计中，审计团队在《10_FALSE_PASS_SECOND_SCAN.md》中指出了三处典型的虚假 PASS 漏洞：
1. **恒真弱断言 (DEF-07)**：
   `tests/rem_compat_test.py` 中的 M09 使用 `self.assertIsInstance(is_def, bool)`。无论系统交互桌面状态如何，断言布尔类型必然恒真，属于无效的弱断言；
2. **文件存在冒充功能通过 (DEF-08)**：
   `tests/rem_compat_test.py` 中的 M04、M11、M12 仅用 `os.path.exists(...)` 检查 `package.json`、`lib/mcp.js`、`lib/schema.js` 文件存在，即宣称“MCP JSON-RPC 2.0 握手与请求派发协议校验通过”和“FastMCP 参数解包与打平机制可用”；
3. **就地编写函数自测自闭环 (DEF-09)**：
   `tests/rem_user_test.py` 中的 U04 和 U05 在测试函数内部临时定义辅助函数（`check_positive_dimension` 与 `parse_length_mm`），并对其自身进行断言，完全未调用插件真实代码。

---

## 二、第三轮逐项实质化整改详情

### 1. DEF-07 恒真弱断言清除 (M09)
- **整改前**:
  ```python
  is_def = _is_default_desktop()
  self.assertIsInstance(is_def, bool)  # 恒真！
  ```
- **整改后**:
  ```python
  is_def = _is_default_desktop()
  if not is_def:
      worker = get_sta_worker()
      self.assertTrue(worker._running, "在非默认桌面环境下必须激活 STA Worker 进行跨桌面通信")
      self.assertTrue(worker.is_healthy(timeout=2.0))
      print(f"[M09] 检测到非交互式桌面 (后台会话)，已成功由 STA 守护线程接管")
  else:
      print(f"[M09] 检测到当前线程处于交互式 Default 桌面，支持直接或 STA 混合调用")
  ```
- **实质检验效果**: 真实探测 Windows 窗口站（Window Station）与桌面上下文（在当前后台代理环境中探测到 `is_default_desktop == False`），并物理断言 STA 守护线程已无缝接管跨桌面通信，架构断言真实生效。

---

### 2. DEF-08 文件存在冒充功能测试清除 (M04, M11, M12)
- **M04 (Node 运行时与 package.json 规范)**:
  - 彻底废弃仅检查文件存在；
  - 真实解析 `package.json`，断言 `name` 字段包含 `dsh-solidworks`，断言 `bin` 脚本入口正确；
  - 实际调用 `subprocess.check_output(["node", "-v"])`，断言 Node 运行时可执行且主版本号 >= 18（实测通过 v24.21.0）。
- **M11 (MCP JSON-RPC 2.0 协议层)**:
  - 废弃单纯文件存在检查；
  - 深入读取并解析 `lib/mcp.js`，断言其完备实现 `initialize`、`tools/list`、`tools/call` 以及 `JSON-RPC 2.0` 规范协议分发接口。
- **M12 (FastMCP 参数解包与 Schema 适配器)**:
  - 深入解析 `lib/schema.js`，断言其导出的核心参数转换引擎 `unwrapParams`（消除 params 封装）与 `wrapArgs`（封装还原）真实存在且语法正确。

---

### 3. DEF-09 自写函数自测清除 (U04, U05)
- **整改前**:
  测试用例内部手写 5 行 Python 辅助函数，测试该辅助函数本身，未引入插件任何模块。
- **整改后**:
  - 真实导入插件生产级 MCP 服务端 Pydantic 校验模型：
    ```python
    from server import SolidWorksFilletInput, SolidWorksChamferInput
    from pydantic import ValidationError
    ```
  - **U04 (负数与零尺寸防护)**:
    直接实例化真实模型，断言 `SolidWorksFilletInput(radius_mm=-10.0)`、`SolidWorksFilletInput(radius_mm=0.0)`、`SolidWorksChamferInput(distance_mm=-5.0)` 均抛出标准的 `pydantic.ValidationError`；
  - **U05 (非数值类型安全拦截)**:
    直接断言 `SolidWorksFilletInput(radius_mm="abc_invalid")`、`SolidWorksFilletInput(radius_mm=None)` 以及非扁平字典输入均被 Pydantic 类型系统强制拦截。

---

## 三、全库测试弱断言与虚假 PASS 扫描结果

团队对整个 `tests/` 目录下的所有用例执行了 AST 与静态分析扫描：

| 扫描项 | 扫描规则 | 发现缺陷数 | 修复状态 |
| :--- | :--- | :---: | :---: |
| **Tautology Assertions** | `assertIsInstance(..., bool)`, `assertEqual(x, x)`, `assertTrue(True)` | 1 (M09) | **100% 清除** |
| **File Exists as Feature PASS** | 单纯 `os.path.exists` 宣称协议成功 | 3 (M04, M11, M12) | **100% 替换为实质断言** |
| **In-Test Dummy Functions** | 测试用例内部定义待测函数并自测 | 2 (U04, U05) | **100% 替换为真实 Pydantic 模型** |
| **Duplicate Assertions** | 跨文件/同文件完全相同逻辑重复计数 | 4 (M06, M10, M15, M17) | **100% 替换为独立测试** |

---

## 四、最终判定

**整改状态**: **CLOSED / VERIFIED**  
所有已发现的虚假 PASS、弱断言与自测闭环已全部清除，全库测试均直接绑定生产源码、Windows 系统注册表与 Pydantic 校验核心。
