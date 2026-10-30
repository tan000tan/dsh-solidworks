# dsh-solidworks

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

| `mode` | publishes |
| --- | --- |
| `read-only` (default) | the 16 read-risk tools |
| `standard` | + the 26 write-risk tools = 42 (create/edit documents, never persist) |
| `full` | all 66; the 24 high-risk tools (save/export/close/pack/FEA/OCP) still need a one-shot grant |

`deny` > `allow` > `mode`. Writes are limited to `allowedRoots` (default: the session working
directory) unless a tool is explicitly `allow`ed. Audit rows carry tool name, risk, an argument
digest, duration, and session id — never raw arguments or tokens.

## Trust boundary

The plugin gates *what the model may ask SolidWorks to do*; it is not a filesystem sandbox — the
CAD writes are performed by `SolidWorks.exe` and remain subject to DSH's own sandbox and approval
policy. A cancelled or timed-out call reports `sideEffects: "unknown"` instead of claiming a
rollback. Automatic backup/rollback is deliberately not implemented in v0.1.

## Verification status

`docs/verification.md` is the authoritative record; the short version:

- 109 assertions across seven suites pass: policy 11, MCP client 8, argument-shape 16, packaging 11,
  audit trail 27, host-shaped end-to-end 27, crash isolation 9.
- `tools/list` against the real Python server returns all 66 tools (protocol 2025-06-18); the
  read-only tier publishes 16 + 2 meta tools and withholds the other 50.
- The plugin loads in a real DSH host from an installed copy, spawns the vendored server, serves
  a real `solidworks_health_check`, survives `dsh plugin remove`, and leaves no orphan Python.
- **No modelling, assembly, drawing, save, or export call has been executed against a live
  SolidWorks session yet.** Write paths are gated and unit-tested, not proven.

One argument-shape detail is worth knowing if you extend the engine: FastMCP wraps every tool's
arguments in `{"params": {...}}`. The plugin hoists that wrapper out of the schema the model sees
and re-wraps on the way back (`lib/schema.js`); without it every parameterised tool returns an
empty result while reporting success.

## License and provenance

The plugin is AGPL-3.0-only (`LICENSE`). The vendored engine is MIT
(`vendor/solidworks-automation-skill/LICENSE`); provenance and the exact upstream source are
recorded in `PROVENANCE.md`, third-party inventory in `NOTICE`. No source code from the
`dsh-solidworks` (AGPL) repository is included — policy, grants, MCP transport, and host entry
points are implemented independently here.