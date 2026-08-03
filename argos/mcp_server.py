# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp==2.0.0"]
# ///

"""Open Argos MCP 2.0 stdio server.

The transport stays intentionally thin.  Typed schema validation lives in
``mcp_contract`` and every policy or workflow decision lives in
``mcp_adapter``.  Nothing in this entrypoint writes non-protocol bytes to
stdout.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

MODULE_DIR = Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from mcp.server import MCPServer  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402

import argos as argos_core  # type: ignore[import-not-found]  # noqa: E402
import mcp_adapter  # noqa: E402
import mcp_contract as contract  # noqa: E402


def _context_payload(
    *,
    files: list[str] | None,
    directories: list[str] | None,
    include: list[str] | None,
    exclude: list[str] | None,
    max_files: int | None,
    max_file_chars: int | None,
    max_total_chars: int | None,
) -> dict[str, Any]:
    return {
        "files": list(files or []),
        "directories": list(directories or []),
        "include": list(include or []),
        "exclude": list(exclude or []),
        "max_files": (
            max_files
            if max_files is not None
            else contract.DEFAULT_MAX_FILES
        ),
        "max_file_chars": (
            max_file_chars
            if max_file_chars is not None
            else contract.DEFAULT_MAX_FILE_CHARS
        ),
        "max_total_chars": (
            max_total_chars
            if max_total_chars is not None
            else contract.DEFAULT_MAX_TOTAL_CHARS
        ),
        "follow_symlinks": False,
    }


def create_mcp_server(
    adapter: mcp_adapter.ArgosMCPAdapter | None = None,
) -> MCPServer:
    bridge = adapter or mcp_adapter.ArgosMCPAdapter()
    server = MCPServer(
        name="open-argos",
        title="Open Argos",
        description=(
            "Typed, workspace-contained MCP bridge for local Argos workflows."
        ),
        instructions=(
            "Inspection tools are read-only. Workflow tools require explicit "
            "artifact_write plus the relevant model or retrieval egress flags. "
            "Reuse request_id only to replay the exact same request."
        ),
        version=argos_core.VERSION,
    )

    read_annotations = ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
    write_annotations = ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
    research_annotations = ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )

    @server.tool(
        "argos_health",
        description=(
            "Inspect local bridge readiness and configured logical providers "
            "without contacting them."
        ),
        annotations=read_annotations,
        structured_output=True,
    )
    async def argos_health(*, probe_paths: bool = False) -> dict[str, Any]:
        return await bridge.argos_health(
            contract.HealthRequest(probe_paths=probe_paths)
        )

    @server.tool(
        "argos_session_list",
        description="List bounded, sanitized Argos sessions in this workspace.",
        annotations=read_annotations,
        structured_output=True,
    )
    async def argos_session_list(
        *,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        return await bridge.argos_session_list(
            contract.SessionListRequest(limit=limit, cursor=cursor)
        )

    @server.tool(
        "argos_session_show",
        description="Show a sanitized Argos session summary and turn index.",
        annotations=read_annotations,
        structured_output=True,
    )
    async def argos_session_show(
        *,
        session_id: str,
        turn_limit: int | None = None,
    ) -> dict[str, Any]:
        return await bridge.argos_session_show(
            contract.SessionShowRequest(
                session_id=session_id,
                turn_limit=turn_limit,
            )
        )

    @server.tool(
        "argos_council_show",
        description="Show Council membership, turn index, and latest synthesis.",
        annotations=read_annotations,
        structured_output=True,
    )
    async def argos_council_show(
        *,
        council_id: str,
        turn_limit: int | None = None,
    ) -> dict[str, Any]:
        return await bridge.argos_council_show(
            contract.CouncilShowRequest(
                council_id=council_id,
                turn_limit=turn_limit,
            )
        )

    @server.tool(
        "argos_run",
        description=(
            "Execute one bounded Argos mode. Requires artifact_write and "
            "model_egress."
        ),
        annotations=write_annotations,
        structured_output=True,
    )
    async def argos_run(
        *,
        request_id: str,
        prompt: str,
        mode: str,
        profile: str = "medium",
        files: list[str] | None = None,
        directories: list[str] | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        max_files: int | None = None,
        max_file_chars: int | None = None,
        max_total_chars: int | None = None,
        images: list[str] | None = None,
        providers: list[str] | None = None,
        artifact_write: bool,
        model_egress: bool = False,
    ) -> dict[str, Any]:
        request = contract.RunRequest(
            request_id=request_id,
            prompt=prompt,
            mode=mode,
            profile=profile,
            context=_context_payload(
                files=files,
                directories=directories,
                include=include,
                exclude=exclude,
                max_files=max_files,
                max_file_chars=max_file_chars,
                max_total_chars=max_total_chars,
            ),
            images=list(images or []),
            providers=list(providers or []),
            artifact_write=artifact_write,
            model_egress=model_egress,
        )
        return await bridge.argos_run(request)

    @server.tool(
        "argos_start",
        description=(
            "Create a session and execute its first turn. The default mode is "
            "Council. Requires artifact_write and model_egress."
        ),
        annotations=write_annotations,
        structured_output=True,
    )
    async def argos_start(
        *,
        request_id: str,
        prompt: str,
        mode: str | None = None,
        profile: str = "medium",
        session_label: str | None = None,
        files: list[str] | None = None,
        directories: list[str] | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        max_files: int | None = None,
        max_file_chars: int | None = None,
        max_total_chars: int | None = None,
        images: list[str] | None = None,
        providers: list[str] | None = None,
        artifact_write: bool,
        model_egress: bool = False,
    ) -> dict[str, Any]:
        request = contract.StartRequest(
            request_id=request_id,
            prompt=prompt,
            mode=mode,
            profile=profile,
            session_label=session_label,
            context=_context_payload(
                files=files,
                directories=directories,
                include=include,
                exclude=exclude,
                max_files=max_files,
                max_file_chars=max_file_chars,
                max_total_chars=max_total_chars,
            ),
            images=list(images or []),
            providers=list(providers or []),
            artifact_write=artifact_write,
            model_egress=model_egress,
        )
        return await bridge.argos_start(request)

    @server.tool(
        "argos_ask",
        description=(
            "Append exactly one turn to a session using expected_turn "
            "optimistic concurrency."
        ),
        annotations=write_annotations,
        structured_output=True,
    )
    async def argos_ask(
        *,
        request_id: str,
        session_id: str,
        expected_turn: int,
        prompt: str,
        profile: str = "medium",
        files: list[str] | None = None,
        directories: list[str] | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        max_files: int | None = None,
        max_file_chars: int | None = None,
        max_total_chars: int | None = None,
        images: list[str] | None = None,
        providers: list[str] | None = None,
        artifact_write: bool,
        model_egress: bool = False,
    ) -> dict[str, Any]:
        request = contract.AskRequest(
            request_id=request_id,
            session_id=session_id,
            expected_turn=expected_turn,
            prompt=prompt,
            profile=profile,
            context=_context_payload(
                files=files,
                directories=directories,
                include=include,
                exclude=exclude,
                max_files=max_files,
                max_file_chars=max_file_chars,
                max_total_chars=max_total_chars,
            ),
            images=list(images or []),
            providers=list(providers or []),
            artifact_write=artifact_write,
            model_egress=model_egress,
        )
        return await bridge.argos_ask(request)

    @server.tool(
        "argos_council_publish",
        description=(
            "Append one immutable-membership Council turn, retain independent "
            "answers, and publish a synthesis."
        ),
        annotations=write_annotations,
        structured_output=True,
    )
    async def argos_council_publish(
        *,
        request_id: str,
        council_id: str,
        expected_turn: int,
        prompt: str,
        profile: str = "medium",
        files: list[str] | None = None,
        directories: list[str] | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        max_files: int | None = None,
        max_file_chars: int | None = None,
        max_total_chars: int | None = None,
        images: list[str] | None = None,
        artifact_write: bool,
        model_egress: bool = False,
    ) -> dict[str, Any]:
        request = contract.CouncilPublishRequest(
            request_id=request_id,
            council_id=council_id,
            expected_turn=expected_turn,
            prompt=prompt,
            profile=profile,
            context=_context_payload(
                files=files,
                directories=directories,
                include=include,
                exclude=exclude,
                max_files=max_files,
                max_file_chars=max_file_chars,
                max_total_chars=max_total_chars,
            ),
            images=list(images or []),
            artifact_write=artifact_write,
            model_egress=model_egress,
        )
        return await bridge.argos_council_publish(request)

    @server.tool(
        "argos_research",
        description=(
            "Run bounded evidence retrieval and optional model synthesis. "
            "Requires artifact_write and retrieval_egress; model synthesis has "
            "a separate approval."
        ),
        annotations=research_annotations,
        structured_output=True,
    )
    async def argos_research(
        *,
        request_id: str,
        prompt: str,
        research_profile: str = "normal",
        max_queries: int | None = None,
        max_sources: int | None = None,
        artifact_write: bool,
        retrieval_egress: bool = False,
        model_egress: bool = False,
        force_model_on_insufficient: bool = False,
    ) -> dict[str, Any]:
        request = contract.ResearchRequest(
            request_id=request_id,
            prompt=prompt,
            research_profile=research_profile,
            max_queries=max_queries,
            max_sources=max_sources,
            artifact_write=artifact_write,
            retrieval_egress=retrieval_egress,
            model_egress=model_egress,
            force_model_on_insufficient=force_model_on_insufficient,
        )
        return await bridge.argos_research(request)

    @server.resource(
        "argos://sessions/{session_id}/summary",
        name="argos_session_summary",
        title="Argos Session Summary",
        description="Sanitized summary for one Argos session.",
        mime_type="application/json",
    )
    async def argos_session_summary(session_id: str) -> str:
        return await bridge.read_resource(
            f"argos://sessions/{session_id}/summary"
        )

    @server.resource(
        "argos://sessions/{session_id}/turns/{turn}",
        name="argos_session_turn",
        title="Argos Session Turn",
        description="Sanitized result for one existing session turn.",
        mime_type="application/json",
    )
    async def argos_session_turn(session_id: str, turn: int) -> str:
        return await bridge.read_resource(
            f"argos://sessions/{session_id}/turns/{turn}"
        )

    @server.resource(
        "argos://sessions/{session_id}/artifacts",
        name="argos_session_artifacts",
        title="Argos Session Artifact Index",
        description="Resource links for existing artifacts in one session.",
        mime_type="application/json",
    )
    async def argos_session_artifacts(session_id: str) -> str:
        return await bridge.read_resource(
            f"argos://sessions/{session_id}/artifacts"
        )

    @server.resource(
        "argos://councils/{council_id}/summary",
        name="argos_council_summary",
        title="Argos Council Summary",
        description="Sanitized Council manifest and latest synthesis.",
        mime_type="application/json",
    )
    async def argos_council_summary(council_id: str) -> str:
        return await bridge.read_resource(
            f"argos://councils/{council_id}/summary"
        )

    @server.resource(
        "argos://councils/{council_id}/turns/{turn}",
        name="argos_council_turn",
        title="Argos Council Turn",
        description="Sanitized result for one existing Council turn.",
        mime_type="application/json",
    )
    async def argos_council_turn(council_id: str, turn: int) -> str:
        return await bridge.read_resource(
            f"argos://councils/{council_id}/turns/{turn}"
        )

    @server.resource(
        "argos://runs/{request_id}/manifest",
        name="argos_run_manifest",
        title="Argos Request Manifest",
        description="Sanitized terminal envelope for one idempotent request.",
        mime_type="application/json",
    )
    async def argos_run_manifest(request_id: str) -> str:
        return await bridge.read_resource(
            f"argos://runs/{request_id}/manifest"
        )

    @server.resource(
        "argos://runs/{request_id}/coverage",
        name="argos_run_coverage",
        title="Argos Research Coverage",
        description="Coverage assessment for an existing research request.",
        mime_type="application/json",
    )
    async def argos_run_coverage(request_id: str) -> str:
        return await bridge.read_resource(
            f"argos://runs/{request_id}/coverage"
        )

    @server.resource(
        "argos://runs/{request_id}/findings",
        name="argos_run_findings",
        title="Argos Findings or Evidence",
        description="Bounded findings or evidence for an existing request.",
        mime_type="application/json",
    )
    async def argos_run_findings(request_id: str) -> str:
        return await bridge.read_resource(
            f"argos://runs/{request_id}/findings"
        )

    return server


mcp = create_mcp_server()


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
