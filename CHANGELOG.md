# Changelog

All notable user-facing changes are documented here. Versions follow Semantic
Versioning; Python package metadata uses the equivalent PEP 440 spelling (for
example `0.9.0rc1`).

## [0.9.0-rc1] - 2026-08-03

### Breaking changes and migrations

- The Codex plugin surface is focused on `$argos`, `$argos-review`,
  `$argos-critique`, `$argos-plan`, `$argos-council`, and `$argos-research`.
  Historical plugin skills route through `$argos` or the corresponding CLI
  command. The historical `argos sota` CLI spelling remains an alias.
- The bundled plugin candidate is `0.5.2-rc.1`; its Git source manifest no
  longer carries a machine-specific Codex cachebuster.
- Directory context now excludes the `benchmarks/` and `.omc/` directories by
  default. Select an individual non-secret file with `--file` when it is
  genuinely needed.

### Added

- Installable `open-argos` wheel/sdist metadata with `argos`, `python -m argos`,
  and `argos-mcp` entrypoints.
- A shared MCP 2.0 bridge for Codex and Claude Code with typed tools, workspace
  containment, explicit egress approvals, idempotency, and local resources.
- Persistent council, bounded debate, source-backed research, safe file and
  directory context, background jobs, and session lifecycle workflows.
- Cross-platform CI and a tag-driven GitHub release gate with clean-install
  smoke tests and checksums.
- English canonical documentation plus a French quick-start.

### Fixed

- Fail early when config, artifact, or lock roots are not writable, including
  restricted Windows sandbox environments.
- Bound stalled provider and MCP bootstrap subprocesses and normalize their
  failures instead of leaving requests pending indefinitely.
- Return controlled CLI errors for truncated session and background job JSON
  rather than raw decoding tracebacks.
- Preserve early aborts while streaming long OpenCode events.
- Preserve caller-provided Argos roots in the generated Windows launcher.

### Removed

- Remove the obsolete Mosaic-to-Argos migration, promotion, mirror-sync, and
  post-rename rebaseline scripts. They contained maintainer-specific paths and
  release-side effects that do not belong in an installable RC.

### Internal

- Add the versioned v2 benchmark harness, frozen judges, replay fixtures, and
  separate harness/replay/isolated/production quality axes.
- Exclude benchmark results, benchmark corpora, local orchestration state, and
  build output from the published Python package.

### Known limitations

- Provider CLIs remain external prerequisites and may require writable state
  directories of their own.
- The first public package publication is blocked until the project owner
  selects and adds a license.
- No comparative "Argos beats Codex" metric is claimed yet; the controlled A/B
  showcase protocol is documented but still needs execution.
