"""Run the Argos CLI with ``python -m argos``."""

from .argos import cli_main


if __name__ == "__main__":  # pragma: no cover - module entrypoint
    raise SystemExit(cli_main())
