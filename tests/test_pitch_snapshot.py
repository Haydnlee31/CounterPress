"""Pitch replay uses bounded, canonical events known at the requested cutoff."""
from counterpress.api.snapshots import SnapshotService, replay_session
from counterpress.audience import ViewingPreferences
from counterpress.domain.models import MatchTime
from test_history import FIXTURES, revise


def test_pitch_is_bounded_chronological_and_independent_of_depth():
    service = SnapshotService(FIXTURES)
    for at in (180000, 400000, 780000):
        casual = service.snapshot('increase', at, preferences=ViewingPreferences(depth='casual'))
        analyst = service.snapshot('increase', at, preferences=ViewingPreferences(depth='analyst'))
        canonical = replay_session(service.history('increase')).snapshot(MatchTime(period=2, elapsed_ms=at))
        assert casual.pitch_events == analyst.pitch_events == canonical.events[-24:]
        assert 1 <= len(casual.pitch_events) <= 24
        assert all(e.available_at.elapsed_ms <= at and e.occurred_at.elapsed_ms <= at for e in casual.pitch_events)
        assert list(casual.pitch_events) == sorted(casual.pitch_events, key=lambda e:e.occurrence_order)


def test_correction_changes_pitch_only_when_available_and_never_duplicates_player_event():
    service = SnapshotService(FIXTURES)
    before = service.snapshot('increase',780000).pitch_events
    event = revise(before[-1], revision=2, source_delivery_sequence=100, available_at={'period':2,'elapsed_ms':785000})
    service.ingest('increase',(event,))
    assert service.snapshot('increase',780000).pitch_events == before
    after = service.snapshot('increase',event.available_at.elapsed_ms).pitch_events
    assert len({e.event_id for e in after}) == len(after)
    assert next(e for e in after if e.event_id==event.event_id) == event
