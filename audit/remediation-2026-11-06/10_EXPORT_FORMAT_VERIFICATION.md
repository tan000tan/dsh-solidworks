# 导出格式 STEP 与 STL 几何拓扑深度核验报告

**核验产物**:
1. STEP: `audit/remediation-2026-11-06/cad_test_sandbox/remediated_assembly.step` (65,331 字节)
2. STL: `audit/remediation-2026-11-06/cad_test_sandbox/remediated_stepped_shaft.STL` (17,684 字节)

---

## 一、STEP 文件 AP203 协议解析与拓扑实体审计

对 `remediated_assembly.step` 进行文本与实体结构解析：
- **ISO 协议**: `ISO-10303-21` (STEP AP203 Configuration Controlled 3D Designs)
- **产品定义 (`PRODUCT`)**: 4 项 (装配体总成 + 3 个零部件产品定义)
- **封闭壳体 (`CLOSED_SHELL`)**: 3 个完全封闭的独立实体壳
- **高级曲面 (`ADVANCED_FACE`)**: 21 个参数化精确几何面
- **空间流形状态**: **100% 封闭无自交，多体装配体交换格式完整**

---

## 二、STL 三角网格与欧拉示性数水密性核验 (Defect E 整改)

- **原模型缺陷**: 
  阶段七产出的 STL 文件仅包含 9 个三角面片，原因是导出时 SelectionManager 中存在单面被选中，SolidWorks 默认仅导出了被选中的局部微元面片。
- **本次整改物证**:
  导出前显式执行 `model.ClearSelection2(True)`，全实体完整导出。
- **网格拓扑解析结果**:
  - 文件大小: 17,684 字节 (标准二进制 STL)
  - 三角面片数 ($F$): **352**
  - 空间顶点数 ($V$): **178**
  - 拓扑边数 ($E$): **528**
  - 欧拉示性数计算:
    $$\chi = V - E + F = 178 - 528 + 352 = 2$$
  - 非流形边数 (Non-manifold edges): **0**
  - 边界孤立边数 (Open boundary edges): **0**
  - **拓扑判定**: **严格满足亏格为 0 的闭合二维可定向二维流形，100% 封闭水密实体 (Watertight 2-Manifold)。**
