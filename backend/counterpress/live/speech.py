"""Event-only speech: no caller text/SSML, private Azure auth, durable quota and cache."""
from collections import deque
from datetime import datetime, timezone
from functools import lru_cache
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from threading import Lock
from time import monotonic
from typing import Literal
from xml.sax.saxutils import escape

from fastapi import HTTPException, Response
from pydantic import Field
from counterpress.api.snapshots import SCENARIOS
from counterpress.domain.models import Contract, MatchTime
from counterpress.fixture import load_fixture
from counterpress.live.api import MATCH_ID

NAMES = dict(zip(
    [f'{team}{n:02}' for team in ('eb','np') for n in range(1,12)],
    ['Theo Ashford','Finn Brooks','Oliver Hayes','Alex Rowan','Elliot Reed','Jamie Vale','Lucas Hart','Kai Mercer','Rory Ellis','Milo West','Owen Cole',
     'Arthur Wells','Ben Fletcher','Callum Stone','Noah Arden','Dylan Frost','Sam Linden','Evan Shore','Leo Marlow','Henry Blake','Isaac Lane','Jude Rivers']))
MONTHLY_CHARACTERS = 200_000


class HighlightRequest(Contract):
    match_id: str = Field(min_length=1, max_length=100)
    events: list[str] = Field(min_length=1, max_length=20)
    revisions: list[int] = Field(min_length=1, max_length=20)
    language: Literal['en', 'zh-Hans'] = 'en'


class SpeechRequest(Contract):
    match_id: str = Field(min_length=1, max_length=100)
    events: list[str] = Field(min_length=1, max_length=4)
    revisions: list[int] = Field(min_length=1, max_length=4)
    cutoff: MatchTime
    language: Literal['en', 'zh-Hans'] = 'en'
    detailed: bool = False
    delivery: Literal['summary', 'highlight-action', 'highlight-result'] = 'summary'


def phrase(events, zh=False, detailed=False, delivery='summary'):
    shot = next((e for e in reversed(events) if e.action.kind == 'shot'), None)
    e = shot or events[-1]
    a = e.action
    name = NAMES[e.actor.player_id]
    club = 'Eastbridge' if e.actor.team_id == 'eastbridge' else 'Northport'
    if not shot and len(events)>1 and all(x.action.kind=='pass' and x.action.outcome=='completed' and x.actor.team_id==e.actor.team_id for x in events):
        target = NAMES[a.recipient.player_id]
        text = f'{club}完成{len(events)}次传球，球来到{target}脚下。' if zh else f'{club} complete {len(events)} passes, finding {target}.'
    elif a.kind == 'shot':
        if a.outcome == 'goal': text = f'进球了！{name}射门得分！' if zh else f'Goal! {name} fires it home!'
        elif a.outcome == 'saved': text = f'{name}射门，门将扑出！' if zh else f'{name} shoots! Saved by {NAMES[a.goalkeeper.player_id]}!'
        elif a.outcome == 'blocked': text = f'{name}射门被挡出！' if zh else f'{name} shoots! Blocked!'
        else: text = f'{name}射门偏出！' if zh else f'{name} shoots! Off target.'
    elif a.kind == 'pass':
        if a.outcome == 'completed': text = f'{name}传给{NAMES[a.recipient.player_id]}。' if zh else f'{name} finds {NAMES[a.recipient.player_id]}.'
        else: text = f'{name}的传球未能找到队友。' if zh else f'{name} cannot find a teammate.'
    elif a.kind == 'carry': text = f'{name}带球推进。' if zh else f'{name} carries the ball.'
    elif a.kind == 'recovery':
        if a.origin == 'restart': text = f'{name}重新开球。' if zh else f'{name} restarts play.'
        else: text = f'{name}赢回球权！' if zh else f'{name} wins it back!'
    else: text = f'{name}{"赢得" if a.outcome=="won" else "输掉"}争抢。' if zh else f'{name} {"wins" if a.outcome=="won" else "loses"} the challenge.'
    if detailed:
        zone = ('前场' if e.position.x>=70 else '中场' if e.position.x>=35 else '后场') if zh else ('near the opposition goal' if e.position.x>=70 else 'in midfield' if e.position.x>=35 else 'deep in their own half')
        text += f' {club}，{zone}。' if zh else f' {club}, {zone}.'
    if delivery == 'highlight-action':
        # A short actor call follows the ball, without announcing an unseen outcome.
        text = name.split()[-1] + ('！' if a.kind == 'shot' else '。') if zh else name.split()[-1] + ('!' if a.kind == 'shot' else '.')
    elif delivery == 'highlight-result':
        text = {'goal': ('Goal!', '进球了！'), 'saved': ('Saved!', '扑出！'),
                'blocked': ('Blocked!', '挡出！'), 'off_target': ('Wide!', '偏了！')}.get(a.outcome, ('Wide!', '偏了！'))[int(zh)]
    exciting = bool(shot)
    voice = 'zh-CN-YunjianNeural' if zh else 'en-US-GuyNeural'
    style = ('sports-commentary-excited' if exciting else 'sports-commentary') if zh else ('excited' if exciting else 'newscast')
    lang = 'zh-CN' if zh else 'en-US'
    ssml = f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="{lang}"><voice name="{voice}"><mstts:express-as style="{style}" styledegree="1.3">{escape(text)}</mstts:express-as></voice></speak>'
    return text, ssml


class SpeechLimit(Exception): pass


class AzureSpeech:
    """Private cache and conditional monthly counter survive restarts and deployments."""
    def __init__(self):
        from azure.identity import AzureCliCredential, ManagedIdentityCredential
        from azure.storage.blob import ContainerClient
        endpoint = os.environ.get('COUNTERPRESS_SPEECH_ENDPOINT', '')
        if not re.fullmatch(r'https://[a-z0-9-]+\.cognitiveservices\.azure\.com',endpoint):
            raise ValueError('Speech endpoint is not configured')
        if os.environ.get('COUNTERPRESS_SPEECH_TIER') != 'F0':
            raise ValueError('Speech requires the reviewed free tier')
        self.endpoint = endpoint
        self.credential = AzureCliCredential(process_timeout=10) if os.environ.get('COUNTERPRESS_SPEECH_AUTH')=='azure-cli' else ManagedIdentityCredential(client_id=os.environ.get('COUNTERPRESS_STREAM_CLIENT_ID'))
        self.cache = ContainerClient(os.environ['COUNTERPRESS_CHECKPOINT_ENDPOINT'], container_name='speech-cache', credential=self.credential, connection_timeout=5, read_timeout=10, retry_total=1, logging_enable=False)
        self.lock = Lock()
        self.requests = deque()

    def reserve(self, amount):
        from azure.core import MatchConditions
        from azure.core.exceptions import ResourceNotFoundError, ResourceExistsError, ResourceModifiedError
        name = 'quota/' + datetime.now(timezone.utc).strftime('%Y-%m') + '.json'
        blob = self.cache.get_blob_client(name)
        for _ in range(5):
            try:
                result = blob.download_blob()
                used = json.loads(result.readall())['characters']
                etag = result.properties.etag
            except ResourceNotFoundError:
                used, etag = 0, None
            if type(used) is not int or used < 0 or used + amount > MONTHLY_CHARACTERS: raise SpeechLimit()
            try:
                data = json.dumps({'characters':used+amount})
                if etag: blob.upload_blob(data,overwrite=True,etag=etag,match_condition=MatchConditions.IfNotModified)
                else: blob.upload_blob(data,overwrite=False)
                return
            except (ResourceExistsError, ResourceModifiedError): continue
        raise SpeechLimit()

    @lru_cache(maxsize=128)
    def audio(self, text, ssml):
        import httpx
        from azure.core.exceptions import ResourceNotFoundError
        key = 'audio/v1/' + sha256(ssml.encode()).hexdigest() + '.mp3'
        blob = self.cache.get_blob_client(key)
        # One application replica; also serializes identical cache misses.
        with self.lock:
            try:
                result = blob.download_blob()
                if result.size > 1_000_000: raise ValueError('Invalid audio')
                return result.readall()
            except ResourceNotFoundError: pass
            now = monotonic()
            while self.requests and self.requests[0] < now-60: self.requests.popleft()
            if len(self.requests) >= 15: raise SpeechLimit()
            self.requests.append(now)
            # Conservative CJK weighting. Failed attempts remain reserved; never refund a possibly billed call.
            self.reserve(sum(2 if ord(char)>127 else 1 for char in text))
            token = self.credential.get_token('https://cognitiveservices.azure.com/.default').token
            response = httpx.post(self.endpoint+'/tts/cognitiveservices/v1',content=ssml.encode(),headers={
                'Authorization':'Bearer '+token,'Content-Type':'application/ssml+xml',
                'X-Microsoft-OutputFormat':'audio-24khz-48kbitrate-mono-mp3','User-Agent':'CounterPress'},timeout=12)
            response.raise_for_status()
            audio = response.content
            if not audio or len(audio)>1_000_000: raise ValueError('Invalid audio')
            blob.upload_blob(audio,overwrite=True)
            return audio


def install_speech(app, root:Path, adapter=None):
    @lru_cache(maxsize=1)
    def corpus():
        paths = [root / path for path,_ in SCENARIOS.values()] + [root/'gi/synthetic/events.json']
        result = {}
        for path in dict.fromkeys(paths):
            feed=load_fixture(path)
            result[feed.match_id] = feed.events
        return result

    @lru_cache(maxsize=1)
    def service(): return adapter or AzureSpeech()

    def enabled(): return adapter is not None or os.environ.get('COUNTERPRESS_SPEECH')=='azure'

    @app.get('/api/voice/config')
    def config(): return {'azure':enabled(), 'languages':['en','zh-Hans']}

    @app.post('/api/voice/commentary')
    def commentary(request:SpeechRequest):
        if not enabled(): raise HTTPException(503,'Broadcast voice is unavailable')
        try: source=corpus().get(request.match_id)
        except (ValueError,OSError,KeyError): raise HTTPException(503,'Voice sources are unavailable') from None
        if not source: raise HTTPException(404,'Unknown match')
        indexes={e.event_id:i for i,e in enumerate(source)}
        positions=[indexes.get(e,-1) for e in request.events]
        # Contiguous observed records only: no arbitrary SSML, text, actor names or voice IDs.
        if -1 in positions or positions != list(range(positions[0],positions[0]+len(positions))) or len(request.revisions)!=len(positions):
            raise HTTPException(422,'Choose up to four consecutive actions')
        events=[source[i] for i in positions]
        if any(e.revision!=revision or e.available_at.key()>request.cutoff.key() or e.occurred_at.key()>request.cutoff.key() for e,revision in zip(events,request.revisions)):
            raise HTTPException(409,'Actions are not available at this playback position')
        if request.delivery != 'summary':
            if len(events) != 1 or not request.match_id.startswith('showcase-') or request.detailed:
                raise HTTPException(422,'Choose one highlight action')
            if request.delivery == 'highlight-result' and events[0].action.kind != 'shot':
                raise HTTPException(422,'Choose a shot result')
        text,ssml=phrase(events,request.language=='zh-Hans',request.detailed,request.delivery)
        try: audio=service().audio(text,ssml)
        except SpeechLimit: raise HTTPException(429,'Broadcast voice is resting; device voice is available',headers={'Retry-After':'60'}) from None
        except Exception: raise HTTPException(503,'Broadcast voice is temporarily unavailable') from None
        return Response(audio,media_type='audio/mpeg',headers={'Cache-Control':'private, max-age=86400','X-Content-Type-Options':'nosniff'})

    @lru_cache(maxsize=24)
    def recorded_track(key):
        # Optional local preview directory; production reads only the private Blob cache.
        local=os.environ.get('COUNTERPRESS_COMMENTARY_DIR')
        if local: raw=(Path(local)/(key+'.json')).read_bytes()
        else:
            download=service().cache.get_blob_client('narration/v2/'+key+'.json').download_blob()
            if download.size>1_500_000: raise ValueError('Invalid commentary asset')
            raw=download.readall()
        if len(raw)>1_500_000: raise ValueError('Invalid commentary asset')
        return json.loads(raw)

    @app.post('/api/voice/highlight')
    def highlight_commentary(request:HighlightRequest):
        from counterpress.live.highlight_narrative import narrative, validate_asset
        if not enabled(): raise HTTPException(503,'Broadcast voice is unavailable')
        try: events=corpus().get(request.match_id)
        except (ValueError,OSError,KeyError): raise HTTPException(503,'Voice sources are unavailable') from None
        if not events: raise HTTPException(404,'Unknown highlight')
        if request.events!=[e.event_id for e in events] or request.revisions!=[e.revision for e in events]:
            raise HTTPException(409,'Choose the complete current highlight')
        try: script=narrative(events,request.language)
        except ValueError: raise HTTPException(404,'Highlight commentary is unavailable') from None
        try: asset=validate_asset(recorded_track(script['key']),script)
        except Exception: raise HTTPException(503,'Highlight commentary is being prepared') from None
        return {**asset,'event_count':len(events)}
