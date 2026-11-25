# Advanced configuration

This page documents every configuration key the `dsh-solidworks` plugin accepts, the interpreter and mirror behaviour behind `setup`, and the diagnostics that do not touch a CAD document. Paths are repo-relative: `lib/index.js:49` means line 49 of that file in this package.

Fourteen keys are declared in the plugin schema (`lib/index.js:49-62`). Whatever you write is passed through `normaliseConfig` (`lib/index.js:105-117`), so bad numbers and unknown modes degrade to defaults instead of failing at load time. Out-of-range values are clamped by `clampTimeout` (`lib/index.js:99-103`).

## 1. Where configuration is read

| Surface | Location | Read by |
| --- | --- | --- |
| Shipped default patch | `cordis.patch.yml:11-21` | the entry DSH inserts into a profile |
| Profile patch | `<DSH_HOME>/profiles/desktop/cordis.patch.yml` (`scripts/dsh_adapter.js:29-32`) | DSH host at startup |
| Plugin schema | `lib/index.js:49-62` | `apply()` after the host hands over the config |
| Environment | `lib/discover.js:263-276` and `lib/discover.js:335` | interpreter and server-script resolution |
| CLI flags | `bin/dsh-solidworks.js:42` | one-shot diagnostics only |

The shipped entry looks like this (values are the defaults, not the only legal ones):

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

## 2. Field reference

| Field | Type | Default | Effect | Change it when | Consequence of changing it |
| --- | --- | --- | --- | --- | --- |
| `mode` (`lib/index.js:49`) | `read-only`, `standard` or `full` | `read-only` (`lib/index.js:82`) | policy ceiling: which server tools are published (`lib/index.js:490-505`) and what the Python server receives as `DSH_POLICY_MODE` / `DSH_ALLOW_LAUNCH_SW` (`lib/index.js:401-402`) | you need modelling (`standard`) or saving/exporting/closing (`full`) | an unrecognised value silently falls back to `read-only` (`lib/index.js:111`); even in `full`, HIGH-risk tools still need an interactive approval (`lib/policy.js:490-497`) |
| `allow` (`lib/index.js:50`) | string array; a comma-separated string is also accepted (`lib/index.js:119-123`) | `[]` (`lib/index.js:83`) | publishes a tool the risk table does not recognise (`lib/policy.js:321-323`, `lib/policy.js:354-356`) and lets it past a mode refusal (`lib/policy.js:430-436`) | the server exposes a tool newer than the plugin's own table | the named tool skips the mode ceiling, HIGH-risk ones included, so name tools deliberately |
| `deny` (`lib/index.js:51`) | string array | `[]` (`lib/index.js:84`) | the tool is never published (`lib/policy.js:321-329`) and a host guard refuses it even if something else registered it (`lib/index.js:836-844`) | a tool must stay unavailable in every mode | wins over `allow`; refusals carry `TOOL_DENIED` (`lib/policy.js:352`) |
| `allowedRoots` (`lib/index.js:52`) | string array of directories | `[]` (`lib/index.js:85`) | path sandbox for CAD files (`lib/policy.js:723-760`); a non-empty list replaces the session working directory (`lib/index.js:479-482`) | models or drawings live outside the DSH session directory | paths outside the listed roots are refused with `PATH_OUTSIDE_ALLOWED_ROOTS`; with no roots and no session cwd every path is refused (`lib/policy.js:731-733`) |
| `toolTimeoutMs` (`lib/index.js:53`) | number, milliseconds | `300000` (`lib/index.js:88`) | per-call timeout on the wire call (`lib/index.js:794`) and on the published tool definition (`lib/index.js:501`) | rebuilds or batch exports exceed five minutes | clamped to 1000..600000 (`lib/index.js:112`); a short value aborts long calls after the server has already started the work |
| `startTimeoutMs` (`lib/index.js:54`) | number, milliseconds | `60000` (`lib/index.js:89`) | MCP `initialize` and the first `listTools` (`lib/index.js:411`, `lib/index.js:487`) | cold Python or a slow disk makes the first start slow | clamped to 1000..300000 (`lib/index.js:113`); on failure the plugin keeps running with no CAD tools |
| `grantTtlMs` (`lib/index.js:55`) | number, milliseconds | `300000` (`lib/index.js:86`) | lifetime of an interactive approval grant (`lib/policy.js:204`, `lib/policy.js:702`) | one approval has to cover a long batch | values that are not finite, <= 0 or above 24 h throw when Policy is built (`lib/policy.js:152-159`); a long TTL widens the window in which one human click authorises repeated calls |
| `challengeTtlMs` (`lib/index.js:56`) | number, milliseconds | `120000` (`lib/index.js:87`) | lifetime of a pending approval challenge (`lib/policy.js:205`, `lib/policy.js:521`) | people need more than two minutes to answer the prompt | an expired challenge is refused as `CHALLENGE_EXPIRED` (`lib/index.js:634-635`) |
| `maxChallenges` (`lib/index.js:57`) | integer | `512` (`lib/index.js:91`) | cap on pending challenges held in memory; the oldest is evicted (`lib/policy.js:512-516`) | many high-risk calls run in parallel | must be an integer 1..10000, otherwise it is silently reset to 512 (`lib/index.js:114-115`) |
| `pythonPath` (`lib/index.js:58`) | string path | unset | explicit interpreter; every other candidate is skipped (`lib/discover.js:283-287`) | `.venv` is broken and a known-good interpreter exists | a bad path fails hard with `PYTHON_INVALID` and no fallback (`lib/discover.js:287`) |
| `serverScript` (`lib/index.js:59`) | string path | unset | overrides the bundled `server.py` (`lib/discover.js:334-343`) | a patched or forked server is in use | a missing file raises `SERVER_SCRIPT_MISSING`; the two meta tools are still registered (`lib/index.js:302-347`) |
| `serverCwd` (`lib/index.js:60`) | string path | unset | working directory of the Python subprocess; default is the parent of `mcp-server` (`lib/discover.js:344-347`) | the server expects a specific cwd | a missing directory raises `SERVER_CWD_MISSING` (`lib/discover.js:346`) |
| `toolPrefix` (`lib/index.js:61`) | string | `''` (`lib/index.js:95`) | prefix on every published name, meta tools included (`lib/index.js:261-262`, `lib/index.js:302-347`) | two instances must coexist in one profile | prompts, saved scripts and `call <tool>` invocations that use the bare name stop matching |
| `auditLog` (`lib/index.js:62`) | string path to a JSONL file | unset (`lib/index.js:90`) | durable audit trail (`lib/policy.js:256-274`) | you need records that outlive a DSH restart | unset means nothing is written to disk; an unwritable path degrades to memory only (§11) |

## 3. Modes and risk tiers

Every server tool is classified as READ, WRITE or HIGH (`lib/policy.js:21-23`). Tools missing from the explicit table are matched by pattern and default to HIGH (`lib/policy.js:126-131`), so a new tool is treated as dangerous until the table knows it.

| Mode | Published tools | HIGH-risk calls | Typical use |
| --- | --- | --- | --- |
| `read-only` | READ only (`lib/policy.js:321-329`) | refused with `POLICY_MODE` | inspection, measurement, review |
| `standard` | READ and WRITE | refused with `POLICY_MODE` | building and editing models without saving |
| `full` | every tier | allowed only after an interactive approval (`lib/policy.js:490-497`) | saving, exporting, closing documents |

Two rules apply in every mode: filenames listed in `PROTECTED_FILENAMES` cannot be written (`lib/policy.js:111-120`, `lib/policy.js:447`), and `solidworks_confirm` always returns `SELF_APPROVAL_PROHIBITED` because AI self-approval is disabled (`lib/index.js:311-347`).

## 4. Interaction of `allow`, `deny` and `allowedRoots`

| Situation | Result | Evidence |
| --- | --- | --- |
| a tool is in `deny` | withheld and refused | `lib/policy.js:321-329`, `lib/index.js:836-844` |
| a tool is in `allow` | published even if unrecognised | `lib/policy.js:354-356` |
| `allow` names a tool the current mode refuses | the call proceeds | `lib/policy.js:430-436` |
| `allowedRoots` is empty | only the session working directory is writable | `lib/index.js:479-482`, `lib/policy.js:723-760` |
| `allowedRoots` is non-empty | those directories replace the session directory | `lib/index.js:479-482` |
| a path argument is relative | rewritten to an absolute path before the call | `lib/policy.js:457-460` |

## 5. Python interpreter selection

`discover()` tries candidates in a fixed order (`lib/discover.js:263-276`); the first one that imports `mcp`, `pydantic`, `jsonschema`, `win32com.client` and `pythoncom` wins.

| Order | Candidate | Evidence |
| --- | --- | --- |
| 1 | `DSH_SOLIDWORKS_PYTHON` environment variable | `lib/discover.js:263-276` |
| 2 | embedded runtime `pluginRoot/.runtime/python/python.exe` | `lib/discover.js:153-161` |
| 3 | the plugin's `.venv` (`Scripts/python.exe`, then `pyvenv.cfg`) | `lib/discover.js:116-151` |
| 4 | DSH primary runtime `dsh-runtimes/dsh-primary-runtime/dependencies/python/python.exe` | `lib/discover.js:235-261` |
| 5 | launcher `py -0p` results | `lib/discover.js:97-114` |
| 6 | `py -3`, `python`, `python3` and standard install directories | `lib/discover.js:75-95` |

Windows Store alias stubs are rejected before probing, because a path containing `WindowsApps` is not a real interpreter (`lib/discover.js:21-29`). Setting `pythonPath` short-circuits the whole list: only that interpreter is probed, and a failure is final (`lib/discover.js:283-287`). The CLI exposes the same override for one run (`bin/dsh-solidworks.js:130`), so `doctor --python <path>` tests a candidate without editing the profile.

Loading the plugin does not install anything by default. When no candidate works, the reported message says so explicitly (`lib/discover.js:323`):

```
未找到包含 'mcp' 与 'pywin32' 核心依赖的可用 Python 环境。已排查候选: ...。加载期默认禁止自动联网安装依赖；
请运行 "dsh-solidworks setup" 安装隔离依赖，或在 DSH 插件设置中手动指定 pythonPath。
```

Automatic bootstrapping runs only when `config.autoBootstrap` is true or `DSH_SOLIDWORKS_AUTO_BOOTSTRAP=1`, and only for a `No module named` failure (`lib/discover.js:293-311`); it then runs pip against the Tsinghua index (`lib/discover.js:163-233`).

| Variable | Effect | Evidence |
| --- | --- | --- |
| `DSH_SOLIDWORKS_PYTHON` | preferred interpreter candidate | `lib/discover.js:263-276` |
| `DSH_SOLIDWORKS_AUTO_BOOTSTRAP` | `1` allows the load-time pip attempt | `lib/discover.js:293` |
| `DSH_SOLIDWORKS_SERVER` | alternative to `serverScript` | `lib/discover.js:335` |

## 6. The local `.venv`

`npm run setup` (`package.json:89`) creates `pluginRoot/.venv` (`scripts/setup.js:246`, `scripts/setup.js:255-257`) and reuses it when both `pyvenv.cfg` and the interpreter exist (`scripts/setup.js:259-262`). If `python -m venv` fails, it writes a proxy instead: a `pyvenv.cfg`, `Scripts/python.cmd` and `Scripts/pip.cmd` that forward to the interpreter it found, with absolute paths baked in (`scripts/setup.js:277-305`).

| Layout | What the interpreter is | Breaks when |
| --- | --- | --- |
| standard venv | a real copy under `.venv` | `.venv` is corrupted or half-deleted |
| proxy | a `.cmd` shim pointing at an absolute outside path | that outside interpreter is uninstalled or moved |

Because the shim stores absolute paths, moving the plugin directory or deleting the interpreter it points at leaves `.venv` unusable. To rebuild without touching CAD data, rename instead of deleting: `Rename-Item .venv .venv.broken-<date>`, run `npm run setup` again, and only remove the renamed folder after `doctor --json` reports `ready: true`. `setup` also writes the DSH entry only for the desktop profile and only three keys (§10).

## 7. PyPI mirror policy

`setup.js` always runs pip, so a dependency install makes HTTPS requests to the index it selects. The selection is argument-driven (`scripts/setup.js:308-320`), and the default is Tsinghua plus the official index as a fallback, not Aliyun.

| Invocation | Index requests | Evidence |
| --- | --- | --- |
| `npm run setup` (no flag) | `https://pypi.tuna.tsinghua.edu.cn/simple` plus `--extra-index-url https://pypi.org/simple` | `scripts/setup.js:314-320` |
| `--aliyun` | `https://mirrors.aliyun.com/pypi/simple/` | `scripts/setup.js:312-313` |
| `--official` or `--no-mirror` | pypi.org only, no mirror | `scripts/setup.js:310-311` |
| `--optional` or `--full` | same index, plus `requirements-optional.txt` | `scripts/setup.js:363-379` |
| `--force` | reinstalls instead of skipping satisfied packages | `scripts/setup.js:331` |

There is no `--tsinghua` flag in this version; Tsinghua is what you get by default. After a failed mirror install the script retries once against the official index without mirror arguments (`scripts/setup.js:338-353`). For an offline machine there is no offline switch: the network-free path is to point `pythonPath` at an interpreter whose probe already succeeds, i.e. one that has the dependencies installed (`lib/discover.js:283-287`). `npm run mcp-config` and `doctor` never install packages.

## 8. MCP client configuration

`npm run mcp-config` (`package.json:94`) prints a ready-to-paste block for third-party MCP hosts. It writes no file by default (`scripts/generate_mcp_config.js:99`); only `--write-direct-config` or `--out <path>` writes one (`scripts/generate_mcp_config.js:84-97`), and that path is warned about because it bypasses the plugin's policy and audit chain (`scripts/generate_mcp_config.js:93`).

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

The generator emits this shape itself (`scripts/generate_mcp_config.js:57-69`): the command is the `.venv` interpreter when it exists (`scripts/generate_mcp_config.js:21-45`), the argument is the bundled server script, and the sandbox root comes from `DSH_ALLOWED_ROOTS` or a resolved default (`scripts/generate_mcp_config.js:50-52`). JSON requires every backslash to be doubled, so `D:\CAD` becomes `D:\\CAD` inside the file. Clients that interpret this block directly talk to the Python server without the JS policy, approvals or audit log.

## 9. Configuring the plugin inside DSH

Edit the `config:` mapping of the `dsh-solidworks` entry in the profile patch (`cordis.patch.yml:11-21`). Three minimal presets:

```yaml
# read-only: inspect and measure only, no document changes
- insert:
    - id: dsh-solidworks
      name: dsh-solidworks
      config:
        mode: read-only
```

```yaml
# standard: modelling without save/export, roots limited to one project tree
- insert:
    - id: dsh-solidworks
      name: dsh-solidworks
      config:
        mode: standard
        allowedRoots:
          - "C:/CAD/projects"
```

```yaml
# full: save/export/close become callable, each HIGH-risk call still needs approval
- insert:
    - id: dsh-solidworks
      name: dsh-solidworks
      config:
        mode: full
        auditLog: "C:/DSH/logs/solidworks-audit.jsonl"
```

Keys you omit fall back to the schema defaults (`lib/index.js:81-97`). For a DSH desktop profile the file is managed by the app, so a full restart of DSH is required after editing; `setup` prints the same reminder (`scripts/setup.js:437-460`).

## 10. Multiple profiles

`scripts/dsh_adapter.js` resolves exactly one directory: `DSH_PROFILE_DIR`, otherwise `<DSH_HOME or %USERPROFILE%\.dsh>/profiles/desktop` (`scripts/dsh_adapter.js:23-32`). `setup` calls it once for that profile (`scripts/setup.js:439-440`). Nothing in the plugin enumerates or edits other profiles, so a second profile has to be configured by hand with the same `- insert:` block.

| Key | Value |
| --- | --- |
| written by `setup`/`dsh_adapter.js` | `mode`, `pythonPath`, `toolTimeoutMs` only (`scripts/dsh_adapter.js:202-207`) |
| other keys in the entry | kept as written; only the three managed keys are replaced (`scripts/dsh_adapter.js:161-201`) |
| backup before writing | `cordis.patch.yml.bak-dshsolidworks-<timestamp>` (`scripts/dsh_adapter.js:212-217`) |
| reported actions | `updated-in-insert`, `repaired-legacy-entry`, `appended-insert`, `unchanged` (`scripts/dsh_adapter.js:241-360`) |
| shape check | `absent`, `insert`, `top-level-named`, `legacy-override` (`scripts/dsh_adapter.js:433-460`) |

`legacy-override` means the host treats the entry as a config override and never loads the plugin, so the profile needs an `insert:` entry rather than a top-level one.

## 11. Audit log

With `auditLog` set, each event is appended as one JSON object per line; `ts` is added first, then the event's own fields (`lib/policy.js:256-274`). The file and its parent directories are created on demand (`lib/policy.js:264`).

| Event | Fields besides `ts` | Evidence |
| --- | --- | --- |
| `policy_allowed` / `policy_refused` | `event`, `tool`, `code`, `risk`, `session`, `challengeId` | `lib/policy.js:339-349` |
| `challenge_rejected` | `event`, `tool`, `challengeId`, `digest`, `code`, `reason`, `session` | `lib/policy.js:622-633` |
| `refused` | `event`, `tool`, `code`, `digest`, `session`, `challengeId` | `lib/index.js:538-541` |
| `approval_requested` | `event`, `tool`, `challengeId`, `channel`, `target`, `digest`, `session`, `callId` | `lib/index.js:604-615` |
| `confirm_granted` | `event`, `tool`, `challengeId`, `channel`, `outcome`, `digest`, `scope`, `session` | `lib/index.js:692-700` |
| `call` | `event`, `tool`, `risk`, `ok`, `granted`, `target`, `digest`, `ms`, `session` | `lib/index.js:806-811` |
| `execution_failed_after_approval` / `error` | `event`, `tool`, `risk`, `code`, `digest`, `ms`, `session` | `lib/index.js:795-805`, `lib/index.js:814-820` |
| `confirm_rejected` | `event`, `tool`, `challengeId`, `code`, `digest`, `message`, `session` | `lib/index.js:330-338` |

If the path cannot be created or appended, the plugin keeps up to 1000 entries in memory (`lib/policy.js:150`, `lib/policy.js:258-260`), increments `failures` and `preservedInMemory`, records `lastError`, and prints one console error (`lib/policy.js:267-274`). Those entries disappear when DSH restarts, so a lost file is a lost trail. `solidworks_status` exposes `audit.configured`, `written`, `failures`, `preservedInMemory` and `lastError` (`lib/index.js:221-245`).

## 12. Read-only self-checks

| Command | What to read |
| --- | --- |
| `node bin/dsh-solidworks.js version --json` | `version` and `pluginRoot`, to confirm which copy is running (`bin/dsh-solidworks.js:122`) |
| `node bin/dsh-solidworks.js doctor --json` | `ready` / `readyFull`, `python.version`, `python.comDeps`, `server.script`, `solidworks.installed`, `nextSteps` (`bin/dsh-solidworks.js:129-152`). `python.state` appears only on probe failure. |
| `node bin/dsh-solidworks.js doctor --profile --json` | whether the desktop profile actually carries the plugin: `installedAsBundle`, `dependencySpec`, `patchEntry`, `mode`, `pythonPath`, `issues[]` |
| `node bin/dsh-solidworks.js list-tools --mode read-only --json` | `total`, `published[]`, `withheld[]` for the current risk table (`bin/dsh-solidworks.js:154-201`) |
| `node bin/dsh-solidworks.js list-tools --mode full --json` | which HIGH-risk tools exist before you switch modes (`bin/dsh-solidworks.js:183-193`) |
| `node bin/dsh-solidworks.js selftest --json` | one `solidworks_health_check` call; it starts the server and touches SolidWorks but changes no document (`bin/dsh-solidworks.js:203-225`) |

`list-tools` and `selftest` start the Python server, so they also prove that discovery works; `doctor` alone does not contact SolidWorks. All five print JSON with `--json` and none of them modifies a document.

## 13. Scope and limits

- Tool publication depends on policy, not on a SolidWorks version check (`lib/index.js:490-505`). These settings were exercised on one machine running SolidWorks 2026 SP4.1; no other version range is claimed here.
- `customTiers` appears in `DEFAULTS` (`lib/index.js:96`), is forwarded to Policy (`lib/index.js:190`) and can only escalate a tier (`lib/policy.js:228-244`), but it is absent from the schema (`lib/index.js:49-62`). Whether a host passes that undeclared key through was not verified, so it is not documented as a supported setting.
- `approvalMode` exists on Policy with a default of `balanced` (`lib/policy.js:196-219`), but the plugin never passes it (`lib/index.js:181-195`), so the approval channel is whatever the host provides.
- Not verified: audit behaviour on a network share or a locked file beyond the error path above; two plugin instances with different `toolPrefix` values in one profile; whether installing the plugin from the market preserves hand-added `config:` keys the way `setup` does (`scripts/dsh_adapter.js:161-201`).