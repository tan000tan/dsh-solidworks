# 工程图三视图与矢量 PDF 深度独立审计报告 (03_DRAWING_REAL_VIEW_AUDIT.md)

**审计对象**: 
- 原生工程图文件: `audit/remediation-2026-11-06/cad_test_sandbox/remediated_drawing.SLDDRW` (92,987 字节)
- 矢量导出 PDF: `audit/remediation-2026-11-06/cad_test_sandbox/remediated_drawing.pdf` (50,893 字节)
**复核方法**: 真实 SolidWorks 2026 COM 接口只读遍历、底层数据指标审计、PDF 内部流矢量算子提取  
**本项最终裁定**: **`PARTIALLY VERIFIED` (部分验证，未完全达到要求)**

---

## 一、真实工程图视图逐一核验

依据任务书最高要求：**严格区分图纸底板、主视图、俯视图、侧视图和轴测图；主视图、俯视图、侧视图和轴测图均需实际证据；若无轴测图明确判定未完全通过。**

通过 SolidWorks COM 接口在只读模式下提取的视图节点如下：

| 视图序号 | 视图名称 (`GetName2`) | 视图类型 (`Type`) | 是否为模型投影视图 | 视角与方向 (`Orientation`) | 独立审计结论 |
| :---: | :--- | :--- | :---: | :--- | :--- |
| **0** | `图纸1` | `swDrawingSheet` | **否 (图纸底板)** | 图纸本身背景，非模型投影 | **不能计入模型视图** |
| **1** | `工程图视图1` | `swDrawingStandardView` | **是** | 正视 / 前视图 (Front) | **FOUND (主视图)** |
| **2** | `工程图视图2` | `swDrawingProjectedView` | **是** | 俯视图 (Top) | **FOUND (俯视图)** |
| **3** | `工程图视图3` | `swDrawingProjectedView` | **是** | 左视 / 侧视图 (Left) | **FOUND (侧视图)** |
| **--** | **轴测图 (Isometric View)** | **--** | **无** | **缺失** | **MISSING (未找到轴测图)** |

### 核心物证缺陷查明：
1. **轴测图缺失**: 
   整改方调用的是 SolidWorks 官方宏 API `Create3rdAngleViews2(shaft_path)`，该 API 在标准定义下**仅生成第三视角的正交三视图（主、俯、左），并不包含右上角的轴测图（Isometric View）**。虽然整改脚本中尝试调用了 `CreateDrawViewFromModelView3(..., "*Isometric", 0.32, 0.22, 0.0)`，但该调用在 SolidWorks 2026 COM 强类型环境下返回了空对象，未能在工程图中生成轴测图！
2. **脱机打开视图丢失缺陷**:
   在整改方自行记录的原始度量数据 `remediation_execution_metrics.json` 中，明确记录了：
   ```json
   "views_created_count": 3,
   "reopened_views_count": 0
   ```
   当关闭源零件并重新只读打开 `remediated_drawing.SLDDRW` 时，由于 SolidWorks 需要解析外部零件引用，在无头静默环境下 `reopened_views_count` 降为 0，工程图脱机持久性存在依赖缺陷。

---

## 二、PDF 可视化与矢量数据流审计

- **文件大小**: 50,893 字节（相比阶段七空白 PDF 的 20,664 字节，增加了 30,229 字节）。
- **解压数据流审计**:
  对 PDF 文件的数据流执行 Deflate 解压，扫描到以下图元操作符：
  - `m` (moveto): 214 次
  - `l` (lineto): 348 次
  - `c` (curveto): 192 次
  - `re` (rectangle): 68 次
- **可视内容确认**:
  解压流中确认包含了阶梯轴外轮廓、圆柱投影母线及中心对称线图元，彻底排除了阶段七的“白板空 PDF”虚假 PASS 问题。

---

## 三、结论与判定

整改方成功修复了“视图为 0”与“PDF 白板”的严重错误，生成了有效的主视、俯视、侧视三视图。但根据本轮审计预设的刚性准则：**缺少轴测图且重新打开离线视图计数为 0，本项明确判定为 `PARTIALLY VERIFIED`。**
