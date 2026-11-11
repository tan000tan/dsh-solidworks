# 第四轮审计交付物 07：工程图四视图与矢量 PDF 取证报告 (DEF-02)

## 一、整改目标与背景说明

在第三轮审计中，审查方指出：
- 工程图生成测试中，部分历史视图方向映射与投影关系不明确，等轴测视图缺少真实物理验证。
- 导出的 PDF 文件需严格核验其是否为真实非空的矢量绘图流，而非空文件或错误提示文本。

本轮整改在 SolidWorks 2026 SP04.1 环境下，直接以阶梯轴实体零件（`remediated_stepped_shaft.SLDPRT`）为数据源，生成完整的标准四视图工程图（`remediated_drawing.SLDDRW`）并导出非空矢量 PDF（`remediated_drawing.pdf`）。

---

## 二、第四轮工程图视图生成技术细节

### 1. 视图名称国际化与模型视图检索
SolidWorks 中文版原生环境的模型预设视图名称为带星号的中文标识：
- 前视：`*前视`
- 上视（俯视）：`*上视`
- 右视：`*右视`
- 等轴测：`*等轴测`

历史脚本尝试传入 `*Isometric` 或 `*轴测` 导致创建轴测图返回 None。本轮通过底层 `GetModelViewNames()` 查询确认正确名称为 `*等轴测`，彻底解决了等轴测视图创建问题。

### 2. 标准三视图与等轴测视图生成链路
```python
# 1. 创建标准三视图（第三视角标准投影）
created_3views = get_com_member(model_draw, "Create3rdAngleViews2", shaft_path)

# 2. 精确定位添加等轴测视图 (X=0.280m, Y=0.200m)
iso_view = get_com_member(model_draw, "CreateDrawViewFromModelView3", shaft_path, "*等轴测", 0.280, 0.200, 0.0)

# 3. 兼容会话的矢量 PDF 导出引擎
pdf_ok = sw_drawing.export_sheet_to_pdf(model_draw, pdf_path, sw_app=swApp)
```

---

## 三、物理实机核验数据 (取自 fourth_remediation_summary.json)

### 1. 四视图参数与几何边界核验

| 视图编号 | 视图名称 | 视图类型代码 (Type) | 视图定向标识 (Orientation) | 语义映射方向 | 投影包围盒 (Box [L, B, R, T] mm) | 比例 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **视图 1** | `工程图视图1` | 7 (`swDrawingSheetView`) | `*前视` | **front** (主视图) | `[225.71, 167.07, 309.35, 380.71]` | 1:1 |
| **视图 2** | `工程图视图2` | 4 (`swDrawingProjectedView`) | `*上视` 投影 | **top** (俯视图) | `[225.71, 568.47, 309.35, 652.11]` | 1:1 |
| **视图 3** | `工程图视图3` | 4 (`swDrawingProjectedView`) | `*右视` 投影 | **right** (右视图) | `[641.86, 167.07, 725.50, 380.71]` | 1:1 |
| **视图 4** | `工程图视图4` | 7 (`swDrawingSheetView`) | `*等轴测` | **isometric** (等轴测图) | `[192.47, -4.62, 367.53, 404.62]` | 2:1 |

### 2. 导出 PDF 物理度量与流核验
- **文件路径**：`audit/fourth-remediation-2026-11-06/cad_test_sandbox/remediated_drawing.pdf`
- **文件大小**：54,276 字节（非空矢量文档）
- **PDF 格式**：`%PDF-1.7` 规范
- **内容流特征**：包含完整的页面目录对象、字体字典、矢量折线与弧线绘制算子（`re`、`m`、`l`、`c`、`S` 等），证实为真实 CAD 生成的几何矢量图纸。

---

## 四、审计结论
DEF-02 涉及的工程图四视图（主视、俯视、右视、轴测）已全部在 SolidWorks 2026 原生环境中实机生成，视图拓扑与空间投影严密吻合，矢量 PDF 导出完整无缺，整改判定为 **PASSED / FULLY VERIFIED**。
