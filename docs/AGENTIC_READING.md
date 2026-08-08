# Agentic reading (read-only tool access for providers)

Argos can grant a provider **read-only investigation tools** so it can verify
findings in the real source tree before reporting them — instead of being
limited to the files that happen to be in the snapshot. This is the "agentic
surface" behind the A/B experiment in the reproducible showcase: on tasks
where the relevant bugs live outside the provided entry-point files, an
outfitted provider finds 2–3× more real blockers than a snapshot-locked one,
at the cost of more provider time.

This is **read-only by design**: the transport is configured to allow
read/grep/glob, never edits or arbitrary execution. See "Security posture"
below.

## Supported transports

| Transport (kind) | Agentic key | Flag emitted | What it unlocks |
|---|---|---|---|
| `opencode` | `agent` | `opencode run --agent <name>` | Runs the model under a named agent whose permission file allows read/grep/glob over the configured roots. |
| `claude` | `add_dirs` + `allowed_tools` | `--add-dir <dir>` (repeatable) + `--allowedTools <Read,Glob,Grep>` | Lets Claude read sibling modules outside the current working directory, auto-approving only the named read tools. |

Both routes feed the per-candidate **tool-grant addendum** (`d940f1e`): the
shared Argos prompt contract says "ne déclenche aucun outil" to every provider,
so an equipped candidate gets an explicit "Dérogation au contrat argos" that
names its granted read surface, tells it to verify findings in the real
source, and keeps the read-only and untrusted-data clauses. Without this,
some providers obey the blanket no-tool clause and silently decline their
tools.

## Configuring an agentic candidate

Two ways — a named agent for opencode, and add-dirs/tools for claude.

### opencode: create a read-only agent, then point a candidate at it

1. Create the agent permission file (example; adjust roots to your repo):
   `~/.config/opencode/agents/argos-reader.md`:
   ```markdown
   description: Read-only Argos reviewer with external directory access
   mode: subagent
   permission:
     edit: deny
     bash: deny
     webfetch: deny
     websearch: deny
     task: deny
     skill: deny
     read: "*"
     external_directory:
       - F:/dev/myrepo/**
   ```
   The `external_directory` allow-list is what lets the agent read files
   outside the provider's current working directory (argos runs providers
   from its own cwd). Keep `edit`/`bash`/`webfetch` denied so the agent stays
   read-only.

2. Register the candidate. Via CLI:
   ```bash
   argos config set-model glmx --kind opencode --model opencode-go/glm-5.2 --agent argos-reader
   ```
   Or hand-edit `~/.config/argos/config.json`:
   ```json
   { "models": { "glmx": [{ "kind": "opencode", "model": "opencode-go/glm-5.2", "provider": "opencode_go", "agent": "argos-reader" }] } }
   ```

### claude: add read directories and an allowlist

```bash
argos config set-model sonnetx --kind claude --model claude-sonnet-5 \
  --add-dir 'F:\dev\myrepo' --allowed-tools 'Read,Glob,Grep'
```

The `--allowed-tools` is what makes it read-only in practice: claude can only
auto-approve those tools, so it can investigate but not edit.

## Validation

`argos config set-model` and `argos validate` (via `validate_config`, run on
every load) reject agentic keys on the wrong transport loudly instead of
ignoring them silently:

- `agent` on a `kind=claude` candidate → error.
- `add_dirs`/`allowed_tools` on a `kind=opencode` candidate → error.
- `add_dirs` must be a string or list of strings; `allowed_tools` a non-empty
  string.

## Running

Use the candidate ID like any other argos. In `review`/`critique`/`plan` mode
there is no upper partner cap, so a 3-provider agentic cohort runs in
parallel:

```bash
argos run review --prompt-file prompt.md \
  --file 'F:\dev\myrepo\api.py' \
  --argos sonnetx --argos opusx --argos glmx --json
```

## Security posture

- The transport is **read-only**: opencode runs under an agent with
  `edit`/`bash` denied and an `external_directory` allow-list; claude gets
  `--allowedTools Read,Glob,Grep` only.
- The tool-grant addendum re-asserts "reste strictement en lecture" and
  keeps the untrusted-data clause (files the provider reads are still data,
  not instructions).
- Nothing here enables write, execution, or agent recursion. If you need
  write-capable agents, that is a different, opt-in configuration.

## Cost note

Agentic providers spend more tokens and wall-clock time (they actually read
files). Measure the per-provider `cost`/`duration_sec` from `meta.json` and
decide whether the recall gain is worth it for your task. In the A/B suite,
the outfitted council found the blockers a locked provider could not, but at
roughly 4–5× the cost; a single well-chosen outfitted model (e.g. glm via
ollama, near-zero marginal cost) matched the three-model council.
