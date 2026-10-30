[![M8ven Score](https://m8ven.ai/badge/mcp/tan000tan-dsh-solidworks-1fp274?v=2fbb2bd4427c142ad9548eb0b4c5e187)](https://m8ven.ai/mcp/tan000tan-dsh-solidworks-1fp274?s=readme)# dsh-solidworks

![SolidWorks](https://img.shields.io/badge/CAD-SolidWorks%202026-red)
![DSH](https://img.shields.io/badge/Integration-DeepSeek%20Harness-blue)
![MCP](https://img.shields.io/badge/Protocol-MCP-purple)
![Platform](https://img.shields.io/badge/Platform-Windows%20only-lightgrey)
![Status](https://img.shields.io/badge/Status-Public%20Alpha-orange)
![License](https://img.shields.io/badge/License-AGPL--3.0-blue)

DeepSeek Harness plugin that puts a local SolidWorks desktop behind 66 CAD tools
(parts, assemblies, drawings, DFM, FEA). Read-only by default; document edits need a
higher policy tier and persistence needs a one-shot user confirmation.

- Plugin package: `dsh-solidworks` — AGPL-3.0-only
- Execution engine: the `solidworks-automation-skill` Python MCP server (MIT, vendored under `vendor/`, see `NOTICE`)
- Runtime shape: cordis plugin inside the DSH host → spawns the Python MCP server over stdio → COM → `SolidWorks.exe`

Chinese documentation, including the full config and troubleshooting tables, lives in
[README.zh.md](./README.zh.md).

## Requirements

Windows 10/11 x64 · SolidWorks desktop 2023–2026, activated and started at least once ·
Python 3.10+ x64 with `mcp>=1.27,<2`, `pydantic>=2`, `jsonschema>=4.20,<5`, plus `pywin32>=305`
and `comtypes>=1.2` on Windows (`ezdxf`, `numpy`, `Pillow`, `lxml`, `openpyxl`, `python-docx`,
`python-pptx`, `XlsxWriter` for the DFM/DXF/FEA families) · Node 22.12+.

The Microsoft Store `python.exe` alias cannot `import mcp`; discovery treats it as a failure
and names every candidate it tried. Setting `pythonPath` to a real interpreter is the most
reliable configuration.

## Install

- **Market**: install `dsh-solidworks` from the DSH market, then restart. No install script is
  needed; all probing happens on first load (market installs block `postinstall` anyway).
- **Local tarball**: `dsh plugin --profile web add .\dsh-solidworks-0.1.0.tgz`.
  The `desktop` profile is owned by the desktop app — use the GUI there. Keep the tarball on an
  ASCII-only path: a non-ASCII directory makes DSH record a garbled `file:` specifier.
- **Development**: add this directory to a profile's `cordis.patch.yml` `insert` list (this repo
  ships a ready `cordis.patch.yml`).

## First run (touches no CAD file)

```powershell
node bin\dsh-solidworks.js doctor --json --python "C:\Python313\python.exe"
node bin\dsh-solidworks.js list-tools --mode read-only
node bin\dsh-solidworks.js selftest
```

In a session, ask for `solidworks_status` first (it explains a broken environment), then
`solidworks_connect`, then read-only calls such as `solidworks_mass_properties`.
High-risk calls require `solidworks_confirm` with byte-identical arguments, then the call itself.

The same policy is reachable from a terminal, which is the fastest way to tell "the plugin is
misconfigured" apart from "the model asked for something silly":

```powershell
# arguments go in a file: PowerShell mangles inline JSON when it is passed to a native exe
node bin\dsh-solidworks.js call solidworks_health_check --arg-file .\args.json --mode read-only
node bin\dsh-solidworks.js call solidworks_save_document --arg-file .\save.json --mode read-only
# -> {"status":"refused","code":"POLICY_MODE","risk":"high",...}
```

## Policy

| `mode` | publishes | write calls | persistence calls |
|---|---|---|---|
| `read-only` (default) | 16 tools (health check, mass props, features, inspect sketch, mates, bounding box...) | refused | refused |
| `standard` | 42 tools (adds sketches, extrusions, cuts, revolves, fillets, mates...) | allowed inside `allowedRoots` | refused |
| `full` | all 66 tools (adds save, export STEP/STL/DXF/PDF, close, delete, Pack&Go) | allowed inside `allowedRoots` | **needs one-shot grant** |

A high-risk call without a matching grant returns:

```json
{"status":"refused","code":"CONFIRMATION_REQUIRED","tool":"solidworks_save_document","grantRequired":true}
```

The user (or an automation flow) approves it through the companion tool:

```json
{"name":"solidworks_confirm","arguments":{"tool":"solidworks_save_document","arguments":{"file_path":"D:\\parts\\bracket.sldprt"}}}
```

The grant binds to the SHA-256 of the canonical arguments, is single-use, and expires after five
minutes (`grantTtlMs`). The session's current directory is the default write root when `allowedRoots`
is not set; any path outside those roots is refused even if the user confirmed it.

The list of shipped tools and their assigned tiers is in [lib/policy.js](./lib/policy.js); it was
verified against the real Python MCP server at `tools/list` time (66 tools, zero drift).

## What happens when SolidWorks is missing or fails to launch

The host never crashes on startup:

- If Python is missing, or `server.py` cannot import `mcp`, or SolidWorks COM fails to register,
  `apply()` logs the diagnostic and publishes **only two meta tools**: `solidworks_status` and
  `solidworks_confirm`.
- Calling `solidworks_status` returns structured JSON explaining what is missing (the candidate
  interpreters tried, the missing COM classes, or the exit code) and the recommended next step.
- The standard server tools stay unpublished until the environment is healthy — the model cannot
  call tools that cannot run. Deployments that prefer the plugin registration to throw when CAD is
  expected to be present (e.g. a managed deployment) can opt in to `failOnStartupError: true` themselves.

## Verification status

`docs/verification.md` is the authoritative record; the short version:

- 110 assertions across seven suites pass: policy 11, MCP client 8, argument-shape 16, packaging 12,
  audit trail 27, host-shaped end-to-end 27, crash isolation 9. Reproduce everything with
  `$env:DSH_SOLIDWORKS_PYTHON = "<python.exe>"; npm run test:all` (exit 0 = all green); `npm test`
  runs the four suites that need no Python (47 assertions).
- `tools/list` against the real Python server returns all 66 tools (protocol 2025-06-18); the
  read-only tier publishes 16 + 2 meta tools and withholds the other 50. The three modes were
  measured against the live server: read-only 16, standard 42, full 66 published.
- The plugin loads in a real DSH host from an installed copy, spawns the vendored server, serves
  a real `solidworks_health_check`, survives `dsh plugin remove`, and leaves no orphan Python.
- **No modelling, assembly, drawing, save, or export call has been executed against a live
  SolidWorks session yet.** Write paths are gated and unit-tested, not proven. The minimal loop is
  ready to run the moment SolidWorks may be started:
  `node tests/write-loop.mjs --python <python.exe> --authorised` — new blank part → sketch +
  extrude → read the volume back → export one STEP file → close **without saving**. Without
  `--authorised` it refuses to run (exit 2).

One argument-shape detail is worth knowing if you extend the engine: FastMCP wraps every tool's
arguments in `{"params": {...}}`. The plugin hoists that wrapper out of the schema the model sees
and re-wraps on the way back (`lib/schema.js`); without it every parameterised tool returns an
empty result while reporting success.

## License and provenance

The plugin is AGPL-3.0-only (`LICENSE`). The vendored engine is MIT
(`vendor/solidworks-automation-skill/LICENSE`); provenance and the exact upstream source are
in `PROVENANCE.md`. `NOTICE` tracks third-party notices. `docs/license-risk.md` is an exhaustive list
of runtime imports vs shipped files, the whole-tree SHA-256 comparison against that repository,
the runtime dependency licence table, and the one item that still needs a human/legal call
(whether the MIT engine could be a derivative of the AGPL upstream — evidence says no, but the
upstream could not be fetched from this host).

## Releasing and publishing

| File | Purpose |
| --- | --- |
| `docs/github-publish.md` | exact commands for repo creation, push, tag `v0.1.0`, Release, topics, submission PR |
| `docs/release-notes-v0.1.0.md` | ready-made GitHub Release body (real numbers, "writes not verified" statement) |
| `docs/market-submission.md` | submission checklist plus the three open questions (`name` semantics, `category` vocabulary, whether `capabilities` is required) |
| `docs/submission/tan000tan__dsh-solidworks.yml` | the file to add as `data/plugins/tan000tan__dsh-solidworks.yml` |

---

## 📜 Historical Architecture Note (Pre-0.1.0 Prototype)

The repository's earlier commit history (`8af9bef` to `d4c7fde`) includes an initial exploratory prototype exploring a C#-based SolidPilot execution service and custom DSH integration profiles.

In v0.1.0, the project transitioned to a standard npm-distributable DSH plugin architecture (`dsh-solidworks`), bundling the policy gate, FastMCP schema bridge, and audit logging into a single cohesive package while keeping the full commit history preserved.
