# 全量测试数量、类别与重复计数彻底对账报告 (09_TEST_COUNT_RECONCILIATION.md)

**执行主体**: dsh-solidworks 第三轮整改验收团队  
**对账时间**: 2026-11-06T20:36:42+08:00  
**对应整改缺陷**: **DEF-06, DEF-10**

---

## 一、第二轮审计揭露的测试数量与分类失真

在第二轮独立审计中，审计团队在《03_TEST_EVIDENCE_RECONCILIATION.md》与《10_FALSE_PASS_SECOND_SCAN.md》中指出了三项严重问题：
1. **测试机制混淆 (DEF-06)**：
   上一轮整改补齐的 66 项测试（`rem_user_test.py` 10项、`rem_compat_test.py` 18项、`rem_stress_test.py` 38项）全为本地纯 Python/Node.js 逻辑断言，无一连接物理 SolidWorks COM 实例，却被包装为“实机测试”；
2. **并发能力夸大 (DEF-06)**：
   压力测试 Category C 将基于 Windows 单线程单元（STA）的串行任务队列调度描述为“并发与重入”，夸大了 COM 并行能力；
3. **重复计数虚增 (DEF-10)**：
   `rem_compat_test.py` 中存在 4 处完全重复的代码和断言（M06 与 M05 均为版本字符串断言；M10/M15 与 U09 均为简单的线程乘法断言；M17 与 U08 均为简单的沙箱路径断言）。

---

## 二、第三轮测试去重与实质化重构

在第三轮整改中，我们对全量测试用例进行了彻底的去重与实质化改造：

### 1. 彻底消除重复计数 (DEF-10)
- **M06**: 彻底重构为调用 Windows 注册表 API 读取 `HKEY_CLASSES_ROOT\SldWorks.Application.34\CLSID`，物理断言 CLSID `{666aaee2-7a21-40fc-b768-2078840a88c3}` 的真实存在（与 M05 的 ProgID 字符串映射完全独立）；
- **M10**: 彻底重构为验证 STA 工作线程内部异常向上跨线程透传且线程自愈（消除与 U09 的重复计算）；
- **M15**: 彻底重构为工作线程在注入连续异常冲击后的生命周期鲁棒性与任务恢复测试（消除与 U09 探活的重复）；
- **M17**: 彻底重构为目录穿越攻击（`..\..\Windows\System32\evil.dll`）沙箱防御拦截测试（消除与 U08 的重复）。

### 2. 测试分类透明化与机制解耦 (DEF-06)
- **清晰界定测试类别**：
  - **A 类：物理实机 CAD COM 自动化端到端测试**（必须依赖 Windows Desktop 物理 SolidWorks 2026 实例，生成实体物证）；
  - **B 类：插件核心协议与安全边界测试**（Node.js MCP 协议、沙箱规则、Schema 打平与解包）；
  - **C 类：STA 架构与并发排队防护测试**（单线程任务队列排队、跨线程异常传递、超时丢弃，明确标注非多线程并行）；
  - **D 类：输入验证与算法模型单元测试**（Pydantic Schema 校验、质量检验器克隆防御、数据溯源）。

---

## 三、第三轮全量测试对账清单 (总计 175 项自动化测试)

### 1. Node.js MCP 协议与安全策略测试套件 (68 项)
- **执行脚本**: `npm test`
- **日志路径**: `audit/third-remediation-2026-11-06/test_execution_logs/npm_test_suite.log`
- **细分对账**:
  - `tests/policy.test.js`: **27 项** (工具风险等级、沙箱路径越界拦截、Junction 穿透防护) -> **27 PASS**
  - `tests/mcp.test.js`: **13 项** (JSON-RPC 2.0 握手、工具列表发现、挂起超时、取消信号) -> **13 PASS**
  - `tests/schema.test.js`: **16 项** (FastMCP 参数解包与打平、嵌套对象与数组提取) -> **16 PASS**
  - `tests/package.test.js`: **12 项** (打包清单、依赖完备性、路径泄露扫描、许可协议) -> **12 PASS**
- **小计**: **68 / 68 PASS (100%)**

### 2. Python 用户交互场景与边界测试套件 (10 项)
- **执行脚本**: `tests/rem_user_test.py`
- **日志路径**: `audit/third-remediation-2026-11-06/test_execution_logs/rem_user_test.log`
- **细分对账**: U01 ~ U10（含 U04/U05 真实 Pydantic 输入模型边界校验）
- **小计**: **10 / 10 PASS (100%)**

### 3. Python 环境兼容性与注册表实测套件 (18 项)
- **执行脚本**: `tests/rem_compat_test.py`
- **日志路径**: `audit/third-remediation-2026-11-06/test_execution_logs/rem_compat_test.log`
- **细分对账**: M01 ~ M18（无重复项，实测 Node、CLSID、交互桌面与 STA 守护线程、沙箱目录穿越）
- **小计**: **18 / 18 PASS (100%)**

### 4. Python 极端压力与 STA 任务队列测试套件 (38 项)
- **执行脚本**: `tests/rem_stress_test.py`
- **日志路径**: `audit/third-remediation-2026-11-06/test_execution_logs/rem_stress_test.log`
- **细分对账**: Category A (6项)、Category B (6项)、Category C (5项 - STA 单线程顺序排队)、Category D (5项)、Category E (4项)、Category F (7项)、Category G (5项)
- **小计**: **38 / 38 PASS (100%)**

### 5. Python 质量检验器防御与克隆拦截专项套件 (11 项)
- **执行脚本**: `tests/remediation_cad_quality_inspector_test.py`
- **日志路径**: `audit/third-remediation-2026-11-06/test_execution_logs/remediation_cad_quality_inspector_test.log`
- **细分对账**: Test 01 ~ Test 11（含场景 9 浅拷贝拦截、场景 10 深拷贝拦截、场景 11 溯源凭据放行）
- **小计**: **11 / 11 PASS (100%)**

### 6. Python 阶段五 AI CAD 高级模块单元测试套件 (30 项)
- **执行脚本**: `tests/stage5_*.py`
- **日志路径**: `audit/third-remediation-2026-11-06/test_execution_logs/stage5_unit_tests.log`
- **细分对账**: 协调器 (5项)、装配规划器 (5项)、自动迭代器 (5项)、特征树优化器 (5项)、多方案规划器 (4项)、检验器基础项 (6项)
- **小计**: **30 / 30 PASS (100%)**

---

## 四、实机物理端到端 CAD 测试套件 (独立物理执行)

- **执行脚本**: `audit/third-remediation-2026-11-06/cad_test_sandbox/run_third_remediation_cad.py`
- **连接进程**: 物理 SolidWorks 2026 SP4.1 (PID: 20644)
- **产生物证**:
  1. `remediated_stepped_shaft.SLDPRT` (真实串联阶梯轴，STL Z 跨度严格 180.0mm)
  2. `remediated_stepped_shaft.STL` (15,684 字节，312 个三角形网格)
  3. `remediated_base.SLDPRT` (80,065 字节，带中心通孔与种子孔)
  4. `remediated_gear.SLDPRT` (78,272 字节，法兰盘与内配合孔)
  5. `remediated_assembly.SLDASM` (65,747 字节，4 个真实有效配合，包含 MateGroup)
  6. `remediated_assembly.step` (66,941 字节，STEP 导出)
  7. `remediated_drawing.SLDDRW` (88,080 字节，4 视图，脱机重新打开度量=4)
  8. `remediated_drawing.pdf` (51,932 字节，矢量工程图)
  9. `third_remediation_metrics.json` (完整实机度量指标数据)

---

## 五、对账结论汇总表

| 测试大类 | 测试用例数 | 实际通过数 (PASS) | 失败数 (FAIL) | 是否连接物理 SolidWorks COM | 虚假/弱断言数 | 重复计数 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| Node.js MCP 协议与安全策略 | 68 | 68 | 0 | 否 (协议层 Mock/Stdio) | 0 | 0 |
| Python 用户交互场景 | 10 | 10 | 0 | 否 (Pydantic/配置层) | 0 | 0 |
| Python 环境兼容性与注册表 | 18 | 18 | 0 | 否 (Win32 API/注册表) | 0 | 0 |
| Python 极端压力与 STA 队列 | 38 | 38 | 0 | 否 (STA 队列/算法边界) | 0 | 0 |
| Python 质量检验器克隆防御 | 11 | 11 | 0 | 否 (几何算法单元层) | 0 | 0 |
| Python 阶段五 AI CAD 单元测试 | 30 | 30 | 0 | 否 (纯逻辑算法单元层) | 0 | 0 |
| **自动化测试总计** | **175** | **175** | **0** | **已全量去重与实质化** | **0** | **0** |
| **物理 SolidWorks E2E 测试** | **6 组场景** | **全量完成** | **0** | **是 (PID 20644)** | **0** | **0** |

**裁定**: 彻底消除了重复计数与虚假包装，全量 175 项自动化测试及物理 SolidWorks CAD 实机套件均具备完整的原始日志与物理物证支撑。
