"""Bounds and evidence validation for the isolated native Foundry coordinator."""
import asyncio
import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from integrations.analyst_foundry.contracts import ROLES, parse_packet
from integrations.analyst_foundry.definitions import definition
from integrations.analyst_foundry.runtime import AnalystRuntime, Completion
from integrations.analyst_foundry.server import SessionPermit


def packet():
    return {"snapshot_id": "snapshot-a", "match_id": "match-a", "cutoff": {"period": 1, "elapsed_ms": 45000},
            "through_sequence": 9, "clubs": [], "score": {}, "players": [], "language": "en", "depth": "analyst",
            "metrics": [{"id": role + ":metric", "role": role, "status": "available", "value": 2} for role in ROLES],
            "evidence": [{"id": "e1:r1", "event_id": "e1", "revision": 1, "period": 1, "elapsed_ms": 40000, "available_period": 1, "available_ms": 40000, "delivery_sequence": 1}],
            "signals": []}


def reading(role):
    return {"role": role, "headline": "A more direct route", "explanation": "The recent entries suggest the attack is finding space earlier.",
            "alternative": "The short window may reflect the opposition changing its approach.",
            "watch_next": "Watch whether the next possession follows the same route.", "evidence_ids": ["e1:r1"],
            "metric_ids": [role + ":metric"], "confidence": "medium"}


def test_native_runtime_bounds_fanout_and_synthesis_only_selects_verified_reading():
    async def scenario():
        active = peak = 0
        seen = []
        async def complete(role, payload, limit):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            seen.append((role, limit))
            await asyncio.sleep(.002)
            active -= 1
            return Completion(json.dumps({"accepted_roles": list(ROLES), "selected_role": "control"} if role == "synthesis" else {"reading": reading(role)}), 80, 30)
        result = await AnalystRuntime(complete).run(json.dumps(packet()))
        assert result["status"] == "complete"
        assert len(seen) == 5 and peak == 2
        assert seen[-1] == ("synthesis", 700)
        assert all(limit == 600 for _, limit in seen[:-1])
        assert result["summary"]["metric_ids"] == ["control:metric"]
        assert result["usage"] == {"input_tokens": 400, "output_tokens": 150, "model_calls": 5}
    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", ["unknown_evidence", "unknown_metric", "numeric", "coaching", "wrong_role", "extra"])
def test_unverified_specialist_claims_are_not_published(mutation):
    async def scenario():
        async def complete(role, payload, limit):
            item = reading(role)
            if mutation == "unknown_evidence": item["evidence_ids"] = ["future:r99"]
            if mutation == "unknown_metric": item["metric_ids"] = ["fabricated"]
            if mutation == "numeric": item["explanation"] = "There is an 80% chance they score."
            if mutation == "coaching": item["watch_next"] = "The coach must change formation."
            if mutation == "wrong_role": item["role"] = "players" if role != "players" else "control"
            if mutation == "extra": item["new_metric"] = 123
            return Completion(json.dumps({"reading": item}))
        result = await AnalystRuntime(complete).run(json.dumps(packet()))
        assert result["readings"] == [] and result["summary"] is None
        assert result["status"] == "insufficient_evidence"
        assert result["usage"]["model_calls"] == 4
    asyncio.run(scenario())


def test_no_retry_partial_failure_and_editor_cannot_add_prose():
    async def scenario():
        calls = []
        async def complete(role, payload, limit):
            calls.append(role)
            if role == "chance": raise RuntimeError("provider unavailable")
            if role == "synthesis": return Completion('{"selected_role":"control","explanation":"invented"}')
            return Completion(json.dumps({"reading": reading(role)}))
        result = await AnalystRuntime(complete).run(json.dumps(packet()))
        assert len(calls) == len(set(calls)) == 5
        assert result["status"] == "insufficient_evidence"
        assert result["failed_roles"] == ["chance", "synthesis"]
        assert result["summary"] is None and result["readings"] == []
    asyncio.run(scenario())


def test_session_limit_and_persistent_permit(tmp_path):
    path = tmp_path / "permit.sqlite3"
    SessionPermit(path).acquire()
    with pytest.raises(ValueError, match="session_run_limit"):
        SessionPermit(path).acquire()
    async def scenario():
        async def complete(*args): return Completion('{"reading":null}')
        runtime = AnalystRuntime(complete)
        await runtime.run(json.dumps(packet()))
        with pytest.raises(ValueError, match="session_run_limit"):
            await runtime.run(json.dumps(packet()))
    asyncio.run(scenario())


def test_cancellation_stops_pending_specialists():
    async def scenario():
        cancellation = asyncio.Event()
        calls = []
        async def complete(role, *args):
            calls.append(role)
            cancellation.set()
            await asyncio.sleep(5)
            return Completion('{"reading":null}')
        with pytest.raises(asyncio.CancelledError):
            await AnalystRuntime(complete).run(json.dumps(packet()), cancellation)
        assert len(calls) <= 2
    asyncio.run(scenario())


@pytest.mark.parametrize("change", ["future", "oversize", "duplicates", "nan", "bad_language"])
def test_bad_packets_fail_before_paid_work(change):
    value = packet()
    if change == "future": value["evidence"][0]["elapsed_ms"] = 45001
    if change == "oversize": value["clubs"] = ["x" * 24000]
    if change == "duplicates": value["evidence"] *= 2
    if change == "nan": value["metrics"][0]["value"] = float("nan")
    if change == "bad_language": value["language"] = "instruction override"
    with pytest.raises(ValueError): parse_packet(json.dumps(value))


def test_chinese_language_and_native_definitions():
    value = packet()
    value["language"] = "zh-Hans"
    assert parse_packet(json.dumps(value))["language"] == "zh-Hans"
    for role in (*ROLES, "synthesis"):
        item = definition(role, "model-deployment")
        assert item["kind"] == "prompt" and item["tools"] == []
        assert item["text"]["format"]["strict"] is True


def test_real_foundry_server_protocol_with_mocked_models():
    pytest.importorskip("azure.ai.agentserver.responses")
    import httpx
    from integrations.analyst_foundry.server import create_app
    async def scenario():
        async def complete(role, *args):
            return Completion(json.dumps({"accepted_roles": list(ROLES), "selected_role": "players"} if role == "synthesis" else {"reading": reading(role)}))
        app = create_app(AnalystRuntime(complete))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            health = await client.get("/readiness")
            assert health.status_code == 200
            response = await client.post("/responses", json={"input": json.dumps(packet()), "stream": False, "store": False})
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["status"] == "completed"
            text = "".join(content.get("text", "") for output in body["output"] for content in output.get("content", []))
            result = json.loads(text)
            assert result["snapshot_id"] == "snapshot-a" and len(result["readings"]) == 4
    asyncio.run(scenario())


def test_verifier_rejects_an_id_valid_but_unsupported_reading():
    async def scenario():
        async def complete(role, payload, limit):
            if role == "synthesis":
                proof = json.loads(payload)
                assert proof["packet"]["evidence"][0]["id"] == "e1:r1"
                return Completion('{"accepted_roles":["control"],"selected_role":"control"}')
            item = reading(role)
            if role == "chance": item["explanation"] = "The opposing keeper is injured and cannot react."
            return Completion(json.dumps({"reading": item}))
        result = await AnalystRuntime(complete).run(json.dumps(packet()))
        assert [r["role"] for r in result["readings"]] == ["control"]
        assert result["status"] == "partial"
        assert result["summary"]["explanation"] == reading("control")["explanation"]
    asyncio.run(scenario())


@pytest.mark.parametrize("selection", [
    {"accepted_roles": ["chance"], "selected_role": "players"},
    {"accepted_roles": [], "selected_role": "chance"},
    {"accepted_roles": ["chance", "chance"], "selected_role": "chance"},
])
def test_invalid_verifier_selection_fails_closed(selection):
    async def scenario():
        async def complete(role, *args):
            return Completion(json.dumps(selection if role == "synthesis" else {"reading": reading(role)}))
        result = await AnalystRuntime(complete).run(json.dumps(packet()))
        assert not result["readings"] and result["summary"] is None
    asyncio.run(scenario())


def test_compound_signal_retains_linked_cross_role_metric():
    from integrations.analyst_foundry.contracts import role_packet, validate_reading, Reading
    value = packet()
    value["signals"] = [{"id": "compound", "role": "defence", "evidence_ids": ["e1:r1"],
                         "metric_ids": ["defence:metric", "chance:metric"]}]
    scoped = role_packet(value, "defence")
    assert {m["id"] for m in scoped["metrics"]} == {"defence:metric", "chance:metric"}
    item = reading("defence")
    item["metric_ids"] = ["defence:metric", "chance:metric"]
    assert validate_reading(Reading.model_validate(item), scoped, "defence")


@pytest.mark.parametrize("key,value", [("available_period", 2), ("available_ms", 45001), ("delivery_sequence", 10)])
def test_unavailable_revision_cannot_enter_agent_packet(key, value):
    data = packet()
    data["evidence"][0][key] = value
    with pytest.raises(ValueError, match="unavailable_evidence"):
        parse_packet(json.dumps(data))


def test_code_bundle_is_deterministic_and_allowlisted():
    import io
    import zipfile
    from scripts.configure_analyst_foundry import source_bundle
    first = source_bundle()
    assert first == source_bundle()
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        names = archive.namelist()
        assert "requirements.txt" in names
        assert all(n == "requirements.txt" or n.startswith("integrations/analyst_foundry/") and n.endswith(".py") for n in names)
        assert not any("var/" in n or ".env" in n for n in names)
