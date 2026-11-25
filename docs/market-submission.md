# DSH marketplace submission

Status of the plugin's listing in the DeepSeek Harness plugin catalogue, what the entry
currently says, and what a maintainer still has to change.

The catalogue is the `awesome-dsh-plugin` index, served at
<https://awesome-dsh-plugin.com> and consumed by the DSH marketplace UI. It is a list of
per-plugin YAML entries in a public repository; the marketplace does not host binaries.
Each entry points at a tarball attached to a GitHub Release.

## Current listing (checked 2026-11-18)

| Field | Value |
| :--- | :--- |
| Catalogue entry | `data/plugins/tan000tan__dsh-solidworks.yml` in `awesome-dsh-plugin/awesome-dsh-plugin` |
| Category | `tools` |
| Tarball the entry serves | `…/releases/download/v0.3.2/dsh-solidworks-0.3.2.tgz` |
| Version users currently get | **v0.3.2** |
| Current GitHub release | v0.3.2 (same asset) |
| Entry update pull request | `awesome-dsh-plugin/awesome-dsh-plugin#16343` — **merged 2026-11-17T17:30:48Z**, merge commit `911b385e2f550e7c8f5a81575cea09f00659eb54` |

The listing therefore installs the same tag that this repository calls its current
release; there is no version skew between catalogue and GitHub Release any more.

Two things are still stale, and both come from the *asset*, not from the entry:

1. The listing page renders the README **from the tagged release it serves**, i.e. the
   README inside the v0.3.2 tarball. That README predates this round of documentation
   work: it still carries the "enterprise-grade" headline and the "110 assertions across
   7 suites" wording. The page will only change when a new release asset is built from a
   commit that contains the rewritten docs.
2. The entry description (written when the update PR was opened) says the plugin will
   "automatically create a plugin-local `.venv` and run pip install … on start" when the
   interpreter lacks `mcp`/`pywin32`. In the shipped code that bootstrap is **opt-in**
   (`autoBootstrap` config / `DSH_SOLIDWORKS_AUTO_BOOTSTRAP=1`; see `lib/discover.js`),
   and the default path is to fail with `PYTHON_NOT_FOUND` / `PYTHON_INVALID` plus a
   message telling the user to run `npm run setup`. Correcting the description needs a
   new single-line entry PR.

Neither issue blocks installing v0.3.2 from the catalogue; both are cases where the public
text is older or looser than the repository.

## What the entry requires from this repository

The catalogue requires a plugin package that the DSH host can install directly:

- `package.json` must declare `dsh.bundle.patch` pointing at a patch file (`cordis.patch.yml` here).
- The package must not rely on `postinstall`: marketplace installs run with lifecycle scripts
  disabled, so anything setup-time has to happen through the documented `npm run setup` or
  through the plugin's own runtime discovery.
- The tarball must be a public HTTPS asset on a GitHub **Release** (not a raw branch URL) and
  its filename must not embed the version.
- The description in the entry must avoid marketing terms; the index review rejects them.

All four were satisfied by the v0.3.2 release asset
(`dsh-solidworks-0.3.2.tgz`, 785,932 bytes, SHA-256
`65f6cabe647cd52f6270e0538dffceff83b78e549eaef4510f9181b08604abc1`), which is what the
entry now serves.

## Remaining work for the marketplace path

1. ~~Get `#16343` reviewed and merged~~ — done 2026-11-17.
2. Confirm that the listing page's install command resolves to the v0.3.2 tarball — the
   entry YAML above is the evidence; the rendered page still shows the old README by design.
3. Install once from the marketplace UI into a throwaway profile and verify that the plugin
   loads and publishes tools. **This has not been done** — see the note below.
4. Build a new release asset from a commit that includes this round's documentation (needs
   an explicit release decision: commit, tag, rebuild, and re-upload the asset), then the
   page's old wording disappears.
5. Open a one-line entry PR to correct the automatic-bootstrap sentence in the description.

## Known gap in this repository's evidence

Marketplace installation has **not** been executed end to end. The local desktop profile
carries the plugin as a `file:` dependency on a tarball, which proves the package installs
and loads from a tarball, but not that the marketplace UI path works. Until step 3 above is
done, treat "install from the marketplace" as unverified.

Not published, and not planned in this round: npm (registry `latest` is still `0.2.0`;
publishing needs an explicit release decision) and PyPI (not applicable — this is not a
Python package distributed through PyPI).