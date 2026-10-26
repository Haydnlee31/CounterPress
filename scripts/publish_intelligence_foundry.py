"""Publish reviewed synthetic evaluation artifacts to the existing Foundry project.

Default: offline plan only. --apply creates a dataset evaluation, never a model
or agent target. Production conversations, native trajectories and LLM judges
are deliberately excluded. Azure SDK dependencies are imported only for apply.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import itertools
import json
import logging
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('curated_foundry_export', ROOT/'scripts/export_intelligence_foundry.py')
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)
MAX_ROWS = 64
FILES = ('manifest.json','evaluation.jsonl','execution-summaries.jsonl')
HEX = re.compile(r'^[a-f0-9]{64}$')
VERSION = 'footie-contract-publication-v1'

# These programs score recorded artifacts, not new model output. The first is
# explicitly an import of local checks; the second independently rechecks only
# the deterministic assertions available in exported context/ground_truth.
LOCAL_GRADER = '''def grade(sample, item):
    try:
        checks = item["local_checks"]
        return float(item["local_pass"] is True and isinstance(checks, dict)
                     and bool(checks) and all(type(v) is bool and v for v in checks.values()))
    except (KeyError, TypeError, AttributeError):
        return 0.0
'''
FACT_GRADER = '''def grade(sample, item):
    import json
    import math
    try:
        if item.get("response_recorded") is not True:
            return 0.0
        context = json.loads(item["context"])
        expected = json.loads(item["ground_truth"])
        facts = context["validated_facts"]
        if not isinstance(facts, list) or context["answer_status"] != expected["status"]:
            return 0.0
        if expected.get("no_facts") and facts:
            return 0.0
        if expected["status"] == "answered" and not facts:
            return 0.0
        for anchor in expected.get("anchors", []):
            matches = [f for f in facts if f.get("metric") == anchor["metric"]
                       and ("subject_id" not in anchor or f.get("subject_id") == anchor["subject_id"])]
            def same(value):
                target = anchor["value"]
                if type(target) in (int, float):
                    return type(value) in (int, float) and math.isfinite(value) and math.isclose(value, target, rel_tol=0, abs_tol=1e-6)
                return value == target and type(value) is type(target)
            if not matches or ("value" in anchor and not any(same(f.get("value")) for f in matches)):
                return 0.0
        for metric in expected.get("null_metrics", []):
            if not any(f.get("metric") == metric and f.get("value") is None for f in facts):
                return 0.0
        if expected.get("required_subject") and not any(f.get("subject_id") == expected["required_subject"] for f in facts):
            return 0.0
        events = []
        def collect(value):
            if isinstance(value, dict):
                if "event_id" in value and "period" in value and "elapsed_ms" in value:
                    events.append(value)
                for child in value.values(): collect(child)
            elif isinstance(value, list):
                for child in value: collect(child)
        collect(context.get("evidence_by_fingerprint", {}))
        ids = {event["event_id"] for event in events}
        required = set(expected.get("evidence_event_ids", []))
        if expected.get("evidence_event_id"): required.add(expected["evidence_event_id"])
        if not required.issubset(ids) or ids.intersection(expected.get("forbidden_evidence_event_ids", [])):
            return 0.0
        if expected.get("max_event"):
            limit = expected["max_event"]
            boundary = (limit["period"], limit["elapsed_ms"])
            selected_match = context.get("request_scope", {}).get("match_id")
            for event in events:
                if selected_match and event.get("match_id") not in (None, selected_match): continue
                if (event["period"], event["elapsed_ms"]) > boundary: return 0.0
                if "available_period" in event and "available_ms" in event and (event["available_period"], event["available_ms"]) > boundary: return 0.0
        return 1.0
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError):
        return 0.0
'''


class PublicationError(Exception):
    """Fixed diagnostic code only; never include SDK errors or private config."""


def require(condition, code):
    if not condition:raise PublicationError(code)


def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def digest(value):return sha256(canonical(value).encode()).hexdigest()
def file_hash(path):return sha256(Path(path).read_bytes()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()


def private_json(path, value, *, replace=False):
    path=Path(path)
    require(not path.is_symlink(), 'receipt_symlink_forbidden')
    target=path.with_name(path.name+'.pending') if replace else path
    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream:
        stream.write(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
        stream.flush();os.fsync(stream.fileno())
    if replace:os.replace(target,path)


def reviewed_export(directory, report_path, manifest_hash, source_status, *, root=ROOT):
    directory=Path(directory).resolve();report_path=Path(report_path).resolve();root=Path(root).resolve()
    require(source_status in ('historical','current'), 'source_status_required')
    require(HEX.fullmatch(manifest_hash or ''), 'manifest_hash_required')
    require(directory.is_dir() and not any((directory/name).is_symlink() for name in FILES), 'export_directory_invalid')
    require({p.name for p in directory.iterdir()}==set(FILES), 'unexpected_export_files')
    require(all((directory/name).stat().st_size<=50_000_000 for name in FILES), 'export_too_large')
    require(file_hash(directory/'manifest.json')==manifest_hash,'reviewed_manifest_changed')
    manifest=json.loads((directory/'manifest.json').read_text())
    require(manifest.get('format')=='footie-foundry-curated-export-v1','export_format_invalid')
    corpus=root/'fixtures/assistant'/str(manifest.get('corpus',''))
    require(corpus.name in exporter.CORPORA and corpus.parent==root/'fixtures/assistant','corpus_not_curated')
    require(file_hash(report_path)==manifest.get('report_sha256'),'report_hash_mismatch')
    # Rebuild with the existing exporter to verify scores and every exported byte
    # are derived from the bound report/corpus, not a rewritten manifest alone.
    with tempfile.TemporaryDirectory(prefix='footie-export-review-') as temp:
        regenerated=Path(temp)/'reviewed'
        exporter.export_report(report_path,corpus,regenerated,root=root)
        require(all((regenerated/name).read_bytes()==(directory/name).read_bytes() for name in FILES),
                'export_does_not_match_bound_report')
    require(type(manifest['scored_rows']) is int and 1<=manifest['scored_rows']<=MAX_ROWS,'row_limit_exceeded')
    changed=[]
    for name,expected in manifest['source_sha256'].items():
        source=(root/name).resolve()
        if not source.is_relative_to(root) or not source.is_file() or file_hash(source)!=expected:changed.append(name)
    if source_status=='current':require(not changed,'current_source_hash_mismatch')
    content={row['case_id']:row for row in map(json.loads,(directory/'evaluation.jsonl').read_text().splitlines())}
    cases={c['id']:c for c in json.loads(corpus.read_text())['cases']}
    rows=[]
    for score in manifest['deterministic_scores']:
        case=cases[score['id']];recorded=score['id'] in content
        entry=content.get(score['id']) or {'case_id':score['id'],'query':case['request']['question'],'response':'',
            'context':canonical({'answer_status':score.get('status'),'validated_facts':[],'evidence_by_fingerprint':{}}),
            'ground_truth':canonical(case['expect'])}
        rows.append(exporter.checked({**entry,'response_recorded':recorded,'local_pass':score['passed'],
            'local_checks':score['checks'],'bucket':score['bucket'],'journey':score['journey']}))
    require(len(rows)==manifest['scored_rows'] and len({r['case_id'] for r in rows})==len(rows),'scored_rows_mismatch')
    require(len(canonical(rows).encode())<=8_000_000,'inline_dataset_too_large')
    return manifest,rows,changed


def project_binding(config_path, expected_hash):
    path=Path(config_path)
    require(not path.is_symlink() and path.stat().st_mode & 0o077==0,'project_config_not_private')
    config=json.loads(path.read_text())
    fields={'project_endpoint','project_resource_sha256','endpoint_sha256','project_name','account_name','resource_group'}
    require(set(config)==fields,'project_config_schema_invalid')
    require(config['project_name']=='CounterPress' and config['account_name']=='counterpress-dev-01'
            and config['resource_group']=='counterpress-dev','project_not_existing_footie')
    endpoint=config['project_endpoint'];parsed=urlsplit(endpoint)
    require(parsed.scheme=='https' and parsed.hostname and parsed.hostname==config['account_name']+'.services.ai.azure.com'
            and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
            and not parsed.port and parsed.path=='/api/projects/CounterPress','project_endpoint_invalid')
    require(HEX.fullmatch(config['project_resource_sha256']) and config['endpoint_sha256']==sha256(endpoint.encode()).hexdigest(),
            'project_resource_binding_invalid')
    require(HEX.fullmatch(expected_hash or '') and digest(config)==expected_hash,'reviewed_project_binding_mismatch')
    return config


def grade_locally(source,row):
    # Only constant, reviewed programs above are executed, never imported input.
    require(source in (LOCAL_GRADER,FACT_GRADER),'unreviewed_grader')
    scope={};exec(source,scope)
    return scope['grade']({},row)


def evaluation_payload():
    fields={name:{'type':'string'} for name in ('case_id','query','response','context','ground_truth','bucket','journey')}
    fields.update({'response_recorded':{'type':'boolean'},'local_pass':{'type':'boolean'},
                   'local_checks':{'type':'object','additionalProperties':{'type':'boolean'}}})
    return {'name':'Footie recorded synthetic contracts v1',
        'data_source_config':{'type':'custom','item_schema':{'type':'object','properties':fields,'required':list(fields),'additionalProperties':False},'include_sample_schema':False},
        'testing_criteria':[{'type':'python','name':'local_contract_pass','source':LOCAL_GRADER,'pass_threshold':0.5},
                            {'type':'python','name':'recorded_fact_assertions','source':FACT_GRADER,'pass_threshold':0.5}]}


def plan(directory,report,manifest_hash,source_status,release_label,*,root=ROOT):
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}',release_label or ''),'release_label_invalid')
    manifest,rows,changed=reviewed_export(directory,report,manifest_hash,source_status,root=root)
    grades={name:[grade_locally(source,row) for row in rows] for name,source in
            (('local_contract_pass',LOCAL_GRADER),('recorded_fact_assertions',FACT_GRADER))}
    original=[float(s['passed']) for s in manifest['deterministic_scores']]
    require(grades['local_contract_pass']==original,'original_scores_inconsistent')
    summary={'schema':VERSION,'release_label':release_label,'source_status':source_status,
        'original_label':manifest['evaluation']['label'],'original_mode':manifest['evaluation']['mode'],
        'manifest_sha256':manifest_hash,'report_sha256':manifest['report_sha256'],'corpus_sha256':manifest['corpus_sha256'],
        'source_manifest_sha256':digest(manifest['source_sha256']),'source_sha256':manifest['source_sha256'],
        'rows':len(rows),'missing_responses':len(manifest['excluded_rows']),
        'scores':{k:{'passed':sum(v),'total':len(v)} for k,v in grades.items()},
        'historical_changed_source_count':len(changed),
        'grader_sha256':digest(evaluation_payload()['testing_criteria']),
        'limitations':['Local contract pass preserves original deterministic checks; it is not a new AI judge score.',
          'Recorded fact assertions recheck status, numeric anchors, nulls, subjects and available event/time assertions only.',
          'No native trajectories, tool-call accuracy, semantic groundedness or causal-football judgments are claimed.',
          'Rows with missing responses stay in the local-score denominator; fact assertions score them zero.',
          'Historical target latency/tokens are original measurements, never inferred from this publication job.'],
        'target_model_calls':0,'judge_model_calls':0}
    return summary,rows


def metadata(summary):
    return {'footie_publication':VERSION,'release':summary['release_label'],'source_status':summary['source_status'],
            'original_label':summary['original_label'],'mode':summary['original_mode'],
            'manifest_sha256':summary['manifest_sha256'],'corpus_sha256':summary['corpus_sha256'],
            'source_sha256':summary['source_manifest_sha256'],'grader_sha256':summary['grader_sha256']}


@contextmanager
def publication_lock(directory,key):
    import fcntl
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    require(not directory.is_symlink() and directory.stat().st_mode & 0o077==0,'receipt_directory_not_private')
    path=directory/(key+'.lock')
    require(not path.is_symlink(),'receipt_symlink_forbidden')
    with os.fdopen(os.open(path,os.O_RDWR|os.O_CREAT,0o600),'w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise PublicationError('publication_already_running') from None
        try:yield directory/(key+'.json')
        finally:fcntl.flock(lock,fcntl.LOCK_UN)


def object_dict(value):return value if isinstance(value,dict) else value.model_dump(mode='json')
def valid_id(value):return isinstance(value,str) and bool(re.fullmatch(r'[A-Za-z0-9_.-]{1,200}',value))


def read_retry(call):
    for attempt in range(2):
        try:return call()
        except Exception:
            if attempt:raise PublicationError('remote_read_failed_resume_safe') from None
            time.sleep(1)


def publish(summary,rows,project_hash,client,*,receipt_directory=None,poll_seconds=30):
    require(type(poll_seconds) is int and 0<=poll_seconds<=55,'poll_duration_invalid')
    key=digest({'project':project_hash,'manifest':summary['manifest_sha256'],'grader':summary['grader_sha256']})
    directory=receipt_directory or ROOT/'var/foundry-publication-receipts'
    with publication_lock(directory,key) as receipt_path:
        if receipt_path.exists():
            require(receipt_path.stat().st_mode & 0o077==0,'receipt_not_private')
            receipt=json.loads(receipt_path.read_text())
            stable=lambda value:{k:v for k,v in value.items() if k!='historical_changed_source_count'}
            require(receipt['publication_key']==key and stable(receipt['plan'])==stable(summary),'receipt_plan_mismatch')
            require(receipt['stage'] not in ('eval_submission_pending','run_submission_pending'),
                    'uncertain_submission_manual_reconciliation_required')
            if receipt['stage']=='verified':return receipt['result']
            require(receipt['stage'] in ('eval_created','run_created'),'receipt_stage_invalid')
        else:
            receipt={'schema':VERSION,'publication_key':key,'project_binding_sha256':project_hash,
                     'created_at':now(),'stage':'eval_submission_pending','plan':summary}
            private_json(receipt_path,receipt)
            try:
                result=object_dict(client.evals.create(**evaluation_payload(),metadata=metadata(summary)))
                require(valid_id(result.get('id')),'remote_eval_id_invalid')
            except Exception:raise PublicationError('eval_submission_uncertain_manual_reconciliation_required') from None
            receipt.update(eval_id=result['id'],stage='eval_created');private_json(receipt_path,receipt,replace=True)
        if receipt['stage']=='eval_created':
            receipt['stage']='run_submission_pending';private_json(receipt_path,receipt,replace=True)
            try:
                result=object_dict(client.evals.runs.create(eval_id=receipt['eval_id'],
                    name='footie-'+summary['release_label']+'-'+summary['original_label'],metadata=metadata(summary),
                    data_source={'type':'jsonl','source':{'type':'file_content','content':[{'item':row} for row in rows]}}))
                require(valid_id(result.get('id')),'remote_run_id_invalid')
            except Exception:raise PublicationError('run_submission_uncertain_manual_reconciliation_required') from None
            receipt.update(run_id=result['id'],stage='run_created');private_json(receipt_path,receipt,replace=True)
        deadline=time.monotonic()+poll_seconds
        while True:
            run=object_dict(read_retry(lambda:client.evals.runs.retrieve(run_id=receipt['run_id'],eval_id=receipt['eval_id'])))
            status=run.get('status')
            if status=='completed':break
            require(status not in ('failed','canceled','cancelled'),'remote_evaluation_failed_no_resubmit')
            require(status in ('queued','in_progress'),'remote_evaluation_status_unknown')
            if time.monotonic()>=deadline:return {'status':'pending','publication_key':key,'model_calls':0}
            time.sleep(min(5,max(0,deadline-time.monotonic())))
        # Read at most MAX_ROWS+1 items. No raw provider errors/content are emitted.
        def outputs():
            page=client.evals.runs.output_items.list(eval_id=receipt['eval_id'],run_id=receipt['run_id'],limit=MAX_ROWS+1)
            return [object_dict(v) for v in itertools.islice(page,MAX_ROWS+1)]
        items=read_retry(outputs)
        require(len(items)==len(rows),'remote_output_count_mismatch')
        # Match the echoed input item and exact hash, never response text or assumed row ordering.
        expected={row['case_id']:row for row in rows};seen=set();scores=[]
        for output in items:
            echoed=output.get('datasource_item',{})
            if isinstance(echoed,dict) and set(echoed)=={'item'}:echoed=echoed['item']
            index=echoed.get('case_id') if isinstance(echoed,dict) else None
            require(index in expected and index not in seen and digest(echoed)==digest(expected[index]),
                    'remote_output_identity_mismatch');seen.add(index)
            sample=output.get('sample') or {}
            require(output.get('status') in ('completed','pass','fail') and isinstance(sample,dict) and not sample.get('error'),
                    'remote_output_incomplete')
            results=output.get('results',[])
            require(isinstance(results,list) and len(results)==2,'remote_metric_count_mismatch')
            by_name={r.get('name'):r for r in results}
            require(set(by_name)=={'local_contract_pass','recorded_fact_assertions'},'remote_metric_names_mismatch')
            row=expected[index];values={}
            for name,source in (('local_contract_pass',LOCAL_GRADER),('recorded_fact_assertions',FACT_GRADER)):
                metric=by_name[name];score=grade_locally(source,row)
                require(type(metric.get('score')) in (int,float) and metric['score']==score and metric.get('passed') is (score==1.0),
                        'remote_score_mismatch')
                require(not metric.get('error'),'remote_grader_error')
                values[name]=score
            scores.append({'case_id':row['case_id'],**values})
        counts=run.get('result_counts')
        passed=sum(all(row[name]==1.0 for name in ('local_contract_pass','recorded_fact_assertions')) for row in scores)
        require(isinstance(counts,dict) and counts.get('total')==len(rows) and counts.get('errored')==0
                and counts.get('passed')==passed and counts.get('failed')==len(rows)-passed,'remote_result_counts_mismatch')
        result={'status':'verified','publication_key':key,'rows':len(rows),'scores':summary['scores'],
                'target_model_calls':0,'judge_model_calls':0}
        receipt.update(stage='verified',verified_at=now(),result=result,row_scores=scores,
                       remote_result_counts=run.get('result_counts'),remote_per_model_usage=run.get('per_model_usage'))
        # Code-only/dataset runs must not silently turn into a target/judge run.
        usage=run.get('per_model_usage')
        require(isinstance(usage,list) and (not usage or all(u.get('invocation_count',0)==0 and u.get('total_tokens',0)==0 for u in usage)),
                'unexpected_remote_model_usage')
        private_json(receipt_path,receipt,replace=True)
        return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export-dir',type=Path,required=True);parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--manifest-sha256',required=True);parser.add_argument('--source-status',choices=('historical','current'),required=True)
    parser.add_argument('--release-label',required=True);parser.add_argument('--apply',action='store_true')
    parser.add_argument('--project-config',type=Path);parser.add_argument('--project-binding-sha256')
    parser.add_argument('--poll-seconds',type=int,default=30)
    args=parser.parse_args()
    try:
        summary,rows=plan(args.export_dir,args.report,args.manifest_sha256,args.source_status,args.release_label)
        config=project_binding(args.project_config,args.project_binding_sha256) if args.project_config is not None else None
        if not args.apply:
            print(json.dumps({'status':'dry_run','plan':summary,'project_binding_sha256':args.project_binding_sha256 if config else None,'network_calls':0},indent=2));return 0
        require(config is not None,'private_project_config_required')
        require(os.environ.get('AZURE_AI_PROJECTS_CONSOLE_LOGGING','false').lower()!='true','sdk_console_logging_forbidden')
        require(os.environ.get('OPENAI_LOG','').lower() not in ('debug','info'),'sdk_console_logging_forbidden')
        for name in ('azure','openai','httpx','httpcore'):logging.getLogger(name).setLevel(logging.CRITICAL)
        from azure.ai.projects import AIProjectClient
        from azure.identity import AzureCliCredential
        with AzureCliCredential() as credential, AIProjectClient(endpoint=config['project_endpoint'],credential=credential,retry_total=0) as project:
            with project.get_openai_client(max_retries=0,timeout=30) as client:
                result=publish(summary,rows,args.project_binding_sha256,client,poll_seconds=args.poll_seconds)
        print(json.dumps(result));return 0 if result['status']=='verified' else 3
    except PublicationError as e:
        print(json.dumps({'status':'blocked','diagnostic':str(e)}));return 2
    except Exception:
        print(json.dumps({'status':'blocked','diagnostic':'publication_validation_or_transport_failed'}));return 2


if __name__=='__main__':raise SystemExit(main())
