# Verification record

What has actually been run for **v0.3.3** (targeted re-verification) and inherited from **v0.3.2** (full 71-tool baseline), on what machine, and what has not been run at all.
Every claim here maps to a command you can re-run; v0.3.3 targeted fixes are explicitly separated from the
v0.3.2 full-matrix baseline below. If a line says *not verified*, treat the corresponding capability as unknown.

The plugin registers **71 tools** (plus two DSH host meta-tools that the host adds: `solidworks_status`
and `solidworks_confirm`). The tool count is asserted by `tests/package.test.js` against
`lib/policy.js`'s `RISK_TABLE`, so this page cannot drift from the code.

- Verification date: 2026-11-25 (v0.3.3 targeted L4 + offline suites; v0.3.2 full L4 baseline recorded 2026-11-18)
- Plugin version: 0.3.3 (`package.json`, branch `feat/v0.3.3-remediation`)
- Platform: Windows 11 x64, Node.js v24.21.0, DSH 0.1.7-rc.2
- Python used for offline & v0.3.3 targeted runs: local 64-bit Python 3.13 (`mcp`, `pywin32`, `comtypes`, `pydantic`, `jsonschema`); v0.3.2 baseline used DSH bundled runtime 3.12.14
- SolidWorks: 2026 SP04.1, COM revision 34.4.1

Verification levels used below: **L1** environment, **L2** MCP server, **L3** DSH host,
**L4** real SolidWorks.

## 1. Summary

| Area | Result | Evidence |
| :--- | :--- | :--- |
| L1 environment | PASS on this machine | §2, `audit/promotion-phase/01-current-state-audit/evidence/env-baseline.txt` |
| L2 MCP server (handshake, tool list, schema, errors) | PASS | §3, `npm run test:all` |
| L3 DSH host (bundle load, tool publication, read-only gate) | PASS for load and gating; GUI approval not exercised | §3, `tests/cordis_activation_test.mjs`, `tests/r5-…` |
| L4 real SolidWorks | v0.3.2 full baseline: 71/71 tools reached (**33 `verified` (7 partial)**, 13 `failed`, 24 `blocked`, 1 `known-limitation`, 14 defects); v0.3.3 targeted re-test: D-01, D-02, D-03a, D-04, coincident mate & BOM PASS | §4, §4.4, `audit/v033-targeted-l4/l4-results.json` |
| Offline automated suites | PASS — 20 top-level suites, 204 assertions; 45 Python suites, 341 cases | §3 |
| SolidWorks 2020–2025 | **not verified** | §5 |

## 2. L1 — environment

| Check | Observed |
| :--- | :--- |
| OS / architecture | Windows 11 x64 |
| Node.js | v24.21.0 (engine floor is `>=22.12`) |
| npm | 11.19.0 |
| DSH CLI | 0.1.7-rc.2 (engine floor is `>=0.1.7-rc.2`) |
| Python | DSH bundled runtime 3.12.14; `pywin32` and `mcp` importable; `comtypes` **absent** |
| SolidWorks | installed desktop SolidWorks 2026, COM revision 34.4.1 |
| Plugin self-check | `node bin/dsh-solidworks.js doctor --json` → `ready: true`, `readiness.full: false` (missing COM extras) |

`comtypes` is optional: without it the COM-backed tools still run through `pywin32`, but the
tools that declare a COM type-library dependency report the gap instead of silently degrading.
`doctor` reports this as `readiness.core` = true / `readiness.full` = false; see
[ADVANCED-CONFIG.md](ADVANCED-CONFIG.md).

## 3. L2 / L3 — MCP server and DSH host

Offline suites, no SolidWorks session required. Runner: `npm run test:all`
(`scripts/run_test_all.mjs`), which also aggregates the Python suites.

| Suite | Assertions | What it covers |
| :--- | ---: | :--- |
| `tests/policy.test.js` | 30 | risk table, mode gating, approval binding, refusals |
| `tests/mcp.test.js` | 17 | MCP handshake, tool registration, schema shape |
| `tests/schema.test.js` | 26 | input/output schema conformance for the registered tools |
| `tests/package.test.js` | 12 | tarball contents, docs/product parity, path-leak and provenance guards |
| `tests/audit.test.js` | 30 | audit log writing, redaction, failure modes |
| `tests/host.test.js` | 39 | DSH host integration, config resolution, discovery |
| `tests/crash.test.js` | 9 | crash and restart recovery paths |
| `tests/audit_outcome.test.js` | 8 | audit records for accepted / refused / failed calls |
| `tests/dsh_adapter_scripts.test.js` | 6 | profile patch merging (user keys preserved), bundle-mode guard, unregister scoping |

Runner accounting: **Total **204 assertions** across 20 top-level suites** — 9 `*.test.js`
suites above, 10 `*.mjs` suites (`approval_security_adversarial_test.mjs`,
`cordis_activation_test.mjs`, `cordis_service_registration_test.mjs`,
`d02_d12_d13_config_and_discovery_test.mjs`, `r1_r5_security_matrix_test.mjs`,
`runtime_isolation_test.mjs`, `phase5_security_approval_test.js`,
`confirm_human_authorization_test.js`, `phase3_productization_test.js`, plus `release-swarm`),
and one aggregator suite (`python-all`) that runs the Python suites below.

Python suites (`scripts/run_all_python_tests.py`): **45 suites, 341 unittest cases, 0 skipped,
0 failed**. They cover the vendored engine's pure-logic paths, path security, job state machine,
dimension pipeline, tool-registry integrity (`tests/tool_registry_integrity_test.py`, which fails if
a decorator is bound to the wrong function), v0.3.3 defect regression guards (`tests/v033_remediation_test.py`), and the fake-COM layer. A pass here means *the Python
code behaves as specified against fakes*; it is not evidence about SolidWorks.

Mock-only coverage is labelled as such: `tests/_fake_sw_com.py` implements the COM surface used by
the offline suites. Any behaviour that depends on the real API is listed in §4 or §5, never in this table.

## 4. L4 — real SolidWorks 2026 SP4.1

Full report, per-tool evidence and defect reproductions:
`audit/promotion-phase/04-regression-validation/l4-real-solidworks.md`. Raw calls:
`audit/promotion-phase/04-regression-validation/evidence/l4-calls.jsonl` (206 calls).
Tool-by-tool status: [FEATURE_MATRIX.md](FEATURE_MATRIX.md).

Method: SolidWorks was started by the auditor outside MCP; the server only attached. All side
effects were written under `audit/promotion-phase/04-regression-validation/solidworks-workspace/`,
which was the only allowed root. At teardown the session called `CloseAllDocuments(false)` and
then `ExitApp()`, and no `SLDWORKS` process remained. Note the exact evidence:
`evidence/teardown.log` records 7 documents open before teardown and `documents_remaining: 4`
after it — the session did not get every document closed before exit, so treat "clean document
state at teardown" as a known limitation, not as a clean shutdown.

| Verdict | Count | Meaning |
| :--- | ---: | :--- |
| `verified` | 33 | call reached real COM and returned a self-consistent result; **7 of these are marked *partial*** because one specific enum value or field still fails (`solidworks_connect`, `solidworks_interference_check`, `solidworks_open_document`, `solidworks_export_active`, `solidworks_identify_dimensions`, `solidworks_review_active`, `solidworks_inspect_hole_features`) |
| `failed` | 13 | calling the tool the documented way fails, or returns a misleading success |
| `blocked` | 24 | the environment could not satisfy the tool's preconditions (no solver, no OCP backend, no DXF source, document ownership); **this is not proof that the tool is broken** |
| `known-limitation` | 1 | `solidworks_recover` never probes COM (`status=not_checked`) |

### 4.1 Defects found on real hardware (v0.3.2 baseline & v0.3.3 status)

| ID | Severity | Summary | Status in v0.3.3 |
| :--- | :--- | :--- | :--- |
| D-01 | blocking | MCP cannot cold-start SolidWorks (`SW_LAUNCH_PROHIBITED`) — contradicts "connect or start one" | **Fixed & targeted re-verified (v0.3.3)**: `read-only` refuses cold start; CLI `--mode standard` & `health_check(start_solidworks=true)` cold-start SW 2026 (`34.4.1`) |
| D-02 | blocking | `solidworks_open_document` does not make the opened document the ActiveDoc → later tools act on the wrong document | **Fixed & targeted re-verified (v0.3.3)**: `open_document()` calls `ActivateDoc3` + verifies `ActiveDoc` across `part_a` (`8000 mm³`), `part_b` (`27000 mm³`), `asm_test` |
| D-03 | blocking | document-ownership model breaks long sessions: assembly components are not registered, ownership is per-process, so a legitimate follow-up call is refused | **D-03a fixed & re-verified (v0.3.3)** (component registration + assembly reactivation); **D-03b** (cross-process CLI ledger) deferred to v0.4.0 |
| D-04 | blocking | `solidworks_shell` reports failure after the geometry was already changed (64000 → 17344 mm³) | **Fixed & targeted re-verified (v0.3.3)**: handles `VT_VOID` (`None`) via rebuild + feature-tree diff; `2 mm` succeeds (`17344 mm³`, `抽壳1`), `50 mm` refuses (`64000 mm³`, `feature_created=false`) |
| D-05 | high | `solidworks_list_edges` returns `ok` with `null` geometry fields | Open (deferred to v0.4.0) |
| D-06 | high | `solidworks_chamfer` dry-run passes but apply always fails | Open (deferred to v0.4.0) |
| D-07 | high | `solidworks_pattern` fails on revolved bodies | Open (deferred to v0.4.0) |
| D-08 | high | `solidworks_add_coincident_mate` has a wire contract incompatible with the other 70 tools | **Decorator fixed (Stage 3) & real-SW re-verified (v0.3.3)**: Top Plane coincident mate passes (`mate_created=true`) |
| D-09 | high | spec-driven tools reject `schema_version` and ship no usable template | Open (deferred to v0.4.0) |
| D-10 | medium | `solidworks_export_active` PDF path raises `AttributeError` | Open (deferred to v0.4.0) |
| D-11 | medium | empty-document false positives (`interference_check` passes, `review_active` scores 92) | Open (deferred to v0.4.0) |
| D-12 | medium | feature type / through-state mapping errors | Open (deferred to v0.4.0) |
| D-13 | medium | `solidworks_pack_and_go` dependency enumeration is always incomplete | Open (deferred to v0.4.0) |
| D-14 | medium | native-wire import tools require a target that already exists and is active → unusable for imports | Open (deferred to v0.4.0) |

### 4.2 What L4 did establish

Parameter-driven part modelling (new document, extrude, cut, fillet, mirror, hole, dimension
edits, configurations, custom properties, save/reopen), measurement (mass properties and bounding
box matched analytic values: 70497.339 mm³ and 1512.0 = 1000 + 512), STEP/STL export (17083 /
55036 / 373684 bytes), assembly component insertion and distance mates, and native geometry readback.

### 4.3 Policy gate behaviour

The gate is real and fails closed on the CLI path: a high-risk tool in `standard` mode is refused,
and in `full` mode without host approval the CLI exits 3; `--yes` / `--allow` do not bypass it.
The gate is **not** in the path of a direct MCP stdio connection — 206 of the v0.3.2 L4 calls were made that
way. The plugin's protection exists only when it is loaded as a DSH plugin. This is disclosed in
[SECURITY.md](../SECURITY.md) and [docs/ADVANCED-CONFIG.md](ADVANCED-CONFIG.md).

### 4.4 v0.3.3 Targeted Real SolidWorks 2026 SP4.1 Re-verification (2026-11-25)

Scope: Targeted re-test ONLY covering D-01, D-02, D-03a (+ D-08 / BOM), and D-04 in isolated sandbox
`audit/v033-targeted-l4/solidworks-workspace/` via `node audit/v033-targeted-l4/run_targeted_l4.mjs`
(results recorded in `audit/v033-targeted-l4/l4-results.json`). The remaining tools from the 71-tool
registry keep their inherited v0.3.2 baseline status above and were NOT re-run in full.

| Targeted Case | Measured Real-Hardware Outcome (SolidWorks 2026 SP4.1, rev `34.4.1`) |
| :--- | :--- |
| D-01 CLI & MCP cold start | `solidworks_connect --mode read-only` refused (`NOT_PUBLISHED`), `--mode read-only --allow solidworks_connect` refused cold launch (`0` `SLDWORKS` processes); `--mode standard` launched SolidWorks (`rev 34.4.1`); `solidworks_health_check(start_solidworks=true)` returned `ok` |
| D-04 `solidworks_shell` | `40×40×40` box (`64000 mm³`) + `thickness_mm=2.0` → `status="ok"`, `feature_created=true`, `feature_name="抽壳1"`, volume `17344 mm³`; invalid `thickness_mm=50.0` → `status="error"`, `feature_created=false`, volume unchanged at `64000 mm³` (note: intermediate `25 mm` closed shell on a `40 mm` box produces an inverted SolidWorks internal offset cavity of `63000 mm³` with no COM error, so `50 mm > 40 mm` was used for impossible geometry) |
| D-02 `solidworks_open_document` | With `part_a` (`20×20×20`), `part_b` (`30×30×30`), and `asm_test.SLDASM` simultaneously open: opening `part_a` switched `ActiveDoc` (`solidworks_mass_properties` reported `8000 mm³`); opening `part_b` reported `27000 mm³`; opening `asm_test.SLDASM` restored assembly focus |
| D-03a / D-08 Assembly chain | Added `part_a` + `part_b` into `asm_test.SLDASM`, created `solidworks_add_distance_mate` (`50 mm`) and `solidworks_add_coincident_mate` (`Top Plane`, `mate_created=true`); follow-up `solidworks_mass_properties` ran on `asm_test.SLDASM` (`35000 mm³`, zero `DEF-SEC-01`) and `solidworks_export_assembly_bom` exported 2 rows (`success=true`, `row_count=2`) |
| Clean teardown | `CloseAllDocuments(False)` + `ExitApp()`, verified `teardownPids=[]` (`0` remaining `SLDWORKS` processes) |

## 5. Not verified (do not treat as working)

| Item | Status | Why |
| :--- | :--- | :--- |
| SolidWorks 2020–2025 | not verified | no real-machine evidence; no version gate in code |
| Educational / student / network licences | not verified | only a commercial-style install was exercised |
| DSH GUI approval dialog (real click path) | not verified | approval is exercised through stubs and the CLI; the desktop UI was not driven |
| Drawing generation / review / inspection | blocked | requires an existing `.SLDDRW`; spec layer rejects `schema_version` (D-09) |
| FEA, DFM, routing, OCP loft/surface | blocked | no solver / OCP backend on this machine; request templates unavailable |
| Motion studies, rotary motor | blocked | `comtypes` + Motion type library absent, and assembly never becomes ActiveDoc (D-02) |
| BOM / pack-and-go / concentric mate | partial in v0.3.3 | `solidworks_export_assembly_bom` and `solidworks_add_coincident_mate` passed in v0.3.3 targeted run; `pack-and-go` (D-13) and `concentric mate` still not passed / re-tested |
| STEP import | failed | D-14 |
| Feature graph compile/execute | failed | malformed input raises an uncaught `AttributeError` |
| Marketplace installation path end-to-end | not verified | the catalogue entry now serves v0.3.2 (update PR merged 2026-11-17), but no install has been run through the marketplace UI; the local desktop profile is a `file:` install |

## 6. How to reproduce

```bash
# offline suites (no SolidWorks needed)
npm run test:all

# environment / readiness
node bin/dsh-solidworks.js doctor --json
node bin/dsh-solidworks.js doctor --profile --json

# tool list the current mode publishes
node bin/dsh-solidworks.js list-tools --mode read-only --json
node bin/dsh-solidworks.js list-tools --mode full --json
```

The L4 session is reproducible with the scripts in
`audit/promotion-phase/04-regression-validation/tools/` (see that report's §7). It needs an
installed SolidWorks and writes only inside its own workspace directory.

## 7. Legacy record

The previous verification log (an MCP-layer evidence journal from the 66-tool era) is kept
unchanged at [docs/archive/verification-2026-11-17-legacy.md](archive/verification-2026-11-17-legacy.md).
It describes an older tool set and must not be quoted as current evidence.