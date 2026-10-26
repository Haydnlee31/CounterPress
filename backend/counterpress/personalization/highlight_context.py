"""Read boundaries for authored highlights, independent of animation availability."""
from hashlib import sha256
import json


def highlight_context(store, clip):
    """Offer a later knowledge boundary without moving the viewer to full time.

    Call under store.snapshot(). Revisions to earlier plays can affect the score
    and milestone context; later-occurring plays must not advance this moment.
    Delivery ceilings distinguish corrections with equal availability timestamps.
    The immutable animation remains unavailable after any match-source change.
    """
    mid = clip['match_id']
    record = store.original(mid)
    fixture = record.fixture
    originals = {(e.event_id, e.revision): e for e in record.events}
    ids = set(clip['event_ids'])
    events = [e for e in record.events if e.event_id in ids]
    if not events or len(events) != len(ids):
        raise ValueError('Invalid highlight references')
    first = min(events, key=lambda e: (e.period, e.elapsed_ms, e.occurrence_order))
    end = (clip['end']['period'], clip['end']['elapsed_ms'])
    all_events = store.events(mid)
    original_past = {e.event_id for e in record.events if (e.period, e.elapsed_ms) <= end}
    overlays = [e for e in all_events if (e.event_id, e.revision) not in originals
                and (e.event_id in original_past or (e.period, e.elapsed_ms) <= end)]
    latest = max([end, *((e.available_period, e.available_ms) for e in overlays)])
    original_sequence = max(e.delivery_sequence for e in record.events)
    latest_sequence = max([original_sequence, *(e.delivery_sequence for e in overlays)])
    goal = max((e for e in all_events if e.event_id == clip['goal_event_id']),
               key=lambda e: e.revision)
    initial_ms = max(0, min(first.elapsed_ms - 1, first.available_ms - 1))
    initial_clock = sum(fixture.period_lengths_ms[:first.period - 1]) + initial_ms
    def clock(period, milliseconds):
        return {'period': period, 'elapsed_ms': milliseconds}
    replay_available = store.evidence_digest(mid) == store.row(mid)['digest']
    # Includes source versions even when a restoration has identical statistics.
    version = {'dataset': store.dataset, 'highlight_id': clip['highlight_id'],
               'original_digest': store.row(mid)['digest'], 'replay_available': replay_available,
               'overlays': [e.model_dump(mode='json') for e in sorted(overlays, key=lambda e: e.delivery_sequence)]}
    return {
        'highlight_id': clip['highlight_id'], 'match_id': mid,
        'period_lengths_ms': list(fixture.period_lengths_ms),
        'teams': [{'team_id': cid, 'name': store.clubs[cid].name,
                   'player_ids': [a.player_id for a in fixture.appearances if a.club_id == cid]}
                  for cid in (fixture.home_id, fixture.away_id)],
        'active_player_ids': [a.player_id for a in fixture.appearances
                              if a.start_ms <= initial_clock < a.end_ms],
        'initial_cutoff': clock(first.period, initial_ms),
        'original_cutoff': clock(*end), 'latest_cutoff': clock(*latest),
        'review_available': latest[1] <= fixture.period_lengths_ms[latest[0] - 1] + 60000,
        'original_sequence': original_sequence, 'latest_sequence': latest_sequence,
        'goal': {'event_id': goal.event_id, 'player_id': goal.player_id, 'revision': goal.revision, 'retracted': goal.retracted,
                 'occurred_at': clock(goal.period, goal.elapsed_ms),
                 'available_at': clock(goal.available_period, goal.available_ms)},
        'replay_available': replay_available,
        'content_version': sha256(json.dumps(version, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
    }
