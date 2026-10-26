"""Official Foundry Responses HTTP host; no public app route or browser credentials."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sqlite3

from .contracts import parse_packet
from .runtime import AnalystRuntime, Completion


class SessionPermit:
    """One paid run per sandbox, survives process restart and idle resumption."""
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def acquire(self):
        with sqlite3.connect(self.path, timeout=2) as db:
            db.execute("CREATE TABLE IF NOT EXISTS permit (id INTEGER PRIMARY KEY CHECK(id=1))")
            try:
                db.execute("INSERT INTO permit VALUES (1)")
            except sqlite3.IntegrityError as exc:
                raise ValueError("session_run_limit") from exc


class NativeCompletions:
    def __init__(self, project, manifest: dict):
        required = {"chance", "defence", "control", "players", "synthesis"}
        if set(manifest) != required or any(set(x) != {"name", "version"} for x in manifest.values()):
            raise ValueError("invalid_agent_manifest")
        self.manifest = manifest
        self.clients = {role: project.get_openai_client(agent_name=reference["name"], max_retries=0, timeout=30)
                        for role, reference in manifest.items()}

    async def __call__(self, role: str, payload: str, max_tokens: int) -> Completion:
        reference = self.manifest[role]
        response = await self.clients[role].responses.create(
            input=payload, max_output_tokens=max_tokens, parallel_tool_calls=False, store=False,
            extra_body={"agent_reference": {"type": "agent_reference", **reference}},
        )
        if response.status != "completed":
            raise ValueError("incomplete_agent_response")
        actual = getattr(response, "agent_reference", None)
        if hasattr(actual, "model_dump"):
            actual = actual.model_dump()
        if not isinstance(actual, dict) or any(str(actual.get(key)) != reference[key] for key in ("name", "version")):
            raise ValueError("agent_version_mismatch")
        usage = response.usage
        return Completion(response.output_text, usage.input_tokens if usage else 0,
                          usage.output_tokens if usage else 0)


def create_app(runtime: AnalystRuntime | None = None, *, permit: SessionPermit | None = None):
    protocol = os.environ.get("FOOTIE_ANALYST_PROTOCOL", "candidate-v1")
    if protocol not in ("candidate-v1", "roundtable-v2"):
        raise ValueError("unsupported_analyst_protocol")
    from azure.ai.agentserver.responses import ResponsesAgentServerHost, ResponsesServerOptions, TextResponse, InMemoryResponseProvider
    # No automatic HTTP/model-content instrumentation. Native Foundry agent runs
    # remain inspectable; content logging is not needed to record routing/status.
    app = ResponsesAgentServerHost(
        configure_observability=None, store=InMemoryResponseProvider(),
        options=ResponsesServerOptions(default_fetch_history_count=1, resilient_background=False,
                                       steerable_conversations=False, shutdown_grace_period_seconds=5),
    )
    state = {"runtime": runtime, "project": None, "credential": None}

    @app.response_handler
    async def handler(request, context, cancellation_signal):
        raw = await context.get_input_text() or ""
        # Validate before consuming the one-run permit or creating cloud clients.
        discussion = protocol == "roundtable-v2"
        if discussion:
            from .discussion import parse_discussion
            parse_discussion(raw)
        else:
            parse_packet(raw)
        if permit is not None:
            permit.acquire()
        if context.shutdown.is_set() or cancellation_signal.is_set():
            raise asyncio.CancelledError
        if state["runtime"] is None:
            from azure.ai.projects.aio import AIProjectClient
            from azure.identity.aio import DefaultAzureCredential
            endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "")
            if not endpoint.startswith("https://"):
                raise ValueError("invalid_project_configuration")
            credential = DefaultAzureCredential()
            project = AIProjectClient(endpoint=endpoint, credential=credential)
            state["project"], state["credential"] = project, credential
            runtime_type = AnalystRuntime
            if discussion:
                from .discussion import NativeDiscussion
                runtime_type = NativeDiscussion
            state["runtime"] = runtime_type(NativeCompletions(
                project, json.loads(os.environ["FOOTIE_SPECIALIST_MANIFEST"])))
        result = await state["runtime"].run(raw, cancellation_signal)
        return TextResponse(context, request, text=json.dumps(result, separators=(",", ":")))

    return app


def main():
    # Foundry gives each session its own persisted HOME; no session can reset
    # the permit merely by restarting its process or idling the compute.
    permit = SessionPermit(Path.home() / ".footie-analyst" / "permit.sqlite3")
    create_app(permit=permit).run()


if __name__ == "__main__":
    main()
