"""Policy and workflow adapter for the local Open Argos MCP server.

This module deliberately has no MCP transport dependency.  It converts the
typed contract into calls to the existing Argos core while enforcing the
security, approval, idempotency, and disclosure boundaries required by both
Codex and Claude Code hosts.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import stat
import sys
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Iterator, TypeVar

from pydantic import ValidationError

MODULE_DIR = Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

import argos as core  # type: ignore[import-not-found]  # noqa: E402
import context_inputs  # noqa: E402
import mcp_contract as contract  # noqa: E402

ApprovalKind = contract.ApprovalKind
EnvelopeStatus = contract.EnvelopeStatus
ErrorClass = contract.ErrorClass
McpApproval = contract.McpApproval
McpEnvelope = contract.McpEnvelope
McpError = contract.McpError
ToolName = contract.ToolName

MAX_INLINE_TEXT = 60_000
MAX_RESULT_TEXT = 20_000
MAX_RESOURCE_TEXT = 180_000
MAX_INTERNAL_JSON = 2_000_000
REQUEST_STATE_VERSION = 1
SESSION_ID_RE = re.compile(r"adv_[0-9T]{15}_[0-9a-f]{8}\Z")
RESOURCE_PATTERNS = (
    re.compile(
        r"argos://sessions/(?P<id>[A-Za-z0-9][A-Za-z0-9._:-]{0,127})/"
        r"(?P<tail>summary|artifacts|turns/(?P<turn>[1-9][0-9]{0,5}))\Z"
    ),
    re.compile(
        r"argos://councils/(?P<id>[A-Za-z0-9][A-Za-z0-9._:-]{0,127})/"
        r"(?P<tail>summary|turns/(?P<turn>[1-9][0-9]{0,5}))\Z"
    ),
    re.compile(
        r"argos://runs/(?P<id>[A-Za-z0-9][A-Za-z0-9._:-]{0,127})/"
        r"(?P<tail>manifest|coverage|findings)\Z"
    ),
)

T = TypeVar("T")


class AdapterFault(RuntimeError):
    """Stable, sanitized adapter failure."""

    def __init__(
        self,
        error_class: ErrorClass,
        message: str,
        *,
        retryable: bool = False,
        outcome_unknown: bool = False,
    ) -> None:
        super().__init__(message)
        self.error_class = error_class
        self.retryable = retryable
        self.outcome_unknown = outcome_unknown


class ResourceNotFoundError(LookupError):
    """Uniform resource miss that does not reveal path existence."""


def _request_key(request_id: str) -> str:
    return hashlib.sha256(request_id.encode("utf-8")).hexdigest()


def _canonical_request_hash(tool: ToolName, request: Any) -> str:
    raw = json.dumps(
        {"tool": tool.value, "request": request.model_dump(mode="json")},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _selection_fingerprint(rows: list[dict[str, Any]]) -> str:
    raw = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _is_link_or_reparse(path: Path) -> bool:
    try:
        value = path.lstat()
    except OSError:
        return True
    if stat.S_ISLNK(value.st_mode):
        return True
    attributes = getattr(value, "st_file_attributes", 0)
    return bool(
        attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _bounded_text(text: str, limit: int) -> tuple[str, bool]:
    return text[:limit], len(text) > limit


def _safe_status(value: Any) -> str:
    status = str(value or "unknown").casefold()
    return status if status in {
        "active",
        "alive",
        "cancelled",
        "complete",
        "completed",
        "dead",
        "error",
        "failed",
        "needs_human",
        "ok",
        "outcome_unknown",
        "partial",
        "rebuild_pending",
        "skipped",
        "unknown",
    } else "unknown"


def _safe_json_value(value: Any, *, depth: int = 0) -> Any:
    """Bound arbitrary artifact JSON before returning it through MCP."""

    if depth > 8:
        return None
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:MAX_RESULT_TEXT]
    if isinstance(value, list):
        return [_safe_json_value(item, depth=depth + 1) for item in value[:200]]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in list(value.items())[:200]:
            name = str(key)[:120]
            lowered = name.casefold()
            if any(
                token in lowered
                for token in (
                    "api_key",
                    "authorization",
                    "command",
                    "credential",
                    "environment",
                    "password",
                    "provider_session",
                    "raw_path",
                    "secret",
                    "token",
                )
            ):
                continue
            result[name] = _safe_json_value(item, depth=depth + 1)
        return result
    return str(value)[:MAX_RESULT_TEXT]


def _approval_field(kind: ApprovalKind) -> str:
    if kind == ApprovalKind.force_insufficient_synthesis:
        return "force_model_on_insufficient"
    return kind.value


def _approval_for(request: Any, kinds: list[ApprovalKind]) -> McpApproval:
    granted = [
        kind for kind in kinds if bool(getattr(request, _approval_field(kind), False))
    ]
    return McpApproval(
        required=bool(set(kinds) - set(granted)),
        kinds=kinds,
        granted=granted,
    )


def _error_envelope(
    request_id: str,
    *,
    summary: str,
    error_class: ErrorClass,
    message: str,
    approval: McpApproval | None = None,
    session_id: str | None = None,
    artifact_dir: str | None = None,
    result: dict[str, Any] | None = None,
    retryable: bool = False,
    outcome_unknown: bool = False,
) -> dict[str, Any]:
    return McpEnvelope(
        request_id=request_id,
        status=EnvelopeStatus.failed,
        summary=summary,
        session_id=session_id,
        artifact_dir=artifact_dir,
        result=result or {},
        approval=approval or McpApproval(),
        error=McpError(
            error_class=error_class,
            message=message,
            retryable=retryable,
            outcome_unknown=outcome_unknown,
        ),
    ).model_dump(mode="json", by_alias=True)


def _success_envelope(
    request_id: str,
    *,
    status: EnvelopeStatus,
    summary: str,
    result: dict[str, Any],
    approval: McpApproval | None = None,
    session_id: str | None = None,
    artifact_dir: str | None = None,
) -> dict[str, Any]:
    return McpEnvelope(
        request_id=request_id,
        status=status,
        summary=summary,
        session_id=session_id,
        artifact_dir=artifact_dir,
        result=result,
        approval=approval or McpApproval(),
    ).model_dump(mode="json", by_alias=True)


class ArgosMCPAdapter:
    """Client-neutral adapter with no stdout side effects."""

    def __init__(
        self,
        workspace: Path | str | None = None,
        *,
        config_path: Path | str | None = None,
    ) -> None:
        raw_workspace = Path(
            workspace or os.environ.get("ARGOS_WORKSPACE") or Path.cwd()
        ).expanduser()
        try:
            resolved_workspace = raw_workspace.resolve(strict=True)
        except OSError as exc:
            raise ValueError("ARGOS_WORKSPACE must be an existing directory") from exc
        if (
            not resolved_workspace.is_dir()
            or _is_link_or_reparse(resolved_workspace)
        ):
            raise ValueError(
                "ARGOS_WORKSPACE must be a regular directory, not a link or reparse point"
            )
        self.workspace = resolved_workspace
        selected_config = (
            config_path
            or os.environ.get("ARGOS_MCP_CONFIG")
            or os.environ.get("ARGOS_CONFIG")
            or core.DEFAULT_CONFIG_PATH
        )
        self.config_path = Path(selected_config).expanduser()
        self.state_root = self.workspace / ".argos" / "mcp"
        self.sessions_root = self.state_root / "sessions"
        self.runs_root = self.state_root / "runs"
        self.requests_root = self.state_root / "requests"
        self._session_locks: dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------
    # Trusted configuration and provider allowlists
    # ------------------------------------------------------------------

    def _load_config(self) -> dict[str, Any]:
        return core.load_config(self.config_path)

    def _allowed_argoses(self, cfg: dict[str, Any]) -> set[str]:
        configured = {
            str(name)
            for name, chain in cfg.get("models", {}).items()
            if isinstance(chain, list) and chain
        }
        raw = os.environ.get("ARGOS_MCP_ALLOWED_ARGOSES")
        if raw is None:
            return configured
        narrowed = {item.strip() for item in raw.split(",") if item.strip()}
        return configured.intersection(narrowed)

    def _require_allowed_argoses(
        self,
        names: list[str],
        cfg: dict[str, Any],
    ) -> None:
        allowed = self._allowed_argoses(cfg)
        if not names:
            raise AdapterFault(
                ErrorClass.invalid_input,
                "No allowed Argos provider is configured for this operation.",
            )
        if any(name not in allowed for name in names):
            raise AdapterFault(
                ErrorClass.invalid_input,
                "The requested Argos provider is not allowed by this MCP server.",
            )

    def _verify_session_provider_state(
        self,
        session: dict[str, Any],
        snapshot: dict[str, Any],
        selected: list[str],
    ) -> dict[str, Any]:
        """Ensure resumable provider commands still come from trusted config."""

        trusted = self._load_config()
        self._require_allowed_argoses(selected, trusted)
        trusted_models = trusted.get("models", {})
        snapshot_models = snapshot.get("models", {})
        states = session.get("argoses") or {}
        for name in selected:
            trusted_chain = trusted_models.get(name)
            snapshot_chain = snapshot_models.get(name)
            if trusted_chain != snapshot_chain:
                raise AdapterFault(
                    ErrorClass.session_conflict,
                    "The session provider configuration no longer matches the "
                    "trusted MCP configuration.",
                )
            state = states.get(name)
            if not isinstance(state, dict):
                raise AdapterFault(
                    ErrorClass.session_conflict,
                    "The session provider state is incomplete.",
                )
            candidate = state.get("candidate")
            if candidate is not None and candidate not in (trusted_chain or []):
                raise AdapterFault(
                    ErrorClass.session_conflict,
                    "The session provider state does not match an allowed candidate.",
                )
        return trusted

    # ------------------------------------------------------------------
    # Workspace path containment
    # ------------------------------------------------------------------

    def _lexical_workspace_path(self, raw: str) -> Path:
        if not isinstance(raw, str) or not raw.strip() or raw.strip() != raw:
            raise AdapterFault(
                ErrorClass.invalid_input,
                "Context paths must be non-empty trimmed strings.",
            )
        if "\0" in raw or raw.startswith("~"):
            raise AdapterFault(
                ErrorClass.path_outside_workspace,
                "The requested path is not allowed by the workspace policy.",
            )
        normalized = raw.replace("\\", "/")
        if (
            normalized.startswith("//")
            or normalized.casefold().startswith(("//?/", "//./"))
        ):
            raise AdapterFault(
                ErrorClass.path_outside_workspace,
                "UNC and device paths are not allowed.",
            )
        segments = [part for part in normalized.split("/") if part not in {"", "."}]
        if ".." in segments:
            raise AdapterFault(
                ErrorClass.path_outside_workspace,
                "Parent traversal is not allowed in workspace paths.",
            )
        for index, segment in enumerate(segments):
            drive = index == 0 and re.fullmatch(r"[A-Za-z]:", segment)
            if ":" in segment and not drive:
                raise AdapterFault(
                    ErrorClass.path_outside_workspace,
                    "Alternate data streams and drive-relative paths are not allowed.",
                )
        path = Path(raw)
        return path if path.is_absolute() else self.workspace / path

    def _existing_workspace_path(
        self,
        raw: str,
        *,
        expected: str,
        allow_denied_components: bool = False,
    ) -> Path:
        candidate = self._lexical_workspace_path(raw)
        try:
            resolved = candidate.resolve(strict=True)
            relative = resolved.relative_to(self.workspace)
        except (OSError, ValueError) as exc:
            raise AdapterFault(
                ErrorClass.path_outside_workspace,
                "The requested path is outside the allowed workspace.",
            ) from exc
        current = self.workspace
        for part in relative.parts:
            current = current / part
            if _is_link_or_reparse(current):
                raise AdapterFault(
                    ErrorClass.path_outside_workspace,
                    "Links and reparse points are not allowed in workspace paths.",
                )
        if not allow_denied_components and any(
            part.casefold() in context_inputs.DENIED_DIRECTORY_NAMES
            for part in relative.parts[:-1] if expected == "file"
        ):
            raise AdapterFault(
                ErrorClass.path_outside_workspace,
                "Protected workspace directories cannot be used as model context.",
            )
        if not allow_denied_components and expected == "directory" and any(
            part.casefold() in context_inputs.DENIED_DIRECTORY_NAMES
            for part in relative.parts
        ):
            raise AdapterFault(
                ErrorClass.path_outside_workspace,
                "Protected workspace directories cannot be used as model context.",
            )
        if expected == "file" and not resolved.is_file():
            raise AdapterFault(ErrorClass.invalid_input, "A regular context file is required.")
        if expected == "directory" and not resolved.is_dir():
            raise AdapterFault(
                ErrorClass.invalid_input,
                "A regular context directory is required.",
            )
        return resolved

    def _safe_existing_owned_path(self, path: Path, *, root: Path) -> Path:
        try:
            resolved_root = root.resolve(strict=True)
            root_relative = resolved_root.relative_to(self.workspace)
            resolved = path.resolve(strict=True)
            relative = resolved.relative_to(resolved_root)
        except (OSError, ValueError) as exc:
            raise ResourceNotFoundError("Argos resource not found") from exc
        current = self.workspace
        for part in root_relative.parts:
            current = current / part
            if _is_link_or_reparse(current):
                raise ResourceNotFoundError("Argos resource not found")
        current = resolved_root
        for part in relative.parts:
            current = current / part
            if _is_link_or_reparse(current):
                raise ResourceNotFoundError("Argos resource not found")
        return resolved

    def _ensure_owned_directory(self, path: Path) -> None:
        try:
            relative = path.relative_to(self.workspace)
        except ValueError as exc:
            raise AdapterFault(
                ErrorClass.path_outside_workspace,
                "Argos state must remain inside the workspace.",
            ) from exc
        current = self.workspace
        for part in relative.parts:
            current = current / part
            if current.exists():
                if _is_link_or_reparse(current) or not current.is_dir():
                    raise AdapterFault(
                        ErrorClass.path_outside_workspace,
                        "Argos state path contains an unsafe filesystem entry.",
                    )
            else:
                current.mkdir(mode=0o700)
        if os.name != "nt":
            os.chmod(path, 0o700)

    def _relative_artifact(self, raw: str | os.PathLike[str]) -> str:
        path = Path(raw)
        try:
            resolved = self._safe_existing_owned_path(path, root=self.state_root)
            return resolved.relative_to(self.workspace).as_posix()
        except ResourceNotFoundError as exc:
            raise AdapterFault(
                ErrorClass.internal_error,
                "Argos returned an artifact outside its MCP state root.",
            ) from exc

    def _prepare_context(self, request: Any) -> dict[str, Any]:
        if request.context.follow_symlinks:
            raise AdapterFault(
                ErrorClass.invalid_input,
                "follow_symlinks is not supported by the Argos MCP bridge.",
            )
        files = [
            self._existing_workspace_path(item, expected="file")
            for item in request.context.files
        ]
        directories = [
            self._existing_workspace_path(item, expected="directory")
            for item in request.context.directories
        ]
        images = [
            self._existing_workspace_path(item, expected="file")
            for item in request.images
        ]
        try:
            context_inputs.expand_context_inputs(
                files=files,
                directories=directories,
                includes=request.context.include,
                excludes=request.context.exclude,
                max_files=request.context.max_files,
                max_file_chars=request.context.max_file_chars,
                max_total_chars=request.context.max_total_chars,
            )
            core.validated_image_paths([str(path) for path in images])
        except context_inputs.ContextLimitError as exc:
            raise AdapterFault(
                ErrorClass.context_limit_exceeded,
                "The selected context exceeds the configured MCP limits.",
            ) from exc
        except (context_inputs.ContextInputError, SystemExit, OSError) as exc:
            raise AdapterFault(
                ErrorClass.invalid_input,
                "One or more context inputs are invalid or unsafe.",
            ) from exc
        return {
            "file": [str(path) for path in files],
            "directory": [str(path) for path in directories],
            "include": list(request.context.include),
            "exclude": list(request.context.exclude),
            "max_files": request.context.max_files,
            "max_file_chars": request.context.max_file_chars,
            "max_total_chars": request.context.max_total_chars,
            "image": [str(path) for path in images],
        }

    # ------------------------------------------------------------------
    # Durable idempotency
    # ------------------------------------------------------------------

    @contextmanager
    def _record_lock(self, key: str) -> Iterator[None]:
        self._ensure_owned_directory(self.requests_root)
        path = self.requests_root / f"{key}.lock"
        with path.open("a+b") as handle:
            core.file_lock_exclusive(handle, blocking=True)
            try:
                yield
            finally:
                core.file_unlock(handle)

    def _record_path(self, key: str) -> Path:
        return self.requests_root / f"{key}.json"

    def _load_record(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            if path.stat().st_size > MAX_INTERNAL_JSON:
                raise ValueError("record too large")
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            raise AdapterFault(
                ErrorClass.interrupted,
                "The durable request record is unreadable.",
                outcome_unknown=True,
            ) from exc
        if not isinstance(payload, dict):
            raise AdapterFault(
                ErrorClass.interrupted,
                "The durable request record is invalid.",
                outcome_unknown=True,
            )
        return payload

    def _claim_request(
        self,
        tool: ToolName,
        request: Any,
        approval: McpApproval,
    ) -> tuple[str, str, dict[str, Any] | None]:
        key = _request_key(request.request_id)
        input_hash = _canonical_request_hash(tool, request)
        path = self._record_path(key)
        with self._record_lock(key):
            record = self._load_record(path)
            if record is not None:
                if (
                    record.get("request_id") != request.request_id
                    or record.get("tool") != tool.value
                    or record.get("input_hash") != input_hash
                ):
                    return key, input_hash, _error_envelope(
                        request.request_id,
                        summary="request_id conflicts with an earlier request",
                        error_class=ErrorClass.idempotency_conflict,
                        message="This request_id was already used with different input.",
                        approval=approval,
                    )
                if record.get("state") == "terminal":
                    envelope = record.get("envelope")
                    if isinstance(envelope, dict):
                        return key, input_hash, envelope
                    raise AdapterFault(
                        ErrorClass.interrupted,
                        "The durable request result is incomplete.",
                        outcome_unknown=True,
                    )
                if core.pid_alive(record.get("pid")):
                    return key, input_hash, _error_envelope(
                        request.request_id,
                        summary="request is already in progress",
                        error_class=ErrorClass.request_in_progress,
                        message="An identical Argos request is still running.",
                        approval=approval,
                        retryable=True,
                    )
                interrupted = _error_envelope(
                    request.request_id,
                    summary="previous request was interrupted",
                    error_class=ErrorClass.interrupted,
                    message=(
                        "The previous server process ended before it committed "
                        "a terminal result."
                    ),
                    approval=approval,
                    outcome_unknown=True,
                )
                record.update(
                    state="terminal",
                    completed_at=core.utc_now(),
                    envelope=interrupted,
                )
                core.atomic_write_json(path, record)
                return key, input_hash, interrupted
            core.atomic_write_json(
                path,
                {
                    "schema_version": REQUEST_STATE_VERSION,
                    "request_id": request.request_id,
                    "tool": tool.value,
                    "input_hash": input_hash,
                    "state": "active",
                    "pid": os.getpid(),
                    "started_at": core.utc_now(),
                },
            )
        return key, input_hash, None

    def _finish_request(
        self,
        key: str,
        input_hash: str,
        envelope: dict[str, Any],
    ) -> None:
        path = self._record_path(key)
        with self._record_lock(key):
            record = self._load_record(path)
            if record is None or record.get("input_hash") != input_hash:
                raise AdapterFault(
                    ErrorClass.interrupted,
                    "The durable request claim changed before completion.",
                    outcome_unknown=True,
                )
            record.update(
                state="terminal",
                completed_at=core.utc_now(),
                envelope=envelope,
            )
            core.atomic_write_json(path, record)

    def _fault_for_exception(self, exc: BaseException) -> AdapterFault:
        if isinstance(exc, AdapterFault):
            return exc
        if isinstance(exc, core.SessionConflictError):
            return AdapterFault(
                ErrorClass.session_conflict,
                "The session advanced since expected_turn was read.",
                retryable=True,
            )
        if isinstance(exc, context_inputs.ContextLimitError):
            return AdapterFault(
                ErrorClass.context_limit_exceeded,
                "The selected context exceeds the configured limits.",
            )
        if isinstance(exc, context_inputs.ContextInputError):
            return AdapterFault(
                ErrorClass.invalid_input,
                "A context input is invalid or unsafe.",
            )
        if isinstance(exc, ValidationError):
            return AdapterFault(
                ErrorClass.invalid_input,
                "The MCP request does not match the Argos contract.",
            )
        if isinstance(exc, SystemExit):
            folded = str(exc).casefold()
            if "not found" in folded or "invalid argos session id" in folded:
                return AdapterFault(
                    ErrorClass.session_not_found,
                    "The requested Argos session was not found.",
                )
            if "busy" in folded or "not active" in folded:
                return AdapterFault(
                    ErrorClass.session_conflict,
                    "The Argos session cannot accept this turn.",
                    retryable=True,
                )
            return AdapterFault(
                ErrorClass.invalid_input,
                "Argos rejected the requested workflow parameters.",
            )
        if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
            return AdapterFault(
                ErrorClass.provider_timeout,
                "An Argos provider timed out.",
                retryable=True,
                outcome_unknown=True,
            )
        return AdapterFault(
            ErrorClass.internal_error,
            "The Argos MCP adapter failed safely.",
        )

    async def _invoke_write(
        self,
        *,
        tool: ToolName,
        request: Any,
        approval_kinds: list[ApprovalKind],
        preflight: Callable[[], T],
        operation: Callable[[T, McpApproval], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        approval = _approval_for(request, approval_kinds)
        if approval.required:
            return _error_envelope(
                request.request_id,
                summary=f"{tool.value} requires explicit approval",
                error_class=ErrorClass.approval_required,
                message="Grant every listed approval before retrying this request.",
                approval=approval,
            )
        try:
            prepared = preflight()
            key, input_hash, previous = self._claim_request(tool, request, approval)
            if previous is not None:
                return previous
        except Exception as exc:
            fault = self._fault_for_exception(exc)
            return _error_envelope(
                request.request_id,
                summary=str(fault),
                error_class=fault.error_class,
                message=str(fault),
                approval=approval,
                retryable=fault.retryable,
                outcome_unknown=fault.outcome_unknown,
            )
        try:
            envelope = await operation(prepared, approval)
        except asyncio.CancelledError:
            cancelled = _success_envelope(
                request.request_id,
                status=EnvelopeStatus.cancelled,
                summary="Argos request cancelled",
                result={},
                approval=approval,
            )
            self._finish_request(key, input_hash, cancelled)
            raise
        except Exception as exc:
            fault = self._fault_for_exception(exc)
            envelope = _error_envelope(
                request.request_id,
                summary=str(fault),
                error_class=fault.error_class,
                message=str(fault),
                approval=approval,
                retryable=fault.retryable,
                outcome_unknown=fault.outcome_unknown,
            )
        self._finish_request(key, input_hash, envelope)
        return envelope

    # ------------------------------------------------------------------
    # Session and artifact reads
    # ------------------------------------------------------------------

    def _session_path(self, session_id: str) -> Path:
        if not SESSION_ID_RE.fullmatch(session_id):
            raise AdapterFault(
                ErrorClass.session_not_found,
                "The requested Argos session was not found.",
            )
        path = self.sessions_root / session_id
        try:
            resolved = self._safe_existing_owned_path(path, root=self.sessions_root)
            manifest = self._safe_existing_owned_path(
                resolved / "session.json",
                root=resolved,
            )
        except ResourceNotFoundError as exc:
            raise AdapterFault(
                ErrorClass.session_not_found,
                "The requested Argos session was not found.",
            ) from exc
        if not resolved.is_dir() or not manifest.is_file():
            raise AdapterFault(
                ErrorClass.session_not_found,
                "The requested Argos session was not found.",
            )
        return resolved

    def _read_text(
        self,
        path: Path,
        *,
        root: Path,
        limit: int,
    ) -> tuple[str, bool]:
        resolved = self._safe_existing_owned_path(path, root=root)
        if not resolved.is_file():
            raise ResourceNotFoundError("Argos resource not found")
        try:
            if resolved.stat().st_size > max(limit * 4, MAX_INTERNAL_JSON):
                raise ResourceNotFoundError("Argos resource not found")
            text = resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ResourceNotFoundError("Argos resource not found") from exc
        return _bounded_text(text, limit)

    def _read_json(
        self,
        path: Path,
        *,
        root: Path,
        limit: int = MAX_INTERNAL_JSON,
    ) -> Any:
        text, truncated = self._read_text(path, root=root, limit=limit)
        if truncated:
            raise ResourceNotFoundError("Argos resource not found")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ResourceNotFoundError("Argos resource not found") from exc

    def _load_session(self, session_id: str) -> tuple[Path, dict[str, Any]]:
        path = self._session_path(session_id)
        try:
            payload = self._read_json(path / "session.json", root=path)
        except ResourceNotFoundError as exc:
            raise AdapterFault(
                ErrorClass.session_not_found,
                "The requested Argos session was not found.",
            ) from exc
        if not isinstance(payload, dict) or payload.get("id") != session_id:
            raise AdapterFault(
                ErrorClass.session_not_found,
                "The requested Argos session was not found.",
            )
        return path, payload

    @asynccontextmanager
    async def _session_guard(self, session_id: str) -> AsyncIterator[None]:
        session_path = self._session_path(session_id)
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            handle = await asyncio.to_thread(
                (session_path / "mcp.lock").open,
                "a+b",
            )
            try:
                await asyncio.to_thread(core.file_lock_exclusive, handle, True)
                yield
            finally:
                await asyncio.to_thread(core.file_unlock, handle)
                await asyncio.to_thread(handle.close)

    def _inputs_manifest(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {}
        included = payload.get("included")
        skipped = payload.get("skipped")
        reasons: dict[str, int] = {}
        if isinstance(skipped, list):
            for row in skipped:
                if isinstance(row, dict):
                    reason = str(row.get("reason") or "unknown")[:80]
                    reasons[reason] = reasons.get(reason, 0) + 1
        return {
            "included_count": len(included) if isinstance(included, list) else 0,
            "skipped_count": len(skipped) if isinstance(skipped, list) else 0,
            "skipped_reasons": reasons,
            "total_chars": int(payload.get("total_chars") or 0),
            "limits": _safe_json_value(payload.get("limits") or {}),
        }

    def _result_rows(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw in payload.get("results") or []:
            if not isinstance(raw, dict):
                continue
            content, truncated = _bounded_text(
                str(raw.get("content") or ""),
                MAX_RESULT_TEXT,
            )
            error = None
            if raw.get("error"):
                error = "The contributor did not return a usable answer."
            rows.append(
                {
                    "argos": str(raw.get("argos") or "")[:128],
                    "status": _safe_status(raw.get("status")),
                    "content": content,
                    "content_truncated": truncated,
                    "error": error,
                }
            )
        return rows

    def _provider_failure(
        self,
        request_id: str,
        *,
        approval: McpApproval,
        payload: dict[str, Any],
        session_id: str | None = None,
        artifact_dir: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        errors = " ".join(
            str(row.get("error") or "")
            for row in payload.get("results") or []
            if isinstance(row, dict)
        ).casefold()
        timed_out = "timeout" in errors or "timed out" in errors
        return _error_envelope(
            request_id,
            summary="Argos providers did not complete the request",
            error_class=(
                ErrorClass.provider_timeout
                if timed_out
                else ErrorClass.provider_unavailable
            ),
            message=(
                "One or more Argos providers timed out."
                if timed_out
                else "No Argos provider returned a usable answer."
            ),
            approval=approval,
            session_id=session_id,
            artifact_dir=artifact_dir,
            result=result,
            retryable=True,
            outcome_unknown=timed_out,
        )

    def _turn_index(
        self,
        session_id: str,
        session_path: Path,
        *,
        turn_limit: int | None,
        council: bool = False,
    ) -> list[dict[str, Any]]:
        turns_root = session_path / "turns"
        if not turns_root.is_dir() or _is_link_or_reparse(turns_root):
            return []
        rows: list[dict[str, Any]] = []
        for path in sorted(turns_root.iterdir()):
            if not path.is_dir() or _is_link_or_reparse(path):
                continue
            try:
                turn = int(path.name)
                meta = self._read_json(path / "meta.json", root=path)
            except (ValueError, ResourceNotFoundError):
                continue
            if not isinstance(meta, dict):
                continue
            contributors = [
                {
                    "argos": str(item.get("argos") or "")[:128],
                    "status": _safe_status(item.get("status")),
                }
                for item in meta.get("results") or []
                if isinstance(item, dict)
            ]
            rows.append(
                {
                    "turn": turn,
                    "status": _safe_status(meta.get("status")),
                    "contributors": contributors,
                    "resource": (
                        f"argos://{'councils' if council else 'sessions'}/"
                        f"{session_id}/turns/{turn}"
                    ),
                }
            )
        if turn_limit is not None:
            return rows[-turn_limit:] if turn_limit else []
        return rows

    def _latest_synthesis(
        self,
        session_path: Path,
        session: dict[str, Any],
        *,
        limit: int = MAX_INLINE_TEXT,
    ) -> dict[str, Any] | None:
        council = session.get("council")
        if not isinstance(council, dict) or not council.get("synthesis_file"):
            return None
        relative = str(council["synthesis_file"]).replace("\\", "/")
        if relative.startswith("/") or ".." in Path(relative).parts:
            return None
        try:
            text, truncated = self._read_text(
                session_path / relative,
                root=session_path,
                limit=limit,
            )
        except ResourceNotFoundError:
            return None
        return {
            "source_turn": council.get("source_turn"),
            "text": text,
            "truncated": truncated,
            "sha256": str(council.get("sha256") or "")[:128] or None,
        }

    def _membership_manifest(self, session: dict[str, Any]) -> dict[str, Any]:
        partners = [
            str(item)[:128]
            for item in (
                session.get("argoses_requested")
                or list((session.get("argoses") or {}).keys())
            )
        ]
        return {
            "partners": partners,
            "immutable": True,
            "persona_count": len(session.get("personas") or {}),
            "assignment_count": len(session.get("assignments") or {}),
        }

    def _session_summary(
        self,
        session_id: str,
        *,
        turn_limit: int | None,
        require_council: bool = False,
    ) -> dict[str, Any]:
        path, session = self._load_session(session_id)
        if require_council and session.get("mode") != "council":
            raise AdapterFault(
                ErrorClass.session_not_found,
                "The requested Argos session was not found.",
            )
        return {
            "session_id": session_id,
            "name": str(session.get("name") or "")[:120] or None,
            "mode": str(session.get("mode") or "")[:40],
            "status": _safe_status(session.get("status")),
            "turn": int(session.get("turn") or 0),
            "last_good_turn": int(session.get("last_good_turn") or 0),
            "last_turn_status": _safe_status(session.get("last_turn_status")),
            "membership_manifest": self._membership_manifest(session),
            "turns": self._turn_index(
                session_id,
                path,
                turn_limit=turn_limit,
                council=require_council,
            ),
            "latest_synthesis": self._latest_synthesis(path, session),
            "history_resource": f"argos://sessions/{session_id}/summary",
            "artifacts_resource": f"argos://sessions/{session_id}/artifacts",
        }

    # ------------------------------------------------------------------
    # Read-only tools
    # ------------------------------------------------------------------

    async def argos_health(
        self,
        request: contract.HealthRequest | None = None,
    ) -> dict[str, Any]:
        request = request or contract.HealthRequest()
        try:
            cfg = self._load_config()
            allowed = self._allowed_argoses(cfg)
            kinds = sorted(
                {
                    str(candidate.get("kind"))
                    for name, chain in cfg.get("models", {}).items()
                    if name in allowed and isinstance(chain, list)
                    for candidate in chain
                    if isinstance(candidate, dict) and candidate.get("kind")
                }
            )
            result = {
                "ready": True,
                "protocol_version": contract.SCHEMA_VERSION,
                "argos_version": core.VERSION,
                "capabilities": {
                    "run": True,
                    "sessions": True,
                    "council": True,
                    "research": True,
                    "resources": True,
                    "streamable_http": False,
                },
                "providers": {
                    "logical_argoses": sorted(allowed),
                    "kinds": kinds,
                },
                "allowed_roots": ["."],
                "warnings": (
                    ["Workspace containment checks passed; providers were not contacted."]
                    if request.probe_paths
                    else []
                ),
            }
            return _success_envelope(
                "health",
                status=EnvelopeStatus.completed,
                summary="Argos MCP bridge is ready",
                result=result,
            )
        except Exception:
            return _error_envelope(
                "health",
                summary="Argos MCP bridge is not ready",
                error_class=ErrorClass.internal_error,
                message="The trusted Argos configuration could not be loaded.",
            )

    async def argos_session_list(
        self,
        request: contract.SessionListRequest,
    ) -> dict[str, Any]:
        try:
            rows: list[dict[str, Any]] = []
            if self.sessions_root.exists():
                root = self._safe_existing_owned_path(
                    self.sessions_root,
                    root=self.state_root,
                )
                for path in sorted(root.iterdir(), key=lambda item: item.name):
                    if not SESSION_ID_RE.fullmatch(path.name):
                        continue
                    try:
                        _, session = self._load_session(path.name)
                    except AdapterFault:
                        continue
                    rows.append(
                        {
                            "session_id": path.name,
                            "name": str(session.get("name") or "")[:120] or None,
                            "mode": str(session.get("mode") or "")[:40],
                            "status": _safe_status(session.get("status")),
                            "turn": int(session.get("turn") or 0),
                            "updated_at": str(session.get("updated_at") or "")[:64],
                            "summary_resource": (
                                f"argos://sessions/{path.name}/summary"
                            ),
                        }
                    )
            rows.sort(
                key=lambda row: (
                    str(row.get("updated_at") or ""),
                    str(row["session_id"]),
                ),
                reverse=True,
            )
            fingerprint_rows = [
                {
                    "session_id": row["session_id"],
                    "updated_at": row["updated_at"],
                    "turn": row["turn"],
                }
                for row in rows
            ]
            fingerprint = _selection_fingerprint(fingerprint_rows)
            offset = 0
            if request.cursor:
                cursor = contract.decode_cursor(request.cursor)
                if cursor.selection_fingerprint != fingerprint:
                    raise AdapterFault(
                        ErrorClass.invalid_input,
                        "The session list changed; restart pagination without a cursor.",
                    )
                offset = cursor.offset
                if offset > len(rows):
                    raise AdapterFault(
                        ErrorClass.invalid_input,
                        "The session cursor is outside the current result set.",
                    )
            limit = request.limit or 20
            selected = rows[offset : offset + limit]
            next_offset = offset + len(selected)
            next_cursor = (
                contract.encode_cursor(
                    selection_fingerprint=fingerprint,
                    offset=next_offset,
                )
                if next_offset < len(rows)
                else None
            )
            return _success_envelope(
                "session_list",
                status=EnvelopeStatus.completed,
                summary="Argos sessions listed",
                result={
                    "items": selected,
                    "count": len(selected),
                    "next_cursor": next_cursor,
                },
            )
        except Exception as exc:
            fault = self._fault_for_exception(exc)
            return _error_envelope(
                "session_list",
                summary=str(fault),
                error_class=fault.error_class,
                message=str(fault),
                retryable=fault.retryable,
            )

    async def argos_session_show(
        self,
        request: contract.SessionShowRequest,
    ) -> dict[str, Any]:
        try:
            result = self._session_summary(
                request.session_id,
                turn_limit=request.turn_limit,
            )
            return _success_envelope(
                request.session_id,
                status=EnvelopeStatus.completed,
                summary="Argos session summary returned",
                result=result,
                session_id=request.session_id,
            )
        except Exception as exc:
            fault = self._fault_for_exception(exc)
            return _error_envelope(
                request.session_id,
                summary=str(fault),
                error_class=fault.error_class,
                message=str(fault),
                retryable=fault.retryable,
            )

    async def argos_council_show(
        self,
        request: contract.CouncilShowRequest,
    ) -> dict[str, Any]:
        try:
            result = self._session_summary(
                request.council_id,
                turn_limit=request.turn_limit,
                require_council=True,
            )
            result["council_id"] = result.pop("session_id")
            result["synthesis_resource"] = (
                f"argos://councils/{request.council_id}/summary"
            )
            return _success_envelope(
                request.council_id,
                status=EnvelopeStatus.completed,
                summary="Argos Council summary returned",
                result=result,
                session_id=request.council_id,
            )
        except Exception as exc:
            fault = self._fault_for_exception(exc)
            return _error_envelope(
                request.council_id,
                summary=str(fault),
                error_class=fault.error_class,
                message=str(fault),
                retryable=fault.retryable,
            )

    # ------------------------------------------------------------------
    # Workflow preparation
    # ------------------------------------------------------------------

    def _base_namespace(
        self,
        request: contract.WorkflowRequestBase,
        context: dict[str, Any],
        *,
        mode: str | None,
        artifact_root: Path,
        session_id: str | None = None,
        expected_turn: int | None = None,
    ) -> argparse.Namespace:
        return argparse.Namespace(
            config=str(self.config_path),
            mode=mode,
            prompt=request.prompt,
            prompt_file=None,
            argoses=list(request.providers) or None,
            single_ok=bool(request.providers),
            artifact_root=str(artifact_root),
            artifact_dir=None,
            background=False,
            synthesize=False,
            synthesizer=None,
            json=False,
            quiet=True,
            session_id=session_id,
            expected_turn=expected_turn,
            retry_of=None,
            retry_argoses=[],
            session_label=getattr(request, "session_label", None),
            **context,
        )

    def _prepare_run(
        self,
        request: contract.RunRequest,
    ) -> tuple[argparse.Namespace, dict[str, Any]]:
        cfg = self._load_config()
        mode, argoses, _ = core.resolve_mode_and_argoses(
            request.mode.value,
            list(request.providers) or None,
            cfg,
        )
        resolved = list(argoses or [])
        self._require_allowed_argoses(resolved, cfg)
        core.enforce_argos_minimum(mode, resolved, bool(request.providers), cfg)
        context = self._prepare_context(request)
        namespace = self._base_namespace(
            request,
            context,
            mode=mode,
            artifact_root=self.runs_root,
        )
        return namespace, cfg

    def _prepare_start(
        self,
        request: contract.StartRequest,
    ) -> tuple[argparse.Namespace, dict[str, Any]]:
        cfg = self._load_config()
        requested_mode = (request.mode or contract.SessionMode.council).value
        mode, argoses, _ = core.resolve_mode_and_argoses(
            requested_mode,
            list(request.providers) or None,
            cfg,
        )
        resolved = list(argoses or [])
        self._require_allowed_argoses(resolved, cfg)
        core.enforce_argos_minimum(mode, resolved, bool(request.providers), cfg)
        context = self._prepare_context(request)
        namespace = self._base_namespace(
            request,
            context,
            mode=mode,
            artifact_root=self.sessions_root,
        )
        return namespace, cfg

    def _prepare_ask(
        self,
        request: contract.AskRequest,
    ) -> tuple[argparse.Namespace, dict[str, Any]]:
        _, session = self._load_session(request.session_id)
        cfg = session.get("config_snapshot")
        if not isinstance(cfg, dict):
            raise AdapterFault(
                ErrorClass.session_conflict,
                "The Argos session does not contain a valid configuration snapshot.",
            )
        members = list((session.get("argoses") or {}).keys())
        selected = list(request.providers) or members
        if any(name not in members for name in selected):
            raise AdapterFault(
                ErrorClass.invalid_input,
                "A requested Argos provider is not a member of this session.",
            )
        self._verify_session_provider_state(session, cfg, selected)
        context = self._prepare_context(request)
        namespace = self._base_namespace(
            request,
            context,
            mode=str(session.get("mode") or ""),
            artifact_root=self.sessions_root,
            session_id=request.session_id,
            expected_turn=request.expected_turn,
        )
        return namespace, cfg

    def _prepare_council(
        self,
        request: contract.CouncilPublishRequest,
    ) -> tuple[argparse.Namespace, dict[str, Any]]:
        if request.providers:
            raise AdapterFault(
                ErrorClass.invalid_input,
                "Council membership is immutable; providers cannot be overridden.",
            )
        _, session = self._load_session(request.council_id)
        if session.get("mode") != "council":
            raise AdapterFault(
                ErrorClass.session_not_found,
                "The requested Argos session was not found.",
            )
        cfg = session.get("config_snapshot")
        if not isinstance(cfg, dict):
            raise AdapterFault(
                ErrorClass.session_conflict,
                "The Council does not contain a valid configuration snapshot.",
            )
        members = list((session.get("argoses") or {}).keys())
        trusted = self._verify_session_provider_state(
            session,
            cfg,
            members,
        )
        context = self._prepare_context(request)
        namespace = self._base_namespace(
            request,
            context,
            mode="council",
            artifact_root=self.sessions_root,
            session_id=request.council_id,
            expected_turn=request.expected_turn,
        )
        return namespace, trusted

    # ------------------------------------------------------------------
    # Write-capable tools
    # ------------------------------------------------------------------

    async def argos_run(self, request: contract.RunRequest) -> dict[str, Any]:
        async def operation(
            prepared: tuple[argparse.Namespace, dict[str, Any]],
            approval: McpApproval,
        ) -> dict[str, Any]:
            namespace, _ = prepared
            code, payload = await core.run_mode(namespace, return_payload=True)
            artifact_dir = self._relative_artifact(payload["artifact_dir"])
            final, truncated = self._read_text(
                Path(payload["artifact_dir"]) / "final.md",
                root=Path(payload["artifact_dir"]),
                limit=MAX_INLINE_TEXT,
            )
            result = {
                "mode": str(payload.get("mode") or ""),
                "profile": request.profile.value,
                "final_text": final,
                "final_text_truncated": truncated,
                "prompt_manifest": self._inputs_manifest(
                    payload.get("inputs_report")
                ),
                "findings_artifact": (
                    f"argos://runs/{request.request_id}/findings"
                    if payload.get("findings")
                    else None
                ),
                "manifest_resource": (
                    f"argos://runs/{request.request_id}/manifest"
                ),
            }
            ok_count = sum(
                1
                for row in payload.get("results") or []
                if isinstance(row, dict) and row.get("status") == "ok"
            )
            if not ok_count:
                return self._provider_failure(
                    request.request_id,
                    approval=approval,
                    payload=payload,
                    artifact_dir=artifact_dir,
                    result=result,
                )
            status = (
                EnvelopeStatus.completed
                if code == core.EXIT_OK
                else EnvelopeStatus.partial
            )
            return _success_envelope(
                request.request_id,
                status=status,
                summary=(
                    "Argos workflow completed"
                    if status == EnvelopeStatus.completed
                    else "Argos workflow completed with partial provider results"
                ),
                result=result,
                approval=approval,
                artifact_dir=artifact_dir,
            )

        return await self._invoke_write(
            tool=ToolName.argos_run,
            request=request,
            approval_kinds=[
                ApprovalKind.artifact_write,
                ApprovalKind.model_egress,
            ],
            preflight=lambda: self._prepare_run(request),
            operation=operation,
        )

    async def argos_start(self, request: contract.StartRequest) -> dict[str, Any]:
        async def operation(
            prepared: tuple[argparse.Namespace, dict[str, Any]],
            approval: McpApproval,
        ) -> dict[str, Any]:
            namespace, _ = prepared
            self._ensure_owned_directory(self.sessions_root)
            code, payload = await core.start_mode(namespace, return_payload=True)
            session_id = str(payload["session_id"])
            artifact_dir = self._relative_artifact(payload["artifact_dir"])
            final, truncated = self._read_text(
                Path(payload["turn_dir"]) / "final.md",
                root=Path(payload["artifact_dir"]),
                limit=MAX_INLINE_TEXT,
            )
            result = {
                "turn": int(payload.get("turn") or 1),
                "mode": str(payload.get("mode") or ""),
                "profile": request.profile.value,
                "final_text": final,
                "final_text_truncated": truncated,
                "prompt_manifest": self._inputs_manifest(
                    payload.get("inputs_report")
                ),
                "history_resource": f"argos://sessions/{session_id}/summary",
            }
            ok_count = sum(
                1
                for row in payload.get("results") or []
                if isinstance(row, dict) and row.get("status") == "ok"
            )
            if not ok_count:
                return self._provider_failure(
                    request.request_id,
                    approval=approval,
                    payload=payload,
                    session_id=session_id,
                    artifact_dir=artifact_dir,
                    result=result,
                )
            status = (
                EnvelopeStatus.completed
                if code == core.EXIT_OK
                else EnvelopeStatus.partial
            )
            return _success_envelope(
                request.request_id,
                status=status,
                summary=(
                    "Argos session started"
                    if status == EnvelopeStatus.completed
                    else "Argos session started with partial provider results"
                ),
                result=result,
                approval=approval,
                session_id=session_id,
                artifact_dir=artifact_dir,
            )

        return await self._invoke_write(
            tool=ToolName.argos_start,
            request=request,
            approval_kinds=[
                ApprovalKind.artifact_write,
                ApprovalKind.model_egress,
            ],
            preflight=lambda: self._prepare_start(request),
            operation=operation,
        )

    async def argos_ask(self, request: contract.AskRequest) -> dict[str, Any]:
        async def operation(
            prepared: tuple[argparse.Namespace, dict[str, Any]],
            approval: McpApproval,
        ) -> dict[str, Any]:
            namespace, _ = prepared
            async with self._session_guard(request.session_id):
                code, payload = await core.ask_mode(namespace, return_payload=True)
            artifact_dir = self._relative_artifact(payload["artifact_dir"])
            final, truncated = self._read_text(
                Path(payload["turn_dir"]) / "final.md",
                root=Path(payload["artifact_dir"]),
                limit=MAX_INLINE_TEXT,
            )
            result = {
                "turn": int(payload.get("turn") or 0),
                "profile": request.profile.value,
                "final_text": final,
                "final_text_truncated": truncated,
                "prompt_manifest": self._inputs_manifest(
                    payload.get("inputs_report")
                ),
                "history_resource": (
                    f"argos://sessions/{request.session_id}/summary"
                ),
            }
            ok_count = sum(
                1
                for row in payload.get("results") or []
                if isinstance(row, dict) and row.get("status") == "ok"
            )
            if not ok_count:
                return self._provider_failure(
                    request.request_id,
                    approval=approval,
                    payload=payload,
                    session_id=request.session_id,
                    artifact_dir=artifact_dir,
                    result=result,
                )
            status = (
                EnvelopeStatus.completed
                if code == core.EXIT_OK
                else EnvelopeStatus.partial
            )
            return _success_envelope(
                request.request_id,
                status=status,
                summary=(
                    "Argos session advanced"
                    if status == EnvelopeStatus.completed
                    else "Argos session advanced with partial provider results"
                ),
                result=result,
                approval=approval,
                session_id=request.session_id,
                artifact_dir=artifact_dir,
            )

        return await self._invoke_write(
            tool=ToolName.argos_ask,
            request=request,
            approval_kinds=[
                ApprovalKind.artifact_write,
                ApprovalKind.model_egress,
            ],
            preflight=lambda: self._prepare_ask(request),
            operation=operation,
        )

    def _council_synthesizer(
        self,
        cfg: dict[str, Any],
        contributors: list[str],
    ) -> str:
        allowed = self._allowed_argoses(cfg)
        candidates = [
            "fable",
            str(cfg.get("synthesis", {}).get("default_model") or ""),
            *contributors,
        ]
        for candidate in candidates:
            if candidate and candidate in allowed:
                return candidate
        raise AdapterFault(
            ErrorClass.provider_unavailable,
            "No allowed Council synthesizer is configured.",
        )

    async def argos_council_publish(
        self,
        request: contract.CouncilPublishRequest,
    ) -> dict[str, Any]:
        async def operation(
            prepared: tuple[argparse.Namespace, dict[str, Any]],
            approval: McpApproval,
        ) -> dict[str, Any]:
            namespace, cfg = prepared
            async with self._session_guard(request.council_id):
                code, payload = await core.ask_mode(namespace, return_payload=True)
                rows = self._result_rows(payload)
                successful_raw = [
                    core.argos_result_from_dict(row)
                    for row in payload.get("results") or []
                    if isinstance(row, dict) and row.get("status") == "ok"
                ]
                artifact_dir = self._relative_artifact(payload["artifact_dir"])
                base_result = {
                    "turn": int(payload.get("turn") or 0),
                    "contributors": [row["argos"] for row in rows],
                    "independent_answers": rows,
                    "synthesis": "",
                    "synthesis_truncated": False,
                    "membership_manifest": self._membership_manifest(
                        self._load_session(request.council_id)[1]
                    ),
                }
                if not successful_raw:
                    return self._provider_failure(
                        request.request_id,
                        approval=approval,
                        payload=payload,
                        session_id=request.council_id,
                        artifact_dir=artifact_dir,
                        result=base_result,
                    )
                turn_dir = Path(payload["turn_dir"])
                synth_dir = turn_dir / "council_synthesis"
                synthesizer = self._council_synthesizer(
                    cfg,
                    [result.argos for result in successful_raw],
                )
                provider_cwd = core.provider_session_cwd(
                    Path(payload["artifact_dir"])
                )
                runner = core.Runner(
                    cfg,
                    synth_dir,
                    provider_cwd=provider_cwd,
                    mode="council",
                )
                synthesis_result = await runner.run_logical(
                    synthesizer,
                    core.build_generic_synthesis_prompt(successful_raw),
                    [],
                )
                if synthesis_result.status != "ok" or not synthesis_result.content.strip():
                    return _success_envelope(
                        request.request_id,
                        status=EnvelopeStatus.partial,
                        summary=(
                            "Council answers were preserved but synthesis failed"
                        ),
                        result=base_result,
                        approval=approval,
                        session_id=request.council_id,
                        artifact_dir=artifact_dir,
                    )
                synthesis_source = synth_dir / "published-synthesis.md"
                core.atomic_write_text(
                    synthesis_source,
                    synthesis_result.content,
                )
                core.publish_council_synthesis(
                    self.sessions_root,
                    request.council_id,
                    str(synthesis_source),
                    False,
                    return_payload=True,
                )
                synthesis, synthesis_truncated = _bounded_text(
                    synthesis_result.content,
                    MAX_INLINE_TEXT,
                )
                base_result["synthesis"] = synthesis
                base_result["synthesis_truncated"] = synthesis_truncated
                all_contributors_ok = all(
                    row.get("status") == "ok"
                    for row in payload.get("results") or []
                    if isinstance(row, dict)
                )
                status = (
                    EnvelopeStatus.completed
                    if code == core.EXIT_OK and all_contributors_ok
                    else EnvelopeStatus.partial
                )
                return _success_envelope(
                    request.request_id,
                    status=status,
                    summary=(
                        "Council turn published"
                        if status == EnvelopeStatus.completed
                        else "Council turn published with partial contributor results"
                    ),
                    result=base_result,
                    approval=approval,
                    session_id=request.council_id,
                    artifact_dir=artifact_dir,
                )

        return await self._invoke_write(
            tool=ToolName.argos_council_publish,
            request=request,
            approval_kinds=[
                ApprovalKind.artifact_write,
                ApprovalKind.model_egress,
            ],
            preflight=lambda: self._prepare_council(request),
            operation=operation,
        )

    def _prepare_research(
        self,
        request: contract.ResearchRequest,
    ) -> tuple[argparse.Namespace, dict[str, Any]]:
        if (
            request.context.files
            or request.context.directories
            or request.context.include
            or request.context.exclude
            or request.images
            or request.providers
        ):
            raise AdapterFault(
                ErrorClass.invalid_input,
                "Research does not accept context, images, or provider overrides.",
            )
        if request.force_model_on_insufficient and not request.model_egress:
            raise AdapterFault(
                ErrorClass.invalid_input,
                "Coverage override requires explicit model_egress approval.",
            )
        cfg = self._load_config()
        allowed = self._allowed_argoses(cfg)
        sota_cfg = cfg.get("sota", {})
        synthesizers = [
            str(name)
            for name in sota_cfg.get("synthesizers", [])
            if str(name) in allowed
        ][:2]
        reviewer_candidates = [
            sota_cfg.get("high_reviewer")
            if request.research_profile == contract.ResearchProfile.deep
            else sota_cfg.get("reviewer"),
            *synthesizers,
        ]
        reviewer = next(
            (
                str(name)
                for name in reviewer_candidates
                if name and str(name) in allowed
            ),
            None,
        )
        if request.model_egress and (not synthesizers or reviewer is None):
            raise AdapterFault(
                ErrorClass.provider_unavailable,
                "No allowed research synthesizer and reviewer are configured.",
            )
        namespace = argparse.Namespace(
            config=str(self.config_path),
            cmd="research",
            question=request.prompt,
            profile=request.research_profile.value,
            source=None,
            since=None,
            max_sources=request.max_sources,
            max_queries=request.max_queries,
            timeout=None,
            high=request.research_profile == contract.ResearchProfile.deep,
            no_model=not request.model_egress,
            strict_topic=True,
            force_model_on_insufficient=request.force_model_on_insufficient,
            synthesizer=synthesizers if request.model_egress else [],
            reviewer=reviewer if request.model_egress else None,
            artifact_root=str(self.runs_root),
            artifact_dir=None,
            json=False,
        )
        return namespace, cfg

    async def argos_research(
        self,
        request: contract.ResearchRequest,
    ) -> dict[str, Any]:
        approval_kinds = [
            ApprovalKind.artifact_write,
            ApprovalKind.retrieval_egress,
        ]
        if request.model_egress or request.force_model_on_insufficient:
            approval_kinds.append(ApprovalKind.model_egress)
        if request.force_model_on_insufficient:
            approval_kinds.append(ApprovalKind.force_insufficient_synthesis)

        async def operation(
            prepared: tuple[argparse.Namespace, dict[str, Any]],
            approval: McpApproval,
        ) -> dict[str, Any]:
            namespace, _ = prepared
            code, payload = await core.sota_mode(namespace, return_payload=True)
            artifact_path = Path(payload["artifact_dir"])
            artifact_dir = self._relative_artifact(artifact_path)
            report, truncated = self._read_text(
                artifact_path / "report.md",
                root=artifact_path,
                limit=MAX_INLINE_TEXT,
            )
            try:
                queries = self._read_json(
                    artifact_path / "query_plan.json",
                    root=artifact_path,
                    limit=MAX_RESOURCE_TEXT,
                )
            except ResourceNotFoundError:
                queries = []
            coverage = _safe_json_value(payload.get("coverage") or {})
            verification = payload.get("verification") or {}
            coverage_status = str((payload.get("coverage") or {}).get("status") or "")
            result = {
                "verification_status": str(
                    verification.get("status") or "unknown"
                )[:80],
                "coverage": coverage,
                "queries": _safe_json_value(queries),
                "evidence_artifact": (
                    f"argos://runs/{request.request_id}/findings"
                ),
                "synthesis": report,
                "synthesis_truncated": truncated,
                "model_skipped": not request.model_egress or not bool(
                    (payload.get("coverage") or {}).get("model_allowed")
                ),
                "manifest_resource": (
                    f"argos://runs/{request.request_id}/manifest"
                ),
            }
            if coverage_status == "insufficient":
                return _success_envelope(
                    request.request_id,
                    status=EnvelopeStatus.insufficient,
                    summary="Research coverage was insufficient",
                    result=result,
                    approval=approval,
                    artifact_dir=artifact_dir,
                )
            evidence_count = int(payload.get("evidence_count") or 0)
            if not evidence_count and code != core.EXIT_OK:
                return _error_envelope(
                    request.request_id,
                    summary="Research retrieval failed",
                    error_class=ErrorClass.retrieval_failed,
                    message="No usable research evidence was retrieved.",
                    approval=approval,
                    artifact_dir=artifact_dir,
                    result=result,
                    retryable=True,
                )
            status = (
                EnvelopeStatus.completed
                if code == core.EXIT_OK
                else EnvelopeStatus.partial
            )
            return _success_envelope(
                request.request_id,
                status=status,
                summary=(
                    "Argos research completed"
                    if status == EnvelopeStatus.completed
                    else "Argos research completed with partial verification"
                ),
                result=result,
                approval=approval,
                artifact_dir=artifact_dir,
            )

        return await self._invoke_write(
            tool=ToolName.argos_research,
            request=request,
            approval_kinds=approval_kinds,
            preflight=lambda: self._prepare_research(request),
            operation=operation,
        )

    # ------------------------------------------------------------------
    # Resources
    # ------------------------------------------------------------------

    def _resource_match(self, uri: str) -> tuple[str, str, str, int | None]:
        for pattern in RESOURCE_PATTERNS:
            match = pattern.fullmatch(uri)
            if not match:
                continue
            kind = uri.split("://", 1)[1].split("/", 1)[0]
            turn = match.groupdict().get("turn")
            return kind, match.group("id"), match.group("tail"), (
                int(turn) if turn is not None else None
            )
        raise ResourceNotFoundError("Argos resource not found")

    def _terminal_record(self, request_id: str) -> dict[str, Any]:
        if not contract.IDENTIFIER_RE.fullmatch(request_id):
            raise ResourceNotFoundError("Argos resource not found")
        path = self._record_path(_request_key(request_id))
        try:
            record = self._load_record(path)
        except AdapterFault as exc:
            raise ResourceNotFoundError("Argos resource not found") from exc
        if (
            not record
            or record.get("request_id") != request_id
            or record.get("state") != "terminal"
            or not isinstance(record.get("envelope"), dict)
        ):
            raise ResourceNotFoundError("Argos resource not found")
        return record

    def _record_artifact_path(self, record: dict[str, Any]) -> Path:
        envelope = record["envelope"]
        relative = envelope.get("artifact_dir")
        if not isinstance(relative, str):
            raise ResourceNotFoundError("Argos resource not found")
        normalized = relative.replace("\\", "/")
        if (
            normalized.startswith("/")
            or ".." in Path(normalized).parts
            or re.match(r"^[A-Za-z]:", normalized)
        ):
            raise ResourceNotFoundError("Argos resource not found")
        path = self.workspace / normalized
        return self._safe_existing_owned_path(path, root=self.state_root)

    def _turn_resource(
        self,
        session_id: str,
        turn: int,
        *,
        council: bool,
    ) -> dict[str, Any]:
        session_path, session = self._load_session(session_id)
        if council and session.get("mode") != "council":
            raise ResourceNotFoundError("Argos resource not found")
        turn_path = session_path / "turns" / f"{turn:03d}"
        try:
            meta = self._read_json(turn_path / "meta.json", root=turn_path)
            final, truncated = self._read_text(
                turn_path / "final.md",
                root=turn_path,
                limit=MAX_RESOURCE_TEXT,
            )
        except (AdapterFault, ResourceNotFoundError) as exc:
            raise ResourceNotFoundError("Argos resource not found") from exc
        if not isinstance(meta, dict) or int(meta.get("turn") or 0) != turn:
            raise ResourceNotFoundError("Argos resource not found")
        return {
            "session_id": session_id,
            "turn": turn,
            "status": _safe_status(meta.get("status")),
            "contributors": [
                {
                    "argos": str(row.get("argos") or "")[:128],
                    "status": _safe_status(row.get("status")),
                }
                for row in meta.get("results") or []
                if isinstance(row, dict)
            ],
            "prompt_manifest": self._inputs_manifest(meta.get("inputs_report")),
            "final_text": final,
            "final_text_truncated": truncated,
        }

    def _artifact_index(
        self,
        session_id: str,
    ) -> dict[str, Any]:
        session_path, _ = self._load_session(session_id)
        turns = self._turn_index(session_id, session_path, turn_limit=None)
        return {
            "session_id": session_id,
            "summary": f"argos://sessions/{session_id}/summary",
            "turn_resources": [row["resource"] for row in turns],
        }

    async def read_resource(self, uri: str) -> str:
        try:
            kind, identifier, tail, turn = self._resource_match(uri)
            if kind == "sessions":
                if tail == "summary":
                    payload = self._session_summary(
                        identifier,
                        turn_limit=None,
                    )
                elif tail == "artifacts":
                    payload = self._artifact_index(identifier)
                elif turn is not None:
                    payload = self._turn_resource(
                        identifier,
                        turn,
                        council=False,
                    )
                else:
                    raise ResourceNotFoundError("Argos resource not found")
            elif kind == "councils":
                if tail == "summary":
                    payload = self._session_summary(
                        identifier,
                        turn_limit=None,
                        require_council=True,
                    )
                elif turn is not None:
                    payload = self._turn_resource(
                        identifier,
                        turn,
                        council=True,
                    )
                else:
                    raise ResourceNotFoundError("Argos resource not found")
            elif kind == "runs":
                record = self._terminal_record(identifier)
                artifact_path = self._record_artifact_path(record)
                if tail == "manifest":
                    envelope = record["envelope"]
                    payload = {
                        "request_id": identifier,
                        "tool": str(record.get("tool") or ""),
                        "state": "terminal",
                        "completed_at": str(record.get("completed_at") or "")[:64],
                        "envelope": _safe_json_value(envelope),
                    }
                elif tail == "coverage":
                    payload = self._read_json(
                        artifact_path / "coverage.json",
                        root=artifact_path,
                        limit=MAX_RESOURCE_TEXT,
                    )
                elif tail == "findings":
                    candidate = artifact_path / "findings.json"
                    if not candidate.exists():
                        candidate = artifact_path / "evidence.json"
                    payload = self._read_json(
                        candidate,
                        root=artifact_path,
                        limit=MAX_RESOURCE_TEXT,
                    )
                else:
                    raise ResourceNotFoundError("Argos resource not found")
            else:
                raise ResourceNotFoundError("Argos resource not found")
            text = json.dumps(
                _safe_json_value(payload),
                ensure_ascii=False,
                indent=2,
            )
            if len(text) > MAX_RESOURCE_TEXT:
                raise ResourceNotFoundError("Argos resource not found")
            return text
        except (AdapterFault, ResourceNotFoundError, OSError, ValueError) as exc:
            raise ResourceNotFoundError("Argos resource not found") from exc


__all__ = [
    "AdapterFault",
    "ArgosMCPAdapter",
    "ResourceNotFoundError",
]
