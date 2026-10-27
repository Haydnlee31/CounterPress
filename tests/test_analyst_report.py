import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from counterpress.analyst.report import report_data, linked_shot, lane, ReportAllowance, ReportRequest, AzureMatchReport, MatchReading, validate_reading
from counterpress.analyst.admission import SQLiteStore
from counterpress.analyst.live_admission import LiveAllowance
from counterpress.analyst.api import install_analyst
from counterpress.analyst.contracts import MATCH_IDS
from counterpress.personalization.store import DataStore
from counterpress.personalization.service import CareerService
from test_analyst_metrics import event,career,MID


def sample():
    return [event(1,1000,player_id='h1',recipient_id='h2',start={'x':60,'y':10},end={'x':80,'y':12}),
            event(2,2000,player_id='h2',recipient_id='h1',start={'x':80,'y':12},end={'x':94,'y':34}),
            event(3,3000,player_id='h1',kind='shot',outcome='goal',goal_for='home',start={'x':94,'y':34},end={'x':105,'y':34}),
            event(4,4000,club_id='away',player_id='a1',kind='other',outcome='own_goal',goal_for='home',start={'x':4,'y':30}),
            event(5,5000,outcome='unknown',start={'x':105,'y':68})]


def test_entry_route_is_not_shot_location_and_own_goal_does_not_inflate_conversion():
    d=report_data(career(sample()),MID);home=d['teams'][0]
    assert home['totals']['goals']==2 and home['totals']['shots']==1 and home['totals']['shot_goals']==1
    assert home['totals']['pass_completion']==100 and home['totals']['known_passes']==2 and home['totals']['passes']==3
    assert home['lanes'][0]=={'lane':'left','shots':1,'goals':1,'conversion':100.0}
    assert d['routes'][0]['entry_lane']=='left' and d['routes'][0]['shot_lane']=='centre'
    assert sum(home['cells'])==4 and home['cells'][17]==1
    assert next(f['value'] for f in d['facts'] if f['id']=='home:all_entries')=={'left':1,'centre':0,'right':0}
    assert next(f['value'] for f in d['facts'] if f['id']=='home:territory')['cells']==home['cells']
    assert lane(0)=='left' and lane(68/3)=='centre' and lane(68)=='right'


@pytest.mark.parametrize('change',[{'club_id':'away','player_id':'a1'}, {'recipient_id':'h2'}, {'outcome':'unknown'}, {'occurrence_order':10}, {'period':2,'available_period':2}])
def test_routes_never_stitch_over_opponents_missing_outcomes_or_broken_links(change):
    es=sample()[:3];es[1]=es[1].model_copy(update=change)
    assert len(linked_shot(es,2))==1


def test_single_shot_has_unknown_entry_and_absent_channel_rate_is_null():
    d=report_data(career([sample()[2]]),MID)
    assert d['routes'][0]['entry_lane']=='unknown'
    assert d['teams'][0]['lanes'][0]['conversion'] is None


def test_corrections_change_report_identity_and_replace_counts():
    es=sample();d=report_data(career(es),MID)
    corrected=es[2].model_copy(update={'revision':2,'delivery_sequence':6,'outcome':'off_target','goal_for':None,'available_ms':6000})
    r=report_data(career(es+[corrected]),MID)
    assert d['source_id']!=r['source_id'] and r['teams'][0]['totals']['shot_goals']==0 and r['teams'][0]['totals']['shots']==1


@pytest.mark.parametrize('mid',MATCH_IDS)
def test_all_library_reports_reconcile_routes_grids_and_scores(mid):
    c=CareerService(DataStore(Path('fixtures/personalization')));d=report_data(c,mid)
    for t in d['teams']:
        assert len(t['cells'])==18 and sum(t['cells'])==t['totals']['located_actions']
        assert sum(l['shots'] for l in t['lanes'])==t['totals']['shots']
        assert sum(l['goals'] for l in t['lanes'])==t['totals']['shot_goals']
        assert t['totals']['goals']==t['totals']['shot_goals']+t['totals']['own_goals_received']
    assert len({f['id'] for f in d['facts']})==len(d['facts'])


@pytest.mark.parametrize('value',[False,1,'true',None])
def test_no_paid_report_without_explicit_boolean_approval(value):
    with pytest.raises(ValidationError):ReportRequest(approve=value)


def test_report_reservation_uses_shared_match_and_total_budget_without_live_settlement_refunds(tmp_path):
    store=SQLiteStore(tmp_path/'budget');reports=ReportAllowance(store);live=LiveAllowance(store)
    job=reports.reserve('report:x',0,'match','report:x',{'period':2,'elapsed_ms':1})
    reports.finish('report:x',job['owner'],{'status':'complete','reading':{'text':'report'}},1)
    assert reports.reserve('report:x',2,'match','report:x',{'period':2,'elapsed_ms':1})['status']=='complete'
    live.reserve('live:y',3,'match','live:y',{'period':1,'elapsed_ms':1})
    state=store.transact(lambda s:(s,s));assert state['spent_cents']==13
    assert state['jobs']['report:x']['accounted_cents']==10
    store.transact(lambda s:({**s,'spent_cents':1200},None))
    assert reports.reserve('report:z',4,'other','scope',{'period':2,'elapsed_ms':1})['status']=='budget_limit'


def test_preview_is_free_and_approved_report_is_shared_with_correction_check(tmp_path):
    class Provider:
        calls=0
        async def analyze(self,data,language):
            self.calls+=1
            return {'status':'complete','reading':{**draft(data),'headline':'Verified'}}
    provider=Provider();app=FastAPI();ledger=LiveAllowance(SQLiteStore(tmp_path/'budget'))
    install_analyst(app,lambda:career(sample()),live_allowance=ledger,report_provider=provider)
    with TestClient(app) as client:
        url=f'/api/analyst/matches/{MID}/report'
        assert client.get(url).json()['status']=='not_requested'
        assert provider.calls==0
        assert client.post(url,json={'approve':False}).status_code==422
        assert client.post(url,json={'approve':True},headers={'origin':'https://evil.example'}).status_code==403
        assert client.post(url,json={'approve':True}).json()['status']=='pending'
        import time;time.sleep(.1)
        assert client.post(url,json={'approve':True}).json()['reading']['headline']=='Verified'
        assert provider.calls==1


def draft(data):
    c={'title':'A pattern','text':'The side created a shooting opportunity.','evidence_ids':[data['facts'][0]['id']]}
    return {'headline':'A match of chances','overview':c,'teams':[{'club_id':t['club_id'],**{k:c for k in ('strength','weakness','player')},'adjustment':{**c,'action':'Review the final pass in the recorded passage.','measure':'Compare the outcomes of the reviewed attempts.'}} for t in data['teams']]}


def test_model_output_requires_known_references_and_both_teams():
    d=report_data(career(sample()),MID);r=draft(d);r['teams'][1]['club_id']='invented'
    with pytest.raises(ValueError):validate_reading(MatchReading.model_validate(r),d)
    r=draft(d);r['overview']['evidence_ids']=['fiction']
    with pytest.raises(ValueError):validate_reading(MatchReading.model_validate(r),d)


def test_independent_reviewer_can_block_entire_report(monkeypatch):
    data=report_data(career(sample()),MID);calls=[]
    async def request(*args,**kwargs):
        calls.append(args[5]);return json.dumps(draft(data) if len(calls)==1 else {'supported':False,'issues':['Unsupported interpretation']}),{}
    monkeypatch.setattr('counterpress.assistant.planner.structured_request',request)
    result=asyncio.run(AzureMatchReport(SimpleNamespace()).analyze(data,'en'))
    assert result['status']=='insufficient_evidence' and result['reading'] is None and len(calls)==2


def test_source_correction_during_generation_prevents_stale_publication(tmp_path):
    es=sample()
    class Provider:
        async def analyze(self,data,language):
            es.append(es[2].model_copy(update={'revision':2,'delivery_sequence':6,'available_ms':6000,'goal_for':None,'outcome':'off_target'}))
            return {'status':'complete','reading':{'headline':'Old score'}}
    app=FastAPI();store=SQLiteStore(tmp_path/'correction');ledger=LiveAllowance(store)
    install_analyst(app,lambda:career(es),live_allowance=ledger,report_provider=Provider())
    with TestClient(app) as client:
        assert client.post(f'/api/analyst/matches/{MID}/report',json={'approve':True}).json()['status']=='pending'
        import time;time.sleep(.1)
        state=store.transact(lambda s:(s,s))
        job=next(iter(state['jobs'].values()))
        assert job['status']=='unavailable' and job['result'] is None and state['spent_cents']==10


def test_passage_records_return_combination_score_context_and_shot_outcomes():
    es=sample()[:3]+[event(4,4000,kind='shot',outcome='blocked',start={'x':90,'y':30})]
    d=report_data(career(es),MID)
    f={f['id']:f['value'] for f in d['facts']}
    first=f['shot:e3:r1']
    assert first['return_pass_before_shot']==['h1','h2','h1']
    assert first['score_before']=='Home 0 – Away 0'
    assert first['observed_duration_seconds']==2
    assert first['last_actions'][1]['recipient']=='h1'
    assert f['shot:e4:r1']['score_before']=='Home 1 – Away 0'
    assert f['shot:e4:r1']['return_pass_before_shot'] is None
    assert f['home:totals']['blocked_shots']==1 and f['home:totals']['shots_on_target']==1
    assert f['match:result']['winner']=='Home'


def test_sparse_archive_does_not_invent_combination_or_recovery():
    d=report_data(career([sample()[2]],source='adapted_archive'),MID)
    shot=next(f['value'] for f in d['facts'] if f['id'].startswith('shot:'))
    assert shot['return_pass_before_shot'] is None and shot['recovery_started_passage'] is False
    assert len(shot['last_actions'])==1


def test_draw_cannot_be_headlined_as_a_win_and_aggregate_cannot_be_invented():
    es=sample()[:3]+[event(4,4000,club_id='away',player_id='a1',kind='shot',outcome='goal',goal_for='away')]
    d=report_data(career(es),MID);r=draft(d)
    r['headline']='Home edges Away after efficient finishing'
    with pytest.raises(ValueError,match='draw_described_as_win'):validate_reading(MatchReading.model_validate(r),d)
    r['headline']='The teams share the points';r['overview']['text']='Home won on aggregate.'
    with pytest.raises(ValueError,match='unsupported_aggregate'):validate_reading(MatchReading.model_validate(r),d)


def test_editor_can_repair_a_draft_reference_before_final_validation(monkeypatch):
    d=report_data(career(sample()),MID);original=draft(d);original['overview']={**original['overview'],'evidence_ids':['invented']}
    calls=[]
    async def request(*args,**kwargs):
        calls.append(args[3])
        return json.dumps(original if len(calls)==1 else {'supported':True,'coaching_ready':True,'issues':[],'reading':draft(d)}),{}
    monkeypatch.setattr('counterpress.assistant.planner.structured_request',request)
    r=asyncio.run(AzureMatchReport(SimpleNamespace()).analyze(d,'en'))
    assert r['status']=='complete' and len(calls)==2
    assert calls[1]['draft']['overview']['evidence_ids']==['invented']
    assert r['reading']['overview']['evidence_ids']!=['invented']


def test_factual_but_generic_review_does_not_publish(monkeypatch):
    d=report_data(career(sample()),MID)
    async def request(*args,**kwargs):
        return json.dumps({'supported':True,'coaching_ready':False,'issues':['Generic coaching task'],'reading':draft(d)}),{}
    monkeypatch.setattr('counterpress.assistant.planner.structured_request',request)
    assert asyncio.run(AzureMatchReport(SimpleNamespace()).review(d,'en',draft(d)))['status']=='insufficient_evidence'


@pytest.mark.parametrize('mid',MATCH_IDS)
def test_full_evidence_and_review_fit_input_budget_without_model_calls(mid,monkeypatch):
    d=report_data(CareerService(DataStore(Path('fixtures/personalization'))),mid);calls=[]
    async def request(config,transport,prompt,data,schema,name,tokens,timeout,**kwargs):
        payload={'model':'gpt-5-mini','messages':[{'role':'system','content':prompt},{'role':'user','content':json.dumps(data,ensure_ascii=False)}],
                 'response_format':{'type':'json_schema','json_schema':{'name':name,'strict':True,'schema':schema}},'max_completion_tokens':tokens,'stream':False,'reasoning_effort':kwargs['reasoning_effort']}
        kwargs['request_guard'](json.dumps(payload).encode());calls.append(name)
        return json.dumps(draft(d) if len(calls)==1 else {'supported':True,'coaching_ready':True,'issues':[],'reading':draft(d)}),{}
    monkeypatch.setattr('counterpress.assistant.planner.structured_request',request)
    assert asyncio.run(AzureMatchReport(SimpleNamespace()).analyze(d,'en'))['status']=='complete'
    assert len(calls)==2


def test_coaching_packet_keeps_whole_match_denominators_and_bound_examples():
    from counterpress.analyst.report import model_context
    d=report_data(CareerService(DataStore(Path('fixtures/personalization'))),MID)
    context,aliases=model_context(d,'en');original={f['id']:f for f in d['facts']}
    selected=[aliases[f['id']] for f in context['facts'] if aliases[f['id']].startswith('shot:')]
    for team in d['teams']:
        own=[key for key in selected if original[key]['value']['club_id']==team['club_id']]
        assert len(own)<=5
        assert any(original[key]['value']['goal'] for key in own)
        fact=next(f for f in context['facts'] if aliases[f['id']]==team['club_id']+':totals')
        assert fact['value']['shots']==team['totals']['shots']
    assert all('role' in f['value'] for f in context['facts'] if aliases[f['id']].startswith('player:'))


def test_review_aliases_resolve_to_real_passages_without_displaying_ids(monkeypatch):
    from counterpress.analyst.report import model_context
    d=report_data(career(sample()),MID);_,aliases=model_context(d,'en');alias=next(iter(aliases));r=draft(d)
    for c in [r['overview']]+[t[k] for t in r['teams'] for k in ('strength','weakness','adjustment','player')]:
        c['evidence_ids']=[alias];c['text']=f'A recorded sequence ({alias}).'
    async def request(*args,**kwargs):return json.dumps({'supported':True,'coaching_ready':True,'issues':[],'reading':r}),{}
    monkeypatch.setattr('counterpress.assistant.planner.structured_request',request)
    result=asyncio.run(AzureMatchReport(SimpleNamespace()).review(d,'en',r))
    assert result['status']=='complete'
    assert result['reading']['overview']['evidence_ids']==[aliases[alias]]
    assert alias not in result['reading']['overview']['text']


def test_writing_packet_omits_incompatible_entry_denominators():
    from counterpress.analyst.report import model_context
    d=report_data(CareerService(DataStore(Path('fixtures/personalization'))),MID)
    context,aliases=model_context(d,'en')
    assert not any(':route:' in ref or ref.endswith(':all_entries') for ref in aliases.values())
    assert len({f['editorial_question'] for f in context['coaching_focus']})==2
    # Charts retain their data; only the writing packet excludes the invalid comparison.
    assert any(f['id'].endswith(':all_entries') for f in d['facts'])
    assert all(t['lanes'] for t in d['teams'])


def test_report_failures_log_safe_diagnostics_without_provider_message(tmp_path,caplog):
    class Provider:
        async def analyze(self,data,language):raise RuntimeError('secret-token-and-private-url')
    app=FastAPI();ledger=LiveAllowance(SQLiteStore(tmp_path/'failure'))
    install_analyst(app,lambda:career(sample()),live_allowance=ledger,report_provider=Provider())
    with TestClient(app) as client:
        client.post(f'/api/analyst/matches/{MID}/report',json={'approve':True})
        import time;time.sleep(.1)
    assert 'analyst_report_failed' in caplog.text and 'RuntimeError' in caplog.text
    assert 'secret-token-and-private-url' not in caplog.text


def test_aliases_used_in_sentences_keep_readable_passage_references():
    from counterpress.analyst.report import readable_text
    facts=[{'id':'shot:e3:r1','label':'Observed shot passage','value':{'clock':'0:03'}}]
    assert readable_text('Review E001 with the passer (E001).',{'E001':'shot:e3:r1'},facts)=='Review the 0:03 passage with the passer.'
    assert readable_text('Compare E001 and E002.',{'E001':'shot:e3:r1','E002':'shot:e3:r1'},facts)=='Compare the 0:03 passage and the 0:03 passage.'


def test_overview_reconciles_cited_match_totals_but_not_qualified_counts():
    from counterpress.analyst.report import reconcile_overview_passes
    d=report_data(career(sample()),MID);r=MatchReading.model_validate(draft(d))
    r.overview.evidence_ids=['home:totals']
    r.overview.text='Home completed 3 passes and nine shots.'
    reconcile_overview_passes(r,d)
    assert r.overview.text=='Home completed 2 of 3 passes and took 1 shot.'
    for text in ('Home completed 1 passes into the box.','Home completed 1 passes in the second half.','At 0:03 Home completed 1 passes.'):
        r.overview.text=text;reconcile_overview_passes(r,d);assert r.overview.text==text
    r.overview.evidence_ids=['shot:e3:r1'];r.overview.text='Home completed 1 passes.'
    reconcile_overview_passes(r,d);assert r.overview.text=='Home completed 1 passes.'


def test_captured_live_report_keeps_verified_totals_and_readable_coaching_actions(monkeypatch):
    fixture=json.loads(Path('fixtures/evaluation/analyst_report_coach_response.json').read_text())
    d=report_data(CareerService(DataStore(Path('fixtures/personalization'))),fixture['match_id'])
    assert d['source_id']==fixture['source_id']
    responses=iter(fixture['outputs'])
    async def request(*args,**kwargs):return json.dumps(next(responses)),{}
    monkeypatch.setattr('counterpress.assistant.planner.structured_request',request)
    result=asyncio.run(AzureMatchReport(SimpleNamespace()).analyze(d,'en'))
    assert result['status']=='complete'
    r=result['reading'];assert r['overview']['text'].startswith(fixture['expected_overview'])
    home,away=r['teams']
    assert '71:12 passage' in home['adjustment']['action']
    assert '11:21 passage and the 20:03 passage' in away['adjustment']['action']
    assert 'Video-review passages the' not in home['adjustment']['action']
    assert 'repeated pattern' not in away['strength']['text']
    assert home['adjustment']['action']!=away['adjustment']['action']


def test_published_report_projects_factual_sections_without_changing_coaching_or_cache():
    from copy import deepcopy
    from counterpress.analyst.report import publication_result
    result=json.loads(Path('fixtures/evaluation/analyst_report_published_response.json').read_text())
    original=deepcopy(result)
    data=report_data(CareerService(DataStore(Path('fixtures/personalization'))),result['match_id'])
    assert data['source_id']==result['source_id']
    projected=publication_result(result,data)
    assert result==original
    text=projected['reading']['overview']['text']
    assert '384 of 442 passes' in text and '316 of 373 passes' in text
    assert 'completed passes (442)' not in text
    for before,after in zip(result['reading']['teams'],projected['reading']['teams']):
        for field in ('strength','weakness','adjustment'):
            assert before[field]==after[field]
    north=next(t for t in projected['reading']['teams'] if t['club_id']=='northport')
    assert 'recovered possession' not in north['player']['text']
    assert 'Jude Rivers → Ben Fletcher → Jude Rivers' in north['player']['text']
    assert '20:03' in north['player']['text']
    assert publication_result(projected,data)==projected
    chinese=publication_result(result,data,'zh-Hans')
    assert '完成384次传球，共尝试442次' in chinese['reading']['overview']['text']
    assert '前锋' in chinese['reading']['teams'][1]['player']['text']


def test_publication_projection_uses_revised_totals_and_does_not_fabricate_passage_links():
    from counterpress.analyst.report import publication_result
    data=report_data(career(sample()),MID)
    r=draft(data)
    for t in r['teams']:
        p=next(f for f in data['facts'] if f['id'].startswith('player:') and f['value']['club_id']==t['club_id'])
        t['player']['evidence_ids']=[p['id']]
    projected=publication_result({'status':'complete','reading':r},data)
    assert 'completed 2 of 3 passes' in projected['reading']['overview']['text']
    for t in projected['reading']['teams']:
        assert len(t['player']['evidence_ids'])==1
        assert 'return-pass' not in t['player']['text']
    assert publication_result({'status':'insufficient_evidence','reading':None},data)['reading'] is None
