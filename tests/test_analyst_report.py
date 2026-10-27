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
            return {'status':'complete','reading':{'headline':'Verified'}}
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
    return {'headline':'A match of chances','overview':c,'teams':[{'club_id':t['club_id'],**{k:c for k in ('strength','weakness','adjustment','player')}} for t in data['teams']]}


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
