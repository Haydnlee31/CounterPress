"""Independent canonical packet → native runtime → public-provider checks.

Provider calls are deterministic fakes; these tests make no paid/cloud calls.
"""
import asyncio
import copy
import json
from pathlib import Path
import sys

import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from integrations.analyst_foundry.contracts import parse_packet,role_packet,Reading,validate_reading
from integrations.analyst_foundry.runtime import AnalystRuntime,Completion
from counterpress.analyst.contracts import AnalystRequest,MATCH_IDS
from counterpress.analyst.service import build_snapshot,build_dispatch_packet
from counterpress.analyst.provider import validate_result
from counterpress.personalization.store import DataStore
from counterpress.personalization.service import CareerService


@pytest.fixture(scope='module')
def career():
    return CareerService(DataStore(Path('fixtures/personalization')))


def packet(career,mid=MATCH_IDS[2],ms=600000,**kwargs):
    return build_dispatch_packet(build_snapshot(career,mid,AnalystRequest(cutoff={'period':1,'elapsed_ms':ms},**kwargs)))


@pytest.mark.parametrize('mid',MATCH_IDS)
def test_real_packets_validate_all_roles_and_exact_temporal_provenance(career,mid):
    p=packet(career,mid)
    assert parse_packet(json.dumps(p,ensure_ascii=False,separators=(',',':')))==p
    for role in ('chance','defence','control','players'):
        scoped=role_packet(p,role)
        for candidate in scoped.get('candidates',[]):
            assert candidate['role']==role
            assert set(candidate['reading']['metric_ids'])<={m['id']for m in scoped['metrics']}
            assert set(candidate['reading']['evidence_ids'])<={e['id']for e in scoped['evidence']}
        assert scoped['windows']==p['windows']
    for event in p['evidence']:
        assert (event['available_period'],event['available_ms'])<=(p['cutoff']['period'],p['cutoff']['elapsed_ms'])
        assert event['delivery_sequence']<=p['through_sequence']


def test_equivalent_received_ceilings_share_same_paid_snapshot(career):
    mid=MATCH_IDS[2];base=AnalystRequest(cutoff={'period':1,'elapsed_ms':120000})
    s=build_snapshot(career,mid,base)
    latest=max(e.delivery_sequence for e in career.store.events(mid))
    exact=build_snapshot(career,mid,base.model_copy(update={'through_sequence':s['through_sequence']}))
    generous=build_snapshot(career,mid,base.model_copy(update={'through_sequence':latest}))
    assert s['snapshot_id']==exact['snapshot_id']==generous['snapshot_id']
    assert s['evidence']==exact['evidence']==generous['evidence']
    earlier=build_snapshot(career,mid,base.model_copy(update={'through_sequence':max(0,s['through_sequence']-1)}))
    assert earlier['snapshot_id']!=s['snapshot_id']


def test_cross_discipline_candidate_support_survives_native_and_provider_validation(career):
    p=packet(career,ms=2096000)
    candidate=next(c for c in p['candidates']if c['role']=='players')
    scoped=role_packet(p,'players');r=candidate['reading']
    assert any(m['role']=='defence'and m['id']in r['metric_ids']for m in scoped['metrics'])
    validate_reading(Reading.model_validate(r),scoped,'players')
    result={k:p[k]for k in ('snapshot_id','match_id','cutoff','through_sequence')}
    result.update(status='complete',readings=[r],summary={k:r[k]for k in ('headline','explanation','evidence_ids','metric_ids')},usage={'model_calls':2})
    assert validate_result(result,p)['readings']==[r]
    # Exact candidate support remains legitimate without redundant signal metadata.
    p['signals']=[]
    assert validate_result(result,p)['readings']==[r]
    p['candidates']=[]
    with pytest.raises(ValueError):validate_result(result,p)


@pytest.mark.parametrize('attack',['invented_id','wrong_role_id','extra_prose'])
def test_adversarial_candidate_selection_cannot_publish_fabricated_readings(career,attack):
    p=packet(career,ms=2096000);calls=[]
    async def complete(role,payload,limit):
        supplied=json.loads(payload);calls.append(role)
        assert role!='synthesis'  # all proposed selectors below are rejected
        choice=supplied['candidates'][0]['id']
        if attack=='invented_id':return Completion(json.dumps({'candidate_id':'invented'}))
        if attack=='wrong_role_id':
            other=next(c['id']for c in p['candidates']if c['role']!=role)
            return Completion(json.dumps({'candidate_id':other}))
        return Completion(json.dumps({'candidate_id':choice,'explanation':'Away find gaps behind the defensive line.'}))
    result=asyncio.run(AnalystRuntime(complete).run(json.dumps(p,separators=(',',':'))))
    checked=validate_result(result,p)
    assert checked['readings']==[]and checked['summary']is None
    assert len(calls)==2


def test_native_selection_returns_exact_localized_candidate(career):
    p=packet(career,ms=2096000,language='zh-Hans')
    async def complete(role,payload,limit):
        supplied=json.loads(payload)
        if role=='synthesis':return Completion(json.dumps({'accepted_roles':['players'],'selected_role':'players'}))
        return Completion(json.dumps({'candidate_id':supplied['candidates'][0]['id']}))
    result=asyncio.run(AnalystRuntime(complete).run(json.dumps(p,ensure_ascii=False,separators=(',',':'))))
    checked=validate_result(result,p)
    expected=next(c['reading']for c in p['candidates']if c['role']=='players')
    assert checked['readings']==[expected]and '夺回球权'in expected['explanation']
    mutated=copy.deepcopy(result);mutated['readings'][0]['explanation']='Unsupported off-ball movement.'
    with pytest.raises(ValueError):validate_result(mutated,p)


@pytest.mark.parametrize('bad_verifier',[None,{'accepted_roles':['players','players'],'selected_role':'players'}, {'accepted_roles':[],'selected_role':'players'}])
def test_verifier_failure_never_publishes_unreviewed_prose(career,bad_verifier):
    p=packet(career,ms=2096000)
    async def complete(role,payload,limit):
        if role=='synthesis':
            if bad_verifier is None:raise TimeoutError('timeout')
            return Completion(json.dumps(bad_verifier))
        return Completion(json.dumps({'candidate_id':json.loads(payload)['candidates'][0]['id']}))
    result=asyncio.run(AnalystRuntime(complete).run(json.dumps(p,separators=(',',':'))))
    assert result['readings']==[] and result['summary'] is None
    assert validate_result(result,p)['status']=='insufficient_evidence'


@pytest.mark.parametrize('mutation',['late_availability','future_sequence'])
def test_native_receipt_rejects_event_not_available_in_snapshot(career,mutation):
    p=copy.deepcopy(packet(career))
    if mutation=='late_availability':p['evidence'][0]['available_ms']=p['cutoff']['elapsed_ms']+1
    else:p['evidence'][0]['delivery_sequence']=p['through_sequence']+1
    with pytest.raises(ValueError):parse_packet(json.dumps(p,separators=(',',':')))


def test_language_preference_survives_transport_and_specialists(career):
    p=packet(career,language='zh-Hans',depth='casual')
    for role in ('chance','defence','control','players'):
        scoped=role_packet(parse_packet(json.dumps(p,ensure_ascii=False,separators=(',',':'))),role)
        assert scoped['language']=='zh-Hans' and scoped['depth']=='casual'


def test_correction_during_paid_work_discards_old_prose_and_stale_ceiling_is_free(tmp_path,monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    import threading
    import time
    import sqlite3
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from counterpress.analyst.api import install_analyst
    from counterpress.analyst.admission import Allowance,SQLiteStore
    version={'n':1};release=threading.Event();started=threading.Event()
    def fake_snapshot(career,mid,request):
        seq=min(version['n'],request.through_sequence) if request.through_sequence is not None else version['n']
        return {'snapshot_id':f'revision-{seq}','match_id':mid,'cutoff':request.cutoff.model_dump(),'through_sequence':seq,'evidence':[{'id':'event'}],'candidates':[{'id':'test-supported'}]}
    monkeypatch.setattr('counterpress.analyst.api.build_snapshot',fake_snapshot)
    class FakeProvider:
        manifest_id='pinned';calls=0
        async def analyze(self,*args):
            self.calls+=1;started.set()
            while not release.is_set():await asyncio.sleep(.001)
            return {'status':'complete','readings':[{'explanation':'obsolete'}],'summary':None}
    provider=FakeProvider();path=tmp_path/'ledger.sqlite3';app=FastAPI()
    install_analyst(app,lambda:SimpleNamespace(store=SimpleNamespace(snapshot=nullcontext)),provider=provider,allowance=Allowance(SQLiteStore(path)))
    body={'cutoff':{'period':1,'elapsed_ms':120000}}
    with TestClient(app)as client:
        assert client.post(f'/api/analyst/matches/{MATCH_IDS[0]}/analysis',json=body).json()['status']=='pending'
        assert started.wait(1)
        version['n']=2;release.set()
        for _ in range(100):
            with sqlite3.connect(path)as db:state=json.loads(db.execute('SELECT payload FROM analyst_control WHERE id=1').fetchone()[0])
            job=next(iter(state['jobs'].values()))
            if job['status']!='pending':break
            time.sleep(.005)
        assert job['status']=='unavailable' and job['result'] is None
        response=client.post(f'/api/analyst/matches/{MATCH_IDS[0]}/analysis',json={**body,'through_sequence':1})
        assert response.status_code==409
        assert provider.calls==1
