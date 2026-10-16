"""Independent actor attribution, eligibility, revision and persisted-source checks."""

import json
from pathlib import Path
import subprocess
import sys

from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError
import pytest

from counterpress.api.main import create_app
from counterpress.api.snapshots import BASELINE, CURRENT, END, SnapshotService
from counterpress.domain.contributions import ContributionPolicy, PlayerContributionEvidence, analyze_contributions
from counterpress.domain.models import Event, MatchTime, ObservationWindow
from counterpress.fixture import PossessionFixture, load_fixture
from counterpress.history import SQLiteHistoryStore
from counterpress.replay import ReplaySession

ROOT = Path(__file__).resolve().parents[1]
ORACLE = json.loads((ROOT / 'tests/expected_contributions.json').read_text())


def feed(name='increase'):
    return load_fixture(ROOT / f'fixtures/contributions/{name}.json')


def at(ms):
    return MatchTime(period=2, elapsed_ms=ms)


def analyze(fixture=None, player='eb04', team='eastbridge', cutoff=780000, **kwargs):
    session = fixture if isinstance(fixture, ReplaySession) else ReplaySession(fixture or feed(), end=at(max(cutoff, 780000)))
    return analyze_contributions(session, team, player, BASELINE, CURRENT, at(cutoff), **kwargs)


def updates():
    return TypeAdapter(tuple[Event, ...]).validate_json((ROOT / 'fixtures/contributions/actor_corrections.json').read_text())


def rewrite(transform):
    raw = feed().model_dump(mode='json')
    for event in raw['events']:
        transform(event)
    return PossessionFixture.model_validate_json(json.dumps(raw))


def audit_continuity(events):
    ball, holder = (70.0, 34.0), 'np04'
    for e in events:
        own = e.actor.team_id == 'eastbridge'
        position = (e.position.x, e.position.y) if own else (105-e.position.x, 68-e.position.y)
        assert position == ball, e.event_id
        action = e.action
        if action.kind == 'recovery':
            holder = e.actor.player_id
        elif action.kind == 'duel':
            assert holder in (e.actor.player_id, action.opponent.player_id)
        else:
            assert e.actor.player_id == holder, e.event_id
        if action.kind in ('pass', 'carry'):
            end = action.end_position
            ball = (end.x, end.y) if own else (105-end.x, 68-end.y)
            if action.kind == 'pass' and action.outcome == 'completed':
                holder = action.recipient.player_id


@pytest.mark.parametrize('name', ['increase', 'control'])
def test_independent_controls_partition_team_totals_and_preserve_continuity(name):
    fixture = feed(name)
    assert len(fixture.events) == 48
    audit_continuity(fixture.events)
    totals = [0, 0]
    for player, expected in ORACLE[name].items():
        evidence = analyze(fixture, player=player)
        for index, key in enumerate(('baseline', 'current')):
            window = getattr(evidence, key)
            assert [r.event_id for r in window.team_events] == ORACLE['team_'+key]
            assert [r.event_id for r in window.player_events] == expected[key]
            assert window.team_count == 4
            assert window.player_count == len(expected[key])
            assert window.share == len(expected[key])/4
            totals[index] += window.player_count
        assert evidence.decision.status == expected['status']
        assert evidence.decision.count_change == expected['count_change']
        assert evidence.decision.share_change == expected['share_change']
        assert PlayerContributionEvidence.model_validate_json(evidence.model_dump_json()) == evidence
    assert totals == [4, 4]  # Every recovery belongs to exactly one recovering actor.


def test_duel_winner_and_pass_recipient_are_not_credited_with_recovery():
    evidence = analyze(player='eb09')
    assert sum(e.action.kind == 'duel' and e.actor.player_id == 'eb09' for e in evidence.records) == 8
    assert evidence.baseline.player_count == evidence.current.player_count == 0
    eb04 = analyze()
    assert [r.event_id for r in eb04.baseline.player_events] == ['b1-recovery']
    assert any(e.action.kind == 'pass' and e.action.recipient and e.action.recipient.player_id == 'eb04' for e in eb04.records)


@pytest.mark.parametrize('policy,status', [
    (ContributionPolicy(minimum_share_increase=0.5), 'eligible'),
    (ContributionPolicy(minimum_share_increase=0.500001), 'below_threshold'),
    (ContributionPolicy(minimum_current_player_recoveries=4), 'below_threshold'),
    (ContributionPolicy(minimum_count_increase=3), 'below_threshold'),
    (ContributionPolicy(minimum_team_recoveries=4), 'eligible'),
    (ContributionPolicy(minimum_team_recoveries=5), 'insufficient_sample'),
])
def test_exact_policy_thresholds(policy, status):
    assert analyze(policy=policy).decision.status == status


def test_shrinking_denominator_alone_does_not_create_improvement():
    # eb08 keeps three recoveries, while the other player's current recovery is a restart.
    raw = feed('control').model_dump(mode='json')
    next(e for e in raw['events'] if e['event_id'] == 'c1-recovery')['action']['origin'] = 'restart'
    evidence = analyze(PossessionFixture.model_validate_json(json.dumps(raw)), player='eb08')
    assert (evidence.baseline.share, evidence.current.share) == (0.75, 1.0)
    assert evidence.decision.count_change == 0
    assert evidence.decision.status == 'below_threshold'


def test_zero_denominator_is_undefined_not_zero_share():
    evidence = analyze(player='np04', team='northport')
    assert evidence.baseline.team_count == evidence.current.team_count == 0
    assert evidence.baseline.share is evidence.current.share is None
    assert evidence.decision.share_change is None
    assert evidence.decision.status == 'insufficient_sample'


@pytest.mark.parametrize('x,expected', [(70.0, 4), (69.999, 0)])
def test_exact_high_recovery_coordinate_threshold(x, expected):
    def move(e):
        if e['actor']['team_id'] == 'eastbridge' and e['action']['kind'] == 'recovery':
            e['position']['x'] = x
    evidence = analyze(rewrite(move))
    assert evidence.baseline.team_count == evidence.current.team_count == expected


def test_start_excluded_split_in_baseline_and_end_in_current():
    def move(e):
        if e['event_id'].startswith('b1-'):
            e['occurred_at']['elapsed_ms'] -= 20000
            # Place the opening feed/duel at coverage start, ordered before recovery.
            e['occurred_at']['elapsed_ms'] = max(180000, e['occurred_at']['elapsed_ms'])
            e['available_at'] = dict(e['occurred_at'])
        if e['event_id'].startswith('c4-'):
            e['occurred_at']['elapsed_ms'] += 20000
            e['available_at'] = dict(e['occurred_at'])
    evidence = analyze(rewrite(move))
    assert [r.event_id for r in evidence.baseline.team_events] == ['b2-recovery','b3-recovery','b4-recovery']
    assert [r.event_id for r in evidence.current.team_events] == ORACLE['team_current']
    assert evidence.baseline.player_count == 0


@pytest.mark.parametrize('team,player', [('eastbridge','missing'),('northport','eb04'),('missing','eb04')])
def test_invalid_player_team_rejected(team, player):
    with pytest.raises(ValueError, match='belong'):
        analyze(team=team, player=player)


@pytest.mark.parametrize('case', ['incomplete','unequal','uncovered','nonadjacent','cross_period'])
def test_invalid_observation_windows(case):
    session = ReplaySession(feed(), end=END)
    baseline, current, cutoff = BASELINE, CURRENT, END
    if case == 'incomplete': cutoff = at(779999)
    if case == 'unequal': baseline = ObservationWindow(start=at(190000), end=BASELINE.end)
    if case == 'uncovered': baseline = ObservationWindow(start=at(170000), end=BASELINE.end)
    if case == 'nonadjacent': current = ObservationWindow(start=at(480001), end=END)
    if case == 'cross_period': baseline = ObservationWindow(start=MatchTime(period=1,elapsed_ms=180000), end=BASELINE.end)
    with pytest.raises(ValueError):
        analyze_contributions(session,'eastbridge','eb04',baseline,current,cutoff)


@pytest.mark.parametrize('field,value', [
    ('minimum_team_recoveries',0), ('minimum_count_increase',0),
    ('minimum_share_increase',float('nan')), ('minimum_share_increase',1.01),
])
def test_invalid_policy(field, value):
    with pytest.raises(ValidationError): ContributionPolicy(**{field:value})


@pytest.mark.parametrize('fault', ['wrong_actor','missing_record','duplicate','future','match','share','decision'])
def test_evidence_rejects_forged_attribution_and_inconsistent_sources(fault):
    data = analyze().model_dump(mode='json')
    source = next(e for e in data['records'] if e['event_id']=='c1-recovery')
    if fault == 'wrong_actor': source['actor']['player_id']='eb08'
    if fault == 'missing_record': data['records'].remove(source)
    if fault == 'duplicate': data['records'].append(source)
    if fault == 'future': source['available_at']['elapsed_ms']=785000
    if fault == 'match': source['match_id']='other-match'
    if fault == 'share': data['current']['share']=0.99
    if fault == 'decision': data['decision']['status']='below_threshold'
    with pytest.raises(ValidationError): PlayerContributionEvidence.model_validate_json(json.dumps(data))


def test_actor_corrections_recompute_both_players_and_keep_earlier_cutoffs():
    session = ReplaySession(feed(),end=at(795000))
    session.deliver(updates())
    session.deliver(updates())  # Exact retransmission must not duplicate attribution.
    for cutoff, count, status, revision in [(780000,3,'eligible',1),(785000,2,'below_threshold',2),
                                           (790000,1,'below_threshold',2),(795000,3,'eligible',3)]:
        evidence = analyze(session,cutoff=cutoff)
        other = analyze(session,player='eb08',cutoff=cutoff)
        assert evidence.current.player_count == count
        assert evidence.current.team_count == 4
        assert evidence.current.player_count+other.current.player_count == 4
        assert evidence.decision.status == status
        assert next(e for e in evidence.records if e.event_id=='c3-recovery').revision == revision
        audit_continuity(evidence.records)
    assert analyze(session).current.player_count == 3


def test_late_actor_revision_is_unavailable_until_delivery():
    session = ReplaySession(feed(),end=at(785000))
    session.deliver(updates()[:3])
    before = analyze(session,cutoff=784999)
    after = analyze(session,cutoff=785000)
    assert before.current.player_count == 3 and after.current.player_count == 2
    assert all(e.revision==1 for e in before.records)


def seeded_root(tmp_path):
    root = tmp_path/'fixtures'
    root.mkdir()
    (root/'recovery_increase.json').write_text(feed().model_dump_json(indent=2))
    return root


def test_api_uses_durable_source_revisions_after_restart_without_fixture(tmp_path):
    root=seeded_root(tmp_path); db=tmp_path/'history.sqlite3'
    service=SnapshotService(root,SQLiteHistoryStore(db))
    service.ingest('increase',updates())
    original=service.contribution('increase','eastbridge','eb04',780000)
    (root/'recovery_increase.json').unlink()
    with TestClient(create_app(root,db)) as client:
        url='/api/scenarios/increase/players/eb04/contribution'
        response=client.get(url,params={'at_ms':780000})
        assert response.status_code==200
        assert response.headers['cache-control']=='no-store'
        assert PlayerContributionEvidence.model_validate_json(response.text)==original
        for cutoff,count in [(785000,2),(790000,1),(795000,3)]:
            response=client.get(url,params={'at_ms':cutoff})
            assert response.status_code==200
            assert response.json()['current']['player_count']==count
        assert client.get(url,params={'at_ms':779999}).status_code==422
        assert client.get(url,params={'at_ms':795001}).status_code==422
        assert client.get(url,params={'at_ms':780000,'team_id':'northport'}).status_code==422
        assert client.get(url.replace('eb04','unknown'),params={'at_ms':780000}).status_code==422
        assert client.get(url.replace('/increase/','/unknown/'),params={'at_ms':780000}).status_code==404


def test_cli_json_and_invalid_selection():
    cmd=[sys.executable,'-m','counterpress.contributions',str(ROOT/'fixtures/contributions/increase.json'),'--player','eb04','--json']
    result=subprocess.run(cmd,capture_output=True,text=True,check=True)
    evidence=PlayerContributionEvidence.model_validate_json(result.stdout)
    assert evidence.decision.status=='eligible'
    invalid=subprocess.run(cmd[:-2]+['unknown','--json'],capture_output=True,text=True)
    assert invalid.returncode==2
    assert 'player must belong' in invalid.stderr
