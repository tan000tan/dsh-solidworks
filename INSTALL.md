# Installing dsh-solidworks

This is the detailed installation guide for [dsh-solidworks](README.md). The short version is two commands; this document explains what those commands do to your machine, how to tell whether they worked, and how to undo them.

Chinese version: [docs/INSTALL.zh.md](docs/INSTALL.zh.md).

## Before you install

| Requirement | How to check |
| :--- | :--- |
| Windows 10/11, 64-bit | `echo %PROCESSOR_ARCHITECTURE%` → `AMD64` or `ARM64` |
| SolidWorks desktop installed and licensed | Launch SolidWorks once by hand and confirm it opens a document |
| DeepSeek Harness `>=0.1.7-rc.2` | `dsh --version` |
| Node.js `>=22.12` | `node --version` |
| Python 3.10+ 64-bit **or** the Python runtime bundled with DSH | `python --version`; if this prints nothing or opens the Microsoft Store, you have no usable Python — `setup` can still use the DSH runtime |
| Network access for `pip` | Required only when Python dependencies are not yet present |

- Close nothing and move no files. `setup` writes only inside the plugin directory and one file in your DSH desktop profile.
- You do **not** need administrator rights, you do **not** need to edit `PATH`, and you do **not** need to install Python system-wide.
- If SolidWorks is open with unsaved documents, leave it open; installation does not touch running SolidWorks.

## What `npm run setup` does

`setup` is a Node script (`scripts/setup.js`). It runs six steps and prints `[n/6]` for each:

1. **Platform check** — reports `process.platform`, OS release and architecture. Non-64-bit Windows produces a warning, not a hard stop.
2. **Python detection** — tries, in order: the interpreter recorded in an existing `.venv/pyvenv.cfg`, the Python bundled with DSH, `--python <path>`, the environment variables `DSH_SOLIDWORKS_PYTHON`, `PYTHON` and `PYTHON_PATH`, the commands `python`, `python3`, `py`, and the usual Windows install directories for Python 3.13/3.12/3.11/3.10. The first interpreter that reports Python ≥3.10 wins; if none does, setup exits with a download link and instructions.
3. **Virtual environment** — creates `.venv` inside the plugin directory. If a normal virtual environment cannot be created, setup writes a lightweight proxy instead (`.venv/pyvenv.cfg` plus `python.cmd` and `pip.cmd` wrappers) that points at the interpreter it detected.
4. **Python dependencies** — installs `requirements.txt` (`mcp`, `pydantic`, `pywin32`, `comtypes`, `jsonschema`) with pip. Already-installed dependencies are detected by import and skipped. Sources: by default the Tsinghua mirror with `pypi.org` as an extra index; `--aliyun` uses the Aliyun mirror; `--official` or `--no-mirror` uses no mirror at all. If a mirror install fails, setup retries against the default index. Optional extras (`requirements-optional.txt`) are installed only with `--optional` or `--full`.
5. **COM registration** — on Windows, verifies `import win32com.client, pythoncom`; if that fails it runs `pywin32_postinstall.py -install -silent` from the virtual environment or the interpreter directory, then verifies again.
6. **DSH registration** — if a DSH desktop profile exists, writes a `dsh-solidworks` entry into `<profile>/cordis.patch.yml`. Before writing it copies the existing file to `cordis.patch.yml.bak-dshsolidworks-<timestamp>`; if the write or the pre-activation check fails it restores that backup. The entry it writes uses mode `read-only` and `toolTimeoutMs: 300000`.

`setup` deliberately does **not** write `dsh-mcp-config.json` into the plugin directory: that file is for third-party MCP clients only, and generating it during setup would let tool calls bypass the plugin's policy layer. Use `npm run mcp-config -- --write-direct-config` if you explicitly want it.

## Install

```cmd
cd <the plugin directory>
npm run setup
npm run doctor
```

Options for `setup`:

| Flag | Effect |
| :--- | :--- |
| `--python <path>` | Use this interpreter instead of auto-detection |
| `--aliyun` | Install Python dependencies from the Aliyun mirror |
| `--official`, `--no-mirror` | Do not use any pip mirror |
| `--optional`, `--full` | Also install `requirements-optional.txt` (DXF, Office, imaging) |
| `--force` | Reinstall dependencies even if they already import |
| `--verify` | Run the doctor check at the end of setup |

If you installed the plugin from the DSH plugin catalogue, the package lives in your DSH profile and its scripts were not executed — run `npm run setup` from that package directory once, then restart DSH.

## Check that it worked

```cmd
npm run doctor
```

The report is JSON. The fields that matter:

| Field | Healthy value | Meaning |
| :--- | :--- | :--- |
| `ready` | `true` | The plugin can start its MCP server |
| `python.version` | `3.10`+ | Interpreter actually selected |
| `python.comDeps` | `true` | `comtypes` is importable; `false` means only `pywin32` is present and some COM features degrade |
| `server.script` | an existing `server.py` under `vendor/` | The MCP server that will be launched |
| `solidworks.installed` | `true` | SolidWorks found on this machine |
| `solidworks.version` | e.g. `2026` | Version read from the registry |
| `nextSteps` | advice | What to do next |
| `readyFull` | `true` | `ready` plus `python.comDeps`; `false` means COM-dependent tools may degrade even though the server starts |

Then start DSH, enable the plugin, and ask for a read-only operation — for example, list the tools or run a health check. Tools appear only after the plugin loads; a restart of DSH is required after registration.

To see whether your DSH profile really carries the plugin (bundle dependency, patch entry, configured mode and `pythonPath`), run:

```cmd
node bin/dsh-solidworks.js doctor --profile --json
```

An empty `issues` array means the profile looks consistent. `installedAsBundle: true` with `patchEntry: false` is normal for a catalogue install: the bundle ships its own patch.

`npm run doctor:cli` gives the same check through the plugin CLI; `node bin/dsh-solidworks.js list-tools --mode read-only --json` prints the tool list that the current mode publishes.

## If it fails

| Symptom | Go to |
| :--- | :--- |
| `setup` says no Python 3.10+ found | [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — Python section |
| pip install fails or times out | same document — network and mirror section |
| `comDeps: false` after setup | same document — pywin32/COM section |
| Plugin loads but tools are missing | same document — MCP startup section |
| SolidWorks is running but calls fail | same document — SolidWorks connection section |
| You need to point the plugin at a specific interpreter | [docs/ADVANCED-CONFIG.md](docs/ADVANCED-CONFIG.md) |

## Upgrade

```cmd
npm run upgrade
```

`upgrade` snapshots your configuration into `config-backups/`, verifies the plugin entry is intact, then refreshes dependencies and the COM registration. If the entry check or the dependency refresh fails, it copies the snapshot files back (a failed copy is swallowed silently, so check the printed list of restored files). The final doctor run is advisory: it does **not** roll back, and warnings do not stop the script — if doctor reports warnings the closing banner still follows doctor's exit code rather than the absence of warnings, so read doctor's own output. Nothing in your CAD documents is touched.

## Uninstall

```cmd
npm run uninstall -- --dry-run
npm run uninstall -- --yes
```

Starting `npm run uninstall` without `--yes` only prints what *would* be removed. The removal list is a fixed allow-list, not a recursive sweep of the plugin directory:

| Removed | Kept |
| :--- | :--- |
| `.venv` (the environment setup created) | Your CAD files (`*.SLDPRT`, `*.SLDASM`, `*.SLDDRW`) |
| `dsh-mcp-config.json` (if it exists) | `config-backups/` |
| `diagnostic-report.json` / `.md` (written by `npm run doctor`) | The plugin package itself |
| Sandbox leftovers from this repository's own tests (an old `测试代码/sandbox_benchmark/` folder, if present) | Other plugins' configuration |
| The `dsh-solidworks` entry in `cordis.patch.yml` (backed up first) | Registry, `PATH` and other system settings |

If the profile entry cannot be removed, the script prints the reason — the backup file `cordis.patch.yml.bak-dshsolidworks-<timestamp>` next to it can be copied back by hand.

## What setup never does

- It never writes project files outside the plugin directory, except the DSH desktop profile's `cordis.patch.yml` (backed up first) and pip's own cache.
- It **can** change the Windows registry, in one specific way: if `import win32com.client` fails, setup runs pywin32's own `pywin32_postinstall.py -install -silent`, which registers pywin32's COM entries under `HKCU`/`HKLM` and `HKEY_CLASSES_ROOT`. It does not touch other registry keys, and it never edits `PATH`, the PowerShell execution policy or system environment variables. When you install and the import already works (the common case on a machine that has used pywin32 before), no registry write happens.
- It never installs into, upgrades or deletes your system Python.
- It never runs with elevated privileges. The COM registration succeeds only if your account already has the rights to write the keys it needs; when it cannot, setup reports a warning instead of escalating.
- It never deletes CAD files, and it never runs a recursive delete of the plugin directory.
- The only network access is `pip` fetching the dependencies listed in `requirements.txt`.