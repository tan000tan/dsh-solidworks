# 功能能力矩阵

本页列出插件当前注册的**全部 71 个工具**（19 个 read、26 个 write、26 个 high）。本页由
`audit/promotion-phase/03-local-remediation/gen-feature-matrix.cjs` 从运行时注册表与源码生成，代码与文档一旦不同步，生成器就会失败。

在这 71 个工具之外，插件自身还注册了两个 DSH 宿主 meta 工具：`solidworks_status` 与 `solidworks_confirm`。后者恒以
`SELF_APPROVAL_PROHIBITED` 失败关闭，存在的意义是让调用方能够证明它无法自我授权。

## 状态列怎么读

| 状态 | 含义 |
| --- | --- |
| `verified` | 在真实 SolidWorks 2026 SP4.1 会话中经真实 COM 到达该工具，且调用无错误返回。带 *(部分)* 标记表示主路径可用，但某个具体枚举值或字段仍然失败，括号里给出缺陷编号。 |
| `automated-test-passed` | 被离线自动化套件覆盖（功能测试，或实现被 mock 时的策略层测试）。 |
| `mock-only` | 仅用假 COM 层覆盖，从未接触真实会话。 |
| `unverified` | 没有任何执行证据。 |
| `failed` | 已知失败。 |
| `known-limitation` | 在文档写明的限制内可用。 |
| `blocked` | 在本环境无法执行。 |

"真实 SolidWorks"列沿用 `audit/promotion-phase/04-regression-validation/l4-real-solidworks.md` 记录的 71 工具全量真机审计基线（对 SolidWorks 2026 SP4.1、COM revision 34.4.1
共发起 206 次 MCP 调用）：**33 个 `verified`**（其中 **7 个标注 *部分***：主路径通过，但某个具体枚举值或字段仍失败，单元格里给出缺陷编号）、
**13 个 `failed`**、**24 个 `blocked`**（环境无法满足该工具的前置条件，不等于工具本身损坏）、**1 个 `known-limitation`**，另有
**14 条带复现步骤的缺陷**。在 **v0.3.3 定向真机复测**（`audit/v033-targeted-l4/l4-results.json`）中重新实测并通过的工具（`solidworks_connect`、`solidworks_open_document`、`solidworks_add_component`、`solidworks_add_coincident_mate`、`solidworks_shell`、`solidworks_export_assembly_bom`）已显式标注`（v0.3.3 定向复测通过）`，其余条目维持沿用自 v0.3.2 的历史基线状态。它证明的是"在一台机器上可达且行为符合记录"，不是其他模型上的几何正确性保证。

风险等级来自 `lib/policy.js` 的 `RISK_TABLE`：19 个 read、26 个 write、26 个 high。模式门禁由风险等级推出：
read 工具需 `read-only` 及以上，write 工具需 `standard` 及以上，high 工具需 `full` 且每次调用都要 DSH 宿主界面人工确认。默认 `read-only` 模式下，
只有 19 个 read 工具会被发布给模型。

自动化测试覆盖：26 项有功能测试引用，19 项只出现在策略/宿主层测试里，25 项无任何引用。有引用只代表
测试文件里出现了该工具名，不代表测试断言了真实 SolidWorks 行为。

### 文档管理 (4)

| 工具 | 用途 | 前置条件 | 参数（必填 / 可选） | 返回 | 风险 | 模式门禁 | 自动化测试 | 真实 SolidWorks | 已知限制 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `solidworks_new_document` | 用模板新建零件/装配体/工程图文档 | 无需打开文档/无额外前置（源码未见 _active_*_required 调用） | 无 / `doc_type`, `template_path` | `status`, `document` | **write** | standard 及以上 | 策略层引用 1 处（非功能测试） | `verified` | 依赖模板存在 |
| `solidworks_open_document` | 按绝对路径打开文档，供后续 MCP 工具使用 | 无需打开文档/无额外前置（源码未见 _active_*_required 调用） | `path` / `read_only`, `silent` | `status`, `document` | **write** | standard 及以上 | 策略层引用 16 处（非功能测试） | `verified`（v0.3.3 定向复测通过：D-02 已修复） | 写操作：会改变当前活动文档 |
| `solidworks_close_documents` | 在沙箱边界内安全关闭本会话拥有的文档 | 需文档由本会话打开 | 无 / `close_all`, `document_path`, `title`, `save_changes` | `status`, `closed`, `force_discard` | **high** | full + 宿主人工确认 | `automated-test-passed`（功能测试 12 处） | `verified` | HIGH：可能丢弃未保存修改（force_discard） |
| `solidworks_import_step_part` | 导入 STEP 为新多实体零件并另存，不改源文件 | 需输入 STEP 文件；PS 子进程 | `expected_document_path`, `step_path`, `output_path` / 无 | `status`, `process_id`, `save_requested`, `manual_review_required`, `saved`, `warnings`, `bodies[]`, `document` | **high** | full + 宿主人工确认 | 无 | `failed`（D-14） | PS 子进程；导入选项需恢复 |

### 零件读取 (4)

| 工具 | 用途 | 前置条件 | 参数（必填 / 可选） | 返回 | 风险 | 模式门禁 | 自动化测试 | 真实 SolidWorks | 已知限制 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `solidworks_list_edges` | 列出模型边线的几何属性（长度/中点/方向/直径/凸凹） | 需打开零件(.SLDPRT) | 无 / `axis`, `circular`, `diameter_mm`, `diameter_tolerance_mm`, `min_length_mm`, `max_length_mm`, `limit`, `include_convexity` | `status`, `edge_count`, `edges`, `errors`, `total_edge_count`, `matched_count`, `returned_count`, `truncated`, `filter`, `rejected_sample` | **read** | read-only 及以上 | 策略层引用 1 处（非功能测试） | `failed`（D-05） | 大模型边数多时结果截断 |
| `solidworks_document_units` | 读取并可修改当前文档的线性/角度单位 | 需打开文档 | 无 / `linear_unit`, `angular_unit`, `decimals` | `linear_unit_enum`, `angular_unit_enum`, `decimals`, `status`, `units_before`, `changes_applied`, `units_after`, `document`, `note` | **write** | standard 及以上 | 策略层引用 1 处（非功能测试） | `verified` | 改单位会改文档，属写操作 |
| `solidworks_inspect_hole_features` | 读取 B-Rep 孔、复合段、槽圆弧与可选孔位验收信息 | 需打开零件(.SLDPRT) | 无 / `expected_holes`, `position_tolerance_mm`, `diameter_tolerance_mm` | `status`, `measurements`, `position_checks`, `document` | **read** | read-only 及以上 | 策略层引用 1 处（非功能测试） | `verified`（部分：D-12） | 只读 B-Rep 解析 |
| `solidworks_inspect_native_geometry` | 读取实体名称、包围盒、体积、错误与组件变换，不保存 | 无需保存，只读；PS 子进程 | `expected_document_path` / 无 | `bodies[]`, `boundingBox`, `volume`, `errors[]`, `components[]` | **read** | read-only 及以上 | 策略层引用 2 处（非功能测试） | `verified` | PS 子进程 + 原生 COM，非纯 COM |

### 装配体 (10)

| 工具 | 用途 | 前置条件 | 参数（必填 / 可选） | 返回 | 风险 | 模式门禁 | 自动化测试 | 真实 SolidWorks | 已知限制 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `solidworks_interference_check` | 对当前装配体做干涉检测并列出每处干涉 | 需打开装配体(.SLDASM) ；需装配体中≥2 个组件 | 无 / `treat_subassemblies_as_components`, `treat_coincidence_as_interference` | `status`, `interference_count`, `items`, `severity`, `manual_review_required`, `options`, `treat_subassemblies_as_components`, `treat_coincidence_as_interference`, `errors`, `path` | **read** | read-only 及以上 | 策略层引用 1 处（非功能测试） | `verified`（部分：D-11） | 需装配体；重合接触可能误报（options 可调） |
| `solidworks_add_component` | 把已有零件/子装配加入当前装配体，可固定 | 需打开装配体(.SLDASM) | `path` / `x_mm`, `y_mm`, `z_mm`, `config_name`, `fix_component` | `status`, `component`, `fixed`, `component_count`, `document` | **write** | standard 及以上 | 无 | `verified`（v0.3.3 定向复测通过：D-03a 归属登记与切回父装配） | 仅加入已有文件，不建新几何 |
| `solidworks_set_component_fixed` | 按名称关键字固定或浮动装配体组件 | 需打开装配体(.SLDASM) | `component_keyword` / `fixed` | `status`, `fixed`, `component`, `document` | **write** | standard 及以上 | 无 | `blocked` — PermissionError/DEF-SEC-01，被 D-03 归属缺陷阻断 | 按名称关键字匹配，可能歧义 |
| `solidworks_add_coincident_mate` | 在两个组件之间添加重合配合 | 需打开装配体(.SLDASM) | `component_a_keyword`, `component_b_keyword` / `feature_a_name`, `feature_b_name`, `mate_name` | `status`, `mate_created`, `mate_name`, `added_mates`, `mate_features`, `document` | **write** | standard 及以上 | 无 | `verified`（v0.3.3 定向复测通过：D-08/D-03a） | 依赖命名基准面/特征存在 |
| `solidworks_add_distance_mate` | 在两个组件的命名基准面/特征间添加距离配合 | 需打开装配体(.SLDASM) ；需两个组件内存在命名基准面/特征 | `component_a_keyword`, `component_b_keyword` / `feature_a_name`, `feature_b_name`, `distance_mm`, `mate_name` | `status`, `error_code`, `mate_created`, `mate_features_before`, `mate_features_after`, `suggestion`, `mate_name`, `added_mates`, `distance_mm`, `component_a` | **write** | standard 及以上 | 无 | `verified` | 依赖命名基准面/特征 |
| `solidworks_add_concentric_mate` | 按匹配圆柱面在两个组件间添加同心配合 | 需打开装配体(.SLDASM) ；需两个组件存在可匹配圆柱面 | `component_a_keyword`, `component_b_keyword` / `radius_a_min_mm`, `radius_a_max_mm`, `radius_b_min_mm`, `radius_b_max_mm`, `lock_rotation`, `mate_name` | `status`, `error_code`, `mate_created`, `mate_features_before`, `mate_features_after`, `suggestion`, `mate_name`, `added_mates`, `lock_rotation`, `component_a` | **write** | standard 及以上 | 无 | `blocked` — RuntimeErrorActive document must be an assem… | 依赖圆柱面匹配 |
| `solidworks_add_rotary_motor` | 在当前装配体建运动算例并加恒速旋转马达 | 需打开文档 ；需装配体且运动算例可建 | `shaft_component_keyword`, `rotor_component_keyword` / `shaft_radius_min_mm`, `shaft_radius_max_mm`, `rotor_radius_min_mm`, `rotor_radius_max_mm`, `rpm`, `study_name`, `motor_name`, `duration_seconds`, `calculate`, `play` | `status`, `study_name`, `motor_name`, `motor_feature_created`, `calculated`, `rpm`, `shaft_component`, `rotor_component`, `document` | **write** | standard 及以上 | 无 | `blocked` — comtypes+Motion 类型库缺失，且装配非 ActiveDoc | 仅恒速旋转马达 |
| `solidworks_inspect_motion_studies` | 读取运动算例定义、马达/力数量与结果状态 | 需打开装配体(.SLDASM) | 无 / 无 | `status`, `motion`, `document` | **read** | read-only 及以上 | 策略层引用 1 处（非功能测试） | `blocked` — 同上：RuntimeErrorActive document must be an as… | 只读 |
| `solidworks_validate_motion_study` | 校验运动算例类型、时长、马达数量、结果存在性与新鲜度 | 需打开装配体(.SLDASM) | 无 / `study_name`, `expected_study_type`, `minimum_duration_seconds`, `minimum_motor_count`, `require_results` | `status`, `motion`, `document` | **read** | read-only 及以上 | 策略层引用 1 处（非功能测试） | `blocked` — 同上 | 仅校验定义/结果元数据 |
| `solidworks_replace_component_preserving_transform` | 按精确实例名替换固定组件，保留变换并校验其余组件 | 需按实例名定位组件；PS 子进程 | `expected_document_path`, `component_name`, `replacement_path` / `configuration` | `status`, `components[]`, `transform_preserved`, `document` | **high** | full + 宿主人工确认 | 无 | `blocked` — native-wire 前置不满足（目标必须已存在且 ActiveDoc） | PS 子进程；仅固定组件 |

### 特征树 (7)

| 工具 | 用途 | 前置条件 | 参数（必填 / 可选） | 返回 | 风险 | 模式门禁 | 自动化测试 | 真实 SolidWorks | 已知限制 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `solidworks_compile_feature_graph` | 把 Feature Graph IR DAG 编译成确定性执行计划 | 纯离线编译，无需 SolidWorks | `graph` / 无 | `status`, `graph_id`, `target_part_name`, `node_count`, `execution_plan` | **read** | read-only 及以上 | `automated-test-passed`（功能测试 4 处） | `failed` | 只编译不执行，不校验几何可构建性 |
| `solidworks_execute_feature_graph` | 在真实 SolidWorks 中执行已验证的 Feature Graph IR DAG | 无需打开文档/无额外前置（源码未见 _active_*_required 调用） | `graph` / `output_path`, `auto_rollback`, `collect_metrics`, `close_on_finish` | `success`, `status`, `execution_id`, `graph_id`, `target_part_name`, `total_nodes`, `executed_count`, `duration_ms`, `created_document`, `succeeded`, `node_records`, `feature_type`, `feature_name`, `created_cad_entity`, `error_type`, `error_message`, `details` | **high** | full + 宿主人工确认 | `automated-test-passed`（功能测试 6 处） | `failed` | 需实机执行；失败可自动回滚；未实机验证 |
| `solidworks_fillet` | 按几何过滤条件（轴/长度/凸凹）选边并倒圆角，支持 dry_run 预演 | 由 geometric 过滤条件自动选边，无需手选 | `radius_mm` / `axis`, `min_length_mm`, `max_length_mm`, `convex_only`, `concave_only`, `dry_run` | `status`, `edge_spec`, `selected_count`, `selected_edges`, `rejected_count`, `rejected_sample`, `errors`, `suggestion`, `dry_run`, `feature_created`, `feature_name`, `document` | **write** | standard 及以上 | `automated-test-passed`（功能测试 1 处） | `verified` | 文档仅标 VERIFIED_IN_MOCK；半径过大易自交失败 |
| `solidworks_chamfer` | 按几何过滤条件选边并倒角 | 由 geometric 过滤条件自动选边，无需手选 | `distance_mm` / `angle_deg`, `axis`, `convex_only`, `concave_only`, `dry_run` | `see tool schema` | **write** | standard 及以上 | `automated-test-passed`（功能测试 1 处） | `failed`（D-06） | 文档仅标 VERIFIED_IN_MOCK |
| `solidworks_shell` | 按统一壁厚把当前零件抽壳 | 需打开零件(.SLDPRT) | `thickness_mm` / `face_to_remove` | `status`, `feature_created`, `error_code`, `suggestion`, `feature_name`, `thickness_mm`, `open_face` | **write** | standard 及以上 | `automated-test-passed`（`v032_cad_remediation_test.py`、`v033_remediation_test.py`） | `verified`（v0.3.3 定向复测通过：D-04 `VT_VOID` 已修复） | 壁厚过大/不可构建时正确返回 `feature_created=false` |
| `design_spec_build` | 按已校验的设计规格构建 SolidWorks 零件 | 需已校验的规格文件；会新建/修改零件 | `spec_path` / `output_path`, `template_path`, `apply_fillets`, `verify_geometry` | `validation`, `errors`, `warnings`, `source_path`, `type`, `feature`, `ok`, `status`, `steps`, `verification`, `hole_count`, `mass_g`, `fillet_results`, `measurements` | **write** | standard 及以上 | 策略层引用 2 处（非功能测试） | `failed` | 受规格 schema 限制，无法表达任意特征 |
| `solidworks_exclude_reviewed_bodies` | 用原生删除实体特征排除指定实体，保留可编辑历史 | 需明确实体名清单；PS 子进程 | `expected_document_path`, `body_names` / `feature_name` | `status`, `excluded[]`, `bodies[]`, `document` | **high** | full + 宿主人工确认 | 无 | `blocked` — 同上：Active document target mismatch | PS 子进程；删除实体不可逆（不保存） |

### 草图 (1)

| 工具 | 用途 | 前置条件 | 参数（必填 / 可选） | 返回 | 风险 | 模式门禁 | 自动化测试 | 真实 SolidWorks | 已知限制 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `solidworks_sketch_and_extrude` | 在指定基准面上画圆/矩形/槽/多边形并拉伸成凸台或切除 | 需打开零件(.SLDPRT) | `depth_mm` / `plane_name`, `shape`, `center_x_mm`, `center_y_mm`, `radius_mm`, `width_mm`, `height_mm`, `corner_x2_mm`, `corner_y2_mm`, `slot_end_x_mm`, `slot_end_y_mm`, `sides`, `midplane`, `cut`, `feature_name` | `status`, `task_id`, `shape`, `feature_created`, `feature_name`, `sketch_name`, `depth_mm`, `operation`, `document`, `error_type` | **write** | standard 及以上 | `automated-test-passed`（功能测试 11 处） | `verified` | 仅圆/矩形/槽/多边形四类轮廓 |

### 拉伸切除旋转 (4)

| 工具 | 用途 | 前置条件 | 参数（必填 / 可选） | 返回 | 风险 | 模式门禁 | 自动化测试 | 真实 SolidWorks | 已知限制 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `solidworks_create_basic_part` | 生成简单圆柱或方块零件，可指定颜色与保存路径 | 需打开零件(.SLDPRT) | 无 / `shape`, `output_path`, `plane_name`, `width_mm`, `height_mm`, `radius_mm`, `depth_mm`, `color` | `status`, `task_id`, `shape`, `sketch_quality`, `rebuild_ok`, `feature_created`, `feature_name`, `appearance_ok`, `saved`, `output_path` | **write** | standard 及以上 | `automated-test-passed`（功能测试 19 处） | `verified` | 仅圆柱/方块两种简单形体 |
| `solidworks_revolve` | 把草图轮廓绕轴旋转生成回转实体 | 需打开零件(.SLDPRT) | `sketch_name` / `angle_deg`, `axis_sketch_name` | `status`, `feature_created`, `suggestion`, `feature_name`, `angle_deg`, `document` | **write** | standard 及以上 | 无 | `failed` | 文档仅标 VERIFIED_IN_MOCK（FEATURE_MATRIX.md:24-32） |
| `solidworks_create_hole_feature` | 在当前零件创建受约束的盲孔/通孔/复合孔或半圆槽 | 需打开零件(.SLDPRT) ；需在零件上定位孔位（可选已有草图/点） | `feature_kind` / `center_x_mm`, `center_y_mm`, `diameter_mm`, `depth_mm`, `secondary_diameter_mm`, `secondary_depth_mm`, `included_angle_deg`, `slot_end_x_mm`, `slot_end_y_mm`, `plane_name`, `feature_name` | `status`, `feature_evidence`, `document` | **write** | standard 及以上 | 无 | `verified` | 孔位约束依赖输入；未实机验证 |
| `solidworks_build_round_sweeps` | 创建原生方程路径圆截面扫描及矩形拉伸（严格规格，不保存） | ready), process_id, save_requested=false, manual_review_required, created[{name,feature_type,path_length_mm,expected_length_mm,diameter_mm}\ | `expected_document_path`, `spec_path` / `dry_run` | `ready`, `process_id`, `save_requested`, `manual_review_required`, `created[]` | **write** | standard 及以上 | 未分类（0 处） | `verified` | 无（tests/ 无任何引用） |

### 阵列镜像 (2)

| 工具 | 用途 | 前置条件 | 参数（必填 / 可选） | 返回 | 风险 | 模式门禁 | 自动化测试 | 真实 SolidWorks | 已知限制 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `solidworks_pattern` | 对已有特征做线性或圆周阵列 | 需打开零件(.SLDPRT) ；需目标特征已存在（按 feature_name） | `feature_name` / `pattern_type`, `count`, `spacing_mm`, `direction`, `axis_name`, `angle_deg`, `equal_spacing` | `status`, `suggestion`, `feature_created`, `feature_name`, `pattern_type`, `count`, `seed_feature` | **write** | standard 及以上 | 无 | `failed`（D-07） | 文档仅标 VERIFIED_IN_MOCK；依赖 feature_name |
| `solidworks_mirror_feature` | 以基准面镜像已有特征 | 需打开零件(.SLDPRT) ；需目标特征与基准面存在 | `feature_name` / `mirror_plane_name` | `status`, `feature_created`, `suggestion`, `feature_name`, `mirror_plane`, `source_feature` | **write** | standard 及以上 | `automated-test-passed`（功能测试 2 处） | `verified` | 文档仅标 VERIFIED_IN_MOCK |

### 参数修改 (4)

| 工具 | 用途 | 前置条件 | 参数（必填 / 可选） | 返回 | 风险 | 模式门禁 | 自动化测试 | 真实 SolidWorks | 已知限制 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `solidworks_update_dimension` | 更新指定名称尺寸，重建并返回改前/改后值 | 需打开文档 | `dimension_name`, `value_mm` / `configuration_mode`, `configuration_names`, `rebuild`, `save` | `success`, `dimension`, `configuration_mode`, `configuration_names`, `requested_mm`, `before_mm`, `after_mm`, `set_status`, `set_status_label`, `rebuild_success`, `save_requested`, `save_success` | **write** | standard 及以上 | `automated-test-passed`（功能测试 1 处） | `verified` | 按精确名称匹配尺寸，名称不对即失败 |
| `solidworks_identify_dimensions` | 枚举模型特征与草图里的全部尺寸 | 需打开文档 | 无 / `feature_name` | `status`, `count`, `dimensions`, `name`, `feature_name`, `feature_type`, `value_mm`, `is_driven`, `dim_type`, `dimension_map`, `model_ir`, `ir_available` | **read** | read-only 及以上 | `automated-test-passed`（功能测试 6 处） | `verified`（部分：D-12） | 大模型尺寸多时结果大 |
| `solidworks_inspect_dimension_impact` | 分析改某个尺寸可能影响的下游特征 | 需打开文档 | `dimension_name` / 无 | `dimension`, `owner_feature`, `owner_feature_index`, `total_features`, `potential_impacted_features`, `impact_count` | **read** | read-only 及以上 | `automated-test-passed`（功能测试 8 处） | `verified` | 基于特征顺序推断，非真实重建影响 |
| `solidworks_modify_dimension_safe` | 带影子备份与自动回滚的安全批量尺寸修改 | 需打开文档 | `updates` / `auto_rollback`, `rebuild`, `save`, `configuration_mode` | `status`, `rebuild_success`, `save_success`, `modified_count`, `before_values_mm`, `after_values_mm`, `applied_details`, `architecture`, `updates`, `rollback_performed`, `error` | **high** | full + 宿主人工确认 | `automated-test-passed`（功能测试 8 处） | `blocked` — PermissionError/DEF-SEC-01（D-03），未能进入批量改尺寸路径 | HIGH：写文件+重建，失败靠影子备份回滚 |

### 测量 (2)

| 工具 | 用途 | 前置条件 | 参数（必填 / 可选） | 返回 | 风险 | 模式门禁 | 自动化测试 | 真实 SolidWorks | 已知限制 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `solidworks_mass_properties` | 读取当前文档的质量、体积、表面积、质心与惯性矩 | 需打开文档 | 无 / `density_kg_m3` | `units`, `mass_g`, `volume_mm3`, `surface_area_mm2`, `center_of_mass_mm`, `moment_of_inertia_kg_mm2`, `density_kg_m3`, `material`, `material_assigned`, `warnings`, `errors` | **read** | read-only 及以上 | 策略层引用 9 处（非功能测试） | `verified` | 未分配材料时按 1000 kg/m³ 估算，不可直接用于工程判断 |
| `solidworks_bounding_box` | 读取当前文档的毫米包围盒，检查尺寸是否超范围 | 需打开文档 | 无 / 无 | `units`, `min_corner_mm`, `max_corner_mm`, `size_mm`, `diagonal_mm`, `errors` | **read** | read-only 及以上 | 策略层引用 1 处（非功能测试） | `verified` | 仅轴对齐包围盒，非最小包围盒 |

### 属性 (5)

| 工具 | 用途 | 前置条件 | 参数（必填 / 可选） | 返回 | 风险 | 模式门禁 | 自动化测试 | 真实 SolidWorks | 已知限制 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `solidworks_set_appearance` | 设置当前文档或装配体组件的外观颜色 | 需打开文档 | `color` / `target`, `component_keyword` | `status`, `target`, `color`, `component`, `document` | **write** | standard 及以上 | 无 | `verified` | 仅颜色，不改材质 |
| `solidworks_inspect_configurations` | 读取配置名称与当前活动配置，不修改文档 | 需打开文档 | 无 / 无 | `status`, `configurations`, `active_configuration`, `review_required`, `limitations` | **read** | read-only 及以上 | 策略层引用 1 处（非功能测试） | `verified` | 只读 |
| `solidworks_create_configuration` | 新建配置，可激活/重建/保存并回读验证 | 需打开文档 | `configuration_name` / `comment`, `alternate_name`, `options`, `if_exists`, `activate`, `rebuild`, `save` | `success`, `configuration`, `requested_configuration`, `created`, `reused`, `listed_after_create`, `configurations_before`, `options`, `activation`, `save_requested`, `save_success`, `review_required` | **write** | standard 及以上 | `automated-test-passed`（功能测试 1 处） | `verified` | 会改文档结构，需审批（write） |
| `solidworks_activate_configuration` | 激活已有配置并回读验证 | 需打开文档 | `configuration_name` / `rebuild`, `save` | `success`, `configuration`, `requested_configuration`, `before`, `after`, `api_called`, `api_return`, `api_success`, `readback_verified`, `rebuild_success`, `save_requested`, `save_success`, `review_required` | **write** | standard 及以上 | `automated-test-passed`（功能测试 1 处） | `verified` | 会切换活动配置 |
| `solidworks_set_custom_properties` | 设置并回读文件级或配置级自定义属性 | 需打开文档 | `properties` / `configuration_name`, `property_type`, `save` | `success`, `configuration`, `property_type`, `properties`, `save_requested`, `save_success`, `name`, `requested`, `add_status`, `verified`, `readback` | **write** | standard 及以上 | `automated-test-passed`（功能测试 1 处） | `verified` | 只写属性，不触发重建 |

### 导出 (6)

| 工具 | 用途 | 前置条件 | 参数（必填 / 可选） | 返回 | 风险 | 模式门禁 | 自动化测试 | 真实 SolidWorks | 已知限制 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `cadstudio_write_open_format` | 不启动 SolidWorks/AutoCAD，直接写出 STEP/IGES/BREP/STL/OBJ/GLB/DXF/SVG/PDF/PNG | 无需打开文档（headless 写出） | `input_path`, `output_dir` / `formats` | `backend`, `status`, `stage`, `artifacts`, `limitations`, `retryable`, `error_code` | **high** | full + 宿主人工确认 | `automated-test-passed`（功能测试 2 处） | `blocked` — invalid_neutral_document缺少 documentId | headless 写出，未经 SolidWorks 校验 |
| `cadstudio_build_dxf_preview_scene` | 把已有 DXF 转成白名单 PreviewScene JSON，用于预览场景 | 需存在输入 DXF 文件 | `source_path`, `output_path` / 无 | `status`, `backend`, `source`, `output`, `limitations` | **high** | full + 宿主人工确认 | 无 | `blocked` — 要求已存在的 DXF 源文件 | 仅产出白名单预览 JSON，非渲染图 |
| `solidworks_export_active` | 把当前文档导出为 STEP/STL/IGES/Parasolid/PDF/DXF | 需打开文档 ；需活动文档 | `output_path`, `export_format` / `stl_quality` | `status`, `success`, `output_path`, `format`, `document` | **high** | full + 宿主人工确认 | 策略层引用 12 处（非功能测试） | `verified`（部分：D-10） | HIGH：写文件；导出质量取决于当前文档状态 |
| `solidworks_batch_export_files` | 批量导出多个本地文件并逐个验证本次产物 | 需本地文件路径列表 | `file_paths`, `output_dir` / `formats`, `overwrite`, `close_documents`, `stl_quality` | `success`, `api_success`, `exists`, `size_bytes`, `produced_this_run`, `output_dir`, `formats`, `documents`, `summary` | **high** | full + 宿主人工确认 | `automated-test-passed`（功能测试 8 处） | `blocked` — 拒绝导出 unowned 文档（D-03 同源） | HIGH：批量写文件，依赖可写输出目录 |
| `solidworks_export_assembly_bom` | 导出组件/属性 BOM CSV，结果须原生 BOM 复核 | 需打开装配体(.SLDASM) | `output_path` / `include_excluded`, `overwrite` | `success`, `path`, `rows`, `row_count`, `quantity_total`, `size_bytes`, `sha256`, `produced_this_run`, `review_required`, `limitations` | **high** | full + 宿主人工确认 | `automated-test-passed`（功能测试 1 处） | `verified`（v0.3.3 定向复测通过：D-02/D-03a 修复后导出通过） | CSV 需原生 BOM 复核（review_required） |
| `solidworks_review_active` | 导出当前文档预览 BMP 与 JSON 审视报告 | 需打开文档 ；需活动文档 | `output_dir` / `basename` | `status`, `report_path`, `evaluation`, `checks`, `previews`, `sketch_quality`, `manual_review_required`, `document` | **high** | full + 宿主人工确认 | 无 | `verified`（部分：D-11） | HIGH：写预览与报告文件 |

### 保存 (2)

| 工具 | 用途 | 前置条件 | 参数（必填 / 可选） | 返回 | 风险 | 模式门禁 | 自动化测试 | 真实 SolidWorks | 已知限制 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `solidworks_save_document` | 保存当前文档，可用另存为 | 需打开文档 ；文档须由本会话拥有(DEF-SEC-01) ；需活动文档（且被本会话拥有） | 无 / `path` | `status`, `success`, `document` | **high** | full + 宿主人工确认 | 策略层引用 37 处（非功能测试） | `verified` | HIGH：可能覆盖磁盘文件，需审批 |
| `solidworks_pack_and_go` | 调用原生 Pack and Go 收集文件到受保护输出目录 | 需打开文档 ；需活动装配体/文档 | `output_dir` / `include_drawings`, `include_simulation_results`, `include_toolbox_components`, `include_suppressed`, `flatten`, `overwrite`, `fallback_policy` | `backend`, `document_count`, `status_codes`, `outputs`, `produced_count`, `manifest`, `success`, `status`, `stage`, `error_code`, `retryable`, `manual_review_required`, `limitations`, `native_backend`, `dependencies`, `component_audit`, `associated_drawings`, `audit_matrix`, `missing_dependencies`, `fallback_used`, `fallback_errors`, `options` | **high** | full + 宿主人工确认 | `automated-test-passed`（功能测试 1 处） | `failed`（D-13） | HIGH：写多文件；依赖原生 API 可用；实现函数名为 native Pack and Go wire function（命名差异，schema 正常，无功能影响） |

### DFM (3)

| 工具 | 用途 | 前置条件 | 参数（必填 / 可选） | 返回 | 风险 | 模式门禁 | 自动化测试 | 真实 SolidWorks | 已知限制 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `cadstudio_check_dfm` | 对机加工/钣金/激光切割/3D 打印做白名单 DFM 检查 | 需结构化 DFM 请求 JSON | `input_path`, `output_path` / `process`, `profile_paths`, `brep_evidence_path` | `kind`, `type`, `format`, `path`, `exists` | **high** | full + 宿主人工确认 | 无 | `blocked` — 同 write_open_format：NeutralCadDocument 校验前置不… | 白名单规则检查，非完整 DFM 认证 |
| `cadstudio_check_routing` | 审查中性布线拓扑、折弯半径、间隙、支撑与 BOM 证据 | 需中性布线拓扑数据 | `input_path`, `output_path` / 无 | `status`, `stage`, `checks`, `artifacts`, `manual_review_required`, `retryable`, `error_code` | **high** | full + 宿主人工确认 | 无 | `blocked` — routing_document_invalid，且 routing preflight… | 中性拓扑审查，非 SolidWorks Routing 实体验证 |
| `cadstudio_routing_preflight` | 探测 SolidWorks Routing 类型库、插件注册与许可证证据 | 无需文档 | 无 / 无 | `backend`, `status`, `stage`, `solidworks`, `addins`, `blockers`, `retryable`, `error_code`, `error` | **read** | read-only 及以上 | 策略层引用 1 处（非功能测试） | `verified` | 仅探测类型库/注册/许可，不建布线 |

### FEA (4)

| 工具 | 用途 | 前置条件 | 参数（必填 / 可选） | 返回 | 风险 | 模式门禁 | 自动化测试 | 真实 SolidWorks | 已知限制 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `cadstudio_fea_preflight` | 发现已批准的 CalculiX/Elmer 求解器可执行文件（不运行） | 无需文档，探测求解器可执行文件 | 无 / `solver` | `status`, `error_code`, `message` | **read** | read-only 及以上 | 策略层引用 1 处（非功能测试） | `verified` | 只发现求解器，不运行 |
| `cadstudio_prepare_fea` | 由结构化 FEA 1.0 请求生成带版本的 CalculiX .inp 文件 | 需结构化 FEA 1.0 请求 | `input_path`, `output_dir` / `solver` | `status`, `stage`, `checks`, `artifacts`, `manual_review_required`, `retryable`, `error_code`, `message`, `solver` | **high** | full + 宿主人工确认 | 无 | `blocked` — ValueErrorFEA 请求含未允许字段: schema_version | 生成 .inp，不解算 |
| `cadstudio_run_fea` | 通过批准的本地求解器运行结构化 FEA 1.0 请求 | 需已批准本地求解器 | `input_path`, `output_dir` / `timeout_seconds` | `executable`, `source`, `solver`, `manual_review_required`, `limitations` | **high** | full + 宿主人工确认 | 无 | `blocked` — fea_invalid_request | 依赖已批准本地求解器；未实机验证 |
| `cadstudio_run_fea_convergence` | 用 3–8 个 CalculiX 网格比较位移/应力收敛性 | 需 3–8 个网格与求解器 | `input_path`, `output_dir` / `timeout_seconds_per_case` | `retryable`, `message`, `id`, `status`, `error_code`, `manual_review_required`, `from`, `changes`, `artifacts`, `limitations` | **high** | full + 宿主人工确认 | 无 | `blocked` — fea_convergence_invalid_request | 需多网格，耗时较长；未实机验证 |

### 其他 (13)

| 工具 | 用途 | 前置条件 | 参数（必填 / 可选） | 返回 | 风险 | 模式门禁 | 自动化测试 | 真实 SolidWorks | 已知限制 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `cadstudio_resolve_backend` | 按操作 ID 解析可用的语言/后端（Python/C#/OCCT/AutoCAD 等），不执行任何几何操作 | 无需打开文档/无额外前置（源码未见 _active_*_required 调用） | `operation_id` / `available_backends`, `available_requirements`, `revision`, `exact_api` | `status`, `operation_id`, `error_code`, `reason`, `revision`, `diagnostic_backends`, `review_required`, `missing_requirements`, `backend`, `accepted` | **read** | read-only 及以上 | 策略层引用 1 处（非功能测试） | `blocked` — 无公开的 capability operation_id 清单 | 仅查询能力矩阵，不执行后端代码 |
| `solidworks_addin_host_status` | 检查 Add-in 程序集、精确注册范围与阻塞项 | 无需文档 | 无 / `assembly_path` | `status`, `error_code`, `assembly`, `code`, `message`, `capability_level`, `addin_guid`, `assembly_exists`, `assembly_bytes`, `type_library` | **read** | read-only 及以上 | 无 | `verified` | 只读诊断，不修复注册 |
| `cadstudio_review_advanced_geometry` | 校验复杂曲面/模具计划并输出试点或阻塞的前置证据报告 | 无需打开文档/无额外前置（源码未见 _active_*_required 调用） | `input_path`, `output_path` / 无 | `schemaVersion`, `status`, `stage`, `checks[]`, `artifacts`, `path`, `producedThisRun`, `sha256`, `sizeBytes`, `manual_review_required`, `retryable`, `error_code`, `planId`, `operationTypes`, `backend`, `geometryProduced`, `generatedAt`, `limitations`, `reportPath` | **high** | full + 宿主人工确认 | 无 | `blocked` — 缺必填 output_path + 无可用 review 输入（RAW 校验错误） | 源码自述 backend_implementation=fail ，仅 pilot/blocked |
| `cadstudio_create_ocp_loft` | 用 OCP 创建真实参数化 loft，并重开产物做验收 | 无需打开文档/无额外前置（源码未见 _active_*_required 调用） | `input_path`, `output_dir` / 无 | `kind`, `artifacts`, `manual_review_required`, `limitations` | **high** | full + 宿主人工确认 | 无 | `blocked` — ocp_loft_invalid_request | 依赖 OCP 运行时；缺依赖则返回 ocp_runtime_missing |
| `cadstudio_create_ocp_surface` | 通过严格结构化请求创建放样/扫描/缝合/加厚曲面 | 无需打开文档/无额外前置（源码未见 _active_*_required 调用） | `input_path`, `output_dir` / 无 | `backend`, `manual_review_required`, `error_code` | **high** | full + 宿主人工确认 | 无 | `blocked` — ocp_surface_invalid_request（operation 仅支持 sm… | 依赖 OCP 运行时；结构受限，无任意表达式 |
| `solidworks_connect` | 连接已运行的 SolidWorks 或启动一个，返回当前文档状态 | 需 SolidWorks 已安装或可启动 | 无 / `visible`, `wait_seconds`, `start_if_needed` | `status`, `revision`, `active_document` | **write** | standard 及以上 | `automated-test-passed`（`v033_remediation_test.py`） | `verified`（v0.3.3 定向复测通过：D-01 已修复） | 在 `standard`/`full` 下可冷启动 SolidWorks 进程 |
| `solidworks_health_check` | 检查 Python 依赖、COM 注册与可选实时连接 | 无需文档 | 无 / `start_solidworks`, `check_motion_type_library` | `status`, `checks`, `issues` | **read** | read-only 及以上 | `automated-test-passed`（功能测试 2 处） | `verified` | 仅环境诊断 |
| `solidworks_recover` | 诊断被阻塞的 SolidWorks 会话，可选关闭阻塞弹窗 | 无需打开文档/无额外前置（源码未见 _active_*_required 调用） | 无 / `dismiss_dialogs`, `probe_timeout_seconds` | `status`, `probe`, `next_step` | **high** | full + 宿主人工确认 | `automated-test-passed`（功能测试 3 处） | `known-limitation` | 可关闭阻塞弹窗，属破坏性恢复 |
| `design_spec_validate` | 纯校验设计规格 JSON，不接触 SolidWorks | 纯离线校验，无需 SolidWorks | `spec_path` / 无 | `status`, `errors`, `warnings`, `source_path` | **read** | read-only 及以上 | 策略层引用 2 处（非功能测试） | `failed`（D-09） | 只校验 JSON 结构/引用 |
| `solidworks_generate_drawing` | 按 DrawingSpec v1 创建工程图、PDF、预览与机器审视报告 | 需活动零件/装配体 + DrawingSpec | `spec_path`, `output_dir` / `drawing_filename`, `overwrite` | `status`, `stage`, `error_code`, `message`, `manual_review_required` | **high** | full + 宿主人工确认 | `automated-test-passed`（功能测试 11 处） | `blocked` — DRAWING_SPEC_SCHEMA_INVALIDschema_version 不被… | HIGH：建工程图并写 PDF/预览，未实机验证 |
| `solidworks_review_drawing` | 打开工程图并做 DrawingSpec/布局/尺寸/孔槽/PDF 证据审视 | 需已有 .SLDDRW 与 DrawingSpec | `drawing_path`, `spec_path`, `output_dir` / `pdf_path`, `basename` | `status`, `drawingPath`, `structure`, `previews`, `review`, `manual_review_required`, `reportPath` | **high** | full + 宿主人工确认 | `automated-test-passed`（功能测试 6 处） | `blocked` — 需已存在的 .SLDDRW | HIGH：需打开并写报告；manual_review_required 恒 True |
| `solidworks_inspect_drawing` | 只读读取工程图页、视图、尺寸、注释、表格结构并生成预览证据 | 需已有 .SLDDRW 路径 | `drawing_path`, `output_dir` / `basename`, `paper_size_hint` | `status`, `drawingPath`, `structure`, `previews`, `manual_review_required`, `reportPath` | **high** | full + 宿主人工确认 | `automated-test-passed`（功能测试 6 处） | `blocked` — 需已存在的 .SLDDRW | HIGH：写预览/报告文件 |
| `cadstudio_read_artifact` | 按 artifact id 返回内联 PNG 预览或带哈希的文件块 | 需先由其它工具发布 artifact | `artifact_id` / `offset`, `max_bytes`, `as_preview` | `as_preview`, `sha256`, `total_bytes`, `offset`, `next_offset`, `encoding`, `data` | **read** | read-only 及以上 | `automated-test-passed`（功能测试 1 处） | `blocked` — FileNotFoundError：ledger 目录下无对应 artifact，无可读产物 | 内联大小上限，超出需分块 |

## 本矩阵刻意不含的

- 没有任何工具能对任意导入实体做通用布尔运算，也没有"什么都能做"的万能工具。
- SolidWorks 本身不在沙箱里：被批准的高风险工具与用户的 SolidWorks 会话拥有同等权限。
- 本矩阵不主张与 SolidWorks 界面功能对等。大量日常操作（钣金、焊件、OCP loft/surface 之外的曲面、CAM）根本没有对应工具。
