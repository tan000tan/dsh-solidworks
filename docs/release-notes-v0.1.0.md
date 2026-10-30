# v0.1.0 — SolidWorks for DeepSeek Harness

A policy-gated DSH plugin that drives a local SOLIDWORKS desktop through a bundled MCP server.
First public package; the read-only half is verified end to end, the write half is gated and unit-tested
but **has not been executed against a live SolidWorks session yet**.

## What it does

- **66 tools** exposed to the model: parts, sketches, features (fillet, chamfer, shell, pattern, mirror,
  revolve), assemblies (components, mates, interference), drawings, exports, measurement, DFM review,
  FEA preparation, plus 12 `cadstudio_*` OCP/DFX tools.
- **Three publish tiers**: `read-only` publishes 16 read tools + 2 meta tools, `standard` 42,
  `full` all 66 — measured against the real server, not just asserted in unit tests.
- **Confirmation for high-risk writes**: 24 tools (save, export, close, delete, Pack&Go…) require
  `mode: full` and a one-shot `solidworks_confirm` grant bound to byte-identical arguments, valid 5 min.
- **Path gate**: write tools refuse targets outside `allowedRoots` (default: session cwd).
- **Audit log**: one JSONL line per call — tool, risk, argument digest, result, duration — no argument
  values, no absolute paths, no tokens.

## Install

```powershell
dsh plugin --profile <profile> add <path-to>\dsh-solidworks-0.1.0.tgz
# or, once published: dsh plugin --profile <profile> add dsh-solidworks
```

Requirements: Windows 10/11 x64, SolidWorks desktop 2023–2026 (activated once), Python 3.10+ x64 with
`mcp>=1.27,<2` + `pydantic>=2` + `pywin32` + `comtypes` (and `jsonschema` for the DFM/FEA tools).
The plugin never installs dependencies and never touches the DSH installation.

## Verified in this release

| What | Evidence |
| --- | --- |
| 110 assertions across 7 suites | `npm run test:all` → exit 0 |
| Real server, real Python | `tools/list` = 66, protocol `2025-06-18`, no risk-table drift |
| Loads in a real DSH host | installed copy → host boot → `solidworks_status` → real `solidworks_health_check` (`status: ok`, `solidworks_detected: true`) |
| Survives a crash-looping server | `tests/crash.test.js` — no throw, 2 meta tools stay, reason reported |
| Install / upgrade / rollback / uninstall | isolated `DSH_HOME`: 0.1.0 → 0.1.1 → 0.1.0, `remove` leaves no orphan Python |
| Chinese/space paths | server found and started from `D:\…\路径 测试\vendor\…` |

## Not verified in this release

- **Any real write**: no sketch, feature, save, export or drawing call has run against SolidWorks here.
  The minimal loop is scripted and one command away (`tests/write-loop.mjs`, needs `--authorised`).
- `mode: full` confirmation against the real save/export tools (closed loop proven with a stub only).
- Assemblies and drawings beyond "listed and classified".
- DFM / FEA / OCP backends (need CalculiX/Elmer and the optional Python packages).

## Requirements and known limits

- Windows-only; the engine uses COM. `failOnStartupError` is not required — a missing SolidWorks or
  Python degrades to two meta tools and a diagnostic status instead of breaking the DSH boot.
- No automatic backup/rollback: saving is the user's (or the calling flow's) responsibility.
- A cancelled or timed-out write reports `sideEffects: "unknown"` rather than pretending to roll back.

## License

AGPL-3.0-only (`LICENSE`). The bundled engine (`vendor/solidworks-automation-skill/`, MIT,
`Copyright (c) 2026 SolidWorks Automation Skill Contributors`) is redistributed unmodified; its license
and the exact upstream commit are recorded in `NOTICE` and `PROVENANCE.md`. No source code from the
AGPL `dsh-solidworks` upstream repository is included — the comparison method and its result are in
`PROVENANCE.md`; that is evidence, not a legal opinion.

**Package**: `dsh-solidworks-0.1.0.tgz`, 204 files, sha256 `7caeb96c32af718b679807aab54a4258be5a2392ad20ac89b0296d4b1d20c1e4`
(re-hash after `npm pack`; the tarball is byte-stable only for identical inputs).