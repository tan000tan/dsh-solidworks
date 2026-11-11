# 运行环境实测基线核验报告 (01_ENVIRONMENT_BASELINE.md)

**执行时间**：2026-11-08 00:27 CST  
**核验方式**：系统实机命令直测（非历史引用）  

---

## 一、宿主环境实测参数

| 维度 | 实测值 | 验证命令与结果证据 | 兼容性评估 |
| :--- | :--- | :--- | :---: |
| **操作系统** | Windows 11 专业版/家庭版 (x64) | OS Build 26100/26200 | 完全支持 Win32/COM 子系统 |
| **Node.js 运行时** | `v24.21.0` | `node -v` -> `v24.21.0` | 完全满足 `>=22.12` 要求 |
| **Python 运行时** | `Python 3.13.16 (64-bit)` | `& 'D:\SWCAD-MCP\Python313\python.exe' --version` | 独立受信任环境，核心包已就绪 |
| **SolidWorks 安装** | SolidWorks 2026 SP04.1 (Build 34.4.1.1011) | `D:\Solidwork\SOLIDWORKS\SLDWORKS.exe` (FileVersion: 34.4.1.1011) | 原生 COM 服务器可用 |
| **SolidWorks 运行状态** | **待机 (Clean Standby)** | `Get-Process sldworks` 返回 0 进程 | 无用户交互冲突，具备隔离执行前提 |
| **磁盘剩余空间 (D:)** | **216,709,685,248 字节 (~201.8 GB)** | `Get-PSDrive D` | 空间充足，完全支撑物理冷备份与 CAD 生成 |
| **Git 仓库 HEAD** | `7d70bc090d5cef146ac3946bb062667ae30a4cc9` | `git rev-parse HEAD` | 属于 `release: finalize v0.2.0` |
| **Git 分支** | `main` | `git branch --show-current` | 基线分支明确 |

---

## 二、工作区原始状态基线

- **跟踪修改文件数**：16 项（`NOTICE`, `docs/USER_GUIDE.md`, `docs/verification.md`, `dsh-plugin.json`, `lib/discover.js`, `lib/index.js`, `lib/policy.js`, `tests/failure_injection_test.py`, `tests/mcp.test.js`, `tests/package.test.js`, `tests/probe-server.mjs`, `server.py`, `cad_task_context.py`, `dimension_manager.py`, `feature_graph_ir.py`, `sw_connect.py`）；
- **已暂存文件数**：0 项；
- **已删除文件数**：0 项；
- **冲突文件数**：0 项；
- **未跟踪条目数**：55 项（包含历史 audit 交付目录、阶段五高阶脚本与测试套件等）。
