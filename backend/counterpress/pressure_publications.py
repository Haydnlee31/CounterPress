"""Independent, append-only publication streams for observed pressure metrics."""

from hashlib import sha256
from typing import Literal, Self

from pydantic import model_validator

from counterpress.domain.models import Contract, Identifier, MatchTime, PositiveInt
from counterpress.domain.pressure import Metric, PressureEvidence, Publication, RateDecision, analyze_pressure
from counterpress.domain.progression import ProgressionEvidence, analyze_progression


class PressureChange(Contract):
    insight_id: Identifier
    evidence_id: Identifier
    revision: PositiveInt
    operation: Literal["create", "update", "withdraw"]
    available_at: MatchTime
    metric: Metric
    decision: RateDecision
    evidence: PressureEvidence | ProgressionEvidence
    invalidates: tuple[PositiveInt, ...] = ()

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.decision not in self.evidence.decisions or self.decision.metric != self.metric:
            raise ValueError("publication must use its evidence decision")
        if self.available_at != self.evidence.cutoff:
            raise ValueError("publication and evidence cutoff must agree")
        if (self.operation != "withdraw") != (self.decision.status == "eligible"):
            raise ValueError("only eligible decisions may create or update stories")
        if any(version >= self.revision for version in self.invalidates):
            raise ValueError("invalidations must precede this revision")
        return self


def project_pressure(history, session, baseline, current, cutoff, *, progression_only=False):
    changes = list(history.pressure_changes)
    receipts = tuple(Publication(match_id=change.evidence.match_id,
        team_id=change.evidence.subject_team_id, metric=change.metric,
        baseline=change.evidence.baseline.window, current=change.evidence.current.window,
        published_at=change.available_at) for change in changes
        if change.operation != "withdraw" and change.available_at.key() <= cutoff.key())
    for team in history.fixture.teams:
        analyzers = (analyze_progression,) if progression_only else (analyze_pressure, analyze_progression)
        for evidence, decision in ((evidence, decision) for analyze in analyzers
                for evidence in (analyze(session, team.team_id, baseline, current, cutoff, publications=receipts),)
                for decision in evidence.decisions):
            identity = f"{history.fixture.match_id}:{team.team_id}:{evidence.rule_version}:{decision.metric}:{baseline.model_dump_json()}:{current.model_dump_json()}"
            digest = sha256(identity.encode()).hexdigest()[:24]
            insight_id = f"pressure-{digest}"
            previous = next((change for change in reversed(changes) if change.insight_id == insight_id), None)
            eligible = decision.status == "eligible"
            if not eligible and (previous is None or previous.operation == "withdraw"):
                continue
            # Ignore cutoff-only advances, but preserve revisions of supporting and
            # excluded episodes so evidence inspection never shows stale records.
            if previous and (previous.evidence.model_dump(exclude={"cutoff"}) == evidence.model_dump(exclude={"cutoff"})):
                continue
            revision = previous.revision + 1 if previous else 1
            operation = "withdraw" if not eligible else "update" if previous and previous.operation != "withdraw" else "create"
            changes.append(PressureChange(insight_id=insight_id, evidence_id=f"pressure-ev-{digest}",
                revision=revision, operation=operation, available_at=cutoff, metric=decision.metric,
                decision=decision, evidence=evidence, invalidates=(previous.revision,) if previous else ()))
    return tuple(changes)
