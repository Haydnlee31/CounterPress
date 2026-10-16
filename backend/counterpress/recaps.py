"""Bounded factual recaps of current ledger publications, never raw model prose."""

from typing import Literal

from pydantic import Field, model_validator

from counterpress.audience import AudienceView, NarrativeVariant, ViewingPreferences
from counterpress.contribution_views import contribution_view
from counterpress.domain.models import Contract, Identifier, MatchTime, ObservationWindow, PositiveInt
from counterpress.history import History
from counterpress.pressure_views import pressure_view


class RecapCitation(Contract):
    kind: Literal['recovery', 'pressure', 'contribution']
    insight_id: Identifier
    revision: PositiveInt
    evidence_id: Identifier
    available_at: MatchTime


class RecapStatement(Contract):
    narrative: NarrativeVariant
    citation: RecapCitation

    @model_validator(mode='after')
    def same_publication(self):
        if (self.narrative.insight_id, self.narrative.revision) != (self.citation.insight_id, self.citation.revision):
            raise ValueError('recap wording and citation must name the same publication')
        return self


class SegmentRecap(Contract):
    match_id: Identifier
    cutoff: MatchTime
    windows: tuple[ObservationWindow, ObservationWindow]
    preferences: ViewingPreferences
    state: Literal['ready', 'collecting', 'no_eligible', 'budget_hidden']
    statements: tuple[RecapStatement, ...] = Field(default=(), max_length=4)
    omitted_count: int = Field(default=0, ge=0)

    @model_validator(mode='after')
    def consistent_release(self):
        if (self.state == 'ready') != bool(self.statements):
            raise ValueError('only ready recaps contain statements')
        if self.state != 'ready' and self.omitted_count:
            raise ValueError('empty recaps cannot omit eligible statements')
        if self.statements and (self.cutoff.key() < self.windows[1].end.key() or self.preferences.card_budget == 0):
            raise ValueError('recap requires completed windows and a visible budget')
        identities = set()
        for item in self.statements:
            c, n = item.citation, item.narrative
            if c.available_at.key() > self.cutoff.key():
                raise ValueError('recap cannot cite future publications')
            if c.insight_id in identities:
                raise ValueError('recap cannot repeat a publication')
            identities.add(c.insight_id)
            if (n.language, n.depth, n.club_id, n.player_id) != (
                    self.preferences.language, self.preferences.depth, self.preferences.club_id, self.preferences.player_id):
                raise ValueError('recap must use the requested perspective')
        return self


def build_recap(history: History, cutoff: MatchTime, windows, prefs: ViewingPreferences,
                audience: AudienceView) -> SegmentRecap:
    """Select latest revisions before filtering withdrawals; use one immutable read.

    Club and metric preferences rank; player preferences require actual recorded
    involvement (and actual attribution for player contribution stories).
    """
    common = dict(match_id=history.fixture.match_id, cutoff=cutoff, windows=windows, preferences=prefs)
    if prefs.card_budget == 0:
        return SegmentRecap(**common, state='budget_hidden')
    if cutoff.key() < windows[1].end.key():
        return SegmentRecap(**common, state='collecting')
    candidates = []

    def add(kind, change, view, evidence_id):
        if view.state != 'ready' or view.variant is None:
            return
        statement = RecapStatement(narrative=view.variant, citation=RecapCitation(
            kind=kind, insight_id=change.insight_id, revision=change.revision,
            evidence_id=evidence_id, available_at=change.available_at))
        candidates.append((view.priority, {'recovery': 0, 'pressure': 1, 'contribution': 2}[kind], statement))

    recovery = next((c for c in reversed(history.changes) if c.available_at.key() <= cutoff.key()), None)
    if recovery and recovery.operation != 'withdraw':
        add('recovery', recovery, audience, recovery.evidence.packet.evidence_id)
    for kind, stream, render in [('pressure', history.pressure_changes, pressure_view),
                                 ('contribution', history.contribution_changes, contribution_view)]:
        latest = {}
        for change in stream:
            if change.available_at.key() <= cutoff.key():
                latest[change.insight_id] = change
        for change in latest.values():
            if change.operation != 'withdraw':
                add(kind, change, render(history, (change,), prefs, False), change.evidence_id)
    statements = tuple(item[2] for item in sorted(candidates, key=lambda item: (
        -item[0], item[1], item[2].citation.insight_id)))
    return SegmentRecap(**common, state='ready' if statements else 'no_eligible',
                        statements=statements[:4], omitted_count=max(0, len(statements)-4))
