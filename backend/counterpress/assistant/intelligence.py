"""Versioned, deterministic explanations over canonical event observations.

These tools describe recorded on-ball sequences, never animation/tracking or
sporting assist credit. All times are release/occurrence times, not delivery times.
Comparison windows exclude their start and include their end.
"""
from collections import Counter
from typing import Iterable
from counterpress.personalization.contracts import Action, Fixture, MatchRecord
from counterpress.personalization.metrics import select_events

RULE_VERSION = 'football-intelligence-v1'
SUCCESS = {'complete', 'completed'}
RECOVERED = {'established', 'won', 'recovered', 'successful'}
ON_BALL = {'pass', 'carry', 'shot', 'recovery'}


def _snapshot(fixture: Fixture, events: Iterable[Action], cutoff=None):
    if cutoff is not None and (cutoff[0] not in (1, 2) or cutoff[1] < 0):
        raise ValueError('Invalid observation cutoff')
    versions = {}
    identities = {}
    deliveries = {}
    for event in events:
        # Pydantic model_copy intentionally bypasses validators; tool callers may
        # pass copied revisions, so recheck the canonical action contract here.
        event = Action.model_validate(event.model_dump())
        if event.match_id != fixture.match_id:
            raise ValueError('Evidence belongs to another match')
        key = (event.event_id, event.revision)
        if key in versions and versions[key] != event:
            raise ValueError('Conflicting delivery of the same event revision')
        if event.event_id in identities and identities[event.event_id] != event.occurrence_order:
            raise ValueError('Occurrence order is immutable')
        if event.delivery_sequence in deliveries and deliveries[event.delivery_sequence] != key:
            raise ValueError('Conflicting delivery sequence')
        identities[event.event_id] = event.occurrence_order
        deliveries[event.delivery_sequence] = key
        versions[key] = event
    histories = {}
    for event in versions.values():
        histories.setdefault(event.event_id, []).append(event)
    for history in histories.values():
        ordered = sorted(history, key=lambda e: e.revision)
        if any((a.available_period, a.available_ms, a.delivery_sequence) >= (b.available_period, b.available_ms, b.delivery_sequence)
               for a, b in zip(ordered, ordered[1:])):
            raise ValueError('Revision chronology conflicts with availability')
    selected = select_events(versions.values(), cutoff)
    selected = [e for e in selected if cutoff is None or (e.period, e.elapsed_ms) <= cutoff]
    # Reuse canonical actor, appearance, identity and spatial contract checks.
    MatchRecord(fixture=fixture, events=tuple(selected))
    return selected


def _ref(e):
    return {'match_id': e.match_id, 'event_id': e.event_id, 'revision': e.revision,
            'source_reference': e.source_reference, 'period': e.period,
            'elapsed_ms': e.elapsed_ms, 'available_period': e.available_period,
            'available_ms': e.available_ms, 'occurrence_order': e.occurrence_order,
            'player_id': e.player_id, 'club_id': e.club_id, 'kind': e.kind,
            'outcome': e.outcome, 'recipient_id': e.recipient_id,
            'situation': e.situation, 'restart': e.restart, 'penalty': e.penalty}


def _base(fixture, cutoff):
    return {'rule_version': RULE_VERSION, 'match_id': fixture.match_id,
            'source_kind': fixture.source_kind, 'cutoff': cutoff,
            'coordinate_basis': '105x68m; each club attacks +x',
            'tracking': 'unavailable'}


def goal_buildup(fixture: Fixture, events: Iterable[Action], *, event_id: str,
                 cutoff: tuple[int, int] | None = None,
                 expected_revision: int | None = None):
    """Describe an observed suffix ending in a selected, currently visible goal.

    A recovery or restart supplies a known start. Opponent pressure is retained
    as context, not as a possession change or an attacking contribution. Other
    opponents' actions, duels, earlier shots and uncertain outcomes are barriers.
    A suffix after such a barrier remains partial: possession is never inferred
    solely from an actor's club. No assist is awarded by this function.
    """
    selected = _snapshot(fixture, events, cutoff)
    base = _base(fixture, cutoff) | {'event_id': event_id}
    goal = next((e for e in selected if e.event_id == event_id), None)
    if goal is None:
        return base | {'status': 'unavailable', 'reason': 'selected_event_not_visible'}
    if expected_revision is not None and goal.revision != expected_revision:
        return base | {'status': 'unavailable', 'reason': 'selected_revision_changed'}
    if goal.kind != 'shot' or goal.outcome != 'goal' or goal.goal_for != goal.club_id:
        return base | {'status': 'unavailable', 'reason': 'selected_event_is_not_a_goal'}
    chain = [goal]
    start_reason = 'observations_begin'
    start_known = bool(goal.restart or goal.penalty)
    if start_known:
        start_reason = 'restart'
    else:
        for e in reversed(selected[:selected.index(goal)]):
            if e.period != goal.period:
                start_reason = 'period_boundary'
                break
            if e.kind == 'pressure':
                chain.append(e)
                continue
            if e.club_id != goal.club_id:
                start_reason = 'opponent_action'
                break
            if e.kind == 'duel' or e.kind in ('other', 'shot'):
                start_reason = 'uncertain_continuity'
                break
            if e.kind == 'pass' and e.outcome not in SUCCESS:
                start_reason = 'unconfirmed_pass'
                break
            next_actor = next(item.player_id for item in reversed(chain) if item.kind in ON_BALL and item.club_id == goal.club_id)
            holder_after = e.recipient_id if e.kind == 'pass' else e.player_id
            if holder_after is not None and holder_after != next_actor:
                start_reason = 'unobserved_transfer'
                break
            if e.kind == 'recovery':
                if e.outcome not in RECOVERED:
                    start_reason = 'unconfirmed_recovery'
                    break
                chain.append(e)
                start_known = True
                start_reason = 'restart' if e.restart else 'recovery'
                break
            if e.kind == 'carry' and e.outcome not in ('completed', 'complete', 'controlled', 'established', 'successful'):
                start_reason = 'unconfirmed_carry'
                break
            chain.append(e)
            if e.restart:
                start_known = True
                start_reason = 'restart'
                break
    chain.reverse()
    # Leading pressure is context for no observed attacking action; trim it.
    while len(chain) > 1 and chain[0].kind == 'pressure':
        chain.pop(0)
    attacking = [e for e in chain if e.club_id == goal.club_id and e.kind in ON_BALL]
    first = attacking[0]
    contribution = {}
    for e in attacking:
        for pid in (e.player_id, e.recipient_id if e.kind == 'pass' and e.outcome in SUCCESS else None):
            if pid and pid not in contribution:
                contribution[pid] = dict(player_id=pid, passes=0, completed_passes=0,
                    receptions=0, carries=0, shots=0, recoveries=0, event_ids=[])
        row = contribution[e.player_id]
        key = {'pass': 'passes', 'carry': 'carries', 'shot': 'shots', 'recovery': 'recoveries'}[e.kind]
        row[key] += 1
        row['event_ids'].append(e.event_id)
        if e.kind == 'pass' and e.outcome in SUCCESS:
            row['completed_passes'] += 1
            if e.recipient_id:
                recipient = contribution[e.recipient_id]
                recipient['receptions'] += 1
                if e.event_id not in recipient['event_ids']:
                    recipient['event_ids'].append(e.event_id)
    duration = round((goal.elapsed_ms - first.elapsed_ms) / 1000, 3)
    metrics = {'completed_passes': sum(e.kind == 'pass' and e.outcome in SUCCESS for e in attacking),
               'carry_count': sum(e.kind == 'carry' for e in attacking),
               'participant_count': len(contribution), 'observed_duration_seconds': duration,
               'regain_to_shot_seconds': duration if start_known and start_reason == 'recovery' else None,
               'net_progression_m': round(goal.start.x - first.start.x, 3) if goal.start and first.start else None}
    return base | {'status': 'available', 'goal': _ref(goal), 'timeline': [_ref(e) for e in chain],
                   'metrics': metrics, 'contributions': list(contribution.values()),
                   'units': {'completed_passes': 'count', 'carry_count': 'segments', 'participant_count': 'players',
                       'observed_duration_seconds': 'seconds', 'regain_to_shot_seconds': 'seconds', 'net_progression_m': 'metres'},
                   'window': {'period': goal.period, 'start_ms': first.elapsed_ms, 'end_ms': goal.elapsed_ms, 'boundary': '[start,end]'},
                   'coverage': {'start_known': start_known, 'start_reason': start_reason,
                       'complete_possession': start_known and all(e.recipient_id for e in attacking if e.kind == 'pass'), 'tracking': 'unavailable',
                       'basis': 'recorded_actions', 'assist_credit': 'not_inferred',
                       'carry_basis': 'recorded_segments',
                       'receptions_complete': all(e.recipient_id for e in attacking if e.kind == 'pass' and e.outcome in SUCCESS),
                       'located_actions': sum(e.start is not None for e in attacking)},
                   'evidence': [_ref(e) for e in chain]}


def _clock(fixture, at):
    return at[1] + (fixture.period_lengths_ms[0] if at[0] == 2 else 0)


def involvement(fixture: Fixture, events: Iterable[Action], *, player_id: str,
                cutoff: tuple[int, int] | None = None,
                window_start: tuple[int, int] | None = None):
    """Recorded action counts and share, not touches or off-ball activity.

    Counts include unlocated observations. Carry segments are not equivalent to
    analytics.py's joined continuous carries. Null marks source-wide missingness.
    """
    selected = _snapshot(fixture, events, cutoff)
    base = _base(fixture, cutoff) | {'player_id': player_id, 'window_start': window_start}
    appearance = next((a for a in fixture.appearances if a.player_id == player_id), None)
    if appearance is None:
        return base | {'status': 'unavailable', 'reason': 'player_not_in_fixture'}
    end = min(sum(fixture.period_lengths_ms), _clock(fixture, cutoff)) if cutoff else sum(fixture.period_lengths_ms)
    if window_start is not None and (window_start[0] not in (1, 2) or not 0 <= window_start[1] <= fixture.period_lengths_ms[window_start[0] - 1]):
        return base | {'status': 'unavailable', 'reason': 'invalid_observation_window'}
    start = _clock(fixture, window_start) if window_start else 0
    if start >= end or start < 0:
        return base | {'status': 'unavailable', 'reason': 'empty_observation_window'}
    minutes = max(0, min(end, appearance.end_ms) - max(start, appearance.start_ms)) / 60000
    if not minutes:
        return base | {'status': 'unavailable', 'reason': 'player_not_on_pitch_in_window'}
    rows = [e for e in selected if window_start is None or (e.period, e.elapsed_ms) > window_start]
    # Team-share denominator covers exactly the player's observed appearance.
    team = [e for e in rows if e.club_id == appearance.club_id and e.kind in ON_BALL
            and max(start, appearance.start_ms) <= _clock(fixture, (e.period, e.elapsed_ms)) <= min(end, appearance.end_ms)]
    own = [e for e in team if e.player_id == player_id]
    successful = [e for e in team if e.kind == 'pass' and e.outcome in SUCCESS]
    recipient_known = [e for e in successful if e.recipient_id]
    unknown_passes = sum(e.kind == 'pass' and e.outcome == 'unknown' for e in own)
    team_unknown_passes = sum(e.kind == 'pass' and e.outcome == 'unknown' for e in team)
    generated = fixture.source_kind == 'calibrated_simulation'
    reception_complete = generated and not team_unknown_passes and len(recipient_known) == len(successful)
    counts = Counter(e.kind for e in own)
    metrics = {'passes': counts['pass'], 'completed_passes': sum(e.kind == 'pass' and e.outcome in SUCCESS for e in own),
               'receptions': sum(e.recipient_id == player_id for e in successful) if reception_complete else None,
               'carries': counts['carry'] if generated else None, 'shots': sum(e.kind == 'shot' and e.outcome != 'own_goal' for e in own),
               'recoveries': sum(e.kind == 'recovery' and e.outcome in RECOVERED and not e.restart for e in own) if fixture.source_kind != 'adapted_archive' else None,
               'observed_actions': len(own), 'action_share_pct': round(len(own) / len(team) * 100, 3) if team else None,
               'minutes': round(minutes, 6)}
    refs = [e for e in team if e.player_id == player_id or e.recipient_id == player_id]
    return base | {'status': 'available', 'club_id': appearance.club_id, 'metrics': metrics,
                   'metric_labels': {'completed_passes': 'Recorded completed passes'},
                   'units': {key: 'minutes' if key == 'minutes' else 'percent' if key == 'action_share_pct' else 'segments' if key == 'carries' else 'count' for key in metrics},
                   'denominators': {'team_actions': len(team), 'located_actions': sum(e.start is not None for e in own),
                       'successful_passes': len(successful), 'recipient_known_passes': len(recipient_known),
                       'passes_with_known_outcomes': counts['pass'] - unknown_passes,
                       'team_unknown_pass_outcomes': team_unknown_passes},
                   'coverage': {'receptions_complete': reception_complete, 'carries_complete': generated,
                       'pass_outcomes_complete': unknown_passes == 0, 'unknown_pass_outcomes': unknown_passes,
                       'recoveries_complete': fixture.source_kind != 'adapted_archive',
                       'basis': 'recorded_actions', 'carry_basis': 'recorded_segments', 'tracking': 'unavailable',
                       'minutes_basis': fixture.minutes_basis},
                   'evidence': [_ref(e) for e in refs]}


def compare_windows(fixture: Fixture, events: Iterable[Action], *, club_id: str,
                    period: int, start_ms: int, split_ms: int, end_ms: int,
                    cutoff: tuple[int, int], min_actions: int = 5):
    """Descriptive counts over adjacent equal-duration, completed (start,end] windows."""
    base = _base(fixture, cutoff) | {'club_id': club_id}
    if club_id not in (fixture.home_id, fixture.away_id):
        return base | {'status': 'unavailable', 'reason': 'club_not_in_fixture'}
    if (period not in (1, 2) or not 0 <= start_ms < split_ms < end_ms
            or split_ms - start_ms != end_ms - split_ms
            or end_ms > fixture.period_lengths_ms[period - 1] or min_actions < 1):
        return base | {'status': 'unavailable', 'reason': 'incomparable_windows'}
    if (period, end_ms) > cutoff:
        return base | {'status': 'unavailable', 'reason': 'window_not_completed'}
    selected = _snapshot(fixture, events, cutoff)
    rows = [e for e in selected if e.club_id == club_id and e.period == period and start_ms < e.elapsed_ms <= end_ms and e.kind in ON_BALL]
    groups = [[e for e in rows if start < e.elapsed_ms <= end] for start, end in ((start_ms, split_ms), (split_ms, end_ms))]
    if any(len(group) < min_actions for group in groups):
        return base | {'status': 'unavailable', 'reason': 'insufficient_observations', 'sample_sizes': list(map(len, groups))}
    def measures(group):
        return {'passes': sum(e.kind == 'pass' for e in group),
                'completed_passes': sum(e.kind == 'pass' and e.outcome in SUCCESS for e in group),
                'shots': sum(e.kind == 'shot' and e.outcome != 'own_goal' for e in group),
                'recoveries': sum(e.kind == 'recovery' and e.outcome in RECOVERED and not e.restart for e in group) if fixture.source_kind != 'adapted_archive' else None,
                'observed_actions': len(group)}
    before, after = map(measures, groups)
    unknown_passes = [sum(e.kind == 'pass' and e.outcome == 'unknown' for e in group) for group in groups]
    return base | {'status': 'available', 'before': before, 'after': after,
                   'metric_labels': {'completed_passes': 'Recorded completed passes'},
                   'units': {key: 'count' for key in before},
                   'delta': {key: after[key] - before[key] if before[key] is not None else None for key in before},
                   'windows': [{'period': period, 'start_ms': start, 'end_ms': end, 'boundary': '(start,end]'}
                               for start, end in ((start_ms, split_ms), (split_ms, end_ms))],
                   'coverage': {'min_actions': min_actions, 'sample_sizes': list(map(len, groups)),
                       'pass_outcomes_complete': not any(unknown_passes),
                       'pass_outcomes_complete_by_window': [n == 0 for n in unknown_passes],
                       'unknown_pass_outcomes': unknown_passes,
                       'basis': 'recorded_actions', 'interpretation': 'descriptive_not_causal', 'tracking': 'unavailable'},
                   'evidence': [_ref(e) for e in rows]}
