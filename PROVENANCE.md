# PROVENANCE — vendored execution engine

Recorded 2026-10-29 by the packaging pass that created this plugin; corrected the same day after
the first real server start showed the import graph was wider than assumed.

## What is vendored

`vendor/solidworks-automation-skill/` — **174 files, 1.95 MB**, all byte-identical to the source
tree (SHA-256 per file, 174/174 identical, 0 missing, 0 modified):

| path | files | role |
| --- | --- | --- |
| `mcp-server/` | 8 | MCP server entry (`server.py`), `artifact_access.py`, requirements |
| `scripts/` | 72 | CAD script package (`sw_*`, `core/`, `cad_*`, `fea_*`, `dfm_*`, OCP writers) |
| `subskills/` | 68 | sub-skill implementations that `scripts/` bridges into (drawing workflow, CNC fillet/chamfer, threaded holes, autocad, vibecad) |
| `apps/desktop/cad_workbench/` | 23 | artifact ledger + job-queue modules imported by `artifact_access.py` and the health check |
| `capabilities.yaml` | 1 | capability registry read by `scripts/capabilities.py` |
| `manifest.json` | 1 | upstream project manifest (kept for traceability) |
| `LICENSE` | 1 | MIT license text of the upstream project |

## Where it came from

- Source path: `D:\Agent工作区\DSH配置\github-upload-staging\solidworks-automation-skill`
- Git commit: `d8b9547` — "SolidWorks 自动化技能（自本机仓库同步）" (single-commit local mirror)
- Declared remote: `https://github.com/tan000tan/solidworks-automation-skill.git`
- License file: MIT, "Copyright (c) 2026 SolidWorks Automation Skill Contributors"

## Changes to vendored files

**None.** Every vendored file was copied verbatim and verified byte-identical to the source at
vendoring time. `__pycache__` directories produced by local runs are deleted, never shipped
(`.gitignore` and the `files` allowlist in `package.json` both exclude them — verify with
`npm pack --dry-run`). Re-verify with:

```powershell
$src = 'D:\Agent工作区\DSH配置\github-upload-staging\solidworks-automation-skill'
$vnd = 'vendor\solidworks-automation-skill'
Get-ChildItem $vnd -Recurse -File | ForEach-Object {
  $rel = $_.FullName.Substring((Resolve-Path $vnd).Path.Length).TrimStart('\')
  $same = (Get-FileHash $src\$rel -Algorithm SHA256).Hash -eq (Get-FileHash $_.FullName -Algorithm SHA256).Hash
  if (-not $same) { "DIFF $rel" }
}
```

## Actual import graph (verified on a real start, not assumed)

The first version of this file claimed `apps/` and `subskills/` were outside the graph. That was
wrong: `server.py` imports cleanly without them, but `tools/list` and the health check do not.
The verified graph is:

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
shipped. That tool reports the add-in as absent rather than crashing; the README documents it as
"requires a locally built add-in".

## Upstream provenance risk (open, must be resolved before public release)

The upstream project declares MIT and carries **no attribution** to `eyfel/mcp-server-solidworks`
(the AGPL upstream that `dsh-solidworks` vendors). Two facts were established by inspection on
2026-10-29:

1. **No verbatim derivation detectable at line level.** Comparing substantive Python lines
   (trimmed, ≥12 chars, comments/imports excluded) between the vendored tree (14,284 lines) and
   the AGPL `dsh-solidworks` tree (8,800 lines) yields 64 shared lines — Jaccard 0.003 — and all
   64 are generic idioms (`changes = []`, `if not isinstance(params, dict):`, …).
2. **File-name overlap is 5 basenames** out of 470 vs 128 files, and only generic ones
   (`__init__.py`, `LICENSE`, `README.md`, `requirements.txt`, `server.py`).

This is evidence, **not a legal conclusion**: line-level dissimilarity does not prove independent
authorship (structure, behaviour, and tool descriptions could still be derived). Before publishing:

- [ ] Ask the upstream maintainer to confirm the MIT claim and the absence of copied AGPL code.
- [ ] Archive this comparison (counts + method) with the release notes.
- [ ] If any file turns out to be derived from AGPL code, that file must be removed from the
      vendored tree or the whole package relicensed — the current split (MIT engine + AGPL plugin)
      depends on the MIT claim holding.

## Sync policy

Re-vendoring is a deliberate, reviewed action: copy from a pinned upstream commit, re-run the
hash comparison, update this file with the new commit and date. No automatic updater ships in
v0.1.0.