"""No cloud credentials used: auth selection, refresh, transport and cleanup."""
import asyncio
import time
import pytest
import httpx2
from azure.core.credentials import AccessToken
from openai import AsyncOpenAI
from pydantic import SecretStr
from counterpress.adaptation.azure import AzureConfig, MODEL_TOKEN_SCOPE, ProviderFailure, load_config, model_auth

CLIENT_ID='00000000-0000-4000-8000-000000000001'


def config(**kwargs):
    return AzureConfig(endpoint='https://test.openai.azure.com',deployment='test-model',auth_mode='managed_identity',managed_identity_client_id=CLIENT_ID,**kwargs)


class FakeCredential:
    def __init__(self, *, expire_first=False, fail=False):
        self.closed=0;self.calls=[];self.expire_first=expire_first;self.fail=fail
    async def get_token(self,*scopes,**kwargs):
        self.calls.append(scopes)
        if self.fail:raise RuntimeError('do-not-expose-token-or-identity-endpoint')
        life=1 if self.expire_first and len(self.calls)==1 else 3600
        return AccessToken('fake-access-token-'+str(len(self.calls)),int(time.time())+life)
    async def close(self):self.closed+=1


def test_config_default_api_key_compatible_and_identity_explicit():
    values={'AZURE_OPENAI_ENDPOINT':'https://test.openai.azure.com','AZURE_OPENAI_DEPLOYMENT':'test','AZURE_OPENAI_API_KEY':'test-old-key'}
    default=load_config(values)
    assert default.auth_mode=='api_key' and default.api_key.get_secret_value()=='test-old-key'
    identity=load_config(values|{'AZURE_OPENAI_AUTH_MODE':'managed_identity','AZURE_OPENAI_MANAGED_IDENTITY_CLIENT_ID':CLIENT_ID})
    assert identity.auth_mode=='managed_identity' and identity.api_key is None
    assert identity.managed_identity_client_id==CLIENT_ID
    assert load_config({}) is None
    assert load_config({'AZURE_CLIENT_ID':CLIENT_ID}) is None
    with pytest.raises(ValueError):load_config(values|{'AZURE_OPENAI_AUTH_MODE':'auto'})
    with pytest.raises(ValueError):load_config({'AZURE_OPENAI_AUTH_MODE':'managed_identity'})
    with pytest.raises(ValueError):load_config(values|{'AZURE_OPENAI_AUTH_MODE':'managed_identity','AZURE_OPENAI_MANAGED_IDENTITY_CLIENT_ID':'private-invalid-id'})


def test_identity_alias_and_system_assigned_selection():
    values={'AZURE_OPENAI_ENDPOINT':'https://test.openai.azure.com','AZURE_OPENAI_DEPLOYMENT':'test','AZURE_OPENAI_AUTH_MODE':'managed_identity'}
    assert load_config(values).managed_identity_client_id is None
    assert load_config(values|{'AZURE_CLIENT_ID':CLIENT_ID}).managed_identity_client_id==CLIENT_ID


def test_invalid_config_and_copied_http_endpoint_never_acquire_token():
    calls=[]
    async def run():
        with pytest.raises(ProviderFailure,match='authentication_configuration_failed'):
            async with model_auth(config().model_copy(update={'endpoint':'http://private.invalid/?key=secret'}),credential_factory=lambda **kw:calls.append(kw)):
                raise AssertionError('Should not enter context')
    asyncio.run(run())
    assert calls==[]
    with pytest.raises(ValueError) as error:
        load_config({'AZURE_OPENAI_ENDPOINT':'http://private.invalid/?key=secret','AZURE_OPENAI_DEPLOYMENT':'private','AZURE_OPENAI_API_KEY':'private-secret'})
    assert 'private' not in str(error.value) and 'secret' not in str(error.value)


def test_api_key_path_does_not_open_identity_and_closes_context():
    async def run():
        def fail(**kwargs):raise AssertionError('No identity lookup for API key')
        api=AzureConfig(endpoint='https://test.openai.azure.com',deployment='test',api_key=SecretStr('test-key'))
        async with model_auth(api,credential_factory=fail) as auth:
            assert await auth.headers()=={'api-key':'test-key'}
            assert auth.sdk_kwargs()=={'api_key':'test-key','default_headers':{'api-key':'test-key'}}
        with pytest.raises(ProviderFailure,match='authentication_unavailable'):await auth.headers()
    asyncio.run(run())


def test_token_cache_scope_and_cleanup():
    credential=FakeCredential();factory_calls=[]
    def factory(**kwargs):factory_calls.append(kwargs);return credential
    async def run():
        async with model_auth(config(),credential_factory=factory) as auth:
            assert await auth.headers()=={'Authorization':'Bearer fake-access-token-1'}
            assert await auth.headers()=={'Authorization':'Bearer fake-access-token-1'}
            assert 'api-key' not in auth.sdk_kwargs()['default_headers']
        assert credential.closed==1
    asyncio.run(run())
    assert credential.calls==[(MODEL_TOKEN_SCOPE,)]
    assert MODEL_TOKEN_SCOPE=='https://ai.azure.com/.default'
    assert factory_calls[0]['client_id']==CLIENT_ID and factory_calls[0]['retry_total']==0


def test_refreshable_sdk_token_provider_reaches_actual_transport():
    credential=FakeCredential(expire_first=True);requests=[]
    async def run():
        def handle(request):
            requests.append(request)
            return httpx2.Response(200,json={'id':'x','object':'chat.completion','created':1,'model':'test',
                'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':'ok'}}]})
        async with model_auth(config(),credential_factory=lambda **kw:credential) as auth:
            async with AsyncOpenAI(**auth.sdk_kwargs(),base_url=config().url.removesuffix('chat/completions'),
                    max_retries=0,http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle),follow_redirects=False)) as sdk:
                for _ in range(2):await sdk.chat.completions.create(model='test',messages=[{'role':'user','content':'test'}])
    asyncio.run(run())
    assert len(requests)==2 and len(credential.calls)==2
    assert [r.headers['authorization'] for r in requests]==['Bearer fake-access-token-1','Bearer fake-access-token-2']
    assert all('api-key' not in r.headers for r in requests)
    assert credential.closed==1


def test_identity_failure_never_falls_back_to_key_and_sanitizes_exception():
    credential=FakeCredential(fail=True)
    async def run():
        async with model_auth(config(api_key=SecretStr('unused-key')),credential_factory=lambda **kw:credential) as auth:
            with pytest.raises(ProviderFailure) as error:await auth.headers()
            assert str(error.value)=='authentication_failed'
            assert error.value.__suppress_context__
    asyncio.run(run())
    assert credential.closed==1 and len(credential.calls)==1


def test_cancelled_token_request_closes_credential():
    class Pending(FakeCredential):
        async def get_token(self,*scopes,**kwargs):
            self.entered.set();await asyncio.Event().wait()
    credential=Pending()
    async def run():
        credential.entered=asyncio.Event()
        async def call():
            async with model_auth(config(),credential_factory=lambda **kw:credential) as auth:await auth.headers()
        task=asyncio.create_task(call());await credential.entered.wait();task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
    asyncio.run(run())
    assert credential.closed==1


def test_header_injection_token_is_rejected_and_close_failure_not_leaked():
    class Broken(FakeCredential):
        async def get_token(self,*scopes,**kwargs):return AccessToken('bad\r\nprivate-value',int(time.time())+3600)
        async def close(self):self.closed+=1;raise RuntimeError('private-cleanup-detail')
    credential=Broken()
    async def run():
        with pytest.raises(ProviderFailure,match='authentication_failed'):
            async with model_auth(config(),credential_factory=lambda **kw:credential) as auth:await auth.headers()
    asyncio.run(run())
    assert credential.closed==1


def test_legacy_draft_adapter_uses_bearer_without_api_key(monkeypatch):
    import httpx
    import json
    import azure.identity.aio
    from counterpress.adaptation.azure import AzureDraftProvider
    from test_adaptation import snapshots, adapt
    credential=FakeCredential();requests=[]
    monkeypatch.setattr(azure.identity.aio,'ManagedIdentityCredential',lambda **kw:credential)
    def handle(request):
        requests.append(request)
        facts=json.loads(json.loads(request.content)['messages'][1]['content'])['required_facts']
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(facts|{'template':'count_first'})}}]})
    result=adapt(snapshots(),AzureDraftProvider(config(),httpx.MockTransport(handle)))
    assert result.status=='accepted'
    assert len(requests)==1 and requests[0].headers['authorization']=='Bearer fake-access-token-1'
    assert 'api-key' not in requests[0].headers and credential.closed==1


@pytest.mark.parametrize('workflow',['comparison','recap','single_editor'])
def test_legacy_workflow_authentication_and_cleanup_on_provider_error(monkeypatch,workflow):
    import azure.identity.aio
    from counterpress.workflow.service import WorkflowService
    from counterpress.workflow.recap_service import RecapWorkflowService
    from counterpress.workflow.single_editor import SingleEditorService
    from test_workflow import snapshots
    credential=FakeCredential();requests=[]
    monkeypatch.setattr(azure.identity.aio,'ManagedIdentityCredential',lambda **kw:credential)
    def handle(request):
        requests.append(request)
        return httpx2.Response(503,json={'error':{'message':'unavailable'}})
    cls={'comparison':WorkflowService,'recap':RecapWorkflowService,'single_editor':SingleEditorService}[workflow]
    service=cls(snapshots(),config(),transport_factory=lambda:httpx2.MockTransport(handle))
    result=asyncio.run(service.run('increase' if workflow=='comparison' else 'pressure-increase',780000))
    assert result.status!='accepted'
    assert requests and all(r.headers['authorization']=='Bearer fake-access-token-1' and 'api-key' not in r.headers for r in requests)
    assert credential.closed==1
