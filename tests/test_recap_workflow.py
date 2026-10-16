import asyncio
import json
from pathlib import Path
import sqlite3

import httpx2
import pytest

from counterpress.api.snapshots import SnapshotService
from counterpress.audience import ViewingPreferences
from counterpress.history import SQLiteHistoryStore
from counterpress.recap_adaptation import fingerprint
from counterpress.workflow.recap_service import RecapWorkflowService
from test_workflow import CONFIG, completion, content
from test_recaps import corrections

ROOT = Path(__file__).resolve().parents[1]


def snapshots(db=':memory:'):
    return SnapshotService(ROOT/'fixtures', SQLiteHistoryStore(db))


class Script:
    def __init__(self, decision='accept', mutate_decision=None, mutate_draft=None, tools=None):
        self.requests = []
        self.decision = decision
        self.mutate_decision, self.mutate_draft = mutate_decision, mutate_draft
        self.tools = tools if tools is not None else ('get_recap_evidence','get_recap_limits')

    def __call__(self, request):
        body = json.loads(request.content)
        self.requests.append(body)
        messages = body['messages']
        if body['response_format']['json_schema']['name'] == 'RecapDraft':
            p = json.loads(content(messages[-1]))
            draft = {'fingerprint': p['fingerprint'], 'language': p['language'], 'heading': 'key_changes',
                     'stories': [s | {'template':'brief'} for s in p['stories']]}
            if self.mutate_draft: self.mutate_draft(draft)
            return completion(draft)
        results = [json.loads(content(m)) for m in messages if m['role']=='tool']
        if not results: return completion(names=self.tools)
        source = next((r for r in results if 'stories' in r), {'fingerprint':'wrong','stories':[]})
        selected = source['stories'] if self.decision=='accept' else source['stories'][:1] if self.decision=='narrow' else []
        decision = {'fingerprint': source['fingerprint'], 'decision': self.decision, 'stories': selected,
                    'reason': {'accept':'supported_comparisons','narrow':'focused_subset','reject':'insufficient_evidence'}[self.decision]}
        if self.mutate_decision: self.mutate_decision(decision)
        return completion(decision)


def runner(app, handler, **kwargs):
    return RecapWorkflowService(app, CONFIG, transport_factory=lambda: httpx2.MockTransport(handler), **kwargs)


def run(app, script, scenario='pressure-increase', prefs=None, **kwargs):
    return asyncio.run(runner(app,script,**kwargs).run(scenario,780000,prefs))


@pytest.mark.parametrize('language',['en','zh-Hans'])
@pytest.mark.parametrize('decision,expected_count',[('accept',2),('narrow',1)])
def test_framework_adapts_only_approved_wording_and_preserves_citations(tmp_path,language,decision,expected_count):
    db=tmp_path/'recap.sqlite3'; app=snapshots(db); script=Script(decision)
    prefs=ViewingPreferences(language=language,metric_focus='pressure_exposure')
    before=app.snapshot('pressure-increase',780000,preferences=prefs)
    result=run(app,script,prefs=prefs)
    assert result.status == ('accepted' if decision=='accept' else 'narrowed')
    assert (result.provider_requests,result.analyst_requests,result.producer_requests,result.tool_invocations)==(3,2,1,2)
    assert result.draft.language==language and len(result.draft.stories)==expected_count
    restarted=SnapshotService(tmp_path/'missing',SQLiteHistoryStore(db))
    after=restarted.snapshot('pressure-increase',780000,preferences=prefs)
    assert after.recap == before.recap  # factual fallback is always present
    assert after.recap_workflow.applied and len(after.adapted_recap.statements)==expected_count
    assert after.adapted_recap.omitted_count == 2-expected_count
    for item in after.adapted_recap.statements:
        assert item.citation in [s.citation for s in before.recap.statements]
        assert item.narrative.language==language
        assert '3/6' in item.narrative.explanation or '3/3' in item.narrative.explanation
        assert 'Only episodes' not in item.narrative.explanation and '仅统计' not in item.narrative.explanation
        assert item.narrative.qualification
    assert restarted.history('pressure-increase').recap_workflows == (result,)
    handoff=script.requests[-1]['messages']
    assert [m['role'] for m in handoff]==['system','user']
    assert 'decision' not in json.loads(content(handoff[-1]))
    assert 'approved_wording' in json.loads(content(handoff[-1]))
    assert all('get_recap_evidence' not in content(m) for m in handoff)


def test_rejection_skips_producer_and_keeps_factual_recap():
    app=snapshots(); result=run(app,Script('reject'))
    assert result.status=='rejected' and result.producer_requests==0 and result.draft is None
    response=app.snapshot('pressure-increase',780000)
    assert response.adapted_recap is None and len(response.recap.statements)==2


@pytest.mark.parametrize('mutation',[
    lambda d:d.update(fingerprint='wrong'),
    lambda d:d['stories'][0].update(revision=999),
    lambda d:d['stories'][0].update(evidence_id='wrong'),
    lambda d:d['stories'].append(d['stories'][0]),
    lambda d:d.update(stories=[]),
    lambda d:d.update(reason='insufficient_evidence'),
])
def test_invalid_analyst_decision_cannot_reach_producer(mutation):
    app=snapshots(); result=run(app,Script(mutate_decision=mutation))
    assert result.status=='invalid' and result.producer_requests==0 and result.draft is None


@pytest.mark.parametrize('mutation',[
    lambda d:d.update(fingerprint='wrong'),
    lambda d:d.update(language='zh-Hans'),
    lambda d:d['stories'][0].update(revision=999),
    lambda d:d['stories'][0].update(template='invented'),
    lambda d:d['stories'].reverse(),
    lambda d:d['stories'].pop(),
    lambda d:d.update(prose='Unsupported tactical claim'),
])
def test_invalid_producer_cannot_change_recap(mutation):
    app=snapshots(); result=run(app,Script(mutate_draft=mutation))
    assert result.status=='invalid' and result.draft is None
    assert app.snapshot('pressure-increase',780000).adapted_recap is None


def test_missing_required_tools_and_tool_budget_are_enforced():
    app=snapshots()
    missing=run(app,Script(tools=('get_recap_evidence',)))
    assert missing.status=='invalid' and missing.producer_requests==0
    excess=run(app,Script(tools=('get_recap_evidence','get_recap_limits','get_recap_evidence','get_recap_limits')))
    assert excess.status=='budget_exhausted' and excess.tool_invocations==3 and excess.producer_requests==0


@pytest.mark.parametrize('scenario,at,prefs,status',[
    ('pressure-control',780000,ViewingPreferences(),'ineligible'),
    ('pressure-increase',779999,ViewingPreferences(),'ineligible'),
    ('pressure-increase',780000,ViewingPreferences(card_budget=0),'ineligible'),
    ('contribution-increase',780000,ViewingPreferences(player_id='eb09'),'ineligible'),
])
def test_ineligible_requests_do_not_call_provider(scenario,at,prefs,status):
    app=snapshots(); script=Script()
    attempt=asyncio.run(runner(app,script).run(scenario,at,prefs))
    assert attempt.status==status and not script.requests and attempt.provider_requests==0


def test_unconfigured_and_historical_requests_skip_provider():
    app=snapshots()
    assert asyncio.run(RecapWorkflowService(app,None).run('pressure-increase',780000)).status=='unconfigured'
    app.ingest('pressure-increase',corrections('pressure/replay_corrections.json'))
    script=Script(); attempt=run(app,script)
    assert attempt.status=='stale' and attempt.reason=='historical_recap' and not script.requests


@pytest.mark.parametrize('pause_at,reason',[(2,'evidence_changed_before_handoff'),(3,'evidence_changed_before_commit')])
def test_concurrent_source_correction_discards_pending_recap(tmp_path,pause_at,reason):
    db=tmp_path/'recap.sqlite3'; app=snapshots(db); script=Script()
    async def check():
        entered,release=asyncio.Event(),asyncio.Event()
        async def pending(request):
            if len(script.requests)+1==pause_at:
                entered.set(); await release.wait()
            return script(request)
        task=asyncio.create_task(runner(app,pending).run('pressure-increase',780000))
        await asyncio.wait_for(entered.wait(),3)
        other=snapshots(db)
        assert other.snapshot('pressure-increase',540000).recap.state=='collecting'
        other.ingest('pressure-increase',corrections('pressure/replay_corrections.json'))
        release.set()
        result=await task
        assert result.status=='stale' and result.reason==reason and result.draft is None
        assert other.snapshot('pressure-increase',795000).adapted_recap is None
    asyncio.run(check())


def test_expiry_viewpoint_and_source_changes_invalidate_presentation(monkeypatch):
    app=snapshots(); result=run(app,Script('narrow'))
    before=app.snapshot('pressure-increase',780000)
    assert before.adapted_recap is not None
    assert app.snapshot('pressure-increase',780000,preferences=ViewingPreferences(language='zh-Hans')).recap_workflow is None
    assert app.snapshot('pressure-increase',779999).recap_workflow is None
    monkeypatch.setattr('counterpress.api.snapshots.time',lambda: result.expires_at_unix_ms/1000)
    expired=app.snapshot('pressure-increase',780000)
    assert expired.adapted_recap is None and expired.recap_workflow.status=='expired' and expired.recap==before.recap
    app.ingest('pressure-increase',corrections('pressure/replay_corrections.json'))
    stale=app.snapshot('pressure-increase',795000)
    assert stale.adapted_recap is None and stale.recap_workflow.status=='stale'


def test_pending_provider_is_cancelled_at_deadline():
    app=snapshots(); app.snapshot('pressure-increase',780000); cancelled=[]
    async def pending(request):
        try: await asyncio.Event().wait()
        finally: cancelled.append(True)
    result=run(app,pending,timeout_seconds=0.5)
    assert result.status=='timeout' and result.provider_requests==1 and cancelled==[True]
    assert result.draft is None and app.snapshot('pressure-increase',780000).recap.state=='ready'


@pytest.mark.parametrize('response,status',[
    (httpx2.Response(503,text='private endpoint diagnostics'),'provider_error'),
    (httpx2.Response(200,json={'choices':[{'message':{'refusal':'no'},'finish_reason':'stop'}]}),'refused'),
    (httpx2.Response(200,text='x'*65537),'invalid'),
])
def test_provider_failures_are_sanitized(response,status):
    app=snapshots(); result=run(app,lambda request:response)
    assert result.status==status and result.draft is None
    assert 'private endpoint' not in result.model_dump_json() and 'test-deployment' not in result.model_dump_json()


def test_audit_append_only_and_additive_migration(tmp_path):
    db=tmp_path/'recap.sqlite3'; app=snapshots(db)
    history=app.history('pressure-increase')
    with sqlite3.connect(db) as c: c.execute('DROP TABLE recap_workflows')
    assert snapshots(db).history('pressure-increase')==history
    attempt=run(app,Script())
    with pytest.raises(ValueError,match='cannot be rewritten'):
        app.store.transact('pressure-increase',lambda h:h.model_copy(update={'recap_workflows':()}))
    assert app.history('pressure-increase').recap_workflows==(attempt,)


def test_fingerprint_covers_score_preferences_and_evidence():
    s=snapshots().snapshot('pressure-increase',780000)
    original=fingerprint(s.recap,s.state.score,s.history_version)
    assert fingerprint(s.recap,{'eastbridge':1,'northport':1},s.history_version)!=original
    assert fingerprint(s.recap,s.state.score,s.history_version+1)!=original


def test_expired_result_cannot_commit():
    app=snapshots(); ticks=iter([1000,61000])
    result=run(app,Script(),now=lambda:next(ticks))
    assert result.status=='expired' and result.reason=='expired_before_commit' and result.draft is None


def test_recap_command_does_not_print_configuration(tmp_path,monkeypatch,capsys):
    from counterpress.workflow.recap import main
    import sys
    for key in ('AZURE_OPENAI_ENDPOINT','AZURE_OPENAI_DEPLOYMENT','AZURE_OPENAI_API_KEY'):
        monkeypatch.delenv(key,raising=False)
    monkeypatch.setattr(sys,'argv',['recap','pressure-increase','--db',str(tmp_path/'command.sqlite3')])
    with pytest.raises(SystemExit) as exc: main()
    assert exc.value.code==2
    output=json.loads(capsys.readouterr().out)
    assert output['status']=='unconfigured' and output['provider_requests']==0
    assert not {'deployment','endpoint','api_key'} & output.keys()
