"""Version-one data contracts. All times are synthetic match time, not UTC."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}$")]
PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class MatchTime(Contract):
    period: Literal[1, 2]
    elapsed_ms: NonNegativeInt

    def key(self) -> tuple[int, int]:
        return self.period, self.elapsed_ms


class InitialState(Contract):
    at: MatchTime
    score: dict[Identifier, NonNegativeInt]
    controlled_possession_team_id: Identifier


class PitchPosition(Contract):
    x: Annotated[float, Field(ge=0, le=105, allow_inf_nan=False)]
    y: Annotated[float, Field(ge=0, le=68, allow_inf_nan=False)]


class Actor(Contract):
    team_id: Identifier
    player_id: Identifier


class PassDetails(Contract):
    kind: Literal["pass"]
    outcome: Literal["completed", "incomplete"]
    end_position: PitchPosition
    recipient: Actor | None = None

    @model_validator(mode="after")
    def completed_has_recipient(self) -> Self:
        if self.outcome == "completed" and self.recipient is None:
            raise ValueError("completed pass requires a recipient")
        return self


class CarryDetails(Contract):
    kind: Literal["carry"]
    end_position: PitchPosition


class DuelDetails(Contract):
    kind: Literal["duel"]
    opponent: Actor
    outcome: Literal["won", "lost"]


class RecoveryDetails(Contract):
    kind: Literal["recovery"]
    from_team_id: Identifier
    control: Literal["established"]
    origin: Literal["open_play", "restart"]


Action = Annotated[
    PassDetails | CarryDetails | DuelDetails | RecoveryDetails,
    Field(discriminator="kind"),
]


class Event(Contract):
    schema_version: Literal["1.0"] = "1.0"
    match_id: Identifier
    event_id: Identifier
    revision: PositiveInt
    source_delivery_sequence: PositiveInt
    occurrence_order: NonNegativeInt
    occurred_at: MatchTime
    available_at: MatchTime
    actor: Actor
    position: PitchPosition
    action: Action

    @model_validator(mode="after")
    def coherent_event(self) -> Self:
        if self.available_at.key() < self.occurred_at.key():
            raise ValueError("availability cannot precede occurrence")
        if isinstance(self.action, PassDetails) and self.action.recipient:
            if self.action.recipient.team_id != self.actor.team_id:
                raise ValueError("pass recipient must belong to the actor's team")
            if self.action.recipient.player_id == self.actor.player_id:
                raise ValueError("a player cannot pass to themselves")
        if isinstance(self.action, DuelDetails):
            if self.action.opponent.team_id == self.actor.team_id:
                raise ValueError("duel opponent must belong to another team")
        if isinstance(self.action, RecoveryDetails):
            if self.action.from_team_id == self.actor.team_id:
                raise ValueError("recovery must change controlled possession")
        return self


class ObservationWindow(Contract):
    start: MatchTime
    end: MatchTime
    boundary: Literal["(start,end]"] = "(start,end]"

    @model_validator(mode="after")
    def increasing(self) -> Self:
        if self.start.key() >= self.end.key():
            raise ValueError("window end must follow start")
        return self

    def contains(self, time: MatchTime) -> bool:
        return self.start.key() < time.key() <= self.end.key()


class EventReference(Contract):
    event_id: Identifier
    revision: PositiveInt


class MatchState(Contract):
    match_id: Identifier
    at: MatchTime
    score: dict[Identifier, NonNegativeInt]
    controlled_possession_team_id: Identifier
    source_delivery_cursor: NonNegativeInt
    applied_events: tuple[EventReference, ...]


class WindowEvidence(Contract):
    window: ObservationWindow
    value: NonNegativeInt
    source_events: tuple[EventReference, ...]

    @model_validator(mode="after")
    def count_matches_references(self) -> Self:
        ids = [ref.event_id for ref in self.source_events]
        if len(set(ids)) != len(ids):
            raise ValueError("a window cannot count the same event twice")
        if self.value != len(ids):
            raise ValueError("count must equal the number of supporting events")
        return self


class EvidencePacket(Contract):
    schema_version: Literal["1.0"] = "1.0"
    evidence_id: Identifier
    evidence_version: PositiveInt
    match_id: Identifier
    subject_team_id: Identifier
    metric: Literal["high_recovery_count"]
    rule_version: Literal["high-recovery-v1"]
    cutoff: MatchTime
    baseline: WindowEvidence
    current: WindowEvidence
    claim_type: Literal["count_comparison"] = "count_comparison"

    @model_validator(mode="after")
    def coherent_comparison(self) -> Self:
        if self.baseline.window.end != self.current.window.start:
            raise ValueError("comparison windows must be adjacent")
        if self.current.window.end.key() > self.cutoff.key():
            raise ValueError("window cannot extend beyond the evidence cutoff")
        baseline_ids = {ref.event_id for ref in self.baseline.source_events}
        if baseline_ids.intersection(ref.event_id for ref in self.current.source_events):
            raise ValueError("an event cannot support both comparison windows")
        return self


class RecoveryFacts(Contract):
    subject_team_id: Identifier
    baseline_count: NonNegativeInt
    current_count: NonNegativeInt
    baseline_window: ObservationWindow
    current_window: ObservationWindow


class Insight(Contract):
    insight_id: Identifier
    revision: PositiveInt
    evidence_id: Identifier
    evidence_version: PositiveInt
    claim_type: Literal["fact"] = "fact"
    template: Literal["high_recovery_increase_v1"] = "high_recovery_increase_v1"
    title: str
    explanation: str
    facts: RecoveryFacts
    eligible_at: MatchTime
