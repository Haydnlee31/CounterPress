"""Offline exporter preserves failures, provenance and privacy boundaries."""
import importlib.util
import json
from hashlib import sha256
from pathlib import Path
import pytest

PATH=Path(__file__).resolve().parents[1]/'scripts/export_intelligence_foundry.py'
spec=importlib.util.spec_from_file_location('foundry_export',PATH)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


@pytest.fixture
def source(tmp_path):
    corpus_path=tmp_path/'fixtures/assistant/intelligence_questions.json'
    corpus_path.parent.mkdir(parents=True)
    corpus={'version':'test-v1','cases':[{'id':'case1','bucket':'supported','journey':'buildup',
        'request':{'question':'What made that goal happen?','match_id':'synthetic-match'},
        'expect':{'status':'answered','anchors':[{'metric':'completed_passes','value':2}]}}]}
    corpus_path.write_text(json.dumps(corpus))
    report={'version':1,'label':'regression','mode':'azure_multiagent','evaluation_status':'failed','sources_changed_during_run':[],
        'corpus_sha256':sha256(corpus_path.read_bytes()).hexdigest(),
        'source_sha256':{str(corpus_path):sha256(corpus_path.read_bytes()).hexdigest(),str(tmp_path/'backend/example.py'):'a'*64},
        'results':[{'id':'case1','bucket':'supported','journey':'buildup','passed':False,'checks':{'anchor_0':False},
            'question':'What made that goal happen?','text':['A completed pass preceded the goal.'],
            'facts':[{'subject_id':'team','metric':'completed_passes','value':1,'unit':'count','evidence':{'events':[{'event_id':'e1','revision':1}]},'href':'#/private-unused'}],
            'execution':{'roles':['match'],'requests':2,'plans':[{'operation':'match'}],'usage':{'total_tokens':40},'completed_result':True,'unapproved_raw_provider_output':'do not export'}}]}
    report_path=tmp_path/'report.json';report_path.write_text(json.dumps(report))
    return tmp_path,corpus_path,report_path,report


def export(source):
    root,corpus,report,_=source
    return module.export_report(report,corpus,root/'export',root=root)


def update(source,mutate):
    root,corpus,path,report=source;mutate(report);path.write_text(json.dumps(report))


def test_export_preserves_failure_and_hashes_without_invented_tool_messages(source):
    manifest=export(source);root=source[0]
    assert manifest['scored_rows']==manifest['exported_rows']==1
    assert manifest['evaluation']['label']=='regression'
    assert manifest['deterministic_scores'][0]['passed'] is False
    rows=[json.loads(line) for line in (root/'export/evaluation.jsonl').read_text().splitlines()]
    assert rows[0]['ground_truth']==module.canonical(source[3] and json.loads(source[1].read_text())['cases'][0]['expect'])
    assert 'private-unused' not in rows[0]['context']
    summary=json.loads((root/'export/execution-summaries.jsonl').read_text())
    assert summary['capture_kind']=='observed_execution_summary'
    assert summary['not_a_native_tool_message_trace'] is True
    assert 'unapproved_raw_provider_output' not in summary['observations']
    assert str(root) not in (root/'export/manifest.json').read_text()
    for name,value in manifest['artifacts_sha256'].items():assert sha256((root/'export'/name).read_bytes()).hexdigest()==value


def test_missing_rendered_response_keeps_original_score_not_fabricated_answer(source):
    update(source,lambda r:r['results'][0].pop('text'))
    manifest=export(source)
    assert manifest['exported_rows']==0 and manifest['scored_rows']==1
    assert manifest['excluded_rows']==[{'id':'case1','reason':'rendered_response_not_recorded'}]


@pytest.mark.parametrize('mutation',[
    lambda r:r.update(corpus_sha256='0'*64),
    lambda r:r.update(sources_changed_during_run=['source.py']),
    lambda r:r['results'][0].update(question='A private user conversation'),
    lambda r:r['results'][0].update(id='unknown-case'),
    lambda r:r['results'].append(dict(r['results'][0])),
    lambda r:r.update(source_sha256={}),
    lambda r:r.update(mode='production_log'),
])
def test_provenance_mismatch_rejected_without_partial_output(source,mutation):
    update(source,mutation)
    with pytest.raises(ValueError):export(source)
    assert not (source[0]/'export').exists()


@pytest.mark.parametrize('text',[
    'Authorization: Bearer abcdefghijklmnop123456',
    'https://private-resource.openai.azure.com/openai/v1/',
    'https://private.services.ai.azure.com/api/projects/private',
    'api_key=superprivate12345',
    '{"api_key":"superprivate12345"}',
    'eyJhbGciOiJub25l.eyJzdWIiOiIxMjMifQ.signature',
])
def test_sensitive_output_fails_closed(source,text):
    update(source,lambda r:r['results'][0].update(text=[text]))
    with pytest.raises(ValueError):export(source)
    assert not (source[0]/'export').exists()


def test_existing_export_cannot_be_overwritten(source):
    export(source)
    with pytest.raises(ValueError,match='new export'):export(source)


def test_noncurated_corpus_not_accepted(source):
    root,corpus,report,_=source
    other=root/'production-conversations.json';other.write_bytes(corpus.read_bytes())
    with pytest.raises(ValueError,match='curated'):
        module.export_report(report,other,root/'export',root=root)


def test_export_timing_metadata_is_bounded_and_strips_provider_content(source):
    good={'stage':'provider_http','role':'match','started_ms':4,'duration_ms':72.5,'status':'ok'}
    contaminated={**good,'url':'https://private-resource.openai.azure.com','prompt':'never export this'}
    update(source,lambda r:(r['results'][0]['execution'].update(stage_timings=[contaminated,
        {**good,'stage':'private-stage'},{**good,'duration_ms':float('inf')},
        {**good,'role':['match']},{**good,'started_ms':-1},{**good,'duration_ms':300001}]),
        r.update(measurement={'app_lifecycle':'shared_app','app_startup_ms':15,'paid_warmup_requests':0,
            'first_request_included':True,'timing_note':'private ignored note'})))
    manifest=export(source)
    summary=json.loads((source[0]/'export/execution-summaries.jsonl').read_text())
    assert summary['observations']['stage_timings']==[good]
    assert manifest['measurement']=={'app_lifecycle':'shared_app','app_startup_ms':15,
        'paid_warmup_requests':0,'first_request_included':True}
    assert 'private' not in (source[0]/'export/execution-summaries.jsonl').read_text()
