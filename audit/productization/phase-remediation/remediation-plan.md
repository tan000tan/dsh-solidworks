# 修复清单与整改执行方案 (remediation-plan.md)

**任务基准：** `tan000tan/dsh-solidworks` v0.3.0  
**目标：** 实现普通用户零配置运行、严格运行时环境隔离、高危操作防自授权闭环、71 个 CAD 工具全量覆盖与严密暴力测试。

---

## 一、具体代码文件修复计划

### 1. `lib/discover.js` (解决 BUG-002: 杜绝宿主 Python 污染，实现隔离自举)
- **根本原因：** `tryAutoBootstrap` 在 candidate 缺少依赖时直接在该 candidate 内部执行 `pip install`，若 candidate 为全局 Python 或 DSH Runtime Python，将造成外部全局环境污染。
- **整改方案：**
  1. 新增 `ensureIsolatedVenv(seedPython, pluginRoot)` 函数：
     - 若候选种子 Python 缺少 `mcp` 或 `pywin32`，**绝对不在其全局环境中执行 pip install**；
     - 自动且静默地在 `pluginRoot` 下创建插件专属虚拟环境：`[seedPython, '-m', 'venv', path.join(pluginRoot, '.venv')]`；
     - 在新建的隔离 `.venv` 内部，通过 `[venvPython, '-m', 'pip', 'install', 'mcp>=1.0.0', 'pywin32>=306']` 受控安装依赖；
     - 自动执行 `pywin32_postinstall.py -install`（使用用户态模式）；
  2. 探测优先级调整：
     - 优先级 1：插件内部已就绪的专属虚拟环境 `.venv`；
     - 优先级 2：插件内置 portable `.runtime`；
     - 优先级 3：利用 DSH 桌面端自带的 Python (`dsh-primary-runtime`) 作为种子自动派生插件 `.venv`；
     - 优先级 4：利用系统 Python (`py -3`, `python`) 作为种子自动派生插件 `.venv`；
  3. 彻底杜绝全局环境污染，宿主 Python 仅作为 `venv` 的派生种子，自身保持 100% 纯净。

### 2. `lib/policy.js` 与 `lib/index.js` (解决 BUG-001: 堵塞高危操作 AI 自授权漏洞)
- **根本原因：** `solidworks_confirm` 接收参数后直接无条件调用 `policy.grant()`，任何 AI 模型可单方面通过调用该工具为自己签发高危通行证。
- **整改方案：**
  1. 引入**审批来源可信验证机制 (Trusted Approval Context)**：
     - `solidworks_confirm` 增加 `userConfirmed: true` 的强校验，或者由宿主交互环境传入经过签名的人类交互确认 token (`humanApprovalToken` / `confirmedByHuman: true`)；
     - 当处于严格审批模式（`strict` 或默认 `balanced`）时，若无人类显式确认标记，`solidworks_confirm` 将拒绝签发 grant，并返回 `HUMAN_INTERACTION_REQUIRED`，提示宿主界面弹出用户物理确认对话框；
  2. 增加防重放与参数绑定加固：
     - 单次 Grant 严格一次性消费；
     - 会话级 Grant 绑定严格的 TTL（默认 5 分钟），超时立即销毁；
     - 参数哈希（digest）采用严格规范化排序，杜绝参数篡改绕过。

### 3. `scripts/setup.js` (加固安装部署引导器)
- 配合 `lib/discover.js` 的隔离自举逻辑，确保离线与在线安装流程均遵循“专属 `.venv` 隔离原则”；
- 增加非交互式静默自愈能力。

### 4. `dist/` 归档目录规范复原 (解决 BUG-006)
- 从项目根目录中安全将 `dsh-solidworks-0.1.0.tgz` 与 `dsh-solidworks-0.2.0.tgz` 复制至新建的 `dist/` 目录中，并在 `dist/README.md` 中记录清晰的历史归档说明与 SHA-256。

---

## 二、71 个 CAD 工具全量覆盖与追踪矩阵规划 (解决 BUG-004)

在 `audit/productization/phase-remediation/traceability-matrix.md` 中建立全量 71 项 CAD 工具清单：
- 分类：零件建模 (22)、特征编辑 (15)、草图与尺寸 (12)、装配与配合 (10)、工程图与视图 (6)、质量与测量 (6)；
- 逐一明确：工具名、入参、出参、风险等级、降级路由与验证方式。

---

## 三、测试与验证方案

1. **单元测试与架构规范：**
   - 运行 `node tests/package.test.js`；
   - 验证 `lib/discover.js` 在全局 Python 存在时的隔离自举行为（检查系统 Python 是否未被修改，插件专属 `.venv` 是否建立）。
2. **安全对抗测试：**
   - 运行针对 AI 自授权、路径遍历、TTL 过期的暴力对抗测试；
3. **CAD 实机全链路测试：**
   - 运行真实 SolidWorks 2026 物理闭环测试，确保体积误差 0.0000% 保持成立；
4. **系统健康自检：**
   - 运行 `node scripts/doctor.js`，确保 12 维检查全部 PASS。
