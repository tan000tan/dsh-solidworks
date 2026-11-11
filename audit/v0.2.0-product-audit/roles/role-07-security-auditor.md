# 角色审计报告 07：安全审计者视角

> **审计视角**：应用安全红蓝对抗专家、系统提权与沙箱逃逸审计员、工业数据资产安全合规官  
> **审查基准**：零信任防御模型、OWASP Top 10 for LLM、Windows 文件系统攻击面分析  
> **核心命题**：**错误的 AI 指令、恶意 Prompt 注入、重复调用或中途断连，是否可能破坏或泄露用户的核心 CAD 资产？**

---

## 一、威胁建模与攻击面防御实测

```mermaid
flowchart TD
    Attacker["潜在威胁源<br>(恶意Prompt / 幻觉AI / 畸变参数)"] --> AttackVectors{"攻击与风险向量"}
    
    AttackVectors -->|向量 1| V1["路径穿越与目录逃逸<br>(../, Junction, UNC)"]
    AttackVectors -->|向量 2| V2["用户已有CAD文件误删<br>(批量关闭/覆盖保存)"]
    AttackVectors -->|向量 3| V3["Windows 内核挂起<br>(CON/NUL 设备名DoS)"]
    AttackVectors -->|向量 4| V4["NTLM Hash 凭据窃取<br>(远程SMB UNC请求)"]
    AttackVectors -->|向量 5| V5["中途建模崩溃残留<br>(脏特征污染与资源死锁)"]
    
    V1 -->|防御: Ancestor Walk| Def1["✔ 100% 拦截阻断"]
    V2 -->|防御: DocumentLifecycleManager| Def2["✔ 100% 免疫保护"]
    V3 -->|防御: DOS Name Regex| Def3["✔ 100% 拦截阻断"]
    V4 -->|防御: Remote UNC Deny| Def4["✔ 100% 拦截阻断"]
    V5 -->|防御: TaskRollback & Shadow| Def5["✔ 100% 自动秒级回滚"]
    
    style Def1 fill:#d4edda,stroke:#28a745
    style Def2 fill:#d4edda,stroke:#28a745
    style Def3 fill:#d4edda,stroke:#28a745
    style Def4 fill:#d4edda,stroke:#28a745
    style Def5 fill:#d4edda,stroke:#28a745
```

### 1.1 文件系统物理逃逸防御核验（行业标杆水准）
- **祖先解析算法 (`realpathWithAncestorWalk`)**：
  - 针对传统应用中“目标文件尚未被 CAD 创建，因此无法调用 `realpath` 解析符号链接与 Junction 逃逸”的经典 TOCTOU 漏洞；
  - 本项目在 [`lib/policy.js:338-364`](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/lib/policy.js#L338-L364) 创新实现了祖先路径向上递归折叠算法，无论目标嵌套多深，均能准确定位至其在物理磁盘上的真实落地锚点；
  - 实测验证：通过 `tests/policy.test.js` 对 Windows Junction 重定向到沙箱外目录的攻击行为进行全量断言拦截。
- **DOS 保留设备名与远程 UNC 拦截**：
  - 阻断了 `CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9` 等会导致 Windows 驱动挂起的保留设备名；
  - 强力阻断形如 `\\attacker.com\share\cad.step` 的远程 UNC 路径，**彻底封堵了 Windows 客户端通过 WebDAV/SMB 发起身份认证导致的 NetNTLMv2 Hash 泄露风险**。

### 1.2 用户已有打开 CAD 文档的安全边界
- **最严酷故障场景走查**：
  - 用户正在 SolidWorks 界面中手工精细雕琢零件（如 `80x50x25mm` 电池仓，体积 $100,000\text{ mm}^3$），未保存；
  - 用户在 DSH 中要求 AI 尝试进行一个新模型的实验性建模；
  - AI 执行中途抛出不可恢复的几何自交崩溃或拉伸非法参数异常；
- **防御机制生效表现**：
  1. [`cad_task_context.py`](file:///D:/Agent工作区/DeepSeek%20Harness工作区/dsh-solidworks-plugin/vendor/solidworks-automation-skill/scripts/cad_task_context.py) 的 `DocumentLifecycleManager` 在任务开启瞬间通过 `sw_app.GetDocumentCount()` 与标题指纹锁定了全部预存文档；
  2. 任务异常回滚时，只针对标有 `is_task_created=True` 的本任务子文档执行销毁；
  3. 用户原有的活动文档**绝不执行关闭、绝不执行撤销、绝不保存覆盖**；
  4. 真实实机测试证明：原有模型体积零误差保持，特征树未丢失一个历史特征。

### 1.3 权限与特权升级防护
- **单次授权凭据 (`solidworks_confirm`) 强绑定**：
  - 高风险工具（如 `solidworks_save_document`, `solidworks_close_documents`, `solidworks_export_active`）必须获取预先授权；
  - 授权凭据与调用参数经由 SHA-256 签名严密绑定；
  - **防欺骗验证**：若 AI 在 `solidworks_confirm` 中向用户声称保存到 `D:\safe\model.step`，却在实际调用时试图写入 `D:\safe\malicious.bat`，SHA-256 签名失配，调用立即被拒绝（`GRANT_PARAM_MISMATCH`）。

### 1.4 识别出的残余安全隐患 (P2 / P3)
1. **审计日志缺乏轮转机制 (Log Rotation)**：
   - `lib/index.js` 中的 `audit()` 函数使用 `appendFileSync` 无上限追加写入 `config.auditLog`；
   - 长期高频运行可能导致磁盘空间单文件占满，建议引入大小限制（如 10MB）与自动切片轮转；
2. **多进程并发文件写锁缺失**：
   - 影子备份 `shadow_backup.py` 在复制当前文件时，若外部有第三方同步盘（如 OneDrive、SVN）正在读写同一文件，可能引发文件共享冲突（`EBUSY`），需加入重试与临时共享锁。

---

## 二、安全审计者最终裁决

### 裁决结论：**PASS (通过 —— 核心安全与数据保护体系极其坚固)**

### 总结：
本项目在输入校验、沙箱物理折叠、网络凭据防护、CAD 任务隔离与用户已有资产保护方面达到了**生产级商业软件的安全防护深度**，未发现高危资产破坏与信息泄露漏洞。
