"""Stateless personalization endpoints: no sign-in, writes, inference or cloud calls."""
from functools import lru_cache
import sqlite3
from fastapi import APIRouter, HTTPException
from starlette.responses import JSONResponse
from counterpress.history import HistoryStorageError
from .contracts import FanRequest, HomeRequest, HistoryRequest, CompareRequest, MatchRequest
from .presentation import VERSION
from .service import FanService, PreferenceError


class FanBodyLimit:
    """Bound bodies before JSON parsing, including chunked requests."""
    def __init__(self, app, limit=16384):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not scope.get('path', '').startswith('/api/fan/'):
            return await self.app(scope, receive, send)
        data = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            data.extend(message.get('body', b''))
            if len(data) > self.limit:
                return await JSONResponse({'detail': 'Preference request is too large'}, status_code=413,
                    headers={'Cache-Control': 'no-store'})(scope, receive, send)
            if not message.get('more_body', False):
                break
        delivered = False

        async def buffered():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(data), 'more_body': False}
            return await receive()

        async def private_send(message):
            if message['type'] == 'http.response.start':
                headers = list(message.get('headers', []))
                headers = [(k, v) for k, v in headers if k.lower() != b'cache-control']
                message = {**message, 'headers': headers + [(b'cache-control', b'private, no-store')]}
            await send(message)

        await self.app(scope, buffered, private_send)


def install_fan(app, career_service, snapshots=None):
    router = APIRouter(prefix='/api/fan', tags=['Fan personalization'])

    @lru_cache(maxsize=1)
    def service():
        return FanService(career_service(), snapshots)

    def call(fn):
        try:
            s = service()
            # One consistent revision snapshot for all cards, baselines and focus.
            with s.store.lock:
                return fn(s)
        except PreferenceError as exc:
            raise HTTPException(422, str(exc)) from None
        except KeyError:
            raise HTTPException(404, 'Player, club or match not found') from None
        except (ValueError, OSError, sqlite3.Error, HistoryStorageError):
            raise HTTPException(503, 'Personalized view is temporarily unavailable') from None

    @router.get('/capabilities')
    def capabilities():
        return {'version': VERSION, 'preference_version': 1, 'storage': 'device',
                'languages': ['en', 'zh-Hans'], 'depths': ['casual', 'analyst'],
                'metric_focus': ['balanced', 'scoring', 'creating', 'passing', 'defending'],
                'limits': {'favorite_clubs': 4, 'favorite_players': 12, 'comparison_players': 4, 'body_bytes': 16384},
                'assistant_available': False, 'cross_device_sync': False,
                'catalog_url': '/api/data/catalog', 'players_url': '/api/data/players?featured=false'}

    @router.post('/preferences/validate')
    def validate(request: FanRequest):
        return call(lambda s: s.envelope(request))

    @router.post('/home')
    def home(request: HomeRequest):
        return call(lambda s: s.home(request))

    @router.post('/players/compare')
    def compare(request: CompareRequest):
        return call(lambda s: s.compare(request))

    @router.post('/players/{player_id}')
    def player(player_id: str, request: HistoryRequest):
        return call(lambda s: s.profile(player_id, 'player', request))

    @router.post('/clubs/{club_id}')
    def club(club_id: str, request: HistoryRequest):
        return call(lambda s: s.profile(club_id, 'club', request))

    @router.post('/matches/{match_id}')
    def match(match_id: str, request: MatchRequest):
        return call(lambda s: s.match(match_id, request))

    app.add_middleware(FanBodyLimit)
    app.include_router(router)
    # Read-only capability for local verification; no preferences live here.
    app.state.fan_service = service
