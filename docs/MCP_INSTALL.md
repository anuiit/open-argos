# MCP installation guide

This guide exposes one installed Open Argos runtime to Codex, Claude Code, or
both. The hosts start the same `argos-mcp` stdio command; Argos keeps workflow
policy, provider configuration, and artifacts outside either client plugin.

Status: `0.9.0-rc1` can build a local wheel and source archive. It is not yet
published to a registry, so installation starts from a Git clone.

## Trust boundary

- Codex and Claude Code share the same Argos config and artifacts only when
  they run in the same operating-system environment.
- Native Windows and WSL are separate installations. Never share their PID or
  lock roots.
- Every MCP registration sets `ARGOS_WORKSPACE` to the project the server may
  access. Do not point it at an entire home/profile directory.
- `ARGOS_WORKSPACE` limits MCP paths; it does not replace the canonical Argos
  model configuration.
- Workflow tools require explicit model/retrieval egress approval. Inspection
  tools remain local and read-only.

## Prerequisites

Install these in the same environment as the client:

- Python 3.10 or newer;
- [`uv`](https://docs.astral.sh/uv/) for the isolated MCP SDK runtime;
- Codex CLI and/or Claude Code;
- at least one supported provider CLI, installed and authenticated.

## 1. Install Argos

```bash
git clone https://github.com/anuiit/open-argos.git
cd open-argos
pipx install .
# or: uv tool install .
```

PowerShell uses the same commands. Confirm that the tool installer added its
binary directory to the same `PATH` seen by Codex/Claude Code:

```powershell
Get-Command argos
Get-Command argos-mcp
argos --version
```

```bash
command -v argos
command -v argos-mcp
argos --version
```

Initialize and inspect the config:

```bash
argos init-config
argos doctor --json
```

Authentication or client-eligibility problems return `needs_human`; Argos does
not silently switch providers after those failures.

## 2. Prepare the isolated MCP runtime

The core CLI is standard-library-only. `argos-mcp` installs the pinned MCP SDK
into a versioned user cache, verifies its native imports, and then uses that
Python to run the bundled server.

Prepare it before registering the host so dependency installation cannot
consume the host's startup timeout:

```bash
argos-mcp --prepare --json
argos-mcp --check --json
```

No model/provider call occurs during preparation. The `uv` commands have a
bounded timeout and fail with a diagnostic if the package runtime cannot be
created.

## 3. Register in Codex

From the project that Argos may inspect:

```powershell
$workspace = (Resolve-Path .).Path
$mcpCommand = (Get-Command argos-mcp).Source
codex mcp add argos `
  --env "ARGOS_WORKSPACE=$workspace" `
  -- $mcpCommand
codex mcp get argos
```

```bash
workspace="$(pwd)"
mcp_command="$(command -v argos-mcp)"
codex mcp add argos \
  --env "ARGOS_WORKSPACE=$workspace" \
  -- "$mcp_command"
codex mcp get argos
```

Add a startup allowance to the existing server table in Codex's user or
trusted project config:

```toml
[mcp_servers.argos]
startup_timeout_sec = 120
```

Codex may defer tool descriptions. Ask it to discover `argos_health` through
tool search before concluding that the server is absent.

## 4. Register in Claude Code

Use project-local scope when the workspace is the current repository:

```powershell
$workspace = (Resolve-Path .).Path
$mcpCommand = (Get-Command argos-mcp).Source
claude mcp add argos --scope local `
  -e "ARGOS_WORKSPACE=$workspace" `
  -- $mcpCommand
claude mcp get argos
```

```bash
workspace="$(pwd)"
mcp_command="$(command -v argos-mcp)"
claude mcp add argos --scope local \
  -e "ARGOS_WORKSPACE=$workspace" \
  -- "$mcp_command"
claude mcp get argos
```

For the first connection, Claude Code can be given explicit startup bounds:

```powershell
$env:MCP_TIMEOUT = '120000'
$env:MCP_CONNECTION_NONBLOCKING = '0'
$env:MCP_CONNECT_TIMEOUT_MS = '60000'
claude
```

```bash
MCP_TIMEOUT=120000 \
MCP_CONNECTION_NONBLOCKING=0 \
MCP_CONNECT_TIMEOUT_MS=60000 \
claude
```

## 5. Verify each layer

1. `argos doctor --json` sees the intended provider CLIs.
2. `argos-mcp --check --json` reports `ready: true`.
3. `codex mcp get argos` and/or `claude mcp get argos` shows the absolute
   `argos-mcp` command and expected workspace.
4. The host discovers and calls `argos_health`.
5. An explicitly approved workflow writes an artifact below the workspace MCP
   state root.

From a source clone, the deterministic MCP regression suite is:

```bash
uv run --with mcp==2.0.0 --with pytest python -m pytest \
  argos/tests/test_mcp_contract.py \
  argos/tests/test_mcp_adapter.py \
  argos/tests/test_mcp_runtime.py \
  argos/tests/test_mcp_launcher.py \
  argos/tests/test_mcp_server.py \
  argos/tests/test_mcp_stdio.py -q
```

PowerShell accepts the same command on one line. Live provider tests remain
opt-in because they may consume paid quota.

## Writable roots in sandboxes

Argos preflights its config, artifact, and lock roots before calling a provider
or allocating a durable session. In a restricted host, set all three to
writable locations before starting Codex/Claude Code:

```powershell
$env:ARGOS_CONFIG_DIR = (Join-Path (Get-Location) '.argos-config')
$env:ARGOS_ARTIFACT_ROOT = (Join-Path (Get-Location) '.argos')
$env:ARGOS_LOCK_ROOT = (Join-Path (Get-Location) '.argos-locks')
```

```bash
export ARGOS_CONFIG_DIR="$PWD/.argos-config"
export ARGOS_ARTIFACT_ROOT="$PWD/.argos"
export ARGOS_LOCK_ROOT="$PWD/.argos-locks"
```

The repository ignores these runtime directories. A failed preflight does not
call a provider or create an incomplete `adv_*` session.

Provider CLIs can own additional state. For example, Kimi may need write access
to `~/.kimi-code`. `ARGOS_*` does not relocate provider-owned state; validate
each CLI inside the same sandbox or use the provider's documented override.

## Context rejected by the bridge

MCP paths must stay inside `ARGOS_WORKSPACE`. Parent traversal, symlinks,
Windows reparse points, protected directories, secret-like files, binaries,
VCS data, local agent state, caches, and benchmark directories are rejected.
Pass only a specific non-secret file when an excluded corpus item is essential.

## Troubleshooting

### The host starts but no tools appear

- verify that the host and `argos-mcp` are in the same Windows/WSL environment;
- inspect the absolute command recorded by `codex mcp get argos` or
  `claude mcp get argos`;
- run `argos-mcp --check --json`;
- restart the host and discover `argos_health` explicitly.

### MCP preparation times out

Run `argos-mcp --prepare --json` in a normal terminal. A timeout means `uv` or
package access is blocked/too slow; fix that environment instead of repeatedly
letting the host restart the server.

### A provider returns `needs_human`

Run `argos doctor --json`, authenticate the named provider in the same OS
environment, and retry explicitly. Authentication and client-eligibility
errors are not safe automatic-fallback signals.

## Update and rollback

Before registry publication, update from the clone:

```bash
git pull --ff-only
pipx install . --force
# or: uv tool install . --force
argos-mcp --prepare --json
```

To roll back, check out the desired tag/commit and rerun the same forced local
install. Restart clients after an update so they reload server and skill
metadata.

## Uninstall

Remove host registrations first:

```bash
codex mcp remove argos
claude mcp remove argos --scope local
```

Then remove the installed tool:

```bash
pipx uninstall open-argos
# or: uv tool uninstall open-argos
```

This deliberately leaves provider credentials, Argos sessions, and the MCP
runtime cache intact. Review any audit history before deleting those directories
manually.
