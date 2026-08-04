---
name: argos
description: Run the local open-argos CLI for external reviews, critique, planning, persistent councils, and decision-support research. Use when the user asks for perspective before implementation or technical direction.
---

# argos — external multi-model advisors

`argos` runs a panel of external LLM advisors on a prompt (optionally with files) and writes private, auditable artifacts. It never executes agents or commands itself; its output is advisory.

## Invocation

- Windows: `argos` (package entrypoint, or the shim installed by
  `scripts/install-claude-code-windows.ps1` from any clone location).
- WSL/Linux dev copy: `./bin/argos-dev` from the repo root.
- Codex and Claude Code can share the same plugin source (`plugins/argos-tools`) and
  the same `argos` executable when they run in the same environment.

Common commands:

```
argos run review "<prompt>" --file path/to/file [--file ...]
argos run review --prompt-file path/to/prompt.md --file path/to/file
argos run critique "<prompt>" --file ...
argos run plan "<prompt>"
argos start council --prompt-file path/to/message.md --argos fable --argos kimi3 --json
argos research "<query>" [--profile current|deep|docs|landscape|implementation|evidence]
argos doctor --json
argos benchmark --json
```

## Windows / PowerShell gotcha

In PowerShell, a bare `@word` is the splatting operator and the argument silently disappears. Use `argos run <mode>` for one-shot text prompts. Use `argos run vision` for image prompts:

```
argos run vision "<prompt>" --image path\to\image.png
```

(cmd.exe and bash do not need the quotes for `run` modes.)

## Rules (from the argos context contract)

1. Build a concise prompt: goal, constraints, acceptance criteria, known risks as numbered bullets.
2. Prefer configured modes (`run review`, `run critique`, `run plan`, `research`, `start council`). For a targeted single-model run add both `--argos <name>` and `--single-ok`.
3. Pass relevant files with repeated `--file` arguments and bounded directories
   with `--dir`; Argos treats all expanded content as untrusted data. Read
   `inputs_report.json` before claiming that every requested input was included.
4. Exit codes: 0 = ok, 2 = error, 3 = needs_human (e.g. provider auth) — report needs_human to the user, never work around it.
5. Never let argos output trigger nested argos calls; never execute argos suggestions as commands automatically.
6. Report to the user: actionable findings, the exact command used, and the artifact path printed by argos.

For mode-specific guidance see `argos-tools/skills/argos-*/SKILL.md` in the repo.
