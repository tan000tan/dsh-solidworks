# 既有清理与验收报告真实性审计：SolidWorks 实机测试结果审查报告 (solidworks-physical-test-review.md)

**审计编号：** `AUDIT-PREFLIGHT-SW-PHYSICAL-20261111`  
**审计目的：** 严格核查 CAD 实机测试环境、COM 通信、模型真实性、文档守恒及是否存在污染用户日常工程文件的风险。

---

## 一、实机环境与进程核查

1. **运行版本确认：**
   - 宿主机实际运行 SolidWorks 版本：`SolidWorks 2026 SP4.1`
   - COM 内部版本修订号（RevisionNumber）：`34.4.1`
   - 进程绑定真实 PID：`34420`
   - 执行脚本路径：`<WORKSPACE_ROOT>\vendor\solidworks-automation-skill\scripts\sw_compat.py`
2. **COM 连接方式确认：**
   - 方式：通过 `win32com.client.Dispatch("SldWorks.Application")` 获取实时运行的 SolidWorks 顶层对象；
   - 调度机制：严格绑定在专用 STA 线程队列（`DesktopPinnedStaWorker`），未发生 `0x8001010E` 跨线程 RPC 异常；
   - 判定：**真实 COM 进程连接 (非 Mock，非静态模拟)**。

---

## 二、测试沙箱与独立文档隔离核查

1. **文档路径隔离：**
   - 所有的零件（`part_a.sldprt`, `part_b.sldprt`）、装配体（`assembly_test.sldasm`）和工程图（`drawing_test.slddrw`）均生成并保存在 Windows 本地隔离临时沙箱：
     `<USER_HOME>\AppData\Local\Temp\dsh_cad_closure_1794364549\`
   - 未在用户工作目录或桌面生成任何未经授权的 CAD 文件。
2. **用户工作文档绝对保护：**
   - 测试前检查用户已有活动文档列表；
   - 测试过程中仅对属于测试会话的临时文档进行打开、编辑、保存与关闭；
   - 绝对禁止并**未调用**任何全局全关闭命令（如 `CloseAllDocuments`）；
   - **未发生任何修改、覆盖或关闭用户文件的行为**。

---

## 三、CAD 建模真实性与物理体积核查

根据原始测试日志 `<WORKSPACE_ROOT>\temp_evidence_v030_compat\D-Real-CAD-Regression\comprehensive_cad_closure.json` 与 `.log`：

1. **凸台拉伸实测体积：**
   - 操作：新建零件，绘制 50mm x 50mm 矩形草图，拉伸 20mm；
   - 理论体积：`50 * 50 * 20 = 50,000.0000 mm³`；
   - SolidWorks COM 实测返回体积：`50000.0 mm³`；
   - 误差：`0.0000%`。
2. **盲切切除自愈实测体积：**
   - 操作：在顶面绘制半径 10mm（直径 20mm）圆，盲切深度 10mm；
   - 切除理论体积：`π * 10² * 10 = 3141.59265 mm³`；
   - 理论剩余体积：`50000 - 3141.59265 = 46858.4073 mm³`；
   - SolidWorks COM 实测返回体积：`46858.407346 mm³`；
   - 误差：`0.0000%`。
3. **质量属性双路径交叉验证：**
   - 路径 A (现代高精度)：`CreateMassProperty` 对象获取；
   - 路径 B (经典回退数组)：`GetMassProperties2` 数组获取；
   - 交叉比对结果：两者数据自洽一致。
4. **特征树与视图投影：**
   - 特征树遍历：22 个特征节点健康无报黄报红；
   - 工程图：成功从测试零件生成前视投影视图（`工程图视图1`），保存并二次重开无损。

---

## 四、四维文档守恒原始证据核查

在 `comprehensive_cad_closure.json` 中记录的文档守恒原始数据：
- `user_initial_doc_count`: `0`
- `user_initial_docs`: `[]`
- `test_session_created_docs`: `["零件2", "零件3", "装配体1", "工程图1 - 图纸1"]`
- `user_final_doc_count`: `0`
- `user_final_docs`: `[]`
- `test_final_doc_count`: `0`
- `user_documents_conserved`: `true`
- `test_documents_purged`: `true`

核查结论：测试前活动文档为 0，测试结束后测试临时文档被 100% 销毁关闭，用户文档数守恒为 0，无任何孤儿文档残留。

---

## 五、实机 vs 模拟严格分级确认

依照任务书最高准则，严谨区分实机测试与模拟验证：
- **SolidWorks 2026 SP4.1**：**`PHYSICAL_VERIFIED (实机验证)`** —— 真实 COM 调用、真实几何计算、体积误差 0.0000%。
- **SolidWorks 2020–2025**：**`INTERFACE_MOCK_VERIFIED (接口模拟验证)`** —— 由于宿主机当前仅安装 2026 SP4.1，旧版本（2020-2025）是在 Python 中通过模拟不同年份 DISPID/参数契约验证降级逻辑，并未在旧版真实实机上执行物理建模。

综合核查判定：**PASS (实机数据绝对真实，且分级口径严密准确)**。
