"""Regressions from the actual 5x replay: skipped goals, peer links and spend."""
import copy
from concurrent.futures import ThreadPoolExecutor
import pytest
from counterpress.analyst.live import priority_events, choose_role, live_packet, check_comment, clean_citation_annotations, Comment
from counterpress.analyst.live_admission import LiveAllowance, accounted_cents, settle_completed
from counterpress.analyst.admission import SQLiteStore
from test_analyst_metrics import event, snap


def metered(**changes):
    execution=dict(model='gpt-5-mini',review_model='gpt-5-mini',model_calls=2,
        input_tokens=5000,output_tokens=1000,
        per_role_usage=[dict(input_tokens=2500,output_tokens=500,usage_complete=True)]*2)
    return {'execution':execution|changes,'messages':[]}


def test_settlement_uses_conservative_round_up_and_complete_usage_only():
    assert accounted_cents(metered())==1
    assert accounted_cents(metered(input_tokens=6000,output_tokens=2000,
        per_role_usage=[dict(input_tokens=3000,output_tokens=1000)]*2))==2
    for changes in ({'model_calls':3},{'model':'unknown'},{'input_tokens':1},
                    {'per_role_usage':[]},{'per_role_usage':[dict(input_tokens=2500,output_tokens=500,usage_complete=False)]*2},
                    {'input_tokens':0,'per_role_usage':[dict(input_tokens=0,output_tokens=500)]*2}):
        assert accounted_cents(metered(**changes))==3
    assert accounted_cents(None)==3


def test_legacy_reconciliation_is_idempotent_and_keeps_unknown_costs():
    state={'spent_cents':9,'matches':{'match':9},'jobs':{
        'complete':{'match_id':'match','status':'complete','result':metered()},
        'failed':{'match_id':'match','status':'unavailable','result':None},
        'partial':{'match_id':'match','status':'complete','result':metered(model_calls=3)}}}
    settle_completed(state)
    assert state['spent_cents']==7 and state['matches']['match']==7 and state['released_cents']==2
    before=copy.deepcopy(state);settle_completed(state);assert state==before
    assert state['jobs']['complete']['accounted_cents']==1


def test_shared_settlement_still_enforces_match_cap_and_survives_restart(tmp_path):
    store=SQLiteStore(tmp_path/'budget.sqlite3');a=LiveAllowance(store)
    for i in range(268):
        job=a.reserve(str(i),i*3,'match','scope',{'period':1,'elapsed_ms':i*1000})
        assert job['admitted'];a.finish(str(i),job['owner'],metered(),i*3+1)
        # A duplicate finish cannot release money twice.
        a.finish(str(i),job['owner'],metered(),i*3+2)
    a=LiveAllowance(store)
    assert a.reserve('new',1000,'match','other',{'period':2,'elapsed_ms':0})['status']=='budget_limit'
    assert a.reserve('0',1000,'match','scope',{'period':1,'elapsed_ms':0})['status']=='complete'
    assert store.transact(lambda s:(s,s['spent_cents']))==268


def test_wrong_owner_and_expired_work_do_not_release_reservation(tmp_path):
    store=SQLiteStore(tmp_path/'budget.sqlite3');a=LiveAllowance(store)
    j=a.reserve('one',0,'match','scope',{'period':1,'elapsed_ms':0})
    a.finish('one','not-owner',metered(),1)
    a.finish('one',j['owner'],metered(),61)
    assert store.transact(lambda s:(s,s['spent_cents']))==3


def test_concurrent_viewers_share_one_reservation_and_one_settlement(tmp_path):
    store=SQLiteStore(tmp_path/'budget.sqlite3');a=LiveAllowance(store)
    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs=list(pool.map(lambda _:a.reserve('same',0,'match','scope',{'period':1,'elapsed_ms':1000}),range(6)))
        assert sum(bool(j.get('admitted')) for j in jobs)==1
        owner=next(j['owner'] for j in jobs if j.get('admitted'))
        list(pool.map(lambda _:a.finish('same',owner,metered(),1),range(6)))
    state=store.transact(lambda s:(s,s))
    assert state['spent_cents']==1 and state['released_cents']==2


def test_unknown_legacy_usage_cannot_create_headroom_at_the_cap(tmp_path):
    store=SQLiteStore(tmp_path/'budget.sqlite3');a=LiveAllowance(store)
    state={'spent_cents':270,'matches':{'match':270},'jobs':{
        'old':{'status':'complete','match_id':'match','expires':100,'result':{'execution':{'input_tokens':10,'output_tokens':20}}}}}
    store.transact(lambda _:(state,None))
    assert a.reserve('new',1,'match','scope',{'period':1,'elapsed_ms':1000})['status']=='budget_limit'


def goal_source():
    # An own goal at 17:58, followed by unrelated passes; next 5x turn at 21:00.
    return snap([event(1,1078000,club_id='away',player_id='a1',kind='other',outcome='own_goal',goal_for='home')]
        +[event(i,1200000+i*1000,recipient_id='h2' if i%2==0 else 'h1',player_id='h1' if i%2==0 else 'h2') for i in range(2,20)],ms=1260000,focus_player_id='h1')


def test_unhandled_own_goal_survives_coalesced_minutes_and_routine_passages():
    s=goal_source();past=[dict(role='control',text='Earlier reading',cutoff={'period':1,'elapsed_ms':960000},evidence_ids=[])]
    assert choose_role(s,past)=='chance'
    packet=live_packet(s,'chance',past)
    assert packet['priority_event_ids']==['e1:r1']
    goal=next(e for e in packet['evidence'] if e['id']=='e1:r1')
    assert goal['scoring_club']=='Home' and goal['club']=='Away'
    assert packet['passages']==[] # Do not attach the 20th-minute passes to the own goal.
    c=Comment(text='Home benefit from an own goal; the lead arrived without a recorded shot in this passage.',metric_ids=[],evidence_ids=['e1:r1'],reply_to=None,relation='observation',visual='none')
    check_comment(c,packet,past,'chance')
    with pytest.raises(ValueError,match='missed_priority_event'):
        check_comment(c.model_copy(update={'evidence_ids':[],'metric_ids':['current:home:shots']}),packet,past,'chance')


def test_failed_turn_does_not_acknowledge_goal_but_published_turn_does():
    s=goal_source();failed=[dict(role='chance',text='',attempt_only=True,cutoff={'period':1,'elapsed_ms':1200000})]
    assert priority_events(s,failed)
    accepted=[dict(role='chance',text='Own goal.',cutoff=s['cutoff'],evidence_ids=['e1:r1'])]
    assert not priority_events(s,accepted)
    old=snap([event(1,1000,goal_for='home',kind='shot',outcome='goal')],ms=1260000)
    assert not priority_events(old) # Fresh seek does not announce an ancient goal.
    assert not priority_events(snap([event(1,1260001,kind='shot',outcome='goal',goal_for='home')],ms=1260000))


def test_reply_assignment_is_specific_historical_and_anchored():
    s=snap([event(1,560000,recipient_id='h2'),event(2,562000,player_id='h2',kind='shot',outcome='saved')])
    history=[dict(role='control',text='Home reached the box but had no attempt yet.',cutoff={'period':1,'elapsed_ms':561000},evidence_ids=['e1:r1'])]
    packet=live_packet(s,'chance',history)
    assert packet['reply_assignment']['role']=='control'
    assert packet['reply_assignment']['point']==history[0]['text']
    assert 'e1:r1' in {e['id'] for e in packet['evidence']}
    assert live_packet(s,'chance',[dict(history[0],text='',attempt_only=True)])['reply_assignment'] is None


def test_observed_off_ball_causality_error_is_blocked_even_if_editor_approves():
    p=live_packet(snap([event(1,599000)]),'control')
    c=Comment(text='The carry pulled Northport wide.',metric_ids=[],evidence_ids=['e1:r1'],reply_to=None,relation='observation',visual='none')
    with pytest.raises(ValueError,match='unsupported_off_ball_movement'):check_comment(c,p,[],'control')


def test_named_reference_annotations_are_removed_but_facts_are_not_rewritten():
    source={'players':[{'name':'Rory Ellis'}],'clubs':[{'name':'Eastbridge'}]}
    assert clean_citation_annotations('He advanced (Rory Ellis e1 → e2).',source)=='He advanced.'
    assert clean_citation_annotations('He advanced (e1 shows a goal).',source)=='He advanced (e1 shows a goal).'
    assert clean_citation_annotations('He advanced (possibly).',source)=='He advanced (possibly).'
    assert clean_citation_annotations('He recovered (Rory Ellis recovery, e5).',source)=='He recovered (Rory Ellis recovery).'
    assert clean_citation_annotations('The move (Ellis pass e5, Cole carry e6).',source)=='The move (Ellis pass, Cole carry).'


def test_repeating_a_discussed_passage_is_not_a_new_contribution():
    s=snap([event(1,599000)])
    history=[dict(role='players',text='A completed pass.',evidence_ids=['e1:r1'],cutoff={'period':1,'elapsed_ms':599000})]
    p=live_packet(s,'control',history)
    c=Comment(text='The pass kept possession.',metric_ids=[],evidence_ids=['e1:r1'],reply_to='players',relation='builds_on',visual='none')
    with pytest.raises(ValueError,match='repeated_passage'):check_comment(c,p,history,'control')


def test_reference_only_see_annotations_are_formatting_not_factual_edits():
    assert clean_citation_annotations('The shot was blocked (see e1–e7).',{})=='The shot was blocked.'
    assert clean_citation_annotations('The shot was blocked (See e1, e2).',{})=='The shot was blocked.'
    assert clean_citation_annotations('The shot (see e1 shows a goal).',{})=='The shot (see e1 shows a goal).'


def test_new_play_cannot_invent_a_correction_to_a_peer():
    p=live_packet(snap([event(1,599000)]),'control')
    c=Comment(text='That recovery line misattributes the finish to a different player.',metric_ids=[],evidence_ids=['e1:r1'],reply_to=None,relation='observation',visual='none')
    with pytest.raises(ValueError,match='unsupported_peer_correction'):check_comment(c,p,[],'control')


def test_shot_destination_cannot_be_claimed_as_its_origin():
    from counterpress.analyst.live import model_source
    p=live_packet(snap([event(1,599000,kind='shot',outcome='goal',goal_for='home',start={'x':80,'y':34},end={'x':105,'y':34})]),'chance')
    c=Comment(text='The move ended with a shot from the penalty box.',metric_ids=[],evidence_ids=['e1:r1'],reply_to=None,relation='observation',visual='none')
    with pytest.raises(ValueError,match='unsupported_shot_location'):check_comment(c,p,[],'chance')
    check_comment(c.model_copy(update={'text':'The move ended with a shot from the centre of the attacking third.'}),p,[],'chance')
    wire=model_source(p)['evidence'][0]
    assert wire['ball_destination_area']=='centre of the penalty box' and 'to_area' not in wire


def test_named_factual_annotation_keeps_words_when_removing_reference_range():
    assert clean_citation_annotations('The move (Lucas Hart recovery and forward pass e4–e6).',{})=='The move (Lucas Hart recovery and forward pass).'


def test_ball_direction_does_not_establish_attacking_intent():
    p=live_packet(snap([event(1,599000)]),'control')
    c=Comment(text='That sequence underlines the drop in attacking intent.',metric_ids=[],evidence_ids=['e1:r1'],reply_to=None,relation='observation',visual='none')
    with pytest.raises(ValueError,match='unsupported_tactical_intent'):check_comment(c,p,[],'control')
