"""Request one validated Azure wording adaptation; prints a sanitized audit record."""

import argparse
import asyncio
import os
from pathlib import Path
import sqlite3

from counterpress.adaptation.azure import AzureDraftProvider, load_config
from counterpress.adaptation.service import AdaptationService
from counterpress.api.snapshots import SCENARIOS, SnapshotService
from counterpress.history import SQLiteHistoryStore


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=SCENARIOS)
    parser.add_argument("--at-ms", type=int, default=780000)
    parser.add_argument("--db", type=Path, default=Path(os.environ.get("COUNTERPRESS_DB_PATH", root / "var/counterpress.sqlite3")))
    parser.add_argument("--fixtures", type=Path, default=Path(os.environ.get("COUNTERPRESS_FIXTURE_DIR", root / "fixtures")))
    args = parser.parse_args()
    try:
        config = load_config()
        snapshots = SnapshotService(args.fixtures, SQLiteHistoryStore(args.db))
        service = AdaptationService(snapshots, AzureDraftProvider(config) if config else None)
        attempt = asyncio.run(service.adapt(args.scenario, args.at_ms))
        print(attempt.model_dump_json(indent=2))
        raise SystemExit(0 if attempt.status == "accepted" else 2)
    except (OSError, ValueError, sqlite3.Error):
        parser.error("Could not configure adaptation or load history. Check local configuration and replay position.")


if __name__ == "__main__":
    main()
