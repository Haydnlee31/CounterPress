"""Request-owned model resources: real SDK/framework, fake network and credentials."""
import asyncio
import json

import httpx2
import pytest

from counterpress.assistant.multiagent import MultiAgentResearch
from counterpress.assistant.research import ResearchFailure
from counterpress.assistant.service import AssistantService
from counterpress.personalization.service import CareerService
from counterpress.personalization.store import DataStore
from test_assistant_multiagent import compound_request, fake_multi
from test_assistant_research import ROOT, CONFIG
from test_model_identity import FakeCredential, config


@pytest.fixture(scope='module')
def service():
    store=DataStore(ROOT/'fixtures/personalization')
    yield AssistantService(CareerService(store))
    store.close()


class TrackedPool(httpx2.AsyncBaseTransport):
    def __init__(self, inner, *, pause=False):
        self.inner=inner;self.close_count=0;self.calls=[];self.active=0;self.max_active=0
        self.queries=0;self.both_queries=asyncio.Event();self.pause=pause
        self.release=asyncio.Event();self.closed_while_active=False

    async def handle_async_request(self,request):
        assert self.close_count==0, 'A stage closed the request-owned pool early'
        payload=json.loads(request.content);self.calls.append((payload,dict(request.headers)))
        self.active+=1;self.max_active=max(self.max_active,self.active)
        try:
            if payload['response_format']['json_schema']['name']=='footie_query':
                self.queries+=1
                if self.queries==2:self.both_queries.set()
                await asyncio.wait_for(self.both_queries.wait(),2)
                if self.pause:await self.release.wait()
            return await self.inner.handle_async_request(request)
        finally:self.active-=1

    async def aclose(self):
        self.close_count+=1
        self.closed_while_active=bool(self.active)
        await self.inner.aclose()


def pooled_agent(service, *, fail_role=None, identity=False, pause=False):
    body=compound_request();old,_=fake_multi(service,body,fail_role=fail_role);pools=[]
    def factory():
        pool=TrackedPool(old.transport_factory(),pause=pause);pools.append(pool);return pool
    agent=MultiAgentResearch(config() if identity else CONFIG,factory)
    return agent,body,pools


def assert_timings_safe(timings):
    assert timings
    for row in timings:
        assert set(row)=={'stage','role','started_ms','duration_ms','status'}
        assert row['stage'] in {'initial','context','route','query','tool','followup','synthesize','auth','provider_http'}
        assert row['role'] in {'orchestrator','match','career'}
        assert row['status'] in {'ok','error','cancelled'}
        assert row['started_ms']>=0 and row['duration_ms']>=0


def test_compound_stages_reuse_one_pool_with_concurrent_isolated_schemas(service):
    agent,body,pools=pooled_agent(service)
    result=asyncio.run(agent.research(service,body,lambda:True))
    assert result.requests==4 and result.tools==2 and result.reported_requests==4
    assert result.usage['total_tokens']==60 and not result.partial_failures
    assert len(pools)==1 and pools[0].close_count==1 and not pools[0].closed_while_active
    assert pools[0].max_active==2 and len(pools[0].calls)==4
    for payload,headers in pools[0].calls:
        schema=payload['response_format']['json_schema']
        assert schema['strict'] is True and headers['api-key']=='fake'
        if schema['name']=='footie_query':
            data=json.loads(payload['messages'][-1]['content'])
            operations=schema['schema']['properties']['operation']['enum']
            if data['context']['selected']['cutoff']:assert 'match' in operations and 'stats' not in operations
            else:assert 'match' not in operations and set(operations)&{'stats','compare','seasons','recent','club_leaders'}
    assert_timings_safe(result.stage_timings)
    queries=[r for r in result.stage_timings if r['stage']=='query']
    assert len(queries)==2 and {r['role'] for r in queries}=={'match','career'}
    assert max(r['started_ms'] for r in queries)<min(r['started_ms']+r['duration_ms'] for r in queries)
    assert len([r for r in result.stage_timings if r['stage']=='provider_http'])==4


def test_managed_identity_credential_and_cached_token_reused_across_stages(service,monkeypatch):
    import azure.identity.aio
    credentials=[]
    def factory(**kwargs):
        credential=FakeCredential();credentials.append(credential);return credential
    monkeypatch.setattr(azure.identity.aio,'ManagedIdentityCredential',factory)
    agent,body,pools=pooled_agent(service,identity=True)
    result=asyncio.run(agent.research(service,body,lambda:True))
    assert len(credentials)==1 and len(credentials[0].calls)==1 and credentials[0].closed==1
    assert len(pools)==1 and pools[0].close_count==1
    assert all(h['authorization']=='Bearer fake-access-token-1' and 'api-key' not in h for _,h in pools[0].calls)
    assert len([r for r in result.stage_timings if r['stage']=='auth'])==4
    assert_timings_safe(result.stage_timings)


def test_concurrent_requests_have_separate_pools_credentials_and_budgets(service,monkeypatch):
    import azure.identity.aio
    credentials=[]
    def factory(**kwargs):
        credential=FakeCredential();credentials.append(credential);return credential
    monkeypatch.setattr(azure.identity.aio,'ManagedIdentityCredential',factory)
    agent,body,pools=pooled_agent(service,identity=True)
    async def run():return await asyncio.gather(*(agent.research(service,body,lambda:True) for _ in range(2)))
    results=asyncio.run(run())
    assert len(pools)==len(credentials)==2
    assert all(p.close_count==1 and len(p.calls)==4 and p.max_active==2 for p in pools)
    assert all(c.closed==1 and len(c.calls)==1 for c in credentials)
    assert all(r.requests==4 and r.tools==2 and r.usage['total_tokens']==60 for r in results)
    assert results[0].stage_timings is not results[1].stage_timings


def test_provider_error_does_not_close_pool_needed_by_other_specialist_and_story(service):
    agent,body,pools=pooled_agent(service,fail_role='career')
    result=asyncio.run(agent.research(service,body,lambda:True))
    assert result.partial_failures==('career:planning_failed',)
    assert result.requests==4 and result.tools==1
    assert pools[0].close_count==1 and len(pools[0].calls)==4
    assert any(t['stage']=='query' and t['role']=='career' and t['status']=='error' for t in result.stage_timings)
    assert any(t['stage']=='synthesize' and t['status']=='ok' for t in result.stage_timings)


def test_cancelling_request_waits_for_specialists_then_closes_resources_once(service,monkeypatch):
    import azure.identity.aio
    credentials=[]
    def factory(**kwargs):
        credential=FakeCredential();credentials.append(credential);return credential
    monkeypatch.setattr(azure.identity.aio,'ManagedIdentityCredential',factory)
    agent,body,pools=pooled_agent(service,identity=True,pause=True)
    async def run():
        task=asyncio.create_task(agent.research(service,body,lambda:True))
        while not pools:await asyncio.sleep(0)
        await asyncio.wait_for(pools[0].both_queries.wait(),3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
    asyncio.run(run())
    assert len(pools)==1 and pools[0].close_count==1 and pools[0].active==0
    assert not pools[0].closed_while_active and credentials[0].closed==1


def test_denied_budget_never_sends_http_and_closes_request_resources(service):
    agent,body,pools=pooled_agent(service)
    with pytest.raises(ResearchFailure) as error:asyncio.run(agent.research(service,body,lambda:False))
    assert error.value.requests==0 and not pools[0].calls and pools[0].close_count==1
    assert_timings_safe(error.value.stage_timings)


def test_identity_error_closes_resources_without_private_metadata(service,monkeypatch):
    import azure.identity.aio
    credential=FakeCredential(fail=True)
    monkeypatch.setattr(azure.identity.aio,'ManagedIdentityCredential',lambda **kwargs:credential)
    agent,body,pools=pooled_agent(service,identity=True)
    with pytest.raises(ResearchFailure) as error:asyncio.run(agent.research(service,body,lambda:True))
    assert not pools[0].calls and pools[0].close_count==1 and credential.closed==1
    assert 'do-not-expose' not in str(error.value)
    assert_timings_safe(error.value.stage_timings)
    assert any(t['stage']=='auth' and t['status']=='error' for t in error.value.stage_timings)


def test_pool_construction_failure_still_closes_owned_credential(service,monkeypatch):
    import azure.identity.aio
    credential=FakeCredential()
    monkeypatch.setattr(azure.identity.aio,'ManagedIdentityCredential',lambda **kwargs:credential)
    def broken_pool():raise RuntimeError('private-transport-address')
    agent=MultiAgentResearch(config(),broken_pool)
    with pytest.raises(ResearchFailure) as error:asyncio.run(agent.research(service,compound_request(),lambda:True))
    assert credential.closed==1 and error.value.requests==0
    assert 'private' not in str(error.value)



def test_shared_identity_still_refreshes_expiring_token(service,monkeypatch):
    import azure.identity.aio
    credential=FakeCredential(expire_first=True)
    monkeypatch.setattr(azure.identity.aio,'ManagedIdentityCredential',lambda **kwargs:credential)
    agent,body,pools=pooled_agent(service,identity=True)
    result=asyncio.run(agent.research(service,body,lambda:True))
    assert result.requests==4 and len(credential.calls)==2 and credential.closed==1
    headers=[h['authorization'] for _,h in pools[0].calls]
    assert headers[0]=='Bearer fake-access-token-1'
    assert headers[1:]==['Bearer fake-access-token-2']*3


def test_cancelling_response_body_closes_stream_but_not_borrowed_pool():
    from counterpress.assistant.multiagent import CallBudget,CompletionTransport,request_resources
    class PendingBody(httpx2.AsyncByteStream):
        def __init__(self):self.entered=asyncio.Event();self.closed=0
        async def __aiter__(self):
            yield b'{'
            self.entered.set();await asyncio.Event().wait()
        async def aclose(self):self.closed+=1
    class Pool(httpx2.AsyncBaseTransport):
        def __init__(self):self.body=PendingBody();self.closed=0
        async def handle_async_request(self,request):return httpx2.Response(200,stream=self.body)
        async def aclose(self):self.closed+=1
    async def run():
        pool=Pool();budget=CallBudget(lambda:True)
        async with request_resources(CONFIG,lambda:pool,budget):
            stage=CompletionTransport(pool,budget,'match',{'type':'object'},'footie_query',owns_inner=False)
            task=asyncio.create_task(stage.handle_async_request(httpx2.Request('POST',CONFIG.url,json={'messages':[]})))
            await pool.body.entered.wait();task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
            await stage.aclose()
            assert pool.closed==0 and pool.body.closed==1
        assert pool.closed==1 and budget.resources is None
        assert budget.requests=={'match':1}
        assert budget.stage_timings[0]['stage']=='provider_http' and budget.stage_timings[0]['status']=='cancelled'
    asyncio.run(run())


def test_unique_approved_story_uses_no_synthesis_call_and_reports_calculated(service):
    from counterpress.assistant.contracts import AskRequest
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from counterpress.assistant.api import install_assistant
    body=AskRequest(question='What is Mateo Cross’s pass accuracy?')
    agent,calls=fake_multi(service,body)
    result=asyncio.run(agent.research(service,body,lambda:True))
    assert result.requests==1 and result.tools==1 and result.selection_mode=='calculated'
    assert not result.partial_failures and len(calls)==1
    assert not any(t['stage']=='synthesize' for t in result.stage_timings)
    app=FastAPI();install_assistant(app,lambda:service.career,researcher=agent)
    with TestClient(app) as client:answer=client.post('/api/fan/assistant/ask',json=body.model_dump(by_alias=True)).json()
    assert answer['status']=='answered' and answer['facts'] and answer['narrative']['blocks']
    assert answer['mode']=='azure_agent' and answer['narrative']['mode']=='calculated'
    assert answer['narrative']['fallback_reason'] is None and not answer.get('research')
    assert len(calls)==2 and all(p['response_format']['json_schema']['name']=='footie_query' for p in calls)
    assert agent.max_requests==4 and agent.deadline_seconds==24


def test_multiple_approved_stories_still_use_model_selection(service):
    from counterpress.assistant.contracts import AskRequest
    body=AskRequest(question='How many goals does Mateo Cross have?')
    agent,calls=fake_multi(service,body)
    result=asyncio.run(agent.research(service,body,lambda:True))
    assert result.requests==2 and result.selection_mode=='agent_selected'
    assert [c['response_format']['json_schema']['name'] for c in calls]==['footie_query','footie_story']
    assert not result.partial_failures


@pytest.mark.parametrize('invalid_kind',['unknown_id','missing_required'])
def test_invalid_unique_story_cannot_skip_receipt_validation(service,monkeypatch,invalid_kind):
    from counterpress.assistant import multiagent
    from counterpress.assistant.narrative import StoryPlan
    from counterpress.assistant.contracts import AskRequest
    body=AskRequest.model_validate({'question':'Explain the buildup and the time from regaining possession to the goal.',
        'match_id':'career-showcase-southbank-redhaven','event_id':'e01178','event_revision':1,
        'cutoff':{'period':2,'elapsed_ms':1632996}})
    def invalid(claims,depth):
        assert any(c.get('required') for c in claims)
        lead='c9999' if invalid_kind=='unknown_id' else next(c['id'] for c in claims if not c.get('required'))
        return {'only':StoryPlan(lead=lead,supporting=[])}
    monkeypatch.setattr(multiagent,'story_candidates',invalid)
    agent,calls=fake_multi(service,body)
    with pytest.raises(ResearchFailure):asyncio.run(agent.research(service,body,lambda:True))
    assert len(calls)==1 and calls[0]['response_format']['json_schema']['name']=='footie_query'


def test_calculated_story_repeats_without_incompatible_shared_cache(service,tmp_path):
    from counterpress.assistant.admission import Admission,SQLiteAdmissionStore,SharedResearcher,Receipt
    from counterpress.assistant.contracts import AskRequest
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from counterpress.assistant.api import install_assistant
    body=AskRequest(question='What is Mateo Cross’s pass accuracy?')
    agent,calls=fake_multi(service,body)
    admission=Admission(SQLiteAdmissionStore(tmp_path/'story-mode.sqlite3'))
    shared=SharedResearcher(agent,admission,'unique-story-v1',lambda:100)
    app=FastAPI();install_assistant(app,lambda:service.career,researcher=shared)
    with TestClient(app) as client:
        first=client.post('/api/fan/assistant/ask',json=body.model_dump(by_alias=True)).json()
        cached=client.post('/api/fan/assistant/ask',json=body.model_dump(by_alias=True)).json()
    assert len(calls)==2
    for answer in (first,cached):
        assert answer['narrative']['mode']=='calculated' and answer['narrative']['fallback_reason'] is None
        assert answer['narrative']['blocks'] and answer['facts']
    state=admission.store.transact(lambda s:s)
    assert not state.jobs and state.weighted==((100,4),(100,4))
    result=asyncio.run(agent.research(service,body,lambda:True))
    receipt=Receipt(plan=result.plan,selection=result.selection,evidence_id=result.evidence_id,selection_mode='calculated')
    legacy=receipt.model_dump();legacy.pop('selection_mode')
    assert Receipt.model_validate(legacy).selection_mode=='agent_selected'
    with pytest.raises(ValueError):Receipt.model_validate({**legacy,'selection_mode':'private-untrusted-string'})
