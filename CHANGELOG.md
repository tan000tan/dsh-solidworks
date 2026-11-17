# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
