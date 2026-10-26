"""Causal replay snapshots and a separately admitted native Foundry workflow."""
import asyncio
from collections import deque
from functools import lru_cache
import hashlib
import json
import logging
import os
import sqlite3
import time

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, Response

from counterpress.gi.service import MATCHES
from counterpress.history import HistoryStorageError
from .admission import Allowance, CosmosStore, SQLiteStore
from .contracts import AnalystRequest
from .service import build_snapshot

ROLES = [
    {'id': 'chance', 'name': 'Chances', 'description': 'How attacks become dangerous'},
    {'id': 'defence', 'name': 'Transitions', 'description': 'What happens when the ball changes hands'},
    {'id': 'control', 'name': 'Control', 'description': 'Who is shaping the game and how'},
    {'id': 'players', 'name': 'Player impact', 'description': 'The people changing the match'},
]


class AnalystBoundary:
    """No cross-site paid requests; bound JSON before parsing, including chunks."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not scope.get('path', '').startswith('/api/analyst/'):
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        origin = headers.get(b'origin')
        host = headers.get(b'host', b'')
        if origin and origin not in (b'http://' + host, b'https://' + host):
            return await JSONResponse({'detail': 'Open Analyst Mode from Footie.'}, status_code=403)(scope, receive, send)
        data = bytearray()
        while True:
            msg = await receive()
            if msg['type'] == 'http.disconnect':
                return await Response(status_code=499)(scope, receive, send)
            data.extend(msg.get('body', b''))
            if len(data) > 4096:
                return await JSONResponse({'detail': 'Request is too large'}, status_code=413)(scope, receive, send)
            if not msg.get('more_body', False):
                break
        delivered = False
        async def buffered():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(data), 'more_body': False}
            return await receive()
        async def private_send(msg):
            if msg['type'] == 'http.response.start':
                msg = {**msg, 'headers': [(k, v) for k, v in msg.get('headers', []) if k.lower() != b'cache-control'] + [(b'cache-control', b'private, no-store')]}
            await send(msg)
        await self.app(scope, buffered, private_send)


def install_analyst(app, career_service, history_store=None, provider=None, allowance=None):
    router = APIRouter(prefix='/api/analyst', tags=['Analyst Mode'])
    if provider is None and os.environ.get('COUNTERPRESS_ANALYST_MODE') == 'foundry':
        from .provider import FoundryAnalyst
        try:
            provider = FoundryAnalyst.from_env()
        except ValueError:
            logging.getLogger(__name__).warning('Analyst Mode disabled: native configuration unavailable')
    enabled = provider is not None
    if enabled and allowance is None:
        if hasattr(history_store, 'container'):
            allowance = Allowance(CosmosStore(history_store.container))
        elif os.environ.get('COUNTERPRESS_ANALYST_LEDGER_PATH'):
            allowance = Allowance(SQLiteStore(os.environ['COUNTERPRESS_ANALYST_LEDGER_PATH']))
        else:
            logging.getLogger(__name__).warning('Analyst Mode disabled: durable allowance unavailable')
            enabled = False
            provider = None
    tasks = set()
    calls = deque()
    @lru_cache(maxsize=1)
    def career():
        return career_service()

    def snapshot(mid, body):
        if mid not in MATCHES:
            raise HTTPException(404, 'This match is not available in Analyst Mode')
        try:
            with career().store.snapshot():
                return build_snapshot(career(), mid, body)
        except KeyError:
            raise HTTPException(404, 'Match or player not found') from None
        except ValueError:
            raise HTTPException(422, 'Choose a valid playback boundary and player') from None
        except (OSError, sqlite3.Error, HistoryStorageError):
            raise HTTPException(503, 'Match records are temporarily unavailable') from None

    @router.get('/config')
    def config():
        return {'available': enabled, 'mode': 'foundry' if enabled else 'metrics',
                'roles': ROLES, 'interval_ms': 60000, 'max_calls_per_run': 5,
                'matches': list(MATCHES)}

    @router.post('/matches/{match_id}/snapshot')
    async def metrics(match_id: str, body: AnalystRequest):
        return await run_in_threadpool(snapshot, match_id, body)

    async def execute(key, owner, snap, body):
        result = None
        try:
            result = await asyncio.wait_for(provider.analyze(snap, body), timeout=125)
            # A native run may outlive a correction. Re-check the same pinned
            # view AND newly received revisions before publishing its prose.
            latest = await run_in_threadpool(snapshot, snap['match_id'], body.model_copy(update={'through_sequence': None}))
            current = await run_in_threadpool(snapshot, snap['match_id'], body)
            if latest['through_sequence'] != snap['through_sequence'] or current['snapshot_id'] != snap['snapshot_id']:
                result = None
        except (Exception, asyncio.CancelledError):
            # Cloud URLs, SDK errors and raw model text never enter logs/UI.
            result = None
        finally:
            try:
                await run_in_threadpool(allowance.finish, key, owner, result, time.time())
            except (HistoryStorageError, OSError):
                pass  # Uncertain attempts remain charged and expire by lease.

    @router.post('/matches/{match_id}/analysis')
    async def analysis(match_id: str, body: AnalystRequest, request: Request):
        now = time.monotonic()
        while calls and calls[0] < now - 60:
            calls.popleft()
        if len(calls) >= 120:
            raise HTTPException(429, 'Please wait a moment', headers={'Retry-After': '30'})
        calls.append(now)
        # Shared minute boundaries prevent one paid run per event or viewer.
        cutoff = body.cutoff.model_copy(update={'elapsed_ms': body.cutoff.elapsed_ms // 60000 * 60000})
        pinned_body = body.model_copy(update={'cutoff': cutoff})
        snap = await run_in_threadpool(snapshot, match_id, pinned_body)
        envelope = {'snapshot_id': snap['snapshot_id'], 'match_id': match_id, 'cutoff': snap['cutoff'],
                    'mode': 'foundry' if enabled else 'metrics', 'readings': [], 'summary': None}
        if not enabled:
            return {**envelope, 'status': 'disabled'}
        if not snap['evidence']:
            return {**envelope, 'status': 'insufficient_evidence'}
        if pinned_body.through_sequence is not None:
            latest = await run_in_threadpool(snapshot, match_id, pinned_body.model_copy(update={'through_sequence': None}))
            if latest['through_sequence'] != snap['through_sequence']:
                raise HTTPException(409, 'This match view has changed. Refresh Analyst Mode.')
        key = hashlib.sha256(json.dumps({'snapshot': snap['snapshot_id'],
            'preferences': body.model_dump(exclude={'cutoff', 'through_sequence'}),
            'manifest': provider.manifest_id}, sort_keys=True).encode()).hexdigest()
        try:
            job = await run_in_threadpool(allowance.reserve, key, time.time())
        except (HistoryStorageError, OSError):
            return {**envelope, 'status': 'unavailable'}
        if job.get('admitted'):
            task = asyncio.create_task(execute(key, job['owner'], snap, pinned_body))
            tasks.add(task)
            task.add_done_callback(tasks.discard)
        if job['status'] == 'complete':
            return {**envelope, **job['result'], 'cached': True}
        return {**envelope, 'status': job['status']}

    app.add_middleware(AnalystBoundary)
    app.include_router(router)
    app.state.analyst_tasks = tasks
