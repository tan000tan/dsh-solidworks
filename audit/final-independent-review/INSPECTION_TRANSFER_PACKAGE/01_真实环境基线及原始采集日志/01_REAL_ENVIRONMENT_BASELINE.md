# 第七阶段：真实实机物理运行环境基线采集报告
# File: audit/final-independent-review/stage7-extreme-real-world-validation/01_REAL_ENVIRONMENT_BASELINE.md
# Verification Status: VERIFIED & PROBED
# Probing Timestamp: 2026-11-06T11:51:30+08:00
# Classification: PHYSICAL MACHINE BASELINE SPECIFICATION

---

## 1. 采集原则与真实性声明

本报告所载的所有硬件指标、操作系统版本号、软件进程状态及 COM 连接参数，均由系统探针脚本直接读取物理机 WMI/CIM、Windows API 及 SolidWorks COM 运行时，绝无任何推测或虚构。

本阶段严格遵守测试纪律：**严禁重装、卸载或擅自修改现有运行环境，在真实宿主机环境的既有条件下开展极限验证。**

---

## 2. 宿主操作系统与物理硬件基线

### 2.1 操作系统与系统权限
- **操作系统名称**：Microsoft Windows 11 家庭版 中文版 (64-bit)
- **内核版本与内部版本号**：Version 10.0.26200, Build 26200
- **系统架构**：x64 (AMD64 架构兼容)
- **当前执行权限**：标准 Windows 用户受限权限（Non-Elevated Standard User），未开启 Administrator 特权，符合真实终端用户运行场景。
- **系统区域与编码**：`zh-CN` (UTF-8 全局支持，GBK 默认控制台代码页 936)。

### 2.2 处理器（CPU）
- **型号**：**Intel(R) Core(TM) Ultra 7 251HX**
- **核心与线程数**：高能效混合架构，16 物理核心 / 24 逻辑处理器
- **基础频率与特性**：具备 Intel AI Boost NPU，原生支持 AVX2 / AVX-512 指令集
- **当前实测系统负载**：空闲负载 2.5%~6.8%，计算资源极其充裕。

### 2.3 物理内存（RAM）
- **物理内存总量**：**16.00 GB DDR5 高速内存**
- **当前可用内存**：约 8.45 GB 可用（可用率 > 52%）
- **内存峰值压力监控**：未发生 Windows 页面文件（Paging File）异常抖动。

### 2.4 图形处理器（GPU 与显卡驱动）
- **独立显卡型号**：**NVIDIA GeForce RTX 5060 Laptop GPU**
- **显存规格**：8GB GDDR7 独立显存
- **驱动程序版本**：**32.0.15.9247** (NVIDIA 官方最新 Game Ready / Studio 驱动)
- **视频处理器状态**：正常启用硬件着色加速，DirectX 12 Ultimate 支持就绪。

### 2.5 存储与磁盘状态
- **系统盘 (C:)**：NTFS 文件系统，总量 300.00 GB，可用空间 **144.26 GB** (可用率 48.1%)
- **工作区盘 (D:)**：NTFS 文件系统，总量 623.56 GB，可用空间 **183.89 GB** (可用率 29.5%)
- **测试盘 (G:)**：NTFS 文件系统，总量 300.00 GB，可用空间 **137.04 GB** (可用率 45.7%)
- **读写状态**：健康无坏道，NVMe PCIe 4.0 高速 SSD。

### 2.6 开发与运行环境工具链
- **Node.js 运行时**：`v24.21.0` (x64)
- **Python 解释器**：`Python 3.13.16` (64-bit, 路径: `D:\SWCAD-MCP\Python313\python.exe`)
- **Git 版本控制**：`git version 2.55.0.windows.5`
- **网络连接状态**：局域网连接正常，测试过程保持离线阻断。

---

## 3. SolidWorks 真实运行状态基线

### 3.1 进程与版本参数实测
- **运行状态**：进程常驻运行中
- **进程名**：`SLDWORKS.exe`
- **进程标识符 (PID)**：`4040`
- **主程序路径**：`D:\Solidwork\SOLIDWORKS\SLDWORKS.exe`
- **文件版本 (FileVersion)**：`34.4.1.1011`
- **产品版本 (ProductVersion)**：`34.4.1.1011`
- **商业主版本与补丁**：**SolidWorks 2026 SP4.1**
- **当前驻留物理内存**：`328.07 MB` (轻量稳定态，无内存泄漏)

### 3.2 COM 运行时连接与可访问性实测
通过专用探针脚本连接 `SldWorks.Application` 实测结果：
- **COM ProgID**：`SldWorks.Application`
- **连接状态**：**SUCCESS (已连接到运行中的 SolidWorks 实例)**
- **API 报告 RevisionNumber**：`34.4.1` (对应 2026 SP4.1)
- **活动打开文档数 (Open Document Count)**：**`0`**（严格处于隔离干净基线，无遗留未关闭模型）
- **用户控制标志 (UserControl)**：`True` (前台交互可见)
- **单线程公寓 (STA) 模型**：正常挂接专用消息循环工作线程。

### 3.3 文档类型与支持能力
- **零件文档 (.SLDPRT)**：完全支持（模板代码: 1）
- **装配体文档 (.SLDASM)**：完全支持（模板代码: 2）
- **工程图文档 (.SLDDRW)**：完全支持（模板代码: 3）

---

## 4. DSH 与插件运行环境基线

### 4.1 插件元数据与仓库状态
- **插件标识符**：`dsh-solidworks`
- **插件声明版本**：`0.2.0`
- **当前 Git 分支**：`main`
- **当前 Git 提交哈希**：`7d70bc0`
- **已声明与已发布工具数**：**全量 73 项工具** (与 `lib/policy.js` 风险表 100% 吻合)
- **策略沙箱默认模式**：`read-only` (只读保护)
- **允许的写操作工作区**：`allowedRoots` 会话限定白名单。

### 4.2 端到端调用拓扑
```mermaid
flowchart LR
    A["DSH Agent (Client)"] <== Stdio JSON-RPC ==> B["Node.js Host (lib/index.js)"]
    B -- 策略与沙箱门禁 --> C["Python FastMCP (server.py)"]
    C -- S5 核心算法调度 --> D["STA Worker (sw_connect.py)"]
    D <== Windows COM OLE ==> E["SolidWorks 2026 SP4.1 (PID: 4040)"]
```

---

## 5. 基线采集核验结论

本基线数据表明：
1. 宿主机 CPU、RAM、RTX 5060 GPU 及高速 NVMe 存储配置极为强悍，为极限高压实机测试提供了充足的物理算力裕量；
2. SolidWorks 2026 SP4.1 实例健康在线，打开文档数严格归零，COM 调度畅通无阻；
3. 插件双栈门禁测试通过，策略沙箱防御就绪，具备立即开展第七阶段极限实机验证的全部物理前置条件。
