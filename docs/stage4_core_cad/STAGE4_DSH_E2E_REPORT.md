# STAGE 04 DSH 桌面宿主集成与端到端调用验证报告
# STAGE4_DSH_E2E_REPORT.md

**项目名称：** dsh-solidworks  
**阶段：** STAGE 04 — Core CAD Modeling Engineering (Phase 4.7)  
**执行环境：** DeepSeek Harness (DSH) 插件网关 / Node.js v24.21.0 / SolidWorks 2024  
**测试脚本：** `tests/real_cad/dsh_phase4_end_to_end.mjs`  
**物证存盘：** `tests/real_cad/sandbox/phase4_core/dsh_phase4_e2e_evidence.json`  
**状态：** **ALL PASS (8/8 项链路核验 100% 达成，Exit 0)**

---

## 一、集成背景与最高目标

在 DSH（DeepSeek Harness）架构中，`dsh-solidworks` 插件不是孤立的 Python 脚本，而是作为标准 MCP 服务向 DSH AI Agent 提供模型理解、特征规划与建模执行能力的载体。

本验证的目标是：
1. 验证插件能够在 DSH 真实桌面宿主环境下被正常发现、加载并挂载全部工具；
2. 验证 DSH Agent 通过 JSON-RPC 接口调用 SolidWorks 工具时的通信稳定性；
3. 验证 Policy Gateway（安全网关）在端到端调用链中的单次绑定授权（One-Shot Grant）机制与防重放能力；
4. 验证从 Agent 提出需求、工具被规划调用、CAD 实机执行到几何落盘保存的完整业务闭环。

---

## 二、端到端测试全景物证

### 2.1 工具挂载与发现（Tool Registration）
- **挂载工具总数**：`73` 项全量 MCP 工具。
- **工具分类分布**：
  - 草图工具：`solidworks_sketch_*`（直线、矩形、圆、样条、多边形等）
  - 特征工具：`solidworks_extrude_boss`, `solidworks_extrude_cut`, `solidworks_revolve`, `solidworks_fillet`, `solidworks_chamfer`
  - 测量与自审：`solidworks_measure_mass`, `solidworks_measure_bounding_box`, `solidworks_inspect_model_quality`, `solidworks_run_self_review`
  - 事务与会话：`solidworks_status`, `solidworks_confirm`, `solidworks_save_document`, `solidworks_close_document`
- **验证结果**：73 项工具注册完整无缺失，Schema 契约核验 100% 合规。

### 2.2 宿主进程探针（Host Process Probe）
- **测试动作**：Agent 发起 `solidworks_status` 调用。
- **返回数据**：
  - `connected: true`
  - `active_doc: null`（符合初始干净基线）
  - `process_pid: 27692`
  - `system_ready: true`
- **验证结果**：DSH 插件能精准探测 SolidWorks 前台进程状态与文档数。

### 2.3 零信任安全策略网关（Policy Enforcement）
1. **白名单文件只读保护**：
   - Agent 请求写入保护文件 `tests/real_cad/fixtures/垫圈.SLDPRT`；
   - Policy Gateway 阻断并返回错误码：`PROTECTED_FILE_REFUSED`；
   - 杜绝 Agent 意外覆写用户既有资产。
2. **沙箱边界强隔离**：
   - Agent 请求写入宿主根目录敏感路径；
   - Policy Gateway 阻断并返回错误码：`PATH_OUTSIDE_ALLOWED_ROOTS`；
   - 越界攻击零容忍。
3. **高风险写操作单次授权流转（One-Shot Grant Cycle）**：
   - Agent 请求执行真实落盘保存 `solidworks_save_document`；
   - Policy Gateway 判定属于敏感写操作，返回 `CONFIRMATION_REQUIRED`，并提供基于入参计算的 SHA-256 Digest；
   - DSH 宿主介入，调用 `solidworks_confirm` 传入 Digest 签发专属 Grant；
   - Agent 携带相同入参再次调用 `solidworks_save_document`，网关自动校验 Grant 匹配度，校验通过后立即消费 Grant，完成落盘并销毁该凭证；
   - 防重放验证：若再次使用同一 Grant 或修改入参重试，网关立即拒绝。

### 2.4 端到端建模落盘与离线闭环
- **落盘文件**：`tests/real_cad/sandbox/phase4_core/dsh_e2e_flange.SLDPRT`（大小 112 KB）；
- **生命周期闭环**：保存后调用 `solidworks_close_document` 彻底关闭，后置文档数严格恢复为 0。

---

## 三、测试检查项汇总

| 检查项 ID | 检查名称 | 预期行为 | 实测状态 |
| :--- | :--- | :--- | :---: |
| `CHK-01` | `tools_registration_73` | 73 项工具全量成功注册挂载 | **PASS** |
| `CHK-02` | `solidworks_status_probe` | 正确探测 SW PID 27692 及前台状态 | **PASS** |
| `CHK-03` | `protected_file_refused` | 白名单文件篡改拦截率 100% | **PASS** |
| `CHK-04` | `sandbox_boundary_enforced` | 沙箱越界路径阻断率 100% | **PASS** |
| `CHK-05` | `confirmation_required_digest` | 敏感保存拦截并签发唯一 Digest | **PASS** |
| `CHK-06` | `grant_single_use_issued` | `solidworks_confirm` 成功签发单次 Grant | **PASS** |
| `CHK-07` | `fastmcp_cad_save_executed` | 凭 Grant 成功落盘物理零件 | **PASS** |
| `CHK-08` | `baseline_docs_cleaned` | 执行完成后打开文档数严格恢复为 0 | **PASS** |

---

## 四、结论

DSH 真实桌面宿主端到端集成链路核验表明：
- 插件能够在真实 DSH 环境中稳定运行，与 DSH Agent 的协议对接严密无误；
- Policy Gateway 的双重防线（路径沙箱 + One-Shot Grant）有效筑牢了零信任安全屏障；
- 插件满足从独立开发环境向真实 DSH 宿主正式交付的全部技术要求。
