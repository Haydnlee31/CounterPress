import asyncio,json
from pathlib import Path
import pytest
from counterpress.analyst.discussion import DiscussionRuntime,Contribution,check_citations,packet_for,render_facts
from test_analyst_metrics import snap,event


def rejected_live_fact_contract():
 return json.loads((Path(__file__).parent/'fixtures'/'analyst_rejected_live_fact_contract.json').read_text())


def test_captured_live_response_remains_rejected_without_repairing_its_claims():
 fixture=rejected_live_fact_contract()
 row=Contribution(**fixture['response'])
 with pytest.raises(ValueError,match='unbound_quantitative_prose'):
  check_citations(row,fixture['packet'])
 # Removing the prose must not conceal its missing citation or reversed window.
 row=row.model_copy(update={'text':'[[fact:0]] [[fact:1]] Circulation alone does not establish control.'})
 with pytest.raises(ValueError,match='uncited_fact'):
  check_citations(row,fixture['packet'])
 row=row.model_copy(update={'metric_ids':row.metric_ids+['current:northport:event_share']})
 with pytest.raises(ValueError,match='incomparable_facts'):
  check_citations(row,fixture['packet'])


def test_adjacent_fact_sentences_render_both_bound_facts_and_preserve_windows():
 fixture=rejected_live_fact_contract();p=fixture['packet']
 row=Contribution(**(fixture['response']|{
  'facts':[{'metric_id':'current:northport:event_share','compare_to':'previous:northport:event_share'},
           {'metric_id':'current:northport:tempo','compare_to':None}],
  'metric_ids':['current:northport:event_share','previous:northport:event_share','current:northport:tempo'],
  'text':'[[fact:0]] [[fact:1]] Circulation alone does not establish control.'}))
 check_citations(row,p)
 result=render_facts(row,p)
 assert result.count('Northport —')==2
 assert 'H1 14:00–H1 19:00' in result and 'H1 19:00–H1 24:00' in result
 assert 'change 2.76513 percentage points' in result
 assert '[[fact:' not in result and result.endswith('Circulation alone does not establish control.')
 # Adjacent placeholders are sentences; prose cannot attach another actor to them.
 for text in ['Northport [[fact:0]] [[fact:1]]','[[fact:0]] Northport [[fact:1]]',
              '[[fact:0]][[fact:1]]']:
  with pytest.raises(ValueError,match='fact_marker_not_standalone'):
   render_facts(row.model_copy(update={'text':text}),p)


def test_fact_markers_must_still_match_the_complete_ordered_fact_array():
 p=packet()
 for text in ['[[fact:1]]','[[fact:0]] [[fact:0]]','', '[[fact:0]] [[fact:1]]']:
  with pytest.raises(ValueError,match='fact_marker_mismatch'):
   render_facts(Contribution(**turn([],text=text)),p)


def test_captured_player_directional_prose_is_not_silently_normalized():
 fixture=json.loads((Path(__file__).parent/'fixtures'/'analyst_rejected_live_player_contract.json').read_text())
 with pytest.raises(ValueError,match='unbound_quantitative_prose'):
  check_citations(Contribution(**fixture['response']),fixture['packet'])


def test_player_club_membership_does_not_cite_a_team_reading():
 fixture=json.loads((Path(__file__).parent/'fixtures'/'analyst_rejected_live_team_citation.json').read_text())
 row=Contribution(**fixture['response'])
 with pytest.raises(ValueError,match='uncited_subject'):
  check_citations(row,fixture['packet'])
 # The model must explicitly cite the available team metric; do not silently
 # inherit it from reply_to or from the player's club membership.
 cited=row.model_copy(update={'metric_ids':row.metric_ids+['current:northport:event_share']})
 check_citations(cited,fixture['packet'])
 assert render_facts(cited,fixture['packet']).startswith('Isaac Lane — Passes:')


def test_server_fact_layout_preserves_all_citation_and_quantitative_guards():
 from counterpress.analyst.discussion import normalize_fact_layout
 p=packet()
 row=Contribution(**turn([],text='Circulation alone does not establish control.'))
 normalized=normalize_fact_layout(row)
 assert normalized.text=='[[fact:0]] Circulation alone does not establish control.'
 assert normalized.facts==row.facts and normalized.metric_ids==row.metric_ids
 check_citations(normalized,p)
 for text in ('They had 99 shots.','More chances are certain.','They had ninety shots.','They had mOrE shots.'):
  with pytest.raises(ValueError,match='unbound_quantitative_prose'):
   check_citations(normalize_fact_layout(row.model_copy(update={'text':text})),p)
 for ids in ([],['unknown']):
  with pytest.raises(ValueError):check_citations(normalize_fact_layout(row.model_copy(update={'metric_ids':ids})),p)
 malformed=row.model_copy(update={'text':'[[fact:9]] Wrong marker.'})
 assert normalize_fact_layout(malformed)==malformed
 with pytest.raises(ValueError,match='fact_marker_mismatch'):check_citations(malformed,p)
 for name in ('analyst_rejected_live_pressure_inference.json','analyst_rejected_live_player_contract.json'):
  fixture=json.loads((Path(__file__).parent/'fixtures'/name).read_text())
  with pytest.raises(ValueError,match='unbound_quantitative_prose'):
   check_citations(normalize_fact_layout(Contribution(**fixture['response'])),fixture['packet'])


def test_runtime_renders_marker_free_facts_before_sharing_and_after_editor_revisions():
 seen=[]
 async def complete(role,prompt,data,schema,tokens):
  seen.append(data['conversation'])
  if role!='footie':value=turn(data['conversation'],text='Activity alone does not establish control.')
  else:value=dict(facts=[],accepted_ids=['control','players','chance','defence'],
   revisions=[dict(id='control',role='control',**turn([],text='Circulation alone does not establish control.'))],
   text='A territorial interpretation needs an attacking payoff.',watch_next='Watch for a supported chance.',metric_ids=['passes'],evidence_ids=[])
  return json.dumps(value),{}
 result=run(complete)
 assert result['status']=='complete'
 assert 'Passes: 12' in seen[1][0]['text']
 assert 'Circulation alone' in result['messages'][0]['text']
 assert result['messages'][0]['draft_text'].startswith('[[fact:0]]')


def test_azure_and_native_discussion_use_bounded_medium_reasoning(monkeypatch):
 from counterpress.adaptation.azure import AzureConfig
 from counterpress.analyst.discussion import AzureDiscussion
 from counterpress.assistant import planner
 from integrations.analyst_foundry.definitions import definition
 seen=[]
 async def complete(config,transport,prompt,data,schema,name,tokens,timeout,**kw):
  seen.append((name,tokens,timeout,kw['reasoning_effort']))
  if name=='analyst_footie':
   value=dict(facts=[],accepted_ids=[],revisions=[],text='',watch_next='',metric_ids=[],evidence_ids=[])
  else:value=dict(facts=[],text='',reply_to=None,relation='observation',metric_ids=[],evidence_ids=[])
  return json.dumps(value),{'prompt_tokens':0,'completion_tokens':0}
 monkeypatch.setattr(planner,'structured_request',complete)
 config=AzureConfig(endpoint='https://fixture.openai.azure.com',deployment='gpt-5-mini',api_key='fake-offline-value')
 asyncio.run(AzureDiscussion(config).analyze(snap([event(1,1000)],ms=60000),None))
 assert seen==[(f'analyst_{role}',2200,20,'medium') for role in ('control','players','chance','defence')]+[('analyst_footie',4000,40,'medium')]
 for role in ('control','players','chance','defence','synthesis'):
  assert definition(role,'gpt-5-mini',discussion=True)['reasoning']['effort']=='medium'


def packet():
 return {'snapshot_id':'s','match_id':'m','cutoff':{'period':1,'elapsed_ms':300000},'through_sequence':4,
 'score':{'home':0,'away':0},'metrics':[{'id':'passes','key':'passes','window':'prefix','value':12,'label':'Passes'}],'evidence':[{'id':'e1'}]}


def turn(prior,**kw):
 return dict(facts=[{'metric_id':'passes','compare_to':None}],text='[[fact:0]] This shows involvement, but does not establish possession time.',reply_to=prior[-1]['id'] if prior else None,relation='builds_on' if prior else 'observation',metric_ids=['passes'],evidence_ids=[])|kw


def run(complete):return asyncio.run(DiscussionRuntime(complete).run(packet()))


def test_real_framework_broadcasts_each_previous_specialist_and_caps_calls():
 seen=[]
 async def complete(role,prompt,data,schema,tokens):
  seen.append((role,[r['id'] for r in data['conversation']]))
  value=turn(data['conversation']) if role!='footie' else dict(facts=[],revisions=[],accepted_ids=['control','players','chance','defence'],text='Activity needs an end product.',watch_next='Watch the next shot.',metric_ids=['passes'],evidence_ids=[])
  return json.dumps(value),{'input_tokens':10,'output_tokens':20}
 result=run(complete)
 assert seen==[('control',[]),('players',['control']),('chance',['control','players']),('defence',['control','players','chance']),('footie',['control','players','chance','defence'])]
 assert len(result['messages'])==5 and result['status']=='complete'
 assert result['execution']['model_calls']==5
 assert result['execution']['input_tokens']==50


def test_unknown_citations_and_invented_numerals_are_rejected():
 for kw in ({'metric_ids':['made-up']},{'text':'They completed 99 passes.'},{'evidence_ids':['future:r1']},{'metric_ids':[]}):
  with pytest.raises(ValueError):check_citations(Contribution(**turn([],**kw)),packet())
 check_citations(Contribution(**turn([])),packet())


def test_rejected_parent_removes_dependent_replies_and_chair_summary():
 async def complete(role,prompt,data,schema,tokens):
  value=turn(data['conversation']) if role!='footie' else dict(facts=[],revisions=[],accepted_ids=['players','chance','defence'],text='A summary.',watch_next='',metric_ids=['passes'],evidence_ids=[])
  return json.dumps(value),{}
 result=run(complete)
 assert result['messages']==[] and result['status']=='insufficient_evidence'


def test_provider_failure_does_not_publish_fake_agent_prose():
 async def complete(*args):raise TimeoutError()
 result=run(complete)
 assert result['messages']==[]
 assert result['failed_roles']==['chance','control','defence','footie','players']
 assert result['execution']['model_calls']==5


def test_role_packet_has_no_prepared_candidates_and_no_future_metrics():
 s=snap([event(1,1000),event(2,100000)],ms=60000)
 p=packet_for(s)
 assert 'candidates' not in p and 'signals' not in p
 assert all(e['elapsed_ms']<=60000 for e in p['evidence'])
 assert next(m for m in p['metrics'] if m['id']=='prefix:home:passes')['value']==1
 assert all(m['value'] is not None for m in p['metrics'])


def test_momentum_reconstructs_revision_visible_at_each_historical_sample():
 first=event(1,30000,kind='shot',outcome='off_target',start={'x':95,'y':34})
 corrected=first.model_copy(update={'revision':2,'delivery_sequence':2,'available_ms':90000,'retracted':True})
 early=snap([first],ms=60000)['momentum'][0]
 later=snap([first,corrected],ms=120000)['momentum']
 assert later[0]==early and early['value']>0
 assert later[1]['value']==0


def test_comparison_is_rendered_from_paired_windows_and_never_calls_zero_to_two_doubling():
 p=packet();p['windows']={'previous':{'period':1,'start_ms':0,'end_ms':150000},'current':{'period':1,'start_ms':150000,'end_ms':300000}}
 p['metrics']=[{'id':'old','key':'box_entries','label':'Box entries','window':'previous','club_id':'home','value':0},{'id':'new','key':'box_entries','label':'Box entries','window':'current','club_id':'home','value':2}]
 row=Contribution(**turn([],text='[[fact:0]] The end product still needs scrutiny.',metric_ids=['old','new'],facts=[{'metric_id':'new','compare_to':'old'}]))
 check_citations(row,p)
 assert 'change 2' in render_facts(row,p) and 'doubl' not in render_facts(row,p)
 for bad in ('Box entries doubled.', 'Box entries doubled to two.', 'Box entries doubled to 2.'):
  with pytest.raises(ValueError):check_citations(row.model_copy(update={'text':bad}),p)


def test_native_adapter_runs_same_shared_conversation_with_pinned_role_mapping():
 from integrations.analyst_foundry.discussion import NativeDiscussion
 from integrations.analyst_foundry.runtime import Completion
 from counterpress.analyst.discussion import VERSION
 seen=[]
 async def complete(role,payload,tokens):
  data=json.loads(payload);seen.append(role)
  value=turn(data['conversation']) if role!='synthesis' else dict(facts=[],revisions=[],accepted_ids=['control','players','chance','defence'],text='Activity needs an end product.',watch_next='',metric_ids=['passes'],evidence_ids=[])
  return Completion(json.dumps(value),10,10)
 p={**packet(),'protocol':VERSION}
 result=asyncio.run(NativeDiscussion(complete).run(json.dumps(p),asyncio.Event()))
 assert len(result['messages'])==5
 assert seen==['control','players','chance','defence','synthesis']


def test_native_definition_is_free_prose_and_bundle_contains_exact_shared_core():
 from integrations.analyst_foundry.definitions import definition
 from scripts.configure_analyst_foundry import source_bundle,ROOT
 import io,zipfile
 d=definition('players','gpt-4.1-mini',discussion=True)
 assert 'candidate_id' not in json.dumps(d)
 assert 'reply_to' in d['text']['format']['schema']['properties']
 with zipfile.ZipFile(io.BytesIO(source_bundle())) as z:
  assert z.read('integrations/analyst_foundry/discussion_core.py')==(ROOT/'backend/counterpress/analyst/discussion.py').read_bytes()


def test_editor_can_repair_a_reply_when_its_parent_was_rejected():
 async def complete(role,prompt,data,schema,tokens):
  if role!='footie': value=turn(data['conversation'])
  else:
   repaired={'id':'players','role':'players',**turn([],text='[[fact:0]] The attacking payoff needs a closer look.')}
   value=dict(facts=[],accepted_ids=['players'],revisions=[repaired],text='Activity needs an end product.',watch_next='',metric_ids=['passes'],evidence_ids=[])
  return json.dumps(value),{}
 result=run(complete)
 assert [m['role'] for m in result['messages']]==['players','footie']
 assert result['messages'][0]['reply_to'] is None


def test_editor_cannot_repair_with_a_new_fabricated_number():
 async def complete(role,prompt,data,schema,tokens):
  if role!='footie': value=turn(data['conversation'])
  else:
   repaired={'id':'control','role':'control',**turn([],text='They made 99 passes.')}
   value=dict(facts=[],accepted_ids=['control'],revisions=[repaired],text='An unsupported conclusion.',watch_next='',metric_ids=['passes'],evidence_ids=[])
  return json.dumps(value),{}
 result=run(complete)
 assert result['messages']==[]
 assert result['failure_reasons']['footie'] in ('fact_marker_mismatch','unbound_quantitative_prose')


def test_cancelling_round_stops_before_any_later_specialist_call():
 async def check():
  seen=[];started=asyncio.Event()
  async def complete(role,*args):
   seen.append(role);started.set();await asyncio.Event().wait()
  task=asyncio.create_task(DiscussionRuntime(complete).run(packet()))
  await asyncio.wait_for(started.wait(),2)
  task.cancel()
  with pytest.raises(asyncio.CancelledError):await task
  assert seen==['control']
 asyncio.run(check())


@pytest.mark.parametrize('field,value',[('window','prefix'),('club_id','away'),('player_id','p2'),('unit','percent'),('key','shots')])
def test_comparison_rejects_wrong_window_actor_metric_and_unit(field,value):
 p=packet();p['windows']={'previous':{'period':1,'start_ms':0,'end_ms':150000},'current':{'period':1,'start_ms':150000,'end_ms':300000}}
 p['metrics']=[{'id':'old','key':'passes','label':'Passes','window':'previous','club_id':'home','player_id':'p1','unit':'count','value':12},{'id':'new','key':'passes','label':'Passes','window':'current','club_id':'home','player_id':'p1','unit':'count','value':12}]
 p['metrics'][0][field]=value
 row=Contribution(**turn([],text='[[fact:0]]',metric_ids=['old','new'],facts=[{'metric_id':'new','compare_to':'old'}]))
 with pytest.raises(ValueError,match='incomparable_facts'):check_citations(row,p)


def test_fact_schema_cannot_supply_a_different_player_value_or_metric_label():
 from pydantic import ValidationError
 for field,value in [('subject','Another player'),('value',99),('label','Goals'),('window','previous')]:
  with pytest.raises(ValidationError):Contribution(**turn([],facts=[{'metric_id':'passes','compare_to':None,field:value}]))
 p=packet();p['metrics'][0].update(subject='Rory Ellis',player_id='eb09',club_id='home',unit='count')
 row=Contribution(**turn([]))
 assert render_facts(row,p).startswith('Rory Ellis — Passes: 12 (kick-off through H1 5:00).')


@pytest.mark.parametrize('text',['He has twelve goals.','He has 12 goals.','He has twice as many passes.','他有十二次传球。'])
def test_unbound_quantities_cannot_borrow_a_cited_number(text):
 with pytest.raises(ValueError):check_citations(Contribution(**turn([],text=text+' [[fact:0]]')),packet())


def test_uncited_same_surname_player_is_rejected():
 p=packet();p['players']=[{'player_id':'p1','name':'Rory Ellis'},{'player_id':'p2','name':'Alex Ellis'}]
 p['metrics'][0].update(player_id='p1',subject='Rory Ellis')
 with pytest.raises(ValueError,match='uncited_subject'):
  check_citations(Contribution(**turn([],text='[[fact:0]] Alex Ellis is involved.')),p)


def test_percentage_comparison_renders_percentage_points_not_percent_increase():
 p=packet();p['windows']={'previous':{'period':1,'start_ms':0,'end_ms':150000},'current':{'period':1,'start_ms':150000,'end_ms':300000}}
 p['metrics']=[{'id':'old','key':'pass_accuracy','label':'Pass completion','window':'previous','club_id':'home','unit':'percent','value':50},{'id':'new','key':'pass_accuracy','label':'Pass completion','window':'current','club_id':'home','unit':'percent','value':75}]
 row=Contribution(**turn([],text='[[fact:0]]',metric_ids=['old','new'],facts=[{'metric_id':'new','compare_to':'old'}]))
 assert 'change 25 percentage points' in render_facts(row,p)


def test_native_boundary_rebuilds_fact_text_and_rejects_tampered_drafts_or_old_protocol():
 from copy import deepcopy
 from counterpress.analyst.provider import FoundryDiscussion
 from counterpress.analyst.discussion import VERSION
 async def complete(role,prompt,data,schema,tokens):
  value=turn(data['conversation']) if role!='footie' else dict(facts=[],revisions=[],accepted_ids=['control','players','chance','defence'],text='Activity needs an end product.',watch_next='',metric_ids=['passes'],evidence_ids=[])
  return json.dumps(value),{}
 result=run(complete);source={**packet(),'players':[],'clubs':[]}
 provider=FoundryDiscussion.__new__(FoundryDiscussion)
 tampered=deepcopy(result);tampered['messages'][0]['text']='Wrong Player scored 99 goals.'
 verified=provider.validate(tampered,source,source)
 assert verified['messages'][0]['text']==result['messages'][0]['text']
 tampered['messages'][0]['draft_text']='Wrong Player scored ninety goals. [[fact:0]]'
 with pytest.raises(ValueError):provider.validate(tampered,source,source)
 with pytest.raises(ValueError,match='protocol'):provider.validate({**result,'protocol':'roundtable-v1'},source,source)
 assert result['protocol']==VERSION


def test_distinct_specialists_challenge_revise_and_synthesize_with_rendered_facts(tmp_path):
 p=packet();p.update(focus_player_id='p1',players=[{'player_id':'p1','name':'Rory Ellis'}],clubs=[{'club_id':'home','name':'Eastbridge'}])
 p['metrics']=[
  {'id':'team-passes','key':'passes','label':'Passes','window':'prefix','club_id':'home','unit':'count','value':12,'subject':'Eastbridge'},
  {'id':'player-passes','key':'passes','label':'Passes','window':'prefix','player_id':'p1','club_id':'home','unit':'count','value':5,'subject':'Rory Ellis'},
  {'id':'shots','key':'shots','label':'Shots','window':'current','club_id':'home','unit':'count','value':2,'subject':'Eastbridge'},
  {'id':'recoveries','key':'recoveries','label':'Recoveries','window':'current','club_id':'home','unit':'count','value':3,'subject':'Eastbridge'},
 ]
 p['windows']={'current':{'period':1,'start_ms':0,'end_ms':300000}}
 def contribution(text,metric,reply=None,relation='observation'):
  return dict(text=text,facts=[{'metric_id':metric,'compare_to':None}],metric_ids=[metric],evidence_ids=[],reply_to=reply,relation=relation)
 scripted={
  'control':contribution('[[fact:0]] This establishes dominance.','team-passes'),
  'players':contribution('[[fact:0]] I would question that reading: involvement alone does not establish control.','player-passes','control','challenges'),
  'chance':contribution('[[fact:0]] The player caution matters; shot opportunities give us a separate test of attacking payoff.','shots','players','builds_on'),
  'defence':contribution('[[fact:0]] Recoveries add context to those chances, but do not establish pressing intent.','recoveries','chance','qualifies'),
 }
 seen=[]
 async def complete(role,prompt,data,schema,tokens):
  seen.append((role,data['conversation']))
  if role!='footie': value=scripted[role]
  else:
   repaired={'id':'control','role':'control',**contribution('[[fact:0]] Ball circulation is visible, but this does not establish dominance.','team-passes')}
   value=dict(facts=[],accepted_ids=list(scripted),revisions=[repaired],text='The specialists agree that activity needs an attacking payoff; the player and defensive cautions keep the control reading tentative.',watch_next='Watch whether the next attack produces a supported chance.',metric_ids=['team-passes','shots','recoveries'],evidence_ids=[])
  return json.dumps(value),{'input_tokens':10,'output_tokens':20}
 result=asyncio.run(DiscussionRuntime(complete).run(p))
 assert result['status']=='complete' and result['execution']['model_calls']==5
 assert [m['role'] for m in result['messages']]==['control','players','chance','defence','footie']
 assert len({m['text'] for m in result['messages']})==5
 assert 'This establishes dominance.' not in json.dumps(result)
 assert 'does not establish dominance' in result['messages'][0]['text']
 assert 'Rory Ellis — Passes: 5' in result['messages'][1]['text']
 assert result['messages'][1]['relation']=='challenges'
 assert 'Eastbridge — Passes: 12' in seen[1][1][0]['text']
 assert result['messages'][-1]['relation']=='synthesis'
 (tmp_path/'scripted-conversation.json').write_text(json.dumps(result,indent=2))
