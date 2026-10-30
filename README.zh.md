# dsh-solidworks

把本机 SolidWorks 桌面接入 DeepSeek Harness（DSH）的插件：66 个 CAD 工具（零件/装配/工程图/DFM/FEA），
默认**只读**，写操作与保存/导出分别需要更高的策略档位和一次性用户授权。

- 插件包：`dsh-solidworks`（AGPL-3.0-only）
- 内嵌执行端：`solidworks-automation-skill` 的 Python MCP 服务器（MIT，见 `vendor/` 与 `NOTICE`）
- 运行形态：DSH 宿主内的 cordis 插件 → 以子进程（stdio）启动 Python MCP 服务器 → COM 驱动本机 SolidWorks

```
DSH 模型 → 工具调用 → lib/index.js（策略/审计） → lib/mcp.js（JSON-RPC over stdio）
        → python server.py（vendor/，MIT） → pywin32/COM → SolidWorks.exe
```

---

## 1. 前置条件

| 项 | 要求 | 检查方式 |
| --- | --- | --- |
| 操作系统 | Windows 10/11 x64 | `dsh-solidworks doctor` |
| SolidWorks | 桌面版 2023–2026，已激活且至少启动过一次（COM 注册） | `doctor` 读 `HKLM\SOFTWARE\SolidWorks` |
| Python | 3.10+ x64，且 `import mcp` 成功（服务器自身要求 `mcp>=1.27,<2`、`pydantic>=2`、`jsonschema>=4.20,<5`；Windows 上还要 `pywin32>=305`、`comtypes>=1.2`；DFM/DXF/FEA 族另需 `ezdxf`、`numpy`、`Pillow`、`lxml`、`openpyxl`、`python-docx`、`python-pptx`、`XlsxWriter`） | `doctor` 逐候选执行 `import mcp` |
| Node | 22.12+（DSH 自带） | `doctor` |
| DSH | 桌面版（插件市场 / 桌面 profile） | — |

> 系统里常见 `C:\Users\<你>\AppData\Local\Microsoft\WindowsApps\python.exe` 是应用商店占位符，能"找到"但
> `import mcp` 必然失败。插件不会把它当成功，会在 `doctor` 里明确报 `PYTHON_INVALID` / `PYTHON_NOT_FOUND`
> 并列出试过的每个候选。装 Python 时把 `python.exe` 的绝对路径填进配置项 `pythonPath` 最稳。

## 2. 安装

**方式 A：DSH 插件市场（推荐给普通用户）**
在 DSH 桌面版打开市场，搜索 `dsh-solidworks`，安装后重启/刷新。市场只分发已收录（curated）插件，
安装期 `postinstall` 脚本被禁用——本包不需要任何安装脚本，全部依赖探测都在首次加载时进行。

**方式 B：本地包装（内测/离线）**
```powershell
dsh plugin --profile web add "D:\path\dsh-solidworks-0.1.0.tgz"
```
注意：`desktop` profile 由桌面端独占，命令行 `dsh plugin --profile desktop add` 会报错，桌面用户请用方式 A 或 GUI。

**方式 C：开发态挂载**
把本目录加进某个 profile 的 `cordis.patch.yml` 的 `insert`（本仓库自带 `cordis.patch.yml` 可直接 `insert`），
配置 `name: dsh-solidworks`。这种方式下 DSH 会以源码目录加载，改动后重启 DSH 生效。

## 3. 首次自检（不会修改任何 CAD 文件）

```powershell
# 1) 环境诊断：解释器 / 服务器脚本 / SolidWorks 是否安装 / 策略档位
node bin\dsh-solidworks.js doctor --json --python "C:\Python313\python.exe"

# 2) 连接与工具清单：启动服务器、握手、列出工具，并显示当前策略下"发布/扣留"了哪些
node bin\dsh-solidworks.js list-tools --mode read-only

# 3) 只读冒烟：调用 solidworks_health_check（读 SolidWorks 状态，不建不存不改）
node bin\dsh-solidworks.js selftest

# 4) 手工调任意工具，策略判定与宿主内完全一致（参数放文件里，PowerShell 会把内联 JSON 弄坏）
node bin\dsh-solidworks.js call solidworks_health_check --arg-file .\args.json --mode read-only
node bin\dsh-solidworks.js call solidworks_save_document --arg-file .\save.json --mode read-only
#   -> {"status":"refused","code":"POLICY_MODE","risk":"high",...}
```

四步都通过才说明"能连上、策略生效"。`doctor` 的 `ready: true` 只代表前置条件齐备，不代表 66 个工具都验证过（见第 7 节）。

## 4. 会话内自检与使用

在 DSH 里先问：

1. `solidworks_status` —— 解释器、服务器脚本、策略档位、最近一次启动错误、子进程 stderr 尾部。任何 CAD 工具失败时先调它。
2. `solidworks_connect` —— 连上正在运行的 SolidWorks（会新建/复用会话，不改文档）。
3. 只读例子：`solidworks_mass_properties`、`solidworks_bounding_box`、`solidworks_list_edges`。
4. 建模例子（需 `mode: standard`）：`solidworks_sketch_and_extrude` → `solidworks_fillet` → `solidworks_mass_properties` 复核。
5. 保存/导出（需 `mode: full` 或 `allow` 放行 + 一次性确认）：
   ```
   solidworks_confirm { tool: "solidworks_save_document", args: { path: "C:\\work\\part.sldprt" }, reason: "用户同意保存" }
   solidworks_save_document { path: "C:\\work\\part.sldprt" }   # 参数必须逐字一致
   ```

## 5. 配置项

在 `cordis.patch.yml` 的 `config:` 下（或市场插件的设置面板）配置：

| 键 | 默认 | 作用 |
| --- | --- | --- |
| `mode` | `read-only` | `read-only` 只发布只读工具；`standard` 再加建/改文档；`full` 全开（高风险仍需确认） |
| `allow` | `[]` | 逐工具放行，**优先于** `mode`（也会绕过下面的 `allowedRoots` 检查，慎用） |
| `deny` | `[]` | 逐工具禁用，**优先于** `allow` 和 `mode` |
| `allowedRoots` | `[]` | 写操作路径白名单；空则用当前 DSH 会话工作目录 |
| `grantTtlMs` | `300000` | `solidworks_confirm` 授权有效期（单次使用，用完即失效） |
| `toolTimeoutMs` | `300000` | 单次 CAD 调用超时（重建/求解慢，故 5 分钟） |
| `startTimeoutMs` | `60000` | 启动服务器 + `tools/list` 超时 |
| `auditLog` | `null` | 审计日志路径（JSONL）；**只记工具名/风险/参数摘要/耗时/会话 ID，不记参数原值** |
| `pythonPath` | `null` | 指定解释器绝对路径（跳过自动探测） |
| `serverScript` | `null` | 覆盖服务器脚本路径（默认用 `vendor/` 内副本） |
| `serverCwd` | `null` | 覆盖服务器工作目录 |
| `toolPrefix` | `""` | 工具名前缀，避免与其他插件撞名 |

`mode` 与风险等级的对应（`lib/policy.js` 的 `RISK_TABLE`，逐工具显式登记）：

- **read**（16 个）：`health_check`、`mass_properties`、`bounding_box`、`list_edges`、`interference_check`、`inspect_*`、`review_*`、`*_preflight`、`design_spec_validate`、`cadstudio_read_artifact` 等。
- **write**（26 个）：建模、装配、配置、尺寸、外观、`open/new_document`、`generate_drawing`、`design_spec_build` 等。
- **high**（24 个）：`save/export/close/pack_and_go/recover`、`cadstudio_run_fea*`、`cadstudio_write_open_format`、OCP loft/surface 等。

## 6. 安全边界（重要，请读完）

**已实现并有单元测试：**

- 默认只读；未登记的工具按名字推断后**从宽不成立**——名字含 `save/export/close/delete/...` 归 high，含 `add/create/set/...` 归 write，其余才是 read（`classify()`），因此新增工具不会自动变成"只读"。
- 高风险调用必须先用 `solidworks_confirm` 提交**逐字相同的参数**换取一次性授权：授权按 `(工具名, 规范化参数)` 绑定、5 分钟过期、用后即焚；参数差一个字符就必须重新授权。
- `deny` > `allow` > `mode`；`deny` 另有一层 `ctx.tools.guard()` 兜底，即使工具被别处注册也会被拒。
- 写操作路径限制在 `allowedRoots`（默认会话工作目录）内，越界返回 `PATH_OUTSIDE_ALLOWED_ROOTS`；只读工具不做路径拦截。
- 审计日志只写工具名、风险、参数**摘要**（sha256 前 16 位）、耗时、会话 ID、目标文件名，不写完整参数，不写 token。

**边界与已知取舍：**

- `allow` 里的工具会跳过 `allowedRoots` 检查（明确放行即视为用户已授权任意路径）。
- 只读工具理论上也能通过 `open_document` 打开文件——插件不阻止，但也不会自动保存；不改文档即无副作用。
- 插件不做文件系统沙箱：CAD 写盘由 SolidWorks 进程执行，最终仍受 DSH 自身的沙箱/审批策略约束（本插件不绕过它）。
- 取消/超时后**副作用未知**：返回 `sideEffects: "unknown"`，要求先检查文档再重试，而不是假装回滚。
- 没有自动备份/回滚：保存前的备份责任在用户/上层流程（这是相对 `dsh-solidworks` 旧实现的明确功能缺口）。

## 7. 验证状态（诚实声明）

| 能力 | 状态 |
| --- | --- |
| 策略/授权/路径/审计单元测试 | **已通过**（11 项，`node tests/policy.test.js`） |
| MCP 客户端（握手/列举/调用/超时/取消/关闭） | **已通过**（8 项，`node tests/mcp.test.js`，用 stub 服务器） |
| FastMCP `params` 参数外壳的解包/回填 | **已通过**（16 项，`node tests/schema.test.js`） |
| 发布包自洽（清单/工具表/许可证/文件白名单） | **已通过**（11 项，`node tests/package.test.js`） |
| 宿主形态端到端（真服务器 + stub 服务器，24 项） | **已通过**（`node tests/host.test.js`） |
| 服务器启动即崩溃时不拖垮宿主 | **已通过**（9 项，`node tests/crash.test.js`） |
| 内嵌服务器在真实 Python 上的 `tools/list` | **已通过**（66 个工具，见 `docs/verification.md`） |
| 在真实 DSH 宿主里加载、连上内嵌服务器并执行只读调用 | **已通过**（隔离 `DSH_HOME` + `swweb` profile，见 E6/E7） |
| 卸载后目录消失、不留 python 子进程 | **已通过**（E10/E11） |
| 真实 SolidWorks 上的建模/装配/工程图/DFM/FEA | **未验证**（需装 SolidWorks 的机器，属待批准动作） |
| 保存/导出/关闭、包与工程图导出 | **未验证** |
| 换版本升级与回滚 | **未验证**（同版本重装已通过） |
| 市场端到端安装（发布后） | **未验证** |

## 8. 排错

| 症状 / 代码 | 含义与处理 |
| --- | --- |
| `PYTHON_NOT_FOUND` | 没找到能 `import mcp` 的解释器。装 `mcp`/`httpx`/`pydantic`，或设 `pythonPath`。`doctor` 会列出每个候选的失败原因。 |
| `PYTHON_INVALID` | 配置的 `pythonPath` 探测失败（常见：指向应用商店占位符、32 位 Python、缺 `mcp`）。 |
| `SERVER_SCRIPT_MISSING` | `vendor/` 内服务器缺失（安装包不完整）。重装，或把 `serverScript` 指到 `solidworks-automation-skill\mcp-server\server.py`。 |
| `SPAWN_FAILED` / `SERVER_EXITED` | 子进程起不来/退出。`solidworks_status` 的 `connection.stderr` 有 Python traceback 尾部。 |
| `POLICY_MODE` | 当前档位不允许该风险等级。改 `mode` 或 `allow`。 |
| `CONFIRMATION_REQUIRED` | 高风险工具没确认，或确认的参数与本次调用不一致/已过期。重新 `solidworks_confirm`。 |
| `PATH_OUTSIDE_ALLOWED_ROOTS` | 写操作目标不在允许目录。改 `allowedRoots` 或把文件放进会话目录。 |
| `TIMEOUT` | 超过 `toolTimeoutMs`。SolidWorks 可能在后台仍在运算——先查文档状态再重试。 |
| 工具不在列表里 | 被 `mode`/`deny` 扣留。`list-tools --mode <档位>` 可看扣留清单与原因。 |
| 宿主启动失败，报 `4 required plugins did not activate` / `152 plugins failed to import` | 该 profile 的 `@deepseek-ai/*` bundle 被 `dsh plugin add/remove` 按 `dependencies` 重算时剪掉了（2026-10-30 实测复现；与插件本身无关）。恢复：桌面端在插件管理器里修复/重装该 profile 的依赖，或新建一个 profile 再装插件（新建 profile 的 bundle 由宿主联网拉取，离线环境下会失败）。本插件在服务器起不来时**不会**让宿主失败（`apply()` 吞掉启动异常，只发布 2 个 meta 工具并报 `environment.state: failed`）。 |
| `dsh plugin --profile X add` 后 profile 里出现乱码 `file:D:/Agent宸ヤ綔鍖?/...` | 安装包路径含中文时 DSH 记录的 spec 会乱码。把 tgz 放到纯 ASCII 路径重装；市场按 npm 包名安装不受影响。 |
| `select a profile only once` | 正确语法是 `dsh --profile <name> web --port N`（profile 在子命令前），不是 `dsh web --profile <name>`。 |
| 在受限沙箱里跑测试全部 `EPERM` | `tests/host.test.js`、`tests/mcp.test.js`、`tests/crash.test.js` 要 spawn 子进程（管道 stdio），必须在普通终端或 danger-full-access 下跑。 |

## 9. 升级 / 停用 / 卸载

- **升级**：市场内升级，或换 tgz 重装；配置项在 profile 的 `cordis.patch.yml` 中保留。
- **停用**：把 `insert` 项加 `disabled: true`，或市场里禁用；不会动 SolidWorks 与已有文档。
- **卸载**：市场卸载 / `dsh plugin --profile web remove dsh-solidworks`；可选删除 `auditLog` 文件。卸载不影响任何 `.sldprt/.sldasm/.slddrw`，宿主退出时会一并关闭 Python 子进程（已实测无残留）。profile 的 `cordis.patch.yml` 里残留的 `- id: dsh-solidworks` 配置项不会报错，也可以一起删掉。
- **回滚**：保留上一版 tgz 即可回退；插件自身不写注册表、不装服务、不改 SolidWorks 设置。

## 10. 许可证与来源

- 本插件：**AGPL-3.0-only**（`LICENSE`）。
- `vendor/solidworks-automation-skill/`：MIT（`vendor/solidworks-automation-skill/LICENSE`），来源与改动见 `PROVENANCE.md`、`NOTICE`。
- 本插件**不包含** `dsh-solidworks`（AGPL）的任何源代码：策略、授权、MCP 客户端、入口均为本包独立实现；两仓库的关系与不合并理由见产品化方案文档。
- 分发时须同时保留 `LICENSE`、`NOTICE`、`vendor/**/LICENSE`。