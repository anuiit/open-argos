# Compatibility policy

## Release boundary

The `0.9.0-rc1` candidate covers:

- the `open-argos` Python distribution and `argos` CLI;
- the isolated `argos-mcp` bridge;
- the bundled `argos-tools` Codex skill facade, versioned separately in its
  plugin manifest.

The internal benchmark harness is quality infrastructure, not a runtime API or
package payload.

## Supported environments

| Environment | 0.9 RC status | Notes |
| --- | --- | --- |
| Native Windows, Python 3.12 | Release target; locally exercised | Provider CLIs and writable roots must exist in Windows. |
| Linux/WSL, Python 3.10-3.14 | Release target; CI gate pending first remote run | WSL is a separate installation from native Windows. |
| Codex + Claude Code in one OS environment | Supported target | Both clients use the same `argos` and `argos-mcp` commands. |
| macOS | Best effort before 1.0 | No release-blocking platform gate yet. |

Provider CLIs and their authentication/state directories are external. A
provider-specific readiness failure is reported explicitly but does not imply
that the Argos runtime itself is corrupt.

## Stability before 1.0

During 0.x releases, these contracts are versioned and changes require release
notes plus a migration path:

- CLI command and flag names;
- config keys;
- MCP tool names and request/response schemas;
- durable session and benchmark schema versions;
- documented plugin skill names and aliases.

Compatibility is not yet promised indefinitely. A breaking 0.x change may be
made when needed for the 1.0 design, but it must be explicit in `CHANGELOG.md`.
Historical CLI aliases should survive at least one minor release after their
replacement is documented.

At 1.0, removal of a documented contract will require a deprecation period and
a major release unless the old behavior is a security vulnerability.

## Language contract

English is canonical for CLI help, machine-readable fields, schemas, skill
invocations, and normative technical documentation. French documentation may
translate explanations and examples, but it does not rename protocol fields or
commands.

## Version domains

- Product/tag version: `0.9.0-rc1` / `v0.9.0-rc1`.
- Python package version: the PEP 440 equivalent `0.9.0rc1`.
- `argos-tools` plugin version: independent SemVer plus a local Codex
  cachebuster suffix.
- MCP protocol/package and benchmark schema versions: independent compatibility
  contracts; they do not follow the product version automatically.
