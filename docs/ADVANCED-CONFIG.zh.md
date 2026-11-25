# 高级配置

本页说明 `dsh-solidworks` 插件接受的全部配置键、`setup` 背后的解释器与镜像行为，以及不触碰 CAD 文档的自检方式。路径均相对仓库根目录：`lib/index.js:49` 指本包内该文件的第 49 行。

插件 schema 声明了十四个键（`lib/index.js:49-62`）。你写入的值都会经过 `normaliseConfig`（`lib/index.js:105-117`），因此错误的数字和未知的 mode 会退化为默认值，而不是在加载时直接报错。越界数值由 `clampTimeout` 收紧（`lib/index.js:99-103`）。

## 1. 配置从哪里读取

| 层面 | 位置 | 由谁读取 |
| --- | --- | --- |
| 随包默认 patch | `cordis.patch.yml:11-21` | DSH 插入 profile 时使用 |
| Profile patch | `<DSH_HOME>/profiles/desktop/cordis.patch.yml`（`scripts/dsh_adapter.js:29-32`） | DSH 宿主在启动时读取 |
| 插件 schema | `lib/index.js:49-62` | 宿主交出配置后由 `apply()` 处理 |
| 环境变量 | `lib/discover.js:263-276` 与 `lib/discover.js:335` | 解释器与 server 脚本解析 |
| 命令行参数 | `bin/dsh-solidworks.js:42` | 仅一次性诊断 |

随包条目如下（这些值就是默认值，并非唯一合法取值）：

```yaml
- insert:
    - id: dsh-solidworks
      name: dsh-solidworks
      config:
        mode: read-only
        toolTimeoutMs: 300000
        startTimeoutMs: 60000
        grantTtlMs: 300000
        allow: []
        deny: []
        allowedRoots: []
```

## 2. 字段参考

| 字段 | 类型 | 默认值 | 作用 | 什么时候改 | 改了的后果 |
| --- | --- | --- | --- | --- | --- |
| `mode`（`lib/index.js:49`） | `read-only`、`standard` 或 `full` | `read-only`（`lib/index.js:82`） | 策略上限：决定发布哪些 server 工具（`lib/index.js:490-505`），并作为 `DSH_POLICY_MODE` / `DSH_ALLOW_LAUNCH_SW` 传给 Python server（`lib/index.js:401-402`） | 需要建模（`standard`）或保存/导出/关闭（`full`）时 | 无法识别的值会静默回退为 `read-only`（`lib/index.js:111`）；即使在 `full` 下，HIGH 风险工具仍需逐次交互式审批（`lib/policy.js:490-497`） |
| `allow`（`lib/index.js:50`） | 字符串数组；也接受逗号分隔的字符串（`lib/index.js:119-123`） | `[]`（`lib/index.js:83`） | 让风险表未识别的工具被发布（`lib/policy.js:321-323`、`lib/policy.js:354-356`），并绕过模式拒绝（`lib/policy.js:430-436`） | server 暴露了比插件风险表更新的工具 | 被点名的工具会跳过模式上限（含 HIGH 风险工具），必须逐个谨慎填写 |
| `deny`（`lib/index.js:51`） | 字符串数组 | `[]`（`lib/index.js:84`） | 工具永不发布（`lib/policy.js:321-329`）；即使被其他组件注册，宿主侧 guard 也会拒绝（`lib/index.js:836-844`） | 某工具在任何模式下都不允许使用 | 优先级高于 `allow`；拒绝码为 `TOOL_DENIED`（`lib/policy.js:352`） |
| `allowedRoots`（`lib/index.js:52`） | 目录字符串数组 | `[]`（`lib/index.js:85`） | CAD 文件路径沙箱（`lib/policy.js:723-760`）；非空时替换会话工作目录（`lib/index.js:479-482`） | 模型或图纸存放在 DSH 会话目录之外 | 列表之外的路径一律以 `PATH_OUTSIDE_ALLOWED_ROOTS` 拒绝；既无 roots 又无会话 cwd 时所有路径都被拒绝（`lib/policy.js:731-733`） |
| `toolTimeoutMs`（`lib/index.js:53`） | 数字，毫秒 | `300000`（`lib/index.js:88`） | 单次调用的超时（`lib/index.js:794`）以及发布工具定义里的超时（`lib/index.js:501`） | 重建或批量导出超过五分钟 | 被夹在 1000..600000（`lib/index.js:112`）；设得太小会在 server 已开始工作后中断长调用 |
| `startTimeoutMs`（`lib/index.js:54`） | 数字，毫秒 | `60000`（`lib/index.js:89`） | MCP `initialize` 与首次 `listTools`（`lib/index.js:411`、`lib/index.js:487`） | 冷启动 Python 或磁盘较慢导致首次启动慢 | 被夹在 1000..300000（`lib/index.js:113`）；失败后插件继续运行但没有 CAD 工具 |
| `grantTtlMs`（`lib/index.js:55`） | 数字，毫秒 | `300000`（`lib/index.js:86`） | 交互式审批授权的有效期（`lib/policy.js:204`、`lib/policy.js:702`） | 一次审批需要覆盖较长的批处理 | 非有限数、<= 0 或超过 24 小时会在构造 Policy 时抛错（`lib/policy.js:152-159`）；越长意味着一次人工点击授权重复调用的时间窗越宽 |
| `challengeTtlMs`（`lib/index.js:56`） | 数字，毫秒 | `120000`（`lib/index.js:87`） | 待处理审批挑战的有效期（`lib/policy.js:205`、`lib/policy.js:521`） | 人需要超过两分钟才能应答弹窗 | 过期的挑战会以 `CHALLENGE_EXPIRED` 拒绝（`lib/index.js:634-635`） |
| `maxChallenges`（`lib/index.js:57`） | 整数 | `512`（`lib/index.js:91`） | 内存中待处理挑战的上限；超出时淘汰最旧的一条（`lib/policy.js:512-516`） | 大量高危调用并发执行 | 必须是 1..10000 的整数，否则静默重置为 512（`lib/index.js:114-115`） |
| `pythonPath`（`lib/index.js:58`） | 字符串路径 | 未设置 | 显式指定解释器，跳过其他所有候选（`lib/discover.js:283-287`） | `.venv` 损坏且已知可用的解释器存在 | 路径错误会直接以 `PYTHON_INVALID` 失败且不回退（`lib/discover.js:287`） |
| `serverScript`（`lib/index.js:59`） | 字符串路径 | 未设置 | 覆盖随包 `server.py`（`lib/discover.js:334-343`） | 使用打过补丁或分叉的 server | 文件不存在会报 `SERVER_SCRIPT_MISSING`；两个元工具仍会被注册（`lib/index.js:302-347`） |
| `serverCwd`（`lib/index.js:60`） | 字符串路径 | 未设置 | Python 子进程的工作目录；默认取 `mcp-server` 的上级目录（`lib/discover.js:344-347`） | server 需要特定 cwd | 目录不存在会报 `SERVER_CWD_MISSING`（`lib/discover.js:346`） |
| `toolPrefix`（`lib/index.js:61`） | 字符串 | `''`（`lib/index.js:95`） | 给所有发布名称加前缀，包括两个元工具（`lib/index.js:261-262`、`lib/index.js:302-347`） | 同一 profile 里需要共存两个实例 | 继续使用裸名字的提示词、脚本和 `call <tool>` 调用将不再匹配 |
| `auditLog`（`lib/index.js:62`） | 指向 JSONL 文件的字符串路径 | 未设置（`lib/index.js:90`） | 持久化审计轨迹（`lib/policy.js:256-274`） | 需要跨 DSH 重启保留记录 | 不设置则磁盘上不写任何内容；路径不可写时退化为仅内存（见 §11） |

## 3. 模式与风险分级

每个 server 工具都被分级为 READ、WRITE 或 HIGH（`lib/policy.js:21-23`）。显式表里没有的工具按模式匹配，默认归为 HIGH（`lib/policy.js:126-131`），因此新工具在被风险表认识之前都按危险处理。

| 模式 | 发布的工具 | HIGH 风险调用 | 典型用途 |
| --- | --- | --- | --- |
| `read-only` | 仅 READ（`lib/policy.js:321-329`） | 以 `POLICY_MODE` 拒绝 | 检查、测量、复核 |
| `standard` | READ 与 WRITE | 以 `POLICY_MODE` 拒绝 | 建模与改模型但不保存 |
| `full` | 所有分级 | 仅在交互式审批通过后执行（`lib/policy.js:490-497`） | 保存、导出、关闭文档 |

所有模式下都有两条额外规则：`PROTECTED_FILENAMES` 中的文件名不可写入（`lib/policy.js:111-120`、`lib/policy.js:447`）；`solidworks_confirm` 永远返回 `SELF_APPROVAL_PROHIBITED`，因为 AI 自确认已被禁用（`lib/index.js:311-347`）。

## 4. `allow`、`deny` 与 `allowedRoots` 的相互影响

| 情形 | 结果 | 依据 |
| --- | --- | --- |
| 工具在 `deny` 中 | 不发布且被拒绝 | `lib/policy.js:321-329`、`lib/index.js:836-844` |
| 工具在 `allow` 中 | 即使未被风险表识别也会发布 | `lib/policy.js:321-323`、`lib/policy.js:354-356` |
| `allow` 点名了当前模式拒绝的工具 | 调用放行 | `lib/policy.js:430-436` |
| `allowedRoots` 为空 | 只有会话工作目录可写 | `lib/index.js:479-482`、`lib/policy.js:723-760` |
| `allowedRoots` 非空 | 这些目录替换会话目录 | `lib/index.js:479-482` |
| 路径参数是相对路径 | 调用前被改写为绝对路径 | `lib/policy.js:457-460` |

## 5. Python 解释器选择

`discover()` 按固定顺序尝试候选（`lib/discover.js:263-276`）；第一个能导入 `mcp`、`pydantic`、`jsonschema`、`win32com.client` 与 `pythoncom` 的候选胜出。

| 顺序 | 候选 | 依据 |
| --- | --- | --- |
| 1 | `DSH_SOLIDWORKS_PYTHON` 环境变量 | `lib/discover.js:263-276` |
| 2 | 内嵌运行时 `pluginRoot/.runtime/python/python.exe` | `lib/discover.js:153-161` |
| 3 | 插件自己的 `.venv`（`Scripts/python.exe`，再退到 `pyvenv.cfg`） | `lib/discover.js:116-151` |
| 4 | DSH 主运行时 `dsh-runtimes/dsh-primary-runtime/dependencies/python/python.exe` | `lib/discover.js:235-261` |
| 5 | `py -0p` 启动器列出的解释器 | `lib/discover.js:97-114` |
| 6 | `py -3`、`python`、`python3` 以及常见安装目录 | `lib/discover.js:75-95` |

路径里含 `WindowsApps` 的 Windows 商店别名桩在探测之前就被排除，因为它不是真正的解释器（`lib/discover.js:21-29`）。设置 `pythonPath` 会短路整个列表：只探测该解释器，失败即终止（`lib/discover.js:283-287`）。命令行也提供同样的单次覆盖（`bin/dsh-solidworks.js:130`），因此 `doctor --python <path>` 可以在不修改 profile 的情况下测试某个候选。

加载插件时默认不安装任何东西。当所有候选都不可用时，报错文案会明确说明这一点（`lib/discover.js:323`）：

```
未找到包含 'mcp' 与 'pywin32' 核心依赖的可用 Python 环境。已排查候选: ...。加载期默认禁止自动联网安装依赖；
请运行 "dsh-solidworks setup" 安装隔离依赖，或在 DSH 插件设置中手动指定 pythonPath。
```

自动自举只有在 `config.autoBootstrap` 为真或 `DSH_SOLIDWORKS_AUTO_BOOTSTRAP=1`，且失败原因是 `No module named` 时才触发（`lib/discover.js:293-311`）；触发后会对清华源执行 pip（`lib/discover.js:163-233`）。

| 环境变量 | 作用 | 依据 |
| --- | --- | --- |
| `DSH_SOLIDWORKS_PYTHON` | 优先的解释器候选 | `lib/discover.js:263-276` |
| `DSH_SOLIDWORKS_AUTO_BOOTSTRAP` | 为 `1` 时允许加载期尝试 pip | `lib/discover.js:293` |
| `DSH_SOLIDWORKS_SERVER` | `serverScript` 的替代来源 | `lib/discover.js:335` |

## 6. 本地 `.venv`

`npm run setup`（`package.json:89`）会创建 `pluginRoot/.venv`（`scripts/setup.js:246`、`scripts/setup.js:255-257`），并在 `pyvenv.cfg` 与解释器都存在时复用（`scripts/setup.js:259-262`）。若 `python -m venv` 失败，它会写入代理方案：`pyvenv.cfg`、`Scripts/python.cmd` 与 `Scripts/pip.cmd` 转调它找到的解释器，绝对路径被写死其中（`scripts/setup.js:277-305`）。

| 形态 | 解释器是什么 | 何时失效 |
| --- | --- | --- |
| 标准 venv | `.venv` 下真实的一份副本 | `.venv` 被损坏或删掉一半 |
| 代理 | 指向外部绝对路径的 `.cmd` shim | 外部解释器被卸载或移动 |

由于 shim 保存的是绝对路径，移动插件目录或删除它指向的解释器都会让 `.venv` 不可用。要在不动 CAD 数据的前提下重建，请改名而不是删除：`Rename-Item .venv .venv.broken-<日期>`，重新运行 `npm run setup`，等 `doctor --json` 报出 `ready: true` 后再删除改名后的目录。`setup` 只会为 desktop profile 写入 DSH 条目，且只写三个键（见 §10）。

## 7. PyPI 镜像策略

`setup.js` 一定会跑 pip，因此安装依赖会对它选中的索引发起 HTTPS 请求。选择由参数决定（`scripts/setup.js:308-320`），默认是清华源加官方源兜底，而不是阿里云。

| 调用方式 | 索引请求 | 依据 |
| --- | --- | --- |
| `npm run setup`（不带参数） | `https://pypi.tuna.tsinghua.edu.cn/simple` 加 `--extra-index-url https://pypi.org/simple` | `scripts/setup.js:314-320` |
| `--aliyun` | `https://mirrors.aliyun.com/pypi/simple/` | `scripts/setup.js:312-313` |
| `--official` 或 `--no-mirror` | 只用 pypi.org，不用镜像 | `scripts/setup.js:310-311` |
| `--optional` 或 `--full` | 同一索引，额外安装 `requirements-optional.txt` | `scripts/setup.js:363-379` |
| `--force` | 强制重装而不是跳过已满足的包 | `scripts/setup.js:331` |

本版本没有 `--tsinghua` 参数；清华就是默认行为。镜像安装失败后，脚本会用不带镜像参数的官方源重试一次（`scripts/setup.js:338-353`）。离线机器没有离线开关：真正不联网的路径是把 `pythonPath` 指向一个探测已通过的解释器，也就是依赖已经装好的那个（`lib/discover.js:283-287`）。`npm run mcp-config` 与 `doctor` 都不会安装任何包。

## 8. MCP 客户端配置

`npm run mcp-config`（`package.json:94`）会打印一段可直接粘贴给第三方 MCP 宿主的配置。默认它不写文件（`scripts/generate_mcp_config.js:99`）；只有加 `--write-direct-config` 或 `--out <path>` 才写文件（`scripts/generate_mcp_config.js:84-97`），而且该路径会附带警告：它绕过了插件的策略审批与审计链路（`scripts/generate_mcp_config.js:93`）。

```json
{
  "mcpServers": {
    "solidworks-cad": {
      "command": "<REPO>\\.venv\\Scripts\\python.exe",
      "args": [
        "<REPO>\\vendor\\solidworks-automation-skill\\mcp-server\\server.py"
      ],
      "env": {
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
        "DSH_ALLOWED_ROOTS": "[\"D:\\\\CAD\\\\projects\"]"
      }
    }
  }
}
```

生成器本身就输出这个形状（`scripts/generate_mcp_config.js:57-69`）：`.venv` 存在时 command 取该解释器（`scripts/generate_mcp_config.js:21-45`），args 指向随包 server 脚本，沙箱根目录来自 `DSH_ALLOWED_ROOTS` 或解析出的默认值（`scripts/generate_mcp_config.js:50-52`）。JSON 里每个反斜杠都要写成两个，所以 `D:\CAD` 在文件中是 `D:\\CAD`。直接使用这段配置的客户端会绕过 JS 策略、审批与审计日志直连 Python server。

## 9. 在 DSH 内配置插件

编辑 profile patch 中 `dsh-solidworks` 条目的 `config:` 映射（`cordis.patch.yml:11-21`）。三档最小样例：

```yaml
# read-only：只能检查与测量，不修改文档
- insert:
    - id: dsh-solidworks
      name: dsh-solidworks
      config:
        mode: read-only
```

```yaml
# standard：可建模但不保存/导出，路径限制在一个项目目录
- insert:
    - id: dsh-solidworks
      name: dsh-solidworks
      config:
        mode: standard
        allowedRoots:
          - "C:/CAD/projects"
```

```yaml
# full：可保存/导出/关闭，每次 HIGH 风险调用仍需审批
- insert:
    - id: dsh-solidworks
      name: dsh-solidworks
      config:
        mode: full
        auditLog: "C:/DSH/logs/solidworks-audit.jsonl"
```

省略的键会回退到 schema 默认值（`lib/index.js:81-97`）。DSH desktop profile 的该文件由应用管理，因此编辑后需要完全退出并重启 DSH；`setup` 会打印同样的提醒（`scripts/setup.js:437-460`）。

## 10. 多 Profile

`scripts/dsh_adapter.js` 只解析一个目录：`DSH_PROFILE_DIR`，否则 `<DSH_HOME 或 %USERPROFILE%\.dsh>/profiles/desktop`（`scripts/dsh_adapter.js:23-32`）。`setup` 只为该 profile 调用它一次（`scripts/setup.js:439-440`）。插件里没有任何遍历或修改其他 profile 的代码，因此第二个 profile 需要你手工写入同样的 `- insert:` 块。

| 项目 | 取值 |
| --- | --- |
| `setup`/`dsh_adapter.js` 写入的键 | 仅 `mode`、`pythonPath`、`toolTimeoutMs`（`scripts/dsh_adapter.js:202-207`） |
| 条目里的其他键 | 原样保留，只有三个受管键会被替换（`scripts/dsh_adapter.js:161-201`） |
| 写入前备份 | `cordis.patch.yml.bak-dshsolidworks-<时间戳>`（`scripts/dsh_adapter.js:212-217`） |
| 返回的动作 | `updated-in-insert`、`repaired-legacy-entry`、`appended-insert`、`unchanged`（`scripts/dsh_adapter.js:241-360`） |
| 形态检查 | `absent`、`insert`、`top-level-named`、`legacy-override`（`scripts/dsh_adapter.js:433-460`） |

`legacy-override` 表示宿主只把该条目当作配置覆盖，永远不会加载插件，因此 profile 里需要的是一条 `insert:` 条目，而不是顶层条目。

## 11. 审计日志

设置了 `auditLog` 后，每个事件都以一行一个 JSON 对象追加写入；`ts` 最先加入，随后是该事件的字段（`lib/policy.js:256-274`）。文件及其父目录会按需创建（`lib/policy.js:264`）。

| 事件 | 除 `ts` 外的字段 | 依据 |
| --- | --- | --- |
| `policy_allowed` / `policy_refused` | `event`、`tool`、`code`、`risk`、`session`、`challengeId` | `lib/policy.js:339-349` |
| `challenge_rejected` | `event`、`tool`、`challengeId`、`digest`、`code`、`reason`、`session` | `lib/policy.js:622-633` |
| `refused` | `event`、`tool`、`code`、`digest`、`session`、`challengeId` | `lib/index.js:538-541` |
| `approval_requested` | `event`、`tool`、`challengeId`、`channel`、`target`、`digest`、`session`、`callId` | `lib/index.js:604-615` |
| `confirm_granted` | `event`、`tool`、`challengeId`、`channel`、`outcome`、`digest`、`scope`、`session` | `lib/index.js:692-700` |
| `call` | `event`、`tool`、`risk`、`ok`、`granted`、`target`、`digest`、`ms`、`session` | `lib/index.js:806-811` |
| `execution_failed_after_approval` / `error` | `event`、`tool`、`risk`、`code`、`digest`、`ms`、`session` | `lib/index.js:795-805`、`lib/index.js:814-820` |
| `confirm_rejected` | `event`、`tool`、`challengeId`、`code`、`digest`、`message`、`session` | `lib/index.js:330-338` |

如果路径无法创建或追加，插件会在内存里保留最多 1000 条（`lib/policy.js:150`、`lib/policy.js:258-260`），同时累加 `failures` 与 `preservedInMemory`、记录 `lastError`，并打印一次控制台错误（`lib/policy.js:267-274`）。这些条目在 DSH 重启后消失，因此文件丢了就等于轨迹丢了。`solidworks_status` 会显示 `audit.configured`、`written`、`failures`、`preservedInMemory` 与 `lastError`（`lib/index.js:221-245`）。

## 12. 只读自检

| 命令 | 该看什么 |
| --- | --- |
| `node bin/dsh-solidworks.js version --json` | `version` 与 `pluginRoot`，确认实际运行的是哪一份副本（`bin/dsh-solidworks.js:122`） |
| `node bin/dsh-solidworks.js doctor --json` | `ready` / `readyFull`、`python.version`、`python.comDeps`、`server.script`、`solidworks.installed`、`nextSteps`（`bin/dsh-solidworks.js:129-152`）；`python.state` 只在探测失败时出现。 |
| `node bin/dsh-solidworks.js doctor --profile --json` | 看桌面 profile 里到底有没有本插件：`installedAsBundle`、`dependencySpec`、`patchEntry`、`mode`、`pythonPath`、`issues[]` |
| `node bin/dsh-solidworks.js list-tools --mode read-only --json` | 当前风险表下的 `total`、`published[]`、`withheld[]`（`bin/dsh-solidworks.js:154-201`） |
| `node bin/dsh-solidworks.js list-tools --mode full --json` | 切换模式前先看存在哪些 HIGH 风险工具（`bin/dsh-solidworks.js:183-193`） |
| `node bin/dsh-solidworks.js selftest --json` | 一次 `solidworks_health_check` 调用；会启动 server 并触碰 SolidWorks，但不修改文档（`bin/dsh-solidworks.js:203-225`） |

`list-tools` 与 `selftest` 会启动 Python server，因此同时也验证了解释器发现链路；只有 `doctor` 不会接触 SolidWorks。五条命令加 `--json` 都会输出 JSON，且都不会修改文档。

## 13. 适用范围与限制

- 工具的发布取决于策略，而不是 SolidWorks 版本检查（`lib/index.js:490-505`）。本文档所述配置在一台运行 SolidWorks 2026 SP4.1 的机器上核对过，不宣称其他版本区间已验证。
- `customTiers` 出现在 `DEFAULTS`（`lib/index.js:96`）、会传给 Policy（`lib/index.js:190`）且只允许升级分级（`lib/policy.js:228-244`），但它不在 schema 中（`lib/index.js:49-62`）。宿主是否会把这种未声明的键透传下来未经验证，因此本文不把它当作受支持配置项。
- Policy 上存在 `approvalMode`，默认 `balanced`（`lib/policy.js:196-219`），但插件从不传它（`lib/index.js:181-195`），因此审批通道就是宿主提供的那一套。
- 未验证：网络共享或文件被锁定时审计的行为（仅上述错误路径可确认）；同一 profile 内两个 `toolPrefix` 不同的插件实例；从市场安装插件时是否像 `setup` 一样保留手工添加的 `config:` 键（`scripts/dsh_adapter.js:161-201`）。