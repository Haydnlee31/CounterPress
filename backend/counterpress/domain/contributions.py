"""Attribute recorded high recoveries to their actors, never to nearby participants."""

from typing import Literal, Self

from pydantic import Field, model_validator

from counterpress.domain.metrics import is_high_recovery
from counterpress.domain.models import (
    Contract, Event, EventReference, Identifier, MatchTime, ObservationWindow,
)
from counterpress.replay import ReplaySession


class ContributionPolicy(Contract):
    minimum_team_recoveries: int = Field(default=3, ge=1)
    minimum_current_player_recoveries: int = Field(default=3, ge=1)
    minimum_count_increase: int = Field(default=2, ge=1)
    minimum_share_increase: float = Field(default=0.25, gt=0, le=1, allow_inf_nan=False)


class ContributionWindow(Contract):
    window: ObservationWindow
    team_events: tuple[EventReference, ...]
    player_events: tuple[EventReference, ...]
    team_count: int = Field(ge=0)
    player_count: int = Field(ge=0)
    share: float | None = Field(ge=0, le=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if len({ref.event_id for ref in self.team_events}) != len(self.team_events):
            raise ValueError("team recoveries must be unique")
        if len(set(self.player_events)) != len(self.player_events) or not set(self.player_events).issubset(self.team_events):
            raise ValueError("player recoveries must be a unique subset of team recoveries")
        if self.team_count != len(self.team_events) or self.player_count != len(self.player_events):
            raise ValueError("counts must match source references")
        expected = self.player_count / self.team_count if self.team_count else None
        if self.share != expected:
            raise ValueError("share must agree with the disclosed fraction")
        return self


def summarize_contribution(events, team_id, player_id, window):
    team = tuple(EventReference(event_id=e.event_id, revision=e.revision) for e in events
                 if is_high_recovery(e, team_id) and window.contains(e.occurred_at))
    player = tuple(EventReference(event_id=e.event_id, revision=e.revision) for e in events
                   if is_high_recovery(e, team_id) and window.contains(e.occurred_at)
                   and e.actor.player_id == player_id)
    return ContributionWindow(window=window, team_events=team, player_events=player,
        team_count=len(team), player_count=len(player), share=len(player)/len(team) if team else None)


class ContributionDecision(Contract):
    status: Literal["eligible", "insufficient_sample", "below_threshold"]
    count_change: int
    share_change: float | None = Field(ge=-1, le=1, allow_inf_nan=False)


def contribution_decision(before, after, policy):
    count_change = after.player_count - before.player_count
    share_change = after.share-before.share if before.share is not None and after.share is not None else None
    if min(before.team_count, after.team_count) < policy.minimum_team_recoveries:
        status = "insufficient_sample"
    elif (after.player_count >= policy.minimum_current_player_recoveries
          and count_change >= policy.minimum_count_increase
          and share_change + 1e-12 >= policy.minimum_share_increase):
        status = "eligible"
    else:
        status = "below_threshold"
    return ContributionDecision(status=status, count_change=count_change, share_change=share_change)


class PlayerContributionEvidence(Contract):
    rule_version: Literal["player-high-recoveries-v1"] = "player-high-recoveries-v1"
    metric: Literal["player_high_recovery_share"] = "player_high_recovery_share"
    match_id: Identifier
    subject_team_id: Identifier
    subject_player_id: Identifier
    cutoff: MatchTime
    coverage_start: MatchTime
    policy: ContributionPolicy
    baseline: ContributionWindow
    current: ContributionWindow
    records: tuple[Event, ...]
    decision: ContributionDecision
    disclosure: Literal[
        "Recorded open-play high recoveries attributed only to the recovering actor. "
        "Shares are not a player rating, per-minute rate, or evidence of tactical causality."
    ] = ("Recorded open-play high recoveries attributed only to the recovering actor. "
         "Shares are not a player rating, per-minute rate, or evidence of tactical causality.")

    @model_validator(mode="after")
    def coherent(self) -> Self:
        bw, cw = self.baseline.window, self.current.window
        times = (self.coverage_start, bw.start, bw.end, cw.start, cw.end, self.cutoff)
        if len({t.period for t in times}) != 1 or bw.end != cw.start:
            raise ValueError("contribution windows must be adjacent in one period")
        if bw.start.key() < self.coverage_start.key() or cw.end.key() > self.cutoff.key():
            raise ValueError("comparison requires covered, completed windows")
        if bw.end.elapsed_ms-bw.start.elapsed_ms != cw.end.elapsed_ms-cw.start.elapsed_ms:
            raise ValueError("raw contribution counts require equal-duration windows")
        if len({e.event_id for e in self.records}) != len(self.records):
            raise ValueError("evidence requires one canonical revision per event")
        if any(e.match_id != self.match_id or e.available_at.key() > self.cutoff.key()
               or e.occurred_at.key() > self.cutoff.key() for e in self.records):
            raise ValueError("evidence requires same-match records available at cutoff")
        keys = [(*e.occurred_at.key(), e.occurrence_order) for e in self.records]
        if keys != sorted(keys):
            raise ValueError("evidence records must be in occurrence order")
        for summary in (self.baseline, self.current):
            if summary != summarize_contribution(self.records, self.subject_team_id, self.subject_player_id, summary.window):
                raise ValueError("attribution must agree with exact source actors and windows")
        if self.decision != contribution_decision(self.baseline, self.current, self.policy):
            raise ValueError("decision must agree with counts, shares and policy")
        return self


def analyze_contributions(session: ReplaySession, team_id: str, player_id: str,
                          baseline: ObservationWindow, current: ObservationWindow,
                          cutoff: MatchTime, *, policy: ContributionPolicy | None = None):
    roster = {team.team_id: team.player_ids for team in session.fixture.teams}
    if player_id not in roster.get(team_id, ()):
        raise ValueError("player must belong to the subject team")
    policy = policy or ContributionPolicy()
    events = session.snapshot(cutoff).events
    before, after = (summarize_contribution(events, team_id, player_id, window) for window in (baseline, current))
    return PlayerContributionEvidence(match_id=session.fixture.match_id,
        subject_team_id=team_id, subject_player_id=player_id, cutoff=cutoff,
        coverage_start=session.clock.start, policy=policy, baseline=before, current=after,
        records=events, decision=contribution_decision(before, after, policy))
