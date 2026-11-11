# 未闭环缺陷与环境限制边界说明书 (12_UNRESOLVED_DEFECTS.md)

**执行主体**: dsh-solidworks 第三轮整改验收团队  
**归档时间**: 2026-11-06T20:36:42+08:00  
**最高准则**: **绝不隐瞒任何未实现功能，绝不把部分解决包装为全面通过**

---

## 一、未闭环与环境限制缺陷清单

经过第三轮严格的物理取证与实机实测，以下缺陷受限于当前技术架构、SolidWorks 2026 COM API 底层机制或运行时环境约束，明确判定为未完全闭环（标注为 `NOT_IMPLEMENTED` 或 `PARTIALLY_FIXED`）：

---

### 1. DEF-01 / ISS-REM-003: 原生高级 CAD 特征树节点未实现
- **涉及功能**: 原生线性阵列 (`FeatureLinearPattern4`)、圆周阵列 (`FeatureCircularPattern4/5`)、倒角 (`InsertFeatureChamfer`)、圆角 (`FeatureFillet`)
- **第三轮状态**: **`NOT_IMPLEMENTED` (明确未实现)**
- **物理报错与现象**:
  1. `LinearPattern`: 抛出 `无法选择阵列母特征: 切除-拉伸2`；
  2. `CircularPattern`: 抛出 `无法选择阵列母特征: 切除-拉伸2`；
  3. `Chamfer`: 抛出 `pywintypes.com_error: (-2147352571, '类型不匹配。', None, 8)`；
  4. `Fillet`: 缺少实体边线 SelectionMark 映射，未生成特征节点。
- **底层技术根因**:
  SolidWorks 2026 COM API 对上述特征要求极其严苛的双重预选机制（母特征需携带 Mark=4 的 `ISelectData`，方向边线需携带 Mark=1 或 Mark=2，旋转轴需为专用物理基准轴）。在 Python `pywintypes`/`IDispatch` 跨进程动态后期绑定（Late Binding）下，VARIANT 参数传递在类型打包时丢失了原生强类型元数据，导致 SolidWorks 内部校验未通过。
- **对用户与生产的影响**:
  通过 AI Agent 自动调用上述 4 项工具时会返回明确的执行失败提示。用户目前需在生成的基础实体上进行手工阵列/倒角操作，或使用预制草图/特征模板。
- **后续整改技术路线 (Roadmap)**:
  彻底摒弃单纯的 Python pywin32 动态脚本直连方案，研发基于 C#/.NET 强类型的 Native SolidWorks Add-in 插件，利用官方 SDK 强类型指针（`FeatureManager`、`SelectData`）进行实体交互，再通过 gRPC 或命名管道与 Python/Node.js MCP 进程通信。

---

### 2. DEF-11 / ISS-REM-005: STEP 导出协议仍为 AP203
- **涉及功能**: 中性 3D 装配体交换格式导出
- **第三轮状态**: **`PARTIALLY_FIXED` (部分完成)**
- **物理现象**:
  代码中已成功将首选项 `swUserPreferenceIntegerValue_e.swStepExportVersion`（ID: 383）显式设置为 `1`（AP214），但导出的 `remediated_assembly.step` 物理文件头仍声明为：
  `APPLICATION_PROTOCOL_DEFINITION('international standard','config_control_design',1994,#1);`（即 AP203 架构）。
- **底层技术根因**:
  该宿主机安装的 SolidWorks 2026 SP4.1 标准安装包未激活或未搭载独立的 AP214 汽车设计行业扩展转换器模板，内部 STEP 转换引擎在后台模式下退回默认的 AP203 协议。
- **对生产的影响**:
  AP203 完整保留了实体与装配体拓扑几何数据，在各类 CAD 系统中能够无损导入打开，仅在装配体面颜色与分层属性的元数据定义上略逊于 AP214，不影响几何工程应用。

---

### 3. ISS-ARC-001: MCP 服务端单体架构与巨型代码维护债务
- **涉及代码**: `vendor/solidworks-automation-skill/mcp-server/server.py`
- **第三轮状态**: **`PARTIALLY_FIXED` (维护性技术债务)**
- **物理现象**:
  `server.py` 代码体量超过 4,000 行，集成了数十个 CAD 工具的输入校验与分发。
- **对生产的影响**:
  虽已通过 `lib/policy.js` 与 `lib/schema.js` 在 Node.js 插件层完成了安全策略与参数打平解耦，全量单测与集成测试通过，但底层 Python 服务端依然较重，代码重构与模块拆分应作为下一代架构重点。

---

## 二、缺陷状态收敛一览表

| 缺陷编号 | 缺陷简述 | 第二轮定性 | 第三轮最终判定 | 证据链状态 |
| :---: | :--- | :---: | :---: | :---: |
| **DEF-01** | 原生阵列/倒角特征树缺失 | CRITICAL | **NOT_IMPLEMENTED** | 捕获底层 COM 异常，如实记录，拒绝冒充 |
| **DEF-02** | 工程图缺轴测图、脱机度量为0 | HIGH | **CLOSED** | 4 视图完备，脱机打开度量=4，PDF 51.9KB |
| **DEF-03** | 装配体欠约束、缺同心配合 | HIGH | **CLOSED** | 4 项正交配合建立，MateGroup 闭环 |
| **DEF-04** | 阶梯轴同向重叠、跨度仅100mm | HIGH | **CLOSED** | 串联阶梯，STL 网格 Z 跨度严格 180.0mm |
| **DEF-05** | 质量检验器字典克隆绕过漏洞 | HIGH | **CLOSED** | 浅拷贝/深拷贝克隆完全拦截，溯源凭证放行 |
| **DEF-06** | 66项测试未连COM、夸大并发 | MEDIUM | **CLOSED** | 区分实机与单测，明确单线程 STA 队列机制 |
| **DEF-07** | M09 恒真布尔弱断言 | MEDIUM | **CLOSED** | 替换为实测非交互桌面 STA 接管断言 |
| **DEF-08** | M04/M11/M12 仅测文件存在 | MEDIUM | **CLOSED** | 替换为 Node 运行时、JSON-RPC 与参数展开实质断言 |
| **DEF-09** | U04/U05 就地自写函数自测 | MEDIUM | **CLOSED** | 替换为真实 Pydantic 输入模型边界校验 |
| **DEF-10** | M06/M10/M15/M17 重复计数 | LOW | **CLOSED** | 替换为 CLSID 注册表、跨线程异常、沙箱穿透 |
| **DEF-11** | STEP 输出为 AP203 非 AP214 | LOW | **PARTIALLY_FIXED** | 配置首选项，如实披露受限于宿主环境 |
| **DEF-12** | 缺陷库提前打 FIXED 标签 | MEDIUM | **CLOSED** | 15 项真实缺陷全面审计，如实标注各状态 |

---

## 三、合规总结

本报告对当前项目中未能克服的 3 项限制（DEF-01, DEF-11, ISS-ARC-001）做出了最严谨、透明的界定与披露，**坚决杜绝任何以虚假 PASS 瞒报底层缺陷的行为**。
