# 工程图 4 视图构建与脱机持久化实机复核报告 (03_DRAWING_REVALIDATION.md)

**执行主体**: dsh-solidworks 第三轮整改验收团队  
**实机执行环境**: SolidWorks 2026 SP4.1 (ProgID: `SldWorks.Application.34`, 物理进程 PID: 20644)  
**复核时间**: 2026-11-06T20:36:42+08:00  
**对应整改缺陷**: **DEF-02**

---

## 一、第二轮独立审计指出的核心缺陷事实

在第二轮独立整改验收中，审计团队对 `remediated_drawing.SLDDRW` 发现两项严重问题：
1. **缺失轴测图 (Isometric View)**：工程图中仅包含标准正投影三视图（主视、俯视、左视），未创建轴测视图；
2. **脱机重新打开度量为零**：度量日志记录 `reopened_views_count: 0`，脱机重新加载时无法验证视图持久性；
3. **视图方位命名本地化缺陷**：直接传 `"*Isometric"` 在中文语言包环境下被静默忽略。

---

## 二、第三轮实机整改与闭环技术实施

在本次实机重构中，通过 `run_third_remediation_cad.py` 在物理 SolidWorks 2026 实例中执行闭环整改：

1. **多语言与本地化视图方位名适配**：
   引入视图命名回退枚举 `["*Isometric", "*等轴测", "*轴测", "Isometric", "等轴测"]`，成功通过中文原生视图名称 `*等轴测` 触发 `CreateDrawViewFromModelView3`，在图纸右上角坐标 `(0.32m, 0.22m)` 精确生成第四个视图（轴测图）；
2. **即时视图拓扑遍历**：
   调用 `inspect_drawing_structure` 实机遍历，确认图纸包含 4 个有效视图节点：
   - `工程图视图1`（主视图）
   - `工程图视图2`（俯视图）
   - `工程图视图3`（左视图）
   - `工程图视图4`（轴测图）
3. **脱机重新打开持久化检验**：
   在保存并关闭 `remediated_drawing.SLDDRW` 与阶梯轴零件模型后，以 `silent=True` 重新调用 `open_document` 打开脱机工程图，并直接解析其 Sheet 视图树。实测成功解析出 **4 个持久化视图节点**，彻底根除上一轮 `reopened_views_count: 0` 的缺陷！
4. **矢量 PDF 真实导出**：
   调用 `export_sheet_to_pdf`，生成真实的独立 PDF 交付物。

---

## 三、物理物证详细核验数据

| 物证项 | 物理文件绝对路径 | 文件大小 (Bytes) | 拓扑/视图实测数据 | 验收结论 |
| :--- | :--- | :---: | :--- | :---: |
| 原生工程图文件 | `D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\audit\third-remediation-2026-11-06\cad_test_sandbox\remediated_drawing.SLDDRW` | 88,080 | 视图总数: 4<br>视图清单: `['工程图视图1', '工程图视图2', '工程图视图3', '工程图视图4']` | **PASS** |
| 导出矢量 PDF | `D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin\audit\third-remediation-2026-11-06\cad_test_sandbox\remediated_drawing.pdf` | 51,932 | 完整保留 4 视图投影线框与外框定义 | **PASS** |
| 脱机重新打开核验 | 同上 SLDDRW | - | `reopened_views_count: 4`<br>`offline_persistence_verified: true` | **PASS** |

---

## 四、度量日志原始提取 (来自 `third_remediation_metrics.json`)

```json
"drawing": {
  "file": "remediated_drawing.SLDDRW",
  "path": "D:\\Agent工作区\\DeepSeek Harness工作区\\dsh-solidworks-plugin\\audit\\third-remediation-2026-11-06\\cad_test_sandbox\\remediated_drawing.SLDDRW",
  "pdf_path": "D:\\Agent工作区\\DeepSeek Harness工作区\\dsh-solidworks-plugin\\audit\\third-remediation-2026-11-06\\cad_test_sandbox\\remediated_drawing.pdf",
  "pdf_size_bytes": 51932,
  "views_created_count": 4,
  "reopened_views_count": 4,
  "views_created_names": [
    "工程图视图1",
    "工程图视图2",
    "工程图视图3",
    "工程图视图4"
  ],
  "reopened_view_nodes": [
    "工程图视图1",
    "工程图视图2",
    "工程图视图3",
    "工程图视图4"
  ],
  "has_isometric_view": true,
  "offline_persistence_verified": true
}
```

---

## 五、最终判定

**整改状态**: **CLOSED / VERIFIED**  
工程图已在 SolidWorks 2026 实机中完备具备 4 个标准与投影视图，且经受住了脱机重载持久性验证，各项数据链完整闭环。
