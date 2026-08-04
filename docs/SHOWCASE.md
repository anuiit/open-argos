# Reproducible showcase

The public showcase should demonstrate where independent, persistent advice is
useful without claiming that more models automatically produce a better answer.

## A/B protocol

For every case:

1. Freeze the input commit, selected files, task wording, acceptance rubric,
   time budget, and tool permissions.
2. Run control A with Codex alone.
3. Run treatment B with the same Codex workflow plus Argos. Count all Argos
   provider time and failures in the treatment budget.
4. Blind the outputs and score blocker recall, false positives, evidence
   quality, actionable verification, elapsed time, and provider cost separately.
5. Publish raw prompts, sanitized artifacts, scorer version, failures, and
   disagreement. Do not collapse different cohorts into one headline score.

Until this protocol has been run, the examples below are capabilities to
demonstrate, not performance claims.

## 1. Multi-file security review

Use the frozen `review-multifile-security` fixture or an equivalent real pull
request. The valuable Argos behavior is independent cross-file tracing and a
synthesis that retains high-confidence blockers without importing unsupported
claims.

```bash
argos run review \
  "Trace the upload boundary across files. Report only evidenced blockers and exact tests." \
  --dir path/to/project --include "**/*.py" \
  --argos fable --argos kimi3 --synthesize --json
```

Score path-traversal/blocker recall, clean-control precision, cited file
accuracy, and whether the proposed test actually reproduces the defect.

## 2. Persistent architecture council

Use a migration where availability, compatibility, and operational simplicity
pull in different directions. The distinctive behavior is not consensus; it is
retaining dissent and user corrections across turns.

```bash
argos start council --prompt-file decision.md \
  --file constraints.md --file options.md \
  --argos fable --argos kimi3 --json
```

Continue with `argos ask <session-id> ...`, then publish a synthesis only after
the unresolved trade-offs and next experiment are explicit. Score constraint
retention, correction handling, and premature-consensus rate.

## 3. Evidence-gap research

Use a decision whose strongest-looking source does not actually support the
claim. Argos should preserve source IDs, flag weak/vendor evidence, and propose
a bounded next check rather than laundering uncertainty through prose.

```bash
argos research "Which supported migration path fits these constraints today?" \
  --profile current --strict-topic --json
```

Score citation integrity, unsupported-claim detection, source quality, and the
cost of the next recommended experiment.

## Publication checklist

- Include the Codex-only control, not only successful Argos runs.
- Include timeouts, `needs_human`, `provider_error`, and `outcome_unknown` in
  denominators.
- Remove credentials and private source, but document every redaction.
- Keep the benchmark corpus and generated results out of the Python package.
- Link each headline statement to a reproducible case and scorer version.
