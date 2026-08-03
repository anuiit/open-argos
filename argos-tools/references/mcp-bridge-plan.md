# Argos MCP bridge contract

Status: implementation contract. The transport, state, and adapter decisions
below are frozen for the first local stdio implementation.

This document defines one client-neutral MCP surface for Claude Code and
Codex. It is deliberately more restrictive than the Argos CLI: MCP callers
receive typed operations, not a remote shell or a way to construct arbitrary
CLI arguments.

## Goals and non-goals

The bridge must:

- keep the existing Argos Python core and artifact/session formats as the
  source of truth;
- support one-shot work, multi-turn conversations, Council, and research;
- accept files **and directories** through the same bounded context contract;
- produce the same artifacts and safety decisions regardless of the MCP
  client;
- run locally over stdio first;
- expose enough metadata for a caller to audit prompt assignments, research
  coverage, review findings, provider egress, and failures.

The first version must not:

- implement arbitrary shell execution;
- accept raw command strings or provider CLI flags;
- mutate Argos configuration;
- expose secrets, raw environment variables, or unrestricted filesystem
  reads;
- add an HTTP transport, authentication layer, or a second client-specific
  server.

## Transport and process contract

The initial server is a local MCP stdio process.

- `stdout` is reserved exclusively for MCP JSON-RPC frames. A banner, debug
  print, traceback, or provider output on `stdout` is a protocol defect.
- Human-readable logs and sanitized diagnostics go to `stderr`.
- The process serves requests until the client closes stdin or sends the MCP
  shutdown sequence. It must cleanly cancel child provider processes on exit.
- Each tool request is independent at the protocol layer. Durable continuity
  comes from an explicit `session_id`, never from hidden process memory.
- The server must not silently retry provider calls. A client can retry only
  when the structured error says the operation is retryable.
- Cancellation should terminate the current child process, preserve any
  already-written audit artifacts, and return `cancelled` if the client still
  accepts a response.

The transport uses the official Python MCP SDK pinned to `mcp==2.0.0`.
Version 2.0.0 is the first stable v2 release, supports the 2026-07-28
protocol revision, and serves earlier protocol revisions from the same
server. The dependency is declared as PEP 723 metadata on the server
entrypoint so the existing standard-library CLI remains dependency-free. A
standard-library bootstrap (`argos/mcp_runtime.py`) prepares a versioned
user-cache runtime and must verify both the SDK version and native
`pydantic_core` import before reporting readiness. Hosts launch that
runtime's Python and the absolute server path directly. `uv run --script` is
retained for portable SDK tests and fallback diagnosis, not as the canonical
host command: dependency resolution and native imports on a cold Windows
machine can exceed host startup defaults. Protocol framing, negotiation,
validation, cancellation dispatch, and structured output must not be
reimplemented locally.

## Common input schema

Tools that run a workflow share the following conceptual input schema. The
implementation should publish equivalent JSON Schema through `tools/list`;
fields marked required below must be required there too.

```json
{
  "request_id": "caller-generated-idempotency-key",
  "prompt": "Required for a new run or turn",
  "mode": "review",
  "profile": "medium",
  "session_id": "optional-existing-session",
  "context": {
    "files": ["README.md", "src/module.py"],
    "directories": ["src", "tests"],
    "include": ["**/*.py", "**/*.md"],
    "exclude": [".git/**", "**/__pycache__/**"],
    "max_files": 200,
    "max_file_chars": 60000,
    "max_total_chars": 180000,
    "follow_symlinks": false
  },
  "images": ["assets/reference.png"],
  "providers": ["fable"],
  "artifact_write": true,
  "model_egress": true,
  "retrieval_egress": false,
  "force_model_on_insufficient": false
}
```

Rules:

- `artifact_write` is required and defaults to `false` for every
  write-capable tool. It remains explicit even though MCP tool annotations
  also classify side effects; annotations are hints, not authorization.
- `request_id` is required for every write-capable tool. Reusing it with the
  same canonical input returns the original result; reusing it with different
  input returns `idempotency_conflict`.
- Every file, directory, include result, and image must resolve under an
  allowlisted workspace root. Path traversal, device paths, and escaping
  symlinks are rejected before reading content.
- Directory expansion is deterministic, sorted, bounded by all three size
  caps, and records skipped files plus reasons in the artifact manifest.
- `include` and `exclude` are data filters, not shell globs. They are never
  interpolated into a command.
- Provider and mode values come from server-side allowlists. Clients cannot
  supply an executable, command, environment, working directory, or arbitrary
  provider flag.
- `model_egress` and `retrieval_egress` are separate because research may
  retrieve evidence without invoking a model. Both default to `false` in the
  MCP schema even if a local CLI profile is more permissive.
- Secrets are resolved from the server's existing configuration/environment
  allowlist. They never appear in input schemas, output payloads, artifacts,
  or logs.

## Common output schema

Every tool returns a JSON object with this stable envelope:

```json
{
  "schema_version": "1.0",
  "request_id": "caller-generated-idempotency-key",
  "status": "completed",
  "summary": "Short, sanitized result for the client",
  "session_id": "optional-session-id",
  "artifact_dir": "workspace-relative-or-null",
  "result": {},
  "approval": {
    "required": false,
    "kinds": [],
    "granted": []
  },
  "error": null
}
```

The error variant is:

```json
{
  "schema_version": "1.0",
  "request_id": "same-request-id",
  "status": "failed",
  "summary": "Provider timed out",
  "session_id": "optional-session-id",
  "artifact_dir": "workspace-relative-or-null",
  "result": {},
  "approval": {
    "required": true,
    "kinds": ["model_egress"],
    "granted": []
  },
  "error": {
    "class": "provider_timeout",
    "message": "Sanitized diagnostic without command lines or secrets",
    "retryable": true,
    "outcome_unknown": false
  }
}
```

Allowed top-level statuses are `completed`, `partial`, `insufficient`,
`cancelled`, and `failed`. Stable error classes initially include
`invalid_input`, `path_outside_workspace`, `context_limit_exceeded`,
`approval_required`, `provider_unavailable`, `provider_timeout`,
`retrieval_failed`, `idempotency_conflict`, `session_not_found`,
`session_conflict`, `request_in_progress`, `interrupted`, and
`internal_error`.

`outcome_unknown` is `true` only when the server cannot prove whether an
external operation completed. The initial Argos surface should normally keep
it `false`, because provider calls synthesize local text rather than mutate
external systems.

## Tool surface and side-effect classification

Names use underscores so the same identifiers remain comfortable in both
clients.

| Tool | Class | Purpose |
| --- | --- | --- |
| `argos_health` | read-only | Return protocol version, Argos version, configured provider names, allowed roots, and capability flags. Never probe a provider unless explicitly requested through a write-capable tool. |
| `argos_session_list` | read-only | List bounded, sanitized session summaries under the active workspace. |
| `argos_session_show` | read-only | Read one session's turn index, status, artifact links, and latest synthesis. |
| `argos_council_show` | read-only | Read one Council's membership manifest, history index, and latest synthesis. |
| `argos_run` | write-capable | Execute one bounded Argos mode (`plan`, `critique`, `review`, `debug`, `ui`, `vision`, `star`, or `consensus`). |
| `argos_start` | write-capable | Create a multi-turn session and execute its first turn. |
| `argos_ask` | write-capable | Append exactly one turn to an existing session using optimistic concurrency. |
| `argos_council_publish` | write-capable | Publish one user turn to an existing Council and synthesize the contributors' independent answers. |
| `argos_research` | write-capable | Run deterministic query planning/retrieval and, only when allowed by coverage plus approval, model synthesis. |

Read-only tools may read existing Argos artifacts but may not write a health
cache, touch timestamps, initialize a session, retrieve from the network, or
contact a model.

Write-capable means the tool creates or updates Argos-owned artifacts and may
also require egress. It does **not** authorize arbitrary filesystem changes.

### Tool-specific input schema

- `argos_health`: optional `probe_paths: boolean` (default `false`). No
  `request_id` is required because it is read-only.
- `argos_session_list`: optional `limit` (1–100) and opaque `cursor`.
- `argos_session_show`: required `session_id`; optional `turn_limit`.
- `argos_council_show`: required `council_id`; optional `turn_limit`.
- `argos_run`: common input with required `request_id`, `prompt`, and `mode`.
- `argos_start`: common input with required `request_id`, `prompt`; optional
  `mode` and `session_label`. Returns a new `session_id`.
- `argos_ask`: required `request_id`, `session_id`, `prompt`, and
  `expected_turn`; optional context additions. A stale `expected_turn`
  returns `session_conflict` rather than interleaving turns.
- `argos_council_publish`: required `request_id`, `council_id`, `prompt`, and
  `expected_turn`; optional bounded context additions.
- `argos_research`: required `request_id`, `prompt`; optional `max_queries`,
  `max_sources`, `retrieval_egress`, `model_egress`, and
  `force_model_on_insufficient`.

### Tool-specific output schema

The `result` member uses these bounded shapes:

- run: `mode`, `profile`, `final_text`, `prompt_manifest`,
  `findings_artifact`;
- session start/ask: `turn`, `final_text`, `prompt_manifest`,
  `history_resource`;
- Council publish: `turn`, `contributors`, `independent_answers`,
  `synthesis`, `membership_manifest`;
- research: `verification_status`, `coverage`, `queries`,
  `evidence_artifact`, `synthesis`, `model_skipped`;
- health: `ready`, `capabilities`, `providers`, `allowed_roots`, `warnings`;
- list/show tools: opaque IDs, indices, summaries, and resource links only.

Large prompts, full file contents, provider transcripts, and secrets are not
returned inline. The output links to private artifacts/resources instead.

## Resources

Use read-only resources for existing, potentially large artifacts:

```text
argos://sessions/{session_id}/summary
argos://sessions/{session_id}/turns/{turn}
argos://sessions/{session_id}/artifacts
argos://councils/{council_id}/summary
argos://councils/{council_id}/turns/{turn}
argos://runs/{request_id}/manifest
argos://runs/{request_id}/coverage
argos://runs/{request_id}/findings
```

Resource reads perform the same workspace/root checks as tools, return
sanitized UTF-8 text or JSON, and never trigger computation or egress.
Unknown or unauthorized identifiers look identical to callers to avoid
turning the server into a path-discovery oracle.

## Approval and egress policy

The bridge reports required approval kinds before starting work:

- `artifact_write` for every write-capable tool;
- `model_egress` before invoking a configured model provider;
- `retrieval_egress` before web/API retrieval;
- `force_insufficient_synthesis` when overriding failed research coverage.

The MCP host remains the user-facing approval authority. The server also
enforces the matching boolean in the input so a permissive host cannot
accidentally widen a request. Missing approval yields `approval_required`
without starting the side effect.

Side-effect annotations are fixed as follows:

- the four inspection tools set `readOnlyHint=true`,
  `destructiveHint=false`, and `openWorldHint=false`;
- write-capable tools set `readOnlyHint=false`,
  `destructiveHint=false`, and `idempotentHint=true`;
- `argos_research` additionally sets `openWorldHint=true`; every other tool
  sets it to `false`.

`argos_research` first performs local query planning. Retrieval requires
`retrieval_egress`. It writes `coverage.json` before any model call. When
coverage is insufficient, model calls are skipped unless both
`model_egress=true` and `force_model_on_insufficient=true` were explicitly
approved and recorded.

The bridge never accepts arbitrary shell, destructive file operations,
network destinations, headers, tokens, or executable paths from MCP tool
arguments. Provider processes are selected from trusted Argos configuration
and launched without a shell.

## Conversation and concurrency semantics

- `argos_start` creates the canonical session manifest before the first model
  call and returns the same session if an identical `request_id` is replayed.
- `argos_ask` appends one user turn, independent provider answers, and one
  synthesis. It preserves the session's assignment/persona provenance but
  does not re-inject a fresh assignment into a resumed provider conversation.
- `expected_turn` provides optimistic concurrency. Two clients cannot silently
  publish turn N+1 from the same N.
- The comparison and claim of `expected_turn` occur inside the existing
  session lock, in the same critical section that sets `active_turn`.
  An adapter-side pre-check alone is a protocol defect.
- Partial provider failure is represented as `partial`; successful answers
  are preserved and missing contributors are explicit.
- Council membership is immutable after creation in v1. Effective identities
  are unique by provider kind, provider, and model—not merely by display name.
- No hidden autonomous loop is exposed through MCP. Each `argos_ask` or
  `argos_council_publish` request creates at most one conversational turn.

## Client setup recipes

Prepare the pinned runtime once, then use the returned absolute paths so host
working-directory changes cannot select another script:

```powershell
$repo = (Resolve-Path ".").Path
$runtime = uv run python (Join-Path $repo "argos\mcp_runtime.py") `
  --workspace $repo `
  --json | ConvertFrom-Json
$mcpPython = $runtime.runtime_python
$mcpServer = $runtime.server_path
```

### Claude Code

Local scope:

```powershell
claude mcp add argos --scope local `
  -e ARGOS_WORKSPACE=$repo `
  -- $mcpPython $mcpServer
claude mcp get argos

$env:MCP_TIMEOUT = '120000'
$env:MCP_CONNECTION_NONBLOCKING = '0'
$env:MCP_CONNECT_TIMEOUT_MS = '60000'
claude
```

Project scope should produce a reviewable `.mcp.json` and requires the normal
Claude Code project-server approval:

```json
{
  "mcpServers": {
    "argos": {
      "type": "stdio",
      "command": "C:\\path\\returned-by-bootstrap\\python.exe",
      "args": ["C:\\path\\to\\open-argos\\argos\\mcp_server.py"],
      "env": {
        "ARGOS_WORKSPACE": "C:\\path\\to\\your-workspace"
      }
    }
  }
}
```

The concrete runtime directory contains the Python ABI tag; copy it from the
bootstrap result rather than assuming `py311`. Claude Code starts MCP servers
non-blocking by default and snapshots tools after a short wait. For this
cold-starting Python server, `MCP_TIMEOUT=120000`,
`MCP_CONNECTION_NONBLOCKING=0`, and `MCP_CONNECT_TIMEOUT_MS=60000` make the
first query deterministic. On native Windows, use `cmd /c` only when the
selected executable requires a shell wrapper; this runtime uses `python.exe`
directly.

### Codex CLI, app, and IDE

Local CLI registration:

```powershell
codex mcp add argos `
  --env ARGOS_WORKSPACE=$repo `
  -- $mcpPython $mcpServer
codex mcp get argos
```

Equivalent trusted project configuration in `.codex/config.toml`:

```toml
[mcp_servers.argos]
command = "C:\\path\\returned-by-bootstrap\\python.exe"
args = ["C:\\path\\to\\open-argos\\argos\\mcp_server.py"]
cwd = "C:\\path\\to\\open-argos"
startup_timeout_sec = 120
tool_timeout_sec = 180

[mcp_servers.argos.env]
ARGOS_WORKSPACE = "F:\\dev\\open-argos"
```

Copy the runtime path from the bootstrap result rather than assuming the ABI
tag shown in the example. Codex CLI, the Codex app, and the Codex IDE
extension share the host's MCP configuration. Project-scoped configuration
must only be enabled for a trusted repository. Codex can defer MCP tool
descriptions, so callers use tool search before the first Argos call.

## Compatibility matrix

| Client | Initial transport | Configuration | Required smoke |
| --- | --- | --- | --- |
| Claude Code, native Windows | stdio | local registration or project `.mcp.json` | add/get, initialize, tools/list, health, one denied write, one approved run |
| Claude Code, WSL/Linux/macOS | stdio | local registration or project `.mcp.json` | same plus POSIX path containment |
| Codex CLI | stdio | `codex mcp add` or `config.toml` | add/get/list, initialize, tools/list, health, one denied write, one approved run |
| Codex app | stdio through shared Codex config | `config.toml` | server discovery, approval display, session resource read |
| Codex IDE extension | stdio through shared Codex config | `config.toml` | server discovery, workspace-root containment, cancellation |

Streamable HTTP is intentionally deferred. It adds authentication,
multi-tenant isolation, origin policy, and deployment concerns without helping
the first local Claude Code/Codex use case.

## Conformance and smoke-test plan

Protocol conformance:

1. initialize/initialized handshake and protocol-version negotiation;
2. `tools/list` exposes stable names, descriptions, input schema, and output
   schema;
3. `resources/list` and `resources/read` never trigger a write or egress;
4. JSON-RPC parse errors are structured and the process remains usable;
5. concurrent requests correlate responses by ID;
6. cancellation terminates the child provider and preserves audit state;
7. zero non-protocol bytes reach `stdout`; diagnostics appear on `stderr`.

Security conformance:

1. absolute, relative, `..`, UNC, device, alternate-data-stream, junction, and
   symlink escape cases on Windows;
2. POSIX symlink and case-sensitivity cases;
3. directory include/exclude expansion and all file/byte caps;
4. prompt-injection text in filenames, file bodies, provider output, and
   research evidence remains inside untrusted-data boundaries;
5. tool arguments cannot select a command, executable, environment variable,
   network host, or artifact root;
6. denied `artifact_write`, `model_egress`, `retrieval_egress`, and override
   approvals cause zero side effects;
7. outputs and `stderr` redact configured secrets and provider command lines.

Behavioral conformance:

1. one-shot plan/review plus prompt manifest and findings artifact;
2. start/ask/replay/conflicting-turn conversation lifecycle;
3. Council independent answers, immutable membership, duplicate effective
   identity rejection, and synthesis;
4. research with sufficient coverage, insufficient coverage/model skipped,
   and explicitly approved override;
5. identical `request_id` replay and conflicting payload rejection;
6. provider timeout, partial success, cancellation, and server restart;
7. the same fixture suite through Claude Code and Codex, comparing normalized
   artifacts rather than client presentation text.

Release requires all deterministic unit/integration tests, the adversarial
Argos smoke suite, both client smokes, and a clean `stdout` capture. A skipped
client smoke is a release blocker for the corresponding compatibility claim.

## Rollout

1. `argos/mcp_contract.py` owns Pydantic request/response schemas, stable
   enums, annotations, cursor encoding, and schema fixtures. Cursors are
   versioned base64url JSON containing only a bounded offset and selection
   fingerprint. They are opaque continuation tokens, not authorization
   tokens.
2. `argos/mcp_adapter.py` owns workspace policy, approvals, idempotency,
   resource resolution, sanitized read models, and translation to existing
   Argos functions. It never writes to stdout.
3. `argos/argos.py` gains only reusable-core seams: silent structured
   returns, the in-lock `expected_turn` check, and reliable Windows
   cancellation fallback. CLI output and behavior remain unchanged.
4. `argos/mcp_server.py` owns the PEP 723 dependency declaration, MCP SDK
   decorators, tool annotations, resources, and stdio entrypoint. It contains
   no provider command construction or artifact business logic.
5. `argos/tests/test_mcp_contract.py`,
   `argos/tests/test_mcp_adapter.py`, and
   `argos/tests/test_mcp_server.py` cover schemas, fake-adapter behavior,
   official-SDK in-memory calls, legacy negotiation, stdout purity, and
   subprocess cancellation.
6. Native Windows smokes bootstrap the pinned cache runtime, execute its
   absolute Python and server paths through the official SDK client, temporary
   Codex configuration, and temporary Claude local scope. The Claude smoke
   uses explicit startup waits; the Codex smoke uses
   `startup_timeout_sec = 120` and dynamic tool discovery. Registrations are
   removed after the smoke. The subprocess suite receives the same executable
   through `ARGOS_MCP_RUNTIME_PYTHON`; without it, the suite exercises the
   portable PEP 723 fallback instead.
7. Only after local v1 is stable, evaluate streamable HTTP as a separate
   threat model and versioned transport.

## Frozen implementation decisions

- No MCP prompts in v1. Tools and resources provide parity without adding a
  second workflow taxonomy.
- MCP-owned state lives under `<workspace>/.argos/mcp/`; provider sessions
  live below `<workspace>/.argos/mcp/sessions/`. No global Argos session is
  made visible implicitly.
- A request ledger lives under `.argos/mcp/requests/`. The filename is the
  SHA-256 of `request_id`; the record stores the canonical-input hash and the
  terminal envelope. Same ID plus same input returns the terminal envelope.
  Same ID plus different input returns `idempotency_conflict`. A live claim
  returns `request_in_progress`; an abandoned claim becomes `interrupted` and
  is never silently re-executed.
- Cancellation persists a terminal `cancelled` envelope after terminating the
  provider process tree. If the client no longer accepts a response, the next
  identical replay reads that envelope. A provider subset failure maps to
  `partial`; deterministic research coverage failure maps to `insufficient`;
  invalid input or complete provider failure maps to `failed`.
- Resource authorization is identifier-based plus canonical root
  containment. Session IDs and request IDs resolve only through MCP-owned
  indices. Unknown, malformed, and outside-root identifiers return the same
  not-found response.
- `ARGOS_MCP_ALLOWED_ARGOSES` may narrow the configured logical Argos IDs.
  Tool arguments can select only from that intersection and can never widen
  it or provide a model, executable, provider command, environment variable,
  or working directory.
- There is no retention or cleanup mutation in v1. Artifacts are retained
  until the operator removes them outside MCP.

## Primary references

- Claude Code MCP guide:
  https://docs.anthropic.com/en/docs/claude-code/mcp
- Claude Code CLI reference:
  https://docs.anthropic.com/en/docs/claude-code/cli-usage
- OpenAI Codex MCP configuration:
  https://developers.openai.com/codex/mcp/
- MCP specification:
  https://modelcontextprotocol.io/specification/
