# STAGE 04 源代码架构与系统安全深度审计报告
# AUDIT_ARCHITECTURE_AND_SECURITY.md

**审计项目：** `dsh-solidworks` DSH 插件  
**审计阶段：** STAGE 04 — CAD 核心建模能力 (架构与安全审计)  
**审计团队：** 第三方独立技术审计组  
**审计重点：** 模块边界、STA Worker 线程模型、COM 交互稳定性、零信任网关 (Policy Gateway)、高风险授权防重放  
**状态：** **AUDITED & SECURE (架构分层清晰，零信任防线坚固，发现 2 项潜在边界风险已建档)**

---

## 一、系统架构分层与模块边界审计

系统整体采用 **“Node.js 宿主插件网关 (Policy Gateway) + FastMCP 进程间 JSON-RPC + 专属 STA Worker 线程 + SolidWorks COM 引擎”** 的四层物理架构：

```
+-------------------------------------------------------------+
|                      DSH (DeepSeek Harness) 宿主             |
+-------------------------------------------------------------+
                              | (JSON-RPC stdio)
+-------------------------------------------------------------+
| Layer 1: Node.js 插件层 (lib/index.js, lib/policy.js)         |
|  - 73 项 MCP 工具 Schema 注册与入参白名单校验               |
|  - 零信任 Policy Gateway (路径沙箱限制 + One-Shot Grant)    |
+-------------------------------------------------------------+
                              | (Spawn stdio)
+-------------------------------------------------------------+
| Layer 2: FastMCP Python 服务端 (server.py)                  |
|  - 工具分发、参数反序列化、业务错误封装                     |
+-------------------------------------------------------------+
                              | (Thread-safe Queue)
+-------------------------------------------------------------+
| Layer 3: STA Worker 线程调度器 (sw_connect.py)               |
|  - Windows 单线程单元 (STA) 循环消息调度                    |
|  - 异常捕获、任务超时控制、状态机状态转移 (cad_task_context) |
+-------------------------------------------------------------+
                              | (COM Late Binding)
+-------------------------------------------------------------+
| Layer 4: SolidWorks 2024 桌面 CAD 宿主 (SLDWORKS.exe)       |
|  - 几何建模、草图求解、三维特征生成、几何度量               |
+-------------------------------------------------------------+
```

### 1.1 模块边界与隔离性审查
- **职责清晰度**：Node.js 层专注于权限拦截与宿主生命周期，Python FastMCP 专注于领域业务转换，STA Worker 专注于 COM 单线程死锁防护，职责切分清晰。
- **是否存在绕过网关的直连路径**：经静态代码审查，外部 DSH Agent 只能通过 `lib/index.js` 暴露的 MCP 管道进行调用，所有工具调用在进入底层 Python 之前均强制通过 `evaluate(tool, args, context)`，不存在未受保护的旁路接口。
- **循环依赖与错误吞噬**：
  - 核心 Python 脚本未发现跨模块循环引用；
  - 在 `sw_connect.py` 的 `worker.execute()` 中，子线程产生的异常会通过 `raise val` 在主线程精准重新抛出，杜绝了底层 COM 错误被静默吞噬为假成功。

---

## 二、SolidWorks 官方 API 契约与使用审计

### 2.1 API 存在性与参数顺序核验
- **凸台拉伸 (`extrude_boss`)**：
  - 调用 `FeatureManager.FeatureExtrusion3`；
  - 校验参数表：Sd (True), Flip (False), Dir, T1 (Blind=0), T2 (0), D1 (米制深度)；
  - 核查结论：参数顺序与 SolidWorks 2024 API SDK 严格一致，单位已由 `mm()` 转换为米制。
- **切除拉伸 (`extrude_cut`)**：
  - 调用 `FeatureManager.FeatureCut4`；
  - 校验参数表：Sd (True), Flip, Dir, EndCondition (0=Blind, 1=ThroughAll), D1 (米制深度)；
  - 核查结论：参数匹配正确。在实体表面操作时 `direction=False` 深入内部，在基准面上操作时 `direction=True`，行为符合几何物理规律。
- **旋转凸台 (`revolve_boss`)**：
  - 调用 `FeatureManager.FeatureRevolve2`；
  - 关键约束：必须预先选择旋转轴线，代码中通过 `sk_mgr.CreateCenterLine` 创建中心线并由 `_capture_sketch_ref` 传递，避免了空轴崩溃。

### 2.2 COM 线程与封送（Marshaling）安全
- SolidWorks COM 为传统 STA 架构，不能在多线程并发直接读写其属性。
- 架构审查确认：全套代码彻底摒弃了主线程直接访问 COM 对象，所有新建、编辑、测量、保存和关闭均委托给专属 STA Worker 线程串行执行，杜绝了 `RPC_E_SERVERCALL_REJECTED` (0x80010105) 跨线程死锁。

---

## 三、零信任安全架构与攻击面防御审计

### 3.1 路径穿越与沙箱边界防御 (Path Traversal Protection)
- **审查逻辑**：`lib/policy.js` 中的 `canonicalPath` 与 `evaluate` 函数；
- **物理拦截实测**：
  - 注入 `../../Windows/System32/payload.SLDPRT`：通过 `ancestor walk` 解析物理路径后，被判定超出 `allowedRoots`，精准拦截并抛出 `PATH_OUTSIDE_ALLOWED_ROOTS`；
  - 注入 Windows Junction 符号链接：系统解析真实物理 `realpath`，指向沙箱外的 Junction 链接被无条件阻断（测试用例 `Windows Junction pointing outside allowedRoots is blocked by physical realpath` PASS）。

### 3.2 用户资产只读白名单保护 (Protected File Immutability)
- **保护范围**：`tests/real_cad/fixtures/` 及配置文件声明的只读模型资产（如 `垫圈.SLDPRT`）；
- **拦截实测**：对受保护白名单文件的任何修改或写入请求，Policy Gateway 直接返回 `PROTECTED_FILE_REFUSED`，未向底层发送写指令，防止用户生产零件被破坏。

### 3.3 高风险写操作单次绑定授权 (One-Shot Grant Architecture)
- **授权模型**：
  1. Agent 请求调用 `solidworks_save_document`；
  2. 网关计算 `sha256(tool + JSON.stringify(args))` 生成 Digest，拦截并返回 `CONFIRMATION_REQUIRED`；
  3. DSH 桌面宿主介入审核后，通过特权工具 `solidworks_confirm` 签发绑定该 Digest 的 Grant；
  4. Agent 携带完全相同参数再次调用时，网关核销 Grant 并允许执行；
- **防重放与防篡改审计**：
  - Grant 存储于内存闭包，一次性使用即焚（Single-Use）；
  - 若调用时参数发生微小篡改（如路径变化或附加参数），计算所得 Digest 无法匹配 Grant，调用立即被拒；
  - 审计结论：彻底解决了高风险 CAD 文件落盘的权限逃逸隐患。

---

## 四、潜在架构风险与边界缺陷记录 (Defects & Risks)

在对抗式审查中，审计组发现以下两项架构级潜在边界风险：

1. **[DEFECT-ARCH-01 | MEDIUM] STA Worker 队列单点阻塞风险**：
   - 当前 STA Worker 采用全局单例（Singleton）。若某一耗时特长或 SolidWorks 弹窗阻塞了 Worker 线程，后续队列任务将排队超时，缺乏外部看门狗强制唤醒机制（需依赖 DSH 宿主的总体超时切断）。
   - *建议*：在后续阶段引入基于 Win32 API 的弹窗自动监测与看门狗线程。
2. **[DEFECT-ARCH-02 | LOW] 特征树长链回滚依赖未完全拓扑校验**：
   - 当前 `CADTaskRollbackManager` 采用线性逆序栈（LIFO）删除特征。如果用户在中间手动删除了某一特征，或特征树存在复杂的跨草图交叉引用，简单的逆序删除可能因下游父子依赖未断开而导致部分特征删除受阻。
   - *建议*：在第五阶段将回滚动作升级为基于 DAG 拓扑排序的递归安全卸载。

---

## 五、架构与安全审计结论

`dsh-solidworks` 在第四阶段建立的系统架构层次清晰、COM 线程安全防护完备，零信任安全网关与 One-Shot Grant 机制有效防御了路径越界、用户资产破坏及写操作越权。未发现严重安全后门或致命架构崩溃风险，**架构与安全审计判定：PASS（合规准予交付）**。
