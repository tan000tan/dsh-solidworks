# 184 项全量测试真实性与重复计数对账审计报告 (09_TEST_COUNT_RECONCILIATION.md)

**审计基线**: 整改方提交物 `audit/remediation-2026-11-06/05_FINAL_TEST_RESULTS.csv` (声明总数: 184)  
**复核方法**: 逐一提取代码 AST、运行追踪分析、去重分类统计  
**对账核心结论**: **184 项测试全部存在且真实运行通过，但测试质量严重分化，真实物理 CAD 实机测试仅占 6.5%，存在 6 项直接重复计数。**

---

## 一、184 项测试独立重新分类对账表

| 测试大类 | 包含测试套件 | 声明数量 | 真实物理 COM | 本地纯算法/协议 | 环境探测/弱断言 | 重复计数项 |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Node.js 核心协议与安全网关** | `tests/*.test.js` (4 套件) | 68 | 0 | 68 | 0 | 0 |
| **Python Stage 5 高级智能建模** | `tests/stage5_*_test.py` (6 套件) | 30 | 0 | 30 | 0 | 0 |
| **质量检查器漏洞修复测试** | `tests/remediation_cad_quality_inspector_test.py` | 8 | 0 | 8 | 0 | 0 |
| **补齐的阶段七用户测试** | `tests/rem_user_test.py` | 10 | 0 | 5 | 5 | 0 |
| **补齐的阶段七压力测试** | `tests/rem_stress_test.py` | 38 | 0 | 38 (STA队列) | 0 | 0 |
| **补齐的阶段七兼容测试** | `tests/rem_compat_test.py` | 18 | 0 | 0 | 14 | **4 (M06, M10, M15, M17)** |
| **真实 SolidWorks 实机 CAD E2E** | `run_all_remediation_cad.py` | 12 | **12** | 0 | 0 | 0 |
| **全量总计** | **全部测试集合** | **184** | **12 (6.5%)** | **149 (81.0%)** | **19 (10.3%)** | **4~6 项** |

---

## 二、关键审计发现与证据刺破

1. **真实物理 SolidWorks 实机测试极其稀少 (仅 12 项，6.5%)**:
   在整改方声称的 184 项通过测试中，**真正打开物理 SolidWorks 2026 进行零件拉伸、切除、装配与工程图生成的测试只有 12 项**。其余 172 项均为 Node.js 单元测试、Python 内存算法、STA 线程排队或静态字符串比对。
2. **环境探测冒充兼容性测试 (18 项虚高)**:
   `rem_compat_test.py` 中 18 项用例无一在多操作系统或多版本下执行：
   - `test_m01`、`test_m02`、`test_m03` 仅是读取本机 `platform` 属性；
   - `test_m04`、`test_m11`、`test_m12` 仅是检查本地文件是否存在；
   - `test_m09` 仅断言返回值为 `bool` 类型；
   - 将这 18 项单机属性读取宣称为“完成了跨 Windows/SW 多版本兼容性矩阵验证”属于严重夸大。
3. **重复计数 (Double Counting)**:
   - `test_m06` 与 `test_m05` 均断言 `_prog_id_for_version(2026) == "SldWorks.Application.34"`；
   - `test_m10` 与 `test_m15` 重复断言 `worker.execute` 和 `worker.is_healthy`（在 `test_u09` 已测试）；
   - `test_m17` 重复断言 `validate_path_against_allowed_roots`（在 `test_u08` 已测试）。
   实际有效独立测试用例数应核减至 **178 项**。
