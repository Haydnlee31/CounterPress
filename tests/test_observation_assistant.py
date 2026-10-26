"""Pinned live-card questions must explain the same evidence the fan selected."""
import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from counterpress.assistant.api import install_assistant
from counterpress.assistant.contracts import AskRequest
from counterpress.assistant.narrative import build_claims, default_story, render_story
from counterpress.assistant.observation import observation_question
from counterpress.assistant.service import AssistantService
from counterpress.fan.contracts import FanPreferences, MatchRequest
from counterpress.fan.service import FanService
from counterpress.personalization.contracts import Action
from counterpress.personalization.service import CareerService
from counterpress.personalization.store import DataStore
from counterpress.domain.models import PitchPosition

ROOT = Path(__file__).resolve().parents[1]
MID = 'career-showcase-southbank-redhaven'
QUESTION = 'What changed in this passage of play?'


@pytest.fixture
def source(monkeypatch):
    store = DataStore(ROOT / 'fixtures/personalization')
    service = AssistantService(CareerService(store))
    # Independently authored: cutoff 7:03; windows (1:03,4:03], (4:03,7:03].
    # Exactly one shot before and three after, with at least five actions each.
    timetable = [(90_000, 'shot'), (120_000, 'pass'), (150_000, 'pass'),
                 (180_000, 'pass'), (243_000, 'pass'), (250_000, 'shot'),
                 (280_000, 'pass'), (310_000, 'shot'), (350_000, 'pass'),
                 (423_000, 'shot')]
    events = [Action(match_id=MID, event_id=f'obs-{i}', revision=1,
                     delivery_sequence=i, occurrence_order=i, period=1,
                     elapsed_ms=ms, available_period=1, available_ms=ms,
                     club_id='redhaven', player_id='rh09', kind=kind,
                     outcome='complete' if kind == 'pass' else 'saved',
                     source_reference=f'authored:observation:{i}')
              for i, (ms, kind) in enumerate(timetable, 1)]
    original = store.events
    monkeypatch.setattr(store, 'events', lambda mid: events if mid == MID else original(mid))
    yield service, events
    store.close()


def selected(service, preferences=None):
    view = FanService(service.career).observations(MID, MatchRequest(
        cutoff={'period': 1, 'elapsed_ms': 423_000},
        preferences=preferences or FanPreferences(), card_budget=1))
    card = view['observations'][0]
    return AskRequest(question=QUESTION, match_id=MID, cutoff=view['cutoff'],
        club_id=card['club_id'], player_id=card['player_id'],
        observation_id=card['id'], observation_fingerprint=card['fingerprint'],
        through_sequence=view['through_sequence'], preferences=preferences or FanPreferences())


def client(service, **providers):
    app = FastAPI()
    install_assistant(app, lambda: service.career, **providers)
    return TestClient(app)


def comparison_facts(answer):
    return [f for f in answer['facts'] if 'interpretation_kind' not in f['evidence']]


def test_exact_trailing_windows_not_fixed_ten_minute_bins(source):
    service, _ = source
    request = selected(service)
    plan = service.local_plan(request)
    assert plan.analysis == 'match_changes'
    answer = service.answer(plan, request)
    assert answer['status'] == 'answered'
    comparison = comparison_facts(answer)
    assert [f['value'] for f in comparison] == [1, 3]
    assert [f['scope']['observation_window'] for f in comparison] == [
        {'period': 1, 'start_ms': 63_000, 'end_ms': 243_000, 'boundary': '(start,end]'},
        {'period': 1, 'start_ms': 243_000, 'end_ms': 423_000, 'boundary': '(start,end]'}]
    assert all(f['scope']['window'] == 'rolling_observation' for f in comparison)
    assert any('1:03–4:03 → 4:03–7:03' in text for text in answer['text'])
    assert answer['visual']['items'][1]['value'] == 3
    assert answer['facts'][0]['evidence']['observation_fingerprint'] == request.observation_fingerprint
    assert all(ref['elapsed_ms'] <= 423_000 for ref in answer['facts'][0]['evidence']['events'])
    assert build_claims(answer, plan, request)[0]['fact_indices'] == list(range(len(answer['facts'])))
    context = service.context(request)
    assert context['requested_analysis'] == 'match_changes'
    assert 'three-minute' in context['selected']['observation']['comparison']


def test_endpoint_and_existing_agent_use_pinned_tool(source):
    from test_assistant_multiagent import fake_multi
    service, _ = source
    request = selected(service)
    agent, calls = fake_multi(service, request)
    receipt = asyncio.run(agent.research(service, request, lambda: True))
    assert receipt.requests <= 4 and len(calls) == receipt.requests
    assert receipt.plan.analysis == 'match_changes'
    assert not receipt.partial_failures
    with client(service, researcher=agent) as api:
        result = api.post('/api/fan/assistant/ask', json=request.model_dump(by_alias=True))
    assert result.status_code == 200, result.text
    answer = result.json()
    assert [f['value'] for f in comparison_facts(answer)] == [1, 3]
    assert answer['observation_interpretation'] is True
    assert any(block['text'] == answer['text'][0] for block in answer['narrative']['blocks'])


@pytest.mark.parametrize('alteration', [
    {'observation_fingerprint': '0' * 64},
    {'observation_id': 'another-observation'},
    {'cutoff': {'period': 1, 'elapsed_ms': 422_999}},
    {'through_sequence': 9},
    {'through_sequence': 11},
    {'preferences': {'depth': 'analyst'}},
    {'match_id': 'wyscout-2058017'},
])
def test_tampered_or_different_context_is_rejected_before_paid_inference(source, alteration):
    service, _ = source
    body = selected(service).model_dump(by_alias=True) | alteration
    class NeverCalled:
        async def research(self, *args):
            pytest.fail('Invalid observation must be rejected before inference')
    with client(service, researcher=NeverCalled()) as api:
        result = api.post('/api/fan/assistant/ask', json=body)
    assert result.status_code == 409, result.text


def test_correction_during_inference_rejects_stale_claims(source):
    from test_assistant_multiagent import fake_multi
    service, events = source
    request = selected(service)
    engine, _ = fake_multi(service, request)
    class Correcting:
        async def research(self, *args):
            receipt = await engine.research(*args)
            events.append(events[-1].model_copy(update={
                'revision': 2, 'delivery_sequence': 11, 'retracted': True}))
            return receipt
    with client(service, researcher=Correcting()) as api:
        result = api.post('/api/fan/assistant/ask', json=request.model_dump(by_alias=True))
    assert result.status_code == 409, result.text


def test_unrelated_followup_does_not_inherit_the_card_metric_or_window(source):
    service, _ = source
    request = selected(service)
    general = request.model_copy(update={'question': 'What has changed in this match?'})
    assert not observation_question(general)
    answer = service.answer(service.local_plan(general), general)
    assert answer['status'] == 'clarify'
    assert 'two ten-minute' in answer['text'][0]
    unsafe = request.model_copy(update={'question': 'Predict who will win this match'})
    answer = service.answer(service.local_plan(unsafe), unsafe)
    assert answer['status'] == 'unsupported' and not answer['facts']
    other_club = request.model_copy(update={'question': 'What changed for Southbank in this match?'})
    assert not observation_question(other_club)
    assert service.local_plan(other_club).club_id == 'southbank'


def test_chinese_observation_keeps_subject_and_facts(source):
    service, _ = source
    prefs = FanPreferences(language='zh-Hans', favorite_player_ids=['rh09'])
    # Current authored sequence has no involvement increase; the shot card remains.
    request = selected(service, prefs).model_copy(update={'question': '这段比赛发生了什么变化？'})
    answer = service.answer(service.local_plan(request), request)
    assert answer['status'] == 'answered' and any('上半场' in text for text in answer['text'])
    assert [f['value'] for f in comparison_facts(answer)] == [1, 3]


def test_followed_player_comparison_has_player_scope_and_no_inferred_touches(source):
    service, events = source
    # Team activity is unchanged; the followed player's own actions rise 2 -> 5.
    events[:3] = [e.model_copy(update={'player_id': 'rh06'}) for e in events[:3]]
    events[3:] = [e.model_copy(update={'kind': 'pass', 'outcome': 'complete',
        'start': PitchPosition(x=30, y=34), 'end': PitchPosition(x=45, y=34)}) for e in events[3:]]
    request = selected(service, FanPreferences(favorite_player_ids=['rh09']))
    answer = service.answer(service.local_plan(request), request)
    assert request.player_id == 'rh09'
    comparison = comparison_facts(answer)
    assert [f['value'] for f in comparison] == [2, 5]
    assert {f['subject_id'] for f in comparison} == {'rh09'}
    assert {f['subject_kind'] for f in comparison} == {'player'}
    assert {f['metric'] for f in comparison} == {'recorded_on_ball_actions'}
    assert 'touches' not in ' '.join(answer['text'])
    assert answer['observation_interpretation'] is True
    assert any(f['metric'] == 'own_half_actions' and f['value'] == 5 for f in answer['facts'])


def test_passing_comparison_exposes_exact_denominators_and_percentage_points(source):
    service, events = source
    template = events[0]
    events[:] = [template.model_copy(update={
        'event_id': f'pass-{i}', 'delivery_sequence': i + 1, 'occurrence_order': i + 1,
        'elapsed_ms': 70_000 + i * 17_000, 'available_ms': 70_000 + i * 17_000,
        'kind': 'pass', 'outcome': 'complete' if i < 17 else 'incomplete',
        'start': PitchPosition(x=30, y=34), 'end': PitchPosition(x=75, y=34),
    }) for i in range(21)]
    # Before: 11/11; after: 6/10. All observations are known and visible.
    request = selected(service, FanPreferences(depth='analyst'))
    answer = service.answer(service.local_plan(request), request)
    assert [f['value'] for f in comparison_facts(answer)] == [100, 11, 11, 60, 6, 10]
    assert [item['value'] for item in answer['visual']['items']] == [100, 60]
    assert all(f['scope']['observation_window']['boundary'] == '(start,end]' for f in comparison_facts(answer))
    assert answer['observation_interpretation'] is True
    assert any(f['metric'] == 'failed_long_passes' and f['value'] == 4 for f in answer['facts'])


@pytest.mark.parametrize('question', ['Why?', 'Why does it matter?', 'What is driving this change?',
                                     'Explain this insight', 'Why does this observation matter?'])
def test_short_followup_variants_only_bind_with_a_selected_observation(question):
    assert not observation_question(AskRequest(question=question))
    selected_request = AskRequest(question=question, match_id='test-match',
        cutoff={'period': 1, 'elapsed_ms': 423_000}, through_sequence=10,
        observation_id='test-match:1:home:shots_increase', observation_fingerprint='a' * 64)
    assert observation_question(selected_request)
    for unrelated in ('Why is Southbank losing?', 'Why does his career matter?',
                      'Predict what is driving this change', 'Why? Also compare the two clubs'):
        assert not observation_question(selected_request.model_copy(update={'question': unrelated}))


def test_diagnostic_projection_preserves_subject_window_and_required_meaning(source, monkeypatch):
    """Authored tool receipt checks the mapper independently of diagnostic rules."""
    service, events = source
    events[:] = [e.model_copy(update={'start': PitchPosition(x=70 if e.elapsed_ms <= 243_000 else 95, y=34)})
                 if e.kind == 'shot' else e for e in events]
    request = selected(service)
    view = FanService(service.career).observations(MID, MatchRequest(
        cutoff=request.playback, preferences=request.preferences, through_sequence=request.through_sequence))
    row = next(c for c in view['observations'] if c['id'] == request.observation_id)
    refs = [ref for ref in row['evidence'] if ref['kind'] == 'shot']
    diagnostic = {'kind': 'box_access', 'headline': 'Getting closer to goal',
        'text': 'Redhaven’s last three shots came from inside the box; the earlier attempt was from outside.',
        'facts': [
            {'metric': 'shots_inside_box', 'label': 'Shots inside the box', 'value': 0, 'unit': 'count', 'scope_window': 'before'},
            {'metric': 'shots_inside_box', 'label': 'Shots inside the box', 'value': 3, 'unit': 'count', 'scope_window': 'after'},
            {'metric': 'shots_on_target', 'label': 'Shots on target', 'value': 3, 'unit': 'count',
             'subject_kind': 'player', 'subject_id': 'rh09', 'scope_window': 'after'},
            {'metric': 'goals_for', 'label': 'Goals so far', 'value': 0, 'unit': 'count',
             'subject_kind': 'club', 'subject_id': 'southbank', 'scope_window': 'at_cutoff'},
        ], 'evidence': refs, 'context': {'score_for': 0, 'score_against': 0, 'period': 1, 'elapsed_ms': 423_000}}
    row = {**row, 'interpretation': diagnostic, 'text': diagnostic['text'], 'summary':
           'Redhaven have taken 3 shots in the last 3 minutes, up from 1 in the previous 3.'}
    monkeypatch.setattr('counterpress.assistant.observation.pinned_observation', lambda *_: row)
    plan = service.local_plan(request)
    answer = service.answer(plan, request)
    assert answer['text'][0] == diagnostic['text']
    assert answer['text'][1].startswith(row['summary'])
    assert len(answer['text']) == 2 and '2 more shots' not in ' '.join(answer['text'])
    supporting = [f for f in answer['facts'] if 'interpretation_kind' in f['evidence']]
    assert [f['value'] for f in supporting] == [0, 3, 3, 0]
    assert supporting[0]['scope']['observation_window']['end_ms'] == 243_000
    assert supporting[1]['scope']['observation_window']['end_ms'] == 423_000
    assert (supporting[2]['subject_id'], supporting[2]['subject_kind']) == ('rh09', 'player')
    assert supporting[3]['subject_id'] == 'southbank'
    assert supporting[3]['scope']['window'] == 'match_at_cutoff'
    assert 'observation_window' not in supporting[3]['scope']
    assert all(f['evidence']['events'] == refs for f in supporting)
    claims = build_claims(answer, plan, request)
    assert claims[0]['required'] and claims[0]['text'] == diagnostic['text']
    assert default_story(claims, 'casual')[0] == claims[0]
    with pytest.raises(ValueError, match='required'):
        render_story({'lead': claims[1]['id'], 'supporting': []}, claims, 'casual')
    assert render_story({'lead': claims[0]['id'], 'supporting': [claims[1]['id']]}, claims, 'casual') == claims


@pytest.mark.parametrize('missing', ['observation_id', 'observation_fingerprint', 'match_id', 'cutoff', 'through_sequence'])
def test_incomplete_observation_contract_rejected(source, missing):
    service, _ = source
    body = selected(service).model_dump(by_alias=True)
    body.pop(missing)
    with pytest.raises(ValidationError):
        AskRequest.model_validate(body)
