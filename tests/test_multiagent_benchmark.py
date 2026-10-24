"""Independent benchmark scoring: plausible facts cannot mask missing specialists."""
import copy
import json
from pathlib import Path

import pytest

from counterpress.assistant.evaluation import AttemptBudget, lookup
from counterpress.assistant.multiagent_evaluation import expected_parts, load_multiagent_cases, score_multiagent
from counterpress.assistant.service import AssistantService
from counterpress.personalization.service import CareerService
from counterpress.personalization.store import DataStore

ROOT = Path(__file__).resolve().parents[1]
CORPUS = json.loads((ROOT/'fixtures/assistant/multiagent_questions.json').read_text())
CASES = {case['id']: case for case in CORPUS['cases']}


@pytest.fixture(scope='module')
def service():
    store = DataStore(ROOT/'fixtures/personalization')
    yield AssistantService(CareerService(store))
    store.close()


def verified_lookup(service):
    case = CASES['multi_goals_direct']
    answer, _, duration = lookup(service, case)
    answer['mode'] = 'azure_agent'
    for claim in answer['narrative']['blocks']: claim['source_role'] = 'career'
    execution = {'roles': ['career'], 'plans': [case['expected_plan']], 'requests': 2, 'partial_failures': []}
    return case, answer, duration, execution


def test_authored_corpus_is_dataset_bound_and_heldout_is_distinct(service):
    core = load_multiagent_cases(ROOT/'fixtures/assistant/multiagent_questions.json', service.store)
    held = load_multiagent_cases(ROOT/'fixtures/assistant/multiagent_heldout.json', service.store)
    fresh = load_multiagent_cases(ROOT/'fixtures/assistant/multiagent_fresh_holdout.json', service.store)
    assert len(core['cases']) == 34 and len(held['cases']) == 8
    assert len(fresh['cases']) == 8
    assert not {c['request']['question'] for c in core['cases']} & {c['request']['question'] for c in held['cases']}
    assert not {c['request']['question'] for c in fresh['cases']} & {c['request']['question'] for c in core['cases']+held['cases']}
    assert sum(4 if c['tasks'] else 2 if c['expected_roles'] else 0 for c in core['cases']+held['cases']) == 84
    assert sum(4 if c['tasks'] else 2 if c['expected_roles'] else 0 for c in fresh['cases']) == 18


@pytest.mark.parametrize('change', ['dataset', 'duplicate', 'span', 'role'])
def test_malformed_labels_fail_before_evaluation(service, tmp_path, change):
    corpus = copy.deepcopy(CORPUS)
    if change == 'dataset': corpus['ledger_sha256'] = 'different'
    elif change == 'duplicate': corpus['cases'].append(corpus['cases'][0])
    elif change == 'span': corpus['cases'][-1]['tasks'][0]['end'] = 900
    else: corpus['cases'][-1]['expected_roles'] = ['career']
    path = tmp_path/'cases.json'
    path.write_text(json.dumps(corpus))
    with pytest.raises(ValueError): load_multiagent_cases(path, service.store)


@pytest.mark.parametrize('change', ['subject', 'scope', 'value', 'evidence', 'visual', 'action', 'story', 'role', 'partial', 'budget', 'fallback'])
def test_benchmark_rejects_plausible_but_wrong_or_incomplete_answers(service, change):
    case, answer, duration, execution = verified_lookup(service)
    assert score_multiagent(service, case, answer, duration, execution=execution)['passed']
    if change == 'subject': answer['facts'][0]['subject_id'] = 'rh08'
    elif change == 'scope': answer['facts'][0]['scope']['season'] = '2025-26'
    elif change == 'value': answer['facts'][0]['value'] += 1
    elif change == 'evidence': answer['facts'][0]['evidence']['baseline_id'] = 'wrong'
    elif change == 'visual': answer['visual']['cells'] = []
    elif change == 'action': answer['actions'][0]['href'] = '#football/player/rh08'
    elif change == 'story': answer['narrative']['blocks'][0]['text'] = 'An unsupported conclusion.'
    elif change == 'role': execution['roles'] = ['match']
    elif change == 'partial': execution['partial_failures'] = ['career:planning_failed']
    elif change == 'budget': execution['requests'] = 5
    else: answer['mode'] = 'lookup_fallback'
    assert not score_multiagent(service, case, answer, duration, execution=execution)['passed']


def test_offline_success_cannot_count_as_multiagent_completion(service):
    case, answer, duration, _ = verified_lookup(service)
    answer['mode'] = 'lookup'
    row = score_multiagent(service, case, answer, duration)
    assert row['facts_passed']
    assert not row['workflow_completed'] and not row['routing_correct'] and not row['passed']


def test_failed_model_plan_does_not_hide_a_correct_calculated_fallback(service):
    case, answer, duration, execution = verified_lookup(service)
    answer['mode'] = 'lookup_fallback'
    answer['fallback_reason'] = 'all_specialists_failed'
    for claim in answer['narrative']['blocks']: claim.pop('source_role', None)
    execution['completed_result'] = False
    execution['plans'] = [{**case['expected_plan'], 'player_ids': ['rh08']}]
    row = score_multiagent(service, case, answer, duration, execution=execution)
    assert row['facts_passed'] and not row['workflow_completed'] and not row['passed']


def test_replay_career_oracle_excludes_current_match(service):
    case = CASES['multi_match_career']
    parts = expected_parts(service, case)
    match, career = parts
    assert match['request'].playback is not None and career['request'].playback is None
    assert career['request'].as_of == service.store.row(case['request']['match_id'])['kickoff']
    assert next(f for f in match['answer']['facts'] if f['metric'] == 'career_goals')['value'] == 75
    # Two goals in this fixture take the recorded pre-match 73 to the milestone 75.
    assert next(f for f in career['answer']['facts'] if f['metric'] == 'goals')['value'] == 73
    assert all(claim['text'].startswith('Before this match kicked off: ') for claim in career['claims'])


def test_expanded_evaluation_budget_keeps_old_ledger_and_daily_bound(tmp_path):
    import time
    path = tmp_path/'attempts.sqlite3'
    legacy = AttemptBudget(path, limit=2)
    assert legacy.reserve() and legacy.reserve()
    legacy.close()
    larger = AttemptBudget(path, limit=30, hourly_limit=30, daily_limit=40)
    assert sum(larger.reserve() for _ in range(40)) == 28
    assert larger.denied
    larger.close()
    daily = AttemptBudget(path, limit=30, hourly_limit=30, daily_limit=40)
    # The old attempts remain charged to the day after their hourly window ends.
    daily.db.execute('UPDATE attempts SET at=?', (time.time()-3700,))
    daily.db.commit()
    assert sum(daily.reserve() for _ in range(40)) == 10
    daily.close()
    with pytest.raises(ValueError): AttemptBudget(path, limit=121, hourly_limit=121)
    with pytest.raises(ValueError): AttemptBudget(path, limit=20, daily_limit=601)
