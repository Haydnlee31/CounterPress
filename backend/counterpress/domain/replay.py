"""Pure canonical selection and state reduction, with an in-memory source journal."""

from collections.abc import Iterable

from counterpress.domain.models import (
    DuelDetails, Event, EventReference, InitialState, MatchState, MatchTime,
    RecoveryDetails, ShotDetails,
)


def validate_records(records: Iterable[Event], match_id: str) -> tuple[Event, ...]:
    """Deduplicate exact retransmissions and reject conflicting source identities."""
    identities: dict[tuple[str, int], Event] = {}
    sequences: dict[int, tuple[str, int]] = {}
    orders: dict[int, str] = {}
    revisions: dict[str, list[Event]] = {}
    for event in records:
        if event.match_id != match_id:
            raise ValueError("journal records must belong to the selected match")
        identity = event.event_id, event.revision
        if identity in identities:
            if event != identities[identity]:
                raise ValueError("conflicting payload for the same event revision")
            continue
        if event.source_delivery_sequence in sequences:
            raise ValueError("source delivery sequence reused by another record")
        if event.occurrence_order in orders and orders[event.occurrence_order] != event.event_id:
            raise ValueError("occurrence order reused by another event")
        identities[identity] = event
        sequences[event.source_delivery_sequence] = identity
        orders[event.occurrence_order] = event.event_id
        revisions.setdefault(event.event_id, []).append(event)
    for versions in revisions.values():
        versions.sort(key=lambda event: event.revision)
        if len({event.occurrence_order for event in versions}) != 1:
            raise ValueError("occurrence order must remain stable across revisions")
        for previous, current in zip(versions, versions[1:]):
            if current.source_delivery_sequence <= previous.source_delivery_sequence:
                raise ValueError("newer revision requires a newer source delivery sequence")
            if current.available_at.key() < previous.available_at.key():
                raise ValueError("newer revision cannot be available before an older revision")
    return tuple(sorted(identities.values(), key=lambda event: event.source_delivery_sequence))


def canonical_events(records: Iterable[Event], cutoff: MatchTime) -> tuple[Event, ...]:
    """Select highest AVAILABLE revision first, then apply occurrence cutoff.

    Input must have passed validate_records. There is deliberately no window
    filtering here: a correction outside a window must supersede its old record.
    """
    selected: dict[str, Event] = {}
    for event in records:
        if event.available_at.key() <= cutoff.key():
            previous = selected.get(event.event_id)
            if previous is None or event.revision > previous.revision:
                selected[event.event_id] = event
    return tuple(sorted(
        (event for event in selected.values() if event.occurred_at.key() <= cutoff.key()),
        key=lambda event: (*event.occurred_at.key(), event.occurrence_order),
    ))


def reduce_state(
    initial: InitialState, match_id: str, events: tuple[Event, ...],
    cutoff: MatchTime, source_delivery_cursor: int,
) -> MatchState:
    """Rebuild possession and score from the initial state and canonical goal records."""
    if cutoff.key() < initial.at.key():
        raise ValueError("cutoff cannot precede initial state")
    score = dict(initial.score)
    control = initial.controlled_possession_team_id
    if control not in initial.score:
        raise ValueError("initial controlling team must have a declared score")
    previous_key = (*initial.at.key(), -1)
    for event in events:
        key = (*event.occurred_at.key(), event.occurrence_order)
        if event.match_id != match_id or event.actor.team_id not in initial.score:
            raise ValueError("event match/team does not match initial state")
        if key <= previous_key or event.occurred_at.key() > cutoff.key() or event.available_at.key() > cutoff.key():
            raise ValueError("state requires canonical, ordered events within the cutoff")
        action = event.action
        if isinstance(action, RecoveryDetails):
            if action.from_team_id != control:
                raise ValueError(f"{event.event_id}: recovery contradicts controlled possession")
            control = event.actor.team_id
        elif isinstance(action, DuelDetails):
            if control not in (event.actor.team_id, action.opponent.team_id):
                raise ValueError(f"{event.event_id}: duel does not involve controlling team")
        elif event.actor.team_id != control:
            raise ValueError(f"{event.event_id}: action contradicts controlled possession")
        if isinstance(action, ShotDetails) and action.outcome == "goal":
            score[event.actor.team_id] += 1
        previous_key = key
    return MatchState(
        match_id=match_id, at=cutoff, score=score,
        controlled_possession_team_id=control, source_delivery_cursor=source_delivery_cursor,
        applied_events=tuple(EventReference(event_id=event.event_id, revision=event.revision) for event in events),
    )


class EventJournal:
    """Small in-memory journal used by replay; HistoryStore supplies durable storage."""

    def __init__(self, match_id: str, records: Iterable[Event] = ()):
        self.match_id = match_id
        self._records = validate_records(records, match_id)

    @property
    def records(self) -> tuple[Event, ...]:
        return self._records

    def append(self, records: Iterable[Event]) -> None:
        # Validation finishes before assignment; a rejected batch leaves the journal intact.
        self._records = validate_records((*self._records, *records), self.match_id)

    def events_at(self, cutoff: MatchTime) -> tuple[Event, ...]:
        return canonical_events(self._records, cutoff)

    def cursor_at(self, cutoff: MatchTime) -> int:
        # Source identity metadata, NOT a safe durable transport checkpoint.
        return max((event.source_delivery_sequence for event in self._records
                    if event.available_at.key() <= cutoff.key()), default=0)
