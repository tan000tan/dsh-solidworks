# dsh-solidworks 故障排查（v0.3.2）

适用于 Windows 10 / 11 x64 上的插件 0.3.2。每条故障统一按「症状 → 原因 → 检查命令 → 修复 → 仍失败怎么办」组织；所有命令都在仓库根目录的终端里执行。

先说清楚边界：`read-only` 模式下写类与高危工具**不会发布**，这是策略设计而不是故障；`solidworks_confirm` 自确认接口**永远是拒绝**；命令行没有 `approve` / `reject`（已移除）。排障时不要试图绕过这三点。

## 0. 先收集三条信息

```powershell
node bin/dsh-solidworks.js doctor --json
npm run doctor
npm run list-tools
```

- `doctor --json`：只读，输出 `plugin` / `host` / `python` / `server` / `solidworks` / `ready` / `nextSteps`，不写文件。
- `npm run doctor`：跑 12 个维度，写出 `diagnostic-report.json` 与 `diagnostic-report.md`。
- `list-tools`：真正连接一次 MCP 服务，列出服务器工具面以及当前模式下"发布/扣留"的情况。

另外在 DSH 里调用 `solidworks_status`，它会带出 `policy.mode`、`connection.running`、`connection.error` 和 `connection.stderr`（最后 10 行）——MCP 子进程的报错基本都在这里。插件自身的 logger 输出进 DSH 宿主日志；MCP 服务的 stderr 由 `solidworks_status` 带出。

## 1. DSH 里看不到工具

**症状**：插件启用后，DSH 里只有 `solidworks_status`，或一个 `solidworks_*` 都没有；让 AI 建零件时它回答"没有这个工具"。

**原因**：插件没有装进当前 profile 的 `node_modules`，或没有在该 profile 启用；安装/改配置后没有完全重启 DSH；Python 依赖探测失败，插件降级为只发布 `solidworks_status`；或者当前是 `read-only`，写工具本来就不发布。

**检查命令**：

```powershell
node bin/dsh-solidworks.js doctor --json
npm run list-tools
npm run list-tools -- --mode standard
```

**修复**：先在 DSH 插件列表里确认 `dsh-solidworks` 已启用，然后**完全退出** DSH 再启动（刷新页面不算）。`doctor --json` 里 `python` 段是 error 的，按第 2、3 节处理。只是缺建模工具而只读工具都在的，按 USER_GUIDE 第 4 节把 `mode` 改成 `standard` 并重启。

**仍失败怎么办**：带上 `doctor --json` 输出与 `solidworks_status` 返回，用 `Installation problem` 模板提 issue。

## 2. Python 找不到 / 版本不对

**症状**：`doctor` 的 `python.state` 为 `error`；报错含 `未找到包含 'mcp' 与 'pywin32' 核心依赖的可用 Python 环境`，或 `configured pythonPath failed the import check`。

**原因**：机器上没有 Python 3.10+；`python` 命令解析到 Microsoft Store 的 `WindowsApps` 占位程序（不是真解释器，探测会直接标记 `WINDOWS_STORE_ALIAS`）；插件设置里的 `pythonPath` 指错——注意它优先级最高，**一旦设置且导入检查失败会直接返回 `PYTHON_INVALID`，不会回退**到其他候选；或者 DSH 自带 runtime 没找到。

**检查命令**：

```powershell
python --version
where python
py -3 --version
node bin/dsh-solidworks.js doctor --json
```

**修复**：在 DSH 插件设置里把 `pythonPath` 指向真实的 `python.exe`（例如 `C:\Users\<你>\AppData\Local\Programs\Python\Python312\python.exe`）；或用 DSH 自带 runtime `%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe`；也可以直接 `npm run setup` 在仓库里建 `.venv`（探测顺序里 `.venv` 优先于系统 `python`）。`where python` 指向 `...\WindowsApps\python.exe` 时不要用它。

**仍失败怎么办**：用 `node bin/dsh-solidworks.js doctor --python "C:\真实路径\python.exe" --json` 单独验证解释器；也可以在启动 DSH 前设 `DSH_SOLIDWORKS_PYTHON` 环境变量指定解释器。

## 3. `mcp` 或 `pywin32` 缺失

**症状**：报错文案同上（`lib/discover.js:323`）：`未找到包含 'mcp' 与 'pywin32' 核心依赖的可用 Python 环境。已排查候选: ... 加载期默认禁止自动联网安装依赖；请运行 "dsh-solidworks setup" 安装隔离依赖，或在 DSH 插件设置中手动指定 pythonPath`；或直接看到 `ModuleNotFoundError: No module named 'mcp'` / `win32com`。

**原因**：`.venv` 建好了但 pip 没装完（安装中断、镜像失败），或包装到了另一个解释器里。

**检查命令**：

```powershell
.venv\Scripts\python.exe -c "import mcp, pydantic, jsonschema; import win32com.client; print('deps ok')"
npm run setup -- --force
```

**修复**：`npm run setup -- --force` 重装核心依赖；镜像不通就加 `--official`。装完再跑一次 `doctor`，`COM_DEPENDENCIES` 应为 PASS。

**仍失败怎么办**：手动执行 `.venv\Scripts\python.exe -m pip install -r requirements.txt`，把完整报错贴进 issue（`Installation problem` 模板）。

## 4. COM 注册异常

**症状**：`pywintypes.com_error`、`Class not registered`、`CO_E_SERVER_EXEC_FAILURE (0x80080005)`；`win32com.client` 导入失败。

**原因**：pywin32 的 postinstall 没跑过；SolidWorks 从未启动过（COM 注册通常在首次启动时完成）；当前用户权限不足；或者 SolidWorks 安装本身损坏。

**检查命令**：

```powershell
.venv\Scripts\python.exe -c "import win32com.client; print('com ok')"
reg query "HKLM\SOFTWARE\SolidWorks" /s
npm run doctor
```

**修复**：跑 `npm run setup`——它只在 `win32com` 导入失败时才调用 `pywin32_postinstall.py -install -silent`；如果自动调用没成功，用**管理员**终端手动执行 `.venv\Scripts\python.exe .venv\Scripts\pywin32_postinstall.py -install`。然后手动启动 SolidWorks 一次，等它完成初始化再退出。

**仍失败怎么办**：修复安装 SolidWorks，重启机器后再试；`npm run doctor` 的 `COM_DEPENDENCIES` 与 `LIVE_COM_ECHO` 两项结果一并附上。

## 5. `npm run setup` 依赖安装失败

**症状**：`[3/6]` 阶段报 `[✖] 依赖安装失败`，退出码 1，并提示"请检查本地网络连接，或尝试手动安装 requirements.txt"。

**原因**：镜像源不可达或被代理拦截；pip 缓存损坏；安装被中断。默认镜像实际是**清华源** `https://pypi.tuna.tsinghua.edu.cn/simple` 并附加官方源 `https://pypi.org/simple` 作为备用；`--aliyun` 用阿里云源；`--official` / `--no-mirror` 不用镜像；`--tsinghua` 走的是默认分支。首选源失败后脚本会自动切官方源重试一次。

**检查命令**：

```powershell
npm run setup -- --official
npm run setup -- --aliyun
```

**修复**：换源重试；离线机器先在能联网的机器上 `pip download -r requirements.txt -d wheels`，拷到本机后 `.venv\Scripts\python.exe -m pip install --no-index --find-links wheels -r requirements.txt`。

**仍失败怎么办**：手动把依赖装进 `.venv` 后再跑 `npm run setup`——依赖已齐时脚本会走幂等检查并跳过下载。

## 6. 网络受限 / 代理

**症状**：pip 超时、SSL 握手失败、连接被重置；但本机 Python 与 SolidWorks 都正常。

**原因**：企业代理/防火墙拦截 PyPI 与镜像；或者指望插件在加载期自动补依赖——加载期默认**禁止**自动联网安装，只有显式设置 `DSH_SOLIDWORKS_AUTO_BOOTSTRAP=1`（或配置 `autoBootstrap`）才会尝试。

**检查命令**：

```powershell
echo $env:HTTPS_PROXY
.venv\Scripts\python.exe -m pip config list
```

**修复**：先在可联网环境完成 `npm run setup`，再把整个 `.venv` 拷到目标机；或在设好 `HTTPS_PROXY` / `HTTP_PROXY` 的终端里执行 `npm run setup -- --official`。不要把"加载期自动联网"当作常规方案。

**仍失败怎么办**：用离线 wheel 安装（见第 5 节），并在 issue 里注明代理环境。

## 7. MCP 服务启动失败 / 超时

**症状**：`solidworks_status` 里 `connection.running` 为 `false`，`connection.error` 含超时；`doctor --json` 的 `server` 段是 error；DSH 日志里没有出现 `tools from server ... published ...` 这行。

**原因**：`startTimeoutMs` 默认 60000 ms，冷启动 + Python 导入较慢时可能不够；`serverScript` 被指到错误路径；`.venv` 里的包损坏。

**检查命令**：

```powershell
npm run list-tools
node bin/dsh-solidworks.js doctor --json
.venv\Scripts\python.exe vendor\solidworks-automation-skill\mcp-server\server.py
```

**修复**：在插件设置里调大 `startTimeoutMs`（允许 1000–300000）；确认 `serverScript` 指向 `vendor\solidworks-automation-skill\mcp-server\server.py`；最后一条命令能直接看到 Python 侧 traceback，按报错修依赖。

**仍失败怎么办**：把 `connection.stderr` 的最后 10 行与手动运行的 traceback 一起提交。

## 8. SolidWorks 无法连接

**症状**：`solidworks_health_check` 失败；`solidworks_connect` 报无法创建实例；出现 `CO_E_SERVER_EXEC_FAILURE (0x80080005)`；教育版授权过期时可能出现 `MK_E_UNAVAILABLE`（历史真实报错，代码里没有硬编码，属运行时 COM 错误）。

**原因**：SolidWorks 没运行，或从未启动过导致 COM 未注册；SolidWorks 里有模态对话框阻塞了 COM 调用；授权过期/未激活；上一次 COM 调用挂起。

**检查命令**：

```powershell
npm run doctor
tasklist | findstr /i sldworks
```

**修复**：手动启动 SolidWorks，关掉所有模态对话框（登录、许可、更新提示），再调用 `solidworks_health_check`；确认授权有效。`read-only` 下不允许 `start_solidworks=True`（会返回 `POLICY_MODE: start_solidworks=True is prohibited`），所以必须人工启动。

**仍失败怎么办**：保存工作后完全退出 SolidWorks 再启动，仍不行就重启机器；带 `doctor` 输出与 SolidWorks 版本，用 `Real SolidWorks validation report` 模板提交。

## 9. `read-only` 下的 "Permission denied" 类拒绝

**症状**：写类工具在工具列表里根本没有；或调用返回 `POLICY_MODE`（"is a write-risk tool and the plugin runs in read-only mode"）；或 `POLICY_MODE: start_solidworks=True is prohibited (read-only mode or DSH_ALLOW_LAUNCH_SW!=1).`；或 `Access denied: ... is outside allowed roots (DSH_ALLOWED_ROOTS)`。

**原因**：这是**预期行为**，不是故障。`read-only` 只发布 READ 级工具；`standard` 排除 HIGH；`full` 才全开。路径类报错来自 `allowedRoots` 白名单（默认只有会话工作目录）。

**检查命令**：

```powershell
npm run list-tools -- --mode read-only
npm run list-tools -- --mode standard
```

**修复**：要建模就改 `mode` 为 `standard` 并重启 DSH；要保存/导出/关闭就改 `full`，并准备好 DSH 宿主的人类审批弹窗；导出路径放进 `allowedRoots`（插件设置）或改用工作目录内的路径。

**仍失败怎么办**：确实只需要放行单个工具时，用 `allow` 白名单显式列出该工具名（谨慎，等于局部降级安全边界）；否则按上面的模式调整。

## 10. 工具调用超时

**症状**：某个工具调用几分钟后失败，提示 timeout；简单工具（如 `solidworks_health_check`）正常。

**原因**：`toolTimeoutMs` 默认 300000 ms（5 分钟），允许范围 1000–600000；重建、导出、批量操作或 FEA 可能更久；也可能是 SolidWorks 弹了对话框在等人。

**检查命令**：

```powershell
node bin/dsh-solidworks.js call solidworks_health_check --json
```

**修复**：在插件设置里调大 `toolTimeoutMs`；把大操作拆成多次小调用；跑之前关掉 SolidWorks 的模态对话框。

**仍失败怎么办**：确认 SolidWorks 界面是否卡住（任务管理器看 CPU）；必要时保存后重启 SolidWorks 再重试，并在 issue 里说明工具名与耗时。

## 11. 安装中断 / 残留

**症状**：`npm run setup` 中途被 Ctrl+C；`.venv` 半成品、依赖报错；DSH profile 里出现重复的插件条目。

**原因**：安装被中断，或重复执行过 setup/upgrade。

**检查命令**：

```powershell
npm run uninstall -- --dry-run
node bin/dsh-solidworks.js doctor --json
```

**修复**：先 `--dry-run` 看清清理范围（`.venv`、`dsh-mcp-config.json`、诊断报告、测试基准件等；`.SLDPRT` / `.SLDASM` / `.SLDDRW` 与 `config-backups\` 会保留），确认后再 `npm run uninstall -- --yes`，然后重新 `npm run setup`。

**仍失败怎么办**：手动删除仓库内的 `.venv` 后重跑 setup；profile 改动前的备份在 `config-backups\`，可据此恢复。仍异常就附 `uninstall --dry-run` 输出提 issue。

## 12. `ok: true` 也可疑：成功不等于正确

工具调用成功只代表调用跑完并返回了载荷，不代表几何正确。v0.3.2 已知两类"可疑成功"：

- **字段为 `null` 但 `ok` 为 true。** `solidworks_list_edges` 在真机上返回 `ok: true`，而 `length`、`mid_point`、`direction` 全是 `null`。把 null 当"没测到"，不要当 0。
- **空输入也能通过。** 对没有任何组件的装配体调用 `solidworks_interference_check` 会报通过，`solidworks_review_active` 也可能给一个模型打出高分，而它并没有真的检查。

结果过于干净时用另一个工具独立复核：改几何后用 `solidworks_mass_properties` 读回，改尺寸后用 `solidworks_inspect_dimension_impact` 读回，或直接对照 SolidWorks 自己的质量属性对话框。逐工具证据（含这两个案例）见 `docs/FEATURE_MATRIX.md` 与 `docs/verification.md`（缺陷 D-05、D-11）。

## 13. 源码依据

- `lib/discover.js:283-287` —— `pythonPath` 优先且失败即 `PYTHON_INVALID`，不回退。
- `lib/discover.js:323` —— Python 依赖缺失的统一报错文案。
- `lib/discover.js:30-38` —— `WindowsApps` 占位解释器识别（`WINDOWS_STORE_ALIAS`）。
- `lib/index.js:49-59` —— `toolTimeoutMs` 300000、`startTimeoutMs` 60000、`pythonPath`。
- `lib/index.js:241-243` —— `solidworks_status` 的 `connection.error` / `connection.stderr`。
- `lib/index.js:493-507` —— 工具按策略过滤注册与 published/withheld 日志。
- `lib/index.js:554-575` —— 无审批通道时 `APPROVAL_CHANNEL_UNAVAILABLE`（失败关闭）。
- `lib/policy.js:321-329`、`430-441` —— 三档模式的发布规则与 `POLICY_MODE` 拒绝文案。
- `scripts/setup.js:308-320` —— 镜像选择：默认清华 + 官方备用，`--aliyun`，`--official`/`--no-mirror`。
- `scripts/setup.js:381-430` —— 仅在 `win32com` 导入失败时执行 `pywin32_postinstall.py -install`。
- `scripts/uninstall.js:24-25` —— `--dry-run` 与 `--yes`。
- `vendor/solidworks-automation-skill/mcp-server/server.py:3976-3977` —— `read-only` 禁止 `start_solidworks=True`。
- `vendor/solidworks-automation-skill/mcp-server/server.py:4653` 等 —— `Access denied: ... outside allowed roots (DSH_ALLOWED_ROOTS)`。
- `vendor/solidworks-automation-skill/mcp-server/server.py:8448` —— 受支持的 MCP 协议版本集合（与 SolidWorks 版本无关）。
- `vendor/solidworks-automation-skill/scripts/sw_session.py:56-71`、`222-227` —— 仅抑制两类非必要弹窗（停调试器、关预发布提示）并读取 CommandInProgress，没有自动点击白名单。