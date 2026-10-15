"""Sustained possession without observed forward gain, using public events only."""

from typing import Literal, Self

from pydantic import Field, model_validator

from counterpress.domain.models import Contract, Event, EventReference, Identifier, MatchTime, ObservationWindow
from counterpress.domain.pressure import PressurePolicy, RateDecision, ref
from counterpress.replay import ReplaySession


class ProgressionPolicy(PressurePolicy):
    minimum_controlled_span_ms: int = Field(default=20000, ge=0)
    minimum_completed_actions: int = Field(default=3, ge=1)
    forward_gain_m: float = Field(default=15.0, gt=0, le=105, allow_inf_nan=False)


class PossessionEpisode(Contract):
    episode_id: Identifier
    start: MatchTime
    end: MatchTime | None
    observed_start: bool
    start_x: float = Field(ge=0, le=105, allow_inf_nan=False)
    maximum_x: float = Field(ge=0, le=105, allow_inf_nan=False)
    forward_gain_m: float = Field(ge=0, le=105, allow_inf_nan=False)
    completed_actions: int = Field(ge=0)
    controlled_span_ms: int = Field(ge=0)
    outcome: Literal["turnover", "restart", "pending"]
    source_events: tuple[EventReference, ...]

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (self.end is None) != (self.outcome == "pending"):
            raise ValueError("only unfinished possessions are pending")
        if self.end and (self.end.period != self.start.period or self.end.elapsed_ms < self.start.elapsed_ms + self.controlled_span_ms):
            raise ValueError("controlled span must fit inside the episode")
        if self.maximum_x < self.start_x or abs(self.forward_gain_m - (self.maximum_x-self.start_x)) > 1e-9:
            raise ValueError("forward gain must agree with maximum controlled x")
        ids = [item.event_id for item in self.source_events]
        if not ids or ids[0] != self.episode_id or len(ids) != len(set(ids)):
            raise ValueError("episode identity must be its first unique source event")
        return self


class ProgressionWindow(Contract):
    window: ObservationWindow
    included: tuple[Identifier, ...]
    without_progression: tuple[Identifier, ...]
    boundary_excluded: tuple[Identifier, ...]
    left_censored: tuple[Identifier, ...]
    pending: tuple[Identifier, ...]
    brief_excluded: tuple[Identifier, ...]
    limited_space: tuple[Identifier, ...]
    completed: int = Field(ge=0)
    without_progression_count: int = Field(ge=0)
    rate: float | None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        ids = (*self.included, *self.boundary_excluded, *self.left_censored, *self.pending, *self.brief_excluded, *self.limited_space)
        if len(ids) != len(set(ids)) or not set(self.without_progression).issubset(self.included):
            raise ValueError("episode categories must be disjoint and numerator must be included")
        if self.completed != len(self.included) or self.without_progression_count != len(set(self.without_progression)) or len(self.without_progression) != len(set(self.without_progression)):
            raise ValueError("counts must match episode identities")
        expected = self.without_progression_count / self.completed if self.completed else None
        if self.rate != expected:
            raise ValueError("rate must agree with its disclosed fraction")
        return self


def possession_episodes(events, team_id, initial_control):
    episodes, active = [], None
    control = initial_control
    for event in events:
        action, own = event.action, event.actor.team_id == team_id
        if action.kind == "recovery":
            control = event.actor.team_id
        if active:
            active["source_events"].append(ref(event))
            if action.kind == "recovery" and not own:
                active.update(end=event.occurred_at, outcome="restart" if action.origin == "restart" else "turnover")
                active["source_events"] = tuple(active["source_events"])
                episodes.append(PossessionEpisode(**active))
                active = None
                continue
        if not own or control != team_id:
            continue
        if active is None:
            active = dict(episode_id=event.event_id, start=event.occurred_at, end=None,
                observed_start=action.kind == "recovery", start_x=event.position.x,
                maximum_x=event.position.x, forward_gain_m=0.0, completed_actions=0,
                controlled_span_ms=0, outcome="pending", source_events=[ref(event)])
        # A recorded holder's release position is observed control. An incomplete
        # pass endpoint is not; it must never manufacture progression.
        active["maximum_x"] = max(active["maximum_x"], event.position.x)
        completed = action.kind == "pass" and action.outcome == "completed"
        completed |= action.kind == "carry" and action.end_position != event.position
        if completed:
            active["completed_actions"] += 1
            active["maximum_x"] = max(active["maximum_x"], action.end_position.x)
            active["controlled_span_ms"] = event.occurred_at.elapsed_ms-active["start"].elapsed_ms
        active["forward_gain_m"] = round(active["maximum_x"]-active["start_x"], 9)
    if active:
        active["source_events"] = tuple(active["source_events"])
        episodes.append(PossessionEpisode(**active))
    return tuple(episodes)


def summarize_progression(episodes, window, policy):
    categories = {key: [] for key in ("included", "without_progression", "boundary_excluded", "left_censored", "pending", "brief_excluded", "limited_space")}
    for episode in episodes:
        if episode.start.key() > window.end.key() or (episode.end and episode.end.key() <= window.start.key()):
            continue
        if not episode.observed_start:
            category = "left_censored"
        elif episode.end is None or episode.end.key() > window.end.key():
            category = "pending"
        elif not window.contains(episode.start):
            category = "boundary_excluded"
        elif episode.start_x > 105-policy.forward_gain_m:
            category = "limited_space"
        elif episode.completed_actions < policy.minimum_completed_actions or episode.controlled_span_ms < policy.minimum_controlled_span_ms:
            category = "brief_excluded"
        else:
            category = "included"
            if episode.forward_gain_m < policy.forward_gain_m:
                categories["without_progression"].append(episode.episode_id)
        categories[category].append(episode.episode_id)
    denominator, numerator = len(categories["included"]), len(categories["without_progression"])
    return ProgressionWindow(window=window, **{key:tuple(value) for key,value in categories.items()},
        completed=denominator, without_progression_count=numerator, rate=numerator/denominator if denominator else None)


class ProgressionEvidence(Contract):
    rule_version: Literal["sustained-possession-v1"] = "sustained-possession-v1"
    match_id: Identifier
    subject_team_id: Identifier
    cutoff: MatchTime
    coverage_start: MatchTime
    policy: ProgressionPolicy
    baseline: ProgressionWindow
    current: ProgressionWindow
    episodes: tuple[PossessionEpisode, ...]
    records: tuple[Event, ...]
    decisions: tuple[RateDecision, ...]
    disclosure: str = "Sustained possessions without 15 m of observed forward gain; this is a spatial proxy, not possession dominance, passing quality or tactical value."

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.baseline.window.end != self.current.window.start or self.current.window.end.key() > self.cutoff.key():
            raise ValueError("evidence requires adjacent completed windows")
        by_ref = {ref(event):event for event in self.records}
        if len({event.event_id for event in self.records}) != len(self.records) or any(event.match_id != self.match_id or event.available_at.key() > self.cutoff.key() or event.occurred_at.key() > self.cutoff.key() for event in self.records):
            raise ValueError("evidence requires canonical same-match records within cutoff")
        if len({episode.episode_id for episode in self.episodes}) != len(self.episodes):
            raise ValueError("episode identities must be unique")
        for episode in self.episodes:
            if any(source not in by_ref for source in episode.source_events):
                raise ValueError("missing source revision")
            if by_ref[episode.source_events[0]].occurred_at != episode.start or (episode.end and by_ref[episode.source_events[-1]].occurred_at != episode.end):
                raise ValueError("episode times must match source references")
        for summary in (self.baseline, self.current):
            if summary != summarize_progression(self.episodes, summary.window, self.policy):
                raise ValueError("summary must agree with episodes")
        return self


def analyze_progression(session: ReplaySession, team_id: str, baseline: ObservationWindow,
                        current: ObservationWindow, cutoff: MatchTime, *, policy=None, publications=()):
    policy = policy or ProgressionPolicy()
    if team_id not in session.fixture.initial_state.score:
        raise ValueError("unknown subject team")
    if baseline.end != current.start or baseline.start.key() < session.clock.start.key():
        raise ValueError("windows must be adjacent and covered by observed history")
    if len({t.period for t in (session.clock.start, baseline.start, baseline.end, current.end, cutoff)}) != 1:
        raise ValueError("possession analysis requires one period")
    if current.end.key() > cutoff.key():
        raise ValueError("comparison is not ready")
    snapshot = session.snapshot(cutoff)
    episodes = possession_episodes(snapshot.events, team_id, session.fixture.initial_state.controlled_possession_team_id)
    before, after = (summarize_progression(episodes, window, policy) for window in (baseline,current))
    change = after.rate-before.rate if before.rate is not None and after.rate is not None else None
    status = "insufficient_sample" if min(before.completed,after.completed) < policy.minimum_episodes else "below_threshold" if abs(change)+1e-12 < policy.minimum_rate_change else "eligible"
    if status == "eligible":
        for receipt in publications:
            if (receipt.match_id,receipt.team_id,receipt.metric) != (session.fixture.match_id,team_id,"possession_without_progression"):
                continue
            if receipt.published_at.period != cutoff.period or receipt.published_at.key() > cutoff.key():
                continue
            if receipt.baseline == baseline and receipt.current == current:
                continue
            if cutoff.elapsed_ms-receipt.published_at.elapsed_ms < policy.cooldown_ms:
                status = "cooldown"
                break
    decision = RateDecision(metric="possession_without_progression",status=status,
        direction="unchanged" if change is None or change == 0 else "increase" if change > 0 else "decrease",
        baseline_numerator=before.without_progression_count,baseline_denominator=before.completed,
        current_numerator=after.without_progression_count,current_denominator=after.completed,change=change)
    return ProgressionEvidence(match_id=session.fixture.match_id,subject_team_id=team_id,cutoff=cutoff,
        coverage_start=session.clock.start,policy=policy,baseline=before,current=after,episodes=episodes,
        records=snapshot.events,decisions=(decision,),disclosure=f"Sustained possessions without {policy.forward_gain_m:g} m of observed forward gain; a spatial proxy, not possession dominance, passing quality or tactical value.")
