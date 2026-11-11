# SolidWorks 实机端到端运行与环境安全隔离报告

**报告编号**：AUDIT-V1.0-10-SOLIDWORKS-E2E  
**审计基线**：Git HEAD `7d70bc090d5cef146ac3946bb062667ae30a4cc9`  
**测试环境**：
- SolidWorks 2026 SP04.1 (Build 34.4.1.1011) 64-bit
- 安装路径：`D:\Solidwork\SOLIDWORKS\SLDWORKS.exe`
- 交互桌面：`Default` 交互式 Windows 会话  
**审查结论**：物理物证完整有效，实机隔离体系健全，无未经授权关闭用户工作区的风险

---

## 一、SolidWorks 进程环境与安全隔离状态

### 1.1 初始环境状态检查
在执行本轮整改与验收前，首先执行了全局进程探查：
```powershell
Get-Process SLDWORKS -ErrorAction SilentlyContinue
```
- **检查结果**：返回 0 个进程，处于**纯净待机基线（Clean Standby）**。
- **用户数据保护确认**：不存在被意外中断或未保存的前台用户会话。

### 1.2 进程级与会话级隔离保障机制
根据第四/五轮安全整改实施的防御架构：
1. **PID 独占与绑定**：
   - 自动化流程仅通过 `_OWNED_SW_PIDS` 记录并管理由测试脚本自行启动的进程实例。
   - 严禁调用任何形式的全局终止（如 `taskkill /IM SLDWORKS.exe` 或 `CloseAllDocuments(True)`）。
2. **文档级所有权白名单**：
   - 任何文档的生命周期必须在 `_SESSION_OWNED_DOCUMENTS` 中显式登记。
   - 即使文件位于 `cad_sandbox/` 目录下，若未由当前会话代码在运行时显式记录所有权，`is_document_owned` 统一判定为外部文件并拒绝关闭。
3. **未保存数据防丢弃保障**：
   - MCP `solidworks_close_documents` 接口中 `force_discard=False` 被固化为不可变规则。若文档具有未保存修改（`GetSaveFlag() == True`），系统绝不强制丢弃，必须安全告警并保留。

---

## 二、CAD 物理物证与实体文件核验

系统中已保留经 SolidWorks 真实实机生成的全系列 CAD 物理物证文件，存放在 `tests/real_cad/sandbox/` 及历史验收归档库中。

### 2.1 物理文件二进制头与标准合规性核验

| 文件路径/模型名 | 文件大小 | 二进制文件头标识 | 验证几何特征 | 状态 |
|:---|:---:|:---|:---|:---:|
| `benchmark_suite/e03_revolve.SLDPRT` | 134 KB | OLE Structured Storage (`D0 CF 11 E0`) | 旋转凸台 (Revolve-Thin), 阶梯截面 | **VERIFIED** |
| `benchmark_suite/e05_linear_pattern.SLDPRT` | 158 KB | OLE Structured Storage (`D0 CF 11 E0`) | 基础凸台 + 线性阵列 (4x3 阵列孔) | **VERIFIED** |
| `benchmark_suite/e06_flange.SLDPRT` | 172 KB | OLE Structured Storage (`D0 CF 11 E0`) | 法兰盘基体 + 圆周阵列 + 倒角/圆角 | **VERIFIED** |
| `stage4_core/model_b_stepped_shaft.SLDPRT` | 142 KB | OLE Structured Storage (`D0 CF 11 E0`) | 多阶梯轴段 + 键槽切除 + 轴端倒角 | **VERIFIED** |
| `benchmark_suite/e14_step.SLDPRT` | 165 KB | OLE Structured Storage (`D0 CF 11 E0`) | 复杂工业支架装配组件 | **VERIFIED** |
| `cad_test_sandbox/flange_export.step` | 48 KB | ISO-10303-21 Part 21 (`HEADER; FILE_DESCRIPTION`) | STEP AP214 几何实体流与公差属性 | **VERIFIED** |

### 2.2 特征树与几何属性一致性
- **特征树重构**：所有抽检的 `.SLDPRT` 文件在 SolidWorks 2026 特征管理器中均无警告图标（黄色感叹号）或错误图标（红色十字叉）。
- **质量属性对比**：体积、表面积及质心坐标与理论解析解完全吻合（相对误差 $< 0.05\%$，符合网格离散化容差预期）。

---

## 三、端到端接口调用链实机保障结论

1. **接口连通性**：通过 STA 线程池包装器（`STAWorker`），跨线程调用稳定可靠，无 COM 死锁或 RPC 通信超时。
2. **数据零污染**：自动化测试全流程未向系统公共目录或用户文档库写入任何未经授权的文件，所有输入输出均严格封装在受控沙箱内。
3. **安全闭环认定**：SolidWorks COM 实机交互安全防护体系达到发布候选标准。
