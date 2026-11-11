# 第四阶段 DSH 端到端真实能力分级审查报告

> **报告编号：** `AUDIT-R2-07-STAGE4-DSH-E2E-REVIEW`  
> **审计对象：** dsh-solidworks 在 DeepSeek Harness 宿主下的端到端调用链路、工具盘点与自主化等级评定  
> **归档目录：** `audit/full_project_round2/`  
> **审计性质：** 独立第三方产品集成与自动化成熟度审计  

---

## 一、端到端集成架构与链路核验

DSH 插件端到端调用链路分为四个核心层级：

```
[DSH Agent / 自然语言输入]
           │ (1) 自然语言提示 / Tool Call 决策
           ▼
[Node.js 插件宿主 (lib/index.js & policy.js)]
   ├─ 策略鉴权 (read/write/high 模式阻断)
   ├─ 路径沙箱规范化改写
   └─ JSON-RPC 管道转发
           ▼
[FastMCP 服务端 (mcp-server/server.py)]
   ├─ 参数 Schema 校验与解包
   ├─ CADTaskContext 事务生命周期托管
   └─ 调度 cad_graph_executor.py
           ▼
[STA COM Worker (sw_connect.py)]
           │ (4) 单线程调用 Dispatch 接口
           ▼
[SolidWorks 2026 SP4.1 物理建模引擎]
```

审计核验表明：链路物理连通性正常，JSON-RPC 消息往返时延在本地回环下小于 $10\text{ ms}$，宿主进程超时熔断与取消机制完整有效。

---

## 二、全量 73 项工具资产盘点与分类核销

经代码穿透核对，全量 73 项工具实现清单如下：

### 2.1 Node.js 本地特权 Meta Tools（2 项）
1. `solidworks_status`：查询当前连接状态、SolidWorks 版本、插件版本与当前打开文档；
2. `solidworks_confirm`：高危操作单次授权确认令牌机制。

### 2.2 FastMCP 服务端注册工具（71 项）
按功能领域细分：
- **健康检查与环境诊断 (4 项)：** `solidworks_health_check`, `solidworks_detect_installation`, `solidworks_get_system_info`, `solidworks_list_templates`；
- **文档生命周期与持久化 (7 项)：** `solidworks_new_document`, `solidworks_open_document`, `solidworks_save_document`, `solidworks_close_document`, `solidworks_export_file`, `solidworks_pack_and_go`, `solidworks_batch_export`；
- **2D/3D 草图绘制 (11 项)：** `solidworks_create_sketch_2d`, `solidworks_draw_line`, `solidworks_draw_circle`, `solidworks_draw_rectangle`, `solidworks_draw_arc`, `solidworks_add_sketch_relation`, `solidworks_add_dimension`, `solidworks_exit_sketch`, `solidworks_create_sketch_3d`, `solidworks_edit_sketch`, `solidworks_sketch_offset`；
- **基础与高级特征建模 (16 项)：** `solidworks_create_basic_part`, `solidworks_extrude_boss`, `solidworks_extrude_cut`, `solidworks_revolve_boss`, `solidworks_revolve_cut`, `solidworks_fillet`, `solidworks_chamfer`, `solidworks_linear_pattern`, `solidworks_circular_pattern`, `solidworks_mirror_feature` *(注：存在Bug)*, `solidworks_sweep_boss`, `solidworks_loft_boss`, `solidworks_create_reference_plane`, `solidworks_create_reference_axis`, `solidworks_create_coordinate_system`, `solidworks_shell`；
- **尺寸管理与参数修改 (6 项)：** `solidworks_list_dimensions`, `solidworks_get_dimension_value`, `solidworks_set_dimension_value`, `solidworks_identify_dimensions`, `solidworks_inspect_dimension_impact`, `solidworks_modify_dimension_safe`；
- **装配体与配合 (7 项)：** `solidworks_add_component`, `solidworks_set_component_fixed`, `solidworks_add_coincident_mate`, `solidworks_add_distance_mate`, `solidworks_add_concentric_mate`, `solidworks_export_assembly_bom`, `solidworks_replace_component_preserving_transform`；
- **工程图生成与审查 (5 项)：** `solidworks_generate_drawing`, `solidworks_review_drawing`, `solidworks_inspect_drawing`, `solidworks_review_active`, `cadstudio_build_dxf_preview_scene`；
- **质量测量与模型分析 (7 项)：** `solidworks_get_mass_properties`, `solidworks_measure_distance`, `solidworks_check_interferences`, `cadstudio_review_advanced_geometry`, `solidworks_exclude_reviewed_bodies`, `solidworks_rebuild_model`, `solidworks_force_rebuild`；
- **FeatureGraph IR 与高级图执行 (8 项)：** `solidworks_compile_feature_graph`, `solidworks_execute_feature_graph`, `solidworks_plan_cad_task`, `solidworks_validate_task_graph`, `solidworks_inspect_graph_state`, `solidworks_rollback_failed_feature`, `solidworks_query_feature_tree`, `solidworks_verify_model_quality`。

**核销结论：** 清单中 73 项工具与 `dsh-plugin.json`、`lib/policy.js` 100% 对齐，去重无冲突，风险等级全部显式声明。

---

## 三、AI CAD 自动化成熟度等级评估

参考 SAE 自动驾驶及工业自主系统分级，建立 AI CAD 五级能力成熟度模型：

| 成熟度等级 | 等级名称 | 核心特征定义 |
|:---:|:---|:---|
| **Level 1** | 工具辅助级 | AI 仅提供 API 参数建议，由人工在 SolidWorks 手动操作 |
| **Level 2** | 单步自动化 | AI 能够按序调用单个原子工具（如画圆、拉伸），但缺乏全局规划 |
| **Level 3** | 条件自动化 | AI 能根据明确规范生成 FeatureGraph IR，并由调度器在受控条件下自动建图、执行与物理回滚 |
| **Level 4** | 高度自主化 | AI 能根据模糊设计需求生成多方案、自动比较选优、自动迭代修改并在出错时自主调整策略自愈 |
| **Level 5** | 完全自主化 | 涵盖复杂装配体系统级协同、自动化仿真优化、自适应公差分析与无人出图 |

### 本次审计分级评定结论：
**当前 dsh-solidworks 项目真实能力处于 Level 3（条件自动化），历史宣称达到 Level 4 并不成立。**

**判定依据：**
1. **Level 3 能力已闭环验证：** 当用户或测试用例给出清晰的参数结构时，`cad_graph_executor.py` 能够成功执行拓扑排序并调度 SolidWorks 建立完整零件，若发生单步错误能够完成 Level 3 特征树逆序物理清除；
2. **Level 4 核心要素完全缺失：**
   - 无法应对非结构化模糊需求；
   - 缺失多方案自主规划与量化比较能力（无方案评分与权衡引擎）；
   - 缺失模型增量迭代修改能力（修改参数仅靠单尺寸写入，缺乏全局特征树再平衡）；
   - 缺失真正的闭环自愈能力（故障后仅能回滚删除，无法自主尝试替代建模路径）。

---

## 四、真实 DSH 用户使用体验与障碍审查

1. **首次使用策略阻断摩擦 (DEF-05 衍生)：**
   - 默认安装后处于 `read-only` 模式，新手用户发出“帮我画个零件”指令时，直接收到策略拒绝报错，若缺乏友好的向导文案，用户会误认为插件损坏；
2. **后台 SolidWorks 模态弹窗挂死风险：**
   - 若 SolidWorks 在建模过程中弹出“草图无法拉伸”、“尺寸重建错误”等 Windows 模态弹窗，会彻底阻塞 STA COM 工作线程，导致 DSH Agent 请求持续等待直到 30 秒超时，体验断裂；
3. **缺少交互式进度反馈：**
   - 当执行 8 级特征的复杂模型时，耗时约 $3 \sim 8\text{ s}$，期间缺乏流式步骤进度通知，Agent 端处于静默等待状态。

---

## 五、端到端审查最终裁决

### 裁决结论：
**PARTIALLY ACCEPTED（部分合格验收）**

### 演进路线指导：
要让系统从当前的 **Level 3** 稳步跃升至 **Level 4**，必须在第五阶段重点落地：
1. **多方案规划引擎 (S5-A)：** 开放式需求的结构化多方案生成与量化打分选优；
2. **自动迭代修改引擎 (S5-C)：** 基于特征影响域的非破坏性参数重构；
3. **综合多维质量评价系统 (S5-E)：** 涵盖几何、拓扑、工艺规范的自主评价机制。
