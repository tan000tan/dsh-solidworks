# dsh-solidworks Troubleshooting (v0.3.2)

Applies to plugin 0.3.2 on Windows 10 / 11 x64. Every entry follows the same order: Symptom → Cause → Check commands → Fix → Still failing. Run all commands from the repository root.

Boundaries up front: under `read-only`, write and high-risk tools are **not published** — that is policy design, not a fault; `solidworks_confirm` **always refuses** self-approval; the CLI has no `approve` / `reject` (removed). Do not try to work around these three points while troubleshooting.

## 0. Collect three pieces of information first

```powershell
node bin/dsh-solidworks.js doctor --json
npm run doctor
npm run list-tools
```

- `doctor --json`: read-only; prints `plugin` / `host` / `python` / `server` / `solidworks` / `ready` / `nextSteps` and writes no file.
- `npm run doctor`: runs 12 checks and writes `diagnostic-report.json` and `diagnostic-report.md`.
- `list-tools`: actually connects to the MCP service and shows the server tool surface plus what the current mode publishes / withholds.

Also call `solidworks_status` in DSH: it returns `policy.mode`, `connection.running`, `connection.error` and `connection.stderr` (last 10 lines) — most MCP child-process errors surface there. The plugin's own logger writes to the DSH host log; the MCP service's stderr is surfaced through `solidworks_status`.

## 1. No tools visible in DSH

**Symptom**: after enabling the plugin, DSH shows only `solidworks_status`, or no `solidworks_*` tool at all; asking the AI to build a part gets "no such tool".

**Cause**: the plugin is not installed into the current profile's `node_modules`, or is not enabled in that profile; DSH was not fully restarted after installing or changing configuration; the Python dependency probe failed and the plugin degraded to publishing only `solidworks_status`; or the mode is `read-only`, where write tools are not published by design.

**Check commands**:

```powershell
node bin/dsh-solidworks.js doctor --json
npm run list-tools
npm run list-tools -- --mode standard
```

**Fix**: confirm `dsh-solidworks` is enabled in the DSH plugin list, then **fully quit** DSH and start it again (refreshing the page does not count). If the `python` section of `doctor --json` is an error, go to sections 2 and 3. If only modelling tools are missing while read tools are present, switch `mode` to `standard` as described in USER_GUIDE section 4 and restart.

**Still failing**: attach the `doctor --json` output and the `solidworks_status` result to an issue using the `Installation problem` template.

## 2. Python not found / wrong version

**Symptom**: `python.state` in `doctor` is `error`; the message contains `未找到包含 'mcp' 与 'pywin32' 核心依赖的可用 Python 环境` or `configured pythonPath failed the import check`.

**Cause**: no Python 3.10+ on the machine; `python` resolves to the Microsoft Store `WindowsApps` stub (not a real interpreter — the probe flags it as `WINDOWS_STORE_ALIAS`); the plugin's `pythonPath` points at the wrong file — note it has the highest priority, and **once set, a failed import check returns `PYTHON_INVALID` without falling back** to other candidates; or the DSH-bundled runtime was not found.

**Check commands**:

```powershell
python --version
where python
py -3 --version
node bin/dsh-solidworks.js doctor --json
```

**Fix**: point `pythonPath` in the DSH plugin settings at a real `python.exe` (for example `C:\Users\<you>\AppData\Local\Programs\Python\Python312\python.exe`); or use the DSH-bundled runtime `%USERPROFILE%\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe`; or run `npm run setup` to create a `.venv` inside the repository (`.venv` is probed before the system `python`). If `where python` points at `...\WindowsApps\python.exe`, do not use it.

**Still failing**: validate one interpreter in isolation with `node bin/dsh-solidworks.js doctor --python "C:\real\path\python.exe" --json`; you can also set the `DSH_SOLIDWORKS_PYTHON` environment variable before starting DSH.

## 3. `mcp` or `pywin32` missing

**Symptom**: the same message as above (`lib/discover.js:323`): `未找到包含 'mcp' 与 'pywin32' 核心依赖的可用 Python 环境。已排查候选: ... 加载期默认禁止自动联网安装依赖；请运行 "dsh-solidworks setup" 安装隔离依赖，或在 DSH 插件设置中手动指定 pythonPath`; or a raw `ModuleNotFoundError: No module named 'mcp'` / `win32com`.

**Cause**: the `.venv` exists but pip did not finish (interrupted install, mirror failure), or the packages went into a different interpreter.

**Check commands**:

```powershell
.venv\Scripts\python.exe -c "import mcp, pydantic, jsonschema; import win32com.client; print('deps ok')"
npm run setup -- --force
```

**Fix**: reinstall the core dependencies with `npm run setup -- --force`; add `--official` if the mirror is unreachable. Re-run `doctor` afterwards; `COM_DEPENDENCIES` should be PASS.

**Still failing**: run `.venv\Scripts\python.exe -m pip install -r requirements.txt` manually and include the full error in an issue (`Installation problem` template).

## 4. COM registration problems

**Symptom**: `pywintypes.com_error`, `Class not registered`, `CO_E_SERVER_EXEC_FAILURE (0x80080005)`; `win32com.client` fails to import.

**Cause**: the pywin32 postinstall never ran; SolidWorks has never been started (COM registration normally happens on first launch); the current user lacks permission; or the SolidWorks installation itself is damaged.

**Check commands**:

```powershell
.venv\Scripts\python.exe -c "import win32com.client; print('com ok')"
reg query "HKLM\SOFTWARE\SolidWorks" /s
npm run doctor
```

**Fix**: run `npm run setup` — it calls `pywin32_postinstall.py -install -silent` only when `win32com` fails to import. If the automatic call did not succeed, run `.venv\Scripts\python.exe .venv\Scripts\pywin32_postinstall.py -install` from an **administrator** terminal. Then start SolidWorks manually once and let it finish initialising.

**Still failing**: repair the SolidWorks installation and reboot, then retry; include the `COM_DEPENDENCIES` and `LIVE_COM_ECHO` results from `npm run doctor`.

## 5. `npm run setup` dependency installation fails

**Symptom**: the `[3/6]` stage prints `[✖] 依赖安装失败`, exits with code 1, and suggests "请检查本地网络连接，或尝试手动安装 requirements.txt".

**Cause**: the mirror is unreachable or blocked by a proxy; the pip cache is corrupt; the installation was interrupted. The default mirror is actually **Tsinghua** `https://pypi.tuna.tsinghua.edu.cn/simple` with the official index `https://pypi.org/simple` added as a fallback; `--aliyun` uses the Aliyun mirror; `--official` / `--no-mirror` disables mirrors; `--tsinghua` is handled by the default branch. When the preferred index fails the script automatically retries once against the official index.

**Check commands**:

```powershell
npm run setup -- --official
npm run setup -- --aliyun
```

**Fix**: retry with a different index; on an offline machine run `pip download -r requirements.txt -d wheels` elsewhere, copy the folder over, then `.venv\Scripts\python.exe -m pip install --no-index --find-links wheels -r requirements.txt`.

**Still failing**: install the dependencies into `.venv` manually and then re-run `npm run setup` — when the dependencies are already present the idempotent check skips the download.

## 6. Restricted network / proxy

**Symptom**: pip timeouts, SSL handshake failures, connection resets; yet local Python and SolidWorks are fine.

**Cause**: a corporate proxy/firewall blocks PyPI and the mirrors; or you expect the plugin to fetch dependencies at load time — load-time auto-install is **disabled by default** and only happens with `DSH_SOLIDWORKS_AUTO_BOOTSTRAP=1` (or `autoBootstrap` configured).

**Check commands**:

```powershell
echo $env:HTTPS_PROXY
.venv\Scripts\python.exe -m pip config list
```

**Fix**: complete `npm run setup` on a connected machine and copy the whole `.venv` over; or run `npm run setup -- --official` in a terminal with `HTTPS_PROXY` / `HTTP_PROXY` set. Do not treat load-time auto-download as the normal path.

**Still failing**: install from offline wheels (see section 5) and mention the proxy environment in the issue.

## 7. MCP service fails to start / times out

**Symptom**: `solidworks_status` shows `connection.running` as `false` with a timeout in `connection.error`; the `server` section of `doctor --json` is an error; the DSH log never shows the line `tools from server ... published ...`.

**Cause**: `startTimeoutMs` defaults to 60000 ms, which a cold start plus Python imports can exceed; `serverScript` points at the wrong path; the packages in `.venv` are broken.

**Check commands**:

```powershell
npm run list-tools
node bin/dsh-solidworks.js doctor --json
.venv\Scripts\python.exe vendor\solidworks-automation-skill\mcp-server\server.py
```

**Fix**: raise `startTimeoutMs` in the plugin settings (allowed range 1000–300000); make sure `serverScript` points at `vendor\solidworks-automation-skill\mcp-server\server.py`; the last command shows the Python-side traceback — fix dependencies according to it.

**Still failing**: submit the last 10 lines of `connection.stderr` together with the manual traceback.

## 8. Cannot connect to SolidWorks

**Symptom**: `solidworks_health_check` fails; `solidworks_connect` reports it cannot create an instance; `CO_E_SERVER_EXEC_FAILURE (0x80080005)`; with an expired educational licence `MK_E_UNAVAILABLE` may appear (a real historical error, not hard-coded in the code — it is a runtime COM error).

**Cause**: SolidWorks is not running, or has never run so COM is not registered; a modal dialog inside SolidWorks blocks the COM call; the licence expired / is not activated; a previous COM call is hung.

**Check commands**:

```powershell
npm run doctor
tasklist | findstr /i sldworks
```

**Fix**: start SolidWorks manually, dismiss every modal dialog (sign-in, licensing, update prompts), then call `solidworks_health_check` again; confirm the licence is valid. Under `read-only`, `start_solidworks=True` is not allowed (it returns `POLICY_MODE: start_solidworks=True is prohibited`), so SolidWorks must be started by hand.

**Still failing**: save your work, fully exit SolidWorks and start it again; if that does not help, reboot. Then submit the `doctor` output and SolidWorks version via the `Real SolidWorks validation report` template.

## 9. "Permission denied"-style refusals under `read-only`

**Symptom**: write tools are absent from the tool list; or a call returns `POLICY_MODE` ("is a write-risk tool and the plugin runs in read-only mode"); or `POLICY_MODE: start_solidworks=True is prohibited (read-only mode or DSH_ALLOW_LAUNCH_SW!=1).`; or `Access denied: ... is outside allowed roots (DSH_ALLOWED_ROOTS)`.

**Cause**: this is **expected behaviour**, not a fault. `read-only` publishes READ tools only; `standard` excludes HIGH; `full` enables everything. Path errors come from the `allowedRoots` allow-list (by default only the session working directory).

**Check commands**:

```powershell
npm run list-tools -- --mode read-only
npm run list-tools -- --mode standard
```

**Fix**: to model, change `mode` to `standard` and restart DSH; to save/export/close, change it to `full` and be ready for the DSH host human approval prompt; put export paths inside `allowedRoots` (plugin settings) or use a path under the working directory.

**Still failing**: if you genuinely need one single tool, list it explicitly in the `allow` allow-list (use with care — it locally narrows the security boundary); otherwise adjust the mode as above.

## 10. Tool call timeout

**Symptom**: a tool call fails after several minutes with a timeout; simple tools such as `solidworks_health_check` still work.

**Cause**: `toolTimeoutMs` defaults to 300000 ms (5 minutes), allowed range 1000–600000; rebuilds, exports, batch operations or FEA can take longer; or SolidWorks is showing a dialog and waiting for a human.

**Check commands**:

```powershell
node bin/dsh-solidworks.js call solidworks_health_check --json
```

**Fix**: raise `toolTimeoutMs` in the plugin settings; split large operations into several smaller calls; dismiss SolidWorks modal dialogs before running.

**Still failing**: check whether the SolidWorks UI is stuck (watch CPU in Task Manager); save, restart SolidWorks and retry, and report the tool name and elapsed time in the issue.

## 11. Interrupted installation / leftovers

**Symptom**: `npm run setup` was interrupted with Ctrl+C; `.venv` is half-built and dependency checks fail; the DSH profile contains duplicate plugin entries.

**Cause**: the installation was interrupted, or setup/upgrade was run repeatedly.

**Check commands**:

```powershell
npm run uninstall -- --dry-run
node bin/dsh-solidworks.js doctor --json
```

**Fix**: run `--dry-run` first to see the cleanup scope (`.venv`, `dsh-mcp-config.json`, diagnostic reports, test benchmark artefacts, etc.; `.SLDPRT` / `.SLDASM` / `.SLDDRW` and `config-backups\` are preserved), then `npm run uninstall -- --yes`, then `npm run setup` again.

**Still failing**: delete `.venv` inside the repository manually and re-run setup; profile changes are backed up under `config-backups\` and can be restored from there. If it is still abnormal, attach the `uninstall --dry-run` output to an issue.

## 12. A `ok: true` result that is still wrong

A successful tool call means the call ran and returned a payload — not that the geometry is right. Two shapes of "suspicious success" are known in v0.3.2:

- **Fields are `null` while `ok` is true.** `solidworks_list_edges` returns `ok: true` with `length`, `mid_point` and `direction` all `null` on real hardware. Treat nulls as "not measured", never as zero.
- **Empty inputs pass.** `solidworks_interference_check` on an assembly with no components reports a pass, and `solidworks_review_active` can return a high score for a model it did not really inspect.

If a result looks too clean, verify it independently: read the value back with another tool (`solidworks_mass_properties` after a geometry change, `solidworks_inspect_dimension_impact` after `solidworks_update_dimension`), or check SolidWorks' own Mass Properties dialog. The per-tool evidence, including these two cases, is in `docs/FEATURE_MATRIX.md` and `docs/verification.md` (defects D-05 and D-11).

## 13. Source references

- `lib/discover.js:283-287` — `pythonPath` has priority and returns `PYTHON_INVALID` on failure without falling back.
- `lib/discover.js:323` — the unified error text for missing Python dependencies.
- `lib/discover.js:30-38` — `WindowsApps` stub interpreter detection (`WINDOWS_STORE_ALIAS`).
- `lib/index.js:49-59` — `toolTimeoutMs` 300000, `startTimeoutMs` 60000, `pythonPath`.
- `lib/index.js:241-243` — `connection.error` / `connection.stderr` in `solidworks_status`.
- `lib/index.js:493-507` — tools registered after policy filtering, with the published/withheld log line.
- `lib/index.js:554-575` — `APPROVAL_CHANNEL_UNAVAILABLE` (fail-closed) when no approval channel exists.
- `lib/policy.js:321-329`, `430-441` — publication rules for the three modes and the `POLICY_MODE` refusal text.
- `scripts/setup.js:308-320` — mirror selection: Tsinghua default + official fallback, `--aliyun`, `--official`/`--no-mirror`.
- `scripts/setup.js:381-430` — runs `pywin32_postinstall.py -install` only when `win32com` fails to import.
- `scripts/uninstall.js:24-25` — `--dry-run` and `--yes`.
- `vendor/solidworks-automation-skill/mcp-server/server.py:3976-3977` — `read-only` prohibits `start_solidworks=True`.
- `vendor/solidworks-automation-skill/mcp-server/server.py:4653` and others — `Access denied: ... outside allowed roots (DSH_ALLOWED_ROOTS)`.
- `vendor/solidworks-automation-skill/mcp-server/server.py:8448` — supported MCP protocol versions (unrelated to SolidWorks versions).
- `vendor/solidworks-automation-skill/scripts/sw_session.py:56-71`, `222-227` — only two non-essential dialogs are suppressed (stop the debugger, disable pre-release notice) and CommandInProgress is read; there is no auto-click allow-list.