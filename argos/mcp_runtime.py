from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


MCP_PACKAGE = "mcp==2.0.0"
MCP_VERSION = "2.0.0"
MARKER_NAME = "runtime.json"
UV_COMMAND_TIMEOUT_SECONDS = 300


class BootstrapError(RuntimeError):
    """Raised when the MCP runtime cannot be prepared safely."""


@dataclass(slots=True)
class RuntimeBootstrapResult:
    workspace: Path
    runtime_root: Path
    runtime_python: Path
    server_path: Path
    marker_path: Path
    ready: bool
    installed_version: str | None
    check_only: bool
    installed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "workspace": str(self.workspace),
            "runtime_root": str(self.runtime_root),
            "runtime_python": str(self.runtime_python),
            "server_path": str(self.server_path),
            "marker_path": str(self.marker_path),
            "ready": self.ready,
            "installed_version": self.installed_version,
            "check_only": self.check_only,
            "installed": self.installed,
        }


def _normalize_path(path: os.PathLike[str] | str) -> Path:
    normalized = Path(os.fspath(path)).expanduser()
    if not normalized.is_absolute():
        normalized = Path.cwd() / normalized
    return Path(os.path.abspath(str(normalized)))


def runtime_python_path(runtime_root: Path, platform_name: str | None = None) -> Path:
    platform = platform_name or os.name
    if platform == "nt":
        return runtime_root / "Scripts" / "python.exe"
    return runtime_root / "bin" / "python"


def default_runtime_root(
    *,
    platform_name: str | None = None,
    environment: dict[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    platform = platform_name or (
        "darwin" if sys.platform == "darwin" else os.name
    )
    env = environment if environment is not None else os.environ
    home_path = home or Path.home()
    if platform == "nt":
        cache_root = Path(
            env.get("LOCALAPPDATA") or home_path / "AppData" / "Local"
        )
    elif platform == "darwin":
        cache_root = home_path / "Library" / "Caches"
    else:
        cache_root = Path(env.get("XDG_CACHE_HOME") or home_path / ".cache")
    python_tag = f"py{sys.version_info.major}{sys.version_info.minor}"
    return (
        cache_root
        / "open-argos"
        / "runtimes"
        / f"mcp-{MCP_VERSION}-{python_tag}"
    )


def _is_link_or_reparse(path: Path) -> bool:
    try:
        value = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:  # pragma: no cover - platform-specific failures
        raise BootstrapError(f"Unable to inspect path {path}: {exc}") from exc
    if stat.S_ISLNK(value.st_mode):
        return True
    if os.name == "nt":
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if getattr(value, "st_file_attributes", 0) & reparse:
            return True
        isjunction = getattr(os.path, "isjunction", None)
        if callable(isjunction) and isjunction(str(path)):
            return True
    return False


def _existing_prefixes(path: Path) -> Iterable[Path]:
    parts = path.parts
    if not parts:
        return ()
    current = Path(parts[0])
    if not current.exists():
        return ()
    prefixes: list[Path] = []
    for part in parts[1:]:
        current = current / part
        if not current.exists():
            break
        prefixes.append(current)
    return prefixes


def _ensure_safe_existing_prefixes(path: Path, label: str) -> None:
    for prefix in _existing_prefixes(path):
        if _is_link_or_reparse(prefix):
            raise BootstrapError(f"{label} must not pass through a symlink or reparse point: {prefix}")
        if not prefix.is_dir():
            raise BootstrapError(f"{label} must be a directory path: {prefix}")


def _validate_existing_directory(path: Path, label: str) -> Path:
    path = _normalize_path(path)
    _ensure_safe_existing_prefixes(path, label)
    if not path.exists():
        raise BootstrapError(f"{label} does not exist: {path}")
    if not path.is_dir():
        raise BootstrapError(f"{label} must be a directory: {path}")
    if _is_link_or_reparse(path):
        raise BootstrapError(f"{label} must not be a symlink or reparse point: {path}")
    return path


def _validate_existing_file(path: Path, label: str) -> Path:
    path = _normalize_path(path)
    _ensure_safe_existing_prefixes(path.parent, f"{label} parent")
    if not path.exists():
        raise BootstrapError(f"{label} does not exist: {path}")
    if not path.is_file():
        raise BootstrapError(f"{label} must be a file: {path}")
    if _is_link_or_reparse(path):
        raise BootstrapError(f"{label} must not be a symlink or reparse point: {path}")
    return path


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f"{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _uv_command(*args: str) -> list[str]:
    return ["uv", *args]


def _run_uv(
    args: Sequence[str],
    cwd: Path | None = None,
    *,
    cache_dir: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = _uv_command(*args)
    environment = None
    if cache_dir is not None:
        environment = os.environ.copy()
        environment.setdefault("UV_CACHE_DIR", str(cache_dir))
    try:
        return subprocess.run(
            command,
            cwd=str(cwd) if cwd is not None else None,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=UV_COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        rendered_command = subprocess.list2cmdline(command)
        raise BootstrapError(
            f"uv timed out after {UV_COMMAND_TIMEOUT_SECONDS} seconds "
            f"while running: {rendered_command}"
        ) from exc
    except OSError as exc:
        raise BootstrapError(f"Unable to launch uv: {exc}") from exc


def _ensure_runtime_venv(
    runtime_root: Path,
    workspace: Path,
    uv_cache_root: Path,
) -> None:
    completed = _run_uv(
        ("venv", "--allow-existing", "--python", sys.executable, str(runtime_root)),
        cwd=workspace,
        cache_dir=uv_cache_root,
    )
    if completed.returncode != 0:
        raise BootstrapError(
            "uv venv failed: " + (completed.stderr.strip() or completed.stdout.strip() or "unknown error")
        )


def _probe_runtime_version(runtime_python: Path) -> str | None:
    if not runtime_python.exists():
        return None
    try:
        probe = subprocess.run(
            [
                str(runtime_python),
                "-c",
                (
                    "import importlib.metadata as md, sys\n"
                    "try:\n"
                    "    import mcp.server, pydantic_core\n"
                    "    sys.stdout.write(md.version('mcp'))\n"
                    "except (ImportError, OSError, md.PackageNotFoundError):\n"
                    "    raise SystemExit(1)\n"
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if probe.returncode != 0:
        return None
    version = probe.stdout.strip()
    return version or None


def _install_mcp(
    runtime_python: Path,
    workspace: Path,
    uv_cache_root: Path,
) -> None:
    completed = _run_uv(
        (
            "pip",
            "install",
            "--reinstall",
            "--python",
            str(runtime_python),
            MCP_PACKAGE,
        ),
        cwd=workspace,
        cache_dir=uv_cache_root,
    )
    if completed.returncode != 0:
        raise BootstrapError(
            "uv pip install failed: " + (completed.stderr.strip() or completed.stdout.strip() or "unknown error")
        )


def bootstrap_runtime(
    workspace: os.PathLike[str] | str = ".",
    *,
    check_only: bool = False,
    runtime_root: os.PathLike[str] | str | None = None,
) -> RuntimeBootstrapResult:
    workspace_path = _validate_existing_directory(_normalize_path(workspace), "workspace")
    selected_runtime = _normalize_path(runtime_root or default_runtime_root())
    _ensure_safe_existing_prefixes(selected_runtime, "runtime path")
    if selected_runtime.exists() and not selected_runtime.is_dir():
        raise BootstrapError(
            f"runtime path must be a directory: {selected_runtime}"
        )
    runtime_python = runtime_python_path(selected_runtime)
    uv_cache_root = selected_runtime.parent / ".uv-cache"
    _ensure_safe_existing_prefixes(uv_cache_root, "uv cache path")
    server_path = _validate_existing_file(workspace_path / "argos" / "mcp_server.py", "server path")
    marker_path = selected_runtime / MARKER_NAME

    installed_version = _probe_runtime_version(runtime_python)
    ready = installed_version == MCP_VERSION and server_path.exists()
    if check_only:
        return RuntimeBootstrapResult(
            workspace=workspace_path,
            runtime_root=selected_runtime,
            runtime_python=runtime_python,
            server_path=server_path,
            marker_path=marker_path,
            ready=ready,
            installed_version=installed_version,
            check_only=True,
            installed=False,
        )

    installed = False
    if installed_version != MCP_VERSION:
        _ensure_runtime_venv(selected_runtime, workspace_path, uv_cache_root)
        _install_mcp(runtime_python, workspace_path, uv_cache_root)
        installed = True
        installed_version = _probe_runtime_version(runtime_python)

    if installed_version != MCP_VERSION:
        raise BootstrapError(
            f"runtime verification failed after installation: expected {MCP_VERSION}, got {installed_version!r}"
        )

    _atomic_write_json(
        marker_path,
        {
            "ready": True,
            "version": installed_version,
            "runtime_python": str(runtime_python),
            "server_path": str(server_path),
        },
    )
    return RuntimeBootstrapResult(
        workspace=workspace_path,
        runtime_root=selected_runtime,
        runtime_python=runtime_python,
        server_path=server_path,
        marker_path=marker_path,
        ready=True,
        installed_version=installed_version,
        check_only=False,
        installed=installed,
    )


def _format_human(result: RuntimeBootstrapResult) -> str:
    return (
        f"ready={str(result.ready).lower()} "
        f"runtime_python={result.runtime_python} "
        f"server_path={result.server_path}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="argos-mcp-runtime")
    parser.add_argument("--workspace", default=".", help="Workspace root to validate and bootstrap.")
    parser.add_argument(
        "--runtime-dir",
        help=(
            "Optional runtime directory. Defaults to a versioned user cache "
            "outside the workspace."
        ),
    )
    parser.add_argument("--check", action="store_true", help="Validate without installing or writing a marker.")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Emit JSON output.")
    args = parser.parse_args(argv)

    try:
        result = bootstrap_runtime(
            args.workspace,
            check_only=args.check,
            runtime_root=args.runtime_dir,
        )
    except BootstrapError as exc:
        if args.json_output:
            print(
                json.dumps(
                    {
                        "ready": False,
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                )
            )
        else:
            print(str(exc), file=sys.stderr)
        return 1

    if args.json_output:
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(_format_human(result))
    return 0 if result.ready else 1


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main())
