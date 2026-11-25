# Security policy

Chinese version: [SECURITY.zh.md](docs/SECURITY.zh.md)

This document describes what `dsh-solidworks` does and does not protect against,
which controls are actually implemented, and how to report a problem. It is
written to be checkable against the source; if a statement here and the code
disagree, the code wins and the document is a bug.

## Supported versions

| Version | Security support | Notes |
| --- | --- | --- |
| 0.3.2 | Supported — fixes land here | Current release; the controls and limitations below refer to it |
| 0.3.1, 0.3.0 | No commitment | Older releases; no backports are promised |
| Earlier than 0.3.0 | Unsupported | Please upgrade to 0.3.2 first |

## How to report a vulnerability

Please use GitHub's private vulnerability reporting: open the repository on
GitHub, go to **Security** and choose **Report a vulnerability** (private
vulnerability reporting). That keeps the details out of public view while a fix
is prepared.

If that entry point is not available in your GitHub settings or on this
repository, do **not** paste exploit details, private CAD files, licence keys or
tokens into a public issue. Instead open a normal issue that says only that you
have a security-relevant finding and ask for a private channel; the maintainer
will follow up with a way to share the details.

A useful report contains: plugin version, DSH version, Windows version,
SolidWorks version and service pack, the configured mode, the tool name, whether
the behaviour was seen on a real session or against mocks, the expected and
actual behaviour, and a minimal reproduction. Redact paths, user names and
business data first. Please test only against your own installation — do not run
attacks against other people's machines or CAD files.

This is a single hobby maintainer, so no fixed response time is promised. See
the disclosure policy below.

## Threat model and boundaries

The plugin is designed to stop an AI agent from doing CAD operations the human
did not intend, within the limits of a local desktop tool. It is not designed to
resist an attacker who already controls the machine.

Trust assumptions:

- The local machine and its SolidWorks installation are trusted, including the
  Python runtime and the COM registration that `npm run setup` performs.
- The plugin runs as the invoking user and has the same file and COM privileges.
- The human at the DSH approval prompt is the decision maker; the plugin cannot
  make that decision for them.
- The DSH host is trusted. It can spawn processes and read files regardless of
  this plugin.

| In scope | Out of scope |
| --- | --- |
| A tool call being published or executed outside the configured mode | A local administrator or root-level attacker on the same machine |
| A HIGH-risk tool executing without host approval, or the plugin approving itself | Compromise of SolidWorks itself, its COM API or its licence system |
| File access escaping the configured `allowedRoots` list | Malicious Python packages the user installs outside `npm run setup` |
| Policy logic failing open when the approval channel is missing | The AI model's judgement about which operation is desirable |
| Audit output claiming something that did not happen | Denial of service through a very large or slow CAD operation |

Three boundaries are worth stating plainly, because they are easy to
misunderstand:

- The plugin does not sandbox the SolidWorks process. A modelling call runs with
  all the privileges of the user's SolidWorks session.
- The policy layer lives inside the plugin. A client configured through the
  direct-MCP configuration that `npm run mcp-config` can emit talks to the Python
  server without the plugin's policy, approval or audit code in the path. That
  configuration is documented as a debugging aid only.
- An approval binds a tool name, a digest of the arguments and the session, with
  a time limit. It is a human click on a specific call, not a code review, and
  it cannot tell whether the resulting geometry is the one the user wanted.

## Security controls that are actually implemented

| Control | What it does | Where it lives |
| --- | --- | --- |
| Three policy modes: `read-only`, `standard`, `full` | `read-only` publishes only the 19 read-only tools out of 71; `standard` publishes 45; `full` publishes all 71. Withheld tools are absent from the tool list, not merely refused at call time | `lib/policy.js` |
| Risk table with three tiers: READ, WRITE, HIGH | Tools not in the table deliberately default to HIGH, so an unclassified new tool is treated as dangerous | `lib/policy.js:21-23`, `lib/policy.js:126-131` |
| HIGH-risk tools require DSH host approval | The grant is bound to the tool name, a digest of the arguments and the session, with a TTL; without an approval channel the call fails with `APPROVAL_CHANNEL_UNAVAILABLE` instead of proceeding | `lib/index.js`, `lib/policy.js` |
| Self-approval is prohibited | `solidworks_confirm`, a DSH host meta-tool rather than one of the 71 server tools, always returns `SELF_APPROVAL_PROHIBITED`; the CLI has no approve or reject command, so a tool or a script cannot grant itself permission | `lib/index.js:334`, `lib/index.js:341` |
| Path allow-list `allowedRoots` | When the list is non-empty, path arguments outside it are refused; an empty list falls back to the session working directory | `lib/policy.js:454` |
| Optional audit log | When `auditLog` is configured, policy decisions, approvals and calls are appended as JSONL; if the file is not writable the plugin keeps up to 1000 entries in memory, raises a stderr error and exposes failure counters through `solidworks_status`, which is also a host meta-tool | `lib/policy.js:150` |

The refusal codes below are the ones a report should quote verbatim; they are
stable enough to search for in the source and in the troubleshooting guide:

```text
POLICY_MODE
CONFIRMATION_REQUIRED
APPROVAL_CHANNEL_UNAVAILABLE
PATH_OUTSIDE_ALLOWED_ROOTS
SELF_APPROVAL_PROHIBITED
```

## Known limitations and non-goals

- The SolidWorks process is not sandboxed. Any file, registry or COM action the
  SolidWorks session can perform is available to a call that the policy allows.
- The plugin does not audit every API call. It logs plugin-level policy events
  and tool calls, and only when `auditLog` is configured; SolidWorks' own COM
  activity and anything the Python server does internally are outside that log.
- It cannot prevent wrong geometry. A well-formed call that produces an
  undesirable shape is allowed by design; work on copies of important documents.
- The policy and approval layers apply only to calls routed through the plugin.
  The direct-MCP configuration bypasses them, as described in
  [docs/ADVANCED-CONFIG.md](docs/ADVANCED-CONFIG.md).
- Shadow backups cover the dimension-modification path only. Other edits do not
  get an automatic shadow copy.
- An approval is a click with a TTL, not an intent check. A human can approve an
  operation that is not what they meant, and the plugin cannot detect that.
- No release-signing or signature-verification code exists in this repository.
  Installing or upgrading trusts the npm package and the pinned vendor snapshot;
  there is no cryptographic check of the Python server before it starts.
- A local administrator-level attacker is out of scope: they can replace the
  plugin files, the Python runtime or the audit log itself.
- SolidWorks 2020–2025 is nominally supported but unverified; the only real
  machine combination exercised is Windows with SolidWorks 2026 SP4.1. See
  [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for the errors that follow
  from that gap. Linux and macOS are not supported at all.

## Dependency and supply-chain notes

- Python dependencies are installed from PyPI by `npm run setup` (and re-checked
  by `npm run upgrade`). The setup script uses a mirror by default — Tsinghua
  University, with `pypi.org` as a fallback — and `--official` turns the mirror
  off. Installing dependencies is the only network access the project performs;
  the plugin and the MCP server otherwise run locally over stdio.
- The plugin itself has no npm runtime dependencies. It runs on the DSH host's
  own runtime, which is why Node.js 22.12+ and DSH 0.1.7-rc.2+ are required.
- `vendor/solidworks-automation-skill/` is a snapshot of an MIT-licensed
  upstream project at commit `d8b9547` (193 files) with local security patches
  applied; the MIT licence text and provenance are recorded in [NOTICE](NOTICE).
  Treat it as third-party code: review vendor changes as vendor changes.
- No compiled binaries are tracked in the repository — no `.exe`, `.dll` or
  `.pyd` files. SolidWorks itself is never redistributed; the plugin only uses a
  SolidWorks installation that already exists on the machine.
- If you install the plugin from a marketplace or a git checkout, the plugin
  version and the DSH version are the two values worth recording in any report.

## Disclosure policy

- Please report privately first and give the maintainer a chance to fix the
  issue before publishing details.
- This project offers no bug bounty and no payment of any kind.
- There is no SLA and no promised response or fix time. It is a single
  maintainer working in spare time, and a report may sit for a while.
- The maintainer will aim to confirm the report, prepare a fix in the current
  release line, and publish a short note in the changelog or a GitHub security
  advisory when a fix ships. Credit is given on request.
- Reports that turn out to be documented limitations (for example an approval
  being a click rather than a review) will be answered with an explanation
  rather than a fix.

## Related documents

| Document | Why read it |
| --- | --- |
| [README.md](README.md) | Feature surface, mode table and current verification status |
| [INSTALL.md](INSTALL.md) | What setup writes, and what it deliberately never touches |
| [docs/ADVANCED-CONFIG.md](docs/ADVANCED-CONFIG.md) | Every policy, approval and audit configuration key |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | What each refusal code means in practice |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Which changes are accepted, including changes to the policy layer |
| [SUPPORT.md](SUPPORT.md) | Where to ask non-security questions |
| [NOTICE](NOTICE) | Third-party provenance for the vendored snapshot |
| [LICENSE](LICENSE) | AGPL-3.0-only terms for this project |