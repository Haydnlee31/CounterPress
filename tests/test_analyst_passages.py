"""Independent passages: source order, visibility, related actors and boundaries."""
import pytest
from test_analyst_metrics import event,snap
from counterpress.analyst.live import live_packet,check_comment,Comment,choose_role
from counterpress.analyst.live_admission import LiveAllowance
from counterpress.analyst.admission import SQLiteStore


def linked():
 return [event(1,560000,kind='recovery',outcome='established'),
         event(2,562000,recipient_id='h2',start={'x':35,'y':20},end={'x':75,'y':30}),
         event(3,565000,player_id='h2',kind='carry',outcome='controlled',start={'x':75,'y':30},end={'x':90,'y':30}),
         event(4,568000,player_id='h2',kind='shot',outcome='saved',start={'x':90,'y':30})]


def test_recovery_to_shot_is_grounded_in_all_intervening_actions():
 s=snap(linked(),focus_player_id='h1');p=s['passages'][0]
 assert p['evidence_ids']==['e1:r1','e2:r1','e3:r1','e4:r1']
 assert p['links']==['same_holder','recipient','same_holder'] and p['ending']=='shot'
 packet=live_packet(s,'players')
 assert packet['passages'][0]['evidence_ids']==p['evidence_ids']
 assert {e['id']for e in packet['evidence']}>=set(p['evidence_ids'])
 check_comment(Comment(text='h1 supplied h2, who carried the ball forward before shooting.',metric_ids=[],evidence_ids=p['evidence_ids'],reply_to=None,relation='observation',visual='pass_routes'),packet,[],'players')


@pytest.mark.parametrize('change', ['opponent','restart','recipient','missing_order','delayed','unknown'])
def test_never_stitches_across_a_break_or_unseen_action(change):
 rows=linked()
 if change=='opponent':rows[2]=rows[2].model_copy(update={'club_id':'away','player_id':'a1'})
 if change=='restart':rows[2]=rows[2].model_copy(update={'restart':True})
 if change=='recipient':rows[2]=rows[2].model_copy(update={'player_id':'h1'})
 if change=='missing_order':rows=rows[:2]+rows[3:]
 if change=='delayed':rows[2]=rows[2].model_copy(update={'available_ms':600001})
 if change=='unknown':rows[1]=rows[1].model_copy(update={'outcome':'unknown'})
 assert not any('e1:r1' in p['evidence_ids'] and 'e4:r1' in p['evidence_ids'] for p in snap(rows)['passages'])


def test_unknown_archive_recipient_supports_only_team_chronology():
 rows=linked();rows[1]=rows[1].model_copy(update={'recipient_id':None})
 assert snap(rows)['passages'][0]['links'][1]=='team_order_only'


def test_revision_retraction_delivery_cap_and_halftime_change_passages():
 rows=linked();revised=rows[1].model_copy(update={'revision':2,'delivery_sequence':5,'available_ms':590000,'outcome':'incomplete'})
 before=snap(rows+[revised],580000);after=snap(rows+[revised])
 assert before['passages'][0]['ending']=='shot'
 assert not any('e1:r1' in p['evidence_ids'] and 'e4:r1' in p['evidence_ids'] for p in after['passages'])
 assert snap(rows+[revised],through_sequence=4)['passages']==before['passages']
 removed=revised.model_copy(update={'revision':3,'delivery_sequence':6,'available_ms':595000,'retracted':True})
 assert not any('e1:r1' in p['evidence_ids'] and 'e4:r1' in p['evidence_ids'] for p in snap(rows+[revised,removed])['passages'])
 assert not snap(rows,2000,period=2)['passages']


def test_passages_bound_payload_and_cannot_exceed_known_cutoff():
 rows=[event(i,500000+i*1000,player_id='h1' if i%2 else 'h2',recipient_id='h2' if i%2 else 'h1')for i in range(1,100)]
 s=snap(rows,550000)
 assert len(s['passages'])<=3
 for p in s['passages']:
  assert len(p['evidence_ids'])<=7 and p['end_ms']<=550000
  assert set(p['evidence_ids'])<={e['id']for e in s['evidence']}
 assert s['passages'][0]['start_truncated'] is True and s['passages'][0]['ending']=='ongoing'


def test_rejected_turn_rotates_without_leaking_unpublished_prose(tmp_path):
 a=LiveAllowance(SQLiteStore(tmp_path/'budget.sqlite3'))
 cut={'period':1,'elapsed_ms':540000};job=a.reserve('first',0,'match','scope',cut)
 a.finish('first',job['owner'],{'messages':[],'execution':{'scheduled_role':'control','publication_decision':'unsupported_claim'}},1)
 later=a.reserve('second',2,'match','scope',{'period':1,'elapsed_ms':600000})
 assert later['history']==[{'role':'control','text':'','attempt_only':True,'cutoff':cut}]
 assert choose_role(snap([event(1,599999)],focus_player_id='h1'),later['history'])=='players'
 assert a.reserve('earlier',3,'match','other',{'period':1,'elapsed_ms':500000})['history']==[]


def test_failed_pass_is_not_promoted_to_confirmed_turnover():
 rows=linked()[:2];rows[1]=rows[1].model_copy(update={'outcome':'incomplete'})
 s=snap(rows)
 assert s['passages'][0]['ending']=='incomplete_pass'
 assert next(m for m in s['metrics'] if m['id']=='current:home:verified_turnovers')['value']==0
