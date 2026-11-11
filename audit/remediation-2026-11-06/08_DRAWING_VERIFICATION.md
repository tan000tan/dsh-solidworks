# 工程图三视图与矢量数据流核验报告

**核验对象**: 
- 原生工程图: `audit/remediation-2026-11-06/cad_test_sandbox/remediated_drawing.SLDDRW`
- 矢量导出图: `audit/remediation-2026-11-06/cad_test_sandbox/remediated_drawing.pdf`
**对比对象**: 阶段七原工程图 `MST-AGU-2026-DRAWING.SLDDRW` 与 `MST-AGU-2026-DRAWING.pdf`

---

## 一、整改前后工程图核心指标对比

| 核心指标 | 阶段七原产物 (Defect A) | 本次整改产物 | 独立验证物证 |
| :--- | :--- | :--- | :--- |
| **视图数量 (`GetViewCount`)** | 0 (无任何模型视图) | **4 (1个图纸底板 + 3个正交投影视图)** | COM `GetViewCount()` 返回 4 |
| **视图名称清单** | `[]` | `['图纸1', '工程图视图1', '工程图视图2', '工程图视图3']` | COM `GetViews()` 遍历节点确认 |
| **PDF 文件大小** | 20,664 字节 | **50,893 字节** (+146% 增量) | 磁盘文件字节数测量 |
| **PDF 内容深度** | 仅含标题栏线框，中心完全空白 | **解压流包含 800+ 个矢量绘图指令** | `re.findall(b'[0-9.-]+\s+[0-9.-]+\s+m', stream)` |
| **三视图投影关系** | 无 | **主视、俯视、左视第三视角标准正交对齐** | `Create3rdAngleViews2` 真实执行 |

---

## 二、工程图视图创建失败根因与技术整改

- **根因查明**:
  在 SolidWorks COM 接口中，`IDrawingDoc.Create3rdAngleViews2(modelPath)` 虽然接收模型路径作为入参，但在后台实例化三维模型的图元着色与投影几何体时，**要求该模型文档在当前 SolidWorks 进程内处于已打开（或会话驻留）状态**。原测试脚本在生成完模型后立即调用了 `CloseDoc`，导致紧随其后的 `Create3rdAngleViews2` 静默返回 `False`，图纸上没有任何视图被添加。
- **整改修复方案**:
  重构工程图生命周期管理策略：在保持模型文档打开的受控会话中，执行 `Create3rdAngleViews2`，确认视图数量满足要求后，再统一执行所有文档的安全保存与有序注销。
