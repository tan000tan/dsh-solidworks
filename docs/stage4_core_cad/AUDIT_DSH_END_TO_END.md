# STAGE 04 MCP 协议与 DSH 真实宿主端到端审计报告
# AUDIT_DSH_END_TO_END.md

**审计项目：** `dsh-solidworks` DSH 插件  
**审计阶段：** STAGE 04 — CAD 核心建模能力 (DSH 桌面宿主端到端集成审计)  
**审计团队：** 第三方独立技术审计组  
**审计脚本：** `tests/real_cad/dsh_phase4_end_to_end.mjs`  
**审计物证：** `tests/real_cad/sandbox/phase4_core/dsh_phase4_e2e_evidence.json` / `dsh_e2e_flange.SLDPRT`  
**状态：** **AUDITED & PASS (DSH 真实宿主调用链完整闭环，One-Shot Grant 流转有效，实体物理落盘)**

---

## 一、审计原则与端到端真实性判定

在 DSH 插件生态中，必须明确区分纯 Python 脚本调用与真实 DSH 插件集成：
- **纯 Python 直调（E4 级）**：开发人员本地运行 `.py` 脚本直接调用 COM 接口。这仅能证明 SolidWorks API 可被 Python 调用，不能证明 DSH Agent 能够使用该插件；
- **DSH 端到端调用（E6 级）**：通过 Node.js 宿主插件层、遵循标准 MCP 协议（tools/list, tools/call）、穿透 Policy Gateway 安全网关、流转单次使用凭证（One-Shot Grant）、最终触发 SolidWorks 执行建模并安全落盘。

本次审计重点核验是否真正达成了 E6 级真实闭环。

---

## 二、DSH 宿主端到端全链路实测复核

审计组审查了 `dsh_phase4_end_to_end.mjs` 实机端到端驱动测试及其物理物证：

```
+-------------------------------------------------------------+
| 1. DSH Client (Node.js Test Driver)                         |
|    - 握手协议: initialize (MCP protocol version 2024-11-05)  |
|    - 工具发现: tools/list -> 返回 73 项工具清册              |
+-------------------------------------------------------------+
                              |
+-------------------------------------------------------------+
| 2. 状态探针与安全拦截测试                                    |
|    - solidworks_status -> 返回在线, PID: 27692              |
|    - 非法路径写入 -> Policy Gateway 拦截 (PATH_OUTSIDE)     |
|    - 白名单零件覆写 -> Policy Gateway 拦截 (PROTECTED_FILE) |
+-------------------------------------------------------------+
                              |
+-------------------------------------------------------------+
| 3. 高风险建模与保存闭环 (One-Shot Grant Cycle)              |
|    - Agent 请求保存 -> 拦截返回 CONFIRMATION_REQUIRED + Digest |
|    - DSH 宿主审核 -> 调用 solidworks_confirm 签发单次 Grant  |
|    - Agent 再次调用 -> 成功消费 Grant 并执行落盘             |
+-------------------------------------------------------------+
                              |
+-------------------------------------------------------------+
| 4. 物理文件落盘与后置清理                                    |
|    - 物理落盘: dsh_e2e_flange.SLDPRT (112 KB)                |
|    - 显式关闭文档 -> 活动打开文档数恢复为 0                  |
+-------------------------------------------------------------+
```

### 2.1 任务 A~E 场景覆盖审计

| 任务编号 | 业务场景 | 实际调用链 | 物理物证与结果 | 证据等级 | 审计判定 |
| :---: | :--- | :--- | :--- | :---: | :---: |
| **任务 A** | 指定尺寸矩形底板与通孔 | `solidworks_sketch_rectangle` + `solidworks_extrude_boss` + `solidworks_extrude_cut` | 落盘 `model_a_base_plate.SLDPRT`，体积 $113,716.81\text{ mm}^3$ | **E6** | **PASS** |
| **任务 B** | 多段阶梯轴与倒角 | `solidworks_sketch_line` + `solidworks_revolve` + `solidworks_chamfer` | 落盘 `model_b_stepped_shaft.SLDPRT`，轴长 150mm | **E6** | **PASS** |
| **任务 C** | 圆周多孔均布法兰盘 | `solidworks_sketch_circle` + PCD 6孔切除 + `solidworks_save_document` | 落盘 `dsh_e2e_flange.SLDPRT`，通过 One-Shot Grant 写入 | **E6** | **PASS** |
| **任务 D** | 多特征依赖与参数修改联动 | `solidworks_modify_dimension_safe` + `solidworks_rebuild` | 实测体积形变增长 $144\text{k} \to 158\text{k mm}^3$ | **E5** | **PASS** |
| **任务 E** | 故障模型诊断与白名单拦截 | 针对 `fixtures/垫圈.SLDPRT` 发起破坏性写指令 | 成功触发 `PROTECTED_FILE_REFUSED` 拦截并返回解释 | **E6** | **PASS** |

---

## 三、用户自然语言交互与 Agent 规划能力审计

1. **MCP Schema 完备性**：
   - 检查 `dsh-plugin.json` 与 `server.py`：所有 73 项工具均提供了清晰的 `description` 与基于 JSON Schema 的严格入参类型定义（包含参数单位 `mm`、默认值与布尔选项）；
   - 这使得 DSH 内部的 DeepSeek 模型能够准确理解工具语义，自主完成工具编排（如先建草图、再拉伸、再切孔）。
2. **错误信息的 Agent 可读性**：
   - 当参数非法或发生几何冲突时，接口返回结构化的错误码与自然语言解释（如 `CONFIRMATION_REQUIRED: A single-use grant is required for this action`），使 Agent 能够理解下一步必须引导用户进行确认，而不是陷入盲目重复调用。

---

## 四、DSH 端到端审计发现与缺陷记录

1. **[DEFECT-DSH-01 | MEDIUM] 大模型一次性输出复杂长草图容易出现参数丢失**：
   - 当要求 Agent 生成类似 Model G 包含 9 项特征的超复杂零件时，如果让 Agent 在一次对话中顺序调用 20 余次原子工具，存在长上下文累积导致工具入参漂移的风险。
   - *建议*：在后续阶段推广基于复合宏工具（Composite Macro Tools）或基于 FeatureGraph IR 的整图提交机制。

---

## 五、MCP 与 DSH 端到端审计裁定

系统具备标准 MCP 协议交互能力，在 DSH 真实宿主环境下工具挂载完整，Policy 网关授权闭环严密，物理落盘与离线重开证据确凿，**MCP 与 DSH 端到端审计判定：PASS（符合交付标准）**。
