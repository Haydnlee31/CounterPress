"""Independent examples for the extended audit's source eligibility and maths."""
from collections import Counter
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'player_distribution_audit', Path(__file__).resolve().parents[1] / 'scripts/audit_player_distributions.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
DEFS = {d[0]: d for d in audit.DEFINITIONS}


def test_every_metric_has_an_explicit_review_classification():
    groups = [audit.COMPARABLE, audit.MODEL_KEYS, set(audit.CAVEATS)]
    assert set(DEFS) == set.union(*groups)
    assert sum(len(g) for g in groups) == len(DEFS)


def test_missing_outcomes_and_geometry_do_not_become_failed_rate_comparisons():
    source = Counter(passes=100, passes_unknown=6, located_passes=94)
    assert 'outcome' in audit.comparability(source, DEFS['passes_completed'])
    assert 'geometry' in audit.comparability(source, DEFS['backward_passes'])
    assert audit.comparability(source, DEFS['passes']) is None
    source.update(passes_unknown=-1, located_passes=1)
    assert audit.comparability(source, DEFS['passes_completed']) is None
    assert audit.comparability(source, DEFS['backward_passes']) is None


def test_small_penalty_samples_are_not_evidence_of_bad_conversion():
    assert audit.comparability(Counter(penalty_shots=29), DEFS['penalty_conversion'])
    assert audit.comparability(Counter(penalty_shots=30), DEFS['penalty_conversion']) is None


def test_weighted_rates_unknown_outcomes_and_own_goal_denominators():
    stats = Counter(minutes=180, goals=1, passes=100, passes_unknown=10, passes_completed=45,
                    saves=6, goals_conceded=3, own_goals_conceded=1)
    assert audit.value(stats, DEFS['goals']) == .5
    assert audit.value(stats, DEFS['pass_accuracy']) == 50
    assert audit.value(stats, DEFS['save_pct']) == 75
    assert audit.value(Counter(), DEFS['save_pct']) is None


def test_progression_boundary_uses_distance_towards_goal_not_pass_length():
    assert audit.prog((10, 34), (40, 34))
    assert not audit.prog((10, 34), (39.99, 34))
    assert audit.prog((45, 34), (60, 34))
    assert audit.prog((70, 34), (80, 34))
    assert not audit.prog((70, 5), (70, 60))


def test_goal_kick_sentinel_geometry_and_unknown_duels_are_excluded(monkeypatch):
    base = [{'id': '1', 'roles': {'1': 'GK'}, 'players': {
        '1': Counter(minutes=90, passes=1, passes_known=0, passes_completed=0, duels=1)}}]
    monkeypatch.setattr(audit, 'source_rows', lambda *args: base)
    matches = [{'wyId': 1, 'teamsData': {'10': {'formation': {'lineup': [{'playerId': 1}], 'bench': []}}}}]
    common = dict(matchId=1, playerId=1, teamId=10, matchPeriod='1H', tags=[])
    events = [dict(common, eventName='Free Kick', subEventName='Goal kick',
                   positions=[{'x': 100, 'y': 100}, {'x': 20, 'y': 50}]),
              dict(common, eventName='Duel', subEventName='Ground defending duel', positions=[])]
    row = audit.source_data(events, matches, [], {'training_match_ids': [1], 'holdout_match_ids': []})[0]
    stats = row['players']['1']
    assert stats['passes'] == stats['passes_unknown'] == 1
    assert stats['passes_incomplete'] == stats['located_passes'] == stats['backward_passes'] == 0
    assert stats['duels_unknown'] == 1 and stats['duels_lost'] == 0


def test_match_cluster_bootstrap_is_reproducible_and_preserves_known_ratio(monkeypatch):
    monkeypatch.setitem(audit.PROTOCOL, 'bootstrap_replicates', 40)
    rows = [{'players': {'a': Counter(minutes=90, passes=p, passes_completed=p // 2)},
             'roles': {'a': 'DF'}} for p in (20, 80)]
    first = audit.bootstrap_reference(rows)
    assert first == audit.bootstrap_reference(rows)
    assert first['pass_accuracy', 'DF'] == [50, 50]
    assert first['passes', 'DF'][0] <= 50 <= first['passes', 'DF'][1]


def test_engineering_tolerances_are_distinct_from_sampling_intervals():
    assert audit.tolerance(6, DEFS['progressive_passes_completed']) == pytest.approx(2.1)
    assert audit.tolerance(0, DEFS['goals']) == .3
    assert audit.tolerance(80, DEFS['pass_accuracy']) == 10


def test_independent_population_uses_same_fixed_gate_and_detects_distortion():
    reference={'MF':Counter(minutes=900,passes=500,passes_completed=400,located_passes=500,
                            progressive_passes_completed=60)}
    observed={'MF':dict(reference['MF'])}
    assert audit.extended_checks(observed,reference)['MF.progressive_passes_completed']['passed']
    observed['MF']['progressive_passes_completed']=120
    check=audit.extended_checks(observed,reference)['MF.progressive_passes_completed']
    assert not check['passed']
    assert check['tolerance']==pytest.approx(2.1)


def test_club_style_requires_sufficient_clubs_matches_and_events():
    teams={str(i):{'DF':Counter(minutes=1800,assists=10),'FW':Counter(minutes=900,assists=10)} for i in range(10)}
    matches=Counter({k:20 for k in teams})
    reference=audit.club_style_reference(teams,matches,DEFS['assists'],{'DF':3600,'FW':900},['DF','FW'])
    assert reference['DF']['eligible']
    assert reference['DF']['central_80_range']==pytest.approx([2/3,2/3])
    matches['0']=19
    assert not audit.club_style_reference(teams,matches,DEFS['assists'],{'DF':3600,'FW':900},['DF','FW'])['DF']['eligible']
    matches['0']=20
    teams['0']['DF']['assists']=9
    assert audit.club_style_reference(teams,matches,DEFS['assists'],{'DF':3600,'FW':900},['DF','FW'])['DF']['source_clubs']==9
