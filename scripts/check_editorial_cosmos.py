"""Explicit real Cosmos control checks in isolated partitions; no provider network calls.

Use seed, then verify in a fresh process with the same --scope. Existing private
COUNTERPRESS_COSMOS_* settings are required. Verification records are retained.
"""

import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
from threading import Barrier
from time import time
from types import SimpleNamespace

from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosBatchOperationError
import httpx2
from pydantic import SecretStr, TypeAdapter

from counterpress.api.snapshots import SnapshotService
from counterpress.audience import ViewingPreferences
from counterpress.cosmos_check import ScopedStore
from counterpress.domain.models import Event
from counterpress.editorial.ledger import CosmosLedgerStore, Ledger, Limits
from counterpress.editorial.service import EditorialController, EditorialRequest
from counterpress.storage import configured_store


def ledger_store(container, scope, suffix):
    store = CosmosLedgerStore(container)
    store.partition = f'verify-editorial-{scope}-{suffix}'
    return store


class RacingContainer:
    """Synchronize the first reads to force a real Cosmos create/ETag conflict."""
    def __init__(self, container, barrier, conflicts):
        self.container, self.barrier, self.conflicts = container, barrier, conflicts
        self.first = True

    def read_item(self, **kwargs):
        try:
            return self.container.read_item(**kwargs)
        finally:
            if self.first:
                self.first = False
                self.barrier.wait(timeout=30)

    def execute_item_batch(self, **kwargs):
        try:
            return self.container.execute_item_batch(**kwargs)
        except (CosmosHttpResponseError, CosmosBatchOperationError) as exc:
            if exc.status_code in (409, 412):
                self.conflicts.append(exc.status_code)
            raise


def synthetic_response(request):
    """Controlled structured model double; no external inference or invented facts."""
    content = json.loads(request.content)['messages'][-1]['content']
    if isinstance(content, list):
        content = ''.join(part['text'] for part in content)
    package = json.loads(content)
    plan = {'fingerprint': package['fingerprint'], 'decision': 'accept',
            'stories': package['stories'], 'reason': 'supported_comparisons',
            'draft': {'fingerprint': package['fingerprint'], 'language': package['language'],
                      'heading': 'key_changes',
                      'stories': [s | {'template': 'brief'} for s in package['stories']]}}
    return httpx2.Response(200, json={'id': 'synthetic-probe', 'object': 'chat.completion',
        'created': 0, 'model': 'synthetic-probe', 'choices': [{'index': 0,
        'message': {'role': 'assistant', 'content': json.dumps(plan)}, 'finish_reason': 'stop'}]})


def mock_config():
    # Only passed to an in-memory mock transport. No private model settings loaded.
    return SimpleNamespace(endpoint='https://invalid.example', deployment='synthetic-probe',
        url='https://invalid.example/openai/v1/chat/completions', api_key=SecretStr('unused'))


def seed(scope, store, fixtures):
    limits = Limits(lifetime=2, daily=2, per_editor_daily=1)
    base = ledger_store(store.container, scope, 'admission')
    # Read-only preflight: refuse to reset an already used verification scope.
    try:
        store.container.read_item(item='editorial-control', partition_key=base.partition)
    except CosmosHttpResponseError as exc:
        if exc.status_code != 404:
            raise
    else:
        raise ValueError('Use a fresh verification scope for seed')
    barrier, conflicts = Barrier(2), []
    now = int(time()*1000)
    def reserve(index):
        racing = RacingContainer(store.container, barrier, conflicts)
        return Ledger(ledger_store(racing, scope, 'admission'), limits).reserve('shared', f'actor-{index}', now)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(reserve, range(2)))
    assert sorted(s for s, _ in outcomes) == ['pending', 'reserved'] and conflicts
    job = next(job for status, job in outcomes if status == 'reserved')
    restarted = Ledger(ledger_store(store.container, scope, 'admission'), limits)
    assert restarted.dispatch('shared', job.owner, int(time()*1000))
    assert not restarted.dispatch('shared', job.owner, int(time()*1000))
    restarted.finish('shared', job.owner, int(time()*1000))
    assert restarted.reserve('second', 'post-race', int(time()*1000))[0] == 'reserved'
    assert restarted.reserve('third', 'new-editor', int(time()*1000))[0] == 'quota_exceeded'

    lease = Ledger(ledger_store(store.container, scope, 'leases'))
    _, old = lease.reserve('handover', 'actor', 1000)
    _, new = lease.reserve('handover', 'actor', 31000)
    assert old.owner != new.owner and not lease.dispatch('handover', old.owner, 31001)
    lease.finish('handover', old.owner, 31001)
    assert lease.dispatch('handover', new.owner, 31001)

    async def history_check():
        calls = []
        def response(request):
            calls.append(1)
            return synthetic_response(request)
        def controller():
            app = SnapshotService(fixtures, ScopedStore(type(store)(store.container), f'editorial-{scope}'))
            return EditorialController(app, mock_config(), Ledger(ledger_store(store.container, scope, 'presentation')),
                transport_factory=lambda: httpx2.MockTransport(response), poll_seconds=.5)
        first = controller()
        context = await first.context('increase', 780000, ViewingPreferences())
        req = EditorialRequest(at_ms=780000, fingerprint=context.fingerprint)
        result = await first.run('increase', req, 'synthetic-editor')
        assert result.status == 'completed' and result.workflow.applied
        second = controller()
        cached = await second.run('increase', req, 'synthetic-editor')
        assert cached.status == 'cached' and cached.workflow.applied and len(calls) == 1
        events = TypeAdapter(tuple[Event, ...]).validate_json((fixtures/'faults/recovery_corrections.json').read_text())
        await asyncio.to_thread(second.snapshots.ingest, 'increase', events)
        assert (await second.run('increase', req, 'synthetic-editor')).status == 'stale'
        latest = await second.snapshot('increase', 795000, ViewingPreferences())
        assert latest.adapted_recap is None
    asyncio.run(history_check())
    return {'real_cosmos_conflict_statuses': sorted(conflicts), 'atomic_duplicate_admission': True,
            'single_dispatch_claim': True, 'durable_quota_exhaustion': True,
            'old_lease_owner_rejected': True, 'lease_test_clock': 'controlled timestamps',
            'revision_cache_reused': True, 'correction_invalidated_presentation': True,
            'model_transport': 'synthetic in-memory double', 'external_model_calls': 0}


def verify(scope, store):
    ledger = Ledger(ledger_store(store.container, scope, 'admission'), Limits(lifetime=2, daily=2, per_editor_daily=1))
    assert ledger.reserve('after-process-restart', 'fresh-editor', int(time()*1000))[0] == 'quota_exceeded'
    state = ledger.store.transact(lambda previous: previous)
    assert state.admitted == 2 and state.jobs['shared'].dispatched
    app = SnapshotService(Path('/nonexistent-counterpress-fixtures'), ScopedStore(store, f'editorial-{scope}'))
    history = app.history('increase')
    assert len(history.records) == 93 and len(history.recap_workflows) == 1
    assert history.recap_workflows[0].prompt_version == 'recap-single-editor-v1'
    assert history.recap_workflows[0].status == 'accepted'
    for at, count in [(780000, 4), (785000, 3), (790000, None), (795000, 2)]:
        snapshot = app.snapshot('increase', at)
        assert (snapshot.insight.facts.current_count if snapshot.insight else None) == count
        assert snapshot.adapted_recap is None
    return {'fresh_process_quota_preserved': True, 'fixture_free_history_recovery': True,
            'single_editor_audit_restored': True, 'historical_counts': [4, 3, None, 2],
            'corrected_presentation_not_applied': True, 'external_model_calls': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['seed', 'verify'])
    parser.add_argument('--scope', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch('[a-z0-9-]{1,32}', args.scope):
        parser.error('scope must be 1–32 lowercase letters, digits or hyphens')
    if os.environ.get('COUNTERPRESS_STORAGE') != 'cosmos':
        parser.error('This explicit live check requires Cosmos storage')
    try:
        store = configured_store(':memory:')
        report = seed(args.scope, store, Path('fixtures')) if args.phase == 'seed' else verify(args.scope, store)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2)+'\n')
        print(f'PASS: real Cosmos editorial {args.phase}; isolated partitions, zero external model calls.')
        return 0
    except Exception as exc:
        status = getattr(exc, 'status_code', None)
        print(f'FAIL: Cosmos editorial {args.phase}; error type {type(exc).__name__}, HTTP status {status}. No private diagnostics printed.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
