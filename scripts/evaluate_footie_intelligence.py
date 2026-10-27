"""Independent intelligence acceptance checks; local lookup by default.

No response oracle is derived from the implementation under evaluation. Exact
anchors are hand-authored. --azure is explicit, bounded and records provider use.
A repeated/tuned suite is regression evidence, never unseen model accuracy.
"""
import argparse
from collections import Counter
from contextlib import ExitStack
import math
import os
from unittest.mock import patch
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import time

from counterpress.assistant.contracts import AskRequest
from counterpress.assistant.service import AssistantService
from counterpress.personalization.service import CareerService
from counterpress.personalization.store import DataStore

ROOT=Path(__file__).resolve().parents[1]
CORPUS=ROOT/'fixtures/assistant/intelligence_questions.json'


TIMING_STAGES={'initial','context','route','query','tool','followup','synthesize','auth','provider_http'}
TIMING_ROLES={'orchestrator','match','career'}
TIMING_STATUSES={'ok','error','cancelled'}


def safe_stage_timings(value):
    """Diagnostic timing metadata only; never persist arbitrary provider strings."""
    if not isinstance(value,(list,tuple)):return []
    result=[]
    for item in value[:100]:
        if not isinstance(item,dict):continue
        if not all(isinstance(item.get(key),str) for key in ('stage','role','status')):continue
        if (item.get('stage') not in TIMING_STAGES or item.get('role') not in TIMING_ROLES
                or item.get('status') not in TIMING_STATUSES):continue
        if not all(isinstance(item.get(key),(int,float)) and not isinstance(item[key],bool)
                   and math.isfinite(item[key]) and 0<=item[key]<=300000 for key in ('started_ms','duration_ms')):continue
        result.append({key:item[key] for key in ('stage','role','started_ms','duration_ms','status')})
    return result


def observed_multiagent(config,budget):
    from evaluate_footie_multiagent import ObservedMultiAgent
    class TimedObserver(ObservedMultiAgent):
        async def research(self,service,request,reserve):
            try:
                result=await super().research(service,request,reserve)
            except BaseException as exc:
                self.execution['stage_timings']=safe_stage_timings(getattr(exc,'stage_timings',()))
                raise
            self.execution['stage_timings']=safe_stage_timings(getattr(result,'stage_timings',()))
            return result
    return TimedObserver(config,budget)


class EvaluationApp:
    """One app/loop, with an isolated observer for each sequential test request."""
    def __init__(self,career,*,single_agent=False,model_calls_per_hour=None):
        if model_calls_per_hour is not None and (type(model_calls_per_hour) is not int or not 1<=model_calls_per_hour<=80):
            raise ValueError('Isolated evaluation API allowance must be between 1 and 80')
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from counterpress.assistant.api import install_assistant
        class Dispatcher:
            max_requests=2 if single_agent else 4
            deadline_seconds=12 if single_agent else 24
            workflow='agent' if single_agent else 'multiagent'
            current=None
            async def research(self,service,request,reserve):
                if self.current is None:raise RuntimeError('Evaluation observer missing')
                return await self.current.research(service,request,reserve)
        self.dispatcher=Dispatcher()
        app=FastAPI()
        # The isolated app must admit the approved invocation allowance; the
        # persistent evaluator ledger remains the hourly/daily authority. Scope
        # this override to app construction so production/environment settings
        # are unchanged, and keep the same API limiter for every warm request.
        if model_calls_per_hour is None:install_assistant(app,lambda:career,researcher=self.dispatcher)
        else:
            with patch.dict(os.environ,{'COUNTERPRESS_ASSISTANT_CALLS_PER_HOUR':str(model_calls_per_hour),'COUNTERPRESS_USAGE_CAPS':'on'}):
                install_assistant(app,lambda:career,researcher=self.dispatcher)
        self.client=TestClient(app)
    def __enter__(self):
        self.client.__enter__()
        return self
    def __exit__(self,*args):return self.client.__exit__(*args)
    def ask(self,request,observer):
        self.dispatcher.current=observer
        try:return self.client.post('/api/fan/assistant/ask',json=request)
        finally:self.dispatcher.current=None


class ObservedSingleAgent:
    """Adapt the existing two-turn ResearchAgent to the same result accounting.

    It uses the same service and typed Plan tool as the multi-agent evaluator,
    but retains its production two-provider-call/one-tool-call limit. This is
    a comparison of existing products, not an equal-budget ablation.
    """
    max_requests=2
    deadline_seconds=12
    workflow='agent'

    def __init__(self,config,budget):
        from evaluate_footie import ObservedResearcher
        self.inner=ObservedResearcher(config,budget)
        self.execution={'requests':0,'roles':[],'plans':[],'usage':{},'completed_result':False}

    async def research(self,service,request,reserve):
        completed=False
        try:
            result=await self.inner.research(service,request,reserve)
            completed=True
            return result
        finally:
            self.execution={'requests':self.inner.requests,'roles':['analyst'] if self.inner.attempted else [],
                'plans':[self.inner.raw] if self.inner.raw else [],'usage':self.inner.usage,
                'tools':self.inner.tools,'completed_result':completed,
                'unreported_usage_attempts':self.inner.requests-self.inner.reported_requests}


def walk(value):
    if isinstance(value,dict):
        yield value
        for item in value.values():yield from walk(item)
    elif isinstance(value,(list,tuple)):
        for item in value:yield from walk(item)


def contains(actual,expected):
    """Check independently authored nested scope fields, allowing other metadata."""
    return (isinstance(actual,dict) and all(k in actual and contains(actual[k],v) for k,v in expected.items())
            if isinstance(expected,dict) else actual==expected)


def score(case, answer, duration_ms, execution=None, store=None):
    expected=case['expect'];facts=answer.get('facts',[]);checks={}
    checks['status']=answer.get('status')==expected['status']
    if 'analysis' in expected:
        plans=[answer.get('plan',{})]+(execution or {}).get('plans',[])
        checks['analysis']=any(p.get('analysis')==expected['analysis'] for p in plans)
    if expected.get('no_facts'):checks['no_facts']=not facts
    if expected.get('no_replay'):
        checks['no_replay']=not any(a.get('highlight') or 'replay' in str(a.get('href','')) for a in answer.get('actions',[]))
    if expected.get('required_subject'):
        checks['subject']=any(f.get('subject_id')==expected['required_subject'] for f in facts)
    for i,anchor in enumerate(expected.get('anchors',[])):
        checks[f'anchor_{i}']=any(all(contains(f.get('scope',{}),v) if k=='scope_contains' else f.get(k)==v
            for k,v in anchor.items()) for f in facts)
    for metric in expected.get('forbidden_nonnull_metrics',[]):
        checks[f'no_{metric}']=all(f.get('value') is None for f in facts if f.get('metric')==metric)
    if expected.get('evidence_event_id'):
        checks['selected_event']=any(item.get('event_id')==expected['evidence_event_id']
            for fact in facts for item in walk(fact.get('evidence',{})))
    evidence_ids={item['event_id'] for fact in facts for item in walk(fact.get('evidence',{})) if 'event_id' in item}
    if expected.get('evidence_event_ids'):
        checks['required_evidence']=set(expected['evidence_event_ids'])<=evidence_ids
    if expected.get('forbidden_evidence_event_ids'):
        checks['forbidden_evidence']=not set(expected['forbidden_evidence_event_ids'])&evidence_ids
    for metric in expected.get('null_metrics',[]):
        checks['null_'+metric]=any(f.get('metric')==metric and f.get('value') is None for f in facts)
    cutoff=expected.get('max_event')
    if cutoff:
        limit=(cutoff['period'],cutoff['elapsed_ms'])
        refs=[item for fact in facts for item in walk(fact.get('evidence',{}))]
        checks['no_future_evidence']=all(
            (item['period'],item['elapsed_ms'])<=limit
            for item in refs if isinstance(item.get('period'),int) and isinstance(item.get('elapsed_ms'),int))
        checks['no_future_availability']=all(
            (item['available_period'],item['available_ms'])<=limit
            for item in refs if isinstance(item.get('available_period'),int) and isinstance(item.get('available_ms'),int))
    if expected.get('history_before_kickoff'):
        baselines=[f for f in facts if f.get('scope',{}).get('window')=='completed_appearances_before_kickoff']
        checks['historical_baseline_present']=bool(baselines)
        if store is not None and baselines:
            mid=case['request']['match_id'];kickoff=store.row(mid)['kickoff']
            checks['history_before_kickoff']=all(f['scope'].get('as_of')==kickoff
                and all(ref['match_id']!=mid and store.row(ref['match_id'])['kickoff']<kickoff
                        for ref in f.get('evidence',{}).get('matches',[])) for f in baselines)
            checks['baseline_sample']=all(3<=len(f.get('evidence',{}).get('matches',[]))<=5 for f in baselines)
        else:checks['history_before_kickoff']=False
    if expected.get('requires_window_comparison'):
        # Independently require two intervals in the visual or fact scopes. The
        # same interval repeated for several measures does not satisfy this.
        intervals={(item.get('period'),item.get('start_ms'),item.get('end_ms')) for item in walk(answer)
            if isinstance(item.get('start_ms'),int) and isinstance(item.get('end_ms'),int)}
        checks['two_windows']=len(intervals)>=2
        checks['equal_completed_windows']=(len(intervals)==2 and len({end-start for _,start,end in intervals})==1
            and len({period for period,_,_ in intervals})==1
            and sorted(intervals)[0][2]==sorted(intervals)[1][1]
            and all(end>start and (not cutoff or (period,end)<=(cutoff['period'],cutoff['elapsed_ms']))
                    for period,start,end in intervals))
    checks['facts_for_supported']=bool(facts) if case['bucket']=='supported' else True
    if execution is not None and case['bucket']=='supported':
        checks['model_completed']=bool(execution.get('completed_result')) and answer.get('mode')=='azure_agent'
    return {'id':case['id'],'bucket':case['bucket'],'journey':case['journey'],
            'passed':all(checks.values()),'checks':checks,'duration_ms':duration_ms,
            'status':answer.get('status'),'mode':answer.get('mode','local_lookup'),
            'question':case.get('request',{}).get('question'), 'title':answer.get('title'), 'text':answer.get('text',[]),
            'narrative':answer.get('narrative'), 'visual':answer.get('visual'),
            'plan':answer.get('plan'), 'facts':facts, 'actions':answer.get('actions',[]),
            'execution':execution,'fallback':answer.get('fallback_reason')}


def percentile(values,fraction):
    import math
    return sorted(values)[max(0,math.ceil(len(values)*fraction)-1)] if values else None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--azure',action='store_true',help='Explicitly permit bounded paid model calls')
    parser.add_argument('--warm-app',action='store_true',help='Reuse one local app/client/event loop; first request is included, no paid priming')
    parser.add_argument('--single-agent',action='store_true',help='Use the existing two-turn ResearchAgent; requires --azure')
    parser.add_argument('--corpus',type=Path,default=CORPUS,help='Independently authored corpus; hashed in report')
    parser.add_argument('--case',action='append',dest='case_ids')
    parser.add_argument('--max-attempts',type=int,default=80)
    parser.add_argument('--label',choices=['baseline','first_holdout','regression'],required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.single_agent and not args.azure:parser.error('--single-agent requires --azure')
    if args.warm_app and not args.azure:parser.error('--warm-app requires --azure')
    if args.output.exists():parser.error('Choose a new report path; earlier scores must be preserved')
    if not 1<=args.max_attempts<=80:parser.error('This evaluator allows at most 80 provider calls per run')
    corpus_path=args.corpus.resolve()
    corpus=json.loads(corpus_path.read_text());cases=corpus['cases']
    if len({c['id'] for c in cases})!=len(cases):parser.error('Duplicate case IDs')
    if args.case_ids:
        if set(args.case_ids)-{c['id'] for c in cases}:parser.error('Unknown case ID')
        cases=[c for c in cases if c['id'] in args.case_ids]
    for case in cases:AskRequest.model_validate(case['request'])
    # Resolve package root, not cwd: a frozen older backend can be benchmarked
    # through PYTHONPATH using this same independent scorer and immutable corpus.
    import counterpress.assistant.service as service_module
    import counterpress.adaptation.azure as azure_module
    source_root=Path(service_module.__file__).parent
    sources=[Path(__file__),corpus_path,ROOT/'fixtures/personalization/manifest.json',
        Path(azure_module.__file__),ROOT/'scripts/evaluate_footie.py',ROOT/'scripts/evaluate_footie_multiagent.py',
        *sorted(source_root.glob('*.py')),
        *sorted((source_root.parent/'personalization').glob('*.py'))]
    fingerprints={str(p):sha256(p.read_bytes()).hexdigest() for p in sources}
    store=DataStore(ROOT/'fixtures/personalization');budget=None;config=None
    if args.azure:
        from counterpress.assistant.evaluation import AttemptBudget
        from counterpress.adaptation.azure import load_config
        from run_footie_local import local_model_settings
        try:
            local_model_settings(ROOT/'.env');config=load_config()
        except ValueError:
            parser.error('Azure configuration invalid; values withheld')
        if config is None:parser.error('Azure configuration missing; values withheld')
        budget=AttemptBudget(ROOT/'var/footie-evaluation-budget.sqlite3',args.max_attempts,hourly_limit=240,daily_limit=600)
    rows=[]
    sessions=ExitStack();warm=None;app_startup_ms=None
    try:
        if args.warm_app:
            app_started=time.monotonic()
            warm=sessions.enter_context(EvaluationApp(CareerService(store),single_agent=args.single_agent,model_calls_per_hour=args.max_attempts))
            app_startup_ms=round((time.monotonic()-app_started)*1000)
        for case in cases:
            service=AssistantService(CareerService(store));started=time.monotonic();execution=None
            try:
                if args.azure:
                    observer=ObservedSingleAgent(config,budget) if args.single_agent else observed_multiagent(config,budget)
                    if warm:response=warm.ask(case['request'],observer)
                    else:
                        with EvaluationApp(service.career,single_agent=args.single_agent,model_calls_per_hour=args.max_attempts) as session:
                            response=session.ask(case['request'],observer)
                    if response.status_code!=200:raise RuntimeError(f'HTTP_{response.status_code}')
                    answer=response.json();execution=observer.execution
                else:
                    request=AskRequest.model_validate(case['request']);plan=service.local_plan(request)
                    with store.lock:answer=service.answer(plan,request)
                    answer['plan']=plan.model_dump()
                row=score(case,answer,round((time.monotonic()-started)*1000),execution,store)
            except Exception as exc:
                # No arbitrary provider/database error content in evaluation output.
                row={'id':case['id'],'bucket':case['bucket'],'journey':case['journey'],'passed':False,
                     'checks':{'request_completed':False},'error_type':type(exc).__name__,
                     'duration_ms':round((time.monotonic()-started)*1000),'execution':execution}
            rows.append(row)
            failed=','.join(k for k,v in row['checks'].items() if not v)
            print(f'{"PASS" if row["passed"] else "FAIL"} {case["id"]} {failed}',flush=True)
            if budget and budget.denied:break
    finally:
        sessions.close()
        attempts=budget.used if budget else 0
        exhausted=budget.denied if budget else False
        if budget:budget.close()
        store.close()
    changed=[str(p) for p in sources if sha256(p.read_bytes()).hexdigest()!=fingerprints[str(p)]]
    by_bucket={b:{'passed':sum(r['passed'] for r in rows if r['bucket']==b),
                  'total':sum(r['bucket']==b for r in rows)} for b in ('supported','clarify','unsupported')}
    complete=len(rows)==len(cases) and not exhausted and not changed
    status='incomplete' if not complete else 'passed' if all(r['passed'] for r in rows) else 'failed'
    usage=Counter()
    for row in rows:usage.update((row.get('execution') or {}).get('usage',{}))
    report={'version':1,'created_at':datetime.now(timezone.utc).isoformat(),'evaluation_status':status,
        'mode':('azure_single_agent' if args.single_agent else 'azure_multiagent') if args.azure else 'local_lookup','label':args.label,
        'workflow_limits':{'provider_calls_per_request':2 if args.single_agent else 4 if args.azure else 0,
            'deadline_seconds':12 if args.single_agent else 24 if args.azure else None,
            'comparison_note':'Existing single-agent has two provider calls and one tool call; multiagent has four provider calls with delegation and optional follow-up. This is not an equal-budget ablation.'},
        'measurement':{'app_lifecycle':'shared_app' if args.warm_app else 'fresh_app_per_case' if args.azure else 'local_service_per_case',
            'app_startup_ms':app_startup_ms,'isolated_api_hourly_limit':args.max_attempts if args.azure else None,
            'persisted_ledger_hourly_limit':240 if args.azure else None,'persisted_ledger_daily_limit':600 if args.azure else None,
            'invocation_attempt_limit':args.max_attempts if args.azure else 0,'paid_warmup_requests':0,'first_request_included':True,
            'timing_note':'Request wall time includes local API processing. Shared-app startup is reported separately. Nested/parallel stage times must not be summed.'},
        'source_sha256':fingerprints,'sources_changed_during_run':changed,
        'corpus_path':str(corpus_path),'corpus_version':corpus.get('version'),'corpus_sha256':sha256(corpus_path.read_bytes()).hexdigest(),'requested_cases':len(cases),
        'model_attempts':attempts,'tokens':dict(usage),'bucket_scores':by_bucket,
        'latency_ms':{'p50':percentile([r['duration_ms'] for r in rows],.5),'p95':percentile([r['duration_ms'] for r in rows],.95)},
        'supported_latency_ms':{'p50':percentile([r['duration_ms'] for r in rows if r['bucket']=='supported'],.5),
                                'p95':percentile([r['duration_ms'] for r in rows if r['bucket']=='supported'],.95)},
        'limitations':['Automatic checks assess authored factual/scope anchors, not all prose correctness or human usefulness.',
            'Local lookup results do not measure model routing quality. No single-agent superiority claim is established.',
            'Cases used to tune implementation must be reported as regression on repeat.'],
        'results':rows}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'status':status,'buckets':by_bucket,'model_attempts':attempts,'tokens':dict(usage)},indent=2))
    return 0 if status=='passed' else 2 if status=='incomplete' else 1


if __name__=='__main__':raise SystemExit(main())
