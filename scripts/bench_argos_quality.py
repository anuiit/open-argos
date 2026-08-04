#!/usr/bin/env python3
"""Public entrypoint for the versioned Argos output benchmark.

This wrapper loads the real implementation from ``argos_benchmark_v2.py`` and
re-exports every public symbol so older imports keep working.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
MODULE_PATH = SCRIPT_DIR / "argos_benchmark_v2.py"


def _load_impl() -> object:
    spec = importlib.util.spec_from_file_location(
        "argos_benchmark_v2_public", MODULE_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load benchmark module: {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_impl = _load_impl()
for _name in dir(_impl):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_impl, _name)

main = _impl.cli_main


if __name__ == "__main__":
    raise SystemExit(main())
