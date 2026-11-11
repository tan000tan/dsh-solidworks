# 第七阶段独立对抗审查与复现指南
## ChatGPT / 外部第三方独立审计专家复核操作手册

**阶段编号**：STAGE7-GUIDE-01  
**适用对象**：ChatGPT-4o / Claude 3.5 Sonnet / 外部资深机械工程审计团队 / 独立安全审计师  
**目标**：提供 100% 可独立复现、零黑盒、证据驱动的对抗式核验操作路径  

---

### 一、致外部独立审计专家

尊敬的外部独立审计专家：

在阅读本阶段报告或对本项目进行对抗式审查时，请**不要轻信任何文本声称的“成功”或“PASS”**。

我们强烈建议您秉持最严格的工程怀疑态度，按照本指南列出的物理路径、校验哈希、实机运行脚本以及几何检查工具，逐项核实底层真实物证。

---

### 二、物理物证与关键文件速查索引

所有物证文件均已物理落盘于本仓库，您可直接定位并提取以下文件进行独立几何校验：

```
audit/final-independent-review/stage7-extreme-real-world-validation/evidence/
├── mst_shaft.SLDPRT        (SolidWorks 2026 原生主传动轴模型)
├── mst_shaft.STL           (3D 打印三角网格模型，可直接用 MeshLab / Blender 打开)
├── mst_base.SLDPRT         (重载底座安装板模型)
├── mst_gear.SLDPRT         (主动传动齿轮模型)
├── mst_assembly.SLDASM     (完整三部件装配体原生模型)
├── mst_assembly.step       (工业标准 STEP AP214 交换模型，可用 FreeCAD / CAD Assistant 查看)
├── mst_drawing.SLDDRW      (原生机械工程图图纸)
├── mst_drawing.pdf         (矢量工程图 PDF，可用 Adobe Acrobat / 浏览器缩放至 1000% 检验矢量曲线)
└── mst_execution_metrics.json (实机测量的体积、表面积、ECO-01 前后体积增量机器可读文件)
```

---

### 三、三步完成本地极限实机复现

如果您拥有已安装 SolidWorks (2020~2026 任意版本) 的 Windows 工作站，可通过以下三步完全复现实机流程：

#### 第 1 步：环境配置与依赖验证
确保 Python 3.10+ 环境并安装有 `pywin32` 和 `pydantic`：
```powershell
# 在项目根目录下执行
Set-Location "D:\Agent工作区\DeepSeek Harness工作区\dsh-solidworks-plugin"
python -m pip install pywin32 pydantic
```

#### 第 2 步：触发终极复杂模型实机构建
直接运行复现脚本，观察本地 SolidWorks 窗口自动拉伸零件、组合装配体并导出工程图：
```powershell
python -B audit/final-independent-review/stage7-extreme-real-world-validation/execute_ultimate_model.py
```
> **实机验证检查点**：
> 1. 控制台是否打印 `Connected successfully to SolidWorks Revision`；
> 2. `mst_shaft` 体积是否约为 `47958.71 mm^3`；
> 3. `ECO-01 Verified` 体积是否单调递增至 `62634.54 mm^3`（Monotonic Increase: True）；
> 4. `Final open document count` 是否严格等于 `0`（无未关闭文档泄漏）。

#### 第 3 步：运行全套回归自动化门禁
```powershell
# 1. 运行 Node.js 插件门禁与脱敏扫描 (68 项)
npm.cmd test

# 2. 运行 Python 阶段高级 CAD 单元测试 (30 项)
python -B -m unittest discover -s tests -p "stage5_*_test.py"
```
**合格标准**：98/98 测试必须 100% 通过（PASS）。

---

### 四、对抗式几何审查重点（常见造假与漏洞排查清单）

请重点核查以下 6 项容易伪造或隐藏缺陷的 CAD 技术点：

1. **是否只是一个“空壳”或空特征？**
   - **核验方法**：在 FreeCAD 或 SolidWorks 中打开 `mst_base.SLDPRT`，检查质量属性，体积必须在 $7.6 \times 10^5\text{ mm}^3$ 左右，安装孔必须贯穿。
2. **装配体是否真的包含了组件，还是只是一个空的装配体文件？**
   - **核验方法**：打开 `mst_assembly.SLDASM` 或导入 `mst_assembly.step`，组件树中必须存在 3 个独立的实体部件（Base、Shaft、Gear）。
3. **ECO 参数化变更是否真实生效，还是写死了静态数值？**
   - **核验方法**：检查 `execute_ultimate_model.py` 中 `update_dimension_mm(model, "D1@草图1", 40.0)`，然后调用 `collect_mass_properties` 实测体积，其增量必须与数学理论 $\pi (20^2 - 17.5^2) \times 50 \approx 14726\text{ mm}^3$ 高度吻合。
4. **工程图导出的 PDF 是否为假图片或损坏文件？**
   - **核验方法**：打开 `mst_drawing.pdf`，选中线条进行文本/矢量对象放大。必须是标准的矢量多边形与圆弧，而非 72dpi 的低清截图。
5. **是否存在多语言环境适配死穴？**
   - **核验方法**：系统在查找草图与尺寸时，是否支持 `"草图1"` 与 `"Sketch1"` 自动兼容？本阶段已通过 `current_sketch_name` 与模糊回退彻底解决。
6. **是否造成 Windows GDI 句柄泄漏与 SolidWorks 进程挂起？**
   - **核验方法**：在任务管理器中观察 `SLDWORKS.exe`，执行完毕后打开文档数必须归零，GDI 句柄净增长 $\le 10$。

---

### 五、审计评分与意见反馈模板

若您作为第三方审计者，可按照以下格式输出对本阶段的审计结论：

```markdown
### 第三方对抗审计评估表
- **硬件与软件环境真实性**：[ ] 确认真实 / [ ] 存疑
- **物理物证完备性 (SLDPRT/ASM/DRW/STEP/STL/PDF)**：[ ] 齐全可用 / [ ] 缺失损坏
- **几何与拓扑真值吻合度**：[ ] 严密相符 / [ ] 存在漂移
- **参数化与设计意图保真度**：[ ] 完美保持 / [ ] 特征断裂
- **异常捕获与环境自愈能力**：[ ] 工业级稳健 / [ ] 存在崩溃
- **最终综合建议**：[ ] 准予验收并推荐生产 / [ ] 要求整改补充
```
