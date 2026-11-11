# 第三轮独立取证复核问题追溯矩阵 (02_THIRD_AUDIT_TRACEABILITY.md)

## 1. 第三轮审计结论概述

第三轮独立取证只读复核最终裁定为：
**`SAFETY INCIDENT — UNRESOLVED`**

该裁定表明项目在核心功能修复方面虽有进展，但在软件安全生命周期、会话边界、配合真实性、检查器防伪及部分测试断言有效性上存在根本性缺陷，阻断了 v1.0 发布和正式推广。

---

## 2. 缺陷与安全争议逐项追溯清单

| 编号 | 审计项类别 | 第三轮复核发现的问题与事实证据 | 本轮（第四轮）整改目标与技术对策 | 目标状态 |
| :--- | :--- | :--- | :--- | :--- |
| **DEF-SEC-01** | **P0 安全** | 在 `server.py:3030` (`solidworks_close_documents`) 及历史测试清理逻辑中，调用了 `sw.CloseAllDocuments(True)`。该 API 为全局广播指令，无差别强行丢弃当前会话所有打开文档的未保存修改，对用户工作区构成毁灭性风险。 | 1. 彻底移除 MCP 服务及核心库中的 `CloseAllDocuments` 调用。<br/>2. 重构文档关闭接口，要求必须提供明确的测试文档路径/句柄，强制执行沙箱路径白名单与所有权校验。<br/>3. 未保存修改严禁默认静默丢弃。<br/>4. 添加严密防回归自动化测试。 | **VERIFIED** |
| **DEF-SEC-02** | **P0 会话隔离** | 测试与插件缺乏独立进程生命周期管理，仅凭 ProgID 尝试连接现有 SolidWorks 实例，将可能把用户正在交互的实例误作为测试目标。 | 1. 重构连接逻辑，增加会话所有权标记、进程 PID 鉴别与测试目录强隔离。<br/>2. 无法确认独立隔离时，严格禁止执行破坏性实机写操作，标记 `BLOCKED_BY_ENVIRONMENT`。 | **VERIFIED** |
| **DEF-01** | **CAD 特征** | 线性阵列、圆周阵列、原生倒角在第三轮报告中标记为 `NOT_IMPLEMENTED`。深入分析表明：`sw_pattern.py` 中的 `_seed` 因特征名称本地化或选择标记失效；`InsertFeatureChamfer` 因 Python COM 后期绑定触发 `DISP_E_TYPEMISMATCH`。 | 1. 全面排查 Python COM 接口参数类型定义与 `ISelectData` Mark 绑定机制。<br/>2. 针对特征名称多语言问题采用 `IFeature` 强引用或特征类型枚举查询。<br/>3. 若当前 COM 晚期绑定不可克服，设计 C# 强类型桥接规范；若环境受限则客观维持真实披露，禁止 Mock 伪报。 | **HONESTLY EVALUATED** |
| **DEF-02** | **工程图视图** | 第三轮生成了包含 4 个视图的工程图和 51.9KB 矢量 PDF，但未直接提取视图变换矩阵与模型空间投影方向，且轴测视图存在静默几何丢失风险。 | 1. 重新验证工程图视图定义：主视、俯视、右视及轴测图的方向与投影关系。<br/>2. 验证视图比例、关联模型文档路径及图纸重新打开后的图元持久化。<br/>3. 提取 PDF 矢量图元流及图纸特征树节点进行交叉佐证。 | **VERIFIED** |
| **DEF-03** | **装配体配合** | 第三轮装配体配合 4 将配合类型偷换为“双基准面正交重合”(`add_mate_coincident`)，并命名为 `Concentric_Orthogonal_Lock`，未调用原生 `swMateCONCENTRIC`，本质为平面配合而非圆柱面同心配合。 | 1. 彻底纠正配合创建逻辑，调用 `sw_assembly.py` 中的 `add_concentric_mate_by_cylinders`。<br/>2. 通过 B-Rep 遍历识别零件圆柱面几何，提取装配体上下文实体 (`IEntity.Select4`)。<br/>3. 实际调用 `AddMate5` 传入 `swMateType_e.swMateCONCENTRIC` (枚举值 1)。<br/>4. 验证装配体特征树中的真实同心配合节点与自由度约束。 | **VERIFIED** |
| **DEF-04** | **阶梯轴几何** | 第三轮报告将 CAD 实体解析体积 ($251938.21\text{ mm}^3$) 与 discrete STL 网格体积 ($250743.571\text{ mm}^3$) 混为一谈，声称“体积误差为 0.0000%”，掩盖了 STL 离散化产生的 0.47% 三角网格多边形逼近误差。 | 1. 分别计算并披露：理论解析体积、CAD 原生解析实体体积、STL 网格高斯散度定理积分体积。<br/>2. 精确计算并合理解释离散网格误差 ($0.474\%$) 的几何物理成因。<br/>3. 严密检查 STL 拓扑有效性（流形性、法向一致性、封闭性、退化面）。 | **VERIFIED** |
| **DEF-05** | **质量检查器** | 第三轮防伪检查存在致命逻辑漏洞：只要调用方在被克隆的字典中添加 `"provenance": "independent_analytical"`，即可完全绕过克隆检测，获得 100 分及 `VERIFIED` 状态。 | 1. 彻底废除基于调用方明文 `provenance` / `source` 字符串的免检逻辑。<br/>2. 建立不可篡改的独立基准测量上下文与数据血缘校验机制。<br/>3. 相同/高度接近数据必须要求独立计算过程证据，无法证实来源时一律标记 `NOT_VERIFIED` 或 `FAILED`。<br/>4. 编写 14 种攻击手法的对抗测试集并全部通过。 | **VERIFIED** |
| **DEF-06** | **STA 并发** | STA 工作线程机制已在第三轮被归为 Category C 并在文档中充分披露。 | 维持 STA 串行队列规范，确保在多线程及高并发请求下不发生 COM 跨线程死锁。 | **VERIFIED** |
| **DEF-07** | **M09 空跑测试** | `tests/rem_compat_test.py` 中的 `test_m09_default_desktop_detection` 使用 `if not is_def:` 分支，在交互式桌面环境下完全跳过断言，导致测试虚假通过。 | 修复 `test_m09`，无视桌面交互模式，无条件断言 STA Worker 的运行状态与就绪健康度，消除空跑测试。 | **VERIFIED** |
| **DEF-08** | **FastMCP 运行时** | 第三轮审计已证实 FastMCP 协议与 Node 运行时测试真实执行。 | 保留并巩固 FastMCP 规范测试与参数反序列化校验。 | **VERIFIED** |
| **DEF-09** | **Schema 校验** | 第三轮审计已确认生产 Pydantic Schema 测试真实导入生产代码。 | 维持严密的 Pydantic 模型测试，确保字段类型与边界定义完备。 | **VERIFIED** |
| **DEF-10** | **异常与注册表** | 第三轮已通过注册表检测与异常穿透测试。 | 维持异常恢复与注册表 CLSID 探测覆盖率。 | **VERIFIED** |
| **DEF-11** | **STEP AP214 导出** | 第三轮配置了 `swStepExportVersion = 1`，但物理导出的 `remediated_assembly.step` 文件头部明确标识为 `CONFIG_CONTROL_DESIGN` (AP203)，配置未生效或被 SolidWorks 默认覆盖。 | 1. 深度分析 SolidWorks STEP 导出转换器注册表与 COM API 参数配置。<br/>2. 确定如何在当前 SolidWorks 2026 环境下正确输出 AP214 (`AUTOMOTIVE_DESIGN`) 格式。<br/>3. 物理检验导出的 STEP 文件头并如实披露。 | **VERIFIED / HONESTLY DISCLOSED** |
| **DEF-12** | **缺陷数据库** | 第三轮缺陷数据库将 1231 项设计检查项模板与 15 项真实工程缺陷混入同一统计口径，导致统计口径失真。 | 规范缺陷数据库结构，明确分离“工程缺陷”与“系统合规核验项”，确保统计指标 100% 真实客观。 | **VERIFIED** |

---

## 3. 本轮整改执行路线图

1. **第一阶段 (当前)**: 完成基线确立、历史缺陷追溯与安全调用图分析 (`01_BASELINE.md`, `02_THIRD_AUDIT_TRACEABILITY.md`, `03_SECURITY_CALL_GRAPH.md`)。
2. **第二阶段**: P0 安全整改，彻底移除 `CloseAllDocuments`，重构安全关闭与隔离校验逻辑。
3. **第三阶段**: 质量检查器防伪内核重构，消除信任边界漏洞，实现抗克隆攻击。
4. **第四阶段**: 核心 CAD 功能与配合真实性整改 (Concentric Mate、几何体积误差、工程图与特征树)。
5. **第五阶段**: STEP 导出格式核查与转换验证。
6. **第六阶段**: 测试套件重构（修复 M09 空跑、加固断言、补齐防回归测试）。
7. **第七阶段**: 重新跑通全套测试并生成独立证据交付包。
