"""Typed MCP contract models for the Argos bridge.

The contract is intentionally narrow: typed request models, a stable response
envelope, and opaque continuation cursors.  It does not implement transport or
workflow behavior.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import re
import sys
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

try:  # pragma: no cover - exercised when the module is imported as a package
    from .context_inputs import (
        DEFAULT_MAX_FILES,
        DEFAULT_MAX_FILE_CHARS,
        DEFAULT_MAX_TOTAL_CHARS,
    )
except Exception:  # pragma: no cover - exercised by direct file loading
    _CONTEXT_PATH = Path(__file__).resolve().with_name("context_inputs.py")
    _CONTEXT_SPEC = importlib.util.spec_from_file_location(
        "argos_context_inputs_for_contract",
        _CONTEXT_PATH,
    )
    if not _CONTEXT_SPEC or not _CONTEXT_SPEC.loader:
        raise ImportError(f"Could not load {_CONTEXT_PATH}")
    _CONTEXT_MODULE = importlib.util.module_from_spec(_CONTEXT_SPEC)
    sys.modules[_CONTEXT_SPEC.name] = _CONTEXT_MODULE
    _CONTEXT_SPEC.loader.exec_module(_CONTEXT_MODULE)
    DEFAULT_MAX_FILES = _CONTEXT_MODULE.DEFAULT_MAX_FILES
    DEFAULT_MAX_FILE_CHARS = _CONTEXT_MODULE.DEFAULT_MAX_FILE_CHARS
    DEFAULT_MAX_TOTAL_CHARS = _CONTEXT_MODULE.DEFAULT_MAX_TOTAL_CHARS

SCHEMA_VERSION = "1.0"
CURSOR_VERSION = 1
IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ToolMode(StrEnum):
    plan = "plan"
    critique = "critique"
    review = "review"
    debug = "debug"
    ui = "ui"
    vision = "vision"
    star = "star"
    consensus = "consensus"


class SessionMode(StrEnum):
    council = "council"
    plan = "plan"
    critique = "critique"
    review = "review"
    debug = "debug"
    ui = "ui"
    vision = "vision"
    star = "star"
    consensus = "consensus"


class ProfileLevel(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class ResearchProfile(StrEnum):
    normal = "normal"
    docs = "docs"
    landscape = "landscape"
    implementation = "implementation"
    current = "current"
    evidence = "evidence"
    deep = "deep"


class ApprovalKind(StrEnum):
    artifact_write = "artifact_write"
    model_egress = "model_egress"
    retrieval_egress = "retrieval_egress"
    force_insufficient_synthesis = "force_insufficient_synthesis"


class EnvelopeStatus(StrEnum):
    completed = "completed"
    partial = "partial"
    insufficient = "insufficient"
    cancelled = "cancelled"
    failed = "failed"


class ErrorClass(StrEnum):
    invalid_input = "invalid_input"
    path_outside_workspace = "path_outside_workspace"
    context_limit_exceeded = "context_limit_exceeded"
    approval_required = "approval_required"
    provider_unavailable = "provider_unavailable"
    provider_timeout = "provider_timeout"
    retrieval_failed = "retrieval_failed"
    idempotency_conflict = "idempotency_conflict"
    session_not_found = "session_not_found"
    session_conflict = "session_conflict"
    request_in_progress = "request_in_progress"
    interrupted = "interrupted"
    internal_error = "internal_error"


class ToolName(StrEnum):
    argos_health = "argos_health"
    argos_session_list = "argos_session_list"
    argos_session_show = "argos_session_show"
    argos_council_show = "argos_council_show"
    argos_run = "argos_run"
    argos_start = "argos_start"
    argos_ask = "argos_ask"
    argos_council_publish = "argos_council_publish"
    argos_research = "argos_research"


def _validate_identifier(value: Any, field_name: str) -> str:
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value or value.strip() != value:
        raise ValueError(f"{field_name} must be a non-empty trimmed string")
    if not IDENTIFIER_RE.fullmatch(value):
        raise ValueError(
            f"{field_name} must be URI-safe, start with an ASCII letter or digit, "
            "and not exceed 128 characters"
        )
    return value


def _validate_text_list(
    value: Any,
    field_name: str,
    *,
    max_item_chars: int,
) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)):
        value = [value]
    result: list[str] = []
    for item in value:
        if isinstance(item, bytes):
            item = item.decode("utf-8")
        if not isinstance(item, str):
            raise TypeError(f"{field_name} entries must be strings")
        if not item or item.strip() != item:
            raise ValueError(f"{field_name} entries must be non-empty trimmed strings")
        if len(item) > max_item_chars:
            raise ValueError(
                f"{field_name} entries must not exceed {max_item_chars} characters"
            )
        result.append(item)
    return result


class ContextInput(ContractModel):
    files: list[str] = Field(default_factory=list, max_length=200)
    directories: list[str] = Field(default_factory=list, max_length=50)
    include: list[str] = Field(default_factory=list, max_length=100)
    exclude: list[str] = Field(default_factory=list, max_length=100)
    max_files: int = Field(default=DEFAULT_MAX_FILES, ge=1)
    max_file_chars: int = Field(default=DEFAULT_MAX_FILE_CHARS, ge=1)
    max_total_chars: int = Field(default=DEFAULT_MAX_TOTAL_CHARS, ge=1)
    follow_symlinks: bool = False

    @field_validator("files", "directories", "include", "exclude", mode="before")
    @classmethod
    def _normalize_context_lists(cls, value: Any, info):  # type: ignore[override]
        field_name = info.field_name or "context item"
        max_item_chars = 1024 if field_name in {"include", "exclude"} else 4096
        return _validate_text_list(
            value,
            field_name,
            max_item_chars=max_item_chars,
        )


class WorkflowRequestBase(ContractModel):
    request_id: str
    prompt: str = Field(max_length=180_000)
    profile: ProfileLevel = ProfileLevel.medium
    context: ContextInput = Field(default_factory=ContextInput)
    images: list[str] = Field(default_factory=list, max_length=20)
    providers: list[str] = Field(default_factory=list, max_length=20)
    artifact_write: bool = Field(..., json_schema_extra={"default": False})
    model_egress: bool = False
    retrieval_egress: bool = False
    force_model_on_insufficient: bool = False

    @field_validator("request_id")
    @classmethod
    def _validate_request_id(cls, value: Any) -> str:
        return _validate_identifier(value, "request_id")

    @field_validator("prompt")
    @classmethod
    def _validate_prompt(cls, value: Any) -> str:
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        if not isinstance(value, str):
            raise TypeError("prompt must be a string")
        if not value.strip():
            raise ValueError("prompt must not be empty")
        return value

    @field_validator("images", "providers", mode="before")
    @classmethod
    def _normalize_workflow_lists(cls, value: Any, info):  # type: ignore[override]
        field_name = info.field_name or "workflow item"
        return _validate_text_list(
            value,
            field_name,
            max_item_chars=128 if field_name == "providers" else 4096,
        )


class RunRequest(WorkflowRequestBase):
    mode: ToolMode


class StartRequest(WorkflowRequestBase):
    mode: SessionMode | None = None
    session_label: str | None = Field(default=None, max_length=120)

    @field_validator("session_label")
    @classmethod
    def _validate_session_label(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("session_label must be a string")
        label = value.strip()
        if not label:
            raise ValueError("session_label must not be empty")
        if "\0" in label or any(ord(char) < 32 for char in label):
            raise ValueError("session_label must not contain NUL or control characters")
        return label


class AskRequest(WorkflowRequestBase):
    session_id: str
    expected_turn: int = Field(ge=0)

    @field_validator("session_id")
    @classmethod
    def _validate_session_id(cls, value: Any) -> str:
        return _validate_identifier(value, "session_id")


class CouncilPublishRequest(WorkflowRequestBase):
    council_id: str
    expected_turn: int = Field(ge=0)

    @field_validator("council_id")
    @classmethod
    def _validate_council_id(cls, value: Any) -> str:
        return _validate_identifier(value, "council_id")


class ResearchRequest(WorkflowRequestBase):
    research_profile: ResearchProfile = ResearchProfile.normal
    max_queries: int | None = Field(default=None, ge=1)
    max_sources: int | None = Field(default=None, ge=1)


class HealthRequest(ContractModel):
    probe_paths: bool = False


class SessionListRequest(ContractModel):
    limit: int | None = Field(default=None, ge=1, le=100)
    cursor: str | None = None


class SessionShowRequest(ContractModel):
    session_id: str
    turn_limit: int | None = Field(default=None, ge=0)

    @field_validator("session_id")
    @classmethod
    def _validate_session_id(cls, value: Any) -> str:
        return _validate_identifier(value, "session_id")


class CouncilShowRequest(ContractModel):
    council_id: str
    turn_limit: int | None = Field(default=None, ge=0)

    @field_validator("council_id")
    @classmethod
    def _validate_council_id(cls, value: Any) -> str:
        return _validate_identifier(value, "council_id")


class McpApproval(ContractModel):
    required: bool = False
    kinds: list[ApprovalKind] = Field(default_factory=list)
    granted: list[ApprovalKind] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_granted_subset(self) -> "McpApproval":
        if not set(self.granted).issubset(set(self.kinds)):
            raise ValueError("approval.granted must be a subset of approval.kinds")
        return self


class McpError(ContractModel):
    error_class: ErrorClass = Field(alias="class")
    message: str
    retryable: bool
    outcome_unknown: bool = False

    @field_validator("message")
    @classmethod
    def _validate_message(cls, value: Any) -> str:
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        if not isinstance(value, str):
            raise TypeError("error.message must be a string")
        if not value.strip():
            raise ValueError("error.message must not be empty")
        return value


ResultT = TypeVar("ResultT")


class McpEnvelope(ContractModel, Generic[ResultT]):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    request_id: str
    status: EnvelopeStatus
    summary: str
    session_id: str | None = None
    artifact_dir: str | None = None
    result: ResultT
    approval: McpApproval = Field(default_factory=McpApproval)
    error: McpError | None = None

    @field_validator("request_id")
    @classmethod
    def _validate_envelope_request_id(cls, value: Any) -> str:
        return _validate_identifier(value, "request_id")

    @field_validator("summary")
    @classmethod
    def _validate_summary(cls, value: Any) -> str:
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        if not isinstance(value, str):
            raise TypeError("summary must be a string")
        if not value.strip():
            raise ValueError("summary must not be empty")
        return value

    @field_validator("session_id")
    @classmethod
    def _validate_optional_identifier(cls, value: Any) -> str | None:
        if value is None:
            return None
        return _validate_identifier(value, "session_id")

    @field_validator("artifact_dir")
    @classmethod
    def _validate_artifact_dir(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("artifact_dir must be a string")
        normalized = value.replace("\\", "/")
        path = PurePosixPath(normalized)
        if (
            not normalized
            or normalized.startswith("/")
            or ":" in normalized
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError("artifact_dir must be a normalized workspace-relative path")
        return path.as_posix()

    @model_validator(mode="after")
    def _check_error_shape(self) -> "McpEnvelope[ResultT]":
        if self.status == EnvelopeStatus.failed:
            if self.error is None:
                raise ValueError("error is required when status is failed")
        elif self.error is not None:
            raise ValueError("error must be null unless status is failed")
        return self


class SelectionCursor(ContractModel):
    version: Literal[1] = CURSOR_VERSION
    selection_fingerprint: str = Field(max_length=128)
    offset: int = Field(ge=0, le=1_000_000)

    @field_validator("selection_fingerprint")
    @classmethod
    def _validate_fingerprint(cls, value: Any) -> str:
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        if not isinstance(value, str):
            raise TypeError("selection_fingerprint must be a string")
        if not value.strip():
            raise ValueError("selection_fingerprint must not be empty")
        return value

def encode_cursor(
    *,
    selection_fingerprint: str,
    offset: int,
) -> str:
    """Encode a versioned cursor token as base64url JSON without padding."""
    payload = SelectionCursor(
        selection_fingerprint=selection_fingerprint,
        offset=offset,
    )
    data = payload.model_dump(mode="json")
    raw = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def decode_cursor(cursor: str) -> SelectionCursor:
    """Decode and validate a cursor token produced by :func:`encode_cursor`."""
    if not isinstance(cursor, str):
        raise TypeError("cursor must be a string")
    token = cursor.strip()
    if not token:
        raise ValueError("cursor must not be empty")
    if len(token) > 2048 or not re.fullmatch(r"[A-Za-z0-9_-]+", token):
        raise ValueError("invalid cursor token")
    padding = "=" * (-len(token) % 4)
    try:
        raw = base64.urlsafe_b64decode(token + padding)
        payload = json.loads(raw.decode("utf-8"))
        return SelectionCursor.model_validate(payload)
    except Exception as exc:  # pragma: no cover - exercised through invalid inputs
        raise ValueError(f"invalid cursor token: {exc}") from exc


# Compatibility aliases for callers that use a shorter name.
Cursor = SelectionCursor
Approval = McpApproval
Error = McpError
Envelope = McpEnvelope[dict[str, Any]]

__all__ = [
    "Approval",
    "ApprovalKind",
    "AskRequest",
    "ContextInput",
    "ContractModel",
    "CouncilPublishRequest",
    "CouncilShowRequest",
    "Cursor",
    "CURSOR_VERSION",
    "DEFAULT_MAX_FILES",
    "DEFAULT_MAX_FILE_CHARS",
    "DEFAULT_MAX_TOTAL_CHARS",
    "decode_cursor",
    "encode_cursor",
    "Envelope",
    "EnvelopeStatus",
    "Error",
    "ErrorClass",
    "HealthRequest",
    "IDENTIFIER_RE",
    "McpApproval",
    "McpEnvelope",
    "McpError",
    "ProfileLevel",
    "ResearchProfile",
    "ResearchRequest",
    "RunRequest",
    "SCHEMA_VERSION",
    "SelectionCursor",
    "SessionMode",
    "SessionListRequest",
    "SessionShowRequest",
    "StartRequest",
    "ToolMode",
    "ToolName",
    "WorkflowRequestBase",
]
