# 71 项 CAD 工具全量追踪矩阵与参数规范报告 (traceability-matrix.md)

**任务基准：** `tan000tan/dsh-solidworks` v0.3.0  
**工具总数：** 71 个底层 CAD 核心工具 + 2 个宿主策略管理工具 = 73 个注册工具  
**覆盖维度：** 风险等级、输入参数、类型与边界、返回值契约、SolidWorks COM 行为、降级路由与验证方法

---

## 一、工具分类总览统计

| 类别 | 涵盖工具数 | 风险等级分布 | 核心功能定位 |
|---|---|---|---|
| **1. 只读检查与测量 (Inspection & Read)** | 19 项 | READ (19) | 模型几何查询、边缘列表、干涉检查、质量属性提取、配置检查、DFM/FEA 预检 |
| **2. 建模与装配编辑 (Creation & Edit)** | 26 项 | WRITE (26) | 零件创建、草图绘制、凸台拉伸、旋转、圆角、倒角、抽壳、镜像、配合添加、尺寸更新 |
| **3. 高危与持久化 (Persistence & Solver)** | 26 项 | HIGH (26) | 文档保存、关闭、批量导出 (STEP/IGES/STL)、装配体重构、工程图生成、有限元求解 |
| **4. 宿主策略工具 (Host Policy & Meta)** | 2 项 | META (2) | `solidworks_status` (连接诊断与健康报告), `solidworks_confirm` (人机授权申请) |

---

## 二、71 项核心 CAD 工具逐项参数规范与追踪矩阵

### 1. 只读与几何查询类 (19 项 - READ)

| 序号 | 工具名称 (Tool Name) | 输入参数 (Parameters) | 必填项 | 返回值类型 | SolidWorks COM 对应 API / 降级策略 | 结果验证方式 |
|---|---|---|---|---|---|---|
| 1 | `solidworks_health_check` | `start_solidworks` (bool) | 否 | JSON 状态 | `SldWorks.RevisionNumber` | 进程 PID 与版本号匹配 |
| 2 | `solidworks_list_edges` | `face_id` (int), `body_name` (str) | 是 | 边线列表数组 | `IFace2.GetEdges` / `IEdge.GetID` | 边缘几何坐标连续性 |
| 3 | `solidworks_mass_properties` | `high_precision` (bool) | 否 | 质量/体积/面积/质心 | `CreateMassProperty` -> `GetMassProperties2` | 双路径质量数值交叉比对 |
| 4 | `solidworks_bounding_box` | `part_only` (bool) | 否 | X/Y/Z 六向边界盒 | `IModelDocExtension.GetBox` | 几何包围盒尺寸正向校验 |
| 5 | `solidworks_interference_check` | `treat_subassemblies` (bool) | 否 | 干涉体列表 | `IInterferenceDetectionMgr` | 碰撞体积计算 |
| 6 | `solidworks_inspect_configurations` | 无 | 否 | 配置名称列表 | `IModelDoc2.GetConfigurationNames` | 配置名数组非空 |
| 7 | `solidworks_inspect_hole_features` | `feature_name` (str) | 否 | 孔参数与类型 | `IWizardHoleFeatureData2` | 深度与直径公差校验 |
| 8 | `solidworks_inspect_motion_studies` | 无 | 否 | 运动算例列表 | `IMotionStudyManager` | 算例树节点比对 |
| 9 | `solidworks_inspect_native_geometry` | `feature_id` (int) | 是 | 拓扑面与环列表 | `IBody2.GetFaces` | 几何拓扑闭合性 |
| 10 | `solidworks_validate_motion_study` | `study_name` (str) | 是 | 约束与自由度评估 | `IMotionStudy.Validate` | 约束矩阵行列式 |
| 11 | `solidworks_addin_host_status` | 无 | 否 | 插件注册表状态 | `ISldWorks.GetAddInObject` | COM 注册表心跳探测 |
| 12 | `design_spec_validate` | `spec_json` (str) | 是 | 规范合规评估 | 本地 JSON Schema 校验器 | 规则约束完备性 |
| 13 | `cadstudio_resolve_backend` | 无 | 否 | 后端运行时信息 | 本地环境探测 | 引擎版本比对 |
| 14 | `cadstudio_routing_preflight` | `route_id` (str) | 是 | 路径预检报告 | 几何拓扑连续性探测 | 弯曲半径干涉核算 |
| 15 | `cadstudio_fea_preflight` | `mesh_size` (float) | 否 | 网格划分可行性 | 实体表面纵横比探测 | 雅可比行列式正定性 |
| 16 | `cadstudio_read_artifact` | `artifact_path` (str) | 是 | 文本/数据内容 | 沙箱文件读取 | 哈希与大小匹配 |
| 17 | `solidworks_compile_feature_graph` | 无 | 否 | 特征 DAG 拓扑图 | 特征树遍历器 | 依赖无环图校验 |
| 18 | `solidworks_identify_dimensions` | `feature_name` (str) | 否 | 尺寸名与当前数值 | `IDisplayDimension` 遍历 | 尺寸双向映射 |
| 19 | `solidworks_inspect_dimension_impact`| `dim_name` (str), `target` (float)| 是 | 拓扑敏感性评估 | 尺寸依赖图追溯 | 关联特征受损预警 |

---

### 2. 建模与装配编辑类 (26 项 - WRITE)

| 序号 | 工具名称 | 关键参数 | 必填项 | 返回值类型 | SolidWorks COM 对应 API / 降级策略 | 结果验证方式 |
|---|---|---|---|---|---|---|
| 20 | `solidworks_connect` | `version` (int), `timeout_ms` (int) | 否 | 连接结果对象 | `win32com.client.Dispatch("SldWorks.Application")` | COM 活动对象引用校验 |
| 21 | `solidworks_open_document` | `filepath` (str), `read_only` (bool) | 是 | 文档句柄对象 | `ISldWorks.OpenDoc6` | 活动文档指针非空 |
| 22 | `solidworks_new_document` | `doc_type` (part/assembly/drawing) | 是 | 新建文档对象 | `ISldWorks.NewDocument` | 文档标题自增核验 |
| 23 | `solidworks_create_basic_part` | `name` (str), `length`, `width`, `height` | 是 | 零件生成状态 | `FeatureExtrusion3` -> `FeatureExtrusion2` | 体积 = L*W*H |
| 24 | `solidworks_sketch_and_extrude`| `plane` (str), `profile` (dict), `depth` (float) | 是 | 特征状态 | `FeatureExtrusion3` (23参数) -> `FeatureExtrusion2` (19参数) | 实体体积物理实测 |
| 25 | `solidworks_revolve` | `angle` (float), `axis` (str) | 是 | 旋转特征对象 | `FeatureRevolve2` -> `FeatureRevolve` | 质量中心旋转对称性 |
| 26 | `solidworks_fillet` | `radius` (float), `edge_ids` (list) | 是 | 圆角特征对象 | `FeatureFillet3` -> `FeatureFillet` | 拓扑边倒圆曲率检验 |
| 27 | `solidworks_chamfer` | `length` (float), `angle` (float) | 是 | 倒角特征对象 | `InsertChamferFeature2` | 切角斜面拓扑面积 |
| 28 | `solidworks_shell` | `thickness` (float), `open_faces` | 是 | 抽壳特征对象 | `InsertFeatureShell` | 腔体体积扣减核算 |
| 29 | `solidworks_pattern` | `count_x`, `spacing_x`, `dir` | 是 | 阵列特征对象 | `FeatureLinearPattern4` -> `FeatureLinearPattern2` | 实例数与间距点阵比对 |
| 30 | `solidworks_mirror_feature` | `mirror_plane` (str), `features` (list) | 是 | 镜像特征对象 | `InsertMirrorFeature2` -> `InsertMirrorFeature` | 镜像平面对称度比对 |
| 31 | `solidworks_create_hole_feature` | `hole_type` (str), `diameter`, `depth` | 是 | 异型孔对象 | `CreateHoleWizard5` | 负体积精确扣减校验 |
| 32 | `solidworks_build_round_sweeps` | `profile_dia` (float), `path_sketch` | 是 | 扫描特征对象 | `InsertSweepRefSurface` / `FeatureSweep` | 扫掠截面沿轨迹积分 |
| 33 | `solidworks_add_component` | `filepath` (str), `x`, `y`, `z` | 是 | 组件实例对象 | `AssemblyDoc.AddComponent5` | 装配树新增节点校验 |
| 34 | `solidworks_set_component_fixed`| `component_name` (str), `fixed` (bool)| 是 | 约束状态 | `Component2.SetSuppression2` / Fix | 自由度 (DOF) 矩阵归零 |
| 35 | `solidworks_add_coincident_mate`| `mate_entities` (list) | 是 | 配合对象 | `AddMate5` -> `AddMate3` | 两平面法向共面距离=0 |
| 36 | `solidworks_add_distance_mate` | `mate_entities` (list), `distance` (float) | 是 | 配合对象 | `AddMate5` -> `AddMate3` | 平行距离测量吻合 |
| 37 | `solidworks_add_concentric_mate`| `mate_entities` (list) | 是 | 配合对象 | `AddMate5` -> `AddMate3` | 旋转轴共线偏移量=0 |
| 38 | `solidworks_set_appearance` | `r`, `g`, `b`, `target_faces` | 是 | 材质外观对象 | `MaterialVisualProperties` | 颜色属性 RGBA 比对 |
| 39 | `solidworks_document_units` | `unit_system` (str) | 是 | 单位状态 | `IModelDocExtension.SetUserPreferenceInteger` | 尺寸显示单位变更 |
| 40 | `solidworks_create_configuration`| `config_name` (str) | 是 | 配置对象 | `ConfigurationManager.AddConfiguration` | 配置树条目新增 |
| 41 | `solidworks_activate_configuration`| `config_name` (str) | 是 | 激活状态 | `IModelDoc2.ShowConfiguration2` | 当前活动配置名称比对 |
| 42 | `solidworks_update_dimension` | `dim_name` (str), `value` (float) | 是 | 修改状态 | `IDimension.SetValue3` + `EditRebuild3` | 重新生成后几何变更 |
| 43 | `solidworks_set_custom_properties`| `property_name` (str), `value` (str)| 是 | 属性字典 | `CustomPropertyManager.Add3` | 自定义摘要信息读取 |
| 44 | `solidworks_add_rotary_motor` | `entity` (str), `speed_rpm` (float) | 是 | 运动载荷对象 | `ISimulationMotorFeatureData` | 驱动参数转速绑定 |
| 45 | `design_spec_build` | `spec_payload` (dict) | 是 | 批量构建指令流 | 连续事务封装调用 | 全体子特征成功率 |

---

### 3. 高危与持久化类 (26 项 - HIGH，强制人类确认)

| 序号 | 工具名称 | 关键参数 | 必填项 | 返回值类型 | 潜在风险说明 | 授权策略与防御机制 |
|---|---|---|---|---|---|---|
| 46 | `solidworks_save_document` | `filepath` (str) | 否 | 保存状态 | 覆盖磁盘已有工程模型 | 强制 `confirmedByHuman`，沙箱路径白名单限制 |
| 47 | `solidworks_close_documents` | `save_changes` (bool), `doc_name` | 否 | 关闭状态 | 丢失未保存图纸与装配 | 拦截全关闭指令，仅限关闭会话专属测试件 |
| 48 | `solidworks_export_active` | `format` (step/iges/stl/pdf), `path` | 是 | 导出文件路径 | 磁盘写入，敏感图纸外发 | 限制导出目录于临时沙箱，校验文件扩展名 |
| 49 | `solidworks_batch_export_files` | `formats` (list), `dest_dir` (str) | 是 | 批量文件列表 | 大批量磁盘 I/O 占用 | 路径穿越防御，批处理耗时熔断保护 (300s) |
| 50 | `solidworks_export_assembly_bom` | `dest_csv` (str), `detailed` (bool) | 是 | CSV 导出结果 | 装配清单与成本敏感数据 | 输出路径限制，防覆写保护 |
| 51 | `solidworks_pack_and_go` | `dest_zip` (str), `include_drawings` | 是 | 打包压缩包 | 整体工程图纸打包外流 | 单次授权消费，UNC 与绝对越权路径拦截 |
| 52 | `solidworks_import_step_part` | `step_file` (str) | 是 | 导入实体对象 | 外部未知实体解析崩溃风险 | 隔离沙箱加载，文件完整性先验校验 |
| 53 | `solidworks_replace_component_preserving_transform` | `old_comp`, `new_filepath` | 是 | 替换结果 | 装配体引用断开与配合报错 | 建立装配配合影子镜像，失败自动回滚 |
| 54 | `solidworks_exclude_reviewed_bodies` | `body_names` (list) | 是 | 实体隔离状态 | 实体隐藏与拓扑失效 | 记录初始显示掩码，支持一键恢复 |
| 55 | `solidworks_recover` | `snapshot_id` (str) | 是 | 恢复状态 | 状态机强制回退至历史快照 | 状态事务校验，防跨会话脏数据恢复 |
| 56 | `solidworks_review_active` | `criteria` (dict) | 否 | 评审结论报告 | 触发完整模型几何扫描 | 进程阻塞监控，内存超限自动熔断 |
| 57 | `solidworks_generate_drawing` | `template_path`, `model_path` | 是 | 工程图文档对象 | 生成标准二维工程图纸 | 模板路径合规性，视图投影自动排版 |
| 58 | `solidworks_review_drawing` | `drawing_path` (str) | 是 | 尺寸与图纸审查报告 | 遍历全图纸注释与尺寸 | 只读解析视图，零图纸篡改 |
| 59 | `solidworks_inspect_drawing` | `view_name` (str) | 是 | 视图投影特征列表 | 二维拓扑查询 | 视图边界框核对 |
| 60 | `cadstudio_write_open_format` | `format` (str), `dest_path` (str) | 是 | 开放格式写入状态 | 外部 STEP/BREP/OBJ 写入 | 路径受限，禁止写入系统敏感目录 |
| 61 | `cadstudio_prepare_fea` | `mesh_config` (dict) | 是 | 有限元网格准备状态 | 占用大量计算资源与显存 | 资源配额限制，超时保护 |
| 62 | `cadstudio_run_fea` | `solver` (str), `load_cases` | 是 | 应力/位移计算云图 | 计算密集型求解器启动 | 求解器子进程隔离，防主进程挂起 |
| 63 | `cadstudio_run_fea_convergence`| `target_error` (float) | 是 | 收敛迭代报告 | 多轮网格自适应细化计算 | 迭代步数上限锁 (max_steps=10) |
| 64 | `cadstudio_create_ocp_loft` | `sections` (list) | 是 | 自由曲面放样特征 | 复杂 B-Rep 放样失败可能退化 | 容差自愈算法，几何未封闭拒绝生成 |
| 65 | `cadstudio_create_ocp_surface` | `boundaries` (list) | 是 | 裁剪曲面对象 | 高阶贝塞尔曲面自交风险 | 曲率连续性 (G1/G2) 预校验 |
| 66 | `cadstudio_check_dfm` | `rule_set` (injection/cnc/sheet) | 是 | DFM 制造性规则评估 | 耗时制造特征检测 | 纯内存拓扑解析，零模型修改 |
| 67 | `cadstudio_check_routing` | `clearance_min` (float) | 是 | 间隙与干涉报告 | 路径干涉与折弯半径检查 | 碰撞矩阵数学求解 |
| 68 | `cadstudio_review_advanced_geometry` | `feature_id` (int) | 是 | 高阶几何曲率分析报告 | 高斯曲率计算占用 | 采样点数限制，防止死循环 |
| 69 | `cadstudio_build_dxf_preview_scene` | `dxf_path` (str) | 是 | SVG/Scene 预览数据 | 解析外部 DXF 图纸 | 实体边界拦截，防止畸变实体越界 |
| 70 | `solidworks_execute_feature_graph` | `graph_ir` (dict) | 是 | 特征图批量执行状态 | 复杂多特征复合创建 | 逐节点事务化执行，遇几何失败立即中断冒泡 |
| 71 | `solidworks_modify_dimension_safe` | `dim_name`, `target_value` | 是 | 安全修改重构状态 | 驱动尺寸变更引发拓扑断裂 | 变更前后模型自愈校验，异常自动回退初始尺寸 |

---

## 三、宿主策略工具说明 (2 项 - META)

1. **`solidworks_status`**：
   - 入参：无
   - 返回：插件运行环境状态、Python 解释器版本与路径、MCP 客户端运行状态、当前策略模式（`read-only` / `standard` / `full`）、声明工具数（73）。
2. **`solidworks_confirm`**：
   - 入参：`tool` (str), `args` (dict), `scope` ('single' / 'session'), `reason` (str), `confirmedByHuman` (bool)
   - 安全控制：必须具备 `confirmedByHuman === true`，杜绝 AI 单方面自闭环签发 Grant。

---

## 四、全量工具验证与测试覆盖对照

- **已完成实机物理几何闭环验证：** 核心特征建模、草图与双向拉伸、圆形盲切切除、双路径质量属性比对、镜像特征反射调用、装配体组件插入、配合重合约束、工程图新建与视图投影、序列化保存与重开校验（覆盖率为 100% 核心物理主链路）。
- **已完成接口降级契约与参数规范验证：** 71 项工具全部完成参数 Schema 紧凑序列化校验、多版本 DISPID 降级映射（`FeatureExtrusion3/2`, `FeatureCut4/3`, `InsertMirrorFeature2/1`, `AddMate5/3`, `CreateDrawViewFromModelView3/2`）与异常分类拦截测试。
