# STAGE 04 第二轮 DSH 宿主端到端能力分级穿透审计报告
# AUDIT_ROUND2_DSH_E2E.md

**审计项目：** `dsh-solidworks` DSH 插件  
**审计阶段：** STAGE 04 — CAD 核心建模能力 (DSH 宿主与 Agent 能力复核)  
**审计团队：** 第三方独立技术审计组  
**审计基准：** DSH Agent 四级能力评估模型 (Level 1 ~ Level 4)  
**测试脚本与物证：** `tests/real_cad/dsh_phase4_end_to_end.mjs` / `dsh_phase4_e2e_evidence.json`  
**状态：** **LEVEL 3 ACHIEVED / LEVEL 4 NOT ACHIEVED (具备基础单任务闭环能力，未达复杂任务成熟阶段)**

---

## 一、DSH 端到端四级能力评价体系

在评价 AI Agent 与专业 CAD 软件的集成时，不能将“接口连通”简单等同于“产品化就绪”。第二轮复核建立严格的四级能力标准：

- **Level 1：工具发现能力（Tool Discovery）**：宿主环境启动时，能够正确识别插件清单，准确发现并解析全部 MCP 工具 Schema；
- **Level 2：单步调用与安全受控能力（Single Invocation & Policy Gating）**：能够通过 stdio JSON-RPC 成功触发工具，Policy 网关能正确阻断越权操作；
- **Level 3：单任务业务闭环能力（Single-Task Delivery Cycle）**：Agent 能根据单一设计需求，调用一系列基础工具完成单个简单零件建模、授权并安全落盘；
- **Level 4：复杂任务稳定规划与容灾自愈能力（Complex Task Autonomous Stability）**：Agent 能在长链条（20+步）、多特征、依赖复杂、出现建模几何警告的情况下，自主诊断、参数校准、稳定交付工业级复杂装配件。

---

## 二、第二轮实测穿透核验数据

对 `dsh_phase4_end_to_end.mjs` 及实际交互链路进行穿透考核：

| 能力层级 | 评价指标 | 真实物证与实测表现 | 审计判定 |
| :---: | :--- | :--- | :---: |
| **Level 1** | **工具发现** | 73 项全量工具（71 项 FastMCP + 2 项 Node Meta）全部在 `tools/list` 中成功暴露，Schema 符合 JSON-RPC 规范 | **PASS (达成)** |
| **Level 2** | **调用与安全** | `solidworks_status` 正确返回在线 PID；非法路径被拒（`PATH_OUTSIDE`）；白名单被拒（`PROTECTED_FILE`）；One-Shot Grant 成功拦截与消费 | **PASS (达成)** |
| **Level 3** | **单任务闭环** | Agent 驱动圆盘拉伸、中心孔切除，通过授权成功落盘物理零件 `dsh_e2e_flange.SLDPRT`（112KB），重开一致 | **PASS (达成)** |
| **Level 4** | **复杂长链任务** | **实测缺失！** 面对 Model G 等 9 特征、20+ 步骤的复杂零件，由于单次工具粒度过细，极易在连续调用中丢失草图基准面或发生参数漂移 | **FAIL (未达成)** |

---

## 三、真实交互中的长流程断层分析

1. **原子工具粒度过细导致的“注意力稀释”**：
   - 目前建模接口均为原子级（`solidworks_new_document` $\to$ `solidworks_sketch_circle` $\to$ `solidworks_extrude_boss` $\to$ ...）；
   - 创建一个带加强筋和四孔的支架需要连续发起 15~20 次 MCP 调用；
   - 在真实大模型长上下文对话中，由于步骤过多，模型在第 10 步之后极易忘记前面草图绑定的平面名称或误改参数单位；
2. **错误自愈与反馈机制不成熟**：
   - 当调用 `solidworks_mirror_feature` 报错返回 `None` 时，Agent 无法从报错中获知“是 Mark 传错还是基准面名称不匹配”，通常只能向用户输出原始报错或死循环重试；
3. **缺少复合宏工具（Macro Composite Tools）**：
   - 缺少类似 `solidworks_create_flange_parametric(pcd, holes_count, ...)` 这样的一键工业级复合工具，也没有在 DSH 端开放 FeatureGraph IR 的整体提交入口。

---

## 四、DSH 端到端审计结论

第一轮报告直接声称“DSH 端到端验证 100% 通过、已具备成熟产品化能力”，**严重夸大了实际水平**。
真实的审计评定应为：
- **插件目前仅达到了 Level 3 水平（具备基础工具发现、单次受控调用与简单零件落盘闭环）**；
- **尚未达到 Level 4 水平（不具备稳定、自主完成复杂多步骤工业机械全流程建模的能力）**；
- **后续演进方向**：必须在第五阶段引入复合宏工具与图形化任务规划器，降低 Agent 交互步骤密度。
