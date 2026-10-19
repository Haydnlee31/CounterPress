from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from counterpress.api.main import create_app
from counterpress.live.api import MATCH_ID
from counterpress.live.speech import install_speech, phrase, SpeechLimit
from counterpress.fixture import load_fixture

ROOT=Path(__file__).resolve().parents[1]/'fixtures'


def test_full_feed_validated_and_no_final_score_metadata():
    with TestClient(create_app()) as client:
        response=client.get('/api/live/matches/'+MATCH_ID)
        assert response.status_code==200
        body=response.json()
        assert len(body['events'])==1267
        assert body['initial_state']['score']=={'eastbridge':0,'northport':0}
        assert 'headline' not in body
        assert client.get('/api/live/matches/other').status_code==404
        assert client.get('/api/voice/config').json()['azure'] is False


class FakeVoice:
    def __init__(self): self.calls=[]
    def audio(self,text,ssml): self.calls.append((text,ssml));return b'ID3-test'


def request(event):
    return dict(match_id=event.match_id,events=[event.event_id],revisions=[event.revision],cutoff=event.available_at.model_dump(),language='en',detailed=False)


def test_voice_rejects_free_text_wrong_revisions_future_and_unknown_events():
    app=FastAPI();voice=FakeVoice();install_speech(app,ROOT,voice)
    feed=load_fixture(ROOT/'gi/synthetic/events.json')
    e=next(e for e in feed.events if e.action.kind=='shot' and e.action.outcome=='goal')
    with TestClient(app) as client:
        payload=request(e)
        assert client.post('/api/voice/commentary',json={**payload,'text':'arbitrary input'}).status_code==422
        assert client.post('/api/voice/commentary',json={**payload,'revisions':[2]}).status_code==409
        assert client.post('/api/voice/commentary',json={**payload,'cutoff':{'period':1,'elapsed_ms':0}}).status_code==409
        assert client.post('/api/voice/commentary',json={**payload,'events':['unknown']}).status_code==422
        assert client.post('/api/voice/commentary',json={**payload,'language':'other'}).status_code==422
        assert not voice.calls
        result=client.post('/api/voice/commentary',json=payload)
        assert result.status_code==200 and result.headers['content-type']=='audio/mpeg'
        assert 'excited' in voice.calls[0][1] and 'Goal!' in voice.calls[0][0]
        result=client.post('/api/voice/commentary',json={**payload,'language':'zh-Hans'})
        assert result.status_code==200 and 'sports-commentary-excited' in voice.calls[-1][1]


def test_voice_limits_and_failures_do_not_expose_provider_details():
    class Limited:
        def audio(self,*args): raise SpeechLimit()
    app=FastAPI();install_speech(app,ROOT,Limited())
    e=load_fixture(ROOT/'gi/synthetic/events.json').events[0]
    with TestClient(app) as client:
        response=client.post('/api/voice/commentary',json=request(e))
        assert response.status_code==429 and response.headers['retry-after']=='60'
    class Failed:
        def audio(self,*args): raise RuntimeError('private endpoint and credentials')
    app=FastAPI();install_speech(app,ROOT,Failed())
    with TestClient(app) as client:
        response=client.post('/api/voice/commentary',json=request(e))
        assert response.status_code==503 and 'private' not in response.text


def test_summary_requires_contiguous_events_and_correct_revision_count():
    app=FastAPI();voice=FakeVoice();install_speech(app,ROOT,voice)
    events=load_fixture(ROOT/'gi/synthetic/events.json').events
    payload=request(events[3]);payload['events']=[events[0].event_id,events[3].event_id];payload['revisions']=[1,1]
    with TestClient(app) as client:
        assert client.post('/api/voice/commentary',json=payload).status_code==422
        payload['events']=[events[2].event_id,events[3].event_id]
        assert client.post('/api/voice/commentary',json=payload).status_code==200
        payload['revisions']=[1]
        assert client.post('/api/voice/commentary',json=payload).status_code==422


def test_monthly_budget_reservation_is_conditional_and_never_overruns():
    from counterpress.live.speech import AzureSpeech, MONTHLY_CHARACTERS
    from azure.core.exceptions import ResourceModifiedError, ResourceNotFoundError
    from azure.core import MatchConditions
    from types import SimpleNamespace
    import json
    import pytest
    class Blob:
        used=MONTHLY_CHARACTERS-10
        uploads=0
        def download_blob(self):
            return SimpleNamespace(readall=lambda:json.dumps({'characters':self.used}).encode(),properties=SimpleNamespace(etag='etag'))
        def upload_blob(self,data,**kwargs):
            assert kwargs['etag']=='etag' and kwargs['match_condition']==MatchConditions.IfNotModified
            self.uploads+=1
            if self.uploads==1:
                self.used+=8
                raise ResourceModifiedError('racing writer')
            self.used=json.loads(data)['characters']
    blob=Blob()
    voice=object.__new__(AzureSpeech);voice.cache=SimpleNamespace(get_blob_client=lambda name:blob)
    with pytest.raises(SpeechLimit):voice.reserve(5)
    assert blob.used==MONTHLY_CHARACTERS-2 and blob.uploads==1
    voice.reserve(2)
    assert blob.used==MONTHLY_CHARACTERS
    with pytest.raises(SpeechLimit):voice.reserve(1)


def test_cache_hit_never_calls_synthesis_or_reserves_quota():
    from counterpress.live.speech import AzureSpeech
    from types import SimpleNamespace
    from threading import Lock
    voice=object.__new__(AzureSpeech);voice.lock=Lock()
    blob=SimpleNamespace(download_blob=lambda:SimpleNamespace(size=3,readall=lambda:b'mp3'))
    voice.cache=SimpleNamespace(get_blob_client=lambda name:blob)
    voice.reserve=lambda n:(_ for _ in ()).throw(AssertionError('cache billed'))
    assert voice.audio('text','ssml')==b'mp3'
    voice.cache=SimpleNamespace(get_blob_client=lambda name:(_ for _ in ()).throw(AssertionError('memory cache missed')))
    assert voice.audio('text','ssml')==b'mp3'


def test_short_highlight_calls_are_grounded_and_results_are_shot_only():
    app=FastAPI();voice=FakeVoice();install_speech(app,ROOT,voice)
    from counterpress.api.snapshots import SCENARIOS
    feed=load_fixture(ROOT/SCENARIOS['last-gasp'][0])
    shot=next(e for e in feed.events if e.action.kind=='shot')
    routine=next(e for e in feed.events if e.action.kind=='pass')
    with TestClient(app) as client:
        assert client.post('/api/voice/commentary',json={**request(shot),'delivery':'highlight-action'}).status_code==200
        assert voice.calls[-1][0].split()==['Marlow!']
        assert client.post('/api/voice/commentary',json={**request(shot),'delivery':'highlight-result'}).status_code==200
        assert voice.calls[-1][0]=='Saved!'
        assert client.post('/api/voice/commentary',json={**request(shot),'delivery':'highlight-result','language':'zh-Hans'}).status_code==200
        assert voice.calls[-1][0]=='扑出！'
        assert client.post('/api/voice/commentary',json={**request(routine),'delivery':'highlight-result'}).status_code==422
        assert client.post('/api/voice/commentary',json={**request(shot),'delivery':'highlight-action','detailed':True}).status_code==422
        full=load_fixture(ROOT/'gi/synthetic/events.json').events[0]
        assert client.post('/api/voice/commentary',json={**request(full),'delivery':'highlight-action'}).status_code==422
