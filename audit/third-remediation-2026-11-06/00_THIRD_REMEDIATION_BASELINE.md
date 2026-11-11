# 第三轮全量缺陷整改与闭环验收基线报告 (00_THIRD_REMEDIATION_BASELINE.md)

**执行主体**: dsh-solidworks 整改实施工程师 / CAD 几何与自动化测试团队  
**基线建立时间**: 2026-11-06T17:45:00+08:00  
**前序审查依据**: 第二轮独立整改验收报告（最终裁定：`PARTIALLY VERIFIED`）  
**最高纪律约束**: 
1. 绝对保护历史证据：`audit/final-independent-review/`、`audit/remediation-2026-11-06/`、`audit/second-independent-remediation-review/` 处于只读锁定；
2. 本轮全部新物证与报告统一放置于 `audit/third-remediation-2026-11-06/`；
3. 不得自行宣布项目通过，严禁直接发布 v0.2.0-rc1 或 GA v1.0。

---

## 一、当前 Git 工作区与环境基线

- **Git HEAD**: `7d70bc090d5cef146ac3946bb062667ae30a4cc9` (`main` 分支)
- **操作系统**: Windows 11 Pro 64-bit (10.0.26200 AMD64)
- **SolidWorks 环境**: SolidWorks 2026 SP4.1 (ProgID: `SldWorks.Application.34`, 物理进程 PID: 4312)
- **Python 环境**: Python 3.13.16 64-bit (`D:\SWCAD-MCP\Python313\python.exe`)
- **Node.js 环境**: Node.js v22.12.0

---

## 二、第二轮独立审计查明的全部缺陷清单

依据第二轮独立验收报告（《11_UNRESOLVED_DEFECTS.md》、《10_FALSE_PASS_SECOND_SCAN.md》与《02_DEFECT_A_TO_G_REVIEW.csv》），汇总建立待整改缺陷清单：

| 缺陷编号 | 缺陷分类 | 对应源码 / 测试 / 物证位置 | 严重程度 | 核心缺陷事实 | 修复目标与验收门槛 | 是否需要实机验证 |
| :--- | :--- | :--- | :---: | :--- | :--- | :---: |
| **DEF-01** | CAD 特征 | `cad_test_sandbox/` / `sw_part.py` | **CRITICAL** | 原生线性阵列 (`LPattern`)、圆周阵列 (`CirPattern`)、镜像 (`Mirror`)、倒角 (`Chamfer`)、圆角 (`Fillet`) 全军覆没 (`has_lpattern: false`) | 实机调用原生 COM API 生成对应特征树节点并重建；若 API 无法兼容必须诚实标注 `NOT_IMPLEMENTED` | **YES** |
| **DEF-02** | 工程图 | `cad_test_sandbox/remediated_drawing.SLDDRW` | **HIGH** | 缺失轴测图 (Isometric View)；脱机重新打开工程图度量记录 `reopened_views_count: 0` | 在独立零件上生成包含主、俯、左、轴测 4 个有效视图的工程图；验证脱机重新打开后视图持久存在；导出矢量 PDF | **YES** |
| **DEF-03** | 装配体 | `cad_test_sandbox/remediated_assembly.SLDASM` | **HIGH** | 仅有 2 个平面重合配合，严重缺失轴孔同轴配合 (`Concentric Mate`)，径向欠约束 | 在 Base、Shaft、Gear 装配体中同时施加并验证平面重合配合与圆柱同轴配合，消除径向自由度 | **YES** |
| **DEF-04** | 几何真实性 | `cad_test_sandbox/remediated_stepped_shaft.SLDPRT` | **HIGH** | 声明总长 180mm，实际 STL 包围盒跨度仅为 100mm（两段圆柱同基准面同向重叠拉伸冒充台阶） | 严格按第一段 D50xL100mm、第二段端面拉伸 D30xL80mm 构建串联真实阶梯轴，验证包围盒 Z 跨度严格等于 180mm，键槽精准切除 | **YES** |
| **DEF-05** | 质量检查器 | `docs/stage5_advanced_ai_cad/scripts/cad_quality_inspector.py:163` | **HIGH** | 仅检查指针同一性 (`is`)，克隆字典 `theo = dict(meas)` 完全绕过并虚假打出 100 分 `VERIFIED` | 引入数据来源标识与克隆字典特征检测；无独立理论基准时强制打出 `NOT_VERIFIED` 且 `is_acceptable=False` | NO (单测) |
| **DEF-06** | 测试有效性 | `tests/rem_user_test.py`, `tests/rem_stress_test.py`, `tests/rem_compat_test.py` | **MEDIUM** | 补齐的 66 项测试无一调用物理 SolidWorks COM；STA 队列串行被描述成并发；环境属性读取被描述成跨版本矩阵 | 准确标记测试执行机制；单测对接真实插件入口；清晰区分物理实机测试与本地纯算法/队列测试 | NO (单测) |
| **DEF-07** | 虚假 PASS | `tests/rem_compat_test.py:95` | **MEDIUM** | `self.assertIsInstance(is_def, bool)` 恒真弱断言 | 替换为验证桌面交互状态有效性的实质断言 | NO (单测) |
| **DEF-08** | 虚假 PASS | `tests/rem_compat_test.py:65, 107, 113` | **MEDIUM** | 仅用 `os.path.exists("lib/mcp.js")` 检查文件存在即声称协议握手与 Schema 展开成功 | 引入真实的 fastmcp / schema / policy 导出结构和函数调用测试 | NO (单测) |
| **DEF-09** | 虚假 PASS | `tests/rem_user_test.py:62, 76` | **MEDIUM** | 测试函数内部就地编写辅助函数并对其自身进行断言，未测实际插件代码 | 替换为调用插件真实输入验证模型（如 `SolidWorksCreateBasicPartInput` 的 Pydantic 校验） | NO (单测) |
| **DEF-10** | 重复计数 | `tests/rem_compat_test.py` | **LOW** | 兼容性测试存在 4 项直接重复计数 (M06=M05, M10=U09, M15=U09, M17=U08) | 剔除重复计数或重构为具备独立测试价值的不同边界用例 | NO (单测) |
| **DEF-11** | 导出目标 | `cad_test_sandbox/remediated_assembly.step` | **LOW** | 导出为 AP203 (`CONFIG_CONTROL_DESIGN`)，未达到 AP214 目标 | 在 SolidWorks COM 设置中尝试配置 AP214 导出首选项；若受限于当前版本则如实记录 AP203 | **YES** |
| **DEF-12** | 缺陷库状态 | `ISSUE_DATABASE_REMEDIATED.json` | **MEDIUM** | 未完全修复的缺陷被提前打上了 `FIXED` 标签 | 对未完全修复或缺少证据的项目撤销 `FIXED`，修正为 `PARTIALLY_FIXED` 或 `NOT_IMPLEMENTED` | NO (数据) |

---

## 三、第三轮整改最高准则

1. **拒绝虚假包装**：对于因 SolidWorks 2026 API 底层限制无法调通的功能（如特定阵列 API），必须诚实标记为 `NOT_IMPLEMENTED`，并在报告中完整披露 COM 错误代码与根本原因，绝不允许再次通过简化几何或草图画圆进行冒充；
2. **严守物理证据**：所有声称在 SolidWorks 实机中完成的功能，必须以在 `audit/third-remediation-2026-11-06/cad_test_sandbox/` 中生成的新模型、COM 节点遍历日志和网格拓扑解析作为唯一判定依据；
3. **消除弱断言**：全量重构测试用例，彻底消除恒真断言、文件存在冒充功能测试及手写函数自测现象。
