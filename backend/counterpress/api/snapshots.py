"""Historical snapshots and deterministic, durable insight lifecycle projection."""

from hashlib import sha256
from itertools import groupby
from pathlib import Path
from time import time
from typing import Literal

from counterpress.domain.metrics import TeamMetrics, compare_recoveries
from counterpress.adaptation.contracts import AdaptationView
from counterpress.audience import AudienceService, AudienceView, ViewingPreferences
from counterpress.workflow.contracts import WorkflowView
from counterpress.domain.models import (
    Contract, Event, EvidencePacket, Identifier, Insight, MatchState, MatchTime,
    NonNegativeInt, ObservationWindow, RecoveryFacts,
)
from counterpress.fixture import Team, load_fixture
from counterpress.history import EvidenceBundle, EvidenceVersion, History, HistoryStore, InsightChange, SQLiteHistoryStore
from counterpress.replay import ReplaySession, display_time
from counterpress.pressure_publications import PressureChange, project_pressure
from counterpress.pressure_views import PressureView, pressure_view
from counterpress.fixture import PossessionFixture

SCENARIOS = {
    "increase": ("recovery_increase.json", "Recovery increase"),
    "control": ("recovery_control.json", "No-increase control"),
    "pressure-increase": ("pressure/increase.json", "Pressure and escape shift"),
    "pressure-control": ("pressure/control.json", "Pressure and escape control"),
    "progression-increase": ("progression/increase.json", "Possession without progression"),
    "progression-control": ("progression/control.json", "Progression control"),
}
START = MatchTime(period=2, elapsed_ms=180000)
SPLIT = MatchTime(period=2, elapsed_ms=480000)
END = MatchTime(period=2, elapsed_ms=780000)
BASELINE = ObservationWindow(start=START, end=SPLIT)
CURRENT = ObservationWindow(start=SPLIT, end=END)


class PlaybackRangeError(ValueError):
    pass


class Scenario(Contract):
    scenario_id: str
    label: str
    start: MatchTime = START
    end: MatchTime = END


class ScreenSnapshot(Contract):
    scenario_id: str
    scope_id: Identifier = "default"
    history_version: NonNegativeInt
    replay_end: MatchTime
    state: MatchState
    metrics: tuple[TeamMetrics, ...]
    windows: tuple[ObservationWindow, ObservationWindow] = (BASELINE, CURRENT)
    comparison_status: Literal["collecting", "no_increase", "ready"]
    insight: Insight | None = None
    evidence: EvidenceBundle | None = None
    lifecycle: InsightChange | None = None
    adaptation: AdaptationView | None = None
    workflow: WorkflowView | None = None
    audience: AudienceView | None = None
    teams: tuple[Team, ...] = ()
    pressure: PressureView | None = None
    pressure_lifecycle: tuple[PressureChange, ...] = ()
    selected_kind: Literal["recovery", "pressure"] | None = None


def horizon(history: History) -> MatchTime:
    return max((END, *(event.available_at for event in history.records)), key=lambda at: at.key())


def replay_session(history: History) -> ReplaySession:
    session = ReplaySession(history.fixture, end=horizon(history))
    session.deliver(history.records)
    return session


def project(history: History, cutoff: MatchTime) -> History:
    history = _project_recoveries(history, cutoff)
    return history.model_copy(update={"pressure_changes": project_pressure(history, replay_session(history), BASELINE, CURRENT, cutoff),
                                      "pressure_version": len(history.records), "episode_rules_version": 2})


def _project_recoveries(history: History, cutoff: MatchTime) -> History:
    """Publish only changed evidence, including a tombstone when eligibility ends."""
    replay = replay_session(history).snapshot(cutoff)
    comparison = compare_recoveries(replay.events, "eastbridge", BASELINE, CURRENT, cutoff)
    refs = comparison.baseline.source_events + comparison.current.source_events
    by_identity = {(event.event_id, event.revision): event for event in replay.events}
    records = tuple(by_identity[(ref.event_id, ref.revision)] for ref in refs)
    previous = history.changes[-1] if history.changes else None
    if previous and (previous.evidence.records == records
                     and previous.evidence.packet.baseline == comparison.baseline
                     and previous.evidence.packet.current == comparison.current):
        return history
    if not comparison.increased and (previous is None or previous.operation == "withdraw"):
        return history
    revision = previous.revision + 1 if previous else 1
    # Stable comparison identity: match, subject, rule and both window bounds.
    identity = f"{history.fixture.match_id}:eastbridge:high-recovery-v1:2:180000:480000:780000"
    digest = sha256(identity.encode()).hexdigest()[:24]
    insight_id, evidence_id = f"insight-{digest}", f"ev-{digest}"
    packet = EvidencePacket(
        evidence_id=evidence_id, evidence_version=revision, match_id=history.fixture.match_id,
        subject_team_id="eastbridge", metric="high_recovery_count", rule_version="high-recovery-v1",
        cutoff=cutoff, baseline=comparison.baseline, current=comparison.current,
    )
    evidence = EvidenceBundle(packet=packet, records=records)
    insight = None
    if comparison.increased:
        facts = RecoveryFacts(subject_team_id="eastbridge", baseline_count=comparison.baseline.value,
                              current_count=comparison.current.value, baseline_window=BASELINE, current_window=CURRENT)
        insight = Insight(
            insight_id=insight_id, revision=revision, evidence_id=evidence_id, evidence_version=revision,
            title="High recoveries increased",
            explanation=f"Eastbridge recorded {facts.current_count} attacking-third recoveries from "
                        f"{display_time(SPLIT)} to {display_time(END)}, up from {facts.baseline_count} "
                        f"in the previous five minutes.", facts=facts, eligible_at=cutoff,
        )
    operation = "withdraw" if insight is None else "update" if previous and previous.operation != "withdraw" else "create"
    change = InsightChange(
        insight_id=insight_id, revision=revision, operation=operation, available_at=cutoff,
        insight=insight, evidence=evidence,
        invalidates=(EvidenceVersion(evidence_id=previous.evidence.packet.evidence_id,
                                     evidence_version=previous.evidence.packet.evidence_version),) if previous else (),
    )
    return history.model_copy(update={"changes": (*history.changes, change)})


class SnapshotService:
    def __init__(self, fixture_dir: Path, store: HistoryStore | None = None):
        self.fixture_dir = fixture_dir
        self.store = store or SQLiteHistoryStore(":memory:")
        self.audiences = AudienceService()

    def history(self, scenario_id: str) -> History:
        if scenario_id not in SCENARIOS:
            raise KeyError("unknown scenario")
        existing = self.store.read(scenario_id)
        if existing is not None:
            if existing.pressure_version == len(existing.records) and existing.episode_rules_version == 2:
                return existing
            # Additive migration: rebuild historical pressure publications without
            # rewriting source, recovery, adaptation or workflow history.
            def backfill(previous):
                assert previous is not None
                if previous.pressure_version == len(previous.records) and previous.episode_rules_version == 2:
                    return previous
                result = previous
                for at in sorted({END.elapsed_ms, *(event.available_at.elapsed_ms for event in previous.records if event.available_at.key() >= END.key())}):
                    cutoff = MatchTime(period=2, elapsed_ms=at)
                    result = result.model_copy(update={"pressure_changes": project_pressure(result, replay_session(result), BASELINE, CURRENT, cutoff,
                        progression_only=previous.pressure_version > 0)})
                return result.model_copy(update={"pressure_version": len(result.records), "episode_rules_version": 2})
            return self.store.transact(scenario_id, backfill)

        def seed(previous: History | None) -> History:
            if previous is not None:
                return previous
            fixture = load_fixture(self.fixture_dir / SCENARIOS[scenario_id][0])
            if scenario_id.startswith("pressure-"):
                # Stretch the independently reviewed two-minute controls across
                # the screen's ten-minute interval; no outcomes or positions change.
                raw = fixture.model_dump()
                raw["match_id"] += "-replay"
                for event in raw["events"]:
                    event["match_id"] = raw["match_id"]
                    for field in ("occurred_at", "available_at"):
                        event[field]["elapsed_ms"] = START.elapsed_ms + (event[field]["elapsed_ms"] - START.elapsed_ms) * 5
                fixture = PossessionFixture.model_validate(raw)
            if fixture.initial_state.at != START or any(event.available_at.period != 2 for event in fixture.events):
                raise ValueError("this demo requires the declared second-half interval")
            history = History(fixture=fixture, records=fixture.events)
            for at in sorted({END.elapsed_ms, *(event.available_at.elapsed_ms for event in fixture.events
                                               if event.available_at.key() >= END.key())}):
                history = project(history, MatchTime(period=2, elapsed_ms=at))
            return history

        return self.store.transact(scenario_id, seed)

    def ingest(self, scenario_id: str, records: tuple[Event, ...]) -> History:
        self.history(scenario_id)

        def append(previous: History | None) -> History:
            assert previous is not None
            session = replay_session(previous)
            session.deliver(records)  # Validate identities, actor membership and revision invariants first.
            known = {(event.event_id, event.revision) for event in previous.records}
            additions = [event for event in session.journal.records if (event.event_id, event.revision) not in known]
            if not additions:
                return previous
            watermark = horizon(previous)
            if any(event.available_at.period != 2 or event.available_at.key() < watermark.key() for event in additions):
                raise ValueError("new deliveries cannot backdate availability before the persisted replay horizon; occurrence may be earlier")
            updated = previous
            # Same-time deliveries form one atomic observation, independent of source sequence gaps.
            additions.sort(key=lambda event: (*event.available_at.key(), event.source_delivery_sequence))
            for at, group in groupby(additions, key=lambda event: event.available_at):
                updated = updated.model_copy(update={"records": (*updated.records, *group)})
                updated = project(updated, at)  # State reduction rejects incoherent possession before commit.
            return updated

        updated = self.store.transact(scenario_id, append)
        self.audiences.invalidate(updated)
        return updated

    def snapshot(self, scenario_id: str, at_ms: int, scope_id: str = "default",
                 preferences: ViewingPreferences | None = None) -> ScreenSnapshot:
        history = self.history(scenario_id)
        end = horizon(history)
        if not START.elapsed_ms <= at_ms <= end.elapsed_ms:
            raise PlaybackRangeError("playback position is outside the persisted replay interval")
        cutoff = MatchTime(period=2, elapsed_ms=at_ms)
        replay = replay_session(history).snapshot(cutoff)
        change = next((item for item in reversed(history.changes) if item.available_at.key() <= cutoff.key()), None)
        insight = change.insight if change else None
        adaptation = None
        now = int(time() * 1000)
        if insight and change == history.changes[-1]:
            candidates = [*history.adaptations, *(item for item in history.workflows if item.available_at.key() <= cutoff.key())]
            for attempt in sorted(candidates, key=lambda item: item.started_at_unix_ms, reverse=True):
                if (attempt.status in ("accepted", "narrowed") and attempt.text
                        and attempt.evidence_id == insight.evidence_id
                        and attempt.evidence_version == insight.evidence_version
                        and attempt.requested_at.key() <= cutoff.key()
                        and attempt.started_at_unix_ms <= now < attempt.expires_at_unix_ms):
                    adaptation = AdaptationView(attempt_id=attempt.attempt_id, evidence_id=insight.evidence_id,
                                                evidence_version=insight.evidence_version, text=attempt.text,
                                                expires_at_unix_ms=attempt.expires_at_unix_ms)
                    break
        audit = next((item for item in reversed(history.workflows)
                      if item.available_at.key() <= cutoff.key() and item.requested_at.key() <= cutoff.key()
                      and (item.source_history_version == len(history.records) or item.status == "stale")), None)
        prefs = preferences or ViewingPreferences()
        audience = self.audiences.build(history, insight, change.evidence if insight else None,
            replay.events, prefs, cutoff.key() < END.key())
        latest_pressure = {}
        for item in history.pressure_changes:
            if item.available_at.key() <= cutoff.key():
                latest_pressure[item.insight_id] = item
        pressure = pressure_view(history, tuple(latest_pressure.values()), prefs, cutoff.key() < END.key())
        selected_kind = "recovery" if audience.state == "ready" else None
        if pressure.state == "ready" and (selected_kind is None or pressure.priority > audience.priority):
            selected_kind = "pressure"
        return ScreenSnapshot(
            scenario_id=scenario_id, scope_id=scope_id, history_version=len(history.records), replay_end=end,
            state=replay.state, metrics=replay.metrics,
            comparison_status="collecting" if cutoff.key() < END.key() else "ready" if insight else "no_increase",
            insight=insight, evidence=change.evidence if insight else None, lifecycle=change,
            adaptation=adaptation,
            workflow=WorkflowView(attempt_id=audit.attempt_id, status=audit.status, actions=audit.actions) if audit else None,
            audience=audience, pressure=pressure, pressure_lifecycle=tuple(latest_pressure.values()), selected_kind=selected_kind,
            teams=history.fixture.teams,
        )

    def evidence(self, scenario_id: str, version: int, at_ms: int) -> EvidenceBundle:
        history = self.history(scenario_id)
        for change in history.changes:
            if change.revision == version and change.available_at.elapsed_ms <= at_ms:
                return change.evidence
        raise KeyError("evidence version not available at this cutoff")

    def pressure_evidence(self, scenario_id: str, insight_id: str, version: int, at_ms: int) -> PressureChange:
        history = self.history(scenario_id)
        if not START.elapsed_ms <= at_ms <= horizon(history).elapsed_ms:
            raise KeyError("cutoff outside history")
        for change in history.pressure_changes:
            if change.insight_id == insight_id and change.revision == version and change.available_at.elapsed_ms <= at_ms:
                return change
        raise KeyError("pressure evidence not available at this cutoff")
