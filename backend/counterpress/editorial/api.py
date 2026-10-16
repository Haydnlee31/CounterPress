"""Private opt-in API. Public snapshots and health never trigger an editor."""

import os
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool

from counterpress.adaptation.azure import load_config
from counterpress.audience import PreferenceError
from counterpress.api.snapshots import PlaybackRangeError
from counterpress.cosmos_history import CosmosHistoryStore
from counterpress.history import HistoryStorageError, SQLiteHistoryStore
from counterpress.editorial.auth import AccessDenied, EntraSettings, EntraVerifier
from counterpress.editorial.ledger import CosmosLedgerStore, Ledger, SQLiteLedgerStore
from counterpress.editorial.service import ContextRequest, EditorialController, EditorialRequest, EditorialContext, EditorialResult


def configure_editorial(snapshots):
    mode = os.environ.get('COUNTERPRESS_EDITORIAL', 'off')
    if mode == 'off':
        return None
    if mode != 'entra':
        raise ValueError('COUNTERPRESS_EDITORIAL must be off or entra')
    settings = EntraSettings(os.environ.get('COUNTERPRESS_ENTRA_TENANT_ID', ''),
        os.environ.get('COUNTERPRESS_ENTRA_AUDIENCE', ''),
        tuple(v.strip() for v in os.environ.get('COUNTERPRESS_ENTRA_CLIENT_IDS', '').split(',') if v.strip()))
    config = load_config()
    if config is None:
        raise ValueError('Editorial activation requires private model configuration')
    store = snapshots.store
    if isinstance(store, CosmosHistoryStore):
        ledger_store = CosmosLedgerStore(store.container)
    elif isinstance(store, SQLiteHistoryStore) and store.path != ':memory:':
        ledger_store = SQLiteLedgerStore(store.path)
    else:
        raise ValueError('Editorial activation requires durable shared storage')
    return EditorialController(snapshots, config, Ledger(ledger_store)), EntraVerifier(settings)


def install_editorial(application, configured):
    router = APIRouter(prefix='/api/editorial', tags=['editorial'])
    bearer = HTTPBearer(auto_error=False)

    async def authorize(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if configured is None:
            raise HTTPException(503, 'Editorial requests are disabled.')
        if credentials is None:
            raise HTTPException(401, 'An editor access token is required.', headers={'WWW-Authenticate': 'Bearer'})
        try:
            return await run_in_threadpool(configured[1].verify, credentials.credentials)
        except AccessDenied as exc:
            raise HTTPException(exc.status, 'Editor access could not be authorized.',
                                headers={'WWW-Authenticate': 'Bearer'} if exc.status == 401 else None) from None

    @application.middleware('http')
    async def editorial_headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith('/api/editorial'):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    async def invoke(call):
        try:
            return await call
        except KeyError:
            raise HTTPException(404, 'Unknown scenario.') from None
        except (PreferenceError, PlaybackRangeError):
            raise HTTPException(422, 'The requested replay or preferences are unavailable.') from None
        except (ValueError, OSError, sqlite3.Error, HistoryStorageError):
            raise HTTPException(503, 'Editorial storage is unavailable; the factual recap remains available.') from None

    @router.post('/{scenario_id}/context', response_model=EditorialContext)
    async def context(scenario_id: str, request: ContextRequest, editor=Depends(authorize)):
        # Explicit read of the current revision and preferences. No paid work.
        return await invoke(configured[0].context(scenario_id, request.at_ms, request.preferences))

    @router.post('/{scenario_id}/run', response_model=EditorialResult)
    async def run(scenario_id: str, request: EditorialRequest, response: Response, editor=Depends(authorize)):
        result = await invoke(configured[0].run(scenario_id, request, editor))
        response.status_code = {'pending': 202, 'busy': 429, 'quota_exceeded': 429, 'stale': 409}.get(result.status, 200)
        if result.status in ('pending', 'busy'):
            response.headers['Retry-After'] = '30'
        return result

    application.include_router(router)
