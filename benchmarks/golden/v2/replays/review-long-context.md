## Blockers

- The authoritative late correction makes explicit CLI flags the highest precedence input. The earlier proposal incorrectly lets the project file win over a CLI override.
- Resolution is read-only: the process must not write the resolved value back to the project configuration. That writeback would persist a one-off CLI choice and change later runs.

## Important issues

- `99-product-correction.md` supersedes the earlier design and migration notes. The implementation and documentation must preserve that correction trail rather than silently following the older proposal.

## Preferences

- Document one precedence table instead of duplicating prose in each configuration layer.

## Minimal fix plan

1. Centralize precedence as CLI, environment, project, then default.
2. Add a test proving a CLI value wins over the project value.
3. Add a read-only regression test proving the project file remains unchanged after resolution.
