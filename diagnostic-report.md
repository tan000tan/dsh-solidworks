# DSH-SolidWorks 系统健康诊断报告 (Diagnostic Report)

- **生成时间**: 2026-11-11T08:38:35.458Z
- **总体状态**: ✅ 正常 (HEALTHY)
- **检测汇总**: 12 PASS / 0 WARN / 0 FAIL

---

## 诊断项目明细

| 序号 | 检查维度 | 状态 | 概要 | 说明与建议 |
|---|---|---|---|---|
| 1 | `OS_PLATFORM_ARCH` | 🟢 通过 | Windows 与 Node.js v24.21.0 环境合规 | 系统: Windows 10.0.26200 (x64), Node: v24.21.0  |
| 2 | `PYTHON_RUNTIME` | 🟢 通过 | Python 3.13.16 (独立虚拟环境 .venv) | 路径: D:\SWCAD-MCP\Python313\python.exe  |
| 3 | `COM_DEPENDENCIES` | 🟢 通过 | Windows COM 与 MCP 核心依赖已全部就绪 | win32com, pythoncom, comtypes, pydantic, mcp 校验通过  |
| 4 | `OPTIONAL_EXTENSIONS` | 🟢 通过 | 核心不受影响；按需扩展包未安装 (ezdxf, numpy, PIL, openpyxl, docx, pptx) | 提示：如需使用 DFM 制造报表或 DXF 轮廓解析，可运行 "npm run setup -- --optional"  |
| 5 | `SOLIDWORKS_REGISTRY` | 🟢 通过 | 已检测到 SOLIDWORKS 2026 SP04.1 | 程序路径: D:\Solidwork\SOLIDWORKS\SLDWORKS.exe (COM 已注册: true)  |
| 6 | `SOLIDWORKS_VERSION_TIER` | 🟢 通过 | 版本兼容支持：SolidWorks 2020-2026 矩阵 (当前识别: SW 2026 SP4) | 验证级别: PHYSICAL_VERIFIED (本机当前运行版本（已完成全量 CAD 几何物理闭环实机验证）)  |
| 7 | `STA_DESKTOP_PERM` | 🟢 通过 | Windows Default 桌面访问与 STA 工作线程权限正常 | 跨线程 STA 消息队列调度与安全重入锁校验通过  |
| 8 | `LIVE_COM_ECHO` | 🟢 通过 | SolidWorks 正在运行，COM 实时心跳响应正常 | 版本修订号: 34.4.1, 当前活动文档数: 0  |
| 9 | `DSH_CLIENT_INTEGRATION` | 🟢 通过 | DeepSeek Harness 客户端已成功挂载本插件 | 配置文件: C:\Users\***\.dsh\profiles\desktop\cordis.patch.yml  |
| 10 | `MCP_CONFIG_VALIDITY` | 🟢 通过 | MCP 客户端配置文件格式合规 | 文件: D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\dsh-mcp-config.json  |
| 11 | `MCP_TOOLSET_INTEGRITY` | 🟢 通过 | 73 项工具完整性校验通过 (2 个宿主策略工具 + 71 个核心 CAD 工具) | 命名空间: solidworks-cad, 声明工具数: 73  |
| 12 | `SANDBOX_ROOTS_SAFETY` | 🟢 通过 | 工作区读写沙箱安全边界校验通过 | 物理沙箱已就绪且可读写: D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\测试代码\sandbox_benchmark  |

---

> **脱敏声明**: 本诊断报告已自动对系统敏感路径与用户标识进行了脱敏处理，可安全提交用于技术诊断。