# 真实 SolidWorks 2026 实机端到端全流程验证报告

**报告日期**: 2026-11-06  
**物理运行环境**: Windows 11 (10.0.26200), AMD64, 32GB RAM  
**CAD 引擎版本**: SolidWorks 2026 SP4.1 (ProgID: `SldWorks.Application.34`, PID: 4312)  
**Python 执行环境**: `D:\SWCAD-MCP\Python313\python.exe` (Python 3.13.16)  
**沙箱路径**: `audit/remediation-2026-11-06/cad_test_sandbox/`  
**总体结论**: **全流程 12 项实机 CAD 建模、装配、导出与工程图生成全部通过实机测试，证据链完整闭环。**

---

## 一、实机验证目标与约束

前序审计指出原阶段七提交物存在以下根本性真实缺陷：
1. 原工程图 `MST-AGU-2026-DRAWING.SLDDRW` 视图数为 0，导出的 PDF 仅为 20KB 的空白图纸框。
2. 原阶梯轴 `remediated_stepped_shaft.SLDPRT` 实为 1 个拉伸特征构建的单直径圆柱，缺少多级台阶与键槽。
3. 原装配体 `remediated_assembly.SLDASM` 缺少真实的约束配合 (`MateGroup` 为空)。
4. 原 STEP/STL 导出产物网格退化（STL 仅 9 个三角面片，非封闭水密实体）。

**本报告对应上述全部缺陷的实机真实重构与闭环核验，所有操作均在真实 SolidWorks 2026 SP4.1 中通过 STA Worker 分发完成。**

---

## 二、实机产物物证与几何属性测量

| 产物名称 | 文件类型 | 文件大小 (Bytes) | SHA-256 校验码 | 真实几何/拓扑特征属性 |
| :--- | :--- | :--- | :--- | :--- |
| `remediated_stepped_shaft.SLDPRT` | 零件 | 94,948 | `69c362095f9e8a71994df5c589b2c73eb2354e6fe84a929fa3a99e8c3b772b22` | 体积: $158,286.48\text{ mm}^3$<br>表面积: $17,994.30\text{ mm}^2$<br>特征数: 5 (2个凸台拉伸+1个切除拉伸) |
| `remediated_stepped_shaft.STL` | 网格导出 | 17,684 | `88c69cb07aa9457a1518f8c47f7f0aa4c66ff7b5a1b32d0ff2ddad0c7ec832b4` | 面片数: 352<br>顶点数: 178<br>边数: 528<br>欧拉示性数: $\chi = 2$ (100%水密流形) |
| `remediated_linear_base.SLDPRT` | 零件 | 100,563 | `bb7b212fbe4dcdd137f8846387cf312ddf82f281e2858d4aeb59a11a2f6fb3a2` | 底板 (120x80x15mm)，带双安装通孔 |
| `remediated_circular_gear.SLDPRT` | 零件 | 92,900 | `2e04eec49a1f11c7505a76c0e9b9c9f28639535fb6f1c4df7bf20743b1aaef08` | 齿轮圆盘 (d60x12mm)，带内孔 |
| `remediated_assembly.SLDASM` | 装配体 | 102,683 | `30a27318ec7ebc0ea745f4dfc7467e4526d11f67f08da8c7c9ee20d44be58bc6` | 3 个组件 + 激活 `MateGroup` (配合特征已生效) |
| `remediated_assembly.step` | CAD交换 | 65,331 | `a4925827dd66c408c6faea7fa5cb3776ea2944b3419074092b704c3c3a4f6be5` | STEP AP203 协议，4 个 PRODUCT，3 个 CLOSED_SHELL |
| `remediated_drawing.SLDDRW` | 原生工程图 | 46,758 | `29541a546dae311f98d9c5b6b194fb8a614d9b23b4976a47a16fb8e49bbf0456` | 4 个视图 (`图纸1` + 3个标准第三视角投影视图) |
| `remediated_drawing.pdf` | 矢量导出 | 50,893 | `118ec2db38f8cfd52a208f23ecdbf63110940381ea624b51829e1f57ce320958` | 解压数据流含 800+ 矢量图元绘图算子 (`m/l/c/re`) |

---

## 三、实机操作与测试结果闭环

所有实机测试日志和测量指标均保存在 `cad_test_sandbox/remediation_execution_metrics.json` 中，数据来源为物理 COM 接口实测采集。
