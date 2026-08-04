# Open Argos

Open Argos adds bounded, auditable multi-provider workflows to coding agents.
Codex or Claude Code remains in control; Argos asks independent provider CLIs
for reviews, critiques, plans, research, or persistent council input and keeps
the evidence in local artifacts.

Current candidate: **0.9.0-rc1**. The project is usable, but the public release
is still pre-1.0 and its compatibility contract is intentionally narrower than
the planned 1.0 contract.

[Documentation en français](README.fr.md) ·
[MCP installation](docs/MCP_INSTALL.md) ·
[Compatibility](docs/COMPATIBILITY.md) ·
[Showcase](docs/SHOWCASE.md) ·
[Release plan](docs/PRE_1_0_RELEASE_PLAN.md)

## Why Argos instead of one more agent prompt?

Argos is useful when a single model answer is not enough evidence:

- independent providers review the same bounded context instead of silently
  reinforcing one another;
- persistent councils retain dissent and corrections across turns;
- runs have explicit timeouts, statuses, and inspectable artifacts;
- directory context is deterministic, size-bounded, and excludes secrets,
  local agent state, and benchmark corpora by default;
- the same CLI and MCP server work from Codex and Claude Code when both clients
  run in the same Windows or Linux/WSL environment.

Argos never launches Codex. It invokes only provider CLIs configured by the
user, and provider access may send the selected context to those providers.

## Install from this repository

Prerequisites:

- Python 3.10 or newer;
- `uv` for the isolated MCP runtime;
- at least one supported provider CLI installed and authenticated in the same
  environment as Argos.

Clone the repository, then choose one installer:

```bash
git clone https://github.com/anuiit/open-argos.git
cd open-argos
pipx install .
# or: uv tool install .
```

The commands are the same in PowerShell, Windows Terminal, WSL, and Linux.
Install separately in native Windows and WSL: they do not share processes,
provider credentials, or lock files.

Verify the core installation:

```bash
argos --version
argos init-config
argos doctor --json
```

The default user paths are:

| Purpose | Path | Override |
| --- | --- | --- |
| Config | `~/.config/argos/config.json` | `ARGOS_CONFIG_DIR` |
| Artifacts | `~/.argos/sessions` | `ARGOS_ARTIFACT_ROOT` |
| Locks | `~/.argos/locks` | `ARGOS_LOCK_ROOT` |

Set all three overrides to writable locations before starting a run when the
host uses a restricted filesystem sandbox.

## Add the shared MCP server

Prepare the isolated runtime once:

```bash
argos-mcp --prepare --json
```

Then register the same executable with either or both clients:

```bash
codex mcp add argos -- argos-mcp
claude mcp add argos --scope local -- argos-mcp
```

If both clients run in the same OS environment, they use the same `argos`
installation, config, artifacts, and MCP runtime. See the
[MCP installation guide](docs/MCP_INSTALL.md) for Windows, WSL, manual config,
verification, update, and removal instructions.

## First useful workflows

Ask two configured providers to review a Python tree and synthesize the result:

```bash
argos run review \
  "Find correctness and security blockers; cite files and verification steps." \
  --dir . --include "**/*.py" \
  --argos fable --argos kimi3 --synthesize --json
```

Start a council whose disagreement survives across turns:

```bash
argos start council \
  "Choose the safest migration path and keep unresolved trade-offs explicit." \
  --argos fable --argos kimi3 --json
```

Run evidence-oriented research:

```bash
argos research "Compare the current supported approaches for this migration" \
  --profile current --json
```

Provider IDs such as `fable` and `kimi3` come from your config. Use
`argos models` and `argos config show` to inspect the local setup.

## Codex plugin

The bundled [`argos-tools`](argos-tools/README.md) plugin provides focused
skills for review, critique, planning, council, and research. It is a facade
over the same `argos` executable; the runtime and configuration remain central
instead of being duplicated inside each client.

## Safety and data egress

- Only explicitly selected files/directories are eligible for provider
  context.
- Secrets, binary files, VCS metadata, agent state, caches, and `benchmarks/`
  are rejected during directory expansion even when an include glob matches.
- A specific non-secret benchmark file can still be passed deliberately with
  `--file`.
- Requests and subprocesses are bounded. Provider failures, timeouts, corrupt
  state, and unavailable artifact roots return controlled statuses instead of
  hanging or leaking raw tracebacks.
- Artifacts remain local unless the user deliberately commits or shares them.

Read [the compatibility policy](docs/COMPATIBILITY.md) before automating around
CLI output or artifact schemas.

## License

Open Argos is distributed under the [MIT License](LICENSE).

## Development

```bash
python -m ruff check .
python -m compileall -q argos
python -m pytest -q
python -m build
```

Development entrypoints that isolate config and artifacts inside the clone are
available as `bin/argos-dev` (Linux/WSL) and `bin\argos-dev.ps1` /
`bin\argos-dev.cmd` (Windows).

Generated benchmark results, local Argos/OMX state, caches, wheels, and source
archives are ignored and are not part of the published Python package. The
golden benchmark corpus remains in Git for reproducibility, but it is quality
infrastructure rather than runtime payload.

See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), and
[CHANGELOG.md](CHANGELOG.md).

Release readiness and compatibility notes live in
[docs/BRANCHING.md](docs/BRANCHING.md),
[docs/COMPATIBILITY.md](docs/COMPATIBILITY.md), and
[docs/SHOWCASE.md](docs/SHOWCASE.md).
