# 第四轮审计交付物 14：变更日志 (CHANGELOG)

## [第四轮全量整改与独立验收交付] - 2026-11-06

### 安全加固 (Security Hardening - P0)
- **根除危险调用**：完全废除并清除代码库中任何形式的 `CloseAllDocuments(True)` 调用。
- **三层沙箱防护**：在 `vendor/solidworks-automation-skill/scripts/sw_connect.py` 的 `close_document` 函数中增加三层安全边界：
  1. 目标非空严格校验；
  2. 会话所有权校验（`_SESSION_OWNED_DOCUMENTS` 登记与 `allowed_roots` 路径白名单约束）；
  3. 未保存修改脏状态检测（`GetSaveFlag()`，未保存时拦截并提示用户确认，除非显式指定 `force_discard=True`）。
- **永久禁止批量关文档**：新增 `close_all_documents` 永久抛出 `PermissionError`，禁止自动化代理批量关闭文档。
- **MCP 接口安全加固**：更新 `vendor/solidworks-automation-skill/mcp-server/server.py`，彻底弃用 `close_all: bool`，改为针对具体 `document_path` 或 `title` 的安全单文档关闭；传入 `close_all=True` 触发 `PermissionError` 拦截。
- **进程隔离保护**：`close_owned_solidworks` 强绑定 `started_by_cad_studio` 与当前启动的 PID，严禁跨进程或全局杀死用户运行中的 SolidWorks 实例。

### 质量审查与凭证引擎 (Quality Inspector Security - DEF-05)
- **密码学凭证签发**：在 `cad_quality_inspector.py` 中引入基于 HMAC-SHA256 的 `BenchmarkCredential` 凭证引擎，包含会话密钥、时间戳、TTL（300秒超时）及随机 Nonce。
- **杜绝来源伪造**：移除对明文 `provenance` 或 `source="baseline"` 的任何直接信任，未提供合规且有效签名的模型一律按未认证执行独立质检。
- **严格克隆检测**：增强浅拷贝、深拷贝、数值字典重建的特征比对算法，检测到克隆但无合法凭证的模型直接判为 `FAILED`（得分 0.0）。
- **自主调度对接**：更新 `advanced_ai_cad_coordinator.py` 在自主工作流中合规生成签名凭证并传递给审查器。

### 核心 CAD 特征与装配体系 (CAD & Assembly - DEF-01, DEF-03, DEF-11)
- **原生倒角与圆角**：修复倒角 COM API 参数类型，传入标准 `double` 浮点数并适配 Callout VARIANT；实机成功创建 `倒角1` 与 `圆角1`。
- **原生阵列特征**：实机成功创建线性阵列（`阵列(线性)1`，3孔）与圆周阵列（`阵列(圆周)1`，6孔），在特征树上留下真实 `LPattern` 和 `CirPattern` 实体节点。
- **原生圆柱面同心配合**：装配体彻底废除正交平面重合替代方案，调用 `AddMate5(1, ...)` 创建 2 对原生 `swMateCONCENTRIC` 圆柱面配合，并在特征树中建立 `MateGroup`。
- **STEP AP214 格式**：纠正偏好设置 API 参数为 `swStepAP(75) = 214`，成功导出物理文件头严格为 `FILE_SCHEMA (( 'AUTOMOTIVE_DESIGN' ));` 的 AP214 STEP 装配体模型。

### 工程图与多视图体系 (Engineering Drawing - DEF-02)
- **四视图投影闭环**：通过 `Create3rdAngleViews2` 与定向为 `*等轴测` 的 `CreateDrawViewFromModelView3`，实机生成包含主视、俯视、右视及等轴测图的完整四视图工程图。
- **矢量 PDF 导出**：使用 `export_sheet_to_pdf` 成功导出 54,276 字节真实几何矢量 PDF 图纸。

### 几何体积与测试对账 (Geometry & Testing - DEF-04, DEF-07, DEF-10)
- **体积三级度量**：严谨分离解析理论值（$251938.210\text{ mm}^3$）、CAD 连续实体值（$252684.717\text{ mm}^3$）与 STL 离散网格值（$251944.796\text{ mm}^3$），详细论述 2,462 面弦割离散微小误差（+0.0026%）。
- **修复 M09 空断言**：在 `tests/rem_compat_test.py` 中移除条件跳过，强制断言 STA 工作线程生命周期与往返调度。
- **全量测试回归**：全量 196 个自动化测试用例（Node.js 68 个、Python 128 个）及 CAD 实机沙箱物证全部 100% 通过。
