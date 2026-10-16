"""Append local synthetic deliveries to the same SQLite history used by the API."""

import argparse
import os
from pathlib import Path
import sqlite3

from pydantic import TypeAdapter

from counterpress.api.snapshots import SCENARIOS, SnapshotService
from counterpress.domain.models import Event
from counterpress.history import SQLiteHistoryStore
from counterpress.replay import display_time


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=SCENARIOS)
    parser.add_argument("updates", type=Path, help="JSON array of Event records; exact duplicates are harmless")
    parser.add_argument("--db", type=Path, default=Path(os.environ.get("COUNTERPRESS_DB_PATH", root / "var/counterpress.sqlite3")))
    parser.add_argument("--fixtures", type=Path, default=Path(os.environ.get("COUNTERPRESS_FIXTURE_DIR", root / "fixtures")))
    args = parser.parse_args()
    try:
        service = SnapshotService(args.fixtures, SQLiteHistoryStore(args.db))
        updates = TypeAdapter(tuple[Event, ...]).validate_json(args.updates.read_text())
        before = service.history(args.scenario)
        after = service.ingest(args.scenario, updates)
        print(f"Stored {len(after.records) - len(before.records)} new records; history version {len(after.records)}")
        for change in after.changes[len(before.changes):]:
            packet = change.evidence.packet
            print(f"{display_time(change.available_at)} | {change.operation} r{change.revision} | "
                  f"{packet.baseline.value} -> {packet.current.value} | evidence v{packet.evidence_version}")
        for change in after.pressure_changes[len(before.pressure_changes):]:
            d = change.decision
            print(f"{display_time(change.available_at)} | {change.evidence.subject_team_id} {change.metric} | "
                  f"{change.operation} r{change.revision} | {d.baseline_numerator}/{d.baseline_denominator} -> "
                  f"{d.current_numerator}/{d.current_denominator} | {d.status}")
        for change in after.contribution_changes[len(before.contribution_changes):]:
            e = change.evidence
            print(f"{display_time(change.available_at)} | {e.subject_team_id}/{e.subject_player_id} {e.metric} | "
                  f"{change.operation} r{change.revision} | {e.baseline.player_count}/{e.baseline.team_count} -> "
                  f"{e.current.player_count}/{e.current.team_count} | {e.decision.status}")
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
