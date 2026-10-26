"""No-network publication controls, graders and real SDK wire serialization."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('foundry_publisher',ROOT/'scripts/publish_intelligence_foundry.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


@pytest.fixture
def exported(tmp_path):
    corpus_path=tmp_path/'fixtures/assistant/intelligence_questions.json';corpus_path.parent.mkdir(parents=True)
    source=tmp_path/'backend/source.py';source.parent.mkdir();source.write_text('stable = True\n')
    cases=[];results=[]
    for i,value in enumerate((2,1)):
        case_id=f'case{i}'
        expect={'status':'answered','anchors':[{'subject_id':'p1','metric':'passes','value':2}],
                'required_subject':'p1','evidence_event_ids':['e1'], 'max_event':{'period':1,'elapsed_ms':2000}}
        cases.append({'id':case_id,'bucket':'supported','journey':'buildup','request':{'question':f'Explain synthetic goal {i}.','match_id':'m1'},'expect':expect})
        results.append({'id':case_id,'bucket':'supported','journey':'buildup','question':cases[-1]['request']['question'],
            'passed':value==2,'checks':{'anchor':value==2},'status':'answered','mode':'azure_agent','text':[f'Recorded passes: {value}.'],
            'facts':[{'subject_kind':'player','subject_id':'p1','metric':'passes','value':value,'unit':'count','scope':{'match_id':'m1'},
                      'evidence':{'events':[{'event_id':'e1','match_id':'m1','period':1,'elapsed_ms':1000,'available_period':1,'available_ms':1500}]}}]})
    corpus_path.write_text(json.dumps({'version':'reviewed-synthetic-v1','cases':cases}))
    report={'version':1,'label':'regression','mode':'azure_multiagent','evaluation_status':'failed','sources_changed_during_run':[],
            'corpus_sha256':m.file_hash(corpus_path),'source_sha256':{str(corpus_path):m.file_hash(corpus_path),str(source):m.file_hash(source)},'results':results}
    report_path=tmp_path/'report.json';report_path.write_text(json.dumps(report))
    directory=tmp_path/'export';m.exporter.export_report(report_path,corpus_path,directory,root=tmp_path)
    return SimpleNamespace(root=tmp_path,corpus=corpus_path,report=report_path,directory=directory,source=source)


def planned(e, status='current'):
    return m.plan(e.directory,e.report,m.file_hash(e.directory/'manifest.json'),status,'release-test',root=e.root)


def rewrite(e,change):
    value=json.loads(e.report.read_text());change(value);e.report.write_text(json.dumps(value))
    fresh=e.root/('export-'+str(len(list(e.root.glob('export*')))))
    m.exporter.export_report(e.report,e.corpus,fresh,root=e.root);e.directory=fresh


def test_scores_are_independent_and_failures_keep_their_denominator(exported):
    plan,rows=planned(exported)
    assert plan['scores']=={'local_contract_pass':{'passed':1.,'total':2},'recorded_fact_assertions':{'passed':1.,'total':2}}
    assert plan['original_label']=='regression' and len(rows)==2
    # Even if a reported pass is incorrectly asserted, numeric anchors independently fail.
    bad=deepcopy(rows[1]);bad['local_pass']=True;bad['local_checks']={'reported':True}
    assert m.grade_locally(m.LOCAL_GRADER,bad)==1
    assert m.grade_locally(m.FACT_GRADER,bad)==0


@pytest.mark.parametrize('mutation',[
    lambda c:c['validated_facts'][0].update(value=True),
    lambda c:c['validated_facts'][0].update(value=999),
    lambda c:c['validated_facts'][0].update(subject_id='other'),
    lambda c:c.update(answer_status='clarify'),
    lambda c:c['evidence_by_fingerprint'].clear(),
    lambda c:next(iter(c['evidence_by_fingerprint'].values()))['events'][0].update(available_ms=3000),
    lambda c:next(iter(c['evidence_by_fingerprint'].values()))['events'][0].update(elapsed_ms=3000),
])
def test_independent_grader_rejects_wrong_facts_scope_and_future_data(exported,mutation):
    _,rows=planned(exported);row=deepcopy(rows[0]);context=json.loads(row['context']);mutation(context);row['context']=json.dumps(context)
    assert m.grade_locally(m.FACT_GRADER,row)==0


def test_presence_only_anchors_and_unsupported_empty_facts_have_defined_semantics(exported):
    _,rows=planned(exported);row=rows[0];expect=json.loads(row['ground_truth']);expect['anchors'][0].pop('value');row['ground_truth']=json.dumps(expect)
    assert m.grade_locally(m.FACT_GRADER,row)==1
    row['context']=json.dumps({'answer_status':'unsupported','validated_facts':[]});row['ground_truth']=json.dumps({'status':'unsupported','no_facts':True})
    assert m.grade_locally(m.FACT_GRADER,row)==1
    row['context']=json.dumps({'answer_status':'unsupported','validated_facts':[{'metric':'invented'}]})
    assert m.grade_locally(m.FACT_GRADER,row)==0


def test_missing_response_is_not_fabricated_or_dropped(exported):
    rewrite(exported,lambda report:report['results'][1].pop('text'))
    plan,rows=planned(exported)
    assert plan['missing_responses']==1 and plan['rows']==2
    assert rows[1]['response']=='' and rows[1]['response_recorded'] is False
    assert m.grade_locally(m.LOCAL_GRADER,rows[1])==m.grade_locally(m.FACT_GRADER,rows[1])==0


def test_reviewed_export_bytes_and_manifest_cannot_be_rewritten(exported):
    original=m.file_hash(exported.directory/'manifest.json')
    p=exported.directory/'evaluation.jsonl';p.write_text(p.read_text().replace('Recorded passes','Forged passes'))
    with pytest.raises(m.PublicationError,match='export_does_not_match_bound_report'):
        m.plan(exported.directory,exported.report,original,'historical','release-test',root=exported.root)
    p=exported.directory/'manifest.json';p.write_text(p.read_text()+' ')
    with pytest.raises(m.PublicationError,match='reviewed_manifest_changed'):
        m.plan(exported.directory,exported.report,original,'historical','release-test',root=exported.root)


def test_historical_sources_are_honestly_labelled_not_certified_current(exported):
    exported.source.write_text('changed = True\n')
    with pytest.raises(m.PublicationError,match='current_source_hash_mismatch'):planned(exported)
    plan,_=planned(exported,'historical')
    assert plan['historical_changed_source_count']==1 and plan['source_status']=='historical'


def test_more_than_64_rows_fails_before_cloud(exported):
    corpus=json.loads(exported.corpus.read_text());report=json.loads(exported.report.read_text())
    for i in range(2,65):
        c=deepcopy(corpus['cases'][0]);c['id']=f'case{i}';corpus['cases'].append(c)
        r=deepcopy(report['results'][0]);r['id']=c['id'];report['results'].append(r)
    exported.corpus.write_text(json.dumps(corpus));report['corpus_sha256']=m.file_hash(exported.corpus);report['source_sha256'][str(exported.corpus)]=m.file_hash(exported.corpus)
    exported.report.write_text(json.dumps(report));fresh=exported.root/'too-many';m.exporter.export_report(exported.report,exported.corpus,fresh,root=exported.root)
    with pytest.raises(m.PublicationError,match='row_limit_exceeded'):
        m.plan(fresh,exported.report,m.file_hash(fresh/'manifest.json'),'historical','release-test',root=exported.root)


def config(path):
    endpoint='https://counterpress-dev-01.services.ai.azure.com/api/projects/CounterPress'
    value={'project_endpoint':endpoint,'project_resource_sha256':'a'*64,'endpoint_sha256':m.sha256(endpoint.encode()).hexdigest(),
           'project_name':'CounterPress','account_name':'counterpress-dev-01','resource_group':'counterpress-dev'}
    m.private_json(path,value);return value


def test_project_is_private_exact_and_review_bound(tmp_path):
    p=tmp_path/'project.json';value=config(p)
    assert m.project_binding(p,m.digest(value))==value
    with pytest.raises(m.PublicationError,match='reviewed_project_binding_mismatch'):m.project_binding(p,'0'*64)
    p.chmod(0o644)
    with pytest.raises(m.PublicationError,match='project_config_not_private'):m.project_binding(p,m.digest(value))
    p.chmod(0o600);value['project_name']='other';p.write_text(json.dumps(value))
    with pytest.raises(m.PublicationError,match='project_not_existing_footie'):m.project_binding(p,m.digest(value))


class FakeClient:
    def __init__(self,rows,*,fail=None,pending=False,mutate=None):
        self.rows=rows;self.fail=fail;self.pending=pending;self.mutate=mutate;self.calls=[]
        self.evals=SimpleNamespace(create=self.create_eval,runs=SimpleNamespace(create=self.create_run,retrieve=self.retrieve,output_items=SimpleNamespace(list=self.outputs)))
    def create_eval(self,**payload):
        self.calls.append(('eval',payload))
        if self.fail=='eval':raise RuntimeError('PRIVATE TOKEN https://private.invalid')
        return {'id':'eval_test'}
    def create_run(self,**payload):
        self.calls.append(('run',payload))
        if self.fail=='run':raise RuntimeError('PRIVATE TOKEN https://private.invalid')
        return {'id':'evalrun_test'}
    def retrieve(self,**_):
        self.calls.append(('read',{}))
        result={'status':'in_progress' if self.pending else 'completed','result_counts':{'total':len(self.rows),'errored':0,
                  'passed':sum(all(m.grade_locally(source,row)==1 for source in (m.LOCAL_GRADER,m.FACT_GRADER)) for row in self.rows),
                  'failed':sum(not all(m.grade_locally(source,row)==1 for source in (m.LOCAL_GRADER,m.FACT_GRADER)) for row in self.rows)},'per_model_usage':[]}
        if self.fail=='model':result['per_model_usage']=[{'invocation_count':1,'total_tokens':1}]
        return result
    def outputs(self,**_):
        self.calls.append(('outputs',{}));outputs=[]
        for index,row in enumerate(self.rows):
            output={'datasource_item_id':index,'datasource_item':deepcopy(row),'status':'completed','sample':None,
                    'results':[{'name':name,'score':m.grade_locally(source,row),'passed':m.grade_locally(source,row)==1}
                               for name,source in (('local_contract_pass',m.LOCAL_GRADER),('recorded_fact_assertions',m.FACT_GRADER))]}
            if self.mutate:self.mutate(output)
            outputs.append(output)
        return outputs


def test_successful_publication_is_idempotent_and_receipts_are_private(exported):
    plan,rows=planned(exported);client=FakeClient(rows);directory=exported.root/'receipts'
    first=m.publish(plan,rows,'a'*64,client,receipt_directory=directory,poll_seconds=0)
    assert first['status']=='verified' and len(client.calls)==4
    assert m.publish(plan,rows,'a'*64,client,receipt_directory=directory,poll_seconds=0)==first
    assert len(client.calls)==4
    receipt=next(directory.glob('*.json'));text=receipt.read_text()
    assert receipt.stat().st_mode & 0o777==0o600 and directory.stat().st_mode & 0o777==0o700
    assert 'https://' not in text and 'PRIVATE' not in text
    assert json.loads(text)['row_scores'][1]['local_contract_pass']==0


@pytest.mark.parametrize('failed_stage',['eval','run'])
def test_uncertain_mutation_never_retries_or_resubmits(exported,failed_stage):
    plan,rows=planned(exported);client=FakeClient(rows,fail=failed_stage);directory=exported.root/'receipts'
    with pytest.raises(m.PublicationError,match='uncertain_manual_reconciliation_required') as error:
        m.publish(plan,rows,'a'*64,client,receipt_directory=directory,poll_seconds=0)
    assert 'PRIVATE' not in str(error.value)
    before=len(client.calls)
    with pytest.raises(m.PublicationError,match='uncertain_submission_manual_reconciliation_required'):
        m.publish(plan,rows,'a'*64,client,receipt_directory=directory,poll_seconds=0)
    assert len(client.calls)==before


def test_resume_pending_run_only_reads(exported):
    plan,rows=planned(exported);client=FakeClient(rows,pending=True);directory=exported.root/'receipts'
    assert m.publish(plan,rows,'a'*64,client,receipt_directory=directory,poll_seconds=0)['status']=='pending'
    client.pending=False
    assert m.publish(plan,rows,'a'*64,client,receipt_directory=directory,poll_seconds=0)['status']=='verified'
    assert [kind for kind,_ in client.calls].count('eval')==[kind for kind,_ in client.calls].count('run')==1


@pytest.mark.parametrize('mutate',[
    lambda o:o['results'][0].update(score=0.7),
    lambda o:o['datasource_item'].update(response='substituted'),
    lambda o:o.update(status='error'),
    lambda o:o['results'].append(dict(o['results'][0])),
])
def test_remote_wrong_score_or_substituted_input_cannot_be_verified(exported,mutate):
    plan,rows=planned(exported);client=FakeClient(rows,mutate=mutate)
    with pytest.raises(m.PublicationError):m.publish(plan,rows,'a'*64,client,receipt_directory=exported.root/'receipts',poll_seconds=0)
    receipt=json.loads(next((exported.root/'receipts').glob('*.json')).read_text());assert receipt['stage']=='run_created'


def test_unexpected_remote_model_usage_cannot_be_certified(exported):
    plan,rows=planned(exported)
    with pytest.raises(m.PublicationError,match='unexpected_remote_model_usage'):
        m.publish(plan,rows,'a'*64,FakeClient(rows,fail='model'),receipt_directory=exported.root/'receipts',poll_seconds=0)
    assert json.loads(next((exported.root/'receipts').glob('*.json')).read_text())['stage']=='run_created'


def test_real_foundry_sdk_serializes_only_python_graders_and_inline_precomputed_rows(exported):
    projects=pytest.importorskip('azure.ai.projects')
    import httpx
    from azure.core.credentials import AccessToken
    plan,rows=planned(exported);seen=[];fake=FakeClient(rows)
    class Credential:
        def get_token(self,*scopes,**kwargs):
            assert scopes==('https://ai.azure.com/.default',)
            return AccessToken('offline-test-token',9999999999)
    def handler(request):
        path=request.url.path;seen.append((request.method,path,json.loads(request.content) if request.content else None))
        if request.method=='POST' and path.endswith('/evals'):
            payload=seen[-1][2]
            assert payload['data_source_config']['include_sample_schema'] is False
            assert {g['type'] for g in payload['testing_criteria']}=={'python'}
            assert all(g['pass_threshold']==.5 for g in payload['testing_criteria'])
            return httpx.Response(200,json={'id':'eval_test'})
        if request.method=='POST' and path.endswith('/runs'):
            payload=seen[-1][2];assert payload['data_source']=={'type':'jsonl','source':{'type':'file_content','content':[{'item':row} for row in rows]}}
            return httpx.Response(200,json={'id':'evalrun_test'})
        if path.endswith('/output_items'):return httpx.Response(200,json={'object':'list','data':fake.outputs(),'has_more':False,'first_id':None,'last_id':None})
        return httpx.Response(200,json=fake.retrieve())
    with projects.AIProjectClient(endpoint='https://counterpress-dev-01.services.ai.azure.com/api/projects/CounterPress',credential=Credential(),retry_total=0) as project:
        with project.get_openai_client(http_client=httpx.Client(transport=httpx.MockTransport(handler)),max_retries=0,timeout=2) as client:
            result=m.publish(plan,rows,'a'*64,client,receipt_directory=exported.root/'receipts',poll_seconds=0)
    assert result['status']=='verified' and len(seen)==4
    assert all('/evals' in path for _,path,_ in seen)


def test_actual_flattened_output_envelope_preserves_exact_rows(exported):
    def wrap(output):
        row=output['datasource_item']
        output['datasource_item']={'item':row,**{'item.'+k:v for k,v in row.items()},
            'item.local_checks.anchor':row['local_checks']['anchor'],
            'item.local_checks.absent_other_case_check':None}
    summary,rows=planned(exported)
    result=m.publish(summary,rows,'a'*64,FakeClient(rows,mutate=wrap),receipt_directory=exported.root/'receipts',poll_seconds=0)
    assert result['status']=='verified' and result['scores']['local_contract_pass']['passed']==1


@pytest.mark.parametrize('alias',[
    {'item.query':'wrong'}, {'unknown':'wrong'}, {'item.unknown':None},
    {'item.local_checks.anchor':1}, {'item.local_checks.absent':True},
    {'item.local_checks.deep.key':None}, {'item.local_checks.':None},
])
def test_flattened_aliases_must_be_known_and_consistent(exported,alias):
    _,rows=planned(exported)
    with pytest.raises(m.PublicationError,match='remote_output_alias'):
        m.echoed_item({'item':rows[0],**alias})


def test_explicit_resume_never_creates_missing_run(exported):
    summary,rows=planned(exported);client=FakeClient(rows);directory=exported.root/'receipts'
    with pytest.raises(m.PublicationError,match='resume_requires_existing_run'):
        m.publish(summary,rows,'a'*64,client,receipt_directory=directory,poll_seconds=0,resume_existing=True)
    assert client.calls==[] and not list(directory.glob('*.json'))


def test_explicit_resume_allows_checkout_drift_but_keeps_original_plan(exported):
    summary,rows=planned(exported);client=FakeClient(rows,pending=True);directory=exported.root/'receipts'
    m.publish(summary,rows,'a'*64,client,receipt_directory=directory,poll_seconds=0)
    exported.source.write_text('changed = True\n')
    with pytest.raises(m.PublicationError,match='current_source_hash_mismatch'):planned(exported)
    resumed,rows=planned(exported,'historical');resumed['source_status']='current'
    client.calls.clear();client.pending=False
    assert m.publish(resumed,rows,'a'*64,client,receipt_directory=directory,poll_seconds=0,resume_existing=True)['status']=='verified'
    assert [kind for kind,_ in client.calls]==['read','outputs']
    receipt=json.loads(next(directory.glob('*.json')).read_text())
    assert receipt['plan']==summary
    resumed['release_label']='changed-label';client.calls.clear()
    with pytest.raises(m.PublicationError,match='receipt_plan_mismatch'):
        m.publish(resumed,rows,'a'*64,client,receipt_directory=directory,poll_seconds=0,resume_existing=True)
    assert client.calls==[]


def test_explicit_resume_rejects_eval_without_run(exported):
    summary,rows=planned(exported);client=FakeClient(rows,pending=True);directory=exported.root/'receipts'
    m.publish(summary,rows,'a'*64,client,receipt_directory=directory,poll_seconds=0)
    path=next(directory.glob('*.json'));receipt=json.loads(path.read_text());receipt['stage']='eval_created';receipt.pop('run_id')
    path.write_text(json.dumps(receipt));client.calls.clear()
    with pytest.raises(m.PublicationError,match='resume_requires_existing_run'):
        m.publish(summary,rows,'a'*64,client,receipt_directory=directory,poll_seconds=0,resume_existing=True)
    assert client.calls==[]
