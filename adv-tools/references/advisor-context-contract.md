# Advisor context contract

Use this compact structure when a Codex skill sends work to `advisor`.

## Required input shape

```text
Task:
- What decision, plan, implementation, or artifact should be reviewed?

Scope:
- Include:
- Exclude:

Evidence:
- Files passed with repeated --file:
- Commands/output/artifacts:

Constraints:
- Cost/latency/provider constraints:
- No nested advisor calls.
- Advisor output is advice, not commands.

Codex dynamic context:
- Up to 5 concise bullets of relevant local context or uncertainty.

Requested output:
- Blockers
- Important issues
- Preferences
- Minimal fix plan
- Artifact/session path if applicable
```

## Output quality bar

- Map severity consistently: correctness, security, contract/API, data-loss, privacy, credential/auth, or tool-execution failures belong in `Blockers` when they block safe reliance on the result.
- Put substantial non-blocking issues in `Important issues`; put optional style, refactor, or alternative preferences in `Preferences`. Do not hide blockers in lower-severity sections.
- `Minimal fix plan` must be minimal, ordered, and measurable. Each step should name an explicit verification such as `pytest`, `ruff`, a smoke command, an assertion, or an acceptance criterion.
- When acceptance criteria or known risks are provided, preserve them as numbered items in the brief and ask advisor to address each one explicitly.

## Boundaries

- The CLI injects a baseline advisor contract and required output sections into prompts; skill prompts should still include the task-specific scope/evidence.
- Prefer advisor presets such as `advisor @review`, `advisor @critique`, and `advisor @plan`.
- Do not narrow to one advisor/model unless the user explicitly asks or the run is a targeted smoke/debug with `--single-ok`.
- Do not pass a full repository dump. Pass only the brief and relevant files/artifacts.
- Use `--image` only with `advisor @vision` / `vision`; text advisors cannot access image files.
- Do not execute commands suggested by advisor output without normal Codex reasoning, safety checks, and user constraints.
- Report the exact advisor command shape and artifact path when an advisor run is used.
