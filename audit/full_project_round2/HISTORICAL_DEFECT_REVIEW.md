# 全项目历史缺陷与漏洞专项追溯复核报告

> **报告编号：** `AUDIT-R2-08-HISTORICAL-DEFECT-REVIEW`  
> **审计对象：** dsh-solidworks 全生命周期历史缺陷（DEF-01 至 DEF-16）  
> **归档目录：** `audit/full_project_round2/`  
> **审计性质：** 独立第三方缺陷闭环与风险穿透审计  

---

## 一、历史缺陷全景分类与生命周期总览

审计团队对项目从初创至当前阶段登记的全部 16 项缺陷实施了穿透式源码核查与测试复现，分类统计如下：

| 缺陷编号 | 缺陷标题 | 所属模块 | 风险等级 | 首次发现阶段 | 当前复核状态 | 闭环物证与测试用例 |
|:---:|:---|:---|:---:|:---:|:---:|:---|
| **DEF-01** | 普通用户环境自发现断层（.venv 被忽略） | `lib/discover.js` | **P1** | Phase 1 | **CLOSED** | `tests/mcp.test.js:121, 128, 137` |
| **DEF-02** | 4 个关键工具未录入 `RISK_TABLE` 导致调用被拒 | `lib/policy.js` | **P1** | Phase 1 | **CLOSED** | `tests/package.test.js:121-133` |
| **DEF-03** | `lib/index.js` 内部常量硬编码为 `0.1.0` | `lib/index.js` | **P1** | Phase 1 | **CLOSED** | `tests/mcp.test.js:113` |
| **DEF-04** | Pack and Go 前后端命名失配（`_tool` 后缀） | `server.py` | **P2** | Phase 1 | **CLOSED** | `tests/mcp.test.js:149` |
| **DEF-05** | 默认只读模式拒绝建模时缺乏中文引导向导 | `lib/index.js` | **P2** | Phase 1 | **CLOSED** | 错误返回中追加清晰配置切换指引 |
| **DEF-06** | `package.json` 测试脚本未集成离线测试与 probe | `package.json` | **P2** | Phase 1 | **MITIGATED** | `npm test` 聚合 4 套门禁；Python 单测独立运行 |
| **DEF-07** | `mcp-server/server.py` 膨胀至 7600+ 行技术债务 | `mcp-server/server.py` | **P2** | Phase 1 | **OPEN** | 技术债务，暂不阻断，待后续模块化解耦 |
| **DEF-08** | 审计日志文件缺乏大小切片与自动轮转机制 | `lib/index.js` | **P2** | Phase 1 | **OPEN** | 长期运行潜在膨胀风险，待产品化封版闭环 |
| **DEF-09** | 宿主层缺乏 TypeScript `.d.ts` 类型定义文件 | `lib/` 宿主层 | **P3** | Phase 1 | **OPEN** | 影响第三方开发者体验，待后续补齐 |
| **DEF-10** | 长耗时 COM 操作缺乏心跳与局部超时细化 | `sw_connect.py` | **P3** | Phase 1 | **OPEN** | 依赖宿主 30 秒整包超时兜底 |
| **DEF-11** | 镜像特征崩溃（Mark 参数错误与基准面未语言适配） | `sw_part.py:858` | **P0** | Phase 4 | **OPEN** | 独立实机测试复现 `NoneType` 异常，严禁上层依赖 |
| **DEF-12** | 全局自愈偷换概念（实为 Pre-flight 阻断与回滚清空） | 全局自愈体系 | **P1** | Phase 4 | **OPEN** | 无自愈调整算法代码，已推翻其宣传声明 |
| **DEF-13** | 独立核验器理论体积盲区与孔位偏移钝化 | `model_quality_inspector.py` | **P1** | Phase 4 | **OPEN** | 3 个模型无理论体积，孔位偏移 8mm 仍报 PASS |
| **DEF-14** | Model B 阶梯传动轴键槽切穿半轴结构 | `tests/real_cad/` | **P2** | Phase 4 | **OPEN** | 切深 19mm 超出半径 15mm，需修正建模参数 |
| **DEF-15** | SolidWorks 宿主版本在测试脚本中被硬编码为 2024 | `stage4_benchmark...py` | **P2** | Phase 4 | **CLOSED** | 真实进程版本已查明为 2026 SP4.1，报告已纠偏 |
| **DEF-16** | 工程图系统存在视图重叠与标注断层 | 工程图生成模块 | **P1** | Phase 3 | **OPEN** | 仅有演示级调用，缺乏工程布局排版算法 |

---

## 二、P0 / P1 严重缺陷技术穿透与隔离要求

### 2.1 DEF-11 (P0): 镜像特征崩溃
- **受影响工具：** `solidworks_mirror_feature`
- **复现代码：**
  ```python
  # 实机调用
  part.FeatureManager.InsertMirrorFeature2(False, False, False, False, 4)
  # 返回 None，随后 feat.Name 抛出 AttributeError: 'NoneType' object has no attribute 'Name'
  ```
- **隔离禁令：**
  在第五阶段及后续开发中，**严禁任何上层规划引擎将镜像特征作为可用依赖**。所有涉及对称特征的任务，必须通过对称草图或独立几何特征建立。

### 2.2 DEF-12 (P1): 自愈能力虚假陈述
- **澄清事实：** 项目目前仅具备“失败后物理逆序删除已建特征”的 Level 3 清除能力。
- **隔离禁令：**
  严禁向用户承诺“系统能够自动修复建模错误”。在第五阶段质量优化模块（S5-E）中，必须将“自愈修复”显式定义为“提出修改建议”，由用户或迭代引擎重新调度，不得伪称底层已具备自动修复闭环。

### 2.3 DEF-13 (P1): 独立核验器盲区
- **风险分析：** 若直接将现有的 `ModelQualityInspector` 用于第五阶段多方案比较和质量评分，可能导致严重畸变或孔位错位的模型获得高分。
- **治理要求：**
  在第五阶段质量优化模块（S5-E）中，必须重构核验逻辑，引入几何特征局部坐标采样校验与理论体积严格比对。

---

## 三、缺陷闭环准则与生命周期约束

为防止缺陷“假闭环”，制定如下铁律：
1. **禁止状态伪造：** 不得以“文档声称修复”或“手动修改状态”作为缺陷关闭依据，必须提供独立可运行的测试脚本和断言证据；
2. **防回归测试锁定：** 所有修复的 P0/P1 缺陷，必须在 `tests/` 下建立永久性回归测试用例（如 DEF-01 至 DEF-04 已纳入 `tests/mcp.test.js` 和 `package.test.js`）；
3. **缺陷穿透继承隔离：** 凡标记为 `OPEN` 的 P0/P1 缺陷，必须在第五阶段的依赖矩阵中显式列为 `BLOCKED` 或 `UNVERIFIED`，禁止上层应用未经验证直接调用。
