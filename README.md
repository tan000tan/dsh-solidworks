[![Release](https://img.shields.io/badge/version-0.4.0-blue.svg)](https://github.com/tan000tan/dsh-solidworks/releases)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%203.0-green.svg)](LICENSE)
[![Platform: Windows x64](https://img.shields.io/badge/Platform-Windows%20x64-lightgrey.svg)](INSTALL.md)
[![SolidWorks: 2026 tested](https://img.shields.io/badge/SolidWorks-2026%20tested-brightgreen.svg)](docs/verification.md)

# dsh-solidworks

> An MCP server plus DeepSeek Harness plugin that connects an AI assistant to the SolidWorks desktop session running on your own machine: it can read models, measure them, and — in a permission mode you choose and with your confirmation — create and modify geometry.

- Plugin package: `dsh-solidworks`, AGPL-3.0-only
- Execution engine: `solidworks-automation-skill` Python MCP server (MIT, vendored under `vendor/`, see `NOTICE`)
- Chinese documentation: [README.zh.md](./README.zh.md)

---

## What it is

`dsh-solidworks` runs a local MCP server that drives SolidWorks through its COM API. DeepSeek Harness (or any standard MCP client) talks to that server, so a conversational assistant can work on the CAD documents that are already open — or that it opens for you.

- It is **local only**: the server runs on your Windows machine and controls the SolidWorks instance on that machine. No cloud CAD service is involved.
- It is **not a CAD replacement**: it calls the same SolidWorks operations a script would call, with the same limits.
- It is **not a macro recorder**: every action is an explicit MCP tool call with explicit arguments.
- It is **not verified on every SolidWorks release** — see [Current status](#current-status) and [docs/verification.md](docs/verification.md).

## What you can do

| Area | What is available |
| :--- | :--- |
| Part modelling | Documents, sketches, extrude, revolve, fillet, chamfer, shell, linear/circular pattern, mirror, holes |
| Assemblies | Open documents, add and fix components, coincident/distance/concentric mates, interference check |
| Drawings and export | Generate drawing, review drawing, export active document, batch export, assembly BOM, pack and go |
| Inspection | Mass properties, bounding box, edges, native geometry inspection, configurations, motion study inspection |
| Dimensions and metadata | Identify dimensions, dimension impact analysis, safe dimension modification, custom properties, units |
| Review workflows | Active-document review, reviewed-body exclusion, STEP import, component replacement |
| Diagnostics | Environment health check, plugin status, tool catalogue, policy and permission diagnostics |

The registry currently exposes **71 MCP tools + 3 host meta-tools** (`solidworks_status`, `solidworks_confirm`, `solidworks_setup_runtime`). Per-tool status — implemented, registered, covered by automated tests, covered on real SolidWorks, or unverified — is listed in [docs/FEATURE_MATRIX.md](docs/FEATURE_MATRIX.md).

The results are uneven, and the areas above are not equally proven. In the full-matrix real-hardware baseline inherited from v0.3.2, **33 of 71 tools were verified (7 only on their main path), 13 failed and 24 were blocked** by a missing precondition such as a Motion licence or an `ActiveDoc`. In v0.4.0 targeted re-verification on SolidWorks 2026 SP4.1, **D-01 (`connect` / CLI cold-start), D-02 (`open_document` `ActiveDoc` switching), D-03a/D-03b (assembly component ownership + cross-process ledger), D-04 (`shell` `VT_VOID`), D-05 (`list_edges`), D-06 (`chamfer`), D-07 (`pattern`), D-08 (`solidworks_add_coincident_mate` decorator), D-10 (`export_active` PDF), D-11 (`interference_check` empty assembly), and D-12 (dimension `ICE` mapping)** passed on real hardware; **D-09, D-13 (`pack_and_go`), and `solidworks_revolve` remain deferred to v0.5.0**. Check the `Real SolidWorks` column before relying on a tool, and treat a successful response as evidence that the call ran, not that the geometry is correct.

## Requirements

| Component | Requirement |
| :--- | :--- |
| Operating system | Windows 10 or Windows 11, 64-bit |
| SolidWorks | Desktop installation, launched manually at least once, licence activated |
| DeepSeek Harness | `>=0.1.7-rc.2` |
| Node.js | `>=22.12` |
| Python | 3.10+ 64-bit, or the Python runtime bundled with DSH |

DeepSeek Harness is the host application: the plugin runs inside it and cannot install it for you. If you arrived from the DSH plugin catalogue, the host is already installed. Otherwise install DeepSeek Harness first and confirm `dsh --version` reports `>=0.1.7-rc.2` before continuing.

SolidWorks **2026 SP4.1** is the only release this project has been exercised against on real hardware. Versions 2020–2025 are *claimed* to be compatible, but there is no version gate in the code and no real-machine evidence for them; see [Current status](#current-status).

**Compatibility self-check (about 3 minutes).** On your own machine: (1) run `node bin/dsh-solidworks.js doctor --json` and confirm `solidworks.installed` is `true`; (2) open one known part in SolidWorks and call `solidworks_health_check`, then `solidworks_mass_properties`; (3) compare the numbers with the values SolidWorks shows under *Evaluate → Mass Properties*. If all three steps agree, read-only access works on your release; if step 2 or 3 fails, treat your release as unverified rather than assuming it works.

## Install

```cmd
npm run setup
npm run doctor
```

The whole path is terminal-only and takes roughly 10–15 minutes on a machine that already has DSH, Node.js and SolidWorks; you need to be able to copy and paste commands. `npm run setup` prepares the plugin's own `.venv` and installs Python dependencies without modifying your system Python; when installed via DSH bundle (`dsh.profile.bundles`), `setup` skips writing duplicate `cordis.patch.yml` entries automatically. `npm run doctor` prints a JSON health report and, if `mcp`/`pywin32` are missing (including when DSH's bundled runtime lacks them), prints a copyable one-line setup command pointing to the actual plugin directory. Then enable the plugin in DSH and start a conversation.

Full prerequisites, what setup creates, how to verify success, and how to uninstall are in [INSTALL.md](INSTALL.md). Do not tune the Python path by hand first — the usual failure is a mismatched interpreter, and `INSTALL.md` covers that case.

## Permissions and safety

| Mode | Behaviour |
| :--- | :--- |
| `read-only` (default) | Only read and analysis tools are published (19 of 71). Create/modify/save/export tools are withheld and cannot be called. |
| `standard` | Modelling tools are published; destructive tools such as save, close and export remain withheld. |
| `full` | Destructive tools become callable, and each high-risk call requires interactive approval from the host application. |

- The default is `read-only`. Changing the mode is an explicit configuration edit, not something an AI assistant can grant itself.
- Extra arguments are not a bypass: approval and policy checks are applied to the actual call, in the plugin runtime.
- Self-approval is disabled. `solidworks_confirm` **is** registered, as a diagnostic stub that always returns `SELF_APPROVAL_PROHIBITED`; the plugin cannot approve its own high-risk calls. See [SECURITY.md](SECURITY.md).
- The policy gate sits in the plugin runtime, not in the MCP server. A tool connected to the server directly, bypassing DSH, bypasses this gate as well — see [docs/verification.md](docs/verification.md) §4.3.
- The plugin confines file access to configured roots and does not write outside them unless you configure it to.
- What this does **not** do: it does not sandbox SolidWorks itself, it does not audit every API call SolidWorks makes, and it cannot prevent a modelling operation from producing geometry you did not intend. Treat AI-driven edits like any other automated CAD edit — work on copies of important files.

## Current status

| Item | Status |
| :--- | :--- |
| Current release | **v0.4.0** (`package.json`, fixes D-01..D-08, D-10..D-12, D-14, runtime setup meta-tool & cross-process ledger; D-09, D-13, `solidworks_revolve` deferred to v0.5.0) |
| DSH plugin catalogue | Entry currently serves **v0.3.2** (PR #16343 merged 2026-11-17); v0.4.0 update PR pending release approval |
| Real SolidWorks verification | Windows 11 x64 + SolidWorks 2026 SP4.1: v0.4.0 real hardware verification + v0.3.2 full-matrix baseline in [docs/verification.md](docs/verification.md) |
| SolidWorks 2020–2025 | **Not verified** — claimed compatibility only, no version gate in code |
| Automated tests | `npm run test:all`: 204 assertions across 20 suites, plus 45 Python suites (341 cases); see [docs/verification.md](docs/verification.md) |
| Drawings / DFM / FEA / motion | Registered tools that have not been exercised on real hardware to the same depth as part modelling |
| Mock-only coverage | The fake-COM layer covers policy, schema and error paths, not real SolidWorks behaviour |

Two caveats about that table. Until the v0.4.0 release asset and catalogue PR are published, the DSH catalogue continues to serve v0.3.2 and its rendered README lags this file. And the automated numbers describe the test suite, not the CAD tools: passing tests means the plugin's own code behaves as designed, not that a given SolidWorks operation succeeds.

## Known limitations

- Windows only. There is no macOS or Linux build, because SolidWorks has none.
- Real-machine coverage is concentrated on SolidWorks 2026 SP4.1 and on a subset of tools; unlisted tools are `unverified`, not "working".
- `read-only` is the default, so a new installation cannot model anything until you change the mode.
- Shadow backups cover the dimension-modification path, not every geometry edit.
- Long-running rebuilds and drawings can exceed the per-call timeout (default 300 s) and must be retried.
- SolidWorks modal dialogs block COM calls; the plugin fast-fails instead of hanging, but the user must still dismiss the dialog.
- Educational, student and network-licence editions are not systematically tested.
- The default `read-only` tool set is not uniformly healthy: of the 19 read-only tools published by default, 9 are clean `verified`, 3 are `verified (partial)`, 3 `failed` and 4 could not be exercised (blocked) in the real-hardware pass.
- A successful response is not a correctness guarantee for unverified paths; `D-09` (`schema_version`), `D-13` (`pack_and_go`), and `solidworks_revolve` remain deferred to v0.5.0.

## Documentation

| Document | Contents |
| :--- | :--- |
| [INSTALL.md](INSTALL.md) | Prerequisites, setup, MCP registration, success checks, uninstall and recovery |
| [docs/ADVANCED-CONFIG.md](docs/ADVANCED-CONFIG.md) | `pythonPath`, local `.venv`, mirrors, timeouts, approval TTLs, multi-profile setup |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Python, pywin32/COM, network, MCP startup and SolidWorks connection failures |
| [docs/FEATURE_MATRIX.md](docs/FEATURE_MATRIX.md) | Tool-by-tool capability and verification matrix |
| [docs/verification.md](docs/verification.md) | What was actually run, on which versions, and what was not |
| [CHANGELOG.md](CHANGELOG.md) | Release history |
| [README.zh.md](README.zh.md) | Chinese README, plus the mirrored Chinese docs under `docs/*.zh.md` |

## Feedback

- Bug: open <https://github.com/tan000tan/dsh-solidworks/issues/new/choose> and pick **Bug report**; include the plugin version, DSH version, SolidWorks version and the exact tool name.
- Installation failure: pick the **Installation problem** template at the same link and paste `doctor --json` and `doctor --profile --json` output.
- Real-machine result: pick the **Real SolidWorks validation report** template — reports from versions other than 2026 SP4.1 are especially useful.
- Security: do not open a public issue; follow [SECURITY.md](SECURITY.md).

## License

- Plugin host and glue: [AGPL-3.0-only](LICENSE).
- Vendored automation engine under `vendor/`: MIT, see [NOTICE](NOTICE).