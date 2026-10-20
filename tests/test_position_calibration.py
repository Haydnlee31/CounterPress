"""Independent small examples for source semantics and positional audit gates."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from counterpress.personalization.positions import source_rows, summarize, position_checks, formation_reference


def source_example():
    people = [{'wyId': 1, 'role': {'name': 'Goalkeeper'}}, {'wyId': 2, 'role': {'name': 'Forward'}},
              {'wyId': 3, 'role': {'name': 'Goalkeeper'}}, {'wyId': 4, 'role': {'name': 'Defender'}}]
    match = {'wyId': 10, 'teamsData': {
        '100': {'score': 1, 'formation': {'lineup': [{'playerId': 1}, {'playerId': 2}], 'substitutions': 'null'}},
        '200': {'score': 0, 'formation': {'lineup': [{'playerId': 3}, {'playerId': 4}], 'substitutions': []}}}}
    def event(pid, team, kind, subtype, tags, second, positions=None):
        return {'matchId': 10, 'playerId': pid, 'teamId': team, 'eventName': kind, 'subEventName': subtype,
                'tags': [{'id': t} for t in tags], 'matchPeriod': '1H', 'eventSec': second,
                'positions': positions or [{'x': 5, 'y': 50}, {'x': 45, 'y': 50}]}
    events = [event(1, 100, 'Pass', 'Simple pass', [1801], 10),
              event(1, 100, 'Pass', 'High pass', [1802], 20),
              event(1, 100, 'Free Kick', 'Goal kick', [], 30),
              event(2, 100, 'Free Kick', 'Throw in', [1801], 40),
              event(2, 100, 'Duel', 'Ground attacking duel', [1801, 702], 50),
              event(4, 200, 'Duel', 'Ground defending duel', [1801, 702], 50),
              event(2, 100, 'Shot', 'Shot', [1205, 1801], 60),
              event(3, 200, 'Save attempt', 'Reflexes', [1205, 1801], 61),
              event(2, 100, 'Shot', 'Shot', [101, 1205], 70),
              event(3, 200, 'Save attempt', 'Reflexes', [101, 1802], 71)]
    return events, [match], people


def test_source_denominators_unknown_restarts_draws_and_saves():
    events, matches, players = source_example()
    row = source_rows(events, matches, players, [10])[0]
    # Three attempts including a goal kick, but only TWO known outcomes.
    keeper = row['players']['1']
    assert (keeper['passes'], keeper['passes_known'], keeper['passes_completed']) == (3, 2, 1)
    assert keeper['completed_long'] == keeper['completed_located'] == 1
    striker = row['players']['2']
    assert striker.get('passes', 0) == 0  # throw-ins are not passes
    assert striker['duels'] == striker['duels_drawn'] == 1
    assert striker['duels_won'] == 0  # tag 1801 alone must not award a win
    assert (striker['shots'], striker['shots_on_target'], striker['goals']) == (2, 2, 1)
    opponent = row['players']['3']
    assert (opponent['saves'], opponent['shots_faced'], opponent['goals_conceded']) == (1, 2, 1)
    assert opponent['clean_sheets'] == 0 and keeper['clean_sheets'] == 1
    assert source_rows(events, matches, players, [99]) == []


def test_source_dismissal_and_substitution_minutes_and_own_goal():
    events, matches, players = source_example()
    dismissed = deepcopy(events[4]); dismissed.update(eventSec=1800, eventName='Foul', subEventName='Foul', tags=[{'id': 1701}])
    own_goal = deepcopy(events[6]); own_goal.update(playerId=4, teamId=200, eventSec=2400, eventName='Others on the ball', subEventName='Touch', tags=[{'id': 102}])
    row = source_rows([*events, dismissed, own_goal], matches, players, [10])[0]
    assert row['players']['2']['minutes'] == 30
    assert row['players']['3']['goals_conceded'] == 2
    assert row['players']['4'].get('goals', 0) == 0


def test_rates_pool_counts_instead_of_averaging_percentages_and_bootstrap_is_reproducible():
    rows = [{'id': str(i), 'players': {'a': {'minutes': 90, 'passes': p, 'passes_known': p, 'passes_completed': c}},
             'roles': {'a': 'GK'}} for i, (p, c) in enumerate([(10, 10), (90, 45)])]
    result = summarize(rows, bootstrap=40)
    assert result == summarize(rows, bootstrap=40)
    assert result['roles']['GK']['rates']['pass_completion'] == .55
    assert result['roles']['GK']['rates']['passes_per90'] == 50
    assert result['roles']['GK']['players_900_minutes'] == 0
    assert result['roles']['GK']['ci95']['pass_completion'][0] <= .55 <= result['roles']['GK']['ci95']['pass_completion'][1]


def test_checks_fail_when_a_position_is_distorted_even_if_other_positions_are_unchanged():
    root = Path(__file__).resolve().parents[1] / 'fixtures/personalization'
    target = json.loads((root / 'calibration.json').read_text())['position_target']
    altered = deepcopy(target)
    altered['roles']['GK']['rates']['passes_per90'] = 10
    altered['roles']['MF']['rates']['duels_per90'] *= 2
    checks = position_checks(altered, target)
    assert not checks['GK.passes_per90']['passed']
    assert not checks['MF.duels_per90']['passed']
    assert checks['DF.passes_per90']['passed']


def test_formation_standardization_uses_minutes_not_synthetic_goal_counts():
    source = {'roles': {r: {'rates': {'goals_per90': g, 'assists_per90': g}} for r, g in [('GK', 0), ('DF', .05), ('MF', .1), ('FW', .3)]}}
    observed = {'roles': {r: {'counts': {'minutes': m, 'goals': 999}} for r, m in [('GK', 90), ('DF', 360), ('MF', 270), ('FW', 270)]}}
    reference = formation_reference({'per_match': {'goals': 2.7}}, source, observed)
    assert reference['goal_role_share']['FW'] == pytest.approx(81 / 126)
    assert sum(reference['goal_role_share'].values()) == pytest.approx(1)
    assert reference['per_match']['goals'] == 2.7
    observed['roles']['FW']['counts']['goals'] = 0
    assert formation_reference({'per_match': {'goals': 2.7}}, source, observed) == reference


def test_empty_holdout_player_cohort_uses_declared_training_distribution():
    root = Path(__file__).resolve().parents[1] / 'fixtures/personalization'
    target = json.loads((root / 'calibration.json').read_text())['position_target']
    short = deepcopy(target)
    for row in short['roles'].values():
        row['players_900_minutes'] = 0
        for distribution in row['distributions'].values():
            distribution.update(n=0, p10=0, p90=0)
    checked = position_checks(target, short, target)
    assert checked['GK.passes_per90.p90']['passed']
    assert checked['GK.passes_per90.p90']['reference'] == 'training_distribution_900_minutes'
    assert not position_checks(target, short)['GK.passes_per90.p90']['passed']


def test_failed_candidate_cannot_be_loaded(tmp_path):
    from counterpress.personalization.store import DataStore
    (tmp_path/'manifest.json').write_text(json.dumps({'validation_status':'failed'}))
    with pytest.raises(ValueError, match='did not pass validation'):
        DataStore(tmp_path)


def test_drawn_duel_survives_replay_without_awarding_either_player_a_win():
    from types import SimpleNamespace
    from counterpress.personalization.contracts import Action, Appearance, Fixture, MatchRecord
    from counterpress.personalization.metrics import reduce_record
    from counterpress.personalization.replay import native_feed
    fixture=Fixture(match_id='draw-match',season='test',kickoff='2026-10-20T00:00:00Z',home_id='home',away_id='away',
        competition='test',source_kind='calibrated_simulation',appearances=(
            Appearance(player_id='a',club_id='home',start_ms=0,end_ms=5400000,starter=True),
            Appearance(player_id='b',club_id='away',start_ms=0,end_ms=5400000,starter=True)))
    event=Action(match_id='draw-match',event_id='draw',revision=1,delivery_sequence=1,occurrence_order=1,
        period=1,elapsed_ms=1000,available_period=1,available_ms=1100,club_id='home',player_id='a',
        kind='duel',outcome='draw',opponent_id='b',start={'x':30,'y':20},source_reference='manual:draw')
    record=MatchRecord(fixture=fixture,events=(event,));summary=reduce_record(record)
    assert [(s['duels'],s['duels_won'],s['duels_unknown']) for s in summary['players'].values()]==[(1,0,0),(1,0,0)]
    feed=native_feed(record,{club:SimpleNamespace(name=club) for club in ('home','away')})
    assert feed.events[0].action.outcome=='draw'
    assert feed.initial_state.controlled_possession_team_id=='home'
