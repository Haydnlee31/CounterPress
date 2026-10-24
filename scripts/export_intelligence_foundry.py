"""Export curated synthetic benchmark responses for review in Foundry.

Offline only: no Azure import, network call, credential read or model execution.
Existing observations are not converted into invented native tool trajectories.
"""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CORPORA = ('intelligence_questions.json', 'intelligence_fresh_questions.json', 'intelligence_final_holdout.json')
HEX = re.compile(r'^[a-f0-9]{64}$')
SENSITIVE = re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----|\bBearer\s+[A-Za-z0-9._~-]{12,}|'
    r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|'
    r'https?://[^\s"<>]*(?:openai\.azure\.com|services\.ai\.azure\.com|webpubsub\.azure\.com)|'
    r'(?:api[_ -]?key|client[_ -]?secret|connection[_ -]?string|access[_ -]?token)\s*["\']?\s*[=:]\s*["\']?[A-Za-z0-9+/._~=-]{8,}', re.I)


def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)


def digest(value):
    return sha256(canonical(value).encode()).hexdigest()


def checked(value):
    raw=canonical(value)
    if len(raw.encode())>1_000_000:raise ValueError('Export row exceeds the reviewable size limit')
    def inspect(item):
        if isinstance(item, str) and SENSITIVE.search(item):
            raise ValueError('Potential credential or private service endpoint in export; inspect source locally')
        if isinstance(item, dict):
            for key, child in item.items():
                if key.lower() in {'api_key','apikey','client_secret','connection_string','access_token','authorization'} and child:
                    raise ValueError('Credential-shaped field in export')
                inspect(child)
        elif isinstance(item, (list, tuple)):
            for child in item:inspect(child)
    inspect(value)
    return value


def select(obj,fields):
    return {key:obj[key] for key in fields if key in obj}



def stage_timings(value):
    """Retain bounded observed timing metadata, never arbitrary provider fields."""
    if not isinstance(value,(list,tuple)):return []
    rows=[]
    for item in value[:100]:
        if not isinstance(item,dict):continue
        if not all(isinstance(item.get(k),str) for k in ('stage','role','status')):continue
        if (item['stage'] not in {'initial','context','route','query','tool','followup','synthesize','auth','provider_http'}
                or item['role'] not in {'orchestrator','match','career'}
                or item['status'] not in {'ok','error','cancelled'}):continue
        if not all(isinstance(item.get(k),(int,float)) and not isinstance(item[k],bool)
                   and math.isfinite(item[k]) and 0<=item[k]<=300000 for k in ('started_ms','duration_ms')):continue
        rows.append(select(item,('stage','role','started_ms','duration_ms','status')))
    return rows


def measurement_metadata(value):
    if not isinstance(value,dict):return {}
    if value.get('app_lifecycle') not in ('shared_app','fresh_app_per_case','local_service_per_case'):return {}
    result={'app_lifecycle':value['app_lifecycle']}
    if isinstance(value.get('first_request_included'),bool):result['first_request_included']=value['first_request_included']
    for key in ('app_startup_ms','paid_warmup_requests','isolated_api_hourly_limit',
                'persisted_ledger_hourly_limit','persisted_ledger_daily_limit','invocation_attempt_limit'):
        number=value.get(key)
        if isinstance(number,(int,float)) and not isinstance(number,bool) and math.isfinite(number) and 0<=number<=300000:result[key]=number
    return result


def response_text(row):
    blocks=(row.get('narrative') or {}).get('blocks',[])
    values=[b.get('text') for b in blocks if isinstance(b,dict)]
    if not values:
        text=row.get('text')
        values=[text] if isinstance(text,str) else text if isinstance(text,list) else []
    return '\n'.join(dict.fromkeys(value.strip() for value in values if isinstance(value,str) and value.strip()))


def content_context(case,row):
    facts=[];evidence={}
    for fact in row.get('facts',[]):
        if not isinstance(fact,dict):raise ValueError('Invalid scored fact')
        item=select(fact,('subject_kind','subject_id','subject_name','metric','label','value','unit','scope','coverage'))
        refs=fact.get('evidence')
        if refs:
            identity=digest(refs);evidence[identity]=refs;item['evidence_ref']=identity
        facts.append(item)
    return {'request_scope':select(case['request'],('match_id','player_id','club_id','event_id','event_revision','cutoff','season','as_of','preferences','previous_plan')),
            'validated_facts':facts,'evidence_by_fingerprint':evidence,
            'answer_status':row.get('status'),
            'limitations':'Recorded football events only; no video tracking or unobserved tactical causality.'}


def export_report(report_path, corpus_path, output_dir, *, root=ROOT):
    report_path=Path(report_path);corpus_path=Path(corpus_path).resolve();output_dir=Path(output_dir)
    allowed={(root/'fixtures/assistant'/name).resolve() for name in CORPORA}
    if corpus_path not in allowed:raise ValueError('Only the curated synthetic intelligence corpora can be exported')
    if output_dir.exists():raise ValueError('Choose a new export directory; prior evidence must be preserved')
    report_bytes=report_path.read_bytes();corpus_bytes=corpus_path.read_bytes()
    if len(report_bytes)>50_000_000 or len(corpus_bytes)>2_000_000:raise ValueError('Input exceeds export size limit')
    report=json.loads(report_bytes);corpus=json.loads(corpus_bytes)
    if report.get('version')!=1 or report.get('label') not in ('baseline','first_holdout','regression'):
        raise ValueError('Expected a labelled intelligence evaluation report')
    if report.get('mode') not in ('local_lookup','azure_single_agent','azure_multiagent'):
        raise ValueError('Unsupported evaluation mode')
    if report.get('sources_changed_during_run'):raise ValueError('Evaluation sources changed during the run')
    corpus_hash=sha256(corpus_bytes).hexdigest()
    if report.get('corpus_sha256')!=corpus_hash:raise ValueError('Report and curated corpus fingerprints differ')
    sources=report.get('source_sha256')
    if not isinstance(sources,dict) or not sources or any(not isinstance(v,str) or not HEX.fullmatch(v) for v in sources.values()):
        raise ValueError('Source fingerprints are missing or invalid')
    if not any(Path(k).resolve()==corpus_path and value==corpus_hash for k,value in sources.items()):
        raise ValueError('Scored source manifest does not bind this corpus')
    cases={c['id']:c for c in corpus['cases']}
    if len(cases)!=len(corpus['cases']):raise ValueError('Duplicate curated case ID')
    results=report.get('results',[])
    if not results or len({r['id'] for r in results})!=len(results):raise ValueError('Empty or duplicate scored case IDs')
    data=[];trajectories=[];scores=[];excluded=[]
    for row in results:
        case=cases.get(row['id'])
        if case is None or row.get('bucket')!=case['bucket'] or row.get('journey')!=case['journey']:
            raise ValueError('Scored row is not bound to the curated case')
        if row.get('question') is not None and row['question']!=case['request']['question']:
            raise ValueError('Question differs from the curated synthetic corpus')
        if not isinstance(row.get('passed'),bool) or not isinstance(row.get('checks'),dict) or not all(isinstance(v,bool) for v in row['checks'].values()):
            raise ValueError('Invalid deterministic score metadata')
        scores.append(checked(select(row,('id','bucket','journey','passed','checks','status','mode','duration_ms','fallback'))))
        response=response_text(row)
        if not response:
            excluded.append({'id':row['id'],'reason':'rendered_response_not_recorded'})
            continue
        # These string columns match the documented precomputed-response dataset
        # shape. Ground truth is the independently authored assertion set, not
        # another answer generated by the system being evaluated.
        item={'case_id':row['id'],'query':case['request']['question'],'response':response,
              'context':canonical(content_context(case,row)), 'ground_truth':canonical(case['expect'])}
        data.append(checked(item))
        execution=row.get('execution') or {}
        trajectory={'case_id':row['id'],'capture_kind':'observed_execution_summary',
            'not_a_native_tool_message_trace':True,
            'observations':select(execution,('roles','plans','requests','tools','usage','reported_requests','unreported_usage_attempts','completed_result','partial_failures')),
            'answer_mode':row.get('mode','local_lookup'),'response_sha256':sha256(response.encode()).hexdigest()}
        if 'stage_timings' in execution:trajectory['observations']['stage_timings']=stage_timings(execution['stage_timings'])
        trajectories.append(checked(trajectory))
    source_hashes={}
    for name,value in sources.items():
        path=Path(name).resolve()
        try:label=path.relative_to(root.resolve()).as_posix()
        except ValueError:label='external-source/'+sha256(str(path).encode()).hexdigest()[:16]+'/'+path.name
        source_hashes[label]=value
    payloads={'evaluation.jsonl':''.join(canonical(row)+'\n' for row in data),
              'execution-summaries.jsonl':''.join(canonical(row)+'\n' for row in trajectories)}
    manifest=checked({'format':'footie-foundry-curated-export-v1','privacy':'curated_synthetic_cases_only; no production conversation ingestion',
        'report_sha256':sha256(report_bytes).hexdigest(),'corpus_sha256':corpus_hash,'corpus_version':corpus.get('version'),
        'corpus':corpus_path.name,'evaluation':select(report,('created_at','evaluation_status','mode','label','requested_cases','model_attempts','tokens','bucket_scores','latency_ms','workflow_limits')),
        'measurement':measurement_metadata(report.get('measurement')),
        'source_sha256':source_hashes,'scored_rows':len(results),'exported_rows':len(data),'excluded_rows':excluded,
        'deterministic_scores':scores,'artifacts_sha256':{name:sha256(raw.encode()).hexdigest() for name,raw in payloads.items()},
        'limitations':['No new model scoring or cloud upload was performed.',
            'Original failure scores and report label are retained; repeat/tuned cases are not fresh holdout evidence.',
            'Content evaluators can use evaluation.jsonl; execution summaries are not native tool-call conversations.',
            'Timing stages overlap and nest; their durations must not be summed into request latency.',
            'Numeric ground-truth anchors do not replace human review of explanation usefulness or causal language.',
            'Review all exported content before upload; pattern checks are not a universal secret detector.']})
    output_dir.mkdir(parents=True)
    for name,raw in payloads.items():(output_dir/name).write_text(raw)
    (output_dir/'manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--corpus',type=Path,default=ROOT/'fixtures/assistant/intelligence_questions.json')
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    try:manifest=export_report(args.report,args.corpus,args.output_dir)
    except (ValueError,KeyError,TypeError,OSError):
        parser.exit(2,'Export rejected: check corpus/report provenance, content safety, and destination; raw values withheld.\n')
    print(json.dumps({'scored_rows':manifest['scored_rows'],'exported_rows':manifest['exported_rows'],
        'excluded_rows':len(manifest['excluded_rows']),'network_calls':0,'model_calls':0},indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
