"""Causal replay snapshots and a separately admitted native Foundry workflow."""
import asyncio
from collections import deque
from functools import lru_cache
import hashlib
import json
import logging
import os
import re
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


def install_analyst(app, career_service, history_store=None, provider=None, allowance=None, discussion_provider=None, live_allowance=None, report_provider=None):
    router = APIRouter(prefix='/api/analyst', tags=['Analyst Mode'])
    if provider is None and os.environ.get('COUNTERPRESS_ANALYST_MODE') == 'foundry':
        from .provider import FoundryAnalyst
        try:
            provider = FoundryAnalyst.from_env()
        except ValueError:
            logging.getLogger(__name__).warning('Analyst Mode disabled: native configuration unavailable')
    if discussion_provider is None and os.environ.get('COUNTERPRESS_ANALYST_DISCUSSION') == 'azure':
        from counterpress.adaptation.azure import load_config
        from .live import AzureLiveDiscussion
        config = load_config()
        if config: discussion_provider = AzureLiveDiscussion(config)
    if discussion_provider is None and os.environ.get('COUNTERPRESS_ANALYST_DISCUSSION') == 'foundry':
        from .provider import FoundryDiscussion
        try:
            discussion_provider = FoundryDiscussion.from_env()
        except ValueError:
            logging.getLogger(__name__).warning('Analyst discussion disabled: native configuration unavailable')
    enabled = provider is not None
    if (enabled or discussion_provider is not None) and allowance is None:
        if hasattr(history_store, 'container'):
            allowance = Allowance(CosmosStore(history_store.container))
        elif os.environ.get('COUNTERPRESS_ANALYST_LEDGER_PATH'):
            allowance = Allowance(SQLiteStore(os.environ['COUNTERPRESS_ANALYST_LEDGER_PATH']))
        else:
            logging.getLogger(__name__).warning('Analyst Mode disabled: durable allowance unavailable')
            enabled = False
            provider = None
            discussion_provider = None
    live = bool(getattr(discussion_provider, 'live', False))
    if live and live_allowance is None:
        from .live_admission import LiveAllowance
        if hasattr(history_store, 'container'):
            store = CosmosStore(history_store.container)
            store.partition = 'analyst-live-control-v1'
            live_allowance = LiveAllowance(store)
        elif os.environ.get('COUNTERPRESS_ANALYST_LEDGER_PATH'):
            live_allowance = LiveAllowance(SQLiteStore(os.environ['COUNTERPRESS_ANALYST_LEDGER_PATH'] + '.live'))
        else:
            discussion_provider = None
            live = False
    from .report import AzureMatchReport, ReportAllowance, ReportRequest, report_data
    if report_provider is None and live_allowance is not None and hasattr(discussion_provider, 'config'):
        report_provider = AzureMatchReport(discussion_provider.config)
    report_ledger = ReportAllowance(live_allowance.store) if live_allowance is not None else None
    tasks = set()
    running = {}
    viewers = {}
    cancelled_views = {}

    def prune_views():
        now = time.monotonic()
        for view, expires in list(cancelled_views.items()):
            if expires <= now:
                cancelled_views.pop(view, None)

    @router.post('/views/{view_id}/cancel')
    async def cancel_view(view_id: str):
        if not re.fullmatch(r'[a-f0-9]{32}', view_id):
            raise HTTPException(422, 'Invalid viewing session')
        prune_views()
        # Bound abandoned-session tombstones, including cancellation arriving
        # while the original request is still constructing its snapshot.
        if view_id not in cancelled_views and len(cancelled_views) >= 4096:
            raise HTTPException(429, 'Please wait a moment')
        cancelled_views[view_id] = time.monotonic() + 180
        count = 0
        for key, interested in list(viewers.items()):
            interested.discard(view_id)
            if not interested and key in running:
                running[key].cancel()
                count += 1
        return {'status': 'cancelled', 'local_jobs_cancelled': count}

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
                'matches': list(MATCHES), 'discussion_available': discussion_provider is not None,
                'discussion_runtime': 'footie_live_turn_manager' if live else 'microsoft_agent_framework' if discussion_provider else None,
                'discussion_style': 'live' if live else 'roundtable', 'match_model_allowance_usd': 2.7 if live else None,
                'cancellation_available': True, 'report_available': report_provider is not None and report_ledger is not None}

    @router.post('/matches/{match_id}/snapshot')
    async def metrics(match_id: str, body: AnalystRequest):
        return await run_in_threadpool(snapshot, match_id, body)

    async def execute(key, owner, snap, body, selected_provider, ledger, history=()):
        result = None
        try:
            result = await asyncio.wait_for(selected_provider.analyze(snap, body, history) if getattr(selected_provider, 'live', False) else selected_provider.analyze(snap, body), timeout=40 if getattr(selected_provider, 'live', False) else 125)
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
                await run_in_threadpool(ledger.finish, key, owner, result, time.time())
            except (HistoryStorageError, OSError):
                pass  # Uncertain attempts remain charged and expire by lease.
            running.pop(key, None)
            viewers.pop(key, None)

    @router.post('/matches/{match_id}/discussion')
    @router.post('/matches/{match_id}/analysis')
    async def analysis(match_id: str, body: AnalystRequest, request: Request):
        discussion = request.url.path.endswith('/discussion')
        selected_provider = discussion_provider if discussion else provider
        view_id = request.headers.get('x-analyst-view')
        if view_id is not None and not re.fullmatch(r'[a-f0-9]{32}', view_id):
            raise HTTPException(422, 'Invalid viewing session')
        prune_views()
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
                    'mode': 'discussion' if discussion and selected_provider else 'foundry' if enabled else 'metrics', 'readings': [], 'summary': None, **({'messages': []} if discussion else {})}
        if view_id in cancelled_views:
            return {**envelope, 'status': 'cancelled'}
        if selected_provider is None:
            return {**envelope, 'status': 'disabled'}
        if not snap['evidence'] or (not discussion and not snap.get('candidates')) or (discussion and cutoff.elapsed_ms < 60000):
            # Quiet/unsupported spells need no model ranking. Do not consume a
            # paid reservation or start hosted compute just to return abstention.
            return {**envelope, 'status': 'insufficient_evidence'}
        if pinned_body.through_sequence is not None:
            latest = await run_in_threadpool(snapshot, match_id, pinned_body.model_copy(update={'through_sequence': None}))
            if latest['through_sequence'] != snap['through_sequence']:
                raise HTTPException(409, 'This match view has changed. Refresh Analyst Mode.')
        ledger = live_allowance if discussion and live else allowance
        key = hashlib.sha256(json.dumps({'snapshot': snap['snapshot_id'],
            'preferences': body.model_dump(exclude={'cutoff', 'through_sequence'}),
            'manifest': selected_provider.manifest_id, 'discussion': discussion}, sort_keys=True).encode()).hexdigest()
        viewers.setdefault(key, set()).add(view_id)  # None preserves legacy viewers without cancellation.
        try:
            if discussion and live:
                from .live import choose_role
                if choose_role(snap) is None:
                    viewers.pop(key, None)
                    return {**envelope, 'status': 'insufficient_evidence'}
                context_scope = hashlib.sha256(json.dumps({'match': match_id, 'preferences': body.model_dump(exclude={'cutoff','through_sequence'}), 'source': snap.get('source_version', snap['through_sequence']), 'manifest': selected_provider.manifest_id}, sort_keys=True).encode()).hexdigest()
                job = await run_in_threadpool(ledger.reserve, key, time.time(), match_id, context_scope, snap['cutoff'])
            else:
                job = await run_in_threadpool(ledger.reserve, key, time.time())
        except (HistoryStorageError, OSError):
            if key not in running: viewers.pop(key, None)
            return {**envelope, 'status': 'unavailable'}
        if job.get('admitted') and not viewers.get(key):
            await run_in_threadpool(ledger.finish, key, job['owner'], None, time.time())
            viewers.pop(key, None)
            return {**envelope, 'status': 'cancelled'}
        if job.get('admitted'):
            task = asyncio.create_task(execute(key, job['owner'], snap, pinned_body, selected_provider, ledger, job.get('history', ())))
            running[key] = task
            tasks.add(task)
            task.add_done_callback(tasks.discard)
        if key not in running: viewers.pop(key, None)
        if view_id in cancelled_views:
            return {**envelope, 'status': 'cancelled'}
        if job['status'] == 'complete':
            return {**envelope, **job['result'], 'cached': True}
        return {**envelope, 'status': job['status']}

    def full_report_data(match_id):
        try:
            return report_data(career(), match_id)
        except KeyError:
            raise HTTPException(404, 'Match not found') from None
        except (ValueError, OSError, sqlite3.Error, HistoryStorageError):
            raise HTTPException(503, 'Match report records are temporarily unavailable') from None

    @router.get('/matches/{match_id}/report')
    async def report_preview(match_id: str):
        data = await run_in_threadpool(full_report_data, match_id)
        return {**data, 'available': report_provider is not None and report_ledger is not None,
                'maximum_cost_usd': .10, 'status': 'not_requested'}

    async def execute_report(key, owner, data, language):
        result = None
        try:
            result = await asyncio.wait_for(report_provider.analyze(data, language), timeout=135)
            latest = await run_in_threadpool(full_report_data, data['match_id'])
            if latest['source_id'] != data['source_id']: result = None
        except (Exception, asyncio.CancelledError) as exc:
            logging.getLogger(__name__).warning('analyst_report_failed stage=%s reason=%s',
                getattr(exc, 'stage', 'validation_or_timeout'),
                getattr(exc, 'reason', type(exc).__name__))
            result = None
        finally:
            try:
                await run_in_threadpool(report_ledger.finish, key, owner, result, time.time())
            except (HistoryStorageError, OSError):
                pass
            running.pop(key, None)

    @router.post('/matches/{match_id}/report')
    async def deep_report(match_id: str, body: ReportRequest):
        now = time.monotonic()
        while calls and calls[0] < now - 60: calls.popleft()
        if len(calls) >= 120: raise HTTPException(429, 'Please wait a moment')
        calls.append(now)
        data = await run_in_threadpool(full_report_data, match_id)
        envelope = {'match_id': match_id, 'source_id': data['source_id'], 'reading': None}
        if report_provider is None or report_ledger is None: return {**envelope, 'status': 'disabled'}
        from .report import VERSION
        deployment = getattr(getattr(report_provider, 'config', None), 'deployment', 'test')
        key = 'report:' + hashlib.sha256(json.dumps([VERSION, data['source_id'], body.language, deployment]).encode()).hexdigest()
        try:
            job = await run_in_threadpool(report_ledger.reserve, key, time.time(), match_id, key, {'period':2,'elapsed_ms':3600000})
        except (HistoryStorageError, OSError):
            return {**envelope, 'status': 'unavailable'}
        if job.get('admitted'):
            task = asyncio.create_task(execute_report(key, job['owner'], data, body.language))
            running[key] = task; tasks.add(task); task.add_done_callback(tasks.discard)
        if job['status'] == 'complete':
            from .report import publication_result
            try:
                result = publication_result(job['result'], data, body.language)
            except (ValueError, KeyError, TypeError):
                return {**envelope, 'status': 'unavailable'}
            return {**envelope, **result, 'cached': True}
        return {**envelope, 'status': job['status']}

    app.add_middleware(AnalystBoundary)
    app.include_router(router)
    app.state.analyst_tasks = tasks
