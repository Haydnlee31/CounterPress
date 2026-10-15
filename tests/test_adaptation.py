import asyncio
import json
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from counterpress.adaptation.azure import AzureConfig, AzureDraftProvider, ProviderFailure, load_config
from counterpress.adaptation.contracts import Draft, expected_fields, validate_and_render
from counterpress.adaptation.service import AdaptationService, utc_ms
from counterpress.api.snapshots import SnapshotService
from counterpress.history import SQLiteHistoryStore
from test_history import updates

ROOT = Path(__file__).resolve().parents[1]


class FakeProvider:
    deployment = "test-deployment"

    def __init__(self, change=None):
        self.calls = 0
        self.change = change

    async def generate(self, packet, name, expires):
        self.calls += 1
        fields = expected_fields(packet, name, expires) | {"template": "count_first"}
        if self.change:
            fields.update(self.change)
        return json.dumps(fields)


def snapshots(db=":memory:"):
    return SnapshotService(ROOT / "fixtures", SQLiteHistoryStore(db))


def adapt(app, provider, **kwargs):
    return asyncio.run(AdaptationService(app, provider, **kwargs).adapt("increase", 780000))


def test_supported_packet_commits_approved_text_and_survives_restart(tmp_path):
    db = tmp_path / "history.sqlite3"
    app, provider = snapshots(db), FakeProvider()
    original = app.snapshot("increase", 780000)
    attempt = adapt(app, provider)
    assert attempt.status == "accepted" and attempt.provider_requests == provider.calls == 1
    assert attempt.text == "Eastbridge: 4 high recoveries in 53:00–58:00, compared with 1 in 48:00–53:00."
    assert attempt.prompt_version == "recovery-wording-v1"
    assert attempt.duration_ms >= 0 and attempt.deployment == "test-deployment"
    restored = snapshots(db).snapshot("increase", 780000)
    assert restored.adaptation.text == attempt.text
    assert restored.insight == original.insight
    assert restored.evidence == original.evidence
    assert snapshots(db).history("increase").adaptations == (attempt,)
    assert snapshots(db).snapshot("increase", 540000).adaptation is None


@pytest.mark.parametrize("changes", [
    {"evidence_id": "invented"}, {"evidence_version": 99}, {"subject_team_id": "northport"},
    {"subject_name": "Northport"}, {"baseline_count": 0}, {"current_count": 9},
    {"period": 1}, {"baseline_start_ms": 180001}, {"baseline_end_ms": 479999},
    {"current_start_ms": 480001}, {"current_end_ms": 780001}, {"expires_at_unix_ms": 1},
    {"current_count": "4"}, {"current_count": True}, {"template": "effective_pressure"},
    {"explanation": "The manager's tactics worked."}, {"subject_name": "x" * 1000},
])
def test_invalid_draft_cannot_replace_factual_fallback(changes):
    app, provider = snapshots(), FakeProvider(changes)
    original = app.snapshot("increase", 780000)
    attempt = adapt(app, provider)
    assert attempt.status == "invalid" and attempt.text is None
    assert attempt.provider_requests == provider.calls == 1
    after = app.snapshot("increase", 780000)
    assert after.insight == original.insight and after.adaptation is None


def test_missing_and_non_json_drafts_are_rejected():
    class Broken(FakeProvider):
        async def generate(self, *args):
            return "{not json"
    assert adapt(snapshots(), Broken()).status == "invalid"
    assert adapt(snapshots(), FakeProvider({"template": None})).status == "invalid"


def test_even_matching_facts_cannot_exceed_card_length():
    packet = snapshots().snapshot("increase", 780000).evidence.packet
    name = "x" * 240
    raw = json.dumps(expected_fields(packet, name, 1) | {"template": "count_first"})
    with pytest.raises(ValueError, match="display limit"):
        validate_and_render(raw, packet, name, 1)


def test_total_deadline_cancels_provider_and_leaves_fallback():
    class Slow(FakeProvider):
        cancelled = False
        async def generate(self, *args):
            self.calls += 1
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled = True
    app, provider = snapshots(), Slow()
    attempt = adapt(app, provider, timeout_seconds=0.01)
    assert attempt.status == "timeout" and attempt.provider_requests == provider.calls == 1
    assert provider.cancelled and attempt.duration_ms < 1000
    assert app.snapshot("increase", 780000).insight.facts.current_count == 4
    assert app.snapshot("increase", 780000).adaptation is None


def test_pending_call_does_not_block_metrics_and_correction_discards_result(tmp_path):
    db = tmp_path / "history.sqlite3"
    app = snapshots(db)
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        class Pending(FakeProvider):
            async def generate(self, packet, name, expires):
                entered.set()
                await release.wait()
                return await super().generate(packet, name, expires)
        provider = Pending()
        task = asyncio.create_task(AdaptationService(app, provider).adapt("increase", 780000))
        await entered.wait()
        # Another service can reduce historical state and commit a withdrawal mid-call.
        other = snapshots(db)
        assert other.snapshot("increase", 540000).state.source_delivery_cursor == 53
        other.ingest("increase", updates()[:3])
        assert other.snapshot("increase", 790000).insight is None
        release.set()
        result = await task
        assert result.status == "stale" and result.text is None
        assert result.reason == "evidence_changed_before_commit"
        assert provider.calls == 1
    asyncio.run(run())
    assert app.snapshot("increase", 780000).adaptation is None


def test_existing_adaptation_is_invalidated_by_correction():
    app = snapshots()
    assert adapt(app, FakeProvider()).status == "accepted"
    app.ingest("increase", updates()[:1])
    assert app.snapshot("increase", 780000).adaptation is None
    assert app.snapshot("increase", 785000).adaptation is None
    assert adapt(app, FakeProvider()).status == "stale"  # Historical version must not cause another call.


def test_expiry_before_commit_and_during_display(monkeypatch):
    app = snapshots()
    started = utc_ms()
    times = iter([started, started + 60000])
    assert adapt(app, FakeProvider(), now=lambda: next(times)).status == "expired"
    assert app.snapshot("increase", 780000).adaptation is None
    accepted = adapt(app, FakeProvider())
    monkeypatch.setattr("counterpress.api.snapshots.time", lambda: accepted.expires_at_unix_ms / 1000)
    assert app.snapshot("increase", 780000).adaptation is None
    assert app.snapshot("increase", 780000).insight is not None


def test_no_azure_or_ineligible_comparison_never_calls_provider():
    app, provider = snapshots(), FakeProvider()
    assert adapt(app, None).status == "unconfigured"
    result = asyncio.run(AdaptationService(app, provider).adapt("control", 780000))
    assert result.status == "ineligible" and result.provider_requests == provider.calls == 0
    result = asyncio.run(AdaptationService(app, provider).adapt("increase", 540000))
    assert result.status == "ineligible" and result.provider_requests == provider.calls == 0


def test_configuration_is_explicit_and_secret_safe():
    assert load_config({}) is None
    with pytest.raises(ValueError, match="together"):
        load_config({"AZURE_OPENAI_API_KEY": "secret"})
    values = {"AZURE_OPENAI_ENDPOINT": "http://untrusted.example/?secret", "AZURE_OPENAI_DEPLOYMENT": "test", "AZURE_OPENAI_API_KEY": "secret"}
    with pytest.raises(ValueError) as exc:
        load_config(values)
    assert "secret" not in str(exc.value)
    values["AZURE_OPENAI_ENDPOINT"] = "https://demo.openai.azure.com/openai/v1/"
    config = load_config(values)
    assert "secret" not in repr(config)
    assert config.url == "https://demo.openai.azure.com/openai/v1/chat/completions"


def test_actual_http_adapter_requests_strict_schema_once_and_no_history():
    captured = []
    def handle(request):
        captured.append(request)
        body = json.loads(request.content)
        facts = json.loads(body["messages"][1]["content"])["required_facts"]
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(facts | {"template": "window_first"})}}]})
    config = AzureConfig(endpoint="https://demo.openai.azure.com", deployment="chosen-deployment", api_key=SecretStr("test-only-key"))
    app = snapshots()
    result = adapt(app, AzureDraftProvider(config, httpx.MockTransport(handle)))
    assert result.status == "accepted"
    assert result.text == "From 53:00–58:00, Eastbridge recorded 4 high recoveries; the 48:00–53:00 window had 1."
    assert len(captured) == 1
    request = captured[0]
    assert str(request.url) == "https://demo.openai.azure.com/openai/v1/chat/completions"
    assert request.headers["api-key"] == "test-only-key"
    body = json.loads(request.content)
    assert body["model"] == "chosen-deployment" and body["max_completion_tokens"] == 800
    schema = body["response_format"]["json_schema"]
    assert schema["strict"] is True and schema["schema"]["additionalProperties"] is False
    assert set(schema["schema"]["required"]) == set(Draft.model_fields)
    assert len(body["messages"]) == 2 and "tools" not in body
    assert "secret" not in result.model_dump_json() and "test-only-key" not in result.model_dump_json()


@pytest.mark.parametrize("kind,status,reason", [
    ("refusal", "refused", "provider_refusal"), ("truncated", "invalid", "incomplete_response"),
    ("bad_json", "invalid", "malformed_response"), ("wrong_shape", "invalid", "malformed_response"),
    ("null_message", "invalid", "malformed_response"),
    ("too_large", "invalid", "response_too_large"), ("rate_limit", "provider_error", "http_429"),
    ("redirect", "provider_error", "http_302"), ("timeout", "timeout", "provider_timeout"),
])
def test_provider_failures_are_recorded_without_retry_or_raw_output(kind, status, reason):
    calls = []
    def handle(request):
        calls.append(request)
        if kind == "timeout":
            raise httpx.ReadTimeout("secret diagnostics")
        if kind == "rate_limit":
            return httpx.Response(429, text="secret diagnostics")
        if kind == "redirect":
            return httpx.Response(302, headers={"Location": "https://elsewhere.example/"})
        if kind == "too_large":
            return httpx.Response(200, content=b"x" * 65537)
        if kind == "bad_json":
            return httpx.Response(200, text="secret diagnostics")
        if kind == "wrong_shape":
            return httpx.Response(200, json={"choices": [None]})
        if kind == "null_message":
            return httpx.Response(200, json={"choices": [{"message": None}]})
        return httpx.Response(200, json={"choices": [{"finish_reason": "length" if kind == "truncated" else "stop",
                                                    "message": {"refusal": "secret diagnostics" if kind == "refusal" else None}}]})
    config = AzureConfig(endpoint="https://demo.openai.azure.com", deployment="test", api_key=SecretStr("test-key"))
    result = adapt(snapshots(), AzureDraftProvider(config, httpx.MockTransport(handle)))
    assert result.status == status and result.reason == reason
    assert len(calls) == 1 and result.text is None
    assert "secret" not in result.model_dump_json()
