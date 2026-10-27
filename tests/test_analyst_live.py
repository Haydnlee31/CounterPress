import asyncio,json
import httpx
import pytest
from counterpress.adaptation.azure import AzureConfig
from counterpress.analyst.live import AzureLiveDiscussion,Comment,choose_role,live_packet,check_comment,guard_live_request
from counterpress.analyst.live_admission import LiveAllowance
from counterpress.analyst.admission import SQLiteStore
from test_analyst_metrics import snap,event,metric


def source():
 return snap([event(1,590000,start={'x':60,'y':30},end={'x':75,'y':30})],focus_player_id='h1')

def comment(**kw):
 return dict(text='The completed pass reached the final third; watch whether the next action turns that entry into a chance.',metric_ids=['current:home:final_third_entries'],evidence_ids=['e1:r1'],reply_to=None,relation='observation',visual='pass_routes')|kw


def test_scheduler_skips_empty_spells_and_prioritizes_shots_and_focus():
 assert choose_role(snap([])) is None
 assert choose_role(snap([event(1,599999,kind='shot',outcome='saved')]))=='chance'
 assert choose_role(snap([event(1,659999)],ms=660000,focus_player_id='h1'))=='players'


def test_trajectories_preserve_only_observed_endpoints():
 s=snap([event(1,1000,kind='shot',outcome='goal',goal_for='home',start={'x':90,'y':25},end={'x':105,'y':34}),event(2,2000,kind='shot',outcome='saved',start={'x':93,'y':40})])
 shots=metric(s,'shot_map')['value']['shots']
 assert shots[0]['end']=={'x':105,'y':34} and shots[1]['end'] is None


def test_source_context_identity_is_stable_for_new_events_but_changes_on_corrections():
 a=event(1,1000)
 assert snap([a],ms=1000)['source_version']==snap([a,event(2,2000)],ms=2000)['source_version']
 revised=a.model_copy(update={'revision':2,'delivery_sequence':2,'available_ms':2000,'outcome':'incomplete'})
 assert snap([a,revised],ms=2000)['source_version']!=snap([a],ms=1000)['source_version']


def test_natural_language_gate_keeps_real_references_and_numbers():
 s=source();p=live_packet(s,'control');e=p['evidence'][0]['id']
 check_comment(Comment(**comment(evidence_ids=[e])),p,[],'control')
 for kw in ({'metric_ids':['invented']},{'text':'They made 99 entries.'},{'reply_to':'players','relation':'builds_on'}):
  with pytest.raises(ValueError):check_comment(Comment(**comment(evidence_ids=[e],**kw)),p,[],'control')


def test_two_calls_publish_only_after_editor_review_and_allow_repairs():
 s=source();seen=[]
 def transport(req):
  data=json.loads(req.content);seen.append(data)
  packet=json.loads(data['messages'][1]['content'])['source'];eid=packet['evidence'][0]['id']
  row=comment(evidence_ids=[eid],metric_ids=[next(m['id'] for m in packet['metrics'] if m['key']=='final_third_entries' and m.get('club_id')=='home' and m['window']=='current')])
  if len(seen)==1:row['text']='They made 99 entries.'
  else:row.update(publish=True,text='The pass entered the final third. That is a route worth following, but the next action will decide whether it becomes a chance.')
  return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(row)}}],'usage':{'prompt_tokens':123,'completion_tokens':80}})
 cfg=AzureConfig(endpoint='https://fixture.openai.azure.com',deployment='gpt-4.1-mini',api_key='fake-test-only')
 r=asyncio.run(AzureLiveDiscussion(cfg,httpx.MockTransport(transport)).analyze(s,None))
 assert r['status']=='complete' and len(r['messages'])==1
 assert r['messages'][0]['verified_by']=='footie' and '99' not in r['messages'][0]['text']
 assert len(seen)==2 and [p['max_completion_tokens'] for p in seen]==[700,2000]
 assert 'reasoning_effort' not in seen[0]


@pytest.mark.parametrize('review', ['reject','invented_number','unknown_citation'])
def test_editor_rejection_or_invalid_repair_never_reaches_conversation(review):
 s=source();count=0
 def transport(req):
  nonlocal count
  count+=1;p=json.loads(json.loads(req.content)['messages'][1]['content'])['source']
  row=comment(evidence_ids=[p['evidence'][0]['id']],metric_ids=[next(m['id'] for m in p['metrics'] if m['key']=='final_third_entries' and m.get('club_id')=='home' and m['window']=='current')])
  if count==2:
   row['publish']=review!='reject'
   if review=='reject':row['text']=''
   if review=='invented_number':row['text']='They scored 99 goals.'
   if review=='unknown_citation':row['metric_ids']=['unknown']
  return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(row)}}],'usage':{}})
 cfg=AzureConfig(endpoint='https://fixture.openai.azure.com',deployment='gpt-4.1-mini',api_key='fake-test-only')
 r=asyncio.run(AzureLiveDiscussion(cfg,httpx.MockTransport(transport)).analyze(s,None))
 assert r['messages']==[] and count==2


def test_durable_match_cap_includes_failed_attempts_and_all_preferences(tmp_path):
 path=tmp_path/'live.sqlite3';a=LiveAllowance(SQLiteStore(path))
 for i in range(90):
  job=a.reserve(str(i),i*60,'match','prefs-'+str(i%4),{'period':1,'elapsed_ms':i*60000})
  assert job['admitted'];a.finish(str(i),job['owner'],None,i*60+1)
 b=LiveAllowance(SQLiteStore(path))
 assert b.reserve('new',10000,'match','new-language',{'period':2,'elapsed_ms':1000})['status']=='budget_limit'
 assert b.reserve('other',10000,'other-match','new',{'period':1,'elapsed_ms':1000})['admitted']


def test_shared_cache_causal_history_and_no_duplicate_charges(tmp_path):
 a=LiveAllowance(SQLiteStore(tmp_path/'live.sqlite3'))
 cut={'period':1,'elapsed_ms':120000};job=a.reserve('a',0,'match','scope',cut)
 assert not a.reserve('a',1,'match','scope',cut).get('admitted')
 a.finish('a',job['owner'],{'messages':[{'role':'control','text':'A supported reading.'}]},2)
 assert a.reserve('a',3601,'match','scope',cut)['status']=='complete'
 assert a.reserve('b',3601,'match','scope',{'period':1,'elapsed_ms':180000})['history'][0]['text']=='A supported reading.'
 assert a.reserve('c',3601,'match','scope',{'period':1,'elapsed_ms':60000})['history']==[]
 assert a.reserve('d',3601,'match','scope',{'period':1,'elapsed_ms':240000})['status']=='busy'


def test_input_guard_rejects_before_network():
 from counterpress.adaptation.azure import ProviderFailure
 with pytest.raises(ProviderFailure):guard_live_request(json.dumps({'input':'different long token '*10000}).encode())


def test_fast_forward_turn_manager_does_not_starve_roles_on_skipped_minutes():
 s=snap([event(1,599999,kind='duel',outcome='won')])
 history=[{'role':'chance'},{'role':'control'},{'role':'players'}]
 assert choose_role(s,history)=='defence'
 assert choose_role(s,[{'role':'defence'},{'role':'players'}])=='control'


def test_player_source_explicitly_distinguishes_attempts_from_completions():
 s=snap([event(1,590000),event(2,591000,outcome='incomplete')],focus_player_id='h1')
 p=live_packet(s,'players')
 attempts=next(m for m in p['metrics'] if m['key']=='passes' and m['window']=='prefix')
 completed=next(m for m in p['metrics'] if m['key']=='passes_completed' and m['window']=='prefix')
 assert attempts['value']==2 and attempts['label']=='Pass attempts'
 assert completed['value']==1


def test_window_duration_is_valid_but_internal_ids_and_self_replies_are_not():
 s=source();p=live_packet(s,'control');e=p['evidence'][0]['id']
 check_comment(Comment(**comment(text='One pass entered the final third in the last 5 minutes.',evidence_ids=[e])),p,[],'control')
 for kw in ({'text':'The entry is recorded in m1.'},{'reply_to':'control','relation':'builds_on'}):
  with pytest.raises(ValueError):check_comment(Comment(**comment(evidence_ids=[e],**kw)),p,[{'role':'control'}],'control')


def test_live_comparisons_do_not_mix_unequal_early_match_windows():
 s=snap([event(1,479999)],ms=480000)
 assert all(m['window']!='previous' for m in live_packet(s,'control')['metrics'])
 assert live_packet(source(),'control')['window_meanings']['current'].startswith('most recent')
