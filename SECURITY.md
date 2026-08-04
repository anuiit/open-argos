# Security policy

## Supported versions

Until 1.0, security fixes target the newest published pre-release only. Older
development snapshots may receive fixes when the patch applies cleanly, but
they are not a supported security branch.

## Reporting a vulnerability

Do not open a public issue for a vulnerability that exposes credentials,
private source code, unsafe process execution, path escape, or unintended model
egress. Use the repository's private GitHub security advisory flow instead:

`Security` → `Advisories` → `Report a vulnerability`

Include the affected version, operating system, exact command or MCP tool,
minimal reproduction, expected boundary, observed behavior, and whether any
provider received unintended data. Remove real secrets from the report.

If private advisories are unavailable, open a public issue containing no
sensitive details and ask the maintainer for a private reporting channel.

## Security boundaries

- Argos executes only locally configured provider CLIs; it does not sandbox
  those third-party programs.
- Selected context may be transmitted to those providers. Directory expansion
  rejects common secret, binary, cache, VCS, benchmark, and local-agent paths,
  but users must still review explicit `--file` selections.
- MCP workflow tools require explicit egress/artifact approvals and constrain
  filesystem access to the configured workspace.
- Artifacts can contain provider responses and selected source context. Protect
  the artifact root as project data and do not commit it.
