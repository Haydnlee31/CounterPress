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


def reading(role,scoped):
    metric=next(m for m in scoped['metrics'] if m['status']!='unavailable' and m['value'] is not None)
    return {'role':role,'headline':'A developing pattern','explanation':'The recorded actions suggest a change in attacking involvement.',
        'alternative':'The short spell may not persist.','watch_next':'Watch whether the same pattern continues.',
        'evidence_ids':[scoped['evidence'][-1]['id']],'metric_ids':[metric['id']],'confidence':'low'}


@pytest.mark.parametrize('mid',MATCH_IDS)
def test_real_packets_validate_all_roles_and_exact_temporal_provenance(career,mid):
    p=packet(career,mid)
    assert parse_packet(json.dumps(p,ensure_ascii=False,separators=(',',':')))==p
    for role in ('chance','defence','control','players'):
        scoped=role_packet(p,role)
        assert scoped['metrics'] and scoped['evidence']
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


def compound_packet(career):
    p=packet(career)
    club=p['clubs'][0]['club_id'];ids=[f'current:{club}:verified_turnovers',f'current:{club}:shots']
    p['signals']=[{'id':'linked-transition','role':'defence','title':'A linked transition','detail':'Recorded loss and shooting evidence.',
        'metric_ids':ids,'evidence_ids':[p['evidence'][-1]['id']],'salience':.8}]
    return p,ids


def test_cross_discipline_support_survives_native_and_provider_validation(career):
    p,ids=compound_packet(career)
    scoped=role_packet(p,'defence')
    assert scoped['signals'] and set(ids)<={m['id']for m in scoped['metrics']}
    r=reading('defence',scoped);r['metric_ids']=ids
    validate_reading(Reading.model_validate(r),scoped,'defence')
    result={k:p[k]for k in ('snapshot_id','match_id','cutoff','through_sequence')}
    result.update(status='complete',readings=[r],summary={k:r[k]for k in ('headline','explanation','evidence_ids','metric_ids')},usage={'model_calls':2})
    assert validate_result(result,p)['readings']==[r]
    # Merely possessing a cross-role metric is not enough without an explicit signal.
    p['signals']=[]
    with pytest.raises(ValueError):validate_result(result,p)


def test_adversarial_semantic_reading_is_dropped_when_independent_verifier_rejects(career):
    p=packet(career)
    calls=[]
    async def complete(role,payload,limit):
        supplied=json.loads(payload);calls.append(role)
        if role=='synthesis':
            # IDs alone do not entail prose. The independent verifier sees the
            # specific metric/event proof, rejects invented tactical positioning.
            assert supplied['packet']['metrics'] and supplied['packet']['evidence']
            assert any(r['role']=='control'for r in supplied['readings'])
            return Completion(json.dumps({'accepted_roles':['chance'],'selected_role':'chance'}))
        r=reading(role,supplied)
        if role=='control':r['explanation']='Away are finding gaps behind Home’s defensive line.'
        return Completion(json.dumps({'reading':r}))
    result=asyncio.run(AnalystRuntime(complete).run(json.dumps(p,separators=(',',':'))))
    checked=validate_result(result,p)
    assert [r['role']for r in checked['readings']]==['chance']
    assert 'defensive line'not in json.dumps(checked)
    assert len(calls)==5


@pytest.mark.parametrize('bad_verifier',[None,{'accepted_roles':['chance','chance'],'selected_role':'chance'}, {'accepted_roles':[],'selected_role':'chance'}])
def test_verifier_failure_never_publishes_unreviewed_prose(career,bad_verifier):
    p=packet(career)
    async def complete(role,payload,limit):
        if role=='synthesis':
            if bad_verifier is None:raise TimeoutError('timeout')
            return Completion(json.dumps(bad_verifier))
        return Completion(json.dumps({'reading':reading(role,json.loads(payload))}))
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
        return {'snapshot_id':f'revision-{seq}','match_id':mid,'cutoff':request.cutoff.model_dump(),'through_sequence':seq,'evidence':[{'id':'event'}]}
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
