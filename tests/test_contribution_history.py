import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError
import pytest

from counterpress.api.main import create_app
from counterpress.api.snapshots import BASELINE, CURRENT, END, SnapshotService, project, replay_session
from counterpress.audience import ViewingPreferences
from counterpress.contribution_publications import ContributionChange, in_cooldown, project_contributions
from counterpress.domain.models import Event, MatchTime, ObservationWindow
from counterpress.history import History, SQLiteHistoryStore
from test_contributions import audit_continuity

ROOT = Path(__file__).resolve().parents[1]


def updates():
    return TypeAdapter(tuple[Event, ...]).validate_json((ROOT/'fixtures/contributions/publication_corrections.json').read_text())


def test_durable_update_withdraw_restore_and_restart_without_fixtures(tmp_path):
    db = tmp_path/'history.sqlite3'
    service = SnapshotService(ROOT/'fixtures',SQLiteHistoryStore(db))
    original = service.snapshot('contribution-increase',780000)
    assert original.selected_kind == 'contribution'
    first = original.contribution.publication
    assert (first.evidence.baseline.player_count, first.evidence.current.player_count) == (1,3)
    history = service.ingest('contribution-increase',updates())
    assert [(c.operation,c.revision,c.available_at.elapsed_ms) for c in history.contribution_changes] == [
        ('create',1,780000),('update',2,782000),('withdraw',3,785000),('create',4,795000)]
    assert len({c.insight_id for c in history.contribution_changes}) == 1
    assert len({c.evidence_id for c in history.contribution_changes}) == 1
    assert service.ingest('contribution-increase',updates()) == history
    restarted = SnapshotService(tmp_path/'missing',SQLiteHistoryStore(db))
    assert restarted.snapshot('contribution-increase',780000).contribution == original.contribution
    for cutoff,revision in [(782000,2),(785000,3),(790000,3),(795000,4)]:
        snapshot = restarted.snapshot('contribution-increase',cutoff)
        assert snapshot.contribution_lifecycle[0].revision == revision
        if revision == 3:
            assert snapshot.contribution.publication is None and snapshot.selected_kind is None
        else:
            assert snapshot.contribution.publication.revision == revision
            assert snapshot.contribution.publication.invalidates == (revision-1,)
        audit_continuity(replay_session(history).snapshot(MatchTime(period=2,elapsed_ms=cutoff)).events)
    assert history.contribution_version == len(history.records)
    assert project(history,MatchTime(period=2,elapsed_ms=795000)).contribution_changes == history.contribution_changes


def test_exact_evidence_endpoint_scopes_identity_revision_and_cutoff():
    app=create_app(); service=app.state.snapshots
    first=service.snapshot('contribution-increase',780000).contribution.publication
    service.ingest('contribution-increase',updates())
    base=f'/api/scenarios/contribution-increase/contributions/{first.insight_id}/evidence/'
    with TestClient(app) as client:
        assert client.get(base+'2?at_ms=780000').status_code == 404
        response=client.get(base+'2?at_ms=782000')
        assert response.status_code == 200 and response.headers['cache-control']=='no-store'
        evidence=response.json()['evidence']
        assert evidence['baseline']['player_events']==[{'event_id':'b1-recovery','revision':2}]
        assert client.get(base+'3?at_ms=785000').json()['operation']=='withdraw'
        assert client.get(base+'1?at_ms=780000').json()['evidence']['baseline']['player_events'][0]['revision']==1
        assert client.get(base+'1?at_ms=999999').status_code==404
        assert client.get(base.replace(first.insight_id,'wrong')+'1?at_ms=780000').status_code==404
        assert client.get(base.replace('contribution-increase','contribution-control')+'1?at_ms=780000').status_code==404


@pytest.mark.parametrize('language',['en','zh-Hans'])
@pytest.mark.parametrize('depth',['analyst','casual'])
def test_bilingual_player_views_keep_exact_team_denominators(language,depth):
    service=SnapshotService(ROOT/'fixtures')
    prefs=ViewingPreferences(language=language,depth=depth,player_id='eb04',metric_focus='player_high_recovery_share')
    snapshot=service.snapshot('contribution-increase',780000,preferences=prefs)
    view=snapshot.contribution
    assert snapshot.selected_kind=='contribution'
    assert view.variant.language==language and view.variant.depth==depth
    assert '1/4' in view.variant.explanation and '3/4' in view.variant.explanation
    assert view.publication.evidence.current.team_count==4
    assert len(view.highlighted_events)==4
    by_ref={(e.event_id,e.revision):e for e in view.publication.evidence.records}
    assert all(by_ref[(r.event_id,r.revision)].actor.player_id=='eb04' for r in view.highlighted_events)
    for player in ['eb08','eb09']:
        other=service.snapshot('contribution-increase',780000,preferences=prefs.model_copy(update={'player_id':player}))
        assert other.contribution.state=='no_contribution' and other.selected_kind is None
        assert other.contribution_lifecycle==snapshot.contribution_lifecycle
    hidden=service.snapshot('contribution-increase',780000,preferences=prefs.model_copy(update={'card_budget':0}))
    assert hidden.selected_kind is None and hidden.contribution.publication is None


def test_early_and_negative_control_never_publish():
    service=SnapshotService(ROOT/'fixtures')
    early=service.snapshot('contribution-increase',779999)
    assert early.contribution.state=='collecting' and early.contribution_lifecycle==()
    assert early.selected_kind is None
    control=service.snapshot('contribution-control',780000)
    assert control.contribution.state=='no_eligible' and control.contribution_lifecycle==()


def test_legacy_schema_backfill_keeps_existing_streams_and_is_idempotent(tmp_path):
    db=tmp_path/'legacy.sqlite3'
    service=SnapshotService(ROOT/'fixtures',SQLiteHistoryStore(db))
    before=service.ingest('contribution-increase',updates())
    pressure=service.history('pressure-increase')
    with sqlite3.connect(db) as conn:
        conn.execute('DROP TABLE contribution_changes')
        conn.execute('DROP TABLE contribution_checkpoints')
    restarted=SnapshotService(tmp_path/'missing',SQLiteHistoryStore(db))
    after=restarted.history('contribution-increase')
    assert after==before
    assert restarted.history('contribution-increase')==after
    assert restarted.history('pressure-increase')==pressure


def test_invalid_ingest_and_history_rewrite_are_atomic(tmp_path):
    service=SnapshotService(ROOT/'fixtures',SQLiteHistoryStore(tmp_path/'history.sqlite3'))
    before=service.history('contribution-increase')
    bad=updates()[1].model_copy(update={'actor':updates()[1].actor.model_copy(update={'player_id':'unknown'})})
    with pytest.raises(ValueError): service.ingest('contribution-increase',(updates()[0],bad))
    assert service.history('contribution-increase')==before
    with pytest.raises(ValueError,match='rewritten'):
        service.store.transact('contribution-increase',lambda h:h.model_copy(update={'contribution_changes':()}))


def test_publication_rejects_mismatched_status_cutoff_and_invalidations():
    first=SnapshotService(ROOT/'fixtures').history('contribution-increase').contribution_changes[0]
    for update in [{'operation':'withdraw'},{'available_at':{'period':2,'elapsed_ms':780001}},{'invalidates':[1]}]:
        data=first.model_dump(mode='json');data.update(update)
        with pytest.raises(ValidationError): ContributionChange.model_validate_json(__import__('json').dumps(data))


@pytest.mark.parametrize('field,value,expected',[
    ('subject_player_id','eb08',False),('subject_team_id','northport',False),('match_id','other-match',False),
    ('cutoff',MatchTime(period=2,elapsed_ms=779999),False),
    ('cutoff',MatchTime(period=2,elapsed_ms=839999),True),
    ('cutoff',MatchTime(period=2,elapsed_ms=840000),False),
])
def test_cooldown_is_scoped_to_player_team_match_and_exact_expiry(field,value,expected):
    first=SnapshotService(ROOT/'fixtures').history('contribution-increase').contribution_changes[0]
    e=first.evidence
    shifted=e.model_copy(update={'baseline':e.baseline.model_copy(update={'window':ObservationWindow(start=MatchTime(period=2,elapsed_ms=181000),end=MatchTime(period=2,elapsed_ms=481000))}),
                                'current':e.current.model_copy(update={'window':ObservationWindow(start=MatchTime(period=2,elapsed_ms=481000),end=MatchTime(period=2,elapsed_ms=781000))})})
    assert in_cooldown((first,),shifted.model_copy(update={field:value})) is expected
    assert not in_cooldown((first,),e)  # Same comparison revisions are exempt.
    assert not in_cooldown((first.model_copy(update={'operation':'withdraw'}),),shifted)


def test_cooldown_blocks_new_comparison_but_not_existing_comparison_corrections():
    service=SnapshotService(ROOT/'fixtures')
    history=service.history('contribution-increase')
    first=history.contribution_changes[0]
    shifted_baseline=ObservationWindow(start=MatchTime(period=2,elapsed_ms=181000),end=MatchTime(period=2,elapsed_ms=481000))
    shifted_current=ObservationWindow(start=shifted_baseline.end,end=MatchTime(period=2,elapsed_ms=781000))
    session=replay_session(history)
    # Extend the clock for a distinct, overlapping observation comparison.
    from counterpress.replay import ReplaySession
    session=ReplaySession(history.fixture,end=MatchTime(period=2,elapsed_ms=840000))
    assert project_contributions(history,session,shifted_baseline,shifted_current,MatchTime(period=2,elapsed_ms=781000))==history.contribution_changes
    after=project_contributions(history,session,shifted_baseline,shifted_current,MatchTime(period=2,elapsed_ms=840000))
    assert len(after)==2 and after[-1].insight_id != first.insight_id
    # A newer publication for another window must not block a source revision on this one.
    recent=after[-1].model_copy(update={'available_at':MatchTime(period=2,elapsed_ms=781000)})
    history=history.model_copy(update={'contribution_changes':(first,recent)})
    session.deliver(updates()[:4])
    changes=project_contributions(history,session,BASELINE,CURRENT,MatchTime(period=2,elapsed_ms=782000))
    assert changes[-1].insight_id==first.insight_id and changes[-1].operation=='update'


def test_cross_metric_ranking_uses_one_budget_and_independent_viewers():
    service=SnapshotService(ROOT/'fixtures')
    player=service.history('contribution-increase').contribution_changes[0]
    # Ranking-only pool: real publications from independent fixtures, no altered facts.
    from counterpress.contribution_views import contribution_view
    from counterpress.pressure_views import pressure_view
    history=service.history('pressure-increase')
    prefs=ViewingPreferences()
    assert contribution_view(history,(player,),prefs,False).priority==pressure_view(history,history.pressure_changes,prefs,False).priority
    focused=prefs.model_copy(update={'metric_focus':'player_high_recovery_share'})
    assert contribution_view(history,(player,),focused,False).priority>pressure_view(history,history.pressure_changes,focused,False).priority
    # Real same-match pool: one baseline restart leaves 3 -> 4 team recoveries,
    # and the player's 1/3 -> 3/4 still meets the contribution rule.
    from counterpress.fixture import PossessionFixture
    import json
    raw=service.history('contribution-increase').fixture.model_dump(mode='json')
    next(e for e in raw['events'] if e['event_id']=='b4-recovery')['action']['origin']='restart'
    feed=PossessionFixture.model_validate_json(json.dumps(raw))
    mixed=SnapshotService(ROOT/'fixtures')
    mixed.store.transact('increase',lambda _:project(History(fixture=feed,records=feed.events),END))
    assert mixed.snapshot('increase',780000).selected_kind=='recovery'
    assert mixed.snapshot('increase',780000,preferences=focused).selected_kind=='contribution'
    assert mixed.snapshot('increase',780000,preferences=ViewingPreferences(card_budget=0)).selected_kind is None
    a=service.snapshot('contribution-increase',780000,'one',ViewingPreferences(player_id='eb04'))
    b=service.snapshot('contribution-increase',780000,'two',ViewingPreferences(player_id='eb09'))
    assert a.contribution_lifecycle==b.contribution_lifecycle
    assert a.selected_kind=='contribution' and b.selected_kind is None
