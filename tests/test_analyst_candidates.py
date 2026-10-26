"""Independent semantic counterexamples for exact localized Analyst candidates."""
import copy
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from integrations.analyst_foundry.contracts import parse_packet,clock_context
from counterpress.analyst.service import build_dispatch_packet,build_snapshot
from counterpress.analyst.contracts import AnalystRequest
from counterpress.personalization.store import DataStore
from counterpress.personalization.service import CareerService
from test_analyst_metrics import event,snap


def family(snapshot,name):return [c for c in snapshot['candidates']if c['id'].startswith('cp2-'+name+'-')]


def test_box_growth_does_not_imply_better_locations_than_previous_window():
    # Before:3/3 inside; now5shots butonly2inside. More shots!=betterpositions.
    rows=[event(i,t,kind='shot',outcome='blocked',start={'x':95 if i<=5 else 60,'y':34})for i,t in enumerate([100000,120000,140000,350000,360000,370000,380000,390000],1)]
    s=snap(rows)
    c=family(s,'box-growth')[0]['reading']
    assert c['headline']=='Home reach the box, but their shots are blocked.'
    assert '5 shots'in c['explanation'] and '3 before'in c['explanation'] and '2 came from inside'in c['explanation']
    assert 'closer'not in ' '.join(c[k]for k in ('headline','explanation'))
    assert 'getting closer'not in json.dumps(s['signals'])


def test_control_keeps_one_entry_and_action_counts_without_claiming_time_possession():
    rows=[event(i,320000+i*5000,start={'x':60,'y':34},end={'x':80 if i==1 else 65,'y':34})for i in range(1,26)]
    rows +=[event(26+i,330000+i*5000,club_id='away',player_id='a1')for i in range(1,6)]
    s=snap(rows);r=family(s,'activity-no-shot')[0]['reading']
    assert '25 on-ball actions'in r['explanation'] and 'only 1 completed pass into the final third'in r['explanation']
    assert 'possession'not in ' '.join(r[k]for k in ('headline','explanation'))
    assert 'Neither club has taken a shot'in r['alternative']


def transition_rows(outcome='goal'):
    # Home led1-0 before Away recovers an incomplete pass and equalizes.
    return [event(1,100000,kind='shot',outcome='goal',goal_for='home'),
        event(2,450000,outcome='incomplete',recipient_id='h2'),
        event(3,451211,club_id='away',player_id='a1',kind='recovery',outcome='established'),
        event(4,459186,club_id='away',player_id='a1',kind='shot',outcome=outcome,goal_for='away'if outcome=='goal'else None)]


def test_transition_duration_equalizer_and_score_are_bound_to_that_shot():
    rows=transition_rows()+[event(5,470000,club_id='away',player_id='a1',kind='shot',outcome='goal',goal_for='away')]
    s=snap(rows,480000);r=family(s,'regain-shot')[0]['reading']
    assert '7.975 seconds'in r['explanation']
    assert 'restored parity at 1–1'in r['explanation']
    assert s['score']=={'home':1,'away':2}
    assert any(m['key'].startswith('score_after_')and m['event_id']=='e4'and m['value']==1 for m in s['metrics'])
    p=build_dispatch_packet(s);parse_packet(json.dumps(p,ensure_ascii=False,separators=(',',':')))


def test_unknown_finish_never_becomes_a_known_miss():
    s=snap(transition_rows('unknown'),480000)
    assert not family(s,'regain-shot') and not family(s,'player-chain')


def test_failed_pass_intended_receiver_is_not_in_opponents_attacking_chain():
    s=snap(transition_rows(),480000,focus_player_id='h2')
    assert family(s,'regain-shot')
    assert not [c for c in s['candidates']if c['role']=='players']


def test_restart_or_broken_actor_chain_abstains():
    rows=transition_rows()
    assert not family(snap(rows[:3]+[rows[3].model_copy(update={'restart':True})],480000),'regain-shot')
    assert not family(snap(rows[:3]+[rows[3].model_copy(update={'club_id':'home','player_id':'h1','goal_for':'home'})],480000),'regain-shot')


def test_passing_decline_requires_less_progression_and_complete_known_windows():
    prior=[event(i+1,100000+i*10000,start={'x':60,'y':34},end={'x':80 if i<3 else 65,'y':34})for i in range(10)]
    current=[event(i+11,350000+i*10000,outcome='complete'if i<6 else'incomplete',start={'x':60,'y':34},end={'x':65,'y':34})for i in range(10)]
    s=snap(prior+current);r=family(s,'passing-progress')[0]['reading']
    assert '100.0% to 60.0%'in r['explanation'] and '3 to 0'in r['explanation']
    assert 'why individual passes failed'in r['alternative']
    assert not family(snap(prior+current[:-1]+[current[-1].model_copy(update={'outcome':'unknown'})]),'passing-progress')
    assert not family(snap(prior+current,599999),'passing-progress')


def test_chinese_player_chain_and_casual_depth_are_deterministic():
    args={'ms':480000,'focus_player_id':'a1'}
    detailed=snap(transition_rows(),language='zh-Hans',**args)
    casual=snap(transition_rows(),language='zh-Hans',depth='casual',**args)
    d=family(detailed,'player-chain')[0]['reading'];c=family(casual,'player-chain')[0]['reading']
    assert '7.975秒'in d['explanation'] and '7.975秒'not in c['explanation']
    assert '把比分扳成1比1'in d['explanation']
    assert '夺回球权'in d['headline'] and 'a1'in d['headline']
    assert d['metric_ids']==c['metric_ids']
    assert detailed['candidates']==snap(transition_rows(),language='zh-Hans',**args)['candidates']
    for s in(detailed,casual):parse_packet(json.dumps(build_dispatch_packet(s),ensure_ascii=False,separators=(',',':')))


def test_early_spells_abstain_without_basic_event_fillers():
    assert snap([event(1,1000)],91000)['candidates']==[]


def test_proof_only_facts_have_display_flag():
    s=snap(transition_rows(),480000)
    proof=[m for m in s['metrics']if m['key'].startswith(('transition_','score_after_'))]
    assert proof and all(m['presentation']=='evidence_only'for m in proof)
    assert any(m['key']=='shots_inside_box'and m.get('presentation')!='evidence_only'for m in s['metrics'])


def test_canonical_regression_candidates_language_and_native_budget():
    career=CareerService(DataStore(Path('fixtures/personalization')))
    cases=[('wyscout-2058017',1,2581000,None,'box-growth'),('synthetic-32fe41c5d304ce68d7d9',1,630000,None,'activity-no-shot'),('synthetic-32fe41c5d304ce68d7d9',2,2314000,'np10','player-chain')]
    for mid,period,ms,focus,expected in cases:
        for lang in('en','zh-Hans'):
            for depth in('casual','analyst'):
                s=build_snapshot(career,mid,AnalystRequest(cutoff={'period':period,'elapsed_ms':ms},language=lang,depth=depth,focus_player_id=focus))
                assert family(s,expected)
                p=build_dispatch_packet(s);raw=json.dumps(p,ensure_ascii=False,separators=(',',':'))
                assert len(raw)<=24000 and len(raw.encode())<=32000
                parse_packet(raw)
                if focus:
                    r=family(s,'player-chain')[0]['reading'];assert 'Isaac Lane'in r['explanation']
                    assert ('射门偏出'in r['explanation'])if lang=='zh-Hans'else('missed the target'in r['explanation'])


def test_phase_lengths_use_fixture_stoppage_not_hardcoded_45_minutes():
    career=CareerService(DataStore(Path('fixtures/personalization')))
    s=build_snapshot(career,'wyscout-2058017',AnalystRequest(cutoff={'period':1,'elapsed_ms':2700000}))
    p=build_dispatch_packet(s)
    assert p['period_lengths_ms']['1']>2700000
    assert clock_context(p)['half_time_boundary'] is False
