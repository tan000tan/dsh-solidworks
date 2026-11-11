# dsh-solidworks 遗留风险与生产部署建议报告

**报告编号**: DSH-SW-RISK-FINAL-20261109  
**评估对象**: `dsh-solidworks` v1.0 正式候选版本  
**综合风险评级**: **低风险 (Low Risk) / 满足生产发布标准**

---

## 一、系统架构与运行环境遗留风险评估

虽然本项目在软件工程、安全鉴权、单文档归属保护和进程生命周期管理上已达成严格闭环，但由于其深度依赖底层宿主桌面 CAD 软件（Dassault Systèmes SolidWorks），仍存在以下客观技术特性需要运维与用户知悉：

### 1. SolidWorks COM 单线程套间 (STA) 与阻塞特性

- **风险特征**:
  SolidWorks 基于微软 COM 单线程套间（Single-Threaded Apartment, STA）架构。如果执行超大规模装配体生成、复杂自由曲面拟合或精细网格划分，COM 线程将处于物理计算忙碌状态，此时无法响应并发请求。
- **缓解机制**:
  - 插件内置 `get_sta_worker()`，通过独立的专用后台 STA 工作线程承载所有 COM 交互，与主 Node.js 事件循环完全异步解耦；
  - 配备看门狗超时机制（默认 60s~120s），超时后强制释放控制权，防止宿主死锁。

### 2. 用户自建工程模板与全局系统弹窗

- **风险特征**:
  虽然插件已在源码中将 `DeleteSelection2` 等内部调用全部切换为静默选项（选项 0），且默认关闭交互提示（`swApp.SetUserPreferenceToggle(swUserPreferenceToggle_e.swExtRefNoRegen, True)` 等）。但若用户本机安装了第三方侵入式 CAD 插件（如某些 CAM 辅助插件或企业 PDM 客户端），在新建文档或保存时可能会由第三方插件强行弹出 GUI 模态窗口。
- **生产规避建议**:
  - 在生产自动化工作站上，建议配置纯净的 SolidWorks 运行环境，禁用非必要的第三方启动加载项；
  - 确保默认零件/装配体/工程图模板文件路径有效且无损坏。

### 3. 多版本 SolidWorks API 细微差异

- **风险特征**:
  本项目已在 SolidWorks 2026 (SP 34.4.1) 上完成端到端全量物理实机取证，并向下兼容 SolidWorks 2022~2025。但在极少数旧版本（如 2021 之前）中，某些高级配合（如特定曲面相切或特定约束）的枚举常量可能略有差异。
- **生产规避建议**:
  - 推荐生产部署环境统一使用 SolidWorks 2024~2026 64 位版本；
  - 部署后首选运行 `solidworks_health_check` 进行版本与 COM 依赖预检。

---

## 二、生产环境安全配置与部署推荐准则

为在企业与团队生产环境中最大化发挥 `dsh-solidworks` 的价值并确保 100% 资产安全，建议遵循以下部署准则：

### 1. 严格落实最小特权策略 (Principle of Least Privilege)

在 DeepSeek Harness 配置文件（`cordis.patch.yml` 或宿主配置）中：
- **普通助理会话**: 默认保持 `mode: "read-only"`。AI 仅具备几何审查、DFM 分析、尺寸查询与装配体检查能力，完全杜绝模型被意外篡改的可能；
- **交互设计会话**: 配置为 `mode: "standard"`。允许 AI 协同建模、绘制草图与修改特征，但阻断磁盘物理保存与批量导出；
- **全自动出图/批处理任务**: 仅在专用受限沙箱中开启 `mode: "full"`。同时必须配置明确的 `allowedRoots`（如 `["D:\\Projects\\AutomatedCAD\\Sandbox"]`），严禁将系统盘根目录或用户主目录设为沙箱根目录。

### 2. Python 运行环境固定

- 生产环境建议在插件根目录建立独立 `.venv`，或在环境变量中显式配置 `DSH_SOLIDWORKS_PYTHON`；
- Python 版本推荐使用 3.11、3.12 或 3.13 64 位版本，确保 `pywin32` 正确注册（运行 `python Scripts/pywin32_postinstall.py -install`）。

### 3. 定期审计日志审查

插件在配置 `auditLogPath` 后，会自动将每一次工具调用的时间戳、工具名、参数 16-hex 哈希与放行/拦截结果写入日志。企业安全审计员可定期对日志进行分析，复核是否存在异常的越权探测或越界路径调用。
