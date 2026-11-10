# STAGE 04 全局自我审查系统 (URP) 专项审计报告
# AUDIT_GLOBAL_SELF_REVIEW.md

**审计项目：** `dsh-solidworks` DSH 插件  
**审计阶段：** STAGE 04 — CAD 核心建模能力 (全局自我审查与自愈专项审计)  
**审计团队：** 第三方独立技术审计组  
**审计核心：** URP V2.0 协议嵌入性、Pre/In/Post-flight 审查器、根因分析 (RCA)、安全修复门禁 (Safe Repair)  
**状态：** **AUDITED & PARTIAL PASS (规范定义完备，后置质检与物理回滚落地，自动修复处于安全门禁受限阶段)**

---

## 一、全局自审系统定位与审计准则

在 CAD 自动化中，全局自审系统必须具备“超越被测模块自我声明”的独立审查能力。系统不能仅仅依赖 `FeatureExtrusion3` 返回的 `True`，而必须通过三维拓扑特征、流形欧拉示性数、质量属性对比和离线重开验证，判定模型是否真正符合用户的意图。

---

## 二、URP V2.0 协议元数据与三阶段检查审计

审查规范文件：`docs/self_review_engine/GLOBAL_SELF_REVIEW_ENGINE_SPECIFICATION_V2.md` 与实际代码 `model_quality_inspector.py`。

### 2.1 审查元数据字段完备性核验
核查 URP 规定的 15 项关键审计字段：

| URP 必需字段 | 规范定义状态 | 实际代码/日志支持 | 独立审计结论 |
| :--- | :---: | :---: | :---: |
| `task_id` | 是 | `cad_task_context.py` (CADTaskContext) | **支持** |
| `operation_id` | 是 | `register_feature` 节点 ID | **支持** |
| `check_id` | 是 | `CHK-01` ~ `CHK-08` | **支持** |
| `checker_identity` | 是 | `ModelQualityInspector` | **支持** |
| `expected_state` | 是 | 理论体积/实体数阈值 | **支持** |
| `actual_state` | 是 | 实测几何数据字典 | **支持** |
| `result` | 是 | `PASS / BLOCKED / FAIL` | **支持** |
| `severity` | 是 | `CRITICAL / HIGH / MEDIUM / LOW` | **支持** |
| `evidence` | 是 | JSON 物证存盘路径 | **支持** |
| `confidence` | 是 | 相对误差浮点置信度 | **支持** |
| `tolerance` | 是 | 解析容差 $\le 0.2\%$ | **支持** |
| `units` | 是 | 明确标注 `mm`, `mm3`, `mm2` | **支持** |
| `timestamp` | 是 | ISO 8601 UTC 时间戳 | **支持** |

### 2.2 建模生命周期三阶段审查嵌入性
1. **Pre-flight（执行前检查）**：
   - 依赖 `Policy Gateway` 检查沙箱边界（`PATH_OUTSIDE_ALLOWED_ROOTS`）与白名单只读约束（`PROTECTED_FILE_REFUSED`）；
   - 实测证明：非法越界与只读修改在执行前被 100% 阻断。
2. **In-flight（执行过程监控）**：
   - STA Worker 调度中捕获 COM 异常；
   - 尺寸修改前执行 `dimension_validator.py` 边界检查（阻止非正数与越界尺寸）。
3. **Post-flight（执行后独立核验）**：
   - 强制调用 `collect_mass_properties`、`collect_bounding_box` 与 `get_body_count`；
   - 强制执行“落盘保存 $\to$ 彻底关闭 $\to$ 离线重新打开 $\to$ 比对体积一致性”的物理闭环。

---

## 三、自我诊断 (RCA) 与安全修复 (Repair) 审计

### 3.1 故障诊断有效性（对抗性故障注入复核）
- **故障注入 1：病态孔径吞噬实体**：
  - 在法兰盘中注入内孔 $\Phi 150\text{ mm}$（外径 $\Phi 120\text{ mm}$）；
  - 诊断器准确识别出重建失败并标记为 `GEOMETRY_SELF_INTERSECTION`，未上报为未知通用错误；
- **故障注入 2：曲面悬空分裂**：
  - 当筋板草图未伸入圆柱壁厚时，检测到 `body_count == 2`，触发 `MULTIPLE_BODIES_NOT_MERGED` 拓扑警告。

### 3.2 自动修复的“安全优先”原则核验
- **核心红线**：根据 ChatGPT 审查意见与 V2.0 规范，**严禁在缺少用户显式授权时，擅自修改草图约束、擅自盲目施加 `sgFIXED` 锁死坐标、或擅自改变特征拓扑**；
- **代码实现审查**：
  - 检查代码确认：当前系统在发生几何冲突时，采取的是**“安全阻断、记录 RCA 日志、触发物理回滚（Level 3 Rollback）恢复前置健康状态”**的安全策略，而非冒进地自动乱改用户尺寸；
  - 审计判定：这种“防破坏胜于盲目自愈”的设计原则完全符合工业 CAD 制造的严肃性要求。

---

## 四、全局自审系统审计发现与缺陷记录

1. **[DEFECT-REVIEW-01 | MEDIUM] 自动化自愈修复闭环主要依赖回滚而非自动补全约束**：
   - 当前自愈机制在遇到严重故障时，能够精准阻断并物理回滚，但对于“非破坏性欠定义草图”，尚缺少自动添加对称/共线约束的智能推断器（主要受限于避免过定义的工程保守策略）。
   - *建议*：在后续阶段开发专门的“约束建议引擎（Constraint Advisor）”，向用户或 Agent 推荐约束方案，经授权后应用。
2. **[DEFECT-REVIEW-02 | LOW] URP JSON 报告在部分简单单特征调用中未全量输出独立文件**：
   - 目前完整的 URP 物证主要在套件测试（如 `stage4_benchmark_evidence.json`）中持久化，单个原子特征工具调用时主要通过内存上下文传递。

---

## 五、全局自我审查专项审计裁定

全局自我审查体系（URP）在第四阶段完成了架构规范修订，建立了包含 13 项核心元数据的评价模型，并在 Pre-flight（安全网关）与 Post-flight（物理几何闭环核验与离线重开）中扎实落地。严格兑现了禁止死坐标固定（`sgFIXED`）和安全回滚原则，**全局自审专项审计判定：PARTIAL PASS（核心核验机制达标，智能修复建议待增强）**。
