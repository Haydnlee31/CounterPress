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
            "signals": [], "candidates": [{"id": role + "-candidate", "role": role, "reading": reading(role)} for role in ROLES]}


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
            return Completion(json.dumps({"accepted_roles": list(ROLES), "selected_role": "control"} if role == "synthesis" else {"candidate_id": role + "-candidate"}), 80, 30)
        result = await AnalystRuntime(complete).run(json.dumps(packet()))
        assert result["status"] == "complete"
        assert len(seen) == 5 and peak == 2
        assert seen[-1] == ("synthesis", 1500)
        assert all(limit == 600 for _, limit in seen[:-1])
        assert result["summary"]["metric_ids"] == ["control:metric"]
        assert result["usage"] == {"input_tokens": 400, "output_tokens": 150, "model_calls": 5}
    asyncio.run(scenario())


@pytest.mark.parametrize("mutation", ["unknown_candidate", "wrong_role", "prose_override", "old_prose_contract"])
def test_specialists_cannot_publish_unprovided_claims(mutation):
    async def scenario():
        async def complete(role, payload, limit):
            answer = {"candidate_id": role + "-candidate"}
            if mutation == "unknown_candidate": answer["candidate_id"] = "fabricated"
            if mutation == "wrong_role": answer["candidate_id"] = "players-candidate" if role != "players" else "control-candidate"
            if mutation == "prose_override": answer["explanation"] = "The opposing keeper is injured."
            if mutation == "old_prose_contract": answer = {"reading": reading(role)}
            return Completion(json.dumps(answer))
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
            return Completion(json.dumps({"candidate_id": role + "-candidate"}))
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
        async def complete(*args): return Completion('{"candidate_id":null}')
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
            return Completion('{"candidate_id":null}')
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
            return Completion(json.dumps({"accepted_roles": list(ROLES), "selected_role": "players"} if role == "synthesis" else {"candidate_id": role + "-candidate"}))
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
            return Completion(json.dumps({"candidate_id": role + "-candidate"}))
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
            return Completion(json.dumps(selection if role == "synthesis" else {"candidate_id": role + "-candidate"}))
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
    import stat
    from scripts.configure_analyst_foundry import source_bundle
    first = source_bundle()
    assert first == source_bundle()
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        names = archive.namelist()
        assert "requirements.txt" in names
        assert all(stat.S_ISREG(info.external_attr >> 16) for info in archive.infolist())
        assert all(n == "requirements.txt" or n.startswith("integrations/analyst_foundry/") and n.endswith(".py") for n in names)
        assert not any("var/" in n or ".env" in n for n in names)


def test_numeric_claims_use_cited_values_units_and_legitimate_precision():
    from integrations.analyst_foundry.contracts import Reading, validate_reading
    value = packet()
    value["metrics"][0].update(value=.026413, unit="expected_goals")
    value["metrics"].append({"id": "uncited", "role": "chance", "value": 80, "unit": "percent", "status": "available"})
    value["windows"] = {"current": {"start_ms": 0, "end_ms": 300000}}
    item = reading("chance")
    item["explanation"] = "The geometric xG estimate is about 0.026 in the 5-minute window."
    assert validate_reading(Reading.model_validate(item), value, "chance")
    for prose in ["The estimated xG is 0.5.", "Pass accuracy is 80%.", "The player ran 0.026 metres.", "The estimated xG is 0."]:
        item["explanation"] = prose
        with pytest.raises(ValueError, match="unsupported_prose"):
            validate_reading(Reading.model_validate(item), value, "chance")
    item["metric_ids"].append("uncited")
    item["explanation"] = "There is an 80% chance of scoring."
    with pytest.raises(ValueError, match="unsupported_prose"):
        validate_reading(Reading.model_validate(item), value, "chance")


@pytest.mark.parametrize("prose", ["The final 5 minutes before halftime show fewer recoveries.", "Watch the changes after halftime.", "The second half is becoming open.", "This is near full time.", "The explanation is incomplete, or if,"])
def test_early_temporal_hallucination_and_incomplete_prose_fail_without_verifier(prose):
    from integrations.analyst_foundry.contracts import Reading, validate_reading, clock_context
    data = packet()
    data["cutoff"]["elapsed_ms"] = 1200000
    assert clock_context(data)["elapsed_in_period"] == "20:00"
    item = reading("chance")
    item["alternative"] = prose
    with pytest.raises(ValueError, match="temporal_claim|incomplete_sentence"):
        validate_reading(Reading.model_validate(item), data, "chance")


@pytest.mark.parametrize('mutation', ['duplicate', 'wrong_role', 'unknown_evidence', 'unsupported_number', 'future_phase'])
def test_invalid_candidate_payload_fails_before_any_paid_call(mutation):
    data = packet()
    if mutation == 'duplicate': data['candidates'].append(copy.deepcopy(data['candidates'][0]))
    if mutation == 'wrong_role': data['candidates'][0]['role'] = 'control'
    if mutation == 'unknown_evidence': data['candidates'][0]['reading']['evidence_ids'] = ['not-supplied']
    if mutation == 'unsupported_number': data['candidates'][0]['reading']['explanation'] = 'Pass accuracy reached 99%.'
    if mutation == 'future_phase': data['candidates'][0]['reading']['explanation'] = 'The second half is changing.'
    async def scenario():
        async def complete(*args): raise AssertionError('Invalid candidates must not invoke models')
        with pytest.raises(ValueError): await AnalystRuntime(complete).run(json.dumps(data))
    asyncio.run(scenario())


def test_selected_candidate_is_copied_exactly_and_scope_excludes_other_roles():
    data = packet()
    second = copy.deepcopy(data['candidates'][2])
    second['id'] = 'control-alternative'
    second['reading']['headline'] = 'A quieter route'
    data['candidates'].append(second)
    async def scenario():
        async def complete(role, payload, limit):
            scoped = json.loads(payload)
            if role == 'synthesis': return Completion('{"accepted_roles":["control"],"selected_role":"control"}')
            assert all(c['role'] == role for c in scoped['candidates'])
            return Completion(json.dumps({'candidate_id': 'control-alternative' if role == 'control' else None}))
        result = await AnalystRuntime(complete).run(json.dumps(data))
        assert result['readings'] == [second['reading']]
        assert result['summary']['headline'] == second['reading']['headline']
    asyncio.run(scenario())


def test_native_completion_rejects_response_served_by_different_version():
    from types import SimpleNamespace
    from integrations.analyst_foundry.server import NativeCompletions
    refs = {r: {'name': 'agent-' + r, 'version': '3'} for r in (*ROLES, 'synthesis')}
    class Responses:
        async def create(self, **kwargs):
            return SimpleNamespace(status='completed', agent_reference={'name': 'agent-chance', 'version': '2'},
                                   usage=None, output_text='{"candidate_id":null}')
    class Project:
        def get_openai_client(self, **kwargs): return SimpleNamespace(responses=Responses())
    async def scenario():
        with pytest.raises(ValueError, match='agent_version_mismatch'):
            await NativeCompletions(Project(), refs)('chance', '{}', 600)
    asyncio.run(scenario())


def test_endpoint_version_pin_is_explicit_and_read_back():
    from types import SimpleNamespace
    from scripts.configure_analyst_foundry import pin_versions
    class Agents:
        rules = None
        def update_details(self, name, body): self.rules = body['agent_endpoint']['version_selector']['version_selection_rules']
        def get(self, agent_name):
            return SimpleNamespace(as_dict=lambda: {'agent_endpoint': {'version_selector': {'version_selection_rules': self.rules}}})
    agents = Agents()
    pin_versions(SimpleNamespace(agents=agents), [{'name': 'FootieAnalystDirector', 'version': '8'}])
    assert agents.rules == [{'type': 'FixedRatio', 'agent_version': '8', 'traffic_percentage': 100}]


def test_manifest_changes_when_only_coordinator_code_or_version_changes():
    from scripts.configure_analyst_foundry import manifest_fingerprint
    first = manifest_fingerprint({}, {"name": "director", "version": "7"}, {}, "code-a")
    assert first != manifest_fingerprint({}, {"name": "director", "version": "8"}, {}, "code-a")
    assert first != manifest_fingerprint({}, {"name": "director", "version": "7"}, {}, "code-b")


def test_no_candidates_make_zero_model_calls():
    value = packet()
    value["candidates"] = []
    async def scenario():
        async def complete(*args): raise AssertionError("No candidates means no model calls")
        result = await AnalystRuntime(complete).run(json.dumps(value))
        assert result["usage"]["model_calls"] == 0
        assert result["status"] == "insufficient_evidence"
    asyncio.run(scenario())


def test_phase_boundaries_require_explicit_fixture_lengths_not_conventional_45_minutes():
    from integrations.analyst_foundry.contracts import clock_context
    value = packet()
    value['cutoff']['elapsed_ms'] = 2_700_000
    assert not clock_context(value)['half_time_boundary']
    assert not clock_context(value)['closing_period']
    value['period_lengths_ms'] = {'1': 3_000_000, '2': 2_880_000}
    assert not clock_context(value)['half_time_boundary']
    value['cutoff']['elapsed_ms'] = 3_000_000
    assert clock_context(value)['half_time_boundary']
    value['cutoff'] = {'period': 2, 'elapsed_ms': 2_880_000}
    assert clock_context(value)['full_time_boundary']
    value['cutoff']['elapsed_ms'] += 1
    with pytest.raises(ValueError, match='period_lengths'):
        parse_packet(json.dumps(value))


def test_chinese_digits_are_checked_without_whitespace_before_number():
    from integrations.analyst_foundry.contracts import Reading,validate_reading
    value = packet()
    item = reading('chance')
    item['explanation'] = '这段时间完成了2次射门。'
    assert validate_reading(Reading.model_validate(item),value,'chance')
    item['explanation'] = '这段时间完成了9次射门。'
    with pytest.raises(ValueError,match='unsupported_prose'):
        validate_reading(Reading.model_validate(item),value,'chance')


@pytest.mark.parametrize('protocol',['roundtable-v1','roundtable-v3',''])
def test_obsolete_or_unknown_host_protocol_is_rejected_before_sdk_or_clients(monkeypatch,protocol):
    from integrations.analyst_foundry.server import create_app
    monkeypatch.setenv('FOOTIE_ANALYST_PROTOCOL',protocol)
    with pytest.raises(ValueError,match='unsupported_analyst_protocol'):
        create_app()
