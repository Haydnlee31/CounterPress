"""Independent football examples for interpretation beyond changing counts.

No generator, model, network or provider fixture supplies the expected facts.
Raw interpretation receives selected events; service checks exercise revision
availability and score context at the actual public boundary.
"""
from types import SimpleNamespace

import pytest

from counterpress.fan.contracts import FanPreferences, MatchRequest
from counterpress.fan.interpretation import interpret_candidates, inside_box
from counterpress.fan.observations import rolling_observations
from counterpress.fan.service import FanService
from counterpress.domain.models import PitchPosition
from counterpress.personalization.contracts import Action, Appearance, Fixture
from counterpress.personalization.metrics import select_events

END = 421000
CLUBS = {'home': 'Eastbridge', 'away': 'Northport'}
PLAYERS = {'h1': 'Alex Finch', 'h2': 'Ben Reed', 'h3': 'Cole Stone',
           'a1': 'Dan Bell', 'a2': 'Evan Park'}


def fixture():
    return Fixture(match_id='diagnostic-match', season='2026-27',
        kickoff='2026-10-19T15:00:00Z', home_id='home', away_id='away',
        competition='Test', source_kind='calibrated_simulation',
        appearances=tuple(Appearance(player_id=pid, club_id='home' if pid[0] == 'h' else 'away',
            start_ms=0, end_ms=5400000, starter=True) for pid in PLAYERS))


def event(i, ms, kind='pass', player='h1', **updates):
    outcome = {'pass': 'complete', 'shot': 'unknown', 'carry': 'controlled',
               'recovery': 'established', 'pressure': 'applied'}[kind]
    return Action(**(dict(match_id='diagnostic-match', event_id=f'e{i}', revision=1,
        delivery_sequence=i, occurrence_order=i, period=1, elapsed_ms=ms,
        available_period=1, available_ms=ms, club_id='home' if player[0] == 'h' else 'away',
        player_id=player, kind=kind, outcome=outcome, source_reference=f'authored:e{i}') | updates))


def point(x, y=34):
    return PitchPosition(x=x, y=y)


def before(player='h1'):
    return [event(1, 80000, player=player), event(2, 100000, player=player),
            event(3, 140000, player=player), event(4, 180000, player=player),
            event(5, 200000, 'shot', player, start=point(75))]


def shooting(*, box=False, unknown=False):
    return before() + [event(6, 270000), event(7, 300000)] + [
        event(i + 8, ms, 'shot', start=None if unknown else point(90 + i if box else 80),
              outcome='unknown' if unknown else 'off_target')
        for i, ms in enumerate((350000, 400000, 420000))]


def interpret(events, preferences=None, match_fixture=None):
    prefs = preferences or FanPreferences()
    match_fixture = match_fixture or fixture()
    candidates = rolling_observations(match_fixture, events, cutoff=(1, END), preferences=prefs,
        club_names=CLUBS, player_names=PLAYERS)
    return interpret_candidates(match_fixture, select_events(events, (1, END)), candidates,
        prefs, CLUBS, PLAYERS)


def metric(row, key, scope='after'):
    return next(f['value'] for f in row['interpretation']['facts']
                if f['metric'] == key and f['scope_window'] == scope)


def service(events):
    store = SimpleNamespace(
        clubs={cid: SimpleNamespace(name=name) for cid, name in CLUBS.items()},
        players={pid: SimpleNamespace(name=name) for pid, name in PLAYERS.items()},
        manifest={'files': {'ledger.json.gz': 'authored-diagnostic-ledger'}},
        row=lambda mid: {'fixture': fixture().model_dump_json()}, events=lambda mid: events)
    return FanService(SimpleNamespace(store=store))


def view(events, **request):
    return service(events).observations('diagnostic-match', MatchRequest(
        cutoff={'period': 1, 'elapsed_ms': END}, card_budget=5, **request))


def test_identical_three_shot_increase_has_different_box_and_range_explanations():
    outside, inside = interpret(shooting())[0], interpret(shooting(box=True))[0]
    assert outside['metrics'] == inside['metrics']
    assert outside['metrics']['before'] == 1 and outside['metrics']['after'] == 3
    assert outside['interpretation']['kind'] == 'range_without_box_chances'
    assert metric(outside, 'shots_outside_box') == 3
    assert metric(outside, 'shots_inside_box') == 0
    assert inside['interpretation']['kind'] == 'closer_chances'
    assert metric(inside, 'shots_inside_box', 'before') == 0
    assert metric(inside, 'shots_inside_box') == 3
    assert outside['summary'] == inside['summary']
    assert outside['text'] != inside['text']
    assert outside['fingerprint'] != inside['fingerprint']
    assert 'outside the box' in outside['text']
    assert 'inside the penalty area' in inside['text']
    # A box corner can be farther from goal than a central shot outside the box.
    assert 'closer to goal' not in inside['text'].lower()


@pytest.mark.parametrize('x,y,expected', [
    (88.5, 13.84, True), (88.5, 54.16, True), (88.499, 34, False),
    (100, 13.839, False), (100, 54.161, False), (105, 34, True),
])
def test_box_geometry_uses_full_penalty_area_boundaries(x, y, expected):
    assert inside_box(event(1, 1000, 'shot', start=point(x, y))) is expected


def regained_shots():
    return before() + [
        event(6, 250000, 'recovery'),
        event(7, 252000, recipient_id='h2', outcome='completed'),
        event(8, 254000, 'carry', 'h2'),
        event(9, 258000, 'shot', 'h2'),
        event(10, 360000, 'recovery'),
        event(11, 363000, recipient_id='h2', outcome='completed'),
        event(12, 368000, 'shot', 'h2'),
        event(13, 410000, 'shot'),
    ]


def test_two_recipient_verified_regains_link_to_shots_without_inferred_assists():
    row = interpret(regained_shots())[0]
    assert row['interpretation']['kind'] == 'regain_chances'
    assert metric(row, 'regain_to_shot_count') == 2
    assert {e['event_id'] for e in row['interpretation']['evidence']} == {
        'e6', 'e7', 'e8', 'e9', 'e10', 'e11', 'e12'}
    assert 'assist' not in row['text'].lower()


@pytest.mark.parametrize('break_kind', ['unknown_recipient', 'opponent', 'restart_pass', 'restart_recovery', 'failed_pass'])
def test_chain_breaks_do_not_become_regain_to_shot_claims(break_kind):
    rows = regained_shots()
    if break_kind == 'unknown_recipient':
        rows[6] = rows[6].model_copy(update={'recipient_id': None, 'outcome': 'complete'})
    elif break_kind == 'opponent':
        rows.append(event(14, 253000, player='a1'))
    elif break_kind == 'restart_pass':
        rows[6] = rows[6].model_copy(update={'restart': True})
    elif break_kind == 'restart_recovery':
        rows[5] = rows[5].model_copy(update={'restart': True})
    else:
        rows[6] = rows[6].model_copy(update={'outcome': 'incomplete', 'recipient_id': None})
    # Only one valid regain remains. Other shot locations/outcomes are unknown,
    # so no alternative explanation is manufactured from the same count rise.
    assert interpret(rows) == []


def test_regain_to_shot_interval_is_inclusive_fifteen_seconds_not_longer():
    rows = regained_shots()
    rows[5] = rows[5].model_copy(update={'elapsed_ms': 243000, 'available_ms': 243000})
    assert metric(interpret(rows)[0], 'regain_to_shot_count') == 2
    rows[5] = rows[5].model_copy(update={'elapsed_ms': 242999, 'available_ms': 242999})
    assert interpret(rows) == []


def passing_loss():
    return [event(i + 1, 70000 + i * 15000) for i in range(10)] + [
        event(i + 11, 250000 + i * 10000, outcome='complete' if i < 6 else 'incomplete')
        for i in range(10)]


def loss_to_shot(regain=342000, shot=350000):
    return passing_loss() + [event(21, regain, 'recovery', 'a1'),
        event(22, 344000, player='a1', recipient_id='a2', outcome='completed'),
        event(23, shot, 'shot', 'a2')]


def test_failed_pass_is_followed_by_adjacent_regain_and_verified_opponent_shot():
    row = interpret(loss_to_shot())[0]
    assert row['interpretation']['kind'] == 'mistakes_to_opponent_shots'
    assert metric(row, 'opponent_shots_after_failed_pass') == 1
    fact = row['interpretation']['facts'][0]
    assert fact['subject_id'] == 'away' and fact['subject_kind'] == 'club'
    assert {e['event_id'] for e in row['interpretation']['evidence']} == {'e20', 'e21', 'e22', 'e23'}
    assert 'within 15 seconds' in row['text']


@pytest.mark.parametrize('regain,shot,expected', [
    (343000, 355000, True), (343001, 355000, False), (343000, 355001, False),
])
def test_failed_pass_links_require_regain_within_three_seconds_and_shot_within_fifteen(regain, shot, expected):
    assert bool(interpret(loss_to_shot(regain, shot))) is expected


@pytest.mark.parametrize('break_kind', ['unknown_recipient', 'opponent', 'restart', 'intervening_completed_pass'])
def test_a_broken_opponent_chain_does_not_blame_failed_passes_for_a_shot(break_kind):
    rows = loss_to_shot()
    if break_kind == 'unknown_recipient':
        rows[-2] = rows[-2].model_copy(update={'outcome': 'complete', 'recipient_id': None})
    elif break_kind == 'opponent':
        rows.append(event(24, 345000, 'carry', 'h3'))
    elif break_kind == 'restart':
        rows[-3] = rows[-3].model_copy(update={'restart': True})
    else:
        rows.append(event(24, 341000))
    assert interpret(rows) == []


def long_pass_failures():
    rows = passing_loss()
    # Six completed short passes, three failed 30m passes, one failed 5m pass.
    # All current origins are in the opponent half, avoiding another diagnosis.
    for index in range(10, 20):
        distance = 30 if 16 <= index <= 18 else 5
        rows[index] = rows[index].model_copy(update={'start': point(70), 'end': point(70 + distance)})
    return rows


def test_recorded_long_pass_geometry_separates_failure_source_from_overall_rate():
    row = interpret(long_pass_failures())[0]
    assert row['interpretation']['kind'] == 'long_pass_failures'
    assert {f['metric']: f['value'] for f in row['interpretation']['facts']} == {
        'failed_long_passes': 3, 'failed_passes': 4,
        'long_pass_attempts': 3, 'long_passes_completed': 0,
        'short_pass_attempts': 7, 'short_passes_completed': 6}


def test_long_pass_diagnosis_requires_locations_and_actual_distance_threshold():
    rows = long_pass_failures()
    rows[10] = rows[10].model_copy(update={'end': None})
    assert interpret(rows) == []
    rows = long_pass_failures()
    rows[16] = rows[16].model_copy(update={'end': point(99.999)})
    assert interpret(rows) == []  # Two long failures no longer account for 2/3.


def deep_pass_handoffs():
    rows = passing_loss()
    rows[16] = rows[16].model_copy(update={'outcome': 'complete'})
    # Two of three failed passes start deep and end at x25. In the opponent's
    # normalized attacking frame the same point is (80,34), not (25,34).
    for index in (17, 18):
        rows[index] = rows[index].model_copy(update={'start': point(20), 'end': point(25)})
    rows[19] = rows[19].model_copy(update={'start': point(70), 'end': point(75)})
    return rows + [event(21, 322000, player='a1', start=point(80), end=point(85)),
                   event(22, 332000, player='a2', start=point(80), end=point(85))]


def test_deep_errors_require_verified_opponent_use_of_the_same_territory():
    row = interpret(deep_pass_handoffs())[0]
    assert row['interpretation']['kind'] == 'deep_pass_failures'
    assert metric(row, 'own_half_failed_passes') == 2
    assert metric(row, 'failed_passes') == 3
    assert metric(row, 'completed_passes_after_opponent_error') == 2
    assert 'Northport made the next completed pass from Eastbridge’s half' in row['text']
    assert 'before they can get play further upfield' not in row['text']
    assert {'e18', 'e19', 'e21', 'e22'} <= {e['event_id'] for e in row['interpretation']['evidence']}


@pytest.mark.parametrize('break_kind', ['wrong_frame', 'spatial_mismatch', 'unknown_carry', 'future_outcome', 'restart', 'unknown_pass'])
def test_deep_origin_alone_is_not_enough_to_claim_opponent_territory(break_kind):
    rows = deep_pass_handoffs()
    for index in (20, 21):
        if break_kind == 'wrong_frame':
            rows[index] = rows[index].model_copy(update={'start': point(25)})
        elif break_kind == 'spatial_mismatch':
            rows[index] = rows[index].model_copy(update={'start': point(86)})
        elif break_kind == 'future_outcome':
            rows[index] = rows[index].model_copy(update={'available_ms': END + 1})
        elif break_kind == 'restart':
            rows[index] = rows[index].model_copy(update={'restart': True})
        elif break_kind == 'unknown_pass':
            rows[index] = rows[index].model_copy(update={'outcome': 'unknown'})
    if break_kind == 'unknown_carry':
        rows += [event(23, 321000, 'carry', 'a1', outcome='unknown'),
                 event(24, 331000, 'carry', 'a2', outcome='unknown')]
    assert interpret(rows) == []
    assert view(rows)['observations'] == []


def test_no_locations_and_unknown_shot_outcomes_leave_count_only_candidate_hidden():
    rows = shooting(unknown=True)
    assert rolling_observations(fixture(), rows, cutoff=(1, END), preferences=FanPreferences(),
        club_names=CLUBS, player_names=PLAYERS)[0]['metrics']['after'] == 3
    assert interpret(rows) == []
    assert view(rows)['observations'] == []


def player_creation():
    return before('h2') + [
        event(6, 250000, 'recovery'),
        event(7, 252000, recipient_id='h2', outcome='completed'),
        event(8, 258000, 'shot', 'h2'),
        event(9, 300000, recipient_id='h2', outcome='completed'),
        event(10, 350000, 'carry'),
        event(11, 400000, recipient_id='h2', outcome='completed'),
        event(12, 410000, 'shot', 'h2'),
    ]


def test_favorite_player_extra_involvement_is_connected_to_two_verified_shooting_moves():
    rows = player_creation()
    assert interpret(rows) == []
    row = interpret(rows, FanPreferences(favorite_player_ids=['h1']))[0]
    assert row['kind'] == 'player_involvement'
    assert row['metrics']['before'] == 0 and row['metrics']['after'] == 5
    assert row['interpretation']['kind'] == 'player_chance_contribution'
    assert metric(row, 'shot_buildups_involved') == 2
    assert row['interpretation']['facts'][0]['subject_id'] == 'h1'
    assert row['interpretation']['facts'][0]['subject_kind'] == 'player'
    assert 'assist' not in row['text'].lower()


def test_missing_receivers_break_player_creation_without_losing_recorded_involvement():
    rows = player_creation()
    for index in (6, 10):
        rows[index] = rows[index].model_copy(update={'recipient_id': None, 'outcome': 'complete'})
    assert interpret(rows, FanPreferences(favorite_player_ids=['h1'])) == []


@pytest.mark.parametrize('changed', [{'start_ms': 120000}, {'end_ms': 401000}])
def test_player_involvement_never_compares_partial_appearance_with_full_window(changed):
    f = fixture()
    f = f.model_copy(update={'appearances': tuple(
        a.model_copy(update=changed) if a.player_id == 'h1' else a for a in f.appearances)})
    assert interpret(player_creation(), FanPreferences(favorite_player_ids=['h1']), f) == []


def test_future_and_unavailable_goals_never_enter_score_context_or_diagnostic_evidence():
    rows = shooting() + [
        event(20, 430000, 'shot', 'h1', outcome='goal', goal_for='home'),
        event(21, 120000, 'shot', 'a1', outcome='goal', goal_for='away', available_ms=500000),
    ]
    row = view(rows)['observations'][0]
    assert row['interpretation']['context'] == {
        'score_for': 0, 'score_against': 0, 'period': 1, 'elapsed_ms': END}
    assert not {'e20', 'e21'} & {e['event_id'] for e in row['interpretation']['evidence']}
    assert 'chasing' not in row['text'] and 'lead' not in row['text']


def test_goal_retraction_changes_context_and_fingerprint_even_outside_count_windows():
    goal = event(20, 20000, 'shot', 'a1', outcome='goal', goal_for='away')
    original_rows = shooting() + [goal]
    original = view(original_rows)['observations'][0]
    assert original['interpretation']['context']['score_against'] == 1
    assert '0–1' in original['text']
    retract = goal.model_copy(update={'revision': 2, 'delivery_sequence': 21,
        'available_ms': END, 'retracted': True})
    updated = view(original_rows + [retract])['observations'][0]
    assert updated['interpretation']['context']['score_against'] == 0
    assert '0–1' not in updated['text']
    assert updated['metrics'] == original['metrics']
    assert updated['evidence'] == original['evidence']
    assert updated['fingerprint'] != original['fingerprint']
    assert view(original_rows + [retract], through_sequence=20)['observations'][0] == original
    delayed = retract.model_copy(update={'available_ms': END + 1})
    assert view(original_rows + [delayed])['observations'][0] == original


def test_visible_shot_position_correction_updates_diagnosis_and_evidence_revision():
    rows = shooting()
    original = view(rows)['observations'][0]
    correction = rows[-1].model_copy(update={'revision': 2, 'delivery_sequence': 11,
        'available_ms': END, 'start': point(93)})
    # One corrected location removes the all-outside claim without proving the
    # separate two-extra-box-shots explanation. Withdrawal is the correct result.
    assert view(rows + [correction])['observations'] == []
    another = rows[-2].model_copy(update={'revision': 2, 'delivery_sequence': 12,
        'available_ms': END, 'start': point(92)})
    updated = view(rows + [correction, another])['observations'][0]
    assert updated['metrics'] == original['metrics']
    assert updated['interpretation']['kind'] == 'closer_chances'
    assert metric(updated, 'shots_inside_box') == 2
    assert updated['fingerprint'] != original['fingerprint']
    assert next(e for e in updated['interpretation']['evidence'] if e['event_id'] == correction.event_id)['revision'] == 2


def test_shots_inside_box_outrank_followed_player_activity_deep_on_the_pitch():
    rows = before('h2') + [
        event(i + 6, ms, start=point(20), end=point(30))
        for i, ms in enumerate((250000, 270000, 290000, 310000, 330000))
    ] + [event(i + 11, ms, 'shot', 'h2', start=point(90 + i))
         for i, ms in enumerate((350000, 400000, 420000))]
    prefs = FanPreferences(favorite_player_ids=['h1'], focus_player_id='h1',
                           favorite_club_ids=['home'], primary_club_id='home')
    result = interpret(rows, prefs)
    assert [row['interpretation']['kind'] for row in result] == [
        'closer_chances', 'player_deep_involvement']
    assert metric(result[0], 'shots_inside_box') == 3
    assert metric(result[1], 'own_half_actions') == 5
    assert result[1]['player_id'] == 'h1'
    assert result[0]['priority'] > result[1]['priority']
