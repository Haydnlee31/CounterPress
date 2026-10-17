"""Opt-in one-call local integration probe; uses isolated SQLite, never public history."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

from counterpress.adaptation.azure import load_config
from counterpress.api.snapshots import SnapshotService
from counterpress.editorial.ledger import Ledger, SQLiteLedgerStore
from counterpress.editorial.service import EditorialController, EditorialRequest
from counterpress.history import SQLiteHistoryStore
from counterpress.studio.service import StudioService, ReviewRequest, DecisionRequest, ReviewConflict


async def check(path):
    if path.exists():
        raise ValueError('Use a fresh isolated probe path')
    config = load_config()
    if config is None:
        raise ValueError('Private configuration is required')
    snapshots = SnapshotService(Path('fixtures'), SQLiteHistoryStore(path))
    controller = EditorialController(snapshots, config, Ledger(SQLiteLedgerStore(path)))
    context = await controller.context('increase', 780000, ReviewRequest().preferences)
    result = await controller.run('increase', EditorialRequest(at_ms=780000,
        preferences=context.recap.preferences, fingerprint=context.fingerprint), '0'*64)
    if not result.workflow or not result.workflow.applied:
        print(json.dumps({'passed': False, 'outcome': result.status, 'model_requests_at_most': 1}))
        return 1
    service = StudioService(snapshots)
    req = ReviewRequest(attempt_id=result.workflow.attempt_id)
    view = service.review('increase', req)
    decision = DecisionRequest(attempt_id=view.attempt_id, fingerprint=view.fingerprint, preferences=view.recap.preferences)
    assert service.decide('increase', decision, '0'*64, 'approve').status == 'approved'
    assert view.attempt_id in service.export('increase', decision)
    service.now = lambda: result.workflow.expires_at_unix_ms
    assert service.review('increase', req).status == 'unavailable'
    try:
        service.export('increase', decision)
    except ReviewConflict:
        pass
    else:
        raise ValueError('Expired export was accepted')
    print(json.dumps({'passed': True, 'model_requests': 1, 'approval_export': True,
                      'expiry_blocks_export': True, 'storage': 'isolated local SQLite',
                      'synthetic_probe_actor': True, 'human_usefulness_evaluation': False}))
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', required=True)
    parser.add_argument('--database', type=Path, required=True)
    args = parser.parse_args()
    try:
        sys.exit(asyncio.run(check(args.database)))
    except Exception:
        print('Studio AI probe failed; private diagnostics and model configuration are not printed.', file=sys.stderr)
        sys.exit(1)
