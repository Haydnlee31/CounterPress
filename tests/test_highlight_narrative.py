import base64,json
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from counterpress.api.snapshots import SCENARIOS
from counterpress.fixture import load_fixture
from counterpress.live.highlight_narrative import narrative,validate_asset,SCRIPTS
from counterpress.live.speech import install_speech
ROOT=Path(__file__).resolve().parents[1]/'fixtures'

def feed(story):return load_fixture(ROOT/SCENARIOS[story][0]).events

def asset(script):
 return dict(key=script['key'],source_hash=script['source_hash'],duration=60,
  markers=[{'at':i*3,**b} for i,b in enumerate(script['beats'])],audio=base64.b64encode(b'ID3'+b'x'*200).decode())

@pytest.mark.parametrize('story',list(SCRIPTS))
@pytest.mark.parametrize('language',['en','zh-Hans'])
def test_complete_narratives_are_grounded_not_isolated_names(story,language):
 events=feed(story);script=narrative(events,language)
 assert len(script['beats'])>=5
 assert script['beats'][0]['position']==0
 if language=='en':
  assert all(len(b['text'].split())>=2 for b in script['beats'])
  assert len(script['beats'][-1]['text'].split())>=4
 else:
  assert all(any('\u4e00'<=c<='\u9fff' for c in b['text']) for b in script['beats'])
 for i,e in enumerate(events):
  if e.action.kind=='shot':assert any(abs(b['position']-(i+.6))<.001 for b in script['beats'])
 assert script['ssml'].count('<voice ')==1
 assert script['ssml'].count('<bookmark ')==len(script['beats'])
 assert validate_asset(asset(script),script)


def test_source_edits_require_narrative_review_and_bad_timing_fails_closed():
 events=feed('last-gasp');script=narrative(events,'en')
 changed=[events[0].model_copy(update={'revision':2}),*events[1:]]
 with pytest.raises(ValueError,match='review'):narrative(changed,'en')
 for mutate in [lambda a:a.update(key='old'),lambda a:a['markers'][1].update(at=-1),lambda a:a['markers'].pop(),lambda a:a.update(audio='not audio')]:
  a=asset(script);mutate(a)
  with pytest.raises(ValueError):validate_asset(a,script)


@pytest.mark.parametrize('profile',['broadcast','natural'])
def test_serving_reviewed_tracks_is_cache_only_and_validates_entire_highlight(tmp_path,monkeypatch,profile):
 monkeypatch.setenv('COUNTERPRESS_COMMENTARY_VOICE',profile)
 events=feed('one-touch');script=narrative(events,'en',profile);bundle=asset(script)
 (tmp_path/(script['key']+'.json')).write_text(json.dumps(bundle))
 monkeypatch.setenv('COUNTERPRESS_COMMENTARY_DIR',str(tmp_path))
 class NoSynthesis:
  def audio(self,*args):raise AssertionError('Serving a recorded highlight must not synthesize')
 app=FastAPI();install_speech(app,ROOT,NoSynthesis())
 payload={'match_id':events[0].match_id,'events':[e.event_id for e in events],'revisions':[e.revision for e in events],'language':'en'}
 with TestClient(app) as client:
  response=client.post('/api/voice/highlight',json=payload)
  assert response.status_code==200 and response.json()['markers']==bundle['markers']
  assert client.post('/api/voice/highlight',json={**payload,'events':payload['events'][:-1]}).status_code==409
  assert client.post('/api/voice/highlight',json={**payload,'text':'arbitrary'}).status_code==422
  assert client.post('/api/voice/highlight',json={**payload,'language':'de'}).status_code==422
  assert client.post('/api/voice/highlight',json={**payload,'language':'zh-Hans'}).status_code==503

@pytest.mark.parametrize('story',list(SCRIPTS))
def test_british_audition_keeps_grounded_script_and_bookmarks_but_separates_cache(story):
 original=narrative(feed(story),'en')
 british=narrative(feed(story),'en','british')
 assert british['beats']==original['beats']
 assert british['source_hash']==original['source_hash']
 assert british['key']!=original['key']
 assert 'en-GB-RyanNeural' in british['ssml'] and 'style="chat"' in british['ssml']
 assert 'style="cheerful"' in british['ssml'] and 'style="excited"' not in british['ssml']
 assert validate_asset(asset(british),british)
 assert narrative(feed(story),'zh-Hans','british')==narrative(feed(story),'zh-Hans')

@pytest.mark.parametrize('story',list(SCRIPTS))
def test_natural_delivery_preserves_original_voice_grounding_and_mandarin(story):
 original=narrative(feed(story),'en')
 natural=narrative(feed(story),'en','natural')
 assert natural['beats']==original['beats']
 assert natural['source_hash']==original['source_hash']
 assert natural['key']!=original['key']
 assert 'en-US-GuyNeural' in natural['ssml']
 assert 'style="friendly" styledegree="1.0"' in natural['ssml']
 assert 'style="excited" styledegree="0.8"' in natural['ssml']
 assert 'newscast' not in natural['ssml'] and 'en-GB' not in natural['ssml']
 assert validate_asset(asset(natural),natural)
 assert narrative(feed(story),'zh-Hans','natural')==narrative(feed(story),'zh-Hans')
