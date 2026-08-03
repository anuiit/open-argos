# MCP readiness topic: Argos on Claude Code and Codex

The canonical design contract is
[`../references/mcp-bridge-plan.md`](../references/mcp-bridge-plan.md).

Implemented state:

- the Argos CLI, files/directories context, conversations, Council, research
  coverage, and review artifacts exist;
- the local MCP 2.0 stdio server and thin host-neutral adapter now exist in
  `argos/mcp_server.py` and `argos/mcp_adapter.py`;
- one local stdio server is shared by Claude Code and Codex;
- its API is typed and narrow: it does not expose raw CLI commands,
  executable paths, environment injection, arbitrary artifact roots, a smoke
  command, or configuration mutation;
- model egress, retrieval egress, and artifact writes are distinct approval
  boundaries;
- typed contracts, approval boundaries, idempotency, stdio conformance, and
  host adapter tests are implemented; `mcp==2.0.0` remains an optional runtime
  dependency rather than a dependency of the standard-library Argos core.

This note intentionally contains no second candidate tool list. Keeping one
normative contract avoids schema and security drift as the runtime evolves.
