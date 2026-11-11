# 导出格式 STEP 与 STL 二进制深度独立审计报告 (07_STEP_STL_BINARY_AUDIT.md)

**审计产物**:
1. STEP: `audit/remediation-2026-11-06/cad_test_sandbox/remediated_assembly.step` (65,331 字节)
2. STL: `audit/remediation-2026-11-06/cad_test_sandbox/remediated_stepped_shaft.STL` (17,684 字节)
**本项最终裁定**: **`VERIFIED WITH LIMITATIONS` (带限制验证通过)**

---

## 一、STEP 文件协议与实体审计

- **文件头结构**:
  ```text
  ISO-10303-21;
  HEADER;
  FILE_DESCRIPTION (( 'STEP AP203' ), '1' );
  FILE_NAME ('remediated_assembly.step', '2026-11-06T08:30:21', ...);
  FILE_SCHEMA (( 'CONFIG_CONTROL_DESIGN' ));
  ENDSEC;
  ```
- **版本审计**:
  文件明确标识为 **`STEP AP203`**，模式为 `CONFIG_CONTROL_DESIGN`。
- **协议版本对照**:
  项目《FEATURE_MATRIX.md》声明支持“标准 AP203/AP214 格式无损导出”。当前导出为 AP203，符合基线最低要求，但**未达到更高阶的 AP214（支持颜色与图层属性交换）导出目标**。
- **实体完整性**: 包含 4 项 `PRODUCT`、3 个 `CLOSED_SHELL`（对应底板、轴、齿轮 3 个实体壳），无组件丢失。

---

## 二、STL 二进制拓扑与网格水密性深度审计

对 `remediated_stepped_shaft.STL` 二进制数据执行严格拓扑网络重建：

| 拓扑几何指标 | 阶段七原产物 (Defect E) | 本次整改产物 | 拓扑健康标准 | 独立审计结论 |
| :--- | :--- | :--- | :--- | :--- |
| **三角面片数 ($F$)** | 9 (单面残片) | **352** | $F > 100$ | **PASS (完整网格)** |
| **空间顶点数 ($V$)** | 8 | **178** | -- | **PASS** |
| **唯一拓扑边数 ($E$)** | 15 | **528** | $3F = 2E$ (1056=1056) | **PASS (无孤立边)** |
| **欧拉示性数 ($\chi$)** | 1 (破损开流形) | **2** | $\chi = V - E + F = 2$ | **PASS (球面同胚)** |
| **非流形边数** | 3 | **0** | 必须为 0 | **PASS (严格二维流形)** |
| **退化三角形数** | 0 | **0** | 必须为 0 | **PASS (无零面积面片)** |
| **水密性状态** | 严重漏水 (破孔) | **100% 封闭水密** | 每条边恰被 2 个面共享 | **VERIFIED** |

### 尺寸约束与限制披露：
虽然 STL 网格在数学拓扑上 100% 水密，但其实际尺寸包围盒为 $50 	imes 49.88 	imes 100	ext{ mm}$，与整改报告声称的 180mm 阶梯轴尺寸存在不一致（详见 05 报告）。
