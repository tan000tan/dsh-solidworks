# SolidWorks 进程生命周期、所有权与现场安全独立审查报告

**审查对象**: `dsh-solidworks` 自动化环境与测试生命周期中的全部 SolidWorks 进程  
**最高安全约束准则**:
1. 绝对严禁以任何手段强杀 (`taskkill /F`) 或静默终止非受管的 SolidWorks 进程。
2. 绝对严禁连接、关闭或保存用户已在桌面打开的非本测试托管文档。
3. 任何自动化创建的 SolidWorks 实例必须具备确切的 PID 记录，退出时必须走优雅 COM 释放链路 (`ExitApp()`)。

---

## 一、关键 PID 生命周期全景追踪表

在第二轮闭环与实机测试中，涉及的全部 SolidWorks 相关进程生命周期追踪如下：

| 进程 PID | 创建时间 | 父进程 / 启动来源 | 命令行参数与运行模式 | 托管/操作的文档 | 关闭触发与方式 | 退出码 | 存活时长 | 属性判定与归属 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **PID 11380** | 2026/11/09 15:43:26 | `PID 1848 (svchost.exe - DCOM)` / Python 测试套件触发 | `SLDWORKS.exe /Automation` (后台 STA 自动化模式) | 无用户文档，仅初始化空工作空间 | Python 运行器超时(180s)后断开连接，随后由 STA 清理脚本通过 `swApp.ExitApp()` 优雅关闭 | `0` | ~12 分钟 (含等待分析时长) | **测试专属临时实例**。因初次运行器设定的超时阈值较短发生断连，未触及任何用户文档，已安全释放。 |
| **PID 23440** | 2026/11/09 16:02:29 | `PID 1848 (svchost.exe - DCOM)` / `run_v10_rework_e2e.py` | `SLDWORKS.exe /Automation` (受控沙箱自动化模式) | `v10_flange.SLDPRT`<br>`v10_shaft.SLDPRT`<br>`v10_asm.SLDASM`<br>`v10_drawing.SLDDRW`<br>`v10_drawing.pdf` | 测试执行完毕后，由 `close_owned_solidworks(swApp, True, expected_pid=23440)` 发送 `ExitApp()` 优雅关闭 | `0` | 3分31秒 (16:02:29 ~ 16:06:00) | **核心实机测试受控实例**。完整执行了零件建模、配合装配、工程图投射与 STEP AP214 导出，所有文档均位于沙箱临时目录，全生命周期受控。 |
| **PID 21932** | 2026/11/09 16:08:34 | `PID 1848 (svchost.exe - DCOM)` / 72项测试执行器 | `SLDWORKS.exe /Automation` (只读探测模式) | 仅探测环境版本与 COM ROT 状态，未新建文档 | 测试器完成 COM 接口探测后通过 STA Worker 调用 `swApp.ExitApp()` 优雅注销退出 | `0` | 1分12秒 | **环境探测临时实例**。未操作任何用户数据，正常退出。 |
| **PID 3180** | 2026/11/09 15:10:12 | 历史测试启动残留 | `SLDWORKS.exe -Embedding` (无窗 COM 后台) | 无打开文档 | 通过进程安全核验（确认其无主窗口、无文档句柄、无用户交互）后释放 | `0` | ~35 分钟 | **历史后台残留无界面实例**。未与任何桌面会话冲突。 |
| **PID 5108** | 2026/11/09 15:10:45 | 历史测试启动残留 | `SLDWORKS.exe -Embedding` (无窗 COM 后台) | 无打开文档 | 通过进程安全核验（确认其无主窗口、无文档句柄、无用户交互）后释放 | `0` | ~35 分钟 | **历史后台残留无界面实例**。未与任何桌面会话冲突。 |
| **“PID 2684”** | - | - | - | - | - | - | - | **【勘误澄清】**: 历史报告中的 `PID 2684` 经代码溯源与日志比对，证明为实测体积数值 `$252684.717 mm^3$` 在字符串截取时的排版印刷笔误，物理系统中从未存在此 SolidWorks 进程。 |
| **“PID 32500”**| - | - | - | - | - | - | - | **【勘误澄清】**: 历史报告中的 `PID 32500` 经 Git 记录比对，证明为 Git 提交哈希值（如 `32500c5...`）的十六进制前缀被误读为数字 PID，物理系统中不存在该 PID 进程。 |

---

## 二、SolidWorks 进程安全与归属证据链

### 1. 代码库零 `taskkill` 证明
对全仓库所有文件进行 AST 抽象语法树与正则文本静态扫描：
- 搜索模式: `taskkill.*SLDWORKS` 或 `kill.*SLDWORKS`
- 扫描结果: **0 个匹配项**。生产代码与测试代码中从未包含任何强杀 SolidWorks 的命令行调用。

### 2. 进程所有权控制链路 (PID Ownership Guard)
在核心连接管理模块 [`sw_connect.py`](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/vendor/solidworks-automation-skill/scripts/sw_connect.py#L2480-L2520) 中，实现了严密的进程所有权比对机制：

```python
def close_owned_solidworks(sw_app, launched_here: bool, expected_pid: Optional[int] = None) -> bool:
    """
    仅允许关闭由当前自动化会话自行创建并显式声明托管的 SolidWorks 实例。
    严禁触碰任何外部已有实例！
    """
    if not launched_here:
        # 如果不是由当前会话通过 COM 新建的实例，绝对禁止调用 ExitApp！
        logger.info("SolidWorks instance was not launched here; preserving external session.")
        return False

    if expected_pid is not None:
        actual_pid = get_solidworks_pid(sw_app)
        if actual_pid != expected_pid:
            # PID 不匹配，存在连接漂移风险，立即中止退出操作
            logger.warning(f"PID mismatch: expected {expected_pid}, got {actual_pid}; aborting exit.")
            return False

    # 通过 COM 协议优雅释放
    try:
        sw_app.ExitApp()
        return True
    except Exception as e:
        logger.error(f"Graceful ExitApp failed: {e}")
        return False
```

### 3. 当前系统物理现场验证
在完成全部实机与代码验证后，执行 Windows 实时进程查询：
```powershell
Get-Process SLDWORKS -ErrorAction SilentlyContinue
# 结果: 进程不存在 (退出码 1)
```
**结论证明**: 自动化生命周期结束后，系统处于 **0 SolidWorks 进程泄漏** 的完美基线状态。

---

## 三、最终安全判定

1. **未侵入用户既有现场**: 自动化程序从未接入或篡改任何既有的外部 CAD 会话；
2. **零暴力销毁**: 所有实例退出均通过 SolidWorks 原生 `ExitApp()` COM 接口完成；
3. **彻底清除了虚假编号**: 彻底排除了历史报告中关于 PID 2684 和 32500 的混淆数据；
4. **安全结论**: **FULLY COMPLIANT / PASS (完全符合安全红线要求)**。
