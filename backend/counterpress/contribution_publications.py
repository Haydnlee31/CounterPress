"""Stable per-player publication streams over immutable contribution evidence."""

from hashlib import sha256
from typing import Literal, Self

from pydantic import model_validator

from counterpress.domain.contributions import PlayerContributionEvidence, analyze_contributions
from counterpress.domain.models import Contract, Identifier, MatchTime, PositiveInt

COOLDOWN_MS = 60_000


class ContributionChange(Contract):
    insight_id: Identifier
    evidence_id: Identifier
    revision: PositiveInt
    operation: Literal['create', 'update', 'withdraw']
    available_at: MatchTime
    evidence: PlayerContributionEvidence
    invalidates: tuple[PositiveInt, ...] = ()

    @model_validator(mode='after')
    def coherent(self) -> Self:
        if self.available_at != self.evidence.cutoff:
            raise ValueError('publication and evidence cutoff must agree')
        if (self.operation != 'withdraw') != (self.evidence.decision.status == 'eligible'):
            raise ValueError('only eligible evidence can create or update a story')
        if self.invalidates != ((self.revision-1,) if self.revision > 1 else ()):
            raise ValueError('publication must invalidate its preceding revision')
        return self


def in_cooldown(changes, evidence):
    for change in changes:
        old = change.evidence
        if change.operation == 'withdraw' or change.available_at.period != evidence.cutoff.period:
            continue
        if (old.match_id, old.subject_team_id, old.subject_player_id, old.metric, old.rule_version) != (
                evidence.match_id, evidence.subject_team_id, evidence.subject_player_id, evidence.metric, evidence.rule_version):
            continue
        if (old.baseline.window, old.current.window) == (evidence.baseline.window, evidence.current.window):
            continue  # Corrections to the same comparison must update or retract immediately.
        age = evidence.cutoff.elapsed_ms-change.available_at.elapsed_ms
        if 0 <= age < COOLDOWN_MS:
            return True
    return False


def project_contributions(history, session, baseline, current, cutoff):
    changes = list(history.contribution_changes)
    for team in history.fixture.teams:
        for player in team.player_ids:
            evidence = analyze_contributions(session, team.team_id, player, baseline, current, cutoff)
            identity = f'{evidence.match_id}:{team.team_id}:{player}:{evidence.rule_version}:{evidence.metric}:{baseline.model_dump_json()}:{current.model_dump_json()}'
            digest = sha256(identity.encode()).hexdigest()[:24]
            insight_id = f'player-{digest}'
            previous = next((c for c in reversed(changes) if c.insight_id == insight_id), None)
            eligible = evidence.decision.status == 'eligible'
            if not eligible and (previous is None or previous.operation == 'withdraw'):
                continue
            if eligible and previous is None and in_cooldown(changes, evidence):
                continue
            if previous and previous.evidence.model_dump(exclude={'cutoff'}) == evidence.model_dump(exclude={'cutoff'}):
                continue
            operation = 'withdraw' if not eligible else 'update' if previous and previous.operation != 'withdraw' else 'create'
            changes.append(ContributionChange(insight_id=insight_id, evidence_id=f'player-ev-{digest}',
                revision=previous.revision+1 if previous else 1, operation=operation, available_at=cutoff,
                evidence=evidence, invalidates=(previous.revision,) if previous else ()))
    return tuple(changes)
