from __future__ import annotations

import base64
import importlib.util
import json
import sys
import unittest
from pathlib import Path

from pydantic import ValidationError


MODULE_PATH = Path(__file__).resolve().parents[1] / "mcp_contract.py"
SPEC = importlib.util.spec_from_file_location("mcp_contract_under_test", MODULE_PATH)
assert SPEC and SPEC.loader
mcp_contract = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mcp_contract
SPEC.loader.exec_module(mcp_contract)


class McpContractTests(unittest.TestCase):
    def test_context_defaults_align_with_existing_helper(self) -> None:
        context = mcp_contract.ContextInput()

        self.assertEqual(context.max_files, mcp_contract.DEFAULT_MAX_FILES)
        self.assertEqual(context.max_file_chars, mcp_contract.DEFAULT_MAX_FILE_CHARS)
        self.assertEqual(context.max_total_chars, mcp_contract.DEFAULT_MAX_TOTAL_CHARS)
        self.assertFalse(context.follow_symlinks)
        self.assertEqual(context.files, [])
        self.assertEqual(context.directories, [])

    def test_request_models_forbid_extra_fields(self) -> None:
        with self.assertRaises(ValidationError):
            mcp_contract.RunRequest(
                request_id="req-1",
                prompt="Do the thing",
                mode=mcp_contract.ToolMode.review,
                artifact_write=False,
                extra_field=True,
            )

    def test_cursor_round_trip_preserves_selection_fingerprint(self) -> None:
        cursor = mcp_contract.encode_cursor(
            selection_fingerprint="session_list",
            offset=12,
        )
        decoded = mcp_contract.decode_cursor(cursor)

        self.assertEqual(decoded.selection_fingerprint, "session_list")
        self.assertEqual(decoded.offset, 12)

    def test_envelope_shape_is_json_serializable(self) -> None:
        envelope = mcp_contract.McpEnvelope(
            request_id="req_123",
            status=mcp_contract.EnvelopeStatus.completed,
            summary="ok",
            result={"ready": True},
        )

        self.assertTrue(json.loads(envelope.model_dump_json())["result"]["ready"])

    def test_run_request_requires_artifact_write(self) -> None:
        with self.assertRaises(ValidationError):
            mcp_contract.RunRequest(
                request_id="req-1",
                prompt="Do the thing",
                mode=mcp_contract.ToolMode.review,
            )

    def test_identifier_validation_rejects_empty_or_pathlike_values(self) -> None:
        with self.assertRaises(ValidationError):
            mcp_contract.AskRequest(
                request_id=" ",
                prompt="Hi",
                artifact_write=False,
                session_id="session-1",
                expected_turn=0,
            )

        with self.assertRaises(ValidationError):
            mcp_contract.AskRequest(
                request_id="req-1",
                prompt="Hi",
                artifact_write=False,
                session_id="session/1",
                expected_turn=0,
            )

        with self.assertRaises(ValidationError):
            mcp_contract.WorkflowRequestBase(
                request_id="req-1",
                prompt="Hi",
                artifact_write=False,
                providers=[" provider-a "],
            )

    def test_context_and_provider_items_have_bounded_lengths(self) -> None:
        with self.assertRaises(ValidationError):
            mcp_contract.ContextInput(files=["x" * 4097])
        with self.assertRaises(ValidationError):
            mcp_contract.ContextInput(include=["x" * 1025])
        with self.assertRaises(ValidationError):
            mcp_contract.WorkflowRequestBase(
                request_id="req-1",
                prompt="Hi",
                artifact_write=False,
                providers=["x" * 129],
            )

    def test_schema_marks_artifact_write_required(self) -> None:
        schema = mcp_contract.RunRequest.model_json_schema()

        self.assertIn("artifact_write", schema["required"])
        self.assertIn("mode", schema["required"])
        self.assertIn("request_id", schema["required"])
        self.assertIn("prompt", schema["required"])

    def test_error_alias_uses_class_key(self) -> None:
        error = mcp_contract.McpError(
            error_class=mcp_contract.ErrorClass.provider_timeout,
            message="timeout",
            retryable=True,
        )

        self.assertEqual(error.model_dump(by_alias=True)["class"], "provider_timeout")

    def test_envelope_enforces_failed_error_contract(self) -> None:
        with self.assertRaises(ValidationError):
            mcp_contract.McpEnvelope(
                request_id="req-1",
                status=mcp_contract.EnvelopeStatus.failed,
                summary="failed",
                result={},
            )

        with self.assertRaises(ValidationError):
            mcp_contract.McpEnvelope(
                request_id="req-1",
                status=mcp_contract.EnvelopeStatus.completed,
                summary="ok",
                result={},
                error=mcp_contract.McpError(
                    error_class=mcp_contract.ErrorClass.internal_error,
                    message="bad",
                    retryable=False,
                ),
            )

        envelope = mcp_contract.McpEnvelope(
            request_id="req-1",
            status=mcp_contract.EnvelopeStatus.completed,
            summary="ok",
            result={},
            artifact_dir="runs/req-1",
        )
        self.assertEqual(envelope.artifact_dir, "runs/req-1")

    def test_cursor_round_trip_and_offset_validation(self) -> None:
        cursor = mcp_contract.encode_cursor(
            selection_fingerprint="abc123",
            offset=3,
        )
        decoded = mcp_contract.decode_cursor(cursor)

        self.assertEqual(decoded.version, mcp_contract.CURSOR_VERSION)
        self.assertEqual(decoded.selection_fingerprint, "abc123")
        self.assertEqual(decoded.offset, 3)

        payload = json.loads(
            base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode("utf-8")
        )
        payload["version"] = 2
        bad_cursor = base64.urlsafe_b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).rstrip(b"=").decode("ascii")

        with self.assertRaises(ValueError):
            mcp_contract.decode_cursor(bad_cursor)

        with self.assertRaises(ValueError):
            mcp_contract.encode_cursor(
                selection_fingerprint="abc123",
                offset=1_000_001,
            )

    def test_start_supports_council_and_human_session_labels(self) -> None:
        request = mcp_contract.StartRequest(
            request_id="req-council",
            prompt="Explore this idea",
            mode="council",
            session_label="  Long-term design council  ",
            artifact_write=True,
            model_egress=True,
        )

        self.assertEqual(request.mode, mcp_contract.SessionMode.council)
        self.assertEqual(request.session_label, "Long-term design council")

    def test_envelope_accepts_only_relative_artifact_paths(self) -> None:
        envelope = mcp_contract.McpEnvelope(
            request_id="req-1",
            status=mcp_contract.EnvelopeStatus.completed,
            summary="ok",
            artifact_dir=".argos\\mcp\\sessions\\adv_20260101T000000_1234abcd",
            result={},
        )
        self.assertEqual(
            envelope.artifact_dir,
            ".argos/mcp/sessions/adv_20260101T000000_1234abcd",
        )

        with self.assertRaises(ValidationError):
            mcp_contract.McpEnvelope(
                request_id="req-1",
                status=mcp_contract.EnvelopeStatus.completed,
                summary="ok",
                artifact_dir="C:\\outside",
                result={},
            )

        with self.assertRaises(ValidationError):
            mcp_contract.McpEnvelope(
                request_id="req-1",
                status=mcp_contract.EnvelopeStatus.completed,
                summary="ok",
                artifact_dir=".argos/mcp/sessions/run:metadata",
                result={},
            )


if __name__ == "__main__":
    unittest.main()
