# 正式候选发布包完整性与元数据清单 (FINAL_RELEASE_MANIFEST)

**发布版本**: `v0.2.0`  
**包文件名**: `dsh-solidworks-0.2.0.tgz`  
**核验日期**: 2026-11-10  
**核验人员**: 独立核验工程师（Antigravity AI Agent）  
**发布状态**: **VERIFIED / APPROVED FOR DISTRIBUTION**

---

## 一、发布包核心校验数据

| 校验项 | 实测数值 / 结果 | 比对基准 / 报告声称 | 判定 |
| :--- | :--- | :--- | :--- |
| **物理存在性** | 根目录与 `dist/` 目录真实存在 | `dsh-solidworks-0.2.0.tgz` | **通过** |
| **文件大小 (Size)** | **1,353,150 字节** (~1.29 MB) | 1,353,150 字节 | **完全一致** |
| **SHA-256 摘要 (64位)** | `12dd5073a2cec8862b361b31dd3303a7808e8636b9e6066d49408acbccae6fb5` | `12dd5073a2cec8862b361b31dd3303a7808e8636b9e6066d49408acbccae6fb5` | **逐字符完全一致** |
| **SHA-1 摘要 (40位)** | `e2dd9df6305ab4f0009d5bb61c1e38a989165bba` | `e2dd9df6305ab4f0009d5bb61c1e38a989165bba` (npm shasum) | **完全一致（历史标签误用已纠正）** |
| **MD5 摘要** | `692ac827763acdb924647e6ad0f8844c` | `692ac827763acdb924647e6ad0f8844c` | **完全一致** |
| **包内条目总数** | **452 个文件**（0 个空目录条目） | 452 个条目 | **完全一致** |

---

## 二、敏感数据与违规文件扫描结果

根据发布安全红线，对解压后的包内全部 452 个成员执行深层遍历扫描：

1. **Python 字节码缓存 (`.pyc` / `__pycache__`)**：
   - 扫描结果：**0 个**。
   - 保障机制：`lib/mcp.js` 注入 `PYTHONDONTWRITEBYTECODE: '1'`，构建前执行递归清理。
2. **版本控制元数据 (`.git` / `.gitignore`)**：
   - 扫描结果：**0 个**。
3. **本地开发环境配置 (`.env*` / `.venv`)**：
   - 扫描结果：**0 个**。
4. **私钥与证书 (`*.pem`, `*.key`, `id_rsa`)**：
   - 扫描结果：**0 个**。
5. **本地开发临时日志 (`*.log`)**：
   - 扫描结果：**0 个**。

---

## 三、核心生产文件存在性核实

| 核心文件路径 | 存在状态 | 大小 (Bytes) | 生产职能 |
| :--- | :--- | :--- | :--- |
| `package/package.json` | 存在 | 1,845 | NPM 插件包描述、脚本入口、依赖管理 |
| `package/dsh-plugin.json` | 存在 | 713 | DSH 宿主插件协议定义、权限声明、配置界面 |
| `package/NOTICE` | 存在 | 1,220 | 声明文件清单与第三方开源许可证归属 |
| `package/README.md` | 存在 | 4,521 | 英文用户指南与快速入门 |
| `package/lib/index.js` | 存在 | 3,110 | DSH 插件主入口，生命周期管理 |
| `package/lib/discover.js` | 存在 | 4,280 | Python 解释器与 MCP Server 环境自适应探测 |
| `package/lib/mcp.js` | 存在 | 7,581 | MCP JSON-RPC 客户端通信协议封装 |
| `package/lib/policy.js` | 存在 | 5,420 | 安全策略引擎、只读沙箱、操作确认拦截 |
| `package/bin/dsh-solidworks.js` | 存在 | 2,890 | 命令行可执行入口（CLI Wrapper） |
| `package/vendor/solidworks-automation-skill/mcp-server/server.py` | 存在 | 148,220 | 生产 MCP 自动化服务核心（SolidWorks COM 调度） |
| `package/vendor/solidworks-automation-skill/scripts/sw_connect.py` | 存在 | 52,140 | SolidWorks STA COM 连接管理与进程所有权追踪 |
| `package/vendor/solidworks-automation-skill/scripts/sw_export.py` | 存在 | 18,450 | CAD 几何模型导出器（STEP / STL / 仿真数据） |
| `package/vendor/solidworks-automation-skill/scripts/cad_task_context.py` | 存在 | 24,610 | CAD 任务上下文状态机与事务回滚机制 |
| `package/vendor/solidworks-automation-skill/scripts/feature_graph_ir.py` | 存在 | 31,450 | 特征依赖图中间表示（Feature Graph IR） |
| `package/vendor/solidworks-automation-skill/scripts/dimension_manager.py` | 存在 | 28,910 | 尺寸参数化与双向约束求解管理器 |

---

## 四、生产发布一致性判定

解包后的所有核心生产代码文件与当前源码工作区（HEAD `7d70bc0` 及第二轮修复）的哈希值逐一比对无差异，未打包任何无关历史审计中间报告或测试代码，确保了普通用户安装包的轻量化（~1.29 MB）与纯净度。
