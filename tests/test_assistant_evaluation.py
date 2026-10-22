"""Evaluation must detect wrong semantics even when all returned numbers are real."""
import copy
import json
from pathlib import Path

import pytest
from counterpress.assistant.contracts import AskRequest
from counterpress.assistant.evaluation import AttemptBudget, load_cases, lookup, score, summarize
from counterpress.assistant.service import AssistantService, blank
from counterpress.personalization.service import CareerService
from counterpress.personalization.store import DataStore

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT/'fixtures/assistant/questions.json').read_text())['cases']

@pytest.fixture(scope='module')
def service():
    store=DataStore(ROOT/'fixtures/personalization')
    yield AssistantService(CareerService(store))
    store.close()

@pytest.mark.parametrize('case',[c for c in CASES if not c['mutation']],ids=lambda c:c['id'])
def test_authored_intent_regressions(service,case):
    answer,raw,duration=lookup(service,case)
    result=score(service,case,answer,raw,duration)
    assert result['passed'], result

@pytest.mark.parametrize('change',['subject','scope','value','evidence','chart','story','action'])
def test_evaluator_rejects_wrong_but_plausible_answer(service,change):
    case=CASES[0];answer,raw,duration=lookup(service,case)
    if change=='subject':answer['facts'][0]['subject_id']='rh08'
    elif change=='scope':answer['facts'][0]['scope']['season']='2025-26'
    elif change=='value':answer['facts'][0]['value']+=1
    elif change=='evidence':answer['facts'][0]['evidence']['baseline_id']='wrong'
    elif change=='chart':answer['visual']['cells']=[]
    elif change=='story':answer['narrative']['blocks'][0]['text']='Invented claim'
    elif change=='action':answer['actions'][0]['href']='#football/player/rh08'
    assert not score(service,case,answer,raw,duration)['passed']


def test_fallback_does_not_hide_failed_model_interpretation(service):
    case=CASES[0];answer,_,duration=lookup(service,case)
    answer['mode']='lookup_fallback';answer['fallback_reason']='plan_rejected'
    row=score(service,case,answer,blank('stats',player_ids=['rh08']).model_dump(),duration,attempted=True)
    report=summarize([row])
    assert row['passed'] and report['model_routing']=={'passed':0,'total':1}
    assert report['fallbacks']=={'plan_rejected':1}


def test_budget_is_persistent_atomic_and_bounded(tmp_path):
    path=tmp_path/'budget.sqlite3'
    a=AttemptBudget(path,limit=2);b=AttemptBudget(path)
    assert a.reserve() and a.reserve() and not a.reserve()
    for _ in range(18):assert b.reserve()
    assert not b.reserve()
    a.close();b.close()
    c=AttemptBudget(path)
    assert not c.reserve()
    c.close()
    with pytest.raises(ValueError):AttemptBudget(path,21)


def test_agent_gate_does_not_count_fallback_or_half_finished_budget_as_success():
    from counterpress.assistant.evaluation import release_gate
    row={'passed':True,'model_attempted':True,'raw_intent_correct':True,'mode':'azure_agent','fallback':None}
    assert release_gate([row],1,azure=True,agent=True)=='passed'
    fallback={**row,'mode':'lookup_fallback','fallback':'query_scope_rejected'}
    assert release_gate([fallback],1,azure=True,agent=True)=='failed'
    halfway={**fallback,'fallback':'model_allowance_exhausted'}
    assert release_gate([halfway],1,azure=True,agent=True)=='incomplete'
    stale={**row,'narrative_fallback':'records_changed'}
    assert release_gate([stale],1,azure=True,agent=True)=='failed'


def test_corpus_requires_matching_dataset_and_unique_ids(service,tmp_path):
    corpus=json.loads((ROOT/'fixtures/assistant/questions.json').read_text())
    for mutation in ['dataset','duplicate']:
        data=copy.deepcopy(corpus)
        if mutation=='dataset':data['ledger_sha256']='invalid'
        else:data['cases'].append(data['cases'][0])
        path=tmp_path/'cases.json';path.write_text(json.dumps(data))
        with pytest.raises(ValueError):load_cases(path,service.store)

@pytest.mark.parametrize('q,plan',[
 ('How many goals does Mateo Cross have last season?',blank('stats',player_ids=['rh09'],season='2026-27')),
 ('Compare Mateo Cross goals in 2025-26 and 2026-27',blank('stats',player_ids=['rh09'],season='2025-26')),
 ('How many goals does Mateo Cross have per 90?',blank('stats',player_ids=['rh09'])),
 ('Show Mateo Cross goals at the 25th minute',blank('stats',player_ids=['rh09'])),
 ('Show Leon Finch save percentage',blank('stats',player_ids=['sb01'],metric='saves')),
 ('How many chances has Enzo Clarke created?',blank('stats',player_ids=['rh08'],metric='assists')),
 ('How many goals and assists does Mateo Cross have?',blank('stats',player_ids=['rh09'])),
])
def test_well_formed_model_plans_cannot_change_explicit_scope(service,q,plan):
    with pytest.raises(ValueError):service.validate(plan,AskRequest(question=q))


def test_budget_can_be_used_by_endpoint_worker_thread(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    budget=AttemptBudget(tmp_path/'worker.sqlite3',limit=2)
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda _:budget.reserve(),range(8)))
        assert sum(results)==2 and budget.used==2
    finally:budget.close()

@pytest.mark.parametrize('case',[c for c in CASES if c['mutation']],ids=lambda c:c['id'])
def test_correction_cases_use_isolated_revision_overlays(case):
    store=DataStore(ROOT/'fixtures/personalization')
    try:
        service=AssistantService(CareerService(store))
        mid='career-showcase-southbank-redhaven'
        events=store.original(mid).events
        goal=next(e for e in events if e.event_id=='e01178')
        store.ingest(mid,[goal.model_copy(update={'revision':2,'delivery_sequence':max(e.delivery_sequence for e in events)+1,
            'available_period':2,'available_ms':2700100,'retracted':True})])
        answer,raw,duration=lookup(service,case)
        assert score(service,case,answer,raw,duration)['passed']
    finally:store.close()


def test_model_must_not_assume_current_season_in_career_view(service):
    for request in [AskRequest(question='How often has Mateo Cross found the net?'),
                    AskRequest(question='How many goals does my favorite player have?',preferences={'favorite_player_ids':['rh09']})]:
        with pytest.raises(ValueError):
            service.validate(blank('stats',player_ids=['rh09'],season='2026-27'),request)


def test_explicit_career_clears_selected_season(service):
    request=AskRequest(question='Show Mateo Cross career goals',season='2025-26')
    plan=service.local_plan(request)
    assert plan.season is None
    assert service.answer(plan,request)['facts'][0]['scope']['season'] is None


def test_recorded_live_wrong_scopes_fall_back_correctly(service):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from counterpress.assistant.api import install_assistant
    from counterpress.assistant.contracts import Plan
    recorded=json.loads((ROOT/'docs/verification/footie-benchmark-azure.json').read_text())['results']
    cases={c['id']:c for c in CASES}
    for row in recorded:
        if row['raw_intent'] is None:continue
        class RecordedPlanner:
            async def plan(self,q,context):return Plan.model_validate(row['raw_intent']),{}
        app=FastAPI();install_assistant(app,lambda:service.career,RecordedPlanner())
        case=cases[row['id']]
        with TestClient(app) as client:
            response=client.post('/api/fan/assistant/ask',json=case['request'])
        assert response.status_code==200
        result=score(service,case,response.json(),row['raw_intent'],0,attempted=True)
        assert result['passed'],result
        if not row['raw_intent_correct']:assert response.json()['mode']=='lookup_fallback'
