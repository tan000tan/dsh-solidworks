# Notices — superseded

> **The authoritative notice file for this package is [`NOTICE`](NOTICE) (no file extension).**
> This file is kept only so the earlier statement is not silently deleted. Where the two disagree,
> `NOTICE` wins, and the disagreement itself is tracked as an open item below.

## Historical record (written 2026-10-30, superseded 2026-11-12)

The original text of this file said:

> This repository includes and modifies SolidPilot from https://github.com/eyfel/mcp-server-solidworks
> … SolidPilot and this derivative distribution are licensed under the GNU Affero General Public
> License version 3 … The DeepSeek Harness integration, DSH profile, policy plugin, orchestration
> changes, and related documentation were modified in 2026 by contributors to `tian-yu200/dsh-solidworks`.

That text described the lineage of a **different** package in the same product family (the
`tian-yu200/dsh-solidworks` SKILL-style package), not the vendored engine that ships here.

## What the shipped package actually contains

- `vendor/solidworks-automation-skill/` is a snapshot of
  `https://github.com/tan000tan/solidworks-automation-skill` at commit `d8b9547`, which declares
  **MIT** in its own `LICENSE` file. It is 193 files, 28 of which carry local content changes and
  19 of which are local additions — see [`PROVENANCE.md`](PROVENANCE.md) for the measured diff.
- The plugin code itself (policy layer, MCP client wiring, CLI, tests, docs) is
  **AGPL-3.0-only**, matching [`LICENSE`](LICENSE).
- No binaries are shipped (no `.exe`, `.dll`, or `.pyd` anywhere in the tree).

## Open item (not resolved here)

Whether the upstream MIT declaration is itself free of obligations inherited from
`eyfel/mcp-server-solidworks` is a **third-party licensing question that this repository cannot
settle on its own**. The line-level comparison in `PROVENANCE.md` ("Upstream provenance risk") found
no verbatim derivation (64 shared generic lines, Jaccard 0.003; 5 generic file-name overlaps), but
that is evidence, not a legal conclusion. Confirmation from the upstream maintainer is recorded
there as an open, blocked checklist item.

Trademarks: SolidWorks is a trademark of Dassault Systèmes SolidWorks Corporation. This project is
independent and is not affiliated with or endorsed by Dassault Systèmes, DeepSeek, or any upstream
skill author.