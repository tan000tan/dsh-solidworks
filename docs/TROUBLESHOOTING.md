# dsh-solidworks-plugin 故障排查与自愈手册 (Troubleshooting)

本文档针对普通用户在使用过程中可能遇到的环境、网络、Windows COM 权限及 CAD 运行时问题提供明确的排查与安全修复方案。

---

## 1. 安装与构建常见问题

### 问题 1.1：运行 `npm run setup` 提示“未在系统中检测到满足要求的 Python 3.10+ 环境”
- **原因分析**：系统中未安装 64位 Python，或安装时未勾选“Add python.exe to PATH”。
- **解决方案**：
  1. 前往 Python 官网下载 64 位安装包：[Python 3.12 / 3.13 64-bit 下载](https://www.python.org/downloads/windows/)；
  2. 运行安装程序，**务必勾选** 底部的 `Add python.exe to PATH`；
  3. 安装完成后，重启终端，重新执行 `npm run setup`；
  4. 若安装在非标准目录，可通过环境变量指定：
     ```bash
     $env:DSH_SOLIDWORKS_PYTHON = "D:\MyPython\python.exe"
     npm run setup
     ```

### 问题 1.2：PowerShell 提示“因为在此系统上禁止运行脚本...” (UnauthorizedAccess)
- **原因分析**：Windows PowerShell 默认的 `ExecutionPolicy` 限制执行 `.ps1` 脚本。
- **解决方案**：
  - 插件的所有核心维护工具已原生改为纯 Node.js，规避了这一限制；
  - 在 CMD 命令行中运行，或在 PowerShell 中调用 `node scripts/setup.js` 或 `cmd /c "npm run setup"`。

### 问题 1.3：依赖下载超时或网络错误
- **解决方案**：使用插件内置支持的清华镜像源重试：
  ```bash
  npm run setup -- --tsinghua
  ```

---

## 2. Windows COM 与 SolidWorks 连接排障

### 问题 2.1：运行 `npm run doctor` 时 `SOLIDWORKS_REGISTRY` 报错 FAIL
- **原因分析**：SolidWorks 安装后未注册 COM  ProgID `SldWorks.Application`。
- **解决方案**：
  1. 手动在桌面上双击启动一次 SolidWorks 软件；
  2. 新建一个空白零件，然后关闭 SolidWorks；
  3. SolidWorks 在首次启动时会自动向 Windows 注册 COM 接口；
  4. 重新运行 `npm run doctor` 确认绿灯。

### 问题 2.2：`STA_DESKTOP_PERM` 报错“STA 桌面工作线程调度异常”
- **原因分析**：当前运行在 Windows 无头后台服务 (Session 0) 或受限无交互权限的远程 SSH 会话中。
- **解决方案**：
  - SolidWorks COM 为单例图形界面自动化表面，必须在当前用户的交互式图形桌面会话中运行；
  - 登录物理桌面或通过标准 RDP 远程桌面连接后运行。

### 问题 2.3：`LIVE_COM_ECHO` 显示“COM 心跳探测响应超时”
- **原因分析**：SolidWorks 当前前台正弹出了模态对话框（如激活提醒、材质缺失确认或未保存退出提示），阻塞了 COM 消息队列。
- **解决方案**：
  1. 查看任务栏是否有闪烁的 SolidWorks 弹窗；
  2. 手动在弹窗上点击“确定”或“取消”；
  3. 插件的 `sw_session.py` 具有模态对话框自动白名单检测机制，通常会自动处理已知提示。

---

## 3. CAD 建模与参数自愈排障

### 问题 3.1：尺寸修改后提示“几何重构失败 / 产生几何自交”
- **表现**：模型出现红叉报错，特征树拓扑断裂。
- **自愈机制**：
  - 插件的 `modify_dimensions_safe` 会自动捕获该异常；
  - 底层 `ShadowBackupManager` 会在 0.5 秒内自动使用修改前抓取的物理快照执行原子覆盖还原；
  - 您的文件将 100% 恢复到修改前完好状态，终端会清晰告知回滚原因。

### 问题 3.2：报错“Access denied: save target ... is outside allowed roots”
- **原因分析**：DSH 安全沙箱策略拦截。默认安全策略严格禁止插件向沙箱以外的敏感系统目录随意写入文件。
- **解决方案**：
  - 将目标保存路径设置在沙箱目录内（例如 `测试代码/sandbox_benchmark/`）；
  - 或在客户端 MCP 配置的 `DSH_ALLOWED_ROOTS` 环境变量中添加您信任的工作目录。

---

## 4. 紧急一键状态重置

若因断电或外部进程意外崩溃导致本地工作区状态异常，可执行一键健康自愈：
```bash
# 1. 运行升级脚本自动热修复虚拟环境与注册状态
npm run upgrade

# 2. 验证修复结果
npm run doctor
```
系统将自动备份、重新检测并恢复全部 8 大维度健康状态。
