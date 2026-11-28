# dsh-solidworks User Guide (v0.3.2)

This guide is for SolidWorks users who are using the plugin for the first time. It describes only behaviour that actually exists in the repository source: it does not promise capabilities the code does not have, and it does not present "unverified" as "verified". The source locations checked while writing this guide are listed at the end.

Applies to: plugin 0.3.2; Windows 10 / 11 x64; DSH `>=0.1.7-rc.2`; Node `>=22.12`; Python 3.10+ x64.

## 1. What this plugin does

`dsh-solidworks` is a DeepSeek Harness (DSH) plugin. It starts a local Python MCP service (`vendor/solidworks-automation-skill/mcp-server/server.py`), connects to the locally installed SolidWorks through COM, and publishes that service's tools to the AI assistant inside DSH. It currently registers 74 CAD tools; DSH adds 2 host-side meta tools (`solidworks_status`, `solidworks_confirm`), for 73 in total.

| Can do | Cannot do |
| --- | --- |
| Read mass properties, bounding box and dimension lists of the active SolidWorks document (read tier) | Does not detect or limit the SolidWorks version: there is no version gate or version probe in the code |
| In `standard` mode: create parts, sketch-and-extrude, change dimensions, open documents | Performs no GUI clicking and does not record or replay macros; COM API only |
| In `full` mode: save, export, close — each call raises a human approval prompt in the DSH host | Under `read-only`, write and high-risk tools do not appear in the tool list at all; it is not "the call fails" but "the tool is absent" |
| The dimension-edit path has a shadow backup and can restore from the shadow file on failure | It is not "every geometry edit is backed up automatically"; sketches, features and other paths have no general rollback |
| Generate drawings, batch export, etc. (high risk, requires `full`) | Cannot bypass approval; the `solidworks_confirm` self-approval endpoint is always refused |
| Self-check the runtime and which tools the current mode publishes via `doctor` / `list-tools` | Without a local SolidWorks installation no CAD tool is available; the plugin degrades to publishing only `solidworks_status` |

## 2. Prerequisites

- Windows 10 or Windows 11, x64.
- DSH `>=0.1.7-rc.2`.
- Node.js `>=22.12`.
- Python 3.10+ (x64). Ticking "Add python.exe to PATH" during installation makes life easier but is not required — the DSH-bundled runtime and the `pythonPath` plugin setting also work (see TROUBLESHOOTING section 2).
- SolidWorks installed **and started manually at least once**. COM registration normally happens on first launch; on a machine where SolidWorks has never run, the plugin cannot create a SolidWorks instance.
- Licensing: SolidWorks 2020–2026 is the nominal range. This project has only been validated on SolidWorks 2026 SP4.1 (Windows 11 x64); other versions are unverified. Differences between Professional and Educational licences are also unverified; history includes an `MK_E_UNAVAILABLE` caused by an expired educational licence (that string is no longer hard-coded in the current code; it is a runtime COM error).
- Disk: the plugin creates a `.venv` inside the repository, which needs a few hundred MB.

## 3. First use

### 3.1 Install dependencies

From the repository directory:

```bash
npm run setup
```

What it does: probes for Python 3.10+, creates or reuses a `.venv` in the repository, installs `requirements.txt` (`mcp`, `pydantic`, `pywin32`, `comtypes`, `jsonschema`) with pip, runs `pywin32_postinstall.py -install -silent` if `win32com` fails to import, and finally — if a DSH desktop profile is detected — writes the plugin entry into that profile's `cordis.patch.yml`.

What it does not do: it does not modify the system Python, does not modify PATH, does not change the PowerShell execution policy, and does not silently write `dsh-mcp-config.json`. The one registry write it can cause is the pywin32 COM registration above (see [INSTALL.md](../INSTALL.md#what-setup-never-does) for the exact keys). It uses the Tsinghua mirror by default with the official index added as a fallback; `--aliyun` switches to Aliyun; `--official` / `--no-mirror` disables mirrors; `--tsinghua` is handled by the default branch (there is no separate Tsinghua branch in the source). If the preferred index fails, it retries once against the official index.

### 3.2 Health check

```bash
npm run doctor
node bin/dsh-solidworks.js doctor --json
```

`npm run doctor` runs 12 checks and writes `diagnostic-report.json` / `diagnostic-report.md`; `doctor --json` only prints the structured result (`plugin`, `host`, `python`, `server`, `solidworks`, `ready`, `nextSteps`) and writes no file, so it is safe to run at any time. Both are read-only and do not need SolidWorks to be running.

### 3.3 Enable the plugin in DSH

Enable `dsh-solidworks` in the DSH plugin list / plugin settings (market-installed plugins live under the profile's `node_modules`). After installing or editing `cordis.patch.yml` you must **fully quit and restart DSH** — refreshing the page is not enough.

Once enabled, ask: "Call `solidworks_status` and show the plugin status." The reply should contain `policy.mode`, `connection.running` and the registered tool count. If `connection.running` is `false`, read `connection.error` and `connection.stderr` (last 10 lines) first, then follow TROUBLESHOOTING.

### 3.4 First read-only conversation

The default mode is `read-only`, which permits read operations only. Open a part in SolidWorks manually, then type in DSH:

> First call `solidworks_health_check` to confirm the SolidWorks connection, then use `solidworks_mass_properties` to tell me the mass and volume of the current part.

The assistant should call `solidworks_health_check` and then `solidworks_mass_properties`. Both are `read` tier and available under `read-only`. Add `solidworks_bounding_box` for overall dimensions, or `solidworks_identify_dimensions` to list editable dimension names.

## 4. From read-only to modelling

Modelling requires switching the policy mode from `read-only` to `standard`. That means **editing configuration and restarting**, not saying "switch to standard" in the chat:

1. Change `mode` to `standard` in the DSH plugin settings, or edit the profile's `cordis.patch.yml` and change `config.mode` from `read-only` to `standard`.
2. Fully quit DSH and start it again.
3. Confirm with `solidworks_status` that `policy.mode` is now `standard`; you can also preview the published tool set with `npm run list-tools -- --mode standard`.

Under `read-only`, write tools (`solidworks_open_document`, `solidworks_new_document`, `solidworks_create_basic_part`, `solidworks_sketch_and_extrude`, `solidworks_update_dimension`, etc.) are not registered at all; under `standard` they appear, but `high` tools such as save, export and close remain unavailable.

First modelling conversation example:

> Create a 60 × 40 × 20 mm box part, then tell me its volume.

The assistant will typically create a document with `solidworks_new_document`, build the geometry with `solidworks_create_basic_part` (or `solidworks_sketch_and_extrude`), and may adjust the size with `solidworks_update_dimension`. The file is still unsaved — saving is `high` risk, see section 5.

## 5. High-risk operations and confirmation

Only `full` mode allows saving, exporting and closing: `solidworks_save_document`, `solidworks_export_active`, `solidworks_batch_export_files`, `solidworks_close_documents`, `solidworks_pack_and_go`, plus high-risk tools such as `solidworks_modify_dimension_safe`, `solidworks_execute_feature_graph` and `cadstudio_run_fea`.

Every high-risk call raises an interactive human approval prompt in the DSH host; the approval is bound to the tool name plus an argument digest and cannot be pre-granted in bulk. When no approval channel is available in the host, the call fails closed and returns `APPROVAL_CHANNEL_UNAVAILABLE` ("Failing closed") — that is by design, not a bug.

`solidworks_confirm` is disabled for self-approval: it always returns `status: refused` and `code: SELF_APPROVAL_PROHIBITED`. The AI cannot issue approval to itself, and the CLI has no `approve` / `reject` subcommands (they were removed and return `APPROVAL_CLI_REMOVED`). Export targets must also stay inside the allowed roots (`allowedRoots`, by default the session working directory); otherwise the call reports `Access denied: ... is outside allowed roots (DSH_ALLOWED_ROOTS)`.

## 6. Three typical workflows

**A. Read model properties (`read-only`)**: open the part manually in SolidWorks → `solidworks_health_check` → `solidworks_mass_properties` (mass, volume, centre of mass) → optionally `solidworks_bounding_box` and `solidworks_identify_dimensions`. Nothing is modified. Note that `solidworks_open_document` is a write-tier tool and is unavailable under `read-only`, so this step must be done by hand.

**B. Change a dimension (`standard`)**: `solidworks_open_document` to open the part (or open it manually) → `solidworks_identify_dimensions` to find the dimension name → `solidworks_update_dimension` to set the new value → rebuild and re-read the dimension to verify. This path has a shadow backup (`ShadowBackupManager` is used only by the dimension management code) and can attempt a restore on failure; it does **not** cover sketches, features or other edits.

**C. Export PDF or STEP (`full` + human approval)**: `solidworks_save_document` to save first, then `solidworks_export_active` with `output_path` and `export_format` (e.g. `pdf` / `step`). Both save and export raise an approval prompt each time; the output directory must be inside `allowedRoots`.

## 7. When something goes wrong

Start with `docs/TROUBLESHOOTING.md`. Three most common judgements:

1. **Few tools in DSH, or only `solidworks_status`**: usually the Python dependency probe failed and the plugin degraded — not a permission problem. Run `node bin/dsh-solidworks.js doctor --json`: a healthy report has `python.version` and `python.comDeps`; the `python.state` field appears **only when the probe failed**.
2. **Modelling tools "disappeared"**: check `policy.mode` first. Under `read-only`, write and high-risk tools are not published; that is expected. To model, switch to `standard` as described in section 4 and restart.
3. **Cannot connect to SolidWorks**: start SolidWorks manually, dismiss modal dialogs, then retry `solidworks_health_check`; if it still fails, see TROUBLESHOOTING section 8 (COM).

## 8. Known limitations

1. Windows only (win32 x64); macOS / Linux are not supported.
2. SolidWorks 2020–2026 is nominal, but this project has only been validated on SolidWorks 2026 SP4.1 (Windows 11 x64); other versions are unverified.
3. `read-only` is the default, so most modelling, save and export tools are unavailable; modelling requires a configuration change and a DSH restart.
4. Backup covers only the dimension-edit path; there is no general rollback, and "every edit is reversible" does not hold.
5. There is no GUI automation and no macro recording/replay; everything goes through the COM API.
6. Professional vs. Educational licence differences are unverified; an expired educational licence can produce `MK_E_UNAVAILABLE`.
7. Per-tool real-machine coverage is tracked in `docs/FEATURE_MATRIX.md`: in the v0.3.2 real-hardware pass, 33 of the 74 tools were verified (7 only on their main path), 13 failed and 24 were blocked by a missing precondition. The matrix is regenerated from the run log; do not copy the numbers elsewhere.

## 9. Feedback

Use GitHub Issues and pick the template that matches:

- `Bug report (tools / runtime)` — tool behaviour and runtime errors.
- `Installation problem` — installation, dependencies, Python environment.
- `Real SolidWorks validation report` — real-machine results on a specific SolidWorks version.
- `Feature request` — new capability requests.

Please attach the output of `node bin/dsh-solidworks.js doctor --json` (redact paths as needed) and the `solidworks_status` result.

## 10. Source references

- `lib/policy.js:21-23` — risk tier constants READ / WRITE / HIGH.
- `lib/policy.js:28-106` — per-tool risk table (`solidworks_health_check`, `solidworks_mass_properties`, `solidworks_open_document`, `solidworks_update_dimension`, `solidworks_save_document`, `solidworks_export_active`, etc.).
- `lib/policy.js:125-133` — unknown tools default to HIGH.
- `lib/policy.js:200`, `212-213` — default mode is `read-only`; only `read-only | standard | full` are accepted.
- `lib/policy.js:321-329` — `read-only` publishes READ only; `standard` excludes HIGH.
- `lib/policy.js:430-441` — mode refusal returns `POLICY_MODE` with a hint.
- `lib/index.js:49-59` — config entries `mode`, `toolTimeoutMs` (300000), `startTimeoutMs` (60000), `pythonPath`.
- `lib/index.js:293-345` — `solidworks_status` and the always-refused `solidworks_confirm` (`SELF_APPROVAL_PROHIBITED`).
- `lib/index.js:493-507` — tools registered after policy filtering, with published/withheld counts logged.
- `lib/index.js:554-575` — fail-closed when no host approval channel exists (`APPROVAL_CHANNEL_UNAVAILABLE`).
- `lib/index.js:241-243` — `solidworks_status` connection diagnostics (`running` / `error` / `stderr`).
- `lib/discover.js:283-287` — `pythonPath` has priority and returns `PYTHON_INVALID` on failure without falling back.
- `lib/discover.js:323` — error text when Python dependencies are missing (includes "自动联网安装依赖" restriction).
- `scripts/setup.js:308-320` — mirror selection (Tsinghua default + official fallback; `--aliyun`; `--official`/`--no-mirror`).
- `scripts/setup.js:381-430` — runs `pywin32_postinstall.py -install` only when `win32com` fails to import.
- `scripts/setup.js:432-445` — does not silently write direct MCP config; writes the DSH profile patch.
- `scripts/doctor.js:367-407` — `SOLIDWORKS_VERSION_TIER` only parses a fixed version string and prints a matrix; it is not a runtime version probe.
- `scripts/uninstall.js:24-25` — `--dry-run` and `--yes`.
- `vendor/solidworks-automation-skill/mcp-server/server.py:8448` — supported MCP protocol versions (unrelated to SolidWorks versions).
- `vendor/solidworks-automation-skill/mcp-server/server.py:3976-3977` — `read-only` prohibits `start_solidworks=True`.
- `vendor/solidworks-automation-skill/mcp-server/server.py:4653` and others — path escape error `Access denied: ... outside allowed roots (DSH_ALLOWED_ROOTS)`.
- `vendor/solidworks-automation-skill/scripts/shadow_backup.py:24` — `ShadowBackupManager` (used only by the dimension-edit path).