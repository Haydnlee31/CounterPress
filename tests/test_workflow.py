import asyncio
import json
from pathlib import Path

import httpx2
import pytest
from pydantic import SecretStr

from counterpress.adaptation.azure import AzureConfig, ProviderFailure
from counterpress.api.snapshots import SnapshotService
from counterpress.history import SQLiteHistoryStore
from counterpress.workflow.budget import Budget, GuardedTransport
from counterpress.workflow.service import WorkflowService
from test_history import updates

ROOT = Path(__file__).resolve().parents[1]
CONFIG = AzureConfig(endpoint="https://test.openai.azure.com", deployment="test-deployment", api_key=SecretStr("test-key"))


def snapshots(db=":memory:"):
    return SnapshotService(ROOT / "fixtures", SQLiteHistoryStore(db))


def completion(content=None, names=()):
    message = {"role": "assistant", "content": json.dumps(content) if content is not None else None}
    if names:
        message["tool_calls"] = [{"id": f"call_{index}", "type": "function", "function": {"name": name, "arguments": "{}"}}
                                 for index, name in enumerate(names)]
    return httpx2.Response(200, json={"id": "test-completion", "object": "chat.completion", "created": 1,
        "model": "test-deployment", "choices": [{"index": 0, "finish_reason": "tool_calls" if names else "stop", "message": message}]})


def content(message):
    value = message["content"]
    return value if isinstance(value, str) else "".join(part["text"] for part in value)


class Script:
    def __init__(self, *, narrow=False, reject=False, decision_change=None, draft_change=None, names=None):
        self.requests = []
        self.narrow, self.reject = narrow, reject
        self.decision_change, self.draft_change = decision_change or {}, draft_change or {}
        self.names = names or ("compare_windows", "get_data_quality")

    def __call__(self, request):
        assert str(request.url) == "https://test.openai.azure.com/openai/v1/chat/completions"
        assert request.headers["api-key"] == "test-key"
        body = json.loads(request.content)
        self.requests.append(body)
        messages = body["messages"]
        if body["response_format"]["json_schema"]["name"] == "ProducerDraft":
            package = json.loads(content(messages[-1]))
            return completion(package["required_facts"] | {"story": "recovery_increase", "audience": "general", "template": "count_first"} | self.draft_change)
        results = [json.loads(content(message)) for message in messages if message["role"] == "tool"]
        if not results:
            return completion(names=self.names)
        comparison = next((item for item in results if "comparison" in item), {})
        decision = {"decision": "reject" if self.reject else "narrow" if self.narrow else "accept",
                    "story": "none" if self.reject else "recovery_increase",
                    "evidence_id": comparison.get("evidence_id"), "evidence_version": comparison.get("evidence_version"),
                    "reason": "no_increase" if self.reject else "unsupported_tactical_claim" if self.narrow else "supported_count_comparison"}
        return completion(decision | self.decision_change)


def service(app, handler, **kwargs):
    return WorkflowService(app, CONFIG, transport_factory=lambda: httpx2.MockTransport(handler), **kwargs)


def run(app, script, scenario="increase", candidate="recovery_increase", **kwargs):
    return asyncio.run(service(app, script, **kwargs).run(scenario, 780000, candidate))


def test_framework_accepts_supported_story_and_fresh_handoff_survives_restart(tmp_path):
    db = tmp_path / "history.sqlite3"
    app, script = snapshots(db), Script()
    before = app.snapshot("increase", 780000)
    result = run(app, script)
    assert result.status == "accepted", result.model_dump_json()
    assert (result.analyst_requests, result.producer_requests, result.tool_invocations) == (2, 1, 2)
    assert len(script.requests) == result.provider_requests == 3
    assert result.evidence_references == before.evidence.packet.baseline.source_events + before.evidence.packet.current.source_events
    assert result.text == "Eastbridge: 4 high recoveries in 53:00–58:00, compared with 1 in 48:00–53:00."
    handoff = script.requests[-1]
    assert len(handoff["messages"]) == 2 and "tools" not in handoff
    assert "decision" not in content(handoff["messages"][-1])
    assert [m["role"] for m in handoff["messages"]] == ["system", "user"]
    assert handoff["response_format"]["json_schema"]["strict"] is True
    restarted = snapshots(db)
    assert restarted.history("increase").workflows == (result,)
    after = restarted.snapshot("increase", 780000)
    assert after.adaptation.text == result.text and after.insight == before.insight
    assert after.workflow.status == "accepted"
    assert restarted.snapshot("increase", 540000).workflow is None


def test_pressure_candidate_is_narrowed_and_control_is_rejected():
    narrowed = run(snapshots(), Script(narrow=True), candidate="pressure_effectiveness")
    assert narrowed.status == "narrowed" and "pressure" not in narrowed.text
    script = Script(reject=True)
    app = snapshots()
    rejected = run(app, script, scenario="control")
    assert rejected.status == "rejected" and rejected.producer_requests == 0 and rejected.text is None
    assert len(script.requests) == 2 and app.snapshot("control", 780000).insight is None


@pytest.mark.parametrize("kwargs,candidate", [
    ({"decision_change": {"evidence_version": 99}}, "recovery_increase"),
    ({"decision_change": {"story": "none"}}, "recovery_increase"),
    ({}, "pressure_effectiveness"),
    ({"names": ("compare_windows",)}, "recovery_increase"),
    ({"draft_change": {"current_count": 9}}, "recovery_increase"),
    ({"draft_change": {"audience": "coach"}}, "recovery_increase"),
    ({"draft_change": {"explanation": "pressure worked"}}, "recovery_increase"),
])
def test_unsupported_decisions_and_drafts_leave_factual_fallback(kwargs, candidate):
    app = snapshots()
    result = run(app, Script(**kwargs), candidate=candidate)
    assert result.status == "invalid" and result.text is None
    assert app.snapshot("increase", 780000).adaptation is None
    assert app.snapshot("increase", 780000).insight.facts.current_count == 4


def test_four_tools_in_one_batch_never_execute_the_fourth():
    script = Script(names=("compare_windows", "get_data_quality", "get_event_sequence", "compare_windows"))
    result = run(snapshots(), script)
    assert result.status == "budget_exhausted" and result.reason == "tool_invocation_limit"
    assert result.tool_invocations == 3 and len(script.requests) == 1
    assert [action.label for action in result.actions].count("Requested comparison") == 1


def test_optional_sequence_is_bounded_and_uses_only_canonical_cutoff_events():
    script = Script(names=("compare_windows", "get_data_quality", "get_event_sequence"))
    result = run(snapshots(), script)
    assert result.status == "accepted" and result.tool_invocations == 3
    tool_results = [json.loads(content(item)) for item in script.requests[1]["messages"] if item["role"] == "tool"]
    sequence = next(item for item in tool_results if "events" in item)
    assert sequence["total_count"] == 89 and sequence["truncated"] is True
    assert len(sequence["events"]) == 12
    assert all(item["available_at"]["elapsed_ms"] <= 780000 for item in sequence["events"])
    assert [item["occurrence_order"] for item in sequence["events"]] == sorted(item["occurrence_order"] for item in sequence["events"])


def test_repeated_model_tool_requests_cannot_exceed_three_analyst_requests():
    calls = []
    def loop(request):
        calls.append(request)
        return completion(names=("get_data_quality",))
    result = run(snapshots(), loop)
    assert result.status in ("invalid", "budget_exhausted") and result.text is None
    assert len(calls) == result.analyst_requests == 3
    assert result.producer_requests == 0 and result.tool_invocations <= 3


def test_exhausted_deadline_blocks_network_and_tools_before_invocation():
    budget = Budget(8)
    budget.deadline = 0
    with pytest.raises(ProviderFailure, match="total_deadline_exceeded"):
        budget.request("analyst")
    with pytest.raises(ProviderFailure, match="total_deadline_exceeded"):
        budget.invoke_tool()
    assert sum(budget.requests.values()) == budget.tools == 0


def test_decoded_provider_responses_are_not_decompressed_twice():
    import gzip
    script = Script()
    def compressed(request):
        response = script(request)
        return httpx2.Response(200, headers={"Content-Encoding": "gzip"}, content=gzip.compress(response.content))
    assert run(snapshots(), compressed).status == "accepted"


def test_request_limits_guard_actual_transport_and_retry_attempts():
    async def check():
        budget = Budget(8)
        calls = []
        def handle(request):
            calls.append(request)
            return completion({})
        for role, count in (("analyst", 3), ("producer", 1)):
            async with httpx2.AsyncClient(transport=GuardedTransport(budget, role, httpx2.MockTransport(handle))) as client:
                for _ in range(count):
                    await client.post("https://test.openai.azure.com/")
                if role == "producer":
                    with pytest.raises(ProviderFailure, match="provider_request_limit"):
                        await client.post("https://test.openai.azure.com/")
        assert len(calls) == 4
        other = Budget(8)
        for _ in range(3):
            other.request("analyst")
        with pytest.raises(ProviderFailure):
            other.request("analyst")
        assert other.requests["analyst"] == 3
    asyncio.run(check())


def test_timeout_cancels_provider_and_preserves_match_calculations():
    cancelled = []
    async def slow(request):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)
    app = snapshots()
    # Exercise cancellation of an entered provider, not cold fixture projection.
    # A 50 ms total budget can expire before the first request on shared CI.
    app.snapshot("increase", 780000)
    result = run(app, slow, timeout_seconds=0.5)
    assert result.status == "timeout" and result.provider_requests == 1 and cancelled == [True]
    assert result.duration_ms < 2000 and result.text is None
    assert app.snapshot("increase", 780000).insight.facts.current_count == 4


@pytest.mark.parametrize("pause_at,reason", [(2, "evidence_changed_before_handoff"), (3, "evidence_changed_before_commit")])
def test_corrections_while_pending_discard_results_and_do_not_block_replay(tmp_path, pause_at, reason):
    db = tmp_path / "history.sqlite3"
    app, script = snapshots(db), Script()
    async def check():
        entered, release = asyncio.Event(), asyncio.Event()
        async def pending(request):
            if len(script.requests) + 1 == pause_at:
                entered.set()
                await release.wait()
            return script(request)
        task = asyncio.create_task(service(app, pending).run("increase", 780000))
        await asyncio.wait_for(entered.wait(), 2)
        other = snapshots(db)
        assert other.snapshot("increase", 540000).state.source_delivery_cursor == 53
        other.ingest("increase", updates()[:3])
        assert other.snapshot("increase", 790000).insight is None
        release.set()
        result = await task
        assert result.status == "stale" and result.reason == reason and result.text is None
        assert result.provider_requests == pause_at
        assert app.snapshot("increase", 780000).workflow is None
        assert app.snapshot("increase", 790000).workflow.status == "stale"
        assert app.snapshot("increase", 780000).adaptation is None
    asyncio.run(check())


@pytest.mark.parametrize("kind,status", [("rate", "provider_error"), ("redirect", "provider_error"),
    ("refusal", "refused"), ("malformed", "invalid"), ("large", "invalid"), ("timeout", "timeout")])
def test_provider_failures_never_retry_or_persist_raw_diagnostics(kind, status):
    calls = []
    def handle(request):
        calls.append(request)
        if kind == "timeout":
            raise httpx2.ReadTimeout("SECRET")
        if kind == "refusal":
            return httpx2.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"refusal": "SECRET"}}]})
        return httpx2.Response(429 if kind == "rate" else 302 if kind == "redirect" else 200,
                              text="SECRET" * (12000 if kind == "large" else 1), headers={"Location": "https://elsewhere.example"})
    result = run(snapshots(), handle)
    assert result.status == status and result.provider_requests == len(calls) == 1
    assert "SECRET" not in result.model_dump_json() and result.text is None


def test_expiry_unconfigured_incomplete_and_historical_do_not_publish(monkeypatch):
    app = snapshots()
    result = run(app, Script())
    monkeypatch.setattr("counterpress.api.snapshots.time", lambda: result.expires_at_unix_ms / 1000)
    assert app.snapshot("increase", 780000).adaptation is None
    ticks = iter([1000, 61000])
    assert run(snapshots(), Script(), now=lambda: next(ticks)).status == "expired"
    assert asyncio.run(WorkflowService(app, None).run("increase", 780000)).status == "unconfigured"
    script = Script()
    assert asyncio.run(service(app, script).run("increase", 540000)).status == "ineligible"
    app.ingest("increase", updates()[:1])
    assert run(app, script).status == "stale" and not script.requests


def test_workflow_history_is_append_only():
    app = snapshots()
    result = run(app, Script())
    with pytest.raises(ValueError, match="cannot be rewritten"):
        app.store.transact("increase", lambda previous: previous.model_copy(update={"workflows": ()}))
    assert app.history("increase").workflows == (result,)
