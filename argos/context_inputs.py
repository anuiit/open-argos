"""Safe, deterministic expansion of file and directory context inputs.

This module deliberately does not read configuration or CLI arguments.  The
caller supplies all inputs and limits, which keeps expansion straightforward to
test and reusable by both the CLI and a future MCP adapter.
"""

from __future__ import annotations

import fnmatch
import os
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Literal, Sequence

DEFAULT_MAX_FILES = 100
DEFAULT_MAX_FILE_CHARS = 60_000
DEFAULT_MAX_TOTAL_CHARS = 180_000

# These are hard safety exclusions.  --include must never make them eligible.
DENIED_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".argos",
        ".aws",
        ".config",
        ".gnupg",
        ".hg",
        ".mypy_cache",
        ".nox",
        ".omc",
        ".omx",
        ".pytest_cache",
        ".ruff_cache",
        ".svn",
        ".ssh",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "benchmarks",
        "coverage",
        "dist",
        "node_modules",
        "target",
        "venv",
    }
)
DENIED_SECRET_PATTERNS = (
    ".env",
    ".env.*",
    "*.key",
    "*.kdbx",
    "*.p12",
    "*.pem",
    "*.pfx",
    "*credentials*",
    "credentials.json",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_ed25519_*",
    "id_rsa",
    "id_rsa_*",
    "secrets.json",
)
DENIED_BINARY_SUFFIXES = frozenset(
    {
        ".7z",
        ".a",
        ".avi",
        ".bin",
        ".bmp",
        ".class",
        ".dll",
        ".dylib",
        ".eot",
        ".exe",
        ".gif",
        ".gz",
        ".ico",
        ".jar",
        ".jpeg",
        ".jpg",
        ".lockb",
        ".mov",
        ".mp3",
        ".mp4",
        ".o",
        ".otf",
        ".pdf",
        ".png",
        ".pyc",
        ".so",
        ".tar",
        ".tiff",
        ".ttf",
        ".wav",
        ".webm",
        ".webp",
        ".woff",
        ".woff2",
        ".zip",
    }
)

SourceKind = Literal["file", "directory"]


class ContextInputError(ValueError):
    """Raised when an explicit input is invalid or unsafe."""


class ContextLimitError(ContextInputError):
    """Raised instead of silently truncating a context expansion."""


@dataclass(frozen=True)
class IncludedContext:
    path: str
    source: SourceKind
    root: str | None
    relative_path: str | None
    chars: int


@dataclass(frozen=True)
class SkippedContext:
    path: str
    source: SourceKind
    reason: str
    root: str | None = None
    relative_path: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class ContextLimits:
    max_files: int
    max_file_chars: int
    max_total_chars: int


@dataclass(frozen=True)
class ContextExpansionReport:
    included: tuple[IncludedContext, ...]
    skipped: tuple[SkippedContext, ...]
    total_chars: int
    limits: ContextLimits

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return asdict(self)


@dataclass(frozen=True)
class ContextExpansion:
    paths: tuple[Path, ...]
    report: ContextExpansionReport


@dataclass(frozen=True)
class _Candidate:
    path: Path
    source: SourceKind
    root: Path | None = None
    relative_path: str | None = None


def _display_path(path: Path) -> str:
    return str(path)


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve(strict=True)))


def _is_reparse_stat(value: os.stat_result) -> bool:
    attributes = getattr(value, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _lstat(path: Path) -> os.stat_result:
    try:
        return path.lstat()
    except OSError as exc:
        raise ContextInputError(
            f"Could not inspect context input {path}: {exc}"
        ) from exc


def _is_link_or_reparse(path: Path, value: os.stat_result | None = None) -> bool:
    value = value or _lstat(path)
    return stat.S_ISLNK(value.st_mode) or _is_reparse_stat(value)


def _matches_pattern(relative_path: str, name: str, pattern: str) -> bool:
    normalized = pattern.replace("\\", "/")
    candidates = (relative_path, name)
    if any(fnmatch.fnmatchcase(candidate, normalized) for candidate in candidates):
        return True
    # Users naturally expect **/*.py to include a root-level file.py too.
    while normalized.startswith("**/"):
        normalized = normalized[3:]
        if any(fnmatch.fnmatchcase(candidate, normalized) for candidate in candidates):
            return True
    return False


def _matches_any(relative_path: str, name: str, patterns: Sequence[str]) -> bool:
    return any(_matches_pattern(relative_path, name, pattern) for pattern in patterns)


def _denied_directory_component(path: Path) -> str | None:
    for part in path.parts:
        if part.casefold() in DENIED_DIRECTORY_NAMES:
            return part
    return None


def _secret_pattern(name: str) -> str | None:
    folded = name.casefold()
    for pattern in DENIED_SECRET_PATTERNS:
        if fnmatch.fnmatchcase(folded, pattern.casefold()):
            return pattern
    return None


def _binary_reason(path: Path, data: bytes) -> str | None:
    if path.suffix.casefold() in DENIED_BINARY_SUFFIXES:
        return "binary_extension"
    if b"\x00" in data:
        return "binary_nul"
    return None


def _has_too_many_control_chars(text: str) -> bool:
    if not text:
        return False
    controls = sum(1 for char in text if ord(char) < 32 and char not in "\t\n\r")
    return controls / len(text) > 0.30


def _read_and_count(
    path: Path, max_file_chars: int
) -> tuple[int | None, str | None, str | None]:
    """Return (character count, skip reason, detail), reading UTF-8 strictly."""
    try:
        if _is_link_or_reparse(path):
            return None, "symlink_or_reparse", "link detected immediately before read"
        size = path.stat().st_size
        with path.open("rb") as handle:
            sample = handle.read(8192)
            binary_reason = _binary_reason(path, sample)
            if binary_reason:
                return None, binary_reason, None
            if size > max_file_chars * 4:
                raise ContextLimitError(
                    f"Context file exceeds max_file_chars={max_file_chars}: {path} "
                    f"({size} bytes cannot fit in {max_file_chars} UTF-8 characters)"
                )
            remainder = handle.read()
    except ContextLimitError:
        raise
    except OSError as exc:
        return None, "unreadable", str(exc)

    data = sample + remainder
    binary_reason = _binary_reason(path, data)
    if binary_reason:
        return None, binary_reason, None
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        return None, "invalid_utf8", f"byte {exc.start}: {exc.reason}"
    if _has_too_many_control_chars(text):
        return None, "binary_control_chars", None
    if len(text) > max_file_chars:
        raise ContextLimitError(
            f"Context file exceeds max_file_chars={max_file_chars}: {path} "
            f"({len(text)} characters)"
        )
    return len(text), None, None


def _resolve_explicit_path(
    raw: str | os.PathLike[str], expected: Literal["file", "directory"]
) -> Path:
    path = Path(raw).expanduser()
    try:
        value = path.lstat()
    except FileNotFoundError as exc:
        raise ContextInputError(f"Context {expected} not found: {path}") from exc
    except OSError as exc:
        raise ContextInputError(
            f"Could not inspect context {expected} {path}: {exc}"
        ) from exc
    if _is_link_or_reparse(path, value):
        raise ContextInputError(
            f"Context {expected} must not be a symlink or reparse point: {path}"
        )
    predicate = stat.S_ISREG if expected == "file" else stat.S_ISDIR
    if not predicate(value.st_mode):
        raise ContextInputError(f"Context input is not a regular {expected}: {path}")
    try:
        return path.resolve(strict=True)
    except OSError as exc:
        raise ContextInputError(
            f"Could not resolve context {expected} {path}: {exc}"
        ) from exc


def _walk_directory(root: Path, skipped: list[SkippedContext]) -> Iterable[_Candidate]:
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as iterator:
                entries = sorted(
                    iterator, key=lambda entry: (entry.name.casefold(), entry.name)
                )
        except OSError as exc:
            relative = current.relative_to(root).as_posix() if current != root else "."
            skipped.append(
                SkippedContext(
                    path=_display_path(current),
                    source="directory",
                    reason="unreadable_directory",
                    root=_display_path(root),
                    relative_path=relative,
                    detail=str(exc),
                )
            )
            continue

        child_directories: list[Path] = []
        for entry in entries:
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            try:
                value = entry.stat(follow_symlinks=False)
            except OSError as exc:
                skipped.append(
                    SkippedContext(
                        path=_display_path(path),
                        source="directory",
                        reason="unreadable",
                        root=_display_path(root),
                        relative_path=relative,
                        detail=str(exc),
                    )
                )
                continue
            if _is_link_or_reparse(path, value):
                skipped.append(
                    SkippedContext(
                        path=_display_path(path),
                        source="directory",
                        reason="symlink_or_reparse",
                        root=_display_path(root),
                        relative_path=relative,
                    )
                )
                continue
            if stat.S_ISDIR(value.st_mode):
                if entry.name.casefold() in DENIED_DIRECTORY_NAMES:
                    skipped.append(
                        SkippedContext(
                            path=_display_path(path),
                            source="directory",
                            reason="denied_directory",
                            root=_display_path(root),
                            relative_path=relative,
                        )
                    )
                else:
                    child_directories.append(path)
                continue
            if stat.S_ISREG(value.st_mode):
                try:
                    resolved = path.resolve(strict=True)
                except OSError as exc:
                    skipped.append(
                        SkippedContext(
                            path=_display_path(path),
                            source="directory",
                            reason="unresolvable",
                            root=_display_path(root),
                            relative_path=relative,
                            detail=str(exc),
                        )
                    )
                    continue
                if not resolved.is_relative_to(root):
                    skipped.append(
                        SkippedContext(
                            path=_display_path(path),
                            source="directory",
                            reason="outside_root",
                            root=_display_path(root),
                            relative_path=relative,
                        )
                    )
                    continue
                yield _Candidate(resolved, "directory", root, relative)
            else:
                skipped.append(
                    SkippedContext(
                        path=_display_path(path),
                        source="directory",
                        reason="not_regular_file",
                        root=_display_path(root),
                        relative_path=relative,
                    )
                )
        stack.extend(reversed(child_directories))


def _validate_limits(
    max_files: int, max_file_chars: int, max_total_chars: int
) -> ContextLimits:
    limits = ContextLimits(max_files, max_file_chars, max_total_chars)
    for name, value in asdict(limits).items():
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ContextInputError(f"{name} must be a positive integer, got {value!r}")
    return limits


def expand_context_inputs(
    *,
    files: Sequence[str | os.PathLike[str]] = (),
    directories: Sequence[str | os.PathLike[str]] = (),
    includes: Sequence[str] = (),
    excludes: Sequence[str] = (),
    max_files: int = DEFAULT_MAX_FILES,
    max_file_chars: int = DEFAULT_MAX_FILE_CHARS,
    max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS,
) -> ContextExpansion:
    """Expand context inputs without following links or silently truncating.

    Includes and excludes are shell-style patterns matched against both the
    POSIX relative path and basename.  Hard deny lists always take precedence.
    Files that cannot safely become text are recorded in ``report.skipped``.
    Invalid explicit paths and exceeded limits raise ``ContextInputError``.
    """
    limits = _validate_limits(max_files, max_file_chars, max_total_chars)
    include_patterns = tuple(includes)
    exclude_patterns = tuple(excludes)
    skipped: list[SkippedContext] = []
    candidates: list[_Candidate] = []

    for raw in files:
        resolved = _resolve_explicit_path(raw, "file")
        candidates.append(_Candidate(resolved, "file"))

    roots: list[Path] = []
    seen_roots: set[str] = set()
    for raw in directories:
        root = _resolve_explicit_path(raw, "directory")
        key = _path_key(root)
        if key in seen_roots:
            skipped.append(
                SkippedContext(
                    path=_display_path(root),
                    source="directory",
                    reason="duplicate_root",
                    root=_display_path(root),
                )
            )
            continue
        seen_roots.add(key)
        roots.append(root)
    for root in sorted(roots, key=lambda item: (_path_key(item), str(item))):
        denied_part = (
            root.name if root.name.casefold() in DENIED_DIRECTORY_NAMES else None
        )
        if denied_part:
            skipped.append(
                SkippedContext(
                    path=_display_path(root),
                    source="directory",
                    reason="denied_directory",
                    root=_display_path(root),
                    detail=f"matched directory component {denied_part!r}",
                )
            )
            continue
        candidates.extend(_walk_directory(root, skipped))

    # Candidate sorting makes results independent from CLI argument order and
    # filesystem enumeration order.  Explicit --file wins duplicate ownership.
    candidates.sort(
        key=lambda item: (
            0 if item.source == "file" else 1,
            _path_key(item.path),
            str(item.path),
        )
    )
    included: list[IncludedContext] = []
    accepted_paths: list[Path] = []
    seen_files: set[str] = set()
    total_chars = 0

    for candidate in candidates:
        path = candidate.path
        relative = candidate.relative_path or path.name
        common = {
            "path": _display_path(path),
            "source": candidate.source,
            "root": _display_path(candidate.root) if candidate.root else None,
            "relative_path": candidate.relative_path,
        }
        key = _path_key(path)
        if key in seen_files:
            skipped.append(SkippedContext(**common, reason="duplicate"))
            continue
        seen_files.add(key)

        relative_parent = Path(relative).parent
        denied_part = (
            _denied_directory_component(relative_parent)
            if candidate.source == "directory"
            else None
        )
        if denied_part:
            skipped.append(
                SkippedContext(
                    **common,
                    reason="denied_directory",
                    detail=f"matched directory component {denied_part!r}",
                )
            )
            continue
        secret_pattern = _secret_pattern(path.name)
        if secret_pattern:
            skipped.append(
                SkippedContext(
                    **common,
                    reason="secret_pattern",
                    detail=f"matched {secret_pattern!r}",
                )
            )
            continue
        if (
            candidate.source == "directory"
            and include_patterns
            and not _matches_any(relative, path.name, include_patterns)
        ):
            skipped.append(SkippedContext(**common, reason="not_included"))
            continue
        if (
            candidate.source == "directory"
            and exclude_patterns
            and _matches_any(relative, path.name, exclude_patterns)
        ):
            skipped.append(SkippedContext(**common, reason="excluded_pattern"))
            continue

        chars, reason, detail = _read_and_count(path, limits.max_file_chars)
        if reason is not None:
            skipped.append(SkippedContext(**common, reason=reason, detail=detail))
            continue
        assert chars is not None
        if len(accepted_paths) + 1 > limits.max_files:
            raise ContextLimitError(
                f"Context expansion exceeds max_files={limits.max_files}; "
                "narrow --dir with --include/--exclude or raise the configured limit"
            )
        if total_chars + chars > limits.max_total_chars:
            raise ContextLimitError(
                f"Context expansion exceeds max_total_chars={limits.max_total_chars}: "
                f"adding {path} ({chars} characters) would reach {total_chars + chars}"
            )
        accepted_paths.append(path)
        total_chars += chars
        included.append(IncludedContext(**common, chars=chars))

    paired = sorted(
        zip(accepted_paths, included, strict=True),
        key=lambda item: (_path_key(item[0]), str(item[0])),
    )
    accepted_paths = [item[0] for item in paired]
    included = [item[1] for item in paired]
    skipped.sort(
        key=lambda item: (
            os.path.normcase(item.path),
            item.reason,
            item.source,
            item.relative_path or "",
        )
    )
    report = ContextExpansionReport(
        tuple(included), tuple(skipped), total_chars, limits
    )
    return ContextExpansion(tuple(accepted_paths), report)
