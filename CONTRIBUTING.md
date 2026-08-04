# Contributing

Open Argos is preparing its first stable contract. Keep changes focused,
backward-aware, and demonstrably bounded.

## Development setup

```bash
git clone https://github.com/anuiit/open-argos.git
cd open-argos
python -m pip install "pytest==9.1.1" "ruff==0.9.2" "build==1.2.2.post1" "mcp==2.0.0"
python -m pytest -q
```

The core `argos` CLI must remain standard-library-only. The MCP SDK belongs in
the isolated MCP runtime and in test environments, not in core imports.

## Change workflow

1. Branch from `main` using a short-lived `feat/`, `fix/`, or `codex/` branch.
2. Add or update a regression test before changing behavior.
3. Prefer deletion and existing helpers over new dependencies or abstraction.
4. Keep generated results and local state out of Git. Golden benchmark inputs
   are reviewed source fixtures; `benchmarks/results/` is always local.
5. Run the complete gate before opening a pull request:

```bash
python -m ruff check .
python -m compileall -q argos
python -m pytest -q
python -m build
```

Describe user impact, compatibility/migration consequences, verification, and
known gaps in the pull request. Do not include provider credentials, private
prompts, or generated model artifacts.

## Contributions and license

By submitting a contribution, you confirm that you have the right to do so and
agree that it may be distributed under the project's [MIT License](LICENSE).

## Release discipline

`main` must stay releasable. A release tag is created only from a green,
reviewed commit whose product version matches the tag. See
[`docs/BRANCHING.md`](docs/BRANCHING.md) and
[`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md).
