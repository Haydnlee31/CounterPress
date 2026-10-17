"""Opt-in delegated producer access; never needs model credentials."""
from dataclasses import dataclass
import os
import sqlite3
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool

from counterpress.audience import PreferenceError
from counterpress.editorial.auth import AccessDenied, EntraSettings, EntraVerifier
from counterpress.history import HistoryStorageError, SQLiteHistoryStore
from counterpress.studio.service import DecisionRequest, ReviewConflict, ReviewRequest, ReviewView, StudioService


@dataclass(frozen=True)
class StudioAccess:
    verifier: EntraVerifier
    client_id: str

    def __post_init__(self):
        if str(UUID(self.client_id)) != self.client_id or self.client_id not in self.verifier.settings.client_ids:
            raise ValueError('Studio client must be a canonical allowed client UUID')


def configure_studio(snapshots):
    mode = os.environ.get('COUNTERPRESS_STUDIO', 'off')
    if mode == 'off':
        return None
    if mode != 'entra':
        raise ValueError('COUNTERPRESS_STUDIO must be off or entra')
    if isinstance(snapshots.store, SQLiteHistoryStore) and snapshots.store.path == ':memory:':
        raise ValueError('Studio requires durable storage')
    client = os.environ.get('COUNTERPRESS_STUDIO_CLIENT_ID', '')
    # Studio is separately allowlisted; a desktop editor token cannot open it.
    settings = EntraSettings(os.environ.get('COUNTERPRESS_ENTRA_TENANT_ID', ''),
                             os.environ.get('COUNTERPRESS_ENTRA_AUDIENCE', ''), (client,))
    return StudioAccess(EntraVerifier(settings), client)


def install_studio(application, snapshots, configured):
    router = APIRouter(prefix='/api/studio', tags=['studio'])
    service, bearer = StudioService(snapshots), HTTPBearer(auto_error=False)

    @application.middleware('http')
    async def headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith('/api/studio'):
            response.headers.update({'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
                                     'X-Content-Type-Options': 'nosniff'})
        return response

    async def authorize(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if configured is None:
            raise HTTPException(503, 'Studio is not enabled on this deployment.')
        if credentials is None:
            raise HTTPException(401, 'Sign in with an assigned editor account.', headers={'WWW-Authenticate': 'Bearer'})
        try:
            return await run_in_threadpool(configured.verifier.verify, credentials.credentials)
        except AccessDenied as exc:
            raise HTTPException(exc.status, 'Studio access could not be authorized.') from None

    @router.get('/config')
    def config():
        if configured is None:
            return {'enabled': False}
        settings = configured.verifier.settings
        # Public identity metadata only. No model/storage URLs, secrets or tokens.
        return {'enabled': True, 'client_id': configured.client_id,
                'authority': f'https://login.microsoftonline.com/{settings.tenant_id}',
                'scope': f'api://{settings.audience}/Editorial.Run'}

    async def invoke(function, *args):
        try:
            return await run_in_threadpool(function, *args)
        except ReviewConflict as exc:
            raise HTTPException(409, str(exc)) from None
        except KeyError:
            raise HTTPException(404, 'Unknown scenario.') from None
        except PreferenceError:
            raise HTTPException(422, 'The requested perspective is unavailable.') from None
        except (ValueError, OSError, sqlite3.Error, HistoryStorageError):
            raise HTTPException(503, 'Review storage is unavailable. Approval cannot be verified.') from None

    @router.post('/{scenario}/review', response_model=ReviewView)
    async def review(scenario: str, request: ReviewRequest, actor=Depends(authorize)):
        return await invoke(service.review, scenario, request)

    @router.post('/{scenario}/approve', response_model=ReviewView)
    async def approve(scenario: str, request: DecisionRequest, actor=Depends(authorize)):
        return await invoke(service.decide, scenario, request, actor, 'approve')

    @router.post('/{scenario}/revoke', response_model=ReviewView)
    async def revoke(scenario: str, request: DecisionRequest, actor=Depends(authorize)):
        return await invoke(service.decide, scenario, request, actor, 'revoke')

    @router.post('/{scenario}/export')
    async def export(scenario: str, request: DecisionRequest, actor=Depends(authorize)):
        content = await invoke(service.export, scenario, request)
        return Response(content, media_type='text/html', headers={
            'Content-Disposition': 'attachment; filename="counterpress-producer-snapshot.html"',
            'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'"})

    application.include_router(router)
