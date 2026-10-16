from typing import Literal, Self
from pydantic import Field, model_validator
from counterpress.domain.models import Contract, Event, Identifier, MatchTime, NonNegativeInt, PositiveInt
from counterpress.api.snapshots import horizon
from counterpress.history import History

MAX_DELIVERY_BYTES = 240_000

class Delivery(Contract):
    schema_version: Literal[1] = 1
    delivery_id: Identifier
    scenario_id: Identifier
    match_id: Identifier
    events: tuple[Event, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode='after')
    def one_match(self) -> Self:
        if any(event.match_id != self.match_id for event in self.events):
            raise ValueError('delivery must contain only its declared match')
        return self

class Revision(Contract):
    kind: Literal['recovery', 'pressure', 'contribution']
    insight_id: Identifier
    revision: PositiveInt
    operation: Literal['create', 'update', 'withdraw']
    available_at: MatchTime

class RevisionNotice(Contract):
    type: Literal['history.changed'] = 'history.changed'
    schema_version: Literal[1] = 1
    scenario_id: Identifier
    match_id: Identifier
    history_version: NonNegativeInt
    replay_end: MatchTime
    revisions: tuple[Revision, ...]


def notice(scenario: str, history: History) -> RevisionNotice:
    latest = {}
    for kind, changes in [('recovery', history.changes), ('pressure', history.pressure_changes),
                          ('contribution', history.contribution_changes)]:
        for change in changes:
            latest[kind, change.insight_id] = Revision(kind=kind, insight_id=change.insight_id,
                revision=change.revision, operation=change.operation, available_at=change.available_at)
    return RevisionNotice(scenario_id=scenario, match_id=history.fixture.match_id,
        history_version=len(history.records), replay_end=horizon(history), revisions=tuple(latest.values()))
