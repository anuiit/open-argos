"""Prepare the isolated MCP runtime and start its stdio server."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Sequence

if __package__:
    from .mcp_runtime import BootstrapError, RuntimeBootstrapResult, bootstrap_runtime
else:  # Direct source-tree execution.
    from mcp_runtime import BootstrapError, RuntimeBootstrapResult, bootstrap_runtime


def package_workspace() -> Path:
    """Return the directory that contains the installed ``argos`` package."""
    return Path(__file__).resolve().parent.parent


def _print_result(result: RuntimeBootstrapResult, *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
        return
    print(
        f"ready={str(result.ready).lower()} "
        f"runtime_python={result.runtime_python} "
        f"server_path={result.server_path}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="argos-mcp",
        description="Prepare and run the isolated Open Argos MCP stdio server.",
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--prepare",
        action="store_true",
        help="install/verify the isolated MCP runtime, print its location, and exit",
    )
    action.add_argument(
        "--check",
        action="store_true",
        help="check the isolated MCP runtime without installing it",
    )
    parser.add_argument("--runtime-dir", help="override the isolated runtime directory")
    parser.add_argument("--json", action="store_true", help="emit machine-readable preparation/check output")
    args = parser.parse_args(argv)
    if args.json and not (args.prepare or args.check):
        parser.error("--json requires --prepare or --check so MCP stdio stays clean")

    try:
        result = bootstrap_runtime(
            package_workspace(),
            check_only=args.check,
            runtime_root=args.runtime_dir,
        )
    except BootstrapError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.prepare or args.check:
        _print_result(result, json_output=args.json)
        return 0 if result.ready else 1

    try:
        completed = subprocess.run(
            [str(result.runtime_python), str(result.server_path)],
            check=False,
        )
    except OSError as exc:
        print(f"Unable to start the MCP server: {exc}", file=sys.stderr)
        return 1
    return completed.returncode


if __name__ == "__main__":  # pragma: no cover - module entrypoint
    raise SystemExit(main())
