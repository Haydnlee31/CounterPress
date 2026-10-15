"""Run one bounded Analyst/Producer review; no automatic model calls on replay polling."""

import argparse
import asyncio
import logging
import os
from pathlib import Path
import sqlite3

from counterpress.adaptation.azure import load_config
from counterpress.api.snapshots import SCENARIOS, SnapshotService
from counterpress.history import SQLiteHistoryStore
from counterpress.workflow.service import WorkflowService


def main():
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=SCENARIOS)
    parser.add_argument("--candidate", choices=("recovery_increase", "pressure_effectiveness"), default="recovery_increase")
    parser.add_argument("--at-ms", type=int, default=780000)
    parser.add_argument("--db", type=Path, default=Path(os.environ.get("COUNTERPRESS_DB_PATH", root / "var/counterpress.sqlite3")))
    parser.add_argument("--fixtures", type=Path, default=Path(os.environ.get("COUNTERPRESS_FIXTURE_DIR", root / "fixtures")))
    args = parser.parse_args()
    # SDK/framework diagnostics may contain model payloads. Print only our sanitized audit.
    logging.getLogger("agent_framework").setLevel(logging.CRITICAL)
    logging.getLogger("openai").setLevel(logging.CRITICAL)
    try:
        service = WorkflowService(SnapshotService(args.fixtures, SQLiteHistoryStore(args.db)), load_config())
        attempt = asyncio.run(service.run(args.scenario, args.at_ms, args.candidate))
        print(attempt.model_dump_json(indent=2))
        raise SystemExit(0 if attempt.status in ("accepted", "narrowed", "rejected") else 2)
    except (OSError, ValueError, sqlite3.Error):
        parser.error("Could not configure workflow or load history. Check local configuration and replay position.")


if __name__ == "__main__":
    main()
