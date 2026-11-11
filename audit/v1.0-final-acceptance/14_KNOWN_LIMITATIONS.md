# 已知局限性与发布前建议清单 (Known Limitations & Advisory)

**报告编号**：AUDIT-V1.0-14-KNOWN-LIMIT  
**审计基线**：Git HEAD `7d70bc090d5cef146ac3946bb062667ae30a4cc9`  
**级别说明**：非阻断性局限（P1/P2 级架构特性与生产部署注意事项）

---

## 一、系统与环境局限性 (System & Runtime Limitations)

### 1.1 COM 单线程模型 (STA) 队列并发特性
- **现状描述**：
  SolidWorks COM API 本质上属于 Windows 单线程单元 (Single-Threaded Apartment, STA)。
- **架构影响**：
  多个 MCP 客户端或并行 Agent 同时向插件发送建模请求时，系统不会并行操作 COM 句柄（并行可能导致 COM 内存冲突崩溃），而是通过 `STAWorker` 内部 FIFO 顺序任务队列排队执行。
- **运维建议**：
  在高频并发调用场景下，各任务耗时将线性累加。客户端可根据 `TASK_TIMEOUT`（默认 60s）合理配置调用超时阈值。

### 1.2 模态对话框 (Modal Dialogs) 阻塞风险
- **现状描述**：
  当加载包含损坏外部引用、缺失特定工程字体或非标准螺纹库的复杂装配体时，SolidWorks GUI 可能会弹窗提示用户确认。
- **架构防护**：
  插件在连接阶段默认开启静默模式（`swUserPreferenceToggle_e.swSilentMode`），可压制绝大多数常规告警；但极少数严重底层系统对话框仍可能需要人工前台干预确认。
- **建议**：
  在生产自动化流水线中，推荐在受控的基础模板库上运行全自动建模。

### 1.3 跨版本 ProgID 兼容性覆盖
- **现状描述**：
  当前物理实机环境配备 SolidWorks 2026 (Revision 34)。对 SolidWorks 2024 (Rev 32) 和 2025 (Rev 33) 的支持已通过 ProgID 动态映射表和兼容性模拟测试套件验证。
- **建议**：
  若最终用户部署环境为 2024 或 2025 版本，首次安装插件后建议运行 `solidworks_health_check` 进行一次就绪度握手。

---

## 二、发布前操作建议 (Pre-Release Checklist)

1. **版本发布权限释放**：
   当前仓库处于整改完毕待发布状态。用户唤醒后，仅需确认发布意图，执行：
   ```powershell
   git add -A
   git commit -m "chore(release): prepare v1.0.0 release candidate"
   git tag -a v1.0.0-rc1 -m "v1.0.0-rc1 release candidate after 5th round remediation"
   ```
2. **DSH 插件市场分发**：
   在 DeepSeek Harness 控制台中加载打包后的 `dsh-solidworks-plugin-1.0.0.tgz` 即可完成本地私有部署或提交至公共市场。
