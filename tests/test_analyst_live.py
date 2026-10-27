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


@pytest.mark.parametrize('reply_link', ['standalone','missing_target','extraneous_target'])
def test_only_the_exact_independently_reviewed_draft_is_published(reply_link):
 s=source();seen=[];draft_text='The pass entered the final third, giving this attack a route towards the box.'
 def transport(req):
  data=json.loads(req.content);seen.append(data)
  payload=json.loads(data['messages'][1]['content']);packet=payload['source']
  row=comment(text=draft_text,evidence_ids=[packet['evidence'][0]['id']],metric_ids=[next(m['id'] for m in packet['metrics'] if m['key']=='final_third_entries' and m.get('club_id')=='home' and m['window']=='current')])
  if len(seen)==1:
   if reply_link=='missing_target':row.update(reply_to=None,relation='builds_on')
   if reply_link=='extraneous_target':row.update(reply_to='players',relation='observation')
  else:
   assert payload['candidates'][0]['text']==draft_text
   assert payload['candidates'][0]['reply_to'] is None and payload['candidates'][0]['relation']=='observation'
   row=dict(publish=True,selected_index=0,added_value='sequence',new_reading='A supported sequence adds context. '*15,unsupported_premises=[])
  if len(seen)==1:row={'comments':[row]}
  return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(row)}}],'usage':{'prompt_tokens':123,'completion_tokens':80}})
 cfg=AzureConfig(endpoint='https://fixture.openai.azure.com',deployment='gpt-4.1-mini',api_key='fake-test-only')
 r=asyncio.run(AzureLiveDiscussion(cfg,httpx.MockTransport(transport)).analyze(s,None))
 assert r['status']=='complete' and len(r['messages'])==1
 assert r['messages'][0]['text']==draft_text and r['messages'][0]['verified_by']=='footie'
 assert r['messages'][0]['reply_to'] is None and r['messages'][0]['relation']=='observation'
 assert len(seen)==2 and [p['max_completion_tokens'] for p in seen]==[2000,2000]
 assert 'text' not in seen[1]['response_format']['json_schema']['schema']['properties']


@pytest.mark.parametrize('review', ['reject','invented_number','unknown_citation','no_added_value','unsupported_premise','repetition','rewritten_text'])
def test_editor_verdict_or_hard_checks_block_invalid_publication(review):
 s=source();count=0
 def transport(req):
  nonlocal count
  count+=1;p=json.loads(json.loads(req.content)['messages'][1]['content'])['source']
  row=comment(evidence_ids=[p['evidence'][0]['id']],metric_ids=[next(m['id'] for m in p['metrics'] if m['key']=='final_third_entries' and m.get('club_id')=='home' and m['window']=='current')])
  if count==1:
   if review=='invented_number':row['text']='They scored 99 goals.'
   if review=='unknown_citation':row['metric_ids']=['unknown']
  else:
   row=dict(publish=review!='reject',selected_index=0,added_value='contrast',new_reading='A new supported contrast.',unsupported_premises=[])
   if review=='repetition':row['new_reading']=''
   if review=='no_added_value':row['added_value']='none'
   if review=='unsupported_premise':row['unsupported_premises']=['Individual blame is not supported']
   if review=='rewritten_text':row['text']='An unreviewed replacement must never publish.'
  if count==1:row={'comments':[row]}
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


def test_focus_context_preserves_defensive_contributions_and_comparable_spells():
 s=snap([event(1,299999,kind='recovery'),event(2,599999,kind='duel',outcome='won')],focus_player_id='h1')
 p=live_packet(s,'players')
 rows={m['id']:m['value'] for m in p['metrics']}
 assert rows['previous:h1:recoveries']==1 and rows['current:h1:recoveries']==0
 assert rows['current:h1:duels_won']==1 and rows['previous:h1:duels_won']==0
 # Partial preceding windows are not a valid comparison.
 assert not any(m['window']=='previous' for m in live_packet(snap([event(1,479999)],ms=480000,focus_player_id='h1'),'players')['metrics'])


def test_idle_focused_player_does_not_get_recycled_turns():
 history=[{'role':'players','cutoff':{'period':1,'elapsed_ms':540000}},{'role':'control'}]
 quiet=snap([event(1,539000),event(2,599999,player_id='a1',club_id='away')],focus_player_id='h1')
 assert choose_role(quiet,history)!='players'
 active=snap([event(1,539000),event(2,599999)],focus_player_id='h1')
 assert choose_role(active,history)=='players'


def test_focus_actions_survive_other_players_activity_without_future_leakage():
 rows=[event(1,500000)]+[event(i,500000+i*1000,player_id='a1',club_id='away') for i in range(2,25)]+[event(25,600001)]
 p=live_packet(snap(rows,focus_player_id='h1'),'players')
 ids={e['id'] for e in p['evidence']}
 assert 'e1:r1' in ids and 'e25:r1' not in ids and len(ids)<=8


def test_gate_rejects_cross_club_citations_and_prefix_as_previous_spell():
 s=snap([event(1,1000),event(2,590000),event(3,2000)],focus_player_id='h1');p=live_packet(s,'players')
 with pytest.raises(ValueError,match='unsupported_trend'):
  check_comment(Comment(**comment(text='His involvement fell from two actions to one.',metric_ids=['prefix:h1:on_ball_actions','current:h1:on_ball_actions'],evidence_ids=[])),p,[],'players')
 p=live_packet(s,'control')
 with pytest.raises(ValueError,match='missing_club_reference'):
  check_comment(Comment(**comment(text='Away made no passes into the box.',metric_ids=['current:home:box_entries'],evidence_ids=[])),p,[],'control')
 check_comment(Comment(**comment(text='Home passes decreased from the preceding spell.',metric_ids=['current:home:passes','previous:home:passes'],evidence_ids=[])),p,[],'control')


def test_fast_replay_does_not_skip_focus_actions_between_coalesced_turns():
 s=snap([event(1,450000),event(2,599999,player_id='a1',club_id='away')],focus_player_id='h1')
 history=[{'role':'players','cutoff':{'period':1,'elapsed_ms':300000}},{'role':'control'}]
 assert choose_role(s,history)=='players'


@pytest.mark.parametrize('text', [
 'Five recoveries have restricted Northport to only one pass into the box.',
 'His pass completion forced the opposition back.',
 'Hayes has been error-free with three completed passes.',
 'Hayes provides no attacking output so far.',
])
def test_observed_editor_false_positives_cannot_publish(text):
 p=live_packet(source(),'control')
 with pytest.raises(ValueError,match='aggregate_causal_claim|unsupported_performance_absolute'):
  check_comment(Comment(**comment(text=text,evidence_ids=['e1:r1'])),p,[],'control')


def test_editor_selects_supported_alternative_without_publishing_rejected_prose():
 s=source();seen=[]
 def transport(req):
  payload=json.loads(req.content);data=json.loads(payload['messages'][1]['content']);seen.append(data);p=data['source']
  if len(seen)==1:
   good=comment(text='The pass advanced the ball into the final third.',evidence_ids=[p['evidence'][0]['id']],metric_ids=[next(m['id'] for m in p['metrics'] if m['key']=='final_third_entries' and m.get('club_id')=='home' and m['window']=='current')])
   out={'comments':[dict(good,text='Invented pressure caused a goal.'),good]}
  else:
   assert len(data['candidates'])==2
   out=dict(publish=True,selected_index=1,added_value='sequence',new_reading='The second candidate describes the supported entry.',unsupported_premises=[])
  return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(out)}}],'usage':{}})
 cfg=AzureConfig(endpoint='https://fixture.openai.azure.com',deployment='gpt-5-mini',api_key='fake-test-only')
 result=asyncio.run(AzureLiveDiscussion(cfg,httpx.MockTransport(transport)).analyze(s,None,[{'role':'players','cutoff':{'period':1,'elapsed_ms':1000},'text':'','attempt_only':True}]))
 assert result['status']=='complete'
 assert result['messages'][0]['text']=='The pass advanced the ball into the final third.'
 assert result['execution']['publication_decision']=='published'
 assert seen[0]['conversation']==[] # Attempt metadata schedules turns but is never spoken history.


@pytest.mark.parametrize('selected', [None,1])
def test_editor_cannot_select_missing_candidate(selected):
 s=source();count=0
 def transport(req):
  nonlocal count
  count+=1;data=json.loads(json.loads(req.content)['messages'][1]['content']);p=data['source']
  out={'comments':[comment(metric_ids=[],evidence_ids=[p['evidence'][0]['id']])]} if count==1 else dict(publish=True,selected_index=selected,added_value='sequence',new_reading='A passage',unsupported_premises=[])
  return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(out)}}],'usage':{}})
 cfg=AzureConfig(endpoint='https://fixture.openai.azure.com',deployment='gpt-5-mini',api_key='fake-test-only')
 result=asyncio.run(AzureLiveDiscussion(cfg,httpx.MockTransport(transport)).analyze(s,None))
 assert result['messages']==[] and result['execution']['model_calls']==2


def test_passage_cannot_be_the_cause_of_a_window_wide_change():
 p=live_packet(snap([event(1,1000,start={'x':60,'y':30},end={'x':80,'y':30})]),'control')
 with pytest.raises(ValueError,match='passage_aggregate_causation'):
  check_comment(Comment(**comment(text='Circulation kept the ball safe but reduced final-third entries.',evidence_ids=[],metric_ids=['current:home:final_third_entries','previous:home:final_third_entries'])),p,[],'control')


@pytest.mark.parametrize('annotation',['(m1 vs m2)','(m1→m2)','(m1, m2 vs m3)','(e1–e2)'])
def test_citation_only_comparison_annotations_are_removed_before_exact_review(annotation):
 s=source();seen=[]
 def transport(req):
  body=json.loads(req.content);data=json.loads(body['messages'][1]['content']);seen.append(data);p=data['source']
  if len(seen)==1:
   out={'comments':[comment(text='The pass entered the final third '+annotation+'.',metric_ids=[next(m['id']for m in p['metrics']if m['key']=='final_third_entries'and m['club_id']=='home'and m['window']=='current')],evidence_ids=[p['evidence'][0]['id']])]}
  else:
   assert data['candidates'][0]['text']=='The pass entered the final third.'
   out=dict(publish=True,selected_index=0,added_value='sequence',new_reading='A supported entry',unsupported_premises=[])
  return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(out)}}],'usage':{}})
 cfg=AzureConfig(endpoint='https://fixture.openai.azure.com',deployment='gpt-5-mini',api_key='fake-test-only')
 result=asyncio.run(AzureLiveDiscussion(cfg,httpx.MockTransport(transport)).analyze(s,None))
 assert result['messages'][0]['text']=='The pass entered the final third.'


def test_event_clock_is_valid_only_when_its_exact_action_is_cited():
 p=live_packet(source(),'control')
 check_comment(Comment(**comment(text='At 9:50 the pass reached the final third.')),p,[],'control')
 for text,ids in [('At 9:51 the pass reached the final third.',['e1:r1']),('At 9:50 the pass reached the final third.',[])]:
  with pytest.raises(ValueError,match='unsupported_clock'):
   check_comment(Comment(**comment(text=text,evidence_ids=ids)),p,[],'control')
