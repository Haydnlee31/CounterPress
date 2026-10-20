import gzip,json
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from counterpress.personalization.api import install_personalization
from counterpress.personalization.contracts import Action
from counterpress.personalization.metrics import digest,reduce_record
from counterpress.personalization.service import CareerService
from counterpress.personalization.store import DataStore

ROOT=Path(__file__).resolve().parents[1]/'fixtures'
MID='career-showcase-southbank-redhaven'
EXPECTED=json.loads((ROOT.parent/'tests/expected_fan_personalization.json').read_text())


@pytest.fixture(scope='module')
def store():
    result=DataStore(ROOT/'personalization');yield result;result.close()


def test_source_split_is_whole_match_and_models_have_holdout_evidence(store):
    model=store.model;train=set(model['training_match_ids']);held=set(model['holdout_match_ids'])
    assert len(train)==304 and len(held)==76 and train.isdisjoint(held)
    report=json.loads((ROOT/'personalization/calibration-report.json').read_text())
    assert all(row['model']<row['global_baseline'] for row in report['brier'].values())
    assert model['provenance']['license']=='CC BY 4.0'
    # Probability cells use pre-pass origin/type, never failed actual endpoints.
    assert all(k.split(':')[1] in ('ground','long','cross','header') for k in model['pass_probability']['cells'])


def test_registry_history_and_featured_visibility_are_distinct(store):
    assert len([c for c in store.clubs.values() if c.featured])==4
    featured=[p for p in store.players.values() if p.featured]
    assert len(featured)==44 and len({p.player_id for p in featured})==44
    assert all(sum(p.club_id==c for p in featured)==11 for c in ('eastbridge','northport','southbank','redhaven'))
    assert len(store.rows())==844 and len(store.rows(featured=True))==4
    assert store.players['eb09'].name=='Rory Ellis'
    assert len({p.name for p in store.players.values()})==len(store.players)
    assert all(p.debut_year==2020 and 18<=p.debut_year-p.birth_year<=21 for p in store.players.values())
    for season in {r['season'] for r in store.rows()}:
        table=CareerService(store).standings(season)['items']
        assert sum(r['goals_for'] for r in table)==sum(r['goals_against'] for r in table)
        assert sum(r['wins'] for r in table)==sum(r['losses'] for r in table)
        assert len({r['played'] for r in table})==1


def test_seed_rehydration_and_four_full_match_ledgers_reconcile(store):
    chosen={r['id'] for r in store.rows(featured=True)}|{f'career-{year}-r01-1' for year in range(2020,2027)}
    for mid in chosen:
        record=store.original(mid);row=store.row(mid)
        assert digest(record.events)==row['digest']
        assert all(e.available_period>e.period or e.available_ms>=e.elapsed_ms+(e.flight_ms or 0) for e in record.events)
        assert reduce_record(record)==json.loads(row['summary'])
        for club,stats in json.loads(row['summary'])['clubs'].items():
            summary=reduce_record(record);own_for=sum(p['own_goals'] for pid,p in summary['players'].items() if store.players[pid].club_id!=club)
            assert stats['goals']==sum(p['goals'] for pid,p in summary['players'].items() if store.players[pid].club_id==club)+own_for
    a=CareerService(store).profile('sb09');history=CareerService(store).history('sb09',limit=1000)['items']
    assert a['totals']['goals']==sum(h['stats']['goals'] for h in history)
    assert a['totals']['minutes']==pytest.approx(sum(h['stats']['minutes'] for h in history))
    assert a['heatmap']['total_actions']==sum(c['actions'] for c in a['heatmap']['cells'])
    assert a['coverage']['tracking_distance_m'] is None


def test_live_milestone_is_available_only_after_its_goal_and_excludes_future(store):
    service=CareerService(store);final=service.live(MID,2,2700000)
    assert final['milestones']
    m=next(m for m in final['milestones'] if m['event_id']==EXPECTED['goal_event_id']);at=m['available_at'];pid=m['player_id']
    before=service.live(MID,at['period'],at['elapsed_ms']-1,pid)
    after=service.live(MID,at['period'],at['elapsed_ms'],pid)
    assert before['milestones']==[]
    assert after['milestones'][0]['career_goals']==EXPECTED['career_goals_after']
    assert after['players'][pid]['career_at_cutoff']['goals']==EXPECTED['career_goals_after']
    assert before['players'][pid]['career_at_cutoff']['goals']==EXPECTED['career_goals_before']
    assert after['players'][pid]['career_before']==before['players'][pid]['career_before']
    # The current full-match total cannot leak into the kickoff baseline.
    assert service.live(MID,1,0)['score']=={'southbank':0,'redhaven':0}


def test_ingestion_idempotency_reordering_retraction_and_atomic_failure(tmp_path):
    store=DataStore(ROOT/'personalization',str(tmp_path/'career.sqlite3'));service=CareerService(store)
    try:
        milestone=service.live(MID,2,2700000)['milestones'][0]
        old=next(e for e in store.original(MID).events if e.event_id==milestone['event_id'])
        end=max(e.delivery_sequence for e in store.original(MID).events)
        v2=old.model_copy(update={'revision':2,'delivery_sequence':end+1,'available_period':2,'available_ms':2700100,'retracted':True})
        v3=v2.model_copy(update={'revision':3,'delivery_sequence':end+2,'available_ms':2700200,'retracted':False})
        assert store.ingest(MID,[v3,v2])['accepted']==2
        assert store.ingest(MID,[v2])=={'accepted':0,'duplicates':1,'received_through_sequence':end+2}
        assert service.live(MID,2,2700099)['milestones']
        assert old.event_id not in {m['event_id'] for m in service.live(MID,2,2700100)['milestones']}
        assert service.changes(MID,2,2700100,end)['changes'][0]['kind']=='withdrawn'
        assert service.live(MID,2,2700200)['milestones'][0]['event_revision']==3
        with pytest.raises(ValueError):store.ingest(MID,[v2.model_copy(update={'outcome':'blocked'})])
        v4=v3.model_copy(update={'revision':4,'delivery_sequence':end+3,'available_ms':2700300,'retracted':True})
        invalid=v4.model_copy(update={'event_id':'new-invalid','occurrence_order':9999,'delivery_sequence':end+4,'player_id':'unknown'})
        with pytest.raises(ValueError):store.ingest(MID,[v4,invalid])
        assert store.db.execute('SELECT COUNT(*) FROM career_revisions').fetchone()[0]==2
    finally:store.close()
    reopened=DataStore(ROOT/'personalization',str(tmp_path/'career.sqlite3'))
    assert CareerService(reopened).live(MID,2,2700200)['milestones'][0]['event_revision']==3
    reopened.close()


def test_readonly_api_contracts_and_bounds():
    app=FastAPI();install_personalization(app,ROOT)
    with TestClient(app) as client:
        assert client.get('/api/data/players').json()['total']==44
        assert client.get('/api/data/matches').json()['total']==4
        assert client.get('/api/data/matches?featured=false').json()['total']==844
        assert client.get('/api/data/players/sb09').json()['totals']['goals']>0
        assert client.get('/api/data/players/sb09/matches?limit=1').json()['total']>100
        response=client.get(f'/api/data/matches/{MID}/live?period=2&elapsed_ms=2700000')
        assert response.status_code==200 and response.json()['milestones']
        assert response.headers['cache-control']=='no-store'
        assert client.get(f'/api/data/matches/{MID}/events?limit=501').status_code==422
        assert client.get('/api/data/players/no-such-player').status_code==404
        assert client.get('/api/data/players/sb09?before=not-a-date').status_code==422
        assert client.get(f'/api/data/matches/{MID}/live?period=3').status_code==422
        assert client.get(f'/api/data/matches/{MID}/live?period=2&elapsed_ms=99999999').status_code==422
        assert client.post(f'/api/data/matches/{MID}/events',json={}).status_code==405
        assert client.get('/api/data/metrics').json()['version']=='career-metrics-v2'
        assert client.get('/api/data/standings/no-season').status_code==404
        replay=client.get(f'/api/data/matches/{MID}/replay')
        assert replay.status_code==200
        assert {t['team_id'] for t in replay.json()['teams']}=={'southbank','redhaven'}
        clips=client.get('/api/data/highlights').json()
        assert len(clips)==3 and len({c['highlight_id'] for c in clips})==3
        for clip in clips:
            assert len(clip['event_ids'])>=2
            replay=client.get('/api/data/highlights/'+clip['highlight_id']+'/replay')
            assert replay.status_code==200
            assert [e['event_id'] for e in replay.json()['events']]==clip['event_ids']
        assert client.get(f'/api/data/matches/{MID}/window?start_period=1&start_ms=1000&end_period=1&end_ms=0').status_code==422


def test_historical_baseline_does_not_leak_later_corrections(tmp_path):
    from datetime import datetime
    store=DataStore(ROOT/'personalization');service=CareerService(store)
    try:
        before=service.live(MID,1,0)
        prior=next(r for r in store.rows(club='southbank',before='2026-10-19T15:00:00Z') if json.loads(r['summary'])['score']['southbank']>0)
        record=store.original(prior['id']);goal=next(e for e in record.events if e.goal_for=='southbank')
        future=datetime.fromisoformat('2026-10-20T15:00:00+00:00');kickoff=datetime.fromisoformat(record.fixture.kickoff.replace('Z','+00:00'))
        available=int((future-kickoff).total_seconds()*1000)-record.fixture.period_lengths_ms[0]-900000
        correction=goal.model_copy(update={'revision':2,'delivery_sequence':max(e.delivery_sequence for e in record.events)+1,
            'available_period':2,'available_ms':available,'retracted':True})
        store.ingest(prior['id'],[correction])
        assert service.live(MID,1,0)==before
        previous=service.profile(goal.player_id,before='2026-10-19T15:00:00Z')
        later=service.profile(goal.player_id,before='2026-10-21T15:00:00Z')
        # Current showcase contributions are accounted separately; inspect the
        # corrected historical fixture directly to establish the boundary.
        at=service.historical_cutoff(prior,'2026-10-19T15:00:00Z')
        assert store.summary(prior['id'],at,completed=True)['players'][goal.player_id]['goals']==json.loads(prior['summary'])['players'][goal.player_id]['goals']
        assert store.summary(prior['id'])['players'][goal.player_id]['goals']==json.loads(prior['summary'])['players'][goal.player_id]['goals']-1
        assert previous['evidence']['baseline_id']!=later['evidence']['baseline_id']
    finally:store.close()


def test_source_assist_credits_are_preserved_without_guessing_recipients(store):
    expected={
        'wyscout-2058017':{'wyscout-263884397':('np09','wyscout-263884396')},
        'wyscout-2058007':{'wyscout-261446490':('np05','wyscout-261446487'),
                          'wyscout-261447221':('eb07','wyscout-261447217'),
                          'wyscout-261447496':('eb04','wyscout-261534737')},
    }
    for mid,credits in expected.items():
        record=store.original(mid)
        assert record.fixture.assist_basis=='provider_tags'
        actual={g['event_id']:(g['assist_id'],g['assist_event_id']) for g in reduce_record(record)['goals'] if g['assist_id']}
        assert actual==credits
    for player in store.players.values():
        if player.featured:
            assert CareerService(store).profile(player.player_id)['coverage']['assists_unavailable_matches']==0


def test_population_matches_benchmarks_beyond_showcase_selection(store):
    from counterpress.personalization.realism import population,checks
    report=store.manifest['population_validation']
    rows=[{'fixture':json.loads(r['fixture']),'summary':json.loads(r['summary'])} for r in store.rows(featured=False)]
    observed=population(rows,list(store.players.values()))
    assert observed==report['historical']
    assert all(v['passed'] for v in checks(observed,report['historical_reference']).values())
    assert report['unselected_3000']['matches']==3000
    assert all(v['passed'] for v in report['validation_checks'].values())
    first,last=report['seed_ranges']['validation']
    assert last-first+1==3000
    assert first>report['seed_ranges']['fitting'][1]
    assert first>report['seed_ranges']['showcase_selection'][1]
    assert report['seed_ranges']['showcase_selection']==[20000,20099]


def test_positional_validation_covers_all_roles_and_three_disjoint_batches(store):
    from counterpress.personalization.positions import position_checks
    report=json.loads((ROOT/'personalization/position-validation.json').read_text())
    assert store.manifest['validation_status']=='passed'
    first,last=store.manifest['population_validation']['seed_ranges']['validation']
    assert report['seed_ranges']==[[first+i,first+i+999] for i in (0,1000,2000)]
    assert report['seed_ranges'][-1][-1]==last
    assert report['historical']['matches']==840
    for sample in [report['historical'],report['pooled_validation'],*[b['observed'] for b in report['validation_batches']]]:
        gates=position_checks(sample,report['source_holdout'],report['source_training'])
        assert len(gates)==57 and all(g['passed'] for g in gates.values())
        assert set(sample['roles'])=={'GK','DF','MF','FW'}
    assert [b['observed']['matches'] for b in report['validation_batches']]==[1000,1000,1000]
