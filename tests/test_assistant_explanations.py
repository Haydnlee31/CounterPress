"""Explanation fidelity against small, independently authored observations."""
from types import SimpleNamespace
import re
import pytest

from counterpress.assistant.contracts import AskRequest
from counterpress.assistant.service import AssistantService, blank, asks_regain_interval, metric_label, METRICS
from counterpress.assistant.narrative import build_claims, default_story, render_story
from counterpress.personalization.contracts import Action, Appearance, Fixture
from counterpress.personalization.metrics import digest


@pytest.fixture
def sandbox(tmp_path):
    fixture=Fixture(match_id='explanation-match',season='2026-27',kickoff='2026-10-19T15:00:00Z',
        home_id='home',away_id='away',competition='Test',source_kind='calibrated_simulation',
        appearances=tuple(Appearance(player_id=p,club_id=c,start_ms=0,end_ms=5400000,starter=True)
            for p,c in [('h1','home'),('h2','home'),('a1','away')]))
    (tmp_path/'highlights.json').write_text('[]')
    def event(i,kind,at,**changes):
        return Action(**(dict(match_id=fixture.match_id,event_id=f'e{i}',revision=1,delivery_sequence=i,
            occurrence_order=i,period=1,elapsed_ms=at,available_period=1,available_ms=at,
            club_id='home',player_id='h1',kind=kind,outcome='controlled',source_reference=f'authored:{i}')|changes))
    service=AssistantService.__new__(AssistantService)
    service.scope=lambda request: ('2026-10-20T00:00:00Z',['2026-27'])
    service.career=SimpleNamespace()
    def attach(events,source='calibrated_simulation',appearances=None):
        f=fixture.model_copy(update={'source_kind':source,**({'appearances':appearances} if appearances else {})})
        service.store=SimpleNamespace(root=tmp_path,
            row=lambda mid: {'fixture':f.model_dump_json(),'digest':digest(events)},
            events=lambda mid: events,evidence_digest=lambda *args: digest(events),rows=lambda **kwargs: [],
            players={p:SimpleNamespace(name=n,role=r,club_id=c) for p,n,r,c in
                [('h1','Alex Vale','FW','home'),('h2','Ben Reed','MF','home'),('a1','Cole Finch','GK','away')]},
            clubs={'home':SimpleNamespace(name='Home'),'away':SimpleNamespace(name='Away')})
        return service
    def answer(events,question,analysis='buildup',at=9500,source='calibrated_simulation',**kwargs):
        service=attach(events,source,kwargs.pop('appearances',None))
        body=AskRequest(question=question,match_id=fixture.match_id,cutoff={'period':1,'elapsed_ms':at},**kwargs)
        plan=blank('match',match_id=fixture.match_id,analysis=analysis,player_ids=['a1'] if analysis=='player_performance' else [])
        return service.intelligence_answer(plan,body),plan,body
    return fixture,event,attach,answer


@pytest.mark.parametrize('question',[
    'Does this buildup begin when the team first won control, or show only the final part?',
    'Does the full move appear in the timeline?',
    'Where did possession begin before the goal?',
    'Was control established before this sequence?',
    '这次进攻的起点确定了吗，还是只有进攻末段？',
])
def test_possession_origin_questions_answer_missing_start_directly(sandbox,question):
    _,event,_,answer=sandbox
    events=[event(1,'carry',6000),event(2,'shot',9000,outcome='goal',goal_for='home',available_ms=9500)]
    result,plan,body=answer(events,question)
    assert asks_regain_interval(question)
    assert 'does not establish' in result['text'][0]
    assert 'not a confirmed full possession' in result['text'][0]
    assert next(f['value'] for f in result['facts'] if f['metric']=='regain_to_shot_seconds') is None
    claims=build_claims(result,plan,body)
    required=[c for c in claims if c.get('required')]
    assert len(required)==1 and required[0]['text']==result['text'][0]
    assert required[0] in default_story(claims,'casual')
    other=next(c for c in claims if not c.get('required'))
    with pytest.raises(ValueError):render_story({'lead':other['id'],'supporting':[]},claims,'casual')


def test_carry_only_finish_leads_with_action_not_zero_passes(sandbox):
    _,event,_,answer=sandbox
    result,plan,body=answer([event(1,'carry',6000),event(2,'shot',9000,outcome='goal',goal_for='home')],
                           'Explain this goal buildup.')
    assert 'carried the ball and finished with a goal' in result['text'][0]
    assert '0 completed' not in ' '.join(result['text'])
    assert '3 seconds' in result['text'][0]
    assert next(f['value'] for f in result['facts'] if f['metric']=='completed_passes')==0
    assert default_story(build_claims(result,plan,body),'casual')[0]['text']==result['text'][0]


def test_shot_only_suffix_does_not_claim_an_entire_attack(sandbox):
    _,event,_,answer=sandbox
    result,_,_=answer([event(1,'shot',9000,outcome='goal',goal_for='home')],'Explain this goal buildup.')
    assert 'scoring shot, without an earlier buildup' in result['text'][0]
    assert not any('0 completed' in line for line in result['text'])


def test_goalkeeper_summary_cites_saves_and_concessions_not_blame_or_future(sandbox):
    _,event,_,answer=sandbox
    events=[event(1,'shot',1000,outcome='saved',goalkeeper_id='a1'),
        event(2,'shot',2000,outcome='off_target'),
        event(3,'shot',3000,outcome='goal',goal_for='home'),
        event(4,'shot',4000,player_id='a1',club_id='away',outcome='own_goal',goal_for='home'),
        event(5,'shot',6000,outcome='saved',goalkeeper_id='a1')]
    result,plan,body=answer(events,'How is Cole Finch doing in this match?','player_performance',at=5000)
    facts={f['metric']:f for f in result['facts']}
    assert facts['saves']['value']==1 and facts['goals_conceded']['value']==2
    assert '1 save' in result['text'][0] and '2 goals' in result['text'][0]
    assert 'during their time on the pitch' in result['text'][0]
    assert 'mistake' not in result['text'][0]
    assert all(ref['elapsed_ms']<=5000 for ref in facts['saves']['evidence']['events'])
    assert {ref['event_id'] for ref in facts['saves']['evidence']['events']}=={'e1','e2','e3','e4'}
    assert default_story(build_claims(result,plan,body),'casual')[0]['required'] is True
    correction=events[0].model_copy(update={'revision':2,'delivery_sequence':6,'available_ms':5000,'outcome':'off_target','goalkeeper_id':None})
    changed,_,_=answer(events+[correction],'How is Cole Finch doing in this match?','player_performance',at=5000)
    assert next(f['value'] for f in changed['facts'] if f['metric']=='saves')==0


@pytest.mark.parametrize('source,outcome,keeper',[
    ('adapted_archive','saved','a1'),('calibrated_simulation','saved',None),
    ('calibrated_simulation','on_target',None),('calibrated_simulation','unknown',None),
])
def test_missing_keeper_coverage_is_unavailable_not_zero(sandbox,source,outcome,keeper):
    _,event,_,answer=sandbox
    result,_,_=answer([event(1,'shot',1000,outcome=outcome,goalkeeper_id=keeper)],
        'How is Cole Finch doing in this match?','player_performance',at=2000,source=source)
    assert next(f['value'] for f in result['facts'] if f['metric']=='saves') is None
    assert 'do not identify saves reliably' in result['text'][0]


def test_goalkeeper_conceded_scope_respects_substitution(sandbox):
    fixture,event,_,answer=sandbox
    appearances=tuple(a.model_copy(update={'start_ms':2500,'starter':False}) if a.player_id=='a1' else a for a in fixture.appearances)
    result,_,_=answer([event(1,'shot',1000,outcome='goal',goal_for='home'),event(2,'shot',3000,outcome='goal',goal_for='home')],
        'How is Cole Finch doing in this match?','player_performance',at=4000,appearances=appearances)
    assert next(f['value'] for f in result['facts'] if f['metric']=='goals_conceded')==1


@pytest.mark.parametrize('metric,per90,value,label',[('goals',False,100,'进球'),('assists',True,.4,'助攻'),('pass_accuracy',False,80,'传球成功率')])
def test_chinese_career_sentence_fact_and_chart_labels_are_localized(sandbox,metric,per90,value,label):
    _,_,attach,_=sandbox
    service=attach([])
    unit='per90' if per90 else 'percent' if metric=='pass_accuracy' else 'count'
    f={'subject_id':'h1','subject_name':'Alex Vale','subject_kind':'player','metric':metric,'label':METRICS[metric][1],
        'value':value,'unit':unit,'scope':{'season':None,'window':'whole_period','matches':10},
        'coverage':{'recorded_matches':10,'total_matches':10},'href':'#football/player/h1','evidence':{}}
    service.measure=lambda *args,**kwargs: (dict(f),{'heatmap':{'cells':[]}})
    plan=blank('stats',player_ids=['h1'],metric=metric,per90=per90)
    body=AskRequest(question='查看生涯数据',preferences={'language':'zh-Hans'})
    result=service._answer_single(plan,body)
    assert label in result['text'][0] and result['facts'][0]['label']==label
    assert METRICS[metric][1].lower() not in result['text'][0].lower()
    if per90:assert '/90分钟' in result['text'][0]
    if unit=='percent':assert '80%' in result['text'][0]


def test_every_supported_metric_has_a_chinese_label():
    assert all(re.search('[\u4e00-\u9fff]',metric_label(key,True)) for key in METRICS)
