import json
from types import SimpleNamespace
import pytest
from counterpress.analyst.live import Comment,live_packet
from counterpress.analyst.memory import conclusion,public_memory
from counterpress.analyst.live_admission import LiveAllowance
from counterpress.analyst.admission import SQLiteStore
from test_analyst_metrics import event,snap


def setup(topic='sterile_circulation'):
    s=live_packet(snap([event(1,599000)]),'control')
    d=Comment(text='The passing is keeping possession without danger.',metric_ids=[],evidence_ids=['e1:r1'],reply_to=None,relation='observation',visual='none')
    r=SimpleNamespace(topic=topic,subject_id='home',novelty='first',prior_memory_id=None,new_reading='Circulation without danger.')
    return s,d,r


def test_paraphrase_new_counts_and_different_speaker_cannot_repeat_lesson():
    s,d,r=setup();m=conclusion(r,d,s,[]);history=[{'role':'players','memory':m}]
    r.novelty='new_mechanism';r.prior_memory_id=m['id']
    d=d.model_copy(update={'text':'The recoveries are not producing shots.'})
    r.topic='ball_winning' # central-lesson normalization catches this observed bypass
    with pytest.raises(ValueError,match='repeated_conclusion'):conclusion(r,d,s,history)


def test_new_score_can_change_meaning_but_missing_comparison_cannot():
    s,d,r=setup();m=conclusion(r,d,s,[]);history=[{'memory':m}]
    r.novelty='new_outcome';s['score']={**s['score'],'home':1}
    with pytest.raises(ValueError,match='uncompared_conclusion'):conclusion(r,d,s,history)
    r.prior_memory_id=m['id'];assert conclusion(r,d,s,history)['score']['home']==1


def test_distinct_player_contribution_is_not_suppressed_by_club_memory():
    s,d,r=setup();m=conclusion(r,d,s,[])
    r.topic='player_link_play';r.subject_id='h1';d=d.model_copy(update={'text':'His pass reached a teammate in the attacking third.'})
    assert conclusion(r,d,s,[{'memory':m}])['subject_id']=='h1'


def test_unknown_subject_and_invented_memory_cannot_publish():
    s,d,r=setup();r.subject_id='invented'
    with pytest.raises(ValueError,match='unknown_conclusion_subject'):conclusion(r,d,s,[])
    r.subject_id='home';r.prior_memory_id='made-up'
    with pytest.raises(ValueError,match='unknown_memory_reference'):conclusion(r,d,s,[])


def test_same_shot_does_not_become_new_when_local_reference_changes():
    s,d,r=setup('finishing');s['evidence'][0]['kind']='shot';d=d.model_copy(update={'text':'The shot was blocked.'})
    m=conclusion(r,d,s,[],{'e1:r1':'canonical-shot'});r.novelty='new_outcome';r.prior_memory_id=m['id']
    with pytest.raises(ValueError,match='no_new_outcome'):conclusion(r,d,s,[{'memory':m}],{'e1:r1':'canonical-shot'})
    assert conclusion(r,d,s,[{'memory':m}],{'e1:r1':'different-shot'})['novelty']=='new_outcome'


def test_memory_survives_restart_is_bounded_and_never_leaks_from_future_or_other_scope(tmp_path):
    path=tmp_path/'memory.sqlite3';a=LiveAllowance(SQLiteStore(path))
    for i in range(22):
        cutoff={'period':1,'elapsed_ms':(i+1)*60000}
        j=a.reserve(str(i),i*3,'match','scope',cutoff)
        a.finish(str(i),j['owner'],{'messages':[{'role':'control','text':f'Lesson {i}'}],
            'conversation_memory':{'id':str(i),'topic':'ball_winning','subject_id':'home','takeaway':f'Lesson {i}'}},i*3+1)
    a=LiveAllowance(SQLiteStore(path))
    j=a.reserve('last',100,'match','scope',{'period':2,'elapsed_ms':1000})
    assert len([m for m in j['history'] if m.get('memory')])==18
    assert len(public_memory(j['history']))==1
    assert public_memory(j['history'])[0]['id']=='21'
    assert a.reserve('seek',101,'match','scope',{'period':1,'elapsed_ms':1000})['history']==[]
    a.finish('last',j['owner'],None,102)
    assert a.reserve('other',103,'match','other-scope',{'period':2,'elapsed_ms':2000})['history']==[]


@pytest.mark.parametrize('text',[
    'His recovery removed a dangerous outlet on the flank.',
    'His duel win blunted their momentum.',
    'His forward pass shifted the tempo.',
])
def test_true_event_cannot_support_an_unobserved_tactical_effect(text):
    from counterpress.analyst.live import check_comment
    s,d,_=setup()
    with pytest.raises(ValueError,match='unsupported_event_effect'):check_comment(d.model_copy(update={'text':text}),s,[],'control')


def test_explicit_allowance_grant_preserves_costs_is_idempotent_and_match_scoped(tmp_path):
    store=SQLiteStore(tmp_path/'grant.sqlite3');a=LiveAllowance(store)
    store.transact(lambda _:({'spent_cents':270,'matches':{'match':270}},None))
    assert a.reserve('blocked',0,'match','scope',{'period':1,'elapsed_ms':60000})['status']=='budget_limit'
    a.grant_match_allowance('approved-once','match',100,'Explicit user approval')
    a.grant_match_allowance('approved-once','match',100,'Explicit user approval')
    a=LiveAllowance(SQLiteStore(tmp_path/'grant.sqlite3'))
    assert a.reserve('allowed',1,'match','scope',{'period':1,'elapsed_ms':60000})['admitted']
    state=store.transact(lambda s:(s,s))
    assert state['spent_cents']==273 and state['matches']['match']==273
    assert len(state['approved_grants'])==1
    from counterpress.history import HistoryStorageError
    with pytest.raises(HistoryStorageError):a.grant_match_allowance('another','match',1,'No double top-up')
    with pytest.raises(HistoryStorageError):a.grant_match_allowance('approved-once','other',100,'Explicit user approval')
    state['spent_cents']=1200;store.transact(lambda _:(state,None))
    assert a.reserve('global-limit',2,'match','scope',{'period':1,'elapsed_ms':120000})['status']=='budget_limit'


def test_large_memory_compaction_preserves_every_value_and_does_not_mutate_inputs():
    import copy
    from counterpress.analyst.memory import compact_context
    data={'source':{'evidence':[{'id':'e1','actor':'A'}],'conversation_memory':[
        {'id':str(i),'topic':'ball_winning','subject_id':'home','takeaway':'A prior lesson'} for i in range(18)]},'conversation':[{'text':'An earlier comment'}]}
    before=copy.deepcopy(data)
    assert compact_context(SimpleNamespace(deployment='gpt-5-mini'),'short',data,{},'test',2000) is data
    result=compact_context(SimpleNamespace(deployment='gpt-5-mini'),'short',data,{},'test',2000,limit=1)
    m=result['source']['conversation_memory']
    assert [dict(zip(m['columns'],r)) for r in m['rows']]==data['source']['conversation_memory']
    assert data==before and result['source']['evidence']==data['source']['evidence']
    assert result['conversation']==data['conversation']


def test_one_failed_pass_does_not_make_a_player_a_liability():
    from counterpress.analyst.live import check_comment
    s,d,_=setup()
    with pytest.raises(ValueError,match='unsupported_tactical_quality'):
        check_comment(d.model_copy(update={'text':'His touch has become a liability.'}),s,[],'control')


def test_large_old_memory_is_pruned_without_erasing_costs_or_active_scope(tmp_path):
    store=SQLiteStore(tmp_path/'bound.sqlite3');a=LiveAllowance(store)
    j=a.reserve('active',0,'match','active-scope',{'period':1,'elapsed_ms':1000})
    def fill(s):
        s['history']={f'old-{i}':[{'text':'x'*80000}] for i in range(18)}
        s['history']['active-scope']=[]
        return s,None
    store.transact(fill);a.finish('active',j['owner'],None,1)
    state=store.transact(lambda s:(s,s))
    assert len(json.dumps(state).encode())<=1_200_000
    assert state['spent_cents']==3 and state['matches']['match']==3
    assert 'active-scope' in state['history']


def test_progression_label_cannot_hide_the_same_sterile_takeaway():
    s,d,r=setup();m=conclusion(r,d,s,[])
    r.topic='territorial_progress';r.novelty='new_mechanism';r.prior_memory_id=m['id']
    d=d.model_copy(update={'text':'They have moved play forward but failed to threaten centrally.'})
    with pytest.raises(ValueError,match='repeated_conclusion'):conclusion(r,d,s,[{'memory':m}])


def test_a_real_shot_is_not_misclassified_as_harmless_circulation():
    s,d,r=setup('chance_creation');s['evidence'][0]['kind']='shot'
    d=d.model_copy(update={'text':'The passing produced a shot but limited end product as it was blocked.'})
    assert conclusion(r,d,s,[])['topic']=='chance_creation'
