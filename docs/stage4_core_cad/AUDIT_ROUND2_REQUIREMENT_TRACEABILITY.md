# STAGE 04 第二轮原始需求与第一轮审计复核追踪表
# AUDIT_ROUND2_REQUIREMENT_TRACEABILITY.md

**审计项目：** `dsh-solidworks` DSH 插件  
**审计性质：** 第二轮独立证据复核（纠偏与证据缺口深挖）  
**审计基准：** 《第四阶段开发任务书》/ 证据等级 E0~E4 / 事实优先于结论  
**状态：** **COMPLETED (推翻第一轮虚高判定，真实暴露证据缺口与未完成项)**

---

## 一、复核说明与口径定义

第一轮审计报告给出的“16 项 PASS / 7 项 PARTIAL / 0 项 FAIL / 阶段 ACCEPTED”结论，经过本轮穿透式核查，发现存在严重的评定标准放宽与概念偷换：
1. **将“草图级重复几何”冒充为“特征级圆周阵列”**；
2. **将“中面对称拉伸”冒充为“特征级镜像”**（实机镜像接口因多语言基准面与选择 Mark 错误而无法运行）；
3. **将“逆序物理回滚（删除清空）”冒充为“自动修复（自愈）”**；
4. **将“单特征法兰跑通”推导为“DSH 端到端复杂建模成熟”**；
5. **七大模型验证存在严重几何盲区（仅比对实体数、体积和包围盒，未校核具体孔径、孔位、孔深及局部截面特征）**。

本表对第四阶段 24 项原始需求进行重新定级与事实核销。

---

## 二、24 项原始需求第二轮独立穿透复核矩阵

| Req ID | 原始要求 | 实际代码实现位置 | 测试方法 | 真实证据位置 | 第一轮状态 | 第二轮独立状态 | 未完成内容 (Gap) | 最终判断 |
| :---: | :--- | :--- | :--- | :--- | :---: | :---: | :--- | :---: |
| **REQ-01** | **二维草图图元**（线、圆、弧、矩形、多边形） | `sw_part.py:566-630` | 实机绘制与成型 | `stage4_benchmark_evidence.json` | PASS | **PASS (E4)** | 样条曲线在高精度非均匀有理 B 样条控制上未完全闭环 | **PASS** |
| **REQ-02** | **几何关系约束**（杜绝 `sgFIXED` 死坐标） | `sw_part.py:721-732` | 约束添加与求解检查 | Model A~G 实机草图 | PARTIAL | **PASS (E4)** | 约束求解依赖 SW 内部求解器，未暴露细粒度冲突解析，但已严格杜绝死坐标 | **PASS** |
| **REQ-03** | **尺寸约束驱动**（真实 DisplayDimension） | `sw_part.py:632-714` | 尺寸修改与重建 | `phase4_modeling_evidence.json` | PASS | **PASS (E4)** | 复杂自相交轮廓时自动标注易过定义，主要由显式参数驱动 | **PASS** |
| **REQ-04** | **拉伸凸台**（单向、对称、合并结果） | `sw_part.py:737-774` | 实机特征创建 | Model A, C, D, G | PASS | **PASS (E4)** | 无重大缺陷，单位转换与法向控制正常 | **PASS** |
| **REQ-05** | **拉伸切除**（贯通/盲孔，严防空气空切） | `sw_part.py:776-801` | 实机切槽与切孔 | Model A, B, C, E, F | PASS | **PASS (E4)** | 区分基准面与表面法向，切除体积正向减少验证完备 | **PASS** |
| **REQ-06** | **旋转凸台**（360°回转体、轴向成型） | `sw_part.py:822-835` | 阶梯轴实机回转 | Model B (`model_b_stepped_shaft.SLDPRT`) | PASS | **PASS (E4)** | 必须显式创建中心线，部分偏心轴线场景支持偏窄 | **PASS** |
| **REQ-07** | **旋转切除**（环形槽、密封槽） | `sw_part.py:837-850` | 单元调用 | 缺乏独立 E4 模型 | PARTIAL | **NOT VERIFIED (E1)** | A~G 七大模型中无旋转切除实例，仅有代码实现，缺少实机证据 | **NOT VERIFIED** |
| **REQ-08** | **圆角特征**（棱边固定与变半径圆角） | `sw_part.py:862-878` | 单元调用 | 缺乏复杂过渡实测 | PARTIAL | **PARTIAL (E3)** | 仅支持基础固定半径圆角，变半径与面圆角未实现，易受拓扑引用失效影响 | **PARTIAL** |
| **REQ-09** | **倒角特征**（端面与棱边角度倒角） | `sw_part.py:852-860` | Model B 轴端倒角 | `model_b_stepped_shaft.SLDPRT` | PASS | **PASS (E4)** | 1.5mm x 45° 倒角在 Model B 实机生成有效 | **PASS** |
| **REQ-10** | **孔特征**（通孔、沉头孔、异型孔向导） | `sw_part.py` (拉伸切孔) | 切除成型孔 | Model A, C, G | PARTIAL | **PARTIAL (E4)** | 仅通过拉伸切除圆柱孔实现，标准异型孔向导（HoleWizard）未封装 | **PARTIAL** |
| **REQ-11** | **线性阵列**（单向/双向特征阵列） | `sw_pattern.py:linear_pattern` | 单元测试 | `sw_pattern.py` | PARTIAL | **PARTIAL (E3)** | 底层代码调用了 `FeatureLinearPattern4`，但 A~G 模型中未直接作为主流程验证 | **PARTIAL** |
| **REQ-12** | **圆周阵列**（特征级圆周分布孔/齿） | `sw_pattern.py:circular_pattern` | 实机单独调用成功 | `verify_pattern_mirror.py` 实测成功 | PARTIAL | **PARTIAL (E4)** | 底层具备 `FeatureCircularPattern4`，但 Model C 采用草图多圆切除替代，工作流未打通 | **PARTIAL** |
| **REQ-13** | **镜像特征**（关于基准面对称镜像） | `sw_part.py:mirror_feature` | 实机独立测试直接报错 | 抛出 `'NoneType' object has no attribute 'Name'` | UNVERIFIED | **FAIL (E1)** | 选择 Mark 错误 (用了 mark=4 实体标记) 且中文基准面别名未解析，实机调用崩溃 | **FAIL** |
| **REQ-14** | **参数化驱动**（尺寸联动与形变） | `dimension_modifier.py` | 上游修改下游重建 | 实测体积形变 $144\text{k} \to 158\text{k mm}^3$ | PASS | **PASS (E4)** | 单零件参数修改有效，跨装配全局方程式未开放 | **PASS** |
| **REQ-15** | **特征树依赖**（DAG 依赖解析与防环） | `cad_task_context.py` | 逆序特征追踪 | `cad_graph_executor_test.py` | PARTIAL | **PARTIAL (E2/E3)** | 仅维护了 Python 内存依赖树，未直接抽取 SW 底层 `GetParents`/`GetChildren` 拓扑树 | **PARTIAL** |
| **REQ-16** | **模型强行重建**（ForceRebuild3） | `sw_connect.py` | 尺寸修改后强制重解 | 全套实机脚本强制嵌入 | PASS | **PASS (E4)** | STA 线程内同步重建执行稳定，未发现重建死锁 | **PASS** |
| **REQ-17** | **几何测量**（质量属性与包围盒独立提取） | `sw_measure.py` | 底层 COM 直接度量 | 全套模型独立实测 | PASS | **PASS (E4)** | 测量准确，但对内部局部截面尺寸（孔深、孔位）缺乏细粒度查询工具 | **PASS** |
| **REQ-18** | **特征树状态探测**（遍历与类型校验） | `sw_part.py:list_feature_names` | 遍历特征节点 | `audit_stage4_independent_verifier.py` | PASS | **PASS (E4)** | 支持全树线性遍历，子特征嵌套展开支持不足 | **PASS** |
| **REQ-19** | **FeatureGraph 编排**（拓扑调度与执行） | `cad_graph_executor.py` | DAG 调度测试 | `cad_graph_executor_test.py` | PARTIAL | **PARTIAL (E2)** | 单元测试通过，但在真实 CAD 实机套件中未被作为主执行器驱动全量模型 | **PARTIAL** |
| **REQ-20** | **事务与故障恢复**（失败后模型复原） | `cad_task_context.py` | 逆序卸载 4 项特征 | `phase4_modeling_evidence.json` | PASS | **PASS (E4)** | 实测逆序物理卸载，实体清零，复原机制有效（但仅为回滚，非修复） | **PASS** |
| **REQ-21** | **独立质量验证**（URP V2.0 规范接入） | `model_quality_inspector.py` | 后置几何与重开校验 | 全套物理模型落盘与重开核验 | PASS | **PARTIAL (E4)** | 实现了后置质量比对，但检查器存在“体积包围盒一致但局部错位无法感知”的盲区 | **PARTIAL** |
| **REQ-22** | **自我诊断 (RCA)**（根因分析与分类） | `cad_task_context.py` | 故障注入拦截 | 捕获相交与越界错误 | PARTIAL | **PARTIAL (E3)** | 能捕获越界与相交错误，但对复杂几何拓扑退化缺少精确根因建议 | **PARTIAL** |
| **REQ-23** | **安全自动修复**（智能自愈与约束补全） | 无实际修复逻辑 | 只有物理回滚卸载 | 第一轮报告虚构为自动修复 | PASS | **FAIL / NOT IMPLEMENTED (E0)** | 核心缺陷！系统根本没有自动补全约束或几何修复能力，仅靠删除回滚冒充修复 | **FAIL** |
| **REQ-24** | **DSH Agent 端到端复杂建模** | `server.py` + `lib/index.js` | 单次法兰落盘测试 | `dsh_phase4_e2e_evidence.json` | PASS | **PARTIAL (E3)** | 仅能证明工具可被发现与单次落盘，未验证 Agent 面对复杂长多特征零件的稳定规划 | **PARTIAL** |

---

## 三、第二轮核销统计与结论

- **全量达标项 (PASS)**：**11 项**（占比 45.8%）；
- **部分完成项 (PARTIAL)**：**10 项**（占比 41.7%）；
- **未验证项 (NOT VERIFIED)**：**1 项**（旋转切除缺少实机物证）；
- **失败 / 虚假实现项 (FAIL)**：**2 项**（镜像特征实机调用崩溃；自动修复根本未实现，属于偷换概念）。

**复核最终判定：** 原始需求中仅 11 项真正达到严格 PASS，未完成度与部分实现度高达 54.2%，第一轮给出的 `ACCEPTED` 结论完全不成立，必须予以推翻！
