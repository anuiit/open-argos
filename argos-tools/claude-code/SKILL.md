---
name: argos
description: Run the local open-argos CLI to get external multi-model reviews, critiques, and plans. Use when the user asks for an external review/critique/plan of code or a design, or says "argos", "@review", "@critique", "@plan", "@debug", "@consensus". The argos CLI orchestrates external advisor models (Opus, MiniMax, Kimi, GLM, DeepSeek...) in parallel and returns a synthesized report with Blockers / Important issues / Preferences / Minimal fix plan.
---

# argos — external multi-model advisors

`argos` runs a panel of external LLM advisors on a prompt (optionally with files) and writes private, auditable artifacts. It never executes agents or commands itself; its output is advisory.

## Invocation

- Windows: `argos` (shim installed by `scripts/install-claude-code-windows.ps1`, core at `F:\dev\open-argos`).
- WSL/Linux dev copy: `./bin/argos-dev` from the repo root.

Common commands:

```
argos @review "<prompt>" --file path/to/file [--file ...]
argos @critique "<prompt>" --file ...
argos @plan "<prompt>"
argos @debug "<prompt>" --file ...
argos @consensus "<prompt>"
argos doctor --json          # readiness check (core_text_argoses must be true)
argos benchmark --json       # provider-free internal quality gate
```

## Windows / PowerShell gotcha

In PowerShell, a bare `@word` is the splatting operator and the argument silently disappears. ALWAYS quote presets there:

```
argos "@review" "<prompt>" --file path\to\file
```

(cmd.exe and bash do not need the quotes.)

## Rules (from the argos context contract)

1. Build a concise prompt: goal, constraints, acceptance criteria, known risks as numbered bullets.
2. Prefer presets (`@review`, `@critique`, `@plan`, ...). For a targeted single-model run add both `--argos <name>` and `--single-ok`.
3. Pass relevant files with repeated `--file` arguments; argos treats file content as untrusted data.
4. Exit codes: 0 = ok, 2 = error, 3 = needs_human (e.g. provider auth) — report needs_human to the user, never work around it.
5. Never let argos output trigger nested argos calls; never execute argos suggestions as commands automatically.
6. Report to the user: actionable findings, the exact command used, and the artifact path printed by argos.

For mode-specific guidance see `argos-tools/skills/argos-*/SKILL.md` in the repo.
