# 安装 dsh-solidworks

这是 [dsh-solidworks](../README.zh.md) 的详细安装说明。简版只有两条命令；本文件说明这两条命令到底对你的机器做了什么、怎么判断是否装好、怎么撤销。

英文版：[INSTALL.md](../INSTALL.md)。

## 安装前检查

| 要求 | 怎么确认 |
| :--- | :--- |
| Windows 10/11，64 位 | `echo %PROCESSOR_ARCHITECTURE%` → `AMD64` 或 `ARM64` |
| SolidWorks 桌面版已安装且有有效许可 | 手动启动 SolidWorks 一次，确认能打开文档 |
| DeepSeek Harness `>=0.1.7-rc.2` | `dsh --version` |
| Node.js `>=22.12` | `node --version` |
| Python 3.10+ 64 位 **或** DSH 自带的 Python 运行时 | `python --version`；如果没有任何输出或弹出应用商店，说明没有可用的 Python，`setup` 仍可改用 DSH 运行时 |
| 能访问网络（供 `pip` 使用） | 仅在 Python 依赖尚未安装时需要 |

- 不需要关任何程序，也不需要移动文件。`setup` 只写插件目录内部和 DSH 桌面 profile 里的一个文件。
- 不需要管理员权限，不需要改 `PATH`，也不需要把 Python 装到系统目录。
- 如果 SolidWorks 正开着且有未保存文档，让它开着即可；安装过程不会碰正在运行的 SolidWorks。

## `npm run setup` 做了什么

`setup` 是一个 Node 脚本（`scripts/setup.js`），分六步执行，每步打印 `[n/6]`：

1. **平台检查**——输出 `process.platform`、系统版本与架构。非 64 位 Windows 只给警告，不强行中断。
2. **探测 Python**——按顺序尝试：已有 `.venv/pyvenv.cfg` 里记录的解释器、DSH 自带的 Python、`--python <路径>`、环境变量 `DSH_SOLIDWORKS_PYTHON`/`PYTHON`/`PYTHON_PATH`、命令 `python`/`python3`/`py`、以及 Windows 常见的 Python 3.13/3.12/3.11/3.10 安装目录。第一个报告 Python ≥3.10 的解释器被采用；全都不满足时退出，并给出下载链接与操作说明。
3. **虚拟环境**——在插件目录内创建 `.venv`。如果无法创建标准虚拟环境，会写一个轻量代理（`.venv/pyvenv.cfg` 加 `python.cmd`、`pip.cmd` 两个包装脚本），指向它探测到的解释器。
4. **Python 依赖**——用 pip 安装 `requirements.txt`（`mcp`、`pydantic`、`pywin32`、`comtypes`、`jsonschema`）。已装好的依赖会被 import 检测出来并跳过。源：默认清华镜像 + `pypi.org` 作为额外索引；`--aliyun` 用阿里云镜像；`--official` 或 `--no-mirror` 完全不用镜像。镜像安装失败时会改用默认源重试。可选依赖（`requirements-optional.txt`）只在加 `--optional` 或 `--full` 时安装。
5. **COM 注册**——在 Windows 上验证 `import win32com.client, pythoncom`；失败则从虚拟环境或解释器目录执行 `pywin32_postinstall.py -install -silent`，然后再验证一次。
6. **注册 DSH**——如果存在 DSH 桌面 profile，往 `<profile>/cordis.patch.yml` 写入 `dsh-solidworks` 条目。写入前先把原文件复制成 `cordis.patch.yml.bak-dshsolidworks-<时间戳>`；如果写入或激活前检查失败，会恢复该备份。写进去的条目使用 `read-only` 模式和 `toolTimeoutMs: 300000`。

`setup` **刻意不**在插件目录里生成 `dsh-mcp-config.json`：那个文件只给第三方 MCP 客户端用，安装期生成它会让工具调用绕过插件的策略层。确实需要时用 `npm run mcp-config -- --write-direct-config` 显式生成。

## 安装

```cmd
cd <插件目录>
npm run setup
npm run doctor
```

`setup` 的参数：

| 参数 | 作用 |
| :--- | :--- |
| `--python <路径>` | 指定解释器，跳过自动探测 |
| `--aliyun` | Python 依赖走阿里云镜像 |
| `--official`、`--no-mirror` | 不使用任何 pip 镜像 |
| `--optional`、`--full` | 同时安装 `requirements-optional.txt`（DXF、Office、图像） |
| `--force` | 依赖已能 import 也强制重装 |
| `--verify` | 安装结束后顺带跑一次 doctor 检查 |

如果你是从 DSH 插件目录安装的插件，包已经在 profile 里、脚本没被执行过——到那个包目录里跑一次 `npm run setup`，然后重启 DSH。

## 判断是否装好

```cmd
npm run doctor
```

报告是 JSON，关键字段：

| 字段 | 正常值 | 含义 |
| :--- | :--- | :--- |
| `ready` | `true` | 插件能启动它的 MCP 服务器 |
| `python.version` | `3.10` 以上 | 实际选中的解释器 |
| `python.comDeps` | `true` | `comtypes` 可 import；`false` 说明只有 `pywin32`，部分 COM 能力会降级 |
| `server.script` | `vendor/` 下真实存在的 `server.py` | 将要启动的 MCP 服务器 |
| `solidworks.installed` | `true` | 本机检测到 SolidWorks |
| `solidworks.version` | 例如 `2026` | 从注册表读到的版本 |
| `nextSteps` | 建议项 | 下一步该做什么 |
| `readyFull` | `true` | 在 `ready` 基础上加上 `python.comDeps`；为 `false` 表示服务器能起但 COM 相关工具可能降级 |

然后启动 DSH、启用插件，先做一次只读操作——例如列出工具或做环境体检。工具只在插件加载后才出现；注册后必须重启 DSH。

想知道 DSH profile 里到底有没有这个插件（bundle 依赖、patch 条目、配置的模式与 `pythonPath`），运行：

```cmd
node bin/dsh-solidworks.js doctor --profile --json
```

`issues` 为空表示 profile 看起来一致。`installedAsBundle: true` 而 `patchEntry: false` 对市场安装是正常的：bundle 自带 patch。

`npm run doctor:cli` 通过插件 CLI 得到同样的检查；`node bin/dsh-solidworks.js list-tools --mode read-only --json` 打印当前模式发布的工具清单。

## 装不上怎么办

| 现象 | 去哪看 |
| :--- | :--- |
| `setup` 说找不到 Python 3.10+ | [docs/TROUBLESHOOTING.zh.md](TROUBLESHOOTING.zh.md) 的 Python 一节 |
| pip 安装失败或超时 | 同一文档的网络与镜像一节 |
| 装完 `comDeps: false` | 同一文档的 pywin32/COM 一节 |
| 插件加载了但没有工具 | 同一文档的 MCP 启动一节 |
| SolidWorks 开着但调用失败 | 同一文档的 SolidWorks 连接一节 |
| 需要指定特定解释器 | [docs/ADVANCED-CONFIG.zh.md](ADVANCED-CONFIG.zh.md) |

## 升级

```cmd
npm run upgrade
```

`upgrade` 会把当前配置快照到 `config-backups/`，校验插件入口完整，然后刷新依赖与 COM 注册。若入口校验或依赖刷新失败，它会把这些快照文件复制回去（单次复制失败会被静默跳过，所以请核对它打印的"已恢复"清单）。最后的 doctor 只是验收提示：**不会**触发回滚，有 WARN 也不会中断脚本——结尾的成功横幅跟的是 doctor 的退出码，而不是"没有告警"，请直接读 doctor 自己打印的结果。你的 CAD 文档不会被触碰。

## 卸载

```cmd
npm run uninstall -- --dry-run
npm run uninstall -- --yes
```

不加 `--yes` 直接运行 `npm run uninstall` 只会打印**将要**删除什么。删除清单是固定白名单，不是对插件目录的递归清扫：

| 会被删除 | 会被保留 |
| :--- | :--- |
| `.venv`（setup 创建的环境） | 你的 CAD 文件（`*.SLDPRT`、`*.SLDASM`、`*.SLDDRW`） |
| `dsh-mcp-config.json`（若存在） | `config-backups/` |
| `diagnostic-report.json` / `.md` | 插件包本身 |
| 本仓库自带测试留下的沙箱残留（`测试代码/sandbox_benchmark/`，若存在） | 其他插件的配置 |
| `cordis.patch.yml` 里的 `dsh-solidworks` 条目（先备份） | 注册表、`PATH` 及其他系统设置 |

如果 profile 条目没能移除，脚本会打印原因——旁边的 `cordis.patch.yml.bak-dshsolidworks-<时间戳>` 可以手工复制回去。

## setup 绝不会做的事

- 除 DSH 桌面 profile 的 `cordis.patch.yml`（先备份）与 pip 自己的缓存外，不会写插件目录以外的项目文件。
- **可能改注册表，但只有一种情况**：如果 `import win32com.client` 失败，setup 会执行 pywin32 自带的 `pywin32_postinstall.py -install -silent`，由它注册 pywin32 的 COM 组件（`HKCU`/`HKLM` 与 `HKEY_CLASSES_ROOT` 下的相关键）。不会碰其它注册表键，也不会改 `PATH`、PowerShell 执行策略或系统环境变量。若导入本来就正常（本机用过 pywin32 的常见情况），不会发生任何注册表写入。
- 不会安装、升级或删除你的系统 Python。
- 不会以管理员权限运行：COM 注册只在你当前账户本来就有写这些键的权限时成功，否则 setup 只报警告，不会提权。
- 不会删除 CAD 文件，也不会对插件目录做递归删除。
- 唯一的联网行为是 pip 下载 `requirements.txt` 里列出的依赖。