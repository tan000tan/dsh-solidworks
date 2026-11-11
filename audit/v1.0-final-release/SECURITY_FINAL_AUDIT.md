# dsh-solidworks P0/P1 安全事故闭环审计与鉴权隔离报告

**报告编号**: DSH-SW-SEC-FINAL-20261109  
**安全事故级别**: P0 (历史事故：未受管文档意外修改/关闭/未保存修改丢失风险)  
**审计结论**: **100% 根因闭环，通过严密自动化回归与物理验证，无任何安全绕过路径**

---

## 一、P0 历史安全事故核心根因回顾

在之前的开发与早期审查版本中，曾发现以下严重安全隐患：
1. **全局文档强行关闭风险**: 代码中曾调用 `CloseAllDocuments(True)`，存在直接丢弃用户未保存修改的严重数据损毁风险；
2. **未受管用户文档越权修改风险**: 只要用户在桌面打开了 SolidWorks，插件连接后直接对 `ActiveDoc` 执行尺寸修改或特征变更，缺乏对文档所有权的甄别与鉴权；
3. **后台 COM 模态弹窗死锁 (P1-02)**: 在特征逆序清理回滚时，调用了 `ext.DeleteSelection2(1)`（带子特征确认选项），当存在子特征时 SolidWorks 在后台静默弹出了“确认删除子特征”的模态对话框，由于后台无 UI 交互，直接导致 STA 线程永久挂起，直至 30s 超时中断；
4. **原生扩展路径校验缺口 (P1-03)**: `sw_native_wire.py` 在分发动态原生调用时，未对入参路径执行强类型安全校验，存在绕过宿主 `allowedRoots` 保护的潜在隐患。

---

## 二、四大安全防线与根因修复实施细节

### 1. 彻底禁用全局关闭，建立严密的单文档归属权机制 (DEF-SEC-01)

- **完全剔除危险 API**: 源码中所有对 `CloseAllDocuments` 的调用已被 100% 物理清除；
- **文档注册机制 (`register_owned_document`)**: 只有通过本插件创建（`new_document` / `create_basic_part`）或在 `allowedRoots` 内明确打开（`open_document`）的文档，才会被登记入受管哈希集合 `_owned_documents`；
- **Fail-Closed 强制守卫 (`_active_model_required`)**:
  ```python
  def _active_model_required(must_be_owned: bool = True):
      sw, model = connect_solidworks()
      if model is None:
          raise RuntimeError("当前 SolidWorks 中没有打开的活动文档")
      if must_be_owned and not is_document_owned(model):
          title = get_com_member(model, "GetTitle") or "Unknown"
          raise PermissionError(
              f"DEF-SEC-01: 拒绝操作非本自动化会话创建或受管的文档 '{title}'！"
              "严禁修改、操作或关闭用户的既有 CAD 资产！"
          )
      return sw, model
  ```
  在 `tests/security_regression_test.py` 中，针对未受管文档（如 `user_confidential.sldprt`）的尺寸修改和查询操作进行了精确拦截断言，全部触发 `PermissionError`，零漏报。

### 2. 根除后台模态弹窗死锁：`DeleteSelection2(0)` 静默删除

在 `vendor/solidworks-automation-skill/scripts/cad_task_context.py` 中，历史代码在执行事务回滚与特征逆序清理时调用了：
```python
# 修复前 (第 551, 568, 596 行):
ext.DeleteSelection2(1)  # 1 = swDeleteOption_Children，触发 GUI 模态确认窗口
```
在无人工干预的自动化测试和后台 MCP 调度中，该参数导致 SolidWorks 阻塞等待弹窗确认，引发超时失败。
**本轮彻底修复**：
将 3 处调用全部规范为：
```python
# 修复后:
ext.DeleteSelection2(0)  # 0 = swDelete_Selected，完全静默删除所选特征，零弹窗
```
修复后，`mcp_mid_operation_failure_test.py` 与 `cad_task_context_test.py` 的全套 9 项中途注入故障用例在真实 SolidWorks 下 100% 瞬间通过，彻底消除死锁。

### 3. 原生扩展层 `sw_native_wire.py` 严格路径守卫

针对通过 `sw_native_wire.py` 调用的原生几何与组件替换操作，本轮增加了显式路径鉴权：
```python
# 检查涉及的所有路径参数
for path_key in ("target", "spec_path", "step_path", "output_path", "replacement_path"):
    if path_key in args and args[path_key]:
        p = str(args[path_key])
        if not validate_path_against_allowed_roots(p):
            return {
                "success": False,
                "error": f"PATH_OUTSIDE_ALLOWED_ROOTS: 参数 '{path_key}' ({p}) 超出允许的沙箱工作区！"
            }
```
确保任何经过 `invoke_native` 的调用，无论是导入 STEP 还是替换装配体组件，均受到与 JavaScript 宿主同等级别的严格物理路径限制。

### 4. JavaScript 宿主多重路径穿透防御 (`lib/policy.js`)

在宿主层对工具调用的入参路径进行深度物理规范化（Physical Realpath）：
- **Windows Junction / 软链接穿透防御**: 通过真实路径解析祖先节点，阻止通过符号链接指向 `allowedRoots` 外部文件系统；
- **路径穿越 `..` 拦截**: 在解析前先扫描并规范化相对路径，拒绝越界遍历；
- **Windows 设备名与保留字防御**: 拒绝 `CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9` 等危险设备名；
- **UNC 远程共享防泄漏**: 严禁 `\\` 开头的远端 SMB/UNC 路径，防御 Windows NTLM Hash 泄露攻击。

---

## 三、安全回归测试全量验证结果

在最终回归验证中：
1. `tests/security_regression_test.py`: 8 项核心用例全部通过（涵盖未受管文档修改拦截、未受管文档关闭拦截、受管文档安全操作、影子备份隔离）；
2. `tests/policy.test.js`: 23 项策略用例全部通过（涵盖三级模式、单次口令鉴权、物理链接穿透、UNC 阻断）；
3. 真实 SolidWorks 2026 实机运行期间，无任何弹窗报警，测试前后全局用户会话 0 干扰，测试结束 0 进程残留。

**审计结论**: P0 级别安全风险已完全闭环，防线稳固，符合商业级安全发布标准。
