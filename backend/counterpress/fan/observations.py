"""Trailing match observations calculated from visible canonical event revisions.

The two adjacent three-minute windows end at the caller's exact playback cutoff,
exclude their start and include their end. They never cross a period boundary.
These are descriptive changes in recorded actions, not tracking-based pressure,
possession, inferred causes, or model-generated statistics. No network calls.
"""
from collections import Counter
from typing import Iterable, Mapping

from counterpress.assistant.intelligence import ON_BALL, SUCCESS, _snapshot
from counterpress.personalization.contracts import Action, Fixture
from .contracts import FanPreferences
from .presentation import fingerprint, words

RULE_VERSION = 'live-observations-v2-diagnostics'
WINDOW_MS = 180_000
MIN_ACTIONS = 5
MIN_PASSES = 10


def _reference(event: Action):
    return {'match_id': event.match_id, 'event_id': event.event_id,
            'revision': event.revision, 'delivery_sequence': event.delivery_sequence,
            'occurrence_order': event.occurrence_order,
            'source_reference': event.source_reference, 'period': event.period,
            'elapsed_ms': event.elapsed_ms, 'available_period': event.available_period,
            'available_ms': event.available_ms, 'club_id': event.club_id,
            'player_id': event.player_id, 'kind': event.kind, 'outcome': event.outcome}


def rolling_observations(fixture: Fixture, events: Iterable[Action], *,
                         cutoff: tuple[int, int], preferences: FanPreferences,
                         club_names: Mapping[str, str], player_names: Mapping[str, str]):
    """Return ranked candidates, using one validated revision snapshot per call.

    Stable semantic IDs allow replacement/withdrawal on every new snapshot. The
    fingerprint pins the actual windows, evidence and audience; it is not an ID
    for a permanently true claim. Callers must replace, not append, this result.
    """
    period, end = cutoff
    if period not in (1, 2) or type(end) is not int or not 0 <= end <= fixture.period_lengths_ms[period - 1]:
        raise ValueError('Playback cutoff outside match')
    if end < WINDOW_MS * 2:
        return []
    start, split = end - WINDOW_MS * 2, end - WINDOW_MS
    windows = [{'period': period, 'start_ms': a, 'end_ms': b, 'boundary': '(start,end]'}
               for a, b in ((start, split), (split, end))]
    selected = _snapshot(fixture, events, cutoff)
    rows = [e for e in selected if e.period == period and start < e.elapsed_ms <= end and e.kind in ON_BALL]
    candidates = []
    followed = set(preferences.favorite_player_ids)
    if preferences.focus_player_id:
        followed.add(preferences.focus_player_id)

    for club_id in (fixture.home_id, fixture.away_id):
        team_rows = [e for e in rows if e.club_id == club_id]
        before = [e for e in team_rows if e.elapsed_ms <= split]
        after = [e for e in team_rows if e.elapsed_ms > split]
        sample_sizes = [len(before), len(after)]
        if min(sample_sizes) < MIN_ACTIONS:
            continue
        name = club_names[club_id]
        evidence = [_reference(e) for e in team_rows]
        preference_boost = (20 if club_id == preferences.primary_club_id else
                            10 if club_id in preferences.favorite_club_ids else 0)

        def candidate(kind, title, text, metrics, priority, player_id=None):
            identity = f'{fixture.match_id}:{period}:{player_id or club_id}:{kind}'
            result = {'id': identity, 'kind': kind, 'title': title, 'text': text,
                      'club_id': club_id, 'player_id': player_id,
                      'windows': windows, 'metrics': {**metrics, 'sample_sizes': sample_sizes},
                      'priority': priority + preference_boost, 'evidence': evidence}
            result['fingerprint'] = fingerprint({'rule_version': RULE_VERSION,
                'preferences': preferences.model_dump(), 'observation': result})
            candidates.append(result)

        shots = [sum(e.kind == 'shot' and e.outcome != 'own_goal' for e in group) for group in (before, after)]
        if shots[1] >= 3 and shots[1] - shots[0] >= 2:
            candidate('shots_increase', words(preferences, f'More shots from {name}', f'{name}射门增多'),
                words(preferences,
                    f'{name} have taken {shots[1]} shots in the last 3 minutes, up from {shots[0]} in the previous 3.',
                    f'{name}最近3分钟完成{shots[1]}次射门，此前3分钟为{shots[0]}次。'),
                {'metric': 'shots', 'before': shots[0], 'after': shots[1], 'unit': 'count'},
                80 + (10 if preferences.metric_focus == 'scoring' else 0))

        passes = [[e for e in group if e.kind == 'pass'] for group in (before, after)]
        # Unknown outcomes cannot silently become failed passes, nor a selectively
        # observed denominator used to claim a team's passing has worsened.
        if min(map(len, passes)) >= MIN_PASSES and all(e.outcome != 'unknown' for group in passes for e in group):
            completed = [sum(e.outcome in SUCCESS for e in group) for group in passes]
            rates = [100 * count / len(group) for count, group in zip(completed, passes)]
            if rates[0] - rates[1] >= 15:
                candidate('passing_decline', words(preferences, f'Fewer passes finding a teammate', '传球成功率下降'),
                    words(preferences,
                        f'{name} completed {completed[1]} of {len(passes[1])} passes in the last 3 minutes, compared with {completed[0]} of {len(passes[0])} in the previous 3.',
                        f'{name}最近3分钟{len(passes[1])}次传球成功{completed[1]}次，此前3分钟{len(passes[0])}次成功{completed[0]}次。'),
                    {'metric': 'pass_completion_pct', 'before': round(rates[0], 3), 'after': round(rates[1], 3),
                     'unit': 'percent', 'completed': completed, 'attempted': list(map(len, passes))},
                    60 + (10 if preferences.metric_focus == 'passing' else 0))

        counts = [Counter(e.player_id for e in group) for group in (before, after)]
        for player_id in sorted(followed & set(counts[1])):
            previous, current = counts[0][player_id], counts[1][player_id]
            if current < 5 or current - previous < 3:
                continue
            player_name = player_names[player_id]
            candidate('player_involvement', words(preferences, f'{player_name} is getting involved', f'{player_name}参与增多'),
                words(preferences,
                    f'{player_name} has made {current} recorded on-ball actions in the last 3 minutes, up from {previous} in the previous 3.',
                    f'{player_name}最近3分钟完成{current}次有球动作，此前3分钟为{previous}次。'),
                {'metric': 'recorded_on_ball_actions', 'before': previous, 'after': current, 'unit': 'count'},
                90 + (10 if player_id == preferences.focus_player_id else 0), player_id)

    return sorted(candidates, key=lambda c: (-c['priority'], c['id']))
