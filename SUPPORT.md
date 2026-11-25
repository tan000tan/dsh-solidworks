# Support

Chinese version: [SUPPORT.zh.md](docs/SUPPORT.zh.md)

This page explains how to get help with `dsh-solidworks` without wasting your
time. The project is maintained by one person in spare time, so the fastest path
is usually a report that already contains the evidence the maintainer would ask
for.

## Before you ask

Work through these five steps in order. Most questions are answered by one of
them.

1. Read [INSTALL.md](INSTALL.md). It covers the setup steps, the Python
   detection order, the flags for mirrors and optional packages, and what setup
   deliberately never touches.
2. Run the read-only health check and keep its output:
   `node bin/dsh-solidworks.js doctor --json`. It reports Python, COM
   dependencies, the server script and the SolidWorks installation, and it
   writes no report files in `--json` mode.
3. Search [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) for the exact error
   code or message. Codes such as `POLICY_MODE`, `CONFIRMATION_REQUIRED`,
   `APPROVAL_CHANNEL_UNAVAILABLE` or `PYTHON_INVALID` have a specific meaning
   and a specific fix.
4. Search the existing issues, open and closed. A closed issue often contains the
   workaround, and duplicates are usually closed quickly.
5. If none of that helps, open an issue with the matching template below and
   include the details listed in "What to include".

```bash
node bin/dsh-solidworks.js doctor --json
node bin/dsh-solidworks.js list-tools --mode read-only
```

## Where to ask

The issue tracker is the only support channel. There is no chat server, no
mailing list and no published maintainer email, so please do not look for one.
Security reports do not go to the public tracker — use the process in
[SECURITY.md](SECURITY.md).

  Template   Use it when   Required evidence  
  ---   ---   ---  
  [Bug report](https://github.com/tan000tan/dsh-solidworks/blob/main/.github/ISSUE_TEMPLATE/01-bug-report.yml)   A tool or the runtime misbehaves in a mode you can name   Plugin version, DSH version, mode, tool name, exact error, expected vs actual, steps  
  [Installation problem](https://github.com/tan000tan/dsh-solidworks/blob/main/.github/ISSUE_TEMPLATE/02-installation-problem.yml)   Setup, Python detection, COM registration or DSH registration fails   Full `doctor --json` output, the exact error, the Python path you used  
  [Real SolidWorks validation](https://github.com/tan000tan/dsh-solidworks/blob/main/.github/ISSUE_TEMPLATE/03-real-solidworks-validation.yml)   You ran tools against a real SolidWorks session and want the result recorded   SolidWorks version, service pack and edition, mode, tools and outcomes, document description  
  [Feature request](https://github.com/tan000tan/dsh-solidworks/blob/main/.github/ISSUE_TEMPLATE/04-feature-request.yml)   The tool surface is missing something you need   The workflow you are trying to do, what stops you, an optional proposal  

If you are not sure which one fits, use the bug report template and say what you
were trying to do; a maintainer can re-label it.

## What to include

  Field   Detail to provide  
  ---   ---  
  Plugin version   From `package.json` or the DSH plugin list; 0.3.2 is the current release  
  DSH version   The host version, for example the rc version from the DSH about screen  
  Operating system   Windows 10 or 11 and the build number; only x64 Windows is supported  
  Python   Version and path, as reported by `doctor`; mention whether it is the plugin-local `.venv`  
  Node.js   Output of `node -v`; the minimum is 22.12  
  SolidWorks   Version, service pack and edition; 2026 SP4.1 on Windows is the verified combination  
  Policy mode   `read-only`, `standard` or `full`, as configured  
  Tool names   The exact registered names, for example `solidworks_health_check` or `solidworks_update_dimension`  
  Verification level   Real SolidWorks session, mock or automated test, MCP layer only, or not verified  
  Expected vs actual   What you expected and what happened, in one sentence each  
  Reproduction steps   The smallest ordered sequence that reproduces the problem  
  Logs   Doctor output, stderr or audit lines, with paths and user names removed  

## Privacy red lines

Do not upload or paste any of the following into an issue:

- Licence keys, activation codes, tokens, passwords or session cookies.
- Private, customer or employer CAD files, drawings, bills of materials or
  screenshots that reveal part names, dimensions or customers. Describe the
  document instead — "a simple bracket with one extrusion and two holes".
- Unredacted absolute paths, user names, machine names or domain names.
- A full DSH profile or `cordis.patch.yml`; it may contain personal settings and
  unrelated configuration.
- Logs from a machine you are not allowed to share.

When in doubt, redact. A report with a missing detail is easy to follow up on; a
leaked customer drawing is not recoverable.

## Response expectations

- One maintainer, spare time, no SLA and no promised response or fix time.
- Security issues should go through the private channel described in
  [SECURITY.md](SECURITY.md), not through a public issue.
- Issues may be closed if they are not reproducible, duplicate an existing
  report, or fall outside the scope below. A closed issue can be reopened with
  new evidence; that is normal, not a rejection of you.
- Feature requests may be declined to keep the tool surface small. A clear
  workflow description helps even when the answer is no.
- Repeated bumps are not necessary; the maintainer reads every issue when time
  allows.

## Out of scope

These are not supported, and a request for them will be answered with a pointer
back to this page:

- Linux and macOS. The plugin drives SolidWorks over COM on Windows; other
  platforms are not supported.
- Cracked, unlicensed or unactivated SolidWorks installations.
- Official SolidWorks support. This project is not Dassault Systèmes; SolidWorks
  bugs and licence questions go to the vendor.
- Remote desktop access or doing the modelling for you. Reports should contain a
  reproduction, not a request to operate your machine.
- Custom modelling consulting, design review sign-off or DFM approval. The DFM
  and review tools report what they compute; they are not an engineering sign-off.
- A compatibility statement for SolidWorks 2020–2025 beyond triage. Those
  versions are nominally supported but unverified, and the repository has no
  version gate.
- Unrelated Python, Node.js or DSH environment problems. Fix those with the
  respective upstream project; this plugin only supports the environment that
  `npm run setup` creates.

## Related documents

  Document   Why read it  
  ---   ---  
  [README.md](README.md)   Feature surface, modes and what the project is  
  [INSTALL.md](INSTALL.md)   Install, upgrade and uninstall details  
  [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)   Error codes and their fixes  
  [docs/USER_GUIDE.md](docs/USER_GUIDE.md)   Day-to-day usage, modes and tool groups  
  [docs/ADVANCED-CONFIG.md](docs/ADVANCED-CONFIG.md)   Configuration keys, including `allowedRoots` and `auditLog`  
  [docs/FEATURE_MATRIX.md](docs/FEATURE_MATRIX.md)   Per-tool status, including unverified tools  
  [docs/verification.md](docs/verification.md)   The evidence record behind the compatibility claims  
  [SECURITY.md](SECURITY.md)   Reporting a vulnerability, and the threat model  
  [CONTRIBUTING.md](CONTRIBUTING.md)   Sending a fix instead of a report  