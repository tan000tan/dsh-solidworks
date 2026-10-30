# 验证记录（verification.md）

本文件记录 `dsh-solidworks` 在真实环境里**实际跑过**的东西，以及**没有跑过**的东西。
只有本文件列出的证据才算"已验证"；源码里有函数、README 里有描述，都不算。

- 验证日期：2026-10-29（Asia/Shanghai）；2026-10-30 全量复核（见 E17）；2026-10-30 打包完整性补测（见 E18）
- 验证机器：Windows 11（`Windows-11-10.0.26200-SP0`）、x64
- Node：v24.21.0 ｜ Python：`D:\SWCAD-MCP\Python313\python.exe` 3.13.16（`mcp` 1.30.0）
- SolidWorks：2026，注册表 `HKLM\SOFTWARE\SolidWorks` 存在，`solidworks_health_check`
  报告 `solidworks_detected: true`、`missing_com_dependencies: []`

## 1. 结论摘要

| 结论 | 状态 |
| --- | --- |
| 插件能被 DSH 宿主加载并注册工具 | **已证实**（E6） |
| 只读档位下发布 16 个工具、扣留 50 个 | **已证实**（E5：风险表；E7：注册数 18 = 2 meta + 16） |
| 内嵌 Python MCP 服务器能在本机启动并列出 66 个工具 | **已证实**（E4：`tools/list` = 66，协议 2025-06-18） |
| 真实只读调用（`health_check`）可用 | **已证实**（E7：`status: ok`） |
| FastMCP 的 `params` 参数外壳被正确解包/回填 | **已证实**（E12；否则所有带参工具在真实宿主里都会返回 `{}`） |
| CLI `call` 与宿主内执行走同一套策略判定 | **已证实**（E13：只读档位下写工具被拒、只读工具放行） |
| 路径门禁（`allowedRoots`）与写操作确认在宿主内生效 | **已证实**（E14：stub 服务器场景） |
| Python 缺失/是应用商店占位符时给出可操作的失败信息 | **已证实**（E8） |
| 服务器启动即崩溃时不拖垮宿主（`apply()` 不抛错、meta 工具仍可用、状态可诊断） | **已证实**（E15，`tests/crash.test.js`；进程内验证，不是整机宿主现场） |
| 写工具、保存、导出、装配、工程图、DFM/FEA 的实际效果 | **未验证**（第 4 节；本轮刻意不执行写操作） |
| 桌面 profile / 插件市场安装路径 | **未验证**（只在隔离 `DSH_HOME` 的 `swweb` profile 里装过 tarball） |
| 卸载（`dsh plugin remove`） | **已证实**（E10） |
| 从 ASCII 路径干净安装到全新 DSH_HOME | **已证实**（E16，安装与 spec 记录；该 profile 的首次启动受离线环境影响，未验证） |
| 发布包自洽（清单/许可证/工具表/文件白名单互相对得上） | **已证实**（E18，`tests/package.test.js` 11 项） |
| 子进程回收（宿主退出后不留 python） | **已证实**（E11） |
| 升级（同版本重装 / 换版本） | **部分证实**：同版本重装、`file:` 源重装均通过；**换版本升级未验证** |

## 2. 单元测试

| 套件 | 命令 | 结果 |
| --- | --- | --- |
| 策略（风险分级、模式、授权、路径门禁、审计脱敏） | `node tests/policy.test.js` | **11 passed / 0 failed** |
| MCP 客户端（握手、列工具、超时、取消、错误映射、stub 服务器） | `node tests/mcp.test.js` | **8 passed / 0 failed** |
| 参数外壳（`params` 解包/回填、schema 提升） | `node tests/schema.test.js` | **16 passed / 0 failed** |
| 宿主形态端到端（load entry → `apply(ctx)` → 真服务器 + stub 服务器） | `node tests/host.test.js --python "D:\SWCAD-MCP\Python313\python.exe"` | **24 passed / 0 failed** |
| 崩溃隔离（服务器启动即退出） | `node tests/crash.test.js "D:\SWCAD-MCP\Python313\python.exe"` | **9 passed / 0 failed** |
| 打包完整性（清单与工具表一致、许可证随包、无缓存垃圾、文档不泄露本机路径） | `node tests/package.test.js` | **11 passed / 0 failed** |

`tests/host.test.js` 是"能不能真的用"的核心证据：它用一个记录 `register()` 的假 `ctx` 调用插件的
`apply()`，连真实的内嵌服务器，断言：注册 18 个工具（2 meta + 16 只读）、`solidworks_status` 报
`connection.running: true` / `tools: 66`、真实 `solidworks_health_check` 返回 JSON、只读档位下
`solidworks_save_document` **不**在注册表里、`ctx.tools.guard()` 已安装；再用 `tests/stub-server.py`
断言 `params` 外壳被提升、参数回填成 `{"params": {...}}`、扁平工具不被包裹、`allowedRoots` 之外的
写目标在**到达服务器之前**就被拒、根目录内的写目标仍要求确认。

> 注：`tests/host.test.js` 与 `tests/mcp.test.js` 会 `spawn` 子进程；在 DSH 的 workspace-write
> 沙箱下 piped spawn 会被拒（`EPERM`），必须在 danger-full-access 或普通终端里跑。

## 3. 真实环境证据

| # | 项目 | 命令 / 动作 | 观察结果 |
| --- | --- | --- | --- |
| E1 | 解释器探测 | `node bin/dsh-solidworks.js doctor --json --python "D:\SWCAD-MCP\Python313\python.exe"` | `ready: true`，python 3.13.16，`solidworks.version: "2026"` |
| E2 | 自动探测（无 `--python`） | `node bin/dsh-solidworks.js doctor --json` | `python.state: error`，逐条列出 `py -3: spawn py ENOENT`、`python (PATH): not a real interpreter (Windows Store alias stub?)`、`python3 (PATH): 同上`，并给出 `nextSteps` |
| E3 | 服务器脚本导入链 | `node bin/dsh-solidworks.js list-tools --mode read-only` | 首次失败：`ModuleNotFoundError: No module named 'apps'`（`artifact_access.py` → `apps.desktop.cad_workbench.artifact_ledger`）。把 `apps/desktop/cad_workbench/` 与 `subskills/` 一起内嵌后通过 |
| E4 | `tools/list` | 同上 | 66 个工具，协议版本 `2025-06-18`，服务器 `solidworks_mcp 1.30.0` |
| E5 | 风险分级与厂商清单一致 | `node tests/probe-server.mjs`（连真服务器，比对 66 条风险表） | 无 drift（drift 时以退出码 3 失败） |
| E6 | 宿主内加载 | 隔离 `DSH_HOME` → `dsh plugin --profile swweb add dsh-solidworks-0.1.0.tgz` → `dsh --profile swweb web --port 50997 --no-open` | 启动无 "did not activate" 告警；`Win32_Process` 里出现父进程为 DSH 宿主、命令行指向**安装后** `...\node_modules\dsh-solidworks\vendor\solidworks-automation-skill\mcp-server\server.py` 的 python 子进程 |
| E7 | 只读真实调用 | `tests/host.test.js` 内调用 `solidworks_health_check` | 返回 `{status:"ok", checks:{python 3.13.16, missing_com_dependencies:[], solidworks_detected:true, server_path: ...\vendor\...}}` |
| E8 | 失败可操作性 | 见 E2 | 错误信息包含每个候选与原因，用户可直接照 `nextSteps` 修 |
| E9 | 打包 | `npm.cmd pack` | `dsh-solidworks-0.1.0.tgz`：202 files（压缩 623,330 B / 解包约 2.2 MB）。压缩体积与 sha256 每次重新打包都会变，以 `.tgz` 实测为准 |
| E10 | 卸载 | `dsh plugin --profile swweb remove dsh-solidworks` → 再次启动宿主 | 安装目录消失；宿主正常启动、stderr 无报错；`Win32_Process` 中不再出现指向 `vendor\...\server.py` 的 python 子进程。profile 里残留的 `- id: dsh-solidworks` 覆盖项**不报错**，只是不再生效 |
| E11 | 进程回收 | 结束宿主进程后检查 `python.exe` | 无残留的 vendored 服务器进程（插件 teardown 关闭子进程） |
| E12 | 参数外壳 | `tests/host.test.js`（stub 服务器）+ `tests/schema.test.js` | 服务器返回 `inputSchema: {properties:{params:{...}}, required:["params"]}` 时，宿主侧注册的是**解包后**的 schema；调用时参数再包回 `{"params": {...}}`；扁平工具原样透传 |
| E13 | CLI 门禁 | `node bin/dsh-solidworks.js call solidworks_inspect_native_geometry --arg-file a.json --mode read-only --python ...` | 只读档位下返回 `{"status":"refused","code":"POLICY_MODE","mode":"read-only","risk":"write"}`；同一命令换只读工具正常返回服务器 JSON |
| E14 | 宿主内门禁 | `tests/host.test.js` 的 `stub_export` 段 | `output_path` 在 `allowedRoots` 外 → `PATH_OUTSIDE_ALLOWED_ROOTS`，无 `stub_export` 调用到达服务器；根目录内 → `CONFIRMATION_REQUIRED` |
| E15 | 崩溃隔离 | `node tests/crash.test.js "D:\SWCAD-MCP\Python313\python.exe"`（服务器脚本第一行就 `SystemExit(3)`） | `apply()` 未抛错；只发布 2 个 meta 工具；`solidworks_status` 报 `environment.state: failed` / `connection.running: false` 并带可读原因；输出里无凭据字段 |

| E16 | 全新 DSH_HOME 的干净安装 | ASCII 路径的 tgz → `DSH_HOME=<空目录> dsh plugin --profile swclean add …tgz` | 退出码 0；当时版本的 247 个文件落到 `profiles\swclean\node_modules\dsh-solidworks`（现已清掉 46 个 `.pyc`，见 E18）；`package.json` 记录的 spec 为 `file:C:/Users/…/swpkg/dsh-solidworks-0.1.0.tgz`（**干净 ASCII**，验证了"中文路径导致乱码"的成因）；`dsh.profile.bundles = ["@deepseek-ai/dsh-base","dsh-solidworks"]`。该全新 profile 的**首次启动**在本机未成功：`@deepseek-ai/dsh-base` 不在该 profile 里，插件管理器尝试联网安装，离线环境下 pnpm 挂起无输出——属测试环境限制，不作为插件缺陷 |

| E17 | 2026-10-30 全量复核 | 五个套件 + `probe-server.mjs` + `bin` 冒烟（`version` / `doctor` / `list-tools` / `call`） | 11+8+16+24+9 = **68 项全过**；真服务器 66 工具、只读档位 16 发布 / 50 扣留、风险表 66 条无 drift；`solidworks_health_check` 163 ms 返回 `status: ok`、`missing_com_dependencies: []`、`solidworks_detected: true`、`motion_type_library_ready: true`；`npm pack` 产出的 35 个代码/配置文件与工作树 SHA-256 **全部一致** |

| E18 | 打包完整性（新增套件） | `node tests/package.test.js`（纯文件检查：不 spawn、不连 CAD、不需要 Python） | **11 passed / 0 failed**。断言：`package.json` 的 `dsh.bundle.patch`/`main`/`bin` 都指向真实文件且无 install 脚本；`files` 白名单覆盖全部运行时目录；`cordis.patch.yml` 的 config 键全部存在于 `DEFAULTS` 且默认 `mode: read-only`；`dsh-plugin.json` 的 68 条工具表 = 2 meta + `RISK_TABLE` 66 条（16 read / 26 write / 24 high）且无重复；清单里的图标、`docs/locale/*.json` 存在且非占位；`LICENSE` 是 AGPL-3.0 全文、`NOTICE` 与 `vendor/LICENSE` 标明 MIT 上游与固定提交；README 不含构建机路径。**顺带查出真实缺陷**：上一版 tgz 混进了 6 个 `__pycache__` / 46 个 `.pyc`（在本机跑服务器时生成在 vendor 里的字节码），使包从 202 文件涨到 247、体积从 0.61 MiB 涨到 1.02 MiB；已删除、写入 `.gitignore`，并加了"不得携带缓存或嵌套仓库"的断言 |

E17 的环境复现说明（**不是**新的插件缺陷）：在隔离 `DSH_HOME` 里用 `--from-default-profile web` 新建
`swclean` profile → `dsh plugin add D:\dsh-sw-test\plugin.tgz`（纯 ASCII 路径）**成功**（`file:D:/dsh-sw-test/plugin.tgz`，
`bundles` 追加 `dsh-solidworks`），`--dump-config` 也能看到正确的 `- id: dsh-solidworks` 覆盖；
但该 profile **首次启动**仍失败（`4 required plugins did not activate` / `@deepseek-ai/* failed to import`，
`.plugin-manager/logs/operation-*/pnpm.log` 为 0 字节）——与本机"受限网络下拉不到 `@deepseek-ai/*` bundle"
一致，属测试环境限制。桌面端用户从应用内安装不存在这一步。

E6 的关键点：python 子进程的路径是**安装副本里的 vendor**，不是源码目录、也不是开发机上原有的
`D:\SWCAD-MCP\solidworks-cad`。这排除了"宿主其实复用了旧 MCP 配置"的可能。

E12 是产品级 bug 修复的证据：FastMCP 把每个工具的参数包在 `params` 里，若不处理，模型按解包后的
schema 传参、服务器按 `params` 解析，结果所有带参工具都会"成功返回空结果"。`lib/schema.js` 负责
两个方向的转换，`bin/` 的 `call` 与宿主内 executor 共用同一实现。

## 4. 明确未验证（不要当成可用）

1. **任何真实写操作**：`mode: standard` 下的草图/拉伸/圆角/阵列/旋转、装配插入与配合、保存、导出
   （STEP/STL/DXF/PDF）、删除、Pack&Go、关闭文档——一次都没有在真实 SolidWorks 里执行。
   风险评估基于源码与工具描述。
2. **`mode: full` + 真实高风险工具**：确认闭环在宿主内用 stub 验证过（E14），但没对真实
   `solidworks_save_document` / `solidworks_export_active` 跑过"拒绝 → 确认 → 放行 → 落盘"。
3. **装配体与工程图**：`solidworks_generate_drawing` / `inspect_drawing` 只验证了"可被列出、
   只读类可调用"，没有生成过真实图纸。
4. **DFM / FEA / OCP 后端**：`cadstudio_*` 系列只在 `tools/list` 与风险分级层面验证；`cadstudio_fea_run`
   等需要 CalculiX/Elmer 的场景未运行。
5. **桌面 profile 与插件市场**：本轮安装在隔离 `DSH_HOME` 的 `swweb` profile；`desktop` profile 由
   桌面端独占（CLI 会报错），市场收录流程（`awesome-dsh-plugin` PR）未走。
6. **换版本升级 / 回滚**：同版本重装与 `file:` 重装都通过，但没有"0.1.0 → 0.2.0 升级 + 回退"的证据。
7. **兼容矩阵**：只在 SolidWorks 2026 / Python 3.13 / Node 24 / x64 上验证；2023–2025、arm64、
   Python 3.10–3.12 未验证（上游 `capabilities.yaml` 声明 2024/2026）。
8. **并发、超时、取消、断连**：客户端层有实现与单元测试（cancel/timeout），真实宿主内未压测。
9. **审计日志**：写盘路径与脱敏有单元测试，未在真实写操作后核对日志内容。

### 已知问题（不是"未验证"，是确认存在的缺陷或坑）

- **中文路径的 `file:` 安装会写坏 spec**：用 `dsh plugin --profile X add D:\...\中文目录\pkg.tgz`
  安装后，profile 的 `package.json` 里记录的 `file:` 说明符是乱码（`file:D:/Agent宸ヤ綔鍖?/...`）。
  本次安装仍然成功，但后续 `add`/`remove` 可能解析失败。**临时规避**：把 tarball 放到纯 ASCII 路径
  再装，或从插件市场按 npm 包名安装（正规用户路径不受影响）。
- **全新 `DSH_HOME` 的首次启动需要能访问 npm registry**：`dsh plugin add` 只安装插件本身，
  profile 声明的 `@deepseek-ai/dsh-base` 等 bundle 由插件管理器在首次启动时联网拉取。离线/受限
  网络下这一步会**静默挂起**（`plugin-manager/logs/operation-*/pnpm.log` 为 0 字节）。正常用户从
  桌面端安装不存在这个问题；只有手工造隔离 `DSH_HOME` 时会遇到。
- **`dsh plugin add` 会裁剪 profile 依赖**：在测试 profile 里跑 `add`/`remove` 之后，profile 原本的
  `@deepseek-ai/dsh-base`、`dsh-market` 等依赖被移除，宿主随即因缺少 bundle 无法启动
  （`preset ... did not activate`）。所以**不要拿正在用的 profile 做安装实验**，用独立 `DSH_HOME`。
- **DSH 命令语法**：`dsh --profile <name> web --port N`（profile 在子命令**前**）；
  `dsh web --profile <name>` 会报 `select a profile only once`。另外 `dsh`/`npm` 的 `.ps1` 包装在
  受限执行策略下会被拒，用 `dsh.cmd` / `npm.cmd`。

## 5. 复现步骤

```powershell
# 1) 静态与单元测试（普通终端，不要用受限沙箱）
cd <插件目录>
node tests/policy.test.js
node tests/mcp.test.js
node tests/schema.test.js
node tests/host.test.js --python "C:\Path\To\python.exe"
node tests/crash.test.js "C:\Path\To\python.exe"

# 2) 环境自检（不改任何 CAD 文件）
node bin\dsh-solidworks.js doctor --json --python "C:\Path\To\python.exe"
node bin\dsh-solidworks.js list-tools --mode read-only
node bin\dsh-solidworks.js selftest --python "C:\Path\To\python.exe"

# 3) 手工调一个工具（参数走文件，避免 PowerShell 引号损坏 JSON）
node bin\dsh-solidworks.js call solidworks_health_check --arg-file .\args.json --mode read-only --python "C:\Path\To\python.exe"

# 4) 隔离 DSH_HOME 里验证"能装、能加载"
$env:DSH_HOME = "C:\temp\dsh-sw-test"
dsh plugin --profile swweb add .\dsh-solidworks-0.1.0.tgz
dsh --profile swweb web --port 50997 --no-open
# 另开一个终端，确认宿主的 python 子进程指向安装副本里的 vendor：
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Select-Object ProcessId,ParentProcessId,CommandLine
```

第 4 步如果 python 子进程没出现，先看 `solidworks_status` 或 `doctor` 的输出——插件在启动失败时
**不会**让宿主崩溃，只会把原因写进 `solidworks_status.environment`。