"""Durable local history boundary; source records and publications are append-only."""

from collections.abc import Callable
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Literal, Protocol, Self

from pydantic import model_validator

from counterpress.adaptation.contracts import AdaptationAttempt
from counterpress.workflow.contracts import WorkflowAttempt
from counterpress.domain.models import Contract, Event, EvidencePacket, Identifier, Insight, MatchTime, PositiveInt
from counterpress.fixture import PossessionFixture
from counterpress.pressure_publications import PressureChange

DEFINITION = "An open-play change into established controlled possession at x ≥ 70 m, in the recovering team's attacking direction. Duels and restarts are excluded."


class EvidenceBundle(Contract):
    packet: EvidencePacket
    records: tuple[Event, ...]
    metric_definition: str = DEFINITION
    coordinate_system: Literal["actor_team_attacks_positive_x"] = "actor_team_attacks_positive_x"


class EvidenceVersion(Contract):
    evidence_id: Identifier
    evidence_version: PositiveInt


class InsightChange(Contract):
    insight_id: Identifier
    revision: PositiveInt
    operation: Literal["create", "update", "withdraw"]
    available_at: MatchTime
    insight: Insight | None
    evidence: EvidenceBundle
    invalidates: tuple[EvidenceVersion, ...] = ()

    @model_validator(mode="after")
    def coherent_publication(self) -> Self:
        packet = self.evidence.packet
        if (self.insight is None) != (self.operation == "withdraw"):
            raise ValueError("only withdrawal messages omit the insight")
        if packet.evidence_version != self.revision or packet.cutoff != self.available_at:
            raise ValueError("publication and evidence versions/cutoffs must agree")
        if self.insight and (self.insight.insight_id != self.insight_id
                             or self.insight.revision != self.revision
                             or self.insight.evidence_id != packet.evidence_id
                             or self.insight.evidence_version != packet.evidence_version
                             or self.insight.eligible_at != self.available_at):
            raise ValueError("insight must reference this publication's evidence")
        if any(item.evidence_id != packet.evidence_id or item.evidence_version >= self.revision for item in self.invalidates):
            raise ValueError("invalidation must reference an older version of this evidence")
        return self


class History(Contract):
    fixture: PossessionFixture
    records: tuple[Event, ...]
    changes: tuple[InsightChange, ...] = ()
    adaptations: tuple[AdaptationAttempt, ...] = ()
    workflows: tuple[WorkflowAttempt, ...] = ()
    pressure_changes: tuple[PressureChange, ...] = ()
    pressure_version: int = 0
    episode_rules_version: int = 0


class HistoryStore(Protocol):
    def read(self, scenario_id: str) -> History | None: ...

    def transact(self, scenario_id: str, build: Callable[[History | None], History]) -> History: ...


class SQLiteHistoryStore:
    """One SQLite transaction commits source records and derived evidence together.

    Connections are short-lived for file databases; :memory: is test-only and
    keeps its connection. BEGIN IMMEDIATE serializes writers across processes.
    """

    def __init__(self, path: str | Path):
        self.path = str(path)
        self._lock = RLock()
        self._memory: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        connection = self._memory or sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        if self.path == ":memory:":
            self._memory = connection
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS scenarios (
                scenario_id TEXT PRIMARY KEY, fixture TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                scenario_id TEXT NOT NULL REFERENCES scenarios(scenario_id),
                ordinal INTEGER NOT NULL, event_id TEXT NOT NULL, revision INTEGER NOT NULL,
                source_sequence INTEGER NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY (scenario_id, event_id, revision),
                UNIQUE (scenario_id, source_sequence), UNIQUE (scenario_id, ordinal)
            );
            CREATE TABLE IF NOT EXISTS changes (
                scenario_id TEXT NOT NULL REFERENCES scenarios(scenario_id),
                revision INTEGER NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY (scenario_id, revision)
            );
            CREATE TABLE IF NOT EXISTS adaptations (
                scenario_id TEXT NOT NULL REFERENCES scenarios(scenario_id),
                ordinal INTEGER NOT NULL, attempt_id TEXT NOT NULL,
                payload TEXT NOT NULL, PRIMARY KEY (scenario_id, attempt_id),
                UNIQUE (scenario_id, ordinal)
            );
            CREATE TABLE IF NOT EXISTS workflows (
                scenario_id TEXT NOT NULL REFERENCES scenarios(scenario_id),
                ordinal INTEGER NOT NULL, attempt_id TEXT NOT NULL,
                payload TEXT NOT NULL, PRIMARY KEY (scenario_id, attempt_id),
                UNIQUE (scenario_id, ordinal)
            );
            CREATE TABLE IF NOT EXISTS pressure_changes (
                scenario_id TEXT NOT NULL REFERENCES scenarios(scenario_id),
                ordinal INTEGER NOT NULL, insight_id TEXT NOT NULL, revision INTEGER NOT NULL,
                payload TEXT NOT NULL, PRIMARY KEY (scenario_id, insight_id, revision),
                UNIQUE (scenario_id, ordinal)
            );
            CREATE TABLE IF NOT EXISTS pressure_checkpoints (
                scenario_id TEXT PRIMARY KEY REFERENCES scenarios(scenario_id), source_version INTEGER NOT NULL,
                rules_version INTEGER NOT NULL DEFAULT 0
            );
        """)
        # Existing checkpoints predate the progression rule. An additive column
        # lets old pressure publications stay intact while the new rule backfills.
        columns = {row[1] for row in connection.execute("PRAGMA table_info(pressure_checkpoints)")}
        if "rules_version" not in columns:
            try:
                connection.execute("ALTER TABLE pressure_checkpoints ADD COLUMN rules_version INTEGER NOT NULL DEFAULT 0")
            except sqlite3.OperationalError:
                # Another service may have migrated the file after our inspection.
                if "rules_version" not in {row[1] for row in connection.execute("PRAGMA table_info(pressure_checkpoints)")}:
                    raise
        return connection

    @staticmethod
    def _read(connection: sqlite3.Connection, scenario_id: str) -> History | None:
        row = connection.execute("SELECT fixture FROM scenarios WHERE scenario_id = ?", (scenario_id,)).fetchone()
        if row is None:
            return None
        records = tuple(Event.model_validate_json(item[0]) for item in connection.execute(
            "SELECT payload FROM events WHERE scenario_id = ? ORDER BY ordinal", (scenario_id,)))
        changes = tuple(InsightChange.model_validate_json(item[0]) for item in connection.execute(
            "SELECT payload FROM changes WHERE scenario_id = ? ORDER BY revision", (scenario_id,)))
        adaptations = tuple(AdaptationAttempt.model_validate_json(item[0]) for item in connection.execute(
            "SELECT payload FROM adaptations WHERE scenario_id = ? ORDER BY ordinal", (scenario_id,)))
        workflows = tuple(WorkflowAttempt.model_validate_json(item[0]) for item in connection.execute(
            "SELECT payload FROM workflows WHERE scenario_id = ? ORDER BY ordinal", (scenario_id,)))
        pressure_changes = tuple(PressureChange.model_validate_json(item[0]) for item in connection.execute(
            "SELECT payload FROM pressure_changes WHERE scenario_id = ? ORDER BY ordinal", (scenario_id,)))
        checkpoint = connection.execute("SELECT source_version, rules_version FROM pressure_checkpoints WHERE scenario_id = ?", (scenario_id,)).fetchone()
        return History(fixture=PossessionFixture.model_validate_json(row[0]), records=records, changes=changes,
            adaptations=adaptations, workflows=workflows, pressure_changes=pressure_changes,
            pressure_version=checkpoint[0] if checkpoint else 0, episode_rules_version=checkpoint[1] if checkpoint else 0)

    def read(self, scenario_id: str) -> History | None:
        with self._lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN")
                result = self._read(connection, scenario_id)
                connection.commit()
                return result
            except Exception:
                connection.rollback()
                raise
            finally:
                if self.path != ":memory:":
                    connection.close()

    def transact(self, scenario_id: str, build: Callable[[History | None], History]) -> History:
        with self._lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN IMMEDIATE")
                previous = self._read(connection, scenario_id)
                result = build(previous)
                old_records = previous.records if previous else ()
                old_changes = previous.changes if previous else ()
                old_adaptations = previous.adaptations if previous else ()
                old_workflows = previous.workflows if previous else ()
                old_pressure = previous.pressure_changes if previous else ()
                if previous and (result.fixture != previous.fixture
                                 or result.records[:len(old_records)] != old_records
                                 or result.changes[:len(old_changes)] != old_changes
                                 or result.adaptations[:len(old_adaptations)] != old_adaptations
                                 or result.workflows[:len(old_workflows)] != old_workflows
                                 or result.pressure_changes[:len(old_pressure)] != old_pressure
                                 or result.pressure_version < previous.pressure_version
                                 or result.episode_rules_version < previous.episode_rules_version):
                    raise ValueError("persisted history cannot be rewritten")
                if previous is None:
                    connection.execute("INSERT INTO scenarios VALUES (?, ?)", (scenario_id, result.fixture.model_dump_json()))
                for index, event in enumerate(result.records[len(old_records):], len(old_records) + 1):
                    connection.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)", (
                        scenario_id, index, event.event_id, event.revision,
                        event.source_delivery_sequence, event.model_dump_json()))
                for change in result.changes[len(old_changes):]:
                    connection.execute("INSERT INTO changes VALUES (?, ?, ?)", (
                        scenario_id, change.revision, change.model_dump_json()))
                for index, attempt in enumerate(result.adaptations[len(old_adaptations):], len(old_adaptations) + 1):
                    connection.execute("INSERT INTO adaptations VALUES (?, ?, ?, ?)", (
                        scenario_id, index, attempt.attempt_id, attempt.model_dump_json()))
                for index, attempt in enumerate(result.workflows[len(old_workflows):], len(old_workflows) + 1):
                    connection.execute("INSERT INTO workflows VALUES (?, ?, ?, ?)", (
                        scenario_id, index, attempt.attempt_id, attempt.model_dump_json()))
                for index, change in enumerate(result.pressure_changes[len(old_pressure):], len(old_pressure) + 1):
                    connection.execute("INSERT INTO pressure_changes VALUES (?, ?, ?, ?, ?)", (
                        scenario_id, index, change.insight_id, change.revision, change.model_dump_json()))
                connection.execute("INSERT INTO pressure_checkpoints VALUES (?, ?, ?) ON CONFLICT(scenario_id) DO UPDATE SET source_version=excluded.source_version, rules_version=excluded.rules_version",
                                   (scenario_id, result.pressure_version, result.episode_rules_version))
                connection.commit()
                return result
            except Exception:
                connection.rollback()
                raise
            finally:
                if self.path != ":memory:":
                    connection.close()
