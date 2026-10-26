import asyncio,json
import pytest
from counterpress.assistant import highlight_summary as module
from counterpress.adaptation.azure import ProviderFailure

EVIDENCE={'context':{'players':{'p':'Owen Cole'},'score_after':{'eastbridge':1,'northport':1}},'events':[{'event_id':'goal','player_id':'p','outcome':'goal'}]}
DRAFT={'paragraphs':[{'text':'Cole makes it all square with the finish.','evidence_ids':['goal','context']}]}

def test_prose_is_written_then_independently_reviewed(monkeypatch):
    calls=[];reserves=[]
    async def request(config,transport,prompt,data,schema,name,tokens,timeout):
        calls.append((name,data))
        return json.dumps(DRAFT if len(calls)==1 else {'supported':True,'issues':[]}),{'total_tokens':10}
    monkeypatch.setattr(module,'structured_request',request)
    result=asyncio.run(module.write_verified_summary(object(),EVIDENCE,lambda:reserves.append(True) or True))
    assert result['text']==['Cole makes it all square with the finish.']
    assert len(reserves)==2 and result['usage']['total_tokens']==20
    assert calls[1][1]=={'source':EVIDENCE,'candidate':DRAFT}
    assert result['mode']=='azure_generated_verified'

@pytest.mark.parametrize('review',[{'supported':False,'issues':['Wrong scorer']},{'supported':True,'issues':['Unsupported score']}])
def test_failed_review_never_returns_the_draft(monkeypatch,review):
    values=iter([DRAFT,review])
    async def request(*a,**k):return json.dumps(next(values)),{}
    monkeypatch.setattr(module,'structured_request',request)
    with pytest.raises(ValueError,match='factual review'):asyncio.run(module.write_verified_summary(object(),EVIDENCE))

def test_fabricated_citation_rejected_before_checker_call(monkeypatch):
    calls=[]
    async def request(*a,**k):
        calls.append(True)
        return json.dumps({'paragraphs':[{'text':'A goal.','evidence_ids':['invented']}]}),{}
    monkeypatch.setattr(module,'structured_request',request)
    with pytest.raises(ValueError,match='evidence'):asyncio.run(module.write_verified_summary(object(),EVIDENCE))
    assert len(calls)==1

def test_budget_is_checked_for_both_model_calls(monkeypatch):
    accepted=iter([True,False]);calls=[]
    async def request(*a,**k):calls.append(True);return json.dumps(DRAFT),{}
    monkeypatch.setattr(module,'structured_request',request)
    with pytest.raises(ProviderFailure,match='summary_limit'):asyncio.run(module.write_verified_summary(object(),EVIDENCE,lambda:next(accepted)))
    assert len(calls)==1

def test_direct_check_rejects_wrong_goal_number_even_before_model_review():
    packet={'context':{'score_after':{'eastbridge':3}},'events':[{'event_id':'g','actor':{'team_id':'eastbridge'},'action':{'outcome':'goal'}}]}
    draft=module.Draft.model_validate({'paragraphs':[{'text':'He scores their second goal.','evidence_ids':['g']}]})
    with pytest.raises(module.SummaryRejected):module.check_goal_ordinals(draft,packet)

def test_source_enrichment_does_not_confuse_attacking_and_own_thirds():
    packet={'context':{'players':{'p':'Owen Cole'},'clubs':{'eastbridge':'Eastbridge'}},'events':[{'event_id':'r','actor':{'team_id':'eastbridge','player_id':'p'},'position':{'x':85,'y':34},'action':{'kind':'recovery'}}]}
    enriched=module.enrich_evidence(packet)['events'][0]['calculated']
    assert enriched['start_third']=='attacking third'
    assert enriched['distance_to_goal_m']==20
    assert enriched['actor_name']=='Owen Cole'

def test_rejects_runs_inferred_from_unclassified_actions_and_wrong_own_goal_net():
    evidence={'context':{'clubs':{'eastbridge':'Eastbridge','northport':'Northport'}},'events':[{'event_id':'own','club_id':'northport','kind':'other','outcome':'own_goal','goal_for':'eastbridge','player_id':'p'}]}
    enriched=module.enrich_evidence(evidence)
    for text in ['Milo West advanced on the ball.','Sam sent the ball into Eastbridge’s goal.']:
        draft=module.Draft.model_validate({'paragraphs':[{'text':text,'evidence_ids':['own']}]})
        with pytest.raises(module.SummaryRejected):module.check_goal_ordinals(draft,enriched)
