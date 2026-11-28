# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-11-28

Upgrades the registry to **74 MCP tools + 3 host meta-tools** (22 read, 26 write, 26 high).

### Added
- Integrated 3 Stage 5 offline workflow tools (solidworks_plan_multi_schemes, solidworks_optimize_feature_tree, solidworks_inspect_cad_quality) under READ tier.
- Added minimal built-in templates (minimal_design_spec.json, minimal_drawing_spec.json).

### Fixed
- `solidworks_revolve`: fixed sketch exit, `SKETCHSEGMENT` / centerline selection with `Mark=4`, and `EditRebuild3`; real-SW 2026 volume verified at `28274.3339 mm³` (`0.0000%` error).
- `solidworks_add_concentric_mate`: upgraded `select_entities_for_mate` to `Select4(CreateSelectData(Mark))` with `Select2` fallback; real-SW 2026 assembly concentric mate + `interference_check` (`0` interferences) passed.
- `solidworks_generate_drawing`: verified real-SW 2026 generation of non-empty `.SLDDRW` (`65,828` bytes) and `.PDF` (`44,748` bytes) from `minimal_drawing_spec.json`.
- `FeatureGraph IR` & Stage 5 E2E: verified `COMPLETED` forward execution, `ROLLED_BACK` auto-rollback on invalid chamfer, and `plan_multi_schemes` → `revolve_boss` → `inspect_cad_quality` (`pass`, `0.0%` error).
- `D-09`: normalized `schema_version` / `schemaVersion` across `design_spec.py` and `drawing_spec.py`.
- `D-13`: enabled recursive `GetDependencies2(Traverseflag=True)` and assembly `GetComponents` fallback in `sw_delivery.py`.

## [0.4.0] - 2026-11-26

Unified public release superseding the unpublished `0.3.3` staging build. Keeps the **71 MCP tools + 3 host meta-tools** (`solidworks_status`, `solidworks_confirm`, `solidworks_setup_runtime`) accounting unchanged.

### Added
- **Interactive runtime setup meta-tool (`solidworks_setup_runtime`, host meta-tool #3)**:
  - Creates an isolated `<pluginRoot>/.venv` and installs `mcp`/`pywin32` on demand with `ctx.approval` fail-closed confirmation, re-entry lock, bounded timeout, failure rollback cleanup, and hot reload (`ensureClientSynced()`), without modifying system Python or `PATH`.
- **Cross-process ownership ledger (`D-03b`, `sw_connect.py`)**:
  - Persists plugin-created document ownership in `owned-docs.json` via file lock and atomic replace (`os.replace`), ensuring external documents remain 100% blocked by `DEF-SEC-01`.
- **Installer/upgrader & CLI risk enhancements (`scripts/setup.js`, `scripts/upgrade.js`, `bin/dsh-solidworks.js`)**:
  - Added `--no-profile` to `setup.js`, `--profile` forwarding and strict rollback errors to `upgrade.js`, and dynamic `conditionalRisk` annotations in `list-tools`.

### Fixed (Re-verified on SolidWorks 2026 SP4.1 + Integrated from v0.3.3 Staging)
- **Cold-start, ActiveDoc switching, assembly ownership & shell fixes (`D-01`, `D-02`, `D-03a`, `D-04`, `D-08`)**:
  - `D-01` cold-start propagation & policy gating; `D-02` `open_document` `ActiveDoc` switching (`ActivateDoc3`); `D-03a` assembly component ownership & parent reactivation; `D-04` `solidworks_shell` `VT_VOID` (`None`) false-failure fix; `D-08` `solidworks_add_coincident_mate` decorator binding fix (real-SW verified).
- **CAD & inspection remediation (`D-05`, `D-06`, `D-07`, `D-10`, `D-11`, `D-12`, `D-14`)**:
  - `D-05` (`solidworks_list_edges`): late-bound COM member protection so edge enumeration and directions succeed without crashing.
  - `D-06` (`solidworks_chamfer`): edge selection pre-check and `EditRebuild3` verification.
  - `D-07` (`solidworks_pattern`): datum plane fallback matching (`Front Plane` / `Top Plane` / `Right Plane`).
  - `D-10` (`solidworks_export_active` PDF): decoupled `ISldWorks` resolution without calling `model.GetSldWorksObject()`.
  - `D-11` (`solidworks_interference_check`): empty assembly cleanly returns `status="insufficient_input"`.
  - `D-12` (`dimension_reader.py`, `sw_review.py`): mapped `ICE` to `Extrusion` and inferred `through_state` from cylinder edge counts.
  - `D-14` (`sw_native_wire.py`): relaxed target-document pre-existence requirement for `import` actions (logic/offline verified).

### Known Limitations & Deferred to v0.5.0
- **`D-09`** (`schema_version` compatibility across drawing templates), **`D-13`** (`solidworks_pack_and_go` complex assembly dependency enumeration), and **`solidworks_revolve`** (real-SW revolve axis/closed profile creation) are explicitly **deferred to v0.5.0**.

## [0.3.3] - 2026-11-25 (Unpublished Staging — Superseded by v0.5.0)

Productization, documentation-truth pass, and targeted blocking CAD/CLI fixes ahead of wider promotion. No tool was added or removed; the 71-tool registry is unchanged.

### Fixed (Targeted v0.3.3 Remediation — Re-verified on SolidWorks 2026 SP4.1)
- **`D-01` Cold-start SolidWorks launch propagation and gating (`bin/dsh-solidworks.js`, `server.py`)**:
  - `bin/dsh-solidworks.js` (`callTool`, `listTools`, `selftest`) now forwards `DSH_POLICY_MODE`, `DSH_ALLOW_LAUNCH_SW`, `DSH_ALLOWED_ROOTS`, and `DSH_DEFAULT_CWD` to the spawned Python MCP server (matching `lib/index.js`).
  - `SolidWorksConnectInput` gains `start_if_needed` (default `True`, `wait_seconds` up to `120`); `solidworks_connect` enforces fail-closed `allow_launch=False` under `read-only` or `DSH_ALLOW_LAUNCH_SW=0` and passes `allow_launch=bool(params.start_if_needed)` under `standard`/`full` (`DSH_ALLOW_LAUNCH_SW=1`). `solidworks_health_check(start_solidworks=true)` now passes `allow_launch=True, wait_seconds=15` after passing the policy gate.
- **`D-02` `open_document` `ActiveDoc` switching (`sw_connect.py`, `sw_assembly.py`)**:
  - Added `activate_document()` and `activate: bool = True` to `open_document()`. Reusing an already-open document (`GetOpenDocumentByName`) and opening via `OpenDoc6`/`LoadFile4` now invoke `ActivateDoc3` (with `ActivateDoc2`/dynamic proxy fallback) and verify `sw.ActiveDoc`. `sw_assembly.add_component` preloads pass `activate=False`.
- **`D-03a` Assembly component ownership & mate follow-up activation (`server.py`)**:
  - `solidworks_add_component` registers components residing inside `DSH_ALLOWED_ROOTS` via `register_owned_document()` and re-activates the parent assembly; `solidworks_add_coincident_mate`, `solidworks_add_distance_mate`, and `solidworks_add_concentric_mate` re-activate the parent assembly after mate solve so follow-up calls (`mass_properties`, `export_assembly_bom`) succeed on the assembly without hitting `DEF-SEC-01`. (`D-03b` cross-process CLI ledger persistence remains deferred to `v0.5.0`.)
- **`D-04` `solidworks_shell` COM `VT_VOID` (`None`) false-failure (`sw_part.py`)**:
  - Real SolidWorks 2026 `sldworks.tlb` defines `IModelDoc2::InsertFeatureShell` as `VT_VOID` (which returns `None` in Python COM). `sw_part.shell()` now only treats explicit `False` as immediate failure; on `None` or `True`, it runs `EditRebuild3()` and verifies `_snapshot_feature_names()` delta growth so valid shells return `feature_created=True` while failing shells (e.g. `50 mm` wall on a `40 mm` box) still return `feature_created=False`.
- **DSH bundled Python mitigation & bundle-mode `cordis.patch.yml` guard (`lib/discover.js`, `bin/dsh-solidworks.js`, `scripts/dsh_adapter.js`, `scripts/setup.js`)**:
  - Kept default silent `autoBootstrap` strictly disabled on load; `PYTHON_NOT_FOUND` / `PYTHON_INVALID` and `doctor` `nextSteps` now print plain bilingual instructions with a one-line copyable `cd /d "<pluginRoot>" && npm run setup` command using the actual resolved `<pluginRoot>`.
  - Added `isInstalledAsDshBundle()` so `scripts/setup.js` skips writing redundant `cordis.patch.yml` entries when running inside a DSH bundle install (`dsh.profile.bundles` + `<profile>/node_modules/dsh-solidworks`, unless `--force-patch`).
- **Offline test portability (`tests/d02_d12_d13_config_and_discovery_test.mjs`)**:
  - Decoupled the `D-17` `COMDEP` test from host `.dsh` Python state via deterministic `_probePython` injection plus fail-closed `PYTHON_INVALID` handling when host runtime deps are absent.

### Fixed (Stage 3 Productization)
- **`solidworks_add_coincident_mate` was registered but unusable.** In the vendored snapshot
  `vendor/solidworks-automation-skill/mcp-server/server.py` the `@mcp.tool(...)` decorator had
  drifted onto the private helper `_mate_delta_payload`, so the advertised tool resolved to a
  function with the wrong signature. The decorator is back on
  `def solidworks_add_coincident_mate(...)` (upstream `d8b9547` layout). Regression guard:
  `tests/tool_registry_integrity_test.py`.
- **Re-running `setup` / `upgrade` silently dropped user security configuration.** Rewriting the
  profile entry only kept `mode` / `pythonPath` / `toolTimeoutMs`, discarding `auditLog`,
  `allow`, `deny`, `allowedRoots`, `grantTtlMs`, `challengeTtlMs`, `customTiers`.
  `scripts/dsh_adapter.js` now merges the existing `config:` block and only replaces the keys it
  manages (`BUG-0004`), covered by `tests/dsh_adapter_scripts.test.js`.
- **`doctor` reported `ready: true` while COM dependencies were missing** and never read the
  profile's real configuration, so a dangling `pythonPath` looked healthy while the host would
  refuse to load the plugin (`PYTHON_INVALID`). `bin/dsh-solidworks.js` now splits
  `readiness.core` / `readiness.full` (`readyFull`), reads the installed profile entry
  (`--profile`, bundle list plus `cordis.patch.yml`), reports the effective configuration source,
  and surfaces dangling paths in `nextSteps`.
- `uninstall.bat` launched the uninstaller without confirmation when double-clicked; it now
  prints the deletion scope and requires typing `y` (arguments are still forwarded verbatim).

### Changed
- README (EN/ZH) rewritten as a mirrored, non-marketing first screen: what it is, what it does,
  requirements, one install entry point, permission model, current verification status, known
  limitations, documentation map, feedback channels. The previous "enterprise-grade",
  "Zero-Friction", "Zero-Trust", "Double-Precision Physical Verification" claims are gone.
- New detailed docs, each with an English/Chinese pair: `INSTALL.md` / `docs/INSTALL.zh.md`,
  `docs/ADVANCED-CONFIG.md`, `docs/USER_GUIDE.md`, `docs/TROUBLESHOOTING.md`,
  `docs/FEATURE_MATRIX.md`, `docs/verification.md`, plus `CONTRIBUTING.md`, `SECURITY.md`,
  `SUPPORT.md` and their `docs/*.zh.md` counterparts.
- `dsh-plugin.json` description/presentation/permissions now state that only 19 read-only tools
  are published under the default `read-only` mode, that the ceiling is 71 tools, and that the
  audit log is optional; `docs/locale/en.json` and `docs/locale/zh.json` no longer tell users to
  self-authorize through `solidworks_confirm` (it always fails closed).
- `PROVENANCE.md` rewritten from measured facts: 193 files / 2,436,053 bytes / tree digest
  `928e10d99b7f6f601bb21bf2f1c0a7742d91fc62b9c2de75237ba07fd5bbafed`; 0 files byte-identical
  to upstream `d8b9547`, 146 differ only by CRLF, 28 differ in content, 19 do not exist upstream.
  `NOTICE.md` is now an explicit "superseded" pointer to `NOTICE` instead of contradicting it.
- Added `.github/ISSUE_TEMPLATE/` (bug report, installation problem, real SolidWorks validation
  report, feature request) with desensitisation requirements, and a documentation consistency
  checker at `audit/promotion-phase/04-regression-validation/doc-check.mjs`.
- `docs/verification.md` (and the new `docs/verification.zh.md`) rewritten as a bilingual,
  evidence-based L1–L4 record: 71 tools reached on real hardware, 33 `verified` (7 partial),
  13 `failed`, 24 `blocked`, 1 `known-limitation`, defects D-01…D-14; 20 top-level offline
  suites / 202 assertions plus 44 Python suites / 336 cases. The older 66-tool evidence journal
  is kept unchanged at `docs/archive/verification-2026-11-17-legacy.md`.
- `docs/FEATURE_MATRIX.md` and `docs/FEATURE_MATRIX.zh.md` are now generated from the runtime
  registry plus the real-SolidWorks run, and use explicit per-tool states
  (`verified` / `failed` / `blocked` / `known-limitation`) instead of the previous blanket
  "PRODUCTION_READY" labels.
- Added `docs/market-submission.md`: records the DSH catalogue entry (updated to v0.3.2 via
  `awesome-dsh-plugin#16343`, merged 2026-11-17), the remaining asset/description lag, and
  the fact that the marketplace UI install path is still unverified.
- `package.json` `files` allowlist now ships `INSTALL.md`, `CONTRIBUTING.md`, `SECURITY.md`,
  `SUPPORT.md` and `NOTICE.md`, so an install from the published tarball carries the same
  guidance as the repository.

## [0.3.2] - 2026-11-17

### CAD Remediation & False-Success Prevention
- **`solidworks_shell` (`sw_part.py`, `server.py`)**:
  - Fixed `AttributeError: <unknown>.InsertFeatureShell` by invoking `IModelDoc2.InsertFeatureShell(thickness, outward)` (verified against SolidWorks 2026 `sldworks.tlb`) instead of `FeatureManager.InsertFeatureShell`.
  - Added strict positive finite thickness checks, `SelectByID2` face-selection failure guards (`SHELL_FACE_NOT_SELECTED`), and post-feature tree verification.
- **Assembly Mate Commit Verification (`sw_assembly.py`, `server.py`)**:
  - Added pre/post `MateGroup` feature-tree delta verification inside `add_mate5_checked` and `solidworks_add_coincident_mate` / `solidworks_add_distance_mate` / `solidworks_add_concentric_mate` to block `SUSPECT_FALSE_SUCCESS` (`MATE_NOT_COMMITTED`) when `AddMate5` returns a proxy without committing a mate feature.
- **Documentation & Package Parity (`docs/verification.md`)**:
  - Updated `docs/verification.md` `tests/host.test.js` historical wording (`21` tools / `tools: 71`) and bumped release candidate metadata to `0.3.2` (live SolidWorks 2026 COM/CAD re-execution remains explicitly gated by `L5-BLOCK-01` where Student Edition is expired).

## [0.3.1] - 2026-11-11

### Security Hardening (P0 Fixes)
- **Fail-Closed Interactive Host Approval (`lib/policy.js`, `lib/index.js`, `lib/validate.js`)**:
  - Completely eliminated the vulnerable `confirmedByHuman: true` boolean check and disabled self-service `solidworks_confirm` (always fails closed with `SELF_APPROVAL_PROHIBITED`).
  - High-risk operations (`mode: full`) generate bound challenges (`challengeId`, canonical arguments digest, target paths, session ID, `callId`, `expiresAt`) and strictly require host-native interactive user authorization (`ctx.approval`); when absent or denied, calls refuse closed (`APPROVAL_CHANNEL_UNAVAILABLE` / `APPROVAL_DENIED`).
  - Merged strict JSON boolean/schema validation (`lib/validate.js`, `AUD-SEC-001`) and session/digest challenge-grant binding (`AUD-SEC-002`).
  - Verified across adversarial and security regression suites (`tests/approval_security_adversarial_test.mjs`, `tests/r1_r5_security_matrix_test.mjs`, `tests/confirm_human_authorization_test.js`, `tests/phase5_security_approval_test.js`).

### Runtime Isolation & Productization (P1 Fixes)
- **Dedicated Python Virtual Environment Isolation (`lib/discover.js`)**:
  - Fixed runtime discovery so host Python installations and DSH Primary Runtimes are treated strictly as seed interpreters.
  - All dependency auto-bootstrapping now creates a dedicated `.venv` inside `<pluginRoot>` and installs core packages (`mcp>=1.0.0`, `pywin32>=306`) inside the private `.venv` only.
  - Ensured host Python and DSH Primary Runtime site-packages remain 100% pristine and uncontaminated.
- **CAD Toolset & Manifest Reconciliation**:
  - Unified exact tool accounting: 71 vendored CAD tools (19 READ, 26 WRITE, 26 HIGH) plus 2 DSH host meta/policy tools (`solidworks_status`, `solidworks_confirm`), totaling 73 declared tools in `dsh-plugin.json` and registered into the DSH host.
### Diagnostics & Lifecycle Verification
- Full PASS on `node scripts/doctor.js` (12/12 checks, 0 blocking errors).
- Full PASS on `node scripts/run_test_all.mjs` (20/20 top-level suites, 201/201 assertions).
- Full PASS on `python -B scripts/run_all_python_tests.py` (42/42 Python test suites, 0 skipped, 0 failed).
- Final Closure & Real-Environment Hardening (`D-02` / `D-11` / `D-12` / `D-13` / `D-17` / `D-18` / `AUD-COM-001`):
  - Added optional `@deepseek-ai/schemastery` native `Config` export in `lib/index.js` for DSH settings form integration (gracefully degrades offline).
  - Added `COMDEP` optional `comtypes`/`win32com` probing in `lib/discover.js` and `environment.degraded` reporting in `lib/index.js`.
  - Eliminated Head-of-Line Blocking in `server.py` (`use_lock=False` for 14 non-COM `cadstudio_*` tools and `solidworks_recover`; finite `SW_LOCK_WAIT_TIMEOUT_SECONDS` fast-fail for COM calls; paired `_com_initialized()` in `solidworks_recover`).
- Note on physical CAD verification: historical live SolidWorks 2026 runs are recorded in `docs/verification.md` and `audit/real-test-integrated-closure/12-final-closure/`; when local SolidWorks Student Edition license expires (`L5-BLOCK-01`), live COM creation is blocked externally until re-activated, while all mock/offline/policy/DSH host regressions remain verified.

## [0.3.0] - 2026-11-10

### Added
- **Multi-Version SolidWorks Compatibility Matrix (`sw_compat.py`)**: Seamless compatibility adapters across SolidWorks 2020 through 2026, dynamic feature probe, and transparent degradation to legacy COM interfaces when modern APIs are unavailable.
- **DSH Plugin Manifest v0.15 Compliance (`dsh-plugin.json`)**: Upgraded to DSH manifest schema v0.15, declaring complete tool permissions, process spawn facets, and multi-language display metadata.

## [0.2.0] - 2026-11-01

### Added
- **CAD Failure Auto-Purge & Safe Retry State Machine (`scripts/cad_task_context.py`)**: Built an industrial-grade failure recovery and task isolation system. Features explicit task ID tracking, reverse feature cleanup protecting native datum planes/origins, automated document purge on failure, COM handle release, and strict state machine verification (`RUNNING` -> `FAILED` -> `ROLLING_BACK` -> `CLEANUP_VERIFYING` -> `READY_TO_RETRY`). Rigorously validated across 10 consecutive live failure injections on SolidWorks 2026, achieving zero background document stacking and zero residual temp files.
- **Automated Zero-Friction Setup Flow (`scripts/setup.js`)**: Pure Node.js cross-language setup pipeline (`npm run setup`). Automatically discovers system Node.js and Python 3.10+ environments across drive letters, provisions an isolated local virtual environment (`.venv`), installs runtime requirements idempotently with optional Tsinghua/Aliyun mirror flags (`--tsinghua`, `--aliyun`), and executes `pywin32_postinstall.py` to register SolidWorks COM automation classes.
- **8-Dimensional System Doctor (`scripts/doctor.js`)**: Comprehensive self-healing diagnostic CLI (`npm run doctor`) validating Windows x64 architecture, Node.js runtime, Python virtual environment, SolidWorks COM registration, STA Worker thread integrity, SolidWorks live heartbeats, workspace I/O sandbox permissions, and MCP configuration endpoints with PASS/WARN/FAIL triage and actionable fix instructions.
- **Safe Workspace Cleanup & Dry-Run Uninstaller (`scripts/uninstall.js`)**: Added `npm run uninstall` supporting `--dry-run` simulation and `--purge` modes. Whitelist-based cleanup safely removes virtual environments and cache directories while strictly protecting user CAD parts (`.sldprt`, `.sldasm`, `.slddrw`) and configuration snapshots.
- **Automated Backup & Safe Upgrader (`scripts/upgrade.js`)**: Added `npm run upgrade` with automated pre-upgrade configuration snapshots (`config-backups/`), idempotent dependency synchronization, automated diagnostic checks, and non-destructive failure rollback hints.
- **Natural Language CAD Parameter Extractor (`vendor/solidworks-automation-skill/scripts/sw_param_extractor.py`)**: Built an intelligent engineering parameter parsing engine supporting bilingual regex extraction (length, width, height, thickness, hole diameter), automated unit normalization (mm, cm, m, inch), geometric and physical validation, and interactive clarification prompt generation when essential dimensions are missing.
- **Kahn Topological Feature Graph Compiler (`scripts/feature_graph_ir.py`)**: Intermediate Representation (IR) for CAD modeling operations featuring Directed Acyclic Graph (DAG) cycle detection, dependency tracking, and Kahn's topological sorting algorithm for deterministic feature execution sequencing.
- **Atomic Shadow Backup & Self-Healing Rollback (`scripts/shadow_backup.py`)**: Integrated transaction-level snapshot management into `sw_session.py`. Creates hidden binary shadow backups prior to destructive geometric mutations, enabling lossless byte-level restoration upon COM rebuild errors or API failures.
- **Model Dimension Inspection & Safe Modification Engine (`scripts/dimension_manager.py`)**: Implemented automated traversal of feature tree sketch dimensions, fuzzy parameter search, downstream topological impact assessment, and self-healing dimension modification with transaction rollbacks.
- **Comprehensive Product Documentation Suite**:
  - `README.md` & `README.zh.md`: User-centric quickstart guides focusing on zero-friction setup and natural language prompts.
  - `docs/USER_GUIDE.md`: In-depth tutorial covering installation, parameter rules, error recovery, and interactive modeling workflows.
  - `docs/TROUBLESHOOTING.md`: Systematic diagnostics and recovery guide for COM errors, virtualenv issues, and file lock collisions.
  - `docs/FEATURE_MATRIX.md`: Transparent capability status matrix covering 13 modeling features, assemblies, drawings, and export formats.

### Fixed
- **Development Path Hardcoding Elimination**: Completely purged developer-specific hardcoded paths across `scripts/setup.js`, `scripts/doctor.js`, and test suites in favor of dynamic cross-disk probing and environment variable overrides.
- **Modal Dialog Guard & Safe Recovery**: Hardened `solidworks_recover` in `server.py` with an explicit bilingual whitelist (`Save As / 另存为`, `Options / 系统选项`, `Open / 打开`), completely eliminating accidental closures of active user dialogs during automated error recovery.
- **Windows Exclusive File Lock Collision (`PermissionError [Errno 13]`)**: Resolved file lock conflicts during shadow restoration by explicitly invoking `CloseDoc` to release native COM file locks before byte-level overwrites, followed by `OpenDoc6` to seamlessly reload the clean model.
- **PowerShell Script Execution Policy Blocking**: Deprecated all `.ps1` wrapper scripts in favor of native Node.js subprocess pipelines, completely bypassing Windows Restricted ExecutionPolicy constraints on developer and enterprise machines.
- **Python Dependency Decoupling**: Separated core runtime dependencies (`requirements.txt`: pywin32, comtypes, pydantic, mcp) from heavy optional numerical analysis packages (`requirements-optional.txt`: numpy, scipy, matplotlib) for lightning-fast installations.
