# Contributing to dsh-solidworks

Chinese version: [CONTRIBUTING.zh.md](docs/CONTRIBUTING.zh.md)

Thanks for considering a contribution. This project is a small, single-maintainer
plugin, so the rules below are mostly about keeping claims honest and keeping the
review load manageable. Please read them before opening a pull request.

## What this project is — and what it is not

`dsh-solidworks` connects DeepSeek Harness (DSH) to a local SolidWorks desktop.
The repository contains two halves: a DSH plugin that registers CAD tools through
the `dsh-mcp-client` contract and enforces a policy layer (modes, risk tiers,
path allow-list, host approvals, optional audit log), and a Python MCP server
under `vendor/solidworks-automation-skill/` that performs the actual COM calls on
Windows. Everything runs locally over stdio; the only network access in the
project is the pip install that `npm run setup` performs.

| This repository is | This repository is not |
| --- | --- |
| A DSH plugin plus a local stdio MCP server | A CAD kernel or a geometry engine |
| A policy, approval and audit wrapper around SolidWorks COM calls | A sandbox for the SolidWorks process |
| An installer that pulls Python dependencies from PyPI at setup time | A redistributor of SolidWorks or of compiled CAD binaries |
| A tool surface whose publication depends on the configured mode | A replacement for the SolidWorks user interface |

Every geometric operation is delegated to SolidWorks through its own API. Errors
in geometry are usually SolidWorks behaviour or a wrong call sequence, not
something this repository recomputes. If you want to change how a fillet or a
sweep is calculated, that change belongs in SolidWorks, not here.

## Ways to contribute

Five kinds of contribution are genuinely useful. Pick the one that matches what
you can actually verify.

### 1. Report a reproducible defect

Use the [bug report template](.github/ISSUE_TEMPLATE/01-bug-report.yml). The
report is only actionable when it says which plugin version, DSH version and mode
were used, which tool name was called, and what the exact error text was
(for example `POLICY_MODE`, `CONFIRMATION_REQUIRED` or
`APPROVAL_CHANNEL_UNAVAILABLE`). State whether the failure was seen on a real
SolidWorks session or against mocks; the template asks for this explicitly and
the maintainer relies on the answer.

### 2. Submit a real SolidWorks validation report

Use the [validation report template](.github/ISSUE_TEMPLATE/03-real-solidworks-validation.yml).
This is the most valuable contribution for versions other than the one that has
been exercised on real hardware: Windows with SolidWorks 2026 SP4.1. SolidWorks
2020–2025 is listed as nominally compatible but has no version gate in code and
has not been verified. A report that a specific tool fails on your version is
useful evidence, not a complaint, and it is the only way the compatibility table
can ever grow.

### 3. Improve the documentation

Documentation fixes are welcome and cheap to review. Two conditions: change the
English file and its Chinese mirror in the same pull request, and keep every
claim traceable to the code or to [docs/verification.md](docs/verification.md).
Every relative link you add must resolve in the repository — broken links are
treated as a defect. If a documented error code no longer matches the code, that
is a bug report, not a style issue.

### 4. Add or repair tests

`npm test` runs four offline Node suites (policy, MCP, schema, package).
`npm run test:all` adds the Python-linked suites and reports each one as PASS,
FAIL, BLOCKED or SKIPPED. Keep new tests offline by default: no test may require
a running SolidWorks instance or network access. Tests that use mocked COM
objects are welcome, but they must be named and commented as mocks and must
never be described as real SolidWorks verification. A new tool needs at least a
registry and publication test; the registry itself is guarded by
`tests/tool_registry_integrity_test.py`.

### 5. Propose code

Open an issue first and describe the scope — what changes, what stays, and how
you intend to verify it. Small pull requests that do one thing are reviewed
faster than large ones. Changes that touch the policy layer, risk classification
or approval path get closer scrutiny, because those are the parts users rely on
to prevent writes they did not ask for. If you are unsure whether a change is in
scope, ask before writing the code.

## Development setup

You need Node.js 22.12 or newer and, for the Python half, Python 3.10+ (64-bit).
`npm run setup` creates a plugin-local `.venv` and installs the Python
requirements from PyPI; it does not touch a system Python, the registry, PATH or
environment variables, and it never needs elevation.

```bash
git clone https://github.com/tan000tan/dsh-solidworks.git
cd dsh-solidworks
npm run setup
npm test
npm run test:all
node bin/dsh-solidworks.js doctor
```

If you only touch JavaScript or Markdown, `npm test` runs from a clean clone;
`npm run setup` is only needed for the Python server and for `npm run test:all`.

| Command | What it does | Needs Python |
| --- | --- | --- |
| `npm run setup` | Creates the plugin-local `.venv`, installs Python requirements, registers the plugin in the DSH profile | Yes |
| `npm test` | Runs the four offline Node suites (policy, MCP, schema, package) | No |
| `npm run test:all` | Runs the full suite list, including the Python and approval-path suites | Yes |
| `node bin/dsh-solidworks.js doctor` | Read-only health report; `--json` prints without writing report files | No |

The `.venv` directory is plugin-local and can be a few hundred MB. To remove it,
run `npm run uninstall -- --dry-run` first and then `npm run uninstall -- --yes`;
the uninstall allow-list removes `.venv`, `dsh-mcp-config.json` and
`diagnostic-report.*` while keeping your CAD files and config backups. Never
commit `.venv`, `node_modules`, `dsh-mcp-config.json` or report files generated
on your own machine. The direct-MCP configuration produced by `npm run mcp-config`
is a debugging aid and bypasses the plugin policy layer, so it does not belong in
a pull request either.

The registry test is a Python test, not a Node test, and is run like this:

```bash
# Windows layout, when setup created the plugin-local venv
.venv/Scripts/python.exe -B tests/tool_registry_integrity_test.py
```

## Coding rules

These are checkable rules, not preferences. A pull request that breaks one of
them will be sent back.

1. **Never present mock results as real SolidWorks verification.** The four
   verification levels are described below; use the one that is true.
2. **Register a new tool everywhere.** A new tool must update
   `docs/locale/en.json` and `docs/locale/zh.json`, `dsh-plugin.json` (tool
   count, namespaces and summary text) and [docs/FEATURE_MATRIX.md](docs/FEATURE_MATRIX.md)
   in the same pull request. A tool that appears in one place only is a defect.
3. **Risk tiers may go up, not down.** Do not lower a tool's classification to
   make an approval prompt disappear. Unknown tools deliberately default to
   HIGH; that default is a security decision, not an oversight.
4. **`read-only` must never publish a write tool.** Publication is decided by the
   policy layer, not by documentation. Under the default mode only 19 of the 71
   tools are published; a write tool showing up in that list is a policy bug.
5. **Every tool name needs a test, or an explicit `unverified` marker** in
   [docs/FEATURE_MATRIX.md](docs/FEATURE_MATRIX.md). "Unverified" is an honest
   status, not a failure — silently upgrading it later is a failure.
6. **Change both languages in one pull request.** The English and Chinese files
   must keep the same section order, table shapes and link set.
7. **Run the checks before pushing.** `npm test` and
   `tests/tool_registry_integrity_test.py` must pass. If a Python suite reports
   BLOCKED or SKIPPED on your machine, say so in the pull request instead of
   hiding it or marking it as passing.
8. **No personal data in committed logs.** Strip user names, absolute paths,
   machine names, licence keys and tokens from doctor output, audit JSONL,
   screenshots and test fixtures.

## Commit and pull-request conventions

| Topic | Convention |
| --- | --- |
| Commit subject | Imperative mood, short: `add shell tool test`, not `Added the test`. |
| Scope | One pull request does one thing. No drive-by refactors or reformatting. |
| Verification level | State one of `automated`, `mock`, `real-SolidWorks` or `unverified` in the pull request body. |
| Evidence | Paste or link the test output, `doctor --json` excerpt or audit lines that show the claim. Redact first. |
| Documentation | English and Chinese together; tool changes also update the locale files and the matrix. |
| CI | The repository has no `.github/workflows`, so run the suites locally and paste the result. |

Use these levels consistently — they are what a reviewer reads first:

| Level | What it means | Evidence to attach |
| --- | --- | --- |
| `automated` | A test in this repository exercises the path with no SolidWorks involved | Test file name and a passing run |
| `mock` | Exercised against mocked COM objects or a fake MCP client | Mock test path, clearly labelled as a mock |
| `real-SolidWorks` | Exercised against a live SolidWorks session on Windows | SolidWorks version, service pack, edition, document description, tool and outcome |
| `unverified` | Not exercised anywhere | Say so plainly; do not reword it as "tested" later |

## Review and merge

This is a single-maintainer, spare-time project. There is no promised response
time and no promised merge timeline. The maintainer may ask for more evidence,
may ask you to split a pull request, and may decline a change that widens the
tool surface without a clear verification story. A review comment is about the
change, not about you. If a pull request goes quiet for a long time, a polite
ping on the issue is fine.

## Licensing of contributions

The project is licensed under AGPL-3.0-only (see [LICENSE](LICENSE)). By opening
a pull request you agree that your contribution is licensed under the same terms.
The repository contains no separate contributor licence agreement document.

`vendor/solidworks-automation-skill/` is a snapshot of an MIT-licensed upstream
project (commit `d8b9547`, 193 files) with local security patches; see
[NOTICE](NOTICE) and the MIT licence text inside that directory. Changes inside
`vendor/` must state the upstream source and the reason for the change in the
pull request, and must keep the MIT notices intact. Do not paste code of unknown
or incompatible licence into the tree.

## What will be rejected

- Fabricated verification: screenshots, logs or claims that no run produced.
- Overstated compatibility: presenting SolidWorks 2020–2025 as verified, or
  claiming Linux/macOS support, when only Windows with SolidWorks 2026 SP4.1 has
  been exercised on real hardware.
- Approval bypasses: lowering a risk tier, allowing self-approval, publishing
  write tools in `read-only` mode, or making the approval path fail open.
- Removing or neutering the audit log, its failure counters, or the fallback that
  keeps audit entries in memory when the log file is not writable.
- Committing binary artifacts. The repository tracks no `.exe`, `.dll` or `.pyd`
  files, and that is intentional.
- Marketing language or unverifiable promises in documentation.
- Pull requests that mix unrelated changes, or that update only one language.
- Secrets, personal data or proprietary CAD files in any form.

## Related documents

| Document | Why read it |
| --- | --- |
| [README.md](README.md) | What the plugin does, the tool count and the current verification status |
| [INSTALL.md](INSTALL.md) | Install, upgrade and uninstall behaviour, including what setup never touches |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Error codes and the fixes that actually apply to them |
| [docs/ADVANCED-CONFIG.md](docs/ADVANCED-CONFIG.md) | Every configuration key, mode semantics and audit log behaviour |
| [docs/FEATURE_MATRIX.md](docs/FEATURE_MATRIX.md) | Per-tool status, including which tools are unverified |
| [docs/verification.md](docs/verification.md) | The evidence record; only listed evidence counts |
| [SECURITY.md](SECURITY.md) | Threat model, implemented controls and how to report a vulnerability |
| [SUPPORT.md](SUPPORT.md) | Where to ask, what to include and what is out of scope |