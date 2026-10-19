"""Read-only, bounded UI/agent contracts. No new model or cloud calls."""
from functools import lru_cache
from datetime import datetime
import json
import os
import sqlite3
from pathlib import Path
from typing import Literal
from fastapi import HTTPException,Query,Response
from .metrics import select_events,action_metrics
from .replay import native_feed,highlight_feed
from counterpress.fixture import PossessionFixture
from .service import CareerService,match_card
from .store import DataStore


def install_personalization(app,root:Path):
    @lru_cache(maxsize=1)
    def service():
        return CareerService(DataStore(root/'personalization',os.environ.get('COUNTERPRESS_PROFILE_DB_PATH',':memory:')))

    def call(fn):
        try:return fn(service())
        except KeyError:raise HTTPException(404,'Player, club or match not found') from None
        except (OSError,ValueError,sqlite3.Error):raise HTTPException(503,'Career data is unavailable or failed validation') from None

    def date(value):
        if value is not None:
            try:datetime.strptime(value,'%Y-%m-%dT%H:%M:%SZ')
            except ValueError:raise HTTPException(422,'before must be a UTC timestamp such as 2026-10-19T15:00:00Z') from None
        return value

    @app.get('/api/data/catalog',tags=['Career data'])
    def catalog():
        return call(lambda s:{'version':s.store.manifest['version'],
            'clubs':[c.model_dump(mode='json') for c in s.store.clubs.values()],
            'seasons':sorted({r['season'] for r in s.store.rows()},reverse=True),
            'counts':{k:s.store.manifest[k] for k in ('featured_clubs','featured_players','historical_matches','featured_matches','total_events')},
            'coordinates':{'pitch_m':[105,68],'attacking_direction':'positive_x','comparison_window':'(start,end]'},
            'metric_definitions':'/api/data/metrics','calibration':s.store.model['provenance']})

    @app.get('/api/data/metrics',tags=['Career data'])
    def definitions():
        try:return json.loads((root/'personalization/metric-definitions.json').read_text())
        except (OSError,ValueError):raise HTTPException(503,'Metric definitions unavailable') from None

    @app.get('/api/data/players',tags=['Career data'])
    def players(featured:bool=True,club_id:str|None=None,role:Literal['GK','DF','MF','FW']|None=None,
                q:str=Query('',max_length=80),offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100)):
        def read(s):
            if club_id and club_id not in s.store.clubs:raise KeyError(club_id)
            rows=[p.model_dump(mode='json',exclude={'involvement','passing','finishing'}) for p in s.store.players.values() if (not featured or p.featured)
                and (not club_id or p.club_id==club_id) and (not role or p.role==role) and q.casefold() in p.name.casefold()]
            return {'total':len(rows),'offset':offset,'limit':limit,'items':rows[offset:offset+limit]}
        return call(read)

    @app.get('/api/data/players/{player_id}',tags=['Career data'])
    def player_profile(player_id:str,season:str|None=None,before:str|None=None):
        cutoff=date(before);return call(lambda s:s.profile(player_id,season=season,before=cutoff))

    @app.get('/api/data/players/{player_id}/matches',tags=['Career data'])
    def player_history(player_id:str,season:str|None=None,before:str|None=None,offset:int=Query(0,ge=0),limit:int=Query(20,ge=1,le=100)):
        cutoff=date(before);return call(lambda s:s.history(player_id,season=season,before=cutoff,offset=offset,limit=limit))

    @app.get('/api/data/clubs/{club_id}',tags=['Career data'])
    def club_profile(club_id:str,season:str|None=None,before:str|None=None):
        cutoff=date(before);return call(lambda s:s.profile(club_id,'club',season,before=cutoff))

    @app.get('/api/data/clubs/{club_id}/matches',tags=['Career data'])
    def club_history(club_id:str,season:str|None=None,offset:int=Query(0,ge=0),limit:int=Query(20,ge=1,le=100)):
        return call(lambda s:s.history(club_id,'club',season,offset=offset,limit=limit))

    @app.get('/api/data/standings/{season}',tags=['Career data'])
    def standings(season:str):
        return call(lambda s:s.standings(season))

    @app.get('/api/data/matches',tags=['Career data'])
    def matches(featured:bool=True,club_id:str|None=None,season:str|None=None,offset:int=Query(0,ge=0),limit:int=Query(20,ge=1,le=100)):
        def read(s):
            if club_id and club_id not in s.store.clubs:raise KeyError(club_id)
            rows=s.store.rows(club=club_id,season=season,featured=True if featured else None)
            return {'total':len(rows),'offset':offset,'limit':limit,'items':[match_card(r,s.store.summary(r['id'])) for r in rows[offset:offset+limit]]}
        return call(read)

    @app.get('/api/data/matches/{match_id}',tags=['Career data'])
    def match(match_id:str):
        return call(lambda s:{'fixture':json.loads(s.store.row(match_id)['fixture']),'summary':s.store.summary(match_id)})

    @app.get('/api/data/matches/{match_id}/events',tags=['Career data'])
    def events(match_id:str,offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=500),player_id:str|None=None):
        def read(s):
            if player_id and player_id not in s.store.players:raise KeyError(player_id)
            rows=[e for e in select_events(s.store.events(match_id)) if not player_id or player_id in (e.player_id,e.recipient_id,e.opponent_id,e.goalkeeper_id)]
            return {'match_id':match_id,'total':len(rows),'offset':offset,'limit':limit,'items':[{**e.model_dump(mode='json'),'metrics':action_metrics(e)} for e in rows[offset:offset+limit]]}
        return call(read)

    @app.get('/api/data/matches/{match_id}/replay',response_model=PossessionFixture,tags=['Career data'])
    def replay(match_id:str):
        def read(s):
            record=s.store.original(match_id)
            if not record.fixture.featured:raise HTTPException(422,'Historical fixtures are available through player history and events')
            if record.fixture.source_kind=='adapted_archive':raise HTTPException(422,'Use /api/gi/matches/{match_id} for archive replay')
            if s.store.evidence_digest(match_id)!=s.store.row(match_id)['digest']:raise HTTPException(409,'Replay has revisions; read current events before rendering')
            # Revisions are exposed through /events and /live. V1 pitch fixtures
            # intentionally accept only their validated initial revisions.
            return native_feed(record,s.store.clubs)
        return call(read)

    @app.get('/api/data/matches/{match_id}/live',tags=['Career data'])
    def live(match_id:str,response:Response,period:int=Query(1,ge=1,le=2),elapsed_ms:int=Query(0,ge=0),player_id:str|None=None,
             through_sequence:int|None=Query(None,ge=0)):
        response.headers['Cache-Control']='no-store'
        def read(s):
            f=json.loads(s.store.row(match_id)['fixture'])
            if elapsed_ms>f['period_lengths_ms'][period-1]+60000:raise HTTPException(422,'Cutoff outside match')
            return s.live(match_id,period,elapsed_ms,player_id,through_sequence)
        return call(read)

    @app.get('/api/data/matches/{match_id}/insight-changes',tags=['Career data'])
    def changes(match_id:str,response:Response,period:int=Query(ge=1,le=2),elapsed_ms:int=Query(ge=0),since_sequence:int=Query(ge=0)):
        response.headers['Cache-Control']='no-store'
        return call(lambda s:s.changes(match_id,period,elapsed_ms,since_sequence))

    @app.get('/api/data/matches/{match_id}/window',tags=['Career data'])
    def window(match_id:str,start_period:int=Query(ge=1,le=2),start_ms:int=Query(ge=0),end_period:int=Query(ge=1,le=2),end_ms:int=Query(ge=0)):
        def read(s):
            f=json.loads(s.store.row(match_id)['fixture']);start=(start_period,start_ms);end=(end_period,end_ms)
            if start>=end or any(t[1]>f['period_lengths_ms'][t[0]-1] for t in (start,end)):raise HTTPException(422,'Invalid comparison window')
            return s.window(match_id,start,end)
        return call(read)

    @app.get('/api/data/highlights',tags=['Career data'])
    def highlights():
        return call(lambda s:json.loads((s.store.root/'highlights.json').read_text()))

    @app.get('/api/data/highlights/{highlight_id}/replay',response_model=PossessionFixture,tags=['Career data'])
    def highlight(highlight_id:str):
        def read(s):
            clips=json.loads((s.store.root/'highlights.json').read_text());clip=next((c for c in clips if c['highlight_id']==highlight_id),None)
            if not clip:raise KeyError(highlight_id)
            mid=clip['match_id']
            if s.store.evidence_digest(mid)!=s.store.row(mid)['digest']:raise HTTPException(409,'Highlight source has revisions; read current events before rendering')
            return highlight_feed(native_feed(s.store.original(mid),s.store.clubs),clip)
        return call(read)
