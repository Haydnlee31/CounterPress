"""Observed build-up episodes and duel-based pressure proxies; no simulator labels."""

from hashlib import sha256
from typing import Literal, Self

from pydantic import Field, model_validator

from counterpress.domain.models import (
    Contract, Event, EventReference, Identifier, MatchTime, NonNegativeInt,
    ObservationWindow,
)
from counterpress.replay import ReplaySession


class PressurePolicy(Contract):
    minimum_episodes: int = Field(default=3, ge=1)
    minimum_rate_change: float = Field(default=0.25, gt=0, le=1, allow_inf_nan=False)
    cooldown_ms: int = Field(default=60000, ge=0)


class BuildUpEpisode(Contract):
    episode_id: Identifier
    start: MatchTime
    end: MatchTime | None
    observed_start: bool
    outcome: Literal["escape", "turnover", "restart", "pending"]
    pressure_events: tuple[EventReference, ...]
    source_events: tuple[EventReference, ...]

    @model_validator(mode="after")
    def coherent_episode(self) -> Self:
        if (self.outcome == "pending") != (self.end is None):
            raise ValueError("only pending episodes have no resolution time")
        if self.end is not None and self.end.key() < self.start.key():
            raise ValueError("episode resolution cannot precede its start")
        ids = [ref.event_id for ref in self.source_events]
        if not ids or ids[0] != self.episode_id or len(ids) != len(set(ids)):
            raise ValueError("episode identity must be its first unique source event")
        if not set(self.pressure_events).issubset(self.source_events):
            raise ValueError("pressure references must belong to episode evidence")
        return self


class EpisodeWindow(Contract):
    window: ObservationWindow
    included: tuple[Identifier, ...]
    boundary_excluded: tuple[Identifier, ...]
    left_censored: tuple[Identifier, ...]
    pending: tuple[Identifier, ...]
    completed: NonNegativeInt
    exposed: NonNegativeInt
    escaped_under_pressure: NonNegativeInt
    exposure_rate: float | None
    pressured_escape_rate: float | None

    @model_validator(mode="after")
    def coherent_counts(self) -> Self:
        identities = (*self.included, *self.boundary_excluded, *self.left_censored, *self.pending)
        if len(identities) != len(set(identities)):
            raise ValueError("window episode categories must be disjoint")
        if self.completed != len(self.included) or not self.escaped_under_pressure <= self.exposed <= self.completed:
            raise ValueError("episode counts must agree with the sample")
        exposure = self.exposed / self.completed if self.completed else None
        escape = self.escaped_under_pressure / self.exposed if self.exposed else None
        if self.exposure_rate != exposure or self.pressured_escape_rate != escape:
            raise ValueError("rates must equal their disclosed fractions")
        return self


Metric = Literal["pressure_exposure", "pressured_escape", "possession_without_progression"]


class Publication(Contract):
    """Caller-owned cooldown receipt. Same-window corrections bypass the cooldown."""

    match_id: Identifier
    team_id: Identifier
    metric: Metric
    baseline: ObservationWindow
    current: ObservationWindow
    published_at: MatchTime

    @model_validator(mode="after")
    def completed_comparison(self) -> Self:
        if self.baseline.end != self.current.start or self.current.end.key() > self.published_at.key():
            raise ValueError("publication requires adjacent completed windows")
        return self


class RateDecision(Contract):
    metric: Metric
    status: Literal["eligible", "insufficient_sample", "below_threshold", "cooldown"]
    direction: Literal["increase", "decrease", "unchanged"]
    baseline_numerator: NonNegativeInt
    baseline_denominator: NonNegativeInt
    current_numerator: NonNegativeInt
    current_denominator: NonNegativeInt
    change: float | None


class PressureEvidence(Contract):
    rule_version: Literal["observed-build-up-v1"] = "observed-build-up-v1"
    match_id: Identifier
    subject_team_id: Identifier
    cutoff: MatchTime
    coverage_start: MatchTime
    policy: PressurePolicy
    baseline: EpisodeWindow
    current: EpisodeWindow
    episodes: tuple[BuildUpEpisode, ...]
    records: tuple[Event, ...]
    decisions: tuple[RateDecision, ...]
    disclosure: str = (
        "Pressure exposure is a defensive-third duel proxy, not tracking-measured pressure. "
        "Escape means observed controlled progression beyond x=35 m. "
        "Rates describe fully observed episodes, not causal tactical effectiveness."
    )

    @model_validator(mode="after")
    def coherent_sources(self) -> Self:
        if self.baseline.window.end != self.current.window.start or self.current.window.end.key() > self.cutoff.key():
            raise ValueError("evidence requires adjacent completed windows")
        records = {ref(event): event for event in self.records}
        if len({event.event_id for event in self.records}) != len(self.records):
            raise ValueError("evidence requires one canonical revision per event")
        if any(event.match_id != self.match_id or event.available_at.key() > self.cutoff.key()
               or event.occurred_at.key() > self.cutoff.key() for event in self.records):
            raise ValueError("evidence contains a foreign or future source event")
        if len({episode.episode_id for episode in self.episodes}) != len(self.episodes):
            raise ValueError("episode identities must be unique")
        for episode in self.episodes:
            if any(source not in records for source in episode.source_events):
                raise ValueError("episode source revision is missing")
            if records[episode.source_events[0]].occurred_at != episode.start:
                raise ValueError("episode start must match its source time")
            if episode.end is not None and records[episode.source_events[-1]].occurred_at != episode.end:
                raise ValueError("episode end must match its resolution source time")
        for summary in (self.baseline, self.current):
            if summarize(self.episodes, summary.window) != summary:
                raise ValueError("window summary must agree with episode evidence")
        return self

    @property
    def fingerprint(self) -> str:
        """Content identity changes with source revisions, boundaries or policy."""
        return sha256(self.model_dump_json().encode()).hexdigest()


def ref(event: Event) -> EventReference:
    return EventReference(event_id=event.event_id, revision=event.revision)


def build_up_episodes(events: tuple[Event, ...], team_id: str, initial_control: str) -> tuple[BuildUpEpisode, ...]:
    """Read canonical, possession-validated events from one period in occurrence order.

    A recovery inside x<=35 or a controlled re-entry from x>35 is an observed
    beginning. First sightings already inside are left-censored. A won duel is
    exposure, not escape; incomplete passes/lost duels await observed resolution.
    """
    episodes = []
    active = None
    control = initial_control

    def start(event, observed):
        return dict(episode_id=event.event_id, start=event.occurred_at,
                    end=None, observed_start=observed, outcome="pending",
                    pressure_events=[], source_events=[])

    def finish(event, outcome):
        nonlocal active
        active["end"], active["outcome"] = event.occurred_at, outcome
        active["source_events"] = tuple(active["source_events"])
        active["pressure_events"] = tuple(active["pressure_events"])
        episodes.append(BuildUpEpisode(**active))
        active = None

    for event in events:
        action = event.action
        own = event.actor.team_id == team_id
        if action.kind == "recovery":
            control = event.actor.team_id
        if active is not None:
            active["source_events"].append(ref(event))
            if action.kind == "recovery" and not own:
                finish(event, "restart" if action.origin == "restart" else "turnover")
                continue
        if not own:
            # Duels can be recorded from the challenger perspective. This is
            # exposure only if an existing subject possession episode is active.
            if active is not None and action.kind == "duel" and action.opponent.team_id == team_id and event.position.x >= 70:
                active["pressure_events"].append(ref(event))
            continue
        if control != team_id:
            continue  # A subject-team challenger is not the team building out.
        controlled_end = action.kind == "carry" or (action.kind == "pass" and action.outcome == "completed")
        entry = controlled_end and event.position.x > 35 and action.end_position.x <= 35
        if active is None:
            if action.kind == "recovery" and event.position.x <= 35:
                active = start(event, True)
            elif entry:
                active = start(event, True)
            elif event.position.x <= 35:
                active = start(event, False)
            if active is not None:
                active["source_events"].append(ref(event))
        if active is None:
            continue
        if action.kind == "duel" and event.position.x <= 35:
            active["pressure_events"].append(ref(event))
        if controlled_end and action.end_position.x > 35:
            finish(event, "escape")
    if active is not None:
        active["source_events"] = tuple(active["source_events"])
        active["pressure_events"] = tuple(active["pressure_events"])
        episodes.append(BuildUpEpisode(**active))
    return tuple(episodes)


def summarize(episodes: tuple[BuildUpEpisode, ...], window: ObservationWindow) -> EpisodeWindow:
    included, boundary, censored, pending = [], [], [], []
    for episode in episodes:
        if episode.start.key() > window.end.key() or (episode.end is not None and episode.end.key() <= window.start.key()):
            continue
        if not episode.observed_start:
            censored.append(episode.episode_id)
        elif episode.end is None or episode.end.key() > window.end.key():
            pending.append(episode.episode_id)
        elif not window.contains(episode.start):
            boundary.append(episode.episode_id)
        else:
            included.append(episode)
    exposed = sum(bool(episode.pressure_events) for episode in included)
    escaped = sum(bool(episode.pressure_events) and episode.outcome == "escape" for episode in included)
    return EpisodeWindow(window=window, included=tuple(episode.episode_id for episode in included),
        boundary_excluded=tuple(boundary), left_censored=tuple(censored), pending=tuple(pending),
        completed=len(included), exposed=exposed, escaped_under_pressure=escaped,
        exposure_rate=exposed / len(included) if included else None,
        pressured_escape_rate=escaped / exposed if exposed else None)


def analyze_pressure(
    session: ReplaySession, team_id: str, baseline: ObservationWindow,
    current: ObservationWindow, cutoff: MatchTime, *, policy: PressurePolicy | None = None,
    publications: tuple[Publication, ...] = (),
) -> PressureEvidence:
    """Rebuild evidence at cutoff, including corrections, without evaluator data."""
    policy = policy or PressurePolicy()
    if team_id not in session.fixture.initial_state.score:
        raise ValueError("unknown subject team")
    if baseline.end != current.start:
        raise ValueError("comparison windows must be adjacent")
    times = (session.clock.start, baseline.start, baseline.end, current.end, cutoff)
    if len({time.period for time in times}) != 1:
        raise ValueError("build-up analysis requires history and windows within one period")
    if baseline.start.key() < session.clock.start.key():
        raise ValueError("comparison begins before observed history")
    if current.end.key() > cutoff.key():
        raise ValueError("comparison is not ready: current window has not ended")
    snapshot = session.snapshot(cutoff)
    episodes = build_up_episodes(snapshot.events, team_id, session.fixture.initial_state.controlled_possession_team_id)
    before, after = summarize(episodes, baseline), summarize(episodes, current)
    decisions = []
    for metric in ("pressure_exposure", "pressured_escape"):
        bnum, bden, cnum, cden = ((before.exposed, before.completed, after.exposed, after.completed)
            if metric == "pressure_exposure" else
            (before.escaped_under_pressure, before.exposed, after.escaped_under_pressure, after.exposed))
        change = cnum / cden - bnum / bden if bden and cden else None
        direction = "unchanged" if change is None or change == 0 else "increase" if change > 0 else "decrease"
        if min(bden, cden) < policy.minimum_episodes:
            status = "insufficient_sample"
        elif abs(change) + 1e-12 < policy.minimum_rate_change:
            status = "below_threshold"
        else:
            status = "eligible"
            for publication in publications:
                if (publication.match_id, publication.team_id, publication.metric) != (session.fixture.match_id, team_id, metric):
                    continue
                if publication.published_at.period != cutoff.period or publication.published_at.key() > cutoff.key():
                    continue  # A future receipt must not leak into historical replay.
                if publication.baseline == baseline and publication.current == current:
                    continue  # A correction refresh is never suppressed by story cooldown.
                if cutoff.elapsed_ms - publication.published_at.elapsed_ms < policy.cooldown_ms:
                    status = "cooldown"
                    break
        decisions.append(RateDecision(metric=metric, status=status, direction=direction,
            baseline_numerator=bnum, baseline_denominator=bden, current_numerator=cnum,
            current_denominator=cden, change=change))
    return PressureEvidence(match_id=session.fixture.match_id, subject_team_id=team_id,
        cutoff=cutoff, coverage_start=session.clock.start, policy=policy, baseline=before,
        current=after, episodes=episodes, records=snapshot.events, decisions=tuple(decisions))
