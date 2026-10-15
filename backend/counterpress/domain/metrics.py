"""Deterministic event metrics, with no expected-results files or model calls."""

from math import fsum, hypot

from counterpress.domain.models import (
    Contract, Event, EventReference, Identifier, MatchTime, NonNegativeInt,
    ObservationWindow, PassDetails, RecoveryDetails, WindowEvidence,
)


class TeamMetrics(Contract):
    team_id: Identifier
    pass_attempts: NonNegativeInt
    pass_completions: NonNegativeInt
    attempted_pass_distance_m: float
    completed_pass_distance_m: float
    high_recoveries: tuple[EventReference, ...]


def is_high_recovery(event: Event, team_id: str) -> bool:
    return (
        event.actor.team_id == team_id
        and isinstance(event.action, RecoveryDetails)
        and event.action.origin == "open_play"
        and event.position.x >= 70
    )


def team_metrics(events: tuple[Event, ...], team_id: str) -> TeamMetrics:
    """Input is canonical, possession-validated state; distance is endpoint distance."""
    passes = [event for event in events if event.actor.team_id == team_id
              and isinstance(event.action, PassDetails)]
    completed = [event for event in passes if event.action.outcome == "completed"]

    def distance(event: Event) -> float:
        return hypot(event.action.end_position.x - event.position.x,
                     event.action.end_position.y - event.position.y)

    return TeamMetrics(
        team_id=team_id, pass_attempts=len(passes), pass_completions=len(completed),
        attempted_pass_distance_m=fsum(distance(event) for event in passes),
        completed_pass_distance_m=fsum(distance(event) for event in completed),
        high_recoveries=tuple(EventReference(event_id=event.event_id, revision=event.revision)
                              for event in events if is_high_recovery(event, team_id)),
    )


class RecoveryComparison(Contract):
    subject_team_id: Identifier
    cutoff: MatchTime
    baseline: WindowEvidence
    current: WindowEvidence

    @property
    def increased(self) -> bool:
        return self.current.value > self.baseline.value


def compare_recoveries(
    events: tuple[Event, ...], team_id: str, baseline: ObservationWindow,
    current: ObservationWindow, cutoff: MatchTime,
) -> RecoveryComparison:
    """Compare completed observation windows after canonical revision selection."""
    if baseline.end != current.start:
        raise ValueError("comparison windows must be adjacent")
    if current.end.key() > cutoff.key():
        raise ValueError("comparison is not ready: current window has not ended")
    if any(event.available_at.key() > cutoff.key() or event.occurred_at.key() > cutoff.key() for event in events):
        raise ValueError("comparison input contains future events")

    def observation(window: ObservationWindow) -> WindowEvidence:
        refs = tuple(EventReference(event_id=event.event_id, revision=event.revision)
                     for event in events if is_high_recovery(event, team_id) and window.contains(event.occurred_at))
        return WindowEvidence(window=window, value=len(refs), source_events=refs)

    return RecoveryComparison(subject_team_id=team_id, cutoff=cutoff,
                              baseline=observation(baseline), current=observation(current))
