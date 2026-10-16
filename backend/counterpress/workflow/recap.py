"""Explicit recap workflow command; polling never starts paid model requests."""

import argparse
import asyncio
import logging
import os
from pathlib import Path
import sqlite3

from counterpress.adaptation.azure import load_config
from counterpress.api.snapshots import SCENARIOS, SnapshotService
from counterpress.audience import ViewingPreferences
from counterpress.history import SQLiteHistoryStore
from counterpress.workflow.recap_service import RecapWorkflowService


def main():
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', choices=SCENARIOS)
    parser.add_argument('--at-ms', type=int, default=780000)
    parser.add_argument('--language', choices=['en', 'zh-Hans'], default='en')
    parser.add_argument('--depth', choices=['analyst', 'casual'], default='analyst')
    parser.add_argument('--club')
    parser.add_argument('--player')
    parser.add_argument('--metric-focus', default='balanced')
    parser.add_argument('--db', type=Path, default=Path(os.environ.get('COUNTERPRESS_DB_PATH', root/'var/counterpress.sqlite3')))
    parser.add_argument('--fixtures', type=Path, default=Path(os.environ.get('COUNTERPRESS_FIXTURE_DIR', root/'fixtures')))
    args = parser.parse_args()
    for name in ('agent_framework', 'openai', 'httpx', 'httpx2', 'httpcore'):
        logging.getLogger(name).setLevel(logging.CRITICAL)
    try:
        prefs = ViewingPreferences(language=args.language, depth=args.depth, club_id=args.club,
                                   player_id=args.player, metric_focus=args.metric_focus)
        service = RecapWorkflowService(SnapshotService(args.fixtures, SQLiteHistoryStore(args.db)), load_config())
        attempt = asyncio.run(service.run(args.scenario, args.at_ms, prefs))
        # No endpoint, deployment name, credentials, model prose or error bodies.
        print(attempt.model_dump_json(indent=2))
        raise SystemExit(0 if attempt.status in ('accepted', 'narrowed', 'rejected') else 2)
    except (OSError, ValueError, sqlite3.Error):
        parser.error('Could not configure recap workflow or load history. Check local configuration and preferences.')


if __name__ == '__main__':
    main()
