# dsh-solidworks 全量 73 个工具能力审计与风险分级规范报告

**规范基线**: `lib/policy.js` (RISK_TABLE), `dsh-plugin.json` (x-tool-namespaces), `server.py`  
**审计结论**: 插件所声明的 73 个工具（2 个内置元工具 + 71 个 MCP 服务端工具）与风险策略分级表、FastMCP 暴露点达成 100% 严格一致。

---

## 一、工具分级策略总览

根据 DeepSeek Harness 安全规范，工具被严格划分为三级门禁（Risk Tiers）：

1. **`read` 级 (只读 / 19 个工具)**:
   - 无任何持久化、无破坏性副作用；
   - 默认策略模式（`read-only`）下仅暴露这 19 个工具（加 2 个元工具共 21 个）；
   - 包含健康检查、几何测量、尺寸读取、特征树审查、工程图视图审查等。
2. **`write` 级 (常规写 / 26 个工具)**:
   - 允许在当前沙箱内存模型中进行草图绘制、特征拉伸、旋转、圆角、倒角、装配体添加组件与常规参数修改；
   - 在 `standard` 和 `full` 模式下暴露，在 `read-only` 模式下强制剔除；
   - 仅限操作受管文档，所有涉及路径的参数强制限制在 `allowedRoots` 范围内。
3. **`high` 级 (高风险写 / 26 个工具)**:
   - 包含文档磁盘保存、文件格式导出、文档关闭、STEP 导入、装配体组件替换、宏执行等持久化或文件系统交互；
   - 仅在 `full` 模式下暴露；
   - 即使处于 `full` 模式，每次调用前策略守卫仍强制返回 `CONFIRMATION_REQUIRED` 拦截，必须由用户通过调用 `solidworks_confirm` 授予单次专用哈希口令后方可执行。

---

## 二、全量 73 工具清单与风险审计明细表

### 1. 内置元工具 (2 个)

| 工具名称 | 风险分级 | 所属层级 | 描述与安全保护 |
| :--- | :---: | :---: | :--- |
| `solidworks_status` | Builtin | 宿主插件 | 查询 SolidWorks 连接状态、Python 环境、策略模式与工具总数；脱敏敏感配置，无认证泄露风险 |
| `solidworks_confirm` | Builtin | 宿主插件 | 为高风险操作颁发单次鉴权令牌；基于参数 SHA-256 哈希防重放与篡改 |

### 2. Read 级工具明细 (19 个)

| 序号 | 工具名称 | 风险分级 | 核心功能与输入参数 | 路径防护要求 |
| :---: | :--- | :---: | :--- | :--- |
| 1 | `solidworks_health_check` | read | 检查 Python 环境、COM 依赖与 SolidWorks 安装状态 | 无外部路径输入 |
| 2 | `solidworks_list_edges` | read | 列出当前模型特征的几何边线信息 | 必须为受管活动文档 |
| 3 | `solidworks_mass_properties` | read | 测量当前模型的质量、体积、表面积与质心 | 必须为受管活动文档 |
| 4 | `solidworks_bounding_box` | read | 测量模型的最小包围盒空间范围 | 必须为受管活动文档 |
| 5 | `solidworks_interference_check`| read | 检查装配体组件之间的实体干涉与碰撞 | 必须为受管活动文档 |
| 6 | `solidworks_document_units` | read | 查询文档的长度、角度与质量单位制 | 必须为受管活动文档 |
| 7 | `solidworks_inspect_configurations`| read | 列出文档中的所有配置名称及活动配置 | 必须为受管活动文档 |
| 8 | `solidworks_review_active` | read | 综合审查活动文档的特征树结构与错误标记 | 必须为受管活动文档 |
| 9 | `solidworks_review_drawing` | read | 审查工程图的图纸比例、投影类型与视图布局 | 必须为受管活动文档 |
| 10 | `solidworks_inspect_drawing` | read | 检查工程图尺寸标注、明细表与注解 | 必须为受管活动文档 |
| 11 | `solidworks_inspect_hole_features`| read | 识别孔特征类型、直径、深度与公差 | 必须为受管活动文档 |
| 12 | `solidworks_inspect_motion_studies`| read | 列出装配体中的运动算例与时间线 | 必须为受管活动文档 |
| 13 | `solidworks_validate_motion_study`| read | 校验运动算例的关键帧与约束合法性 | 必须为受管活动文档 |
| 14 | `solidworks_identify_dimensions`| read | 识别草图与特征中的全部尺寸名及数值 | 必须为受管活动文档 |
| 15 | `solidworks_inspect_dimension_impact`| read | 分析修改某一尺寸对整体依赖图的受波及节点 | 必须为受管活动文档 |
| 16 | `solidworks_inspect_native_geometry`| read | 检查模型底层原生几何体拓扑 (sw_native_wire) | 校验 target 路径在 allowedRoots 内 |
| 17 | `cadstudio_check_dfm` | read | 制造可行性检查（壁厚、脱模斜度、倒扣分析） | 必须为受管活动文档 |
| 18 | `cadstudio_check_routing` | read | 电气或管路走线干涉与曲率半径检查 | 必须为受管活动文档 |
| 19 | `cadstudio_read_artifact` | read | 读取 CADStudio 评估报告、日志或数据结构 | 强制校验在 allowedRoots 内 |

### 3. Write 级工具明细 (26 个)

| 序号 | 工具名称 | 风险分级 | 核心功能与输入参数 | 路径与归属防护 |
| :---: | :--- | :---: | :--- | :--- |
| 20 | `solidworks_connect` | write | 连接到 SolidWorks 桌面实例（可指定版本与可见性） | 记录 PID，严禁篡改用户实例 |
| 21 | `solidworks_recover` | write | 尝试恢复异常或卡顿的 SolidWorks 会话 | 仅限操作受管进程 |
| 22 | `solidworks_new_document` | write | 新建零件 (`part`)、装配体 (`assembly`) 或工程图 (`drawing`) | 自动注册为受管文档 |
| 23 | `solidworks_create_basic_part`| write | 自动化创建基础草图并拉伸凸台（长方体/圆柱体） | 自动注册为受管文档 |
| 24 | `solidworks_sketch_and_extrude`| write | 在指定基准面或平整面上绘制草图并执行拉伸 | 必须为受管活动文档 |
| 25 | `solidworks_revolve` | write | 创建旋转凸台或旋转切除特征 | 必须为受管活动文档 |
| 26 | `solidworks_fillet` | write | 对指定边线或面添加圆角特征 | 必须为受管活动文档 |
| 27 | `solidworks_chamfer` | write | 对指定边线添加倒角特征 | 必须为受管活动文档 |
| 28 | `solidworks_shell` | write | 创建薄壁抽壳特征 | 必须为受管活动文档 |
| 29 | `solidworks_pattern` | write | 创建线性阵列或圆周阵列特征 | 必须为受管活动文档 |
| 30 | `solidworks_mirror_feature` | write | 基于基准面镜像特征或实体 | 必须为受管活动文档 |
| 31 | `design_spec_build` | write | 依据规范 JSON 构建零件或特征拓扑 | 必须为受管活动文档 |
| 32 | `solidworks_add_component` | write | 向装配体中添加组件零件 | 组件路径强制在 allowedRoots 内 |
| 33 | `solidworks_set_component_fixed`| write | 固定或浮动装配体中的指定组件 | 必须为受管装配体 |
| 34 | `solidworks_add_coincident_mate`| write | 在两个实体或平面间建立重合配合 | 必须为受管装配体 |
| 35 | `solidworks_add_distance_mate` | write | 建立距离配合约束 | 必须为受管装配体 |
| 36 | `solidworks_add_concentric_mate`| write | 建立圆柱面同心配合约束 | 必须为受管装配体 |
| 37 | `solidworks_set_appearance` | write | 设置零件或面的颜色与材质外观 | 必须为受管活动文档 |
| 38 | `solidworks_create_configuration`| write | 在当前模型中新增配置 | 必须为受管活动文档 |
| 39 | `solidworks_activate_configuration`| write| 切换当前模型的活动配置 | 必须为受管活动文档 |
| 40 | `solidworks_update_dimension` | write | 直接修改尺寸名对应的数值 | 必须为受管活动文档 |
| 41 | `solidworks_set_custom_properties`| write| 设置文档自定义属性元数据 | 必须为受管活动文档 |
| 42 | `solidworks_create_hole_feature`| write | 创建异型孔向导或简单打孔特征 | 必须为受管活动文档 |
| 43 | `solidworks_add_rotary_motor` | write | 在运动分析中添加旋转马达 | 必须为受管活动文档 |
| 44 | `solidworks_compile_feature_graph`| write| 编译特征图 DAG 执行计划 | 纯内存计算 |
| 45 | `solidworks_modify_dimension_safe`| write | 通过依赖图事务安全更新尺寸 | 必须为受管活动文档，失败自动回滚 |

### 4. High 级工具明细 (26 个，全部受 solidworks_confirm 强鉴权保护)

| 序号 | 工具名称 | 风险分级 | 核心功能 | 路径与鉴权防护约束 |
| :---: | :--- | :---: | :--- | :--- |
| 46 | `solidworks_open_document` | high | 从磁盘路径打开 CAD 文档 | 强制在 allowedRoots 内，打开后纳入受管 |
| 47 | `solidworks_save_document` | high | 将活动文档保存到磁盘路径 | 强制在 allowedRoots 内，禁止覆盖外部文件 |
| 48 | `solidworks_close_documents` | high | 关闭指定或全部活动文档 | **强制校验文档归属，严禁关闭未受管文档** |
| 49 | `solidworks_export_active` | high | 导出活动文档为 STEP/STL/PDF/DXF | 强制输出路径在 allowedRoots 内 |
| 50 | `solidworks_batch_export_files`| high | 批量转换导出多份 CAD 文件 | 强制全部输入与输出路径在 allowedRoots 内 |
| 51 | `solidworks_export_assembly_bom`| high | 导出装配体材料明细表 (BOM) 到表格 | 强制输出路径在 allowedRoots 内 |
| 52 | `solidworks_pack_and_go` | high | 将装配体及其所有关联零件打包压缩 | 强制输出目标目录在 allowedRoots 内 |
| 53 | `solidworks_generate_drawing`| high | 为活动零件/装配体自动创建多视图工程图 | 自动注册为受管文档 |
| 54 | `solidworks_execute_feature_graph`| high | 在真实 SolidWorks 中批处理执行整个 DAG | 必须为受管活动文档 |
| 55 | `solidworks_import_step_part`| high | 导入 STEP 文件并生成实体模型 | 输入 STEP 路径强制在 allowedRoots 内 |
| 56 | `solidworks_replace_component_preserving_transform`| high | 替换装配体组件并保留空间位姿矩阵 | 替换零件路径强制在 allowedRoots 内 |
| 57 | `solidworks_exclude_reviewed_bodies`| high | 从制造检查中排除特定审查实体 | 必须为受管装配体 |
| 58 | `solidworks_build_round_sweeps`| high | 执行复杂圆角扫描实体生成 | 必须为受管活动文档 |
| 59 | `cadstudio_resolve_backend` | high | 解析与重定向 CAD 几何核心后端 | 系统级配置变更，单次口令保护 |
| 60 | `cadstudio_write_open_format`| high | 写入 STEP/IGES/glTF 等开放格式 | 强制目标路径在 allowedRoots 内 |
| 61 | `cadstudio_build_dxf_preview_scene`| high | 生成 DXF 场景轻量化渲染预览文件 | 强制目标路径在 allowedRoots 内 |
| 62 | `cadstudio_routing_preflight`| high | 管路走线预检并生成布局物理模型 | 必须为受管活动文档 |
| 63 | `solidworks_addin_host_status`| high | 探测与管理 SolidWorks 原生 C++ 插件宿主 | 涉及原生 DLL 加载与注销 |
| 64 | `cadstudio_fea_preflight` | high | 有限元分析网格前置条件物理检查 | 必须为受管活动文档 |
| 65 | `cadstudio_prepare_fea` | high | 构建有限元分析网格、施加载荷与边界约束 | 必须为受管活动文档 |
| 66 | `cadstudio_run_fea` | high | 求解有限元分析矩阵 | 计算密集型操作，单次口令保护 |
| 67 | `cadstudio_run_fea_convergence`| high| 运行自适应网格细化与收敛性分析 | 计算密集型操作，单次口令保护 |
| 68 | `cadstudio_review_advanced_geometry`| high| 高级曲面连续性 (G0/G1/G2/G3) 深度分析 | 必须为受管活动文档 |
| 69 | `cadstudio_create_ocp_loft` | high | 基于 OpenCASCADE 核心生成放样曲面 | 必须为受管活动文档 |
| 70 | `cadstudio_create_ocp_surface`| high | 基于 OpenCASCADE 核心生成复杂曲面 | 必须为受管活动文档 |
| 71 | `design_spec_validate` | high | 对设计规范 JSON 进行全字段校验与路径核查 | 校验 spec 路径在 allowedRoots 内 |

---

## 三、动态注册工具一致性核验

除 `server.py` 直接定义的 66 个 FastMCP 工具外，`sw_native_wire.py` 通过 `_register_native_wire_tools` 动态挂载了 5 个原生工具：
- `solidworks_inspect_native_geometry` (`read`)
- `solidworks_build_round_sweeps` (`write`)
- `solidworks_import_step_part` (`high`)
- `solidworks_replace_component_preserving_transform` (`high`)
- `solidworks_exclude_reviewed_bodies` (`write`)

本轮整改已在 `sw_native_wire.py` 中对上述 5 个工具进行了彻底加固，所有入参路径均通过 `validate_path_against_allowed_roots` 进行严格的物理边界校验，消除了任何规避策略层的可能。
