# PROVENANCE — vendored execution engine

Last verified: 2026-11-18 (promotion-phase audit, `audit/promotion-phase/02-product-readiness-audit/`).

This file states what is vendored, where it came from, and exactly how the current tree differs
from the upstream commit it claims. An earlier revision of this file said *"174 files, 1.95 MB,
174/174 byte-identical, 0 modified"*. **That was wrong** — the shipped tree has 193 files,
2,436,053 bytes, and 28 of them contain real local changes. The numbers below were re-measured
against the upstream git history and supersede that statement.

## What is vendored

`vendor/solidworks-automation-skill/` — **193 files, 2,436,053 bytes**:

| path | files | role |
| --- | --- | --- |
| `mcp-server/` | 8 | MCP server entry (`server.py`), `artifact_access.py`, requirements, launcher scripts |
| `scripts/` | 91 | CAD script package (`sw_*`, `core/`, `cad_*`, `fea_*`, `dfm_*`, dimension/OCP writers) |
| `subskills/` | 68 | sub-skill implementations bridged from `scripts/` (drawing workflow, CNC fillet/chamfer, threaded holes, AutoCAD, vibecad) |
| `apps/desktop/cad_workbench/` | 23 | artifact ledger + job-queue modules imported by `artifact_access.py` and the health check |
| `capabilities.yaml` | 1 | capability registry read by `scripts/capabilities.py` |
| `manifest.json` | 1 | upstream project manifest (kept for traceability) |
| `LICENSE` | 1 | MIT license text of the upstream project |

Recomputed whole-tree digest (ordered `sha256sum` lines, LF-joined):

```
928e10d99b7f6f601bb21bf2f1c0a7742d91fc62b9c2de75237ba07fd5bbafed
```

Per-file SHA-256 for all 193 files is kept as a repository artifact at
`audit/promotion-phase/02-product-readiness-audit/vendor-sha256.txt` (the `audit/` tree is **not**
part of the npm package — see the `files` allowlist in `package.json`).

## Where it came from

- Declared remote: `https://github.com/tan000tan/solidworks-automation-skill.git` (reachable; HEAD at
  verification time: `7fdfbcf9a4851677ad7a04db372e74ba9aecee9b`, "docs: 顶部添加上游镜像说明").
- Pinned commit: `d8b9547` — "SolidWorks 自动化技能（自本机仓库同步）"; that commit's tree holds 470
  files, of which 193 are vendored here.
- Upstream license: MIT (`vendor/solidworks-automation-skill/LICENSE`).
- Earlier revisions of this file recorded a local staging path
  (`<DSH_WORKSPACE>\github-upload-staging\solidworks-automation-skill`) as the copy source. That path
  is no longer used; the git commit above is the authoritative reference.

## Changes to vendored files (measured, not assumed)

Method: clone the upstream repository into
`audit/promotion-phase/02-product-readiness-audit/upstream-probe`, `git checkout d8b9547`, then
compare every vendored file by SHA-256 and, for mismatches, by content after normalizing line
endings (CRLF → LF).

| result | files |
| --- | --- |
| byte-identical to `d8b9547` | **0** |
| differ only in line endings (local tree is CRLF) | 146 |
| differ in real content | **28** |
| not present in `d8b9547` at all (local additions) | **19** |

### The 28 files with real local changes

`mcp-server/server.py`, plus `scripts/`:
`advanced_geometry.py`, `advanced_geometry_ocp.py`, `advanced_surface_ocp.py`, `design_spec.py`,
`dfm_review.py`, `dxf_preview_scene.py`, `fea_analysis.py`, `fea_convergence.py`,
`headless_cad_writer.py`, `headless_occt_service.py`, `routing_review.py`, `sw_assembly.py`,
`sw_connect.py`, `sw_delivery.py`, `sw_export.py`, `sw_macro_guard.py`, `sw_measure.py`,
`sw_native_wire.py`, `sw_part.py`, `sw_pattern.py`, `sw_preflight.py`, `sw_process.py`,
`sw_review.py`, `sw_session.py`, `sw_sheet_metal.py`, `validate_mcp.py`, and
`subskills/solidworks-engineering-drawing/scripts/drawing_workflow.py`.

These carry the local security hardening (`path_security` integration, `DSH_ALLOWED_ROOTS` checks,
UI-free session behaviour) and the audit fixes applied during v0.3.x remediation. They are **not**
verbatim upstream code.

### The 19 files that exist only in this repository

`scripts/`: `cad_graph_executor.py`, `cad_task_context.py`, `cad_task_planner.py`,
`design_intent.py`, `dimension_dependency_graph.py`, `dimension_ir.py`, `dimension_manager.py`,
`dimension_modifier.py`, `dimension_reader.py`, `dimension_resolver.py`, `dimension_validator.py`,
`feature_graph_ir.py`, `model_quality_inspector.py`, `model_rebuilder.py`, `path_security.py`,
`shadow_backup.py`, `sw_compat.py`, `sw_job_object.py`, `sw_param_extractor.py`.

## Re-verification procedure

```bash
git clone --filter=blob:none --no-checkout https://github.com/tan000tan/solidworks-automation-skill.git /tmp/upstream-probe
git -C /tmp/upstream-probe checkout d8b9547
# then compare every file under vendor/solidworks-automation-skill/ the same way
```

Normalize line endings before claiming a content difference: this repository checks the vendored
tree out with CRLF, so a naive byte comparison reports 174 differences instead of 28.

## Actual import graph (verified on a real start, not assumed)

An earlier version of this file claimed `apps/` and `subskills/` were outside the graph. That was
wrong: `server.py` imports cleanly without them, but `tools/list` and the health check do not. The
verified graph is:

```
mcp-server/server.py
  ├─ mcp.server.fastmcp, pydantic           (PyPI, user-installed)
  ├─ scripts.sw_preflight                   (vendored, stdlib only)
  ├─ scripts.core.execution → core/{recovery,state,trace,verification,capability}
  ├─ artifact_access                        (vendored)
  │    └─ apps.desktop.cad_workbench.artifact_ledger
  │         ├─ .agent_contracts, .core      (stdlib only)
  │         └─ (queue_worker path) .agent_providers, .engineering_orchestrator,
  │            .knowledge_retrieval, .reviewer_gate, .worker_health  (stdlib only)
  └─ scripts.sw_native_wire                 (vendored, pydantic only)
```

`scripts/sw_drawing.py` and `scripts/drawing_spec.py` load
`subskills/solidworks-engineering-drawing/scripts/drawing_workflow.py` through
`importlib.util.spec_from_file_location` at call time, which is why `subskills/` must ship.

Nothing under `scripts/core/` imports `pywin32` at module import time, so `tools/list` works on a
machine without pywin32; COM imports happen lazily on the first tool that needs SolidWorks.
`apps/workbench-ui/` (Tauri front end), `dotnet/` (the .NET add-in source), `agents/`, `ai_team/`,
and `tests/` are **not** imported by any shipped tool. They stay out of the package; the two
maintainer scripts that reference them (`scripts/release_check.py`, `scripts/sync_bundled_skill.py`)
are inert unless a human runs them.

Consequence to keep visible: `solidworks_addin_host_status` looks for
`dotnet/CadStudio.SolidWorks.AddinHost/bin/Release/net48/*.dll`, which is a build output and is not
shipped. That tool reports the add-in as absent rather than crashing; the documentation describes it
as "requires a locally built add-in".

## Binaries

The repository ships **no** executables or native modules: no `.exe`, `.dll`, or `.pyd` exists
anywhere under `vendor/`, and no `swbridge.exe` (a file name that appeared in earlier internal notes)
was found anywhere in the tree. Everything is Python source, YAML/JSON metadata, and documentation.

## Upstream provenance risk (still open, tracked)

The upstream project declares MIT and carries **no attribution** to `eyfel/mcp-server-solidworks`
(the AGPL upstream that the larger `dsh-solidworks` product family vendors). Two measurements were
recorded during the 2026-10-29 audit:

1. **No verbatim derivation detectable at line level.** Comparing substantive Python lines
   (trimmed, ≥12 chars, comments/imports excluded) between the vendored tree (14,284 lines) and the
   AGPL `dsh-solidworks` tree (8,800 lines) yields 64 shared lines — Jaccard 0.003 — and all 64 are
   generic idioms (`changes = []`, `if not isinstance(params, dict):`, …).
2. **File-name overlap is 5 basenames** out of 470 vs 128 files, and only generic ones
   (`__init__.py`, `LICENSE`, `README.md`, `requirements.txt`, `server.py`).

Status of the release checklist:

- [x] Archive the comparison (counts + method) with the release notes — this section plus
      `audit/promotion-phase/02-product-readiness-audit/vendor-sha256.txt`.
- [ ] Ask the upstream maintainer to confirm the MIT claim and the absence of copied AGPL code —
      **open / blocked**: no confirmed contact channel was established, so this is recorded as an
      unresolved third-party question rather than a settled fact.
- [ ] If any file turns out to be derived from AGPL code, that file must be removed from the
      vendored tree or the whole package relicensed — the current split (MIT engine + AGPL plugin)
      depends on the MIT claim holding.

This is evidence, **not a legal conclusion**: line-level dissimilarity does not prove independent
authorship (structure, behaviour, and tool descriptions could still be derived).

## Sync policy

Re-vendoring is a deliberate, reviewed action: copy from a pinned upstream commit, re-run the
comparison above, update this file with the new commit, file counts, and date. No automatic updater
ships with the plugin.