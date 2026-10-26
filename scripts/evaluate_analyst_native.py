"""Source-anchored native Analyst acceptance benchmark; offline unless --azure.

Six preselected windows and two adversarial Editor checks; at most32 reserved
model calls and80 admission cents. Model quality requires recorded human review.
No retries or inference while preparing/validating the corpus.
"""
from __future__ import annotations
import argparse
import asyncio
from collections import Counter
from datetime import datetime,timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from counterpress.analyst.admission import Allowance,SQLiteStore
from counterpress.analyst.contracts import AnalystRequest
from counterpress.analyst.provider import FoundryAnalyst
from counterpress.analyst.service import build_snapshot,build_dispatch_packet
from counterpress.assistant.evaluation import AttemptBudget
from counterpress.personalization.service import CareerService
from counterpress.personalization.store import DataStore
from integrations.analyst_foundry.contracts import Selection,parse_packet

CASES=[
 {'id':'archive_box_growth','match_id':'wyscout-2058017','period':1,'elapsed_ms':2581000,
  'expected':{'club_id':'northport','current_shots':3,'previous_shots':0,'box_shots':3,'score':[2,1]},
  'expectation':'Northport are creating more close-range opportunities while trailing. Distinguish recent threat from the actual score; do not infer defensive shape.',
  'roles':['chance','control']},
 {'id':'activity_without_shots','match_id':'synthetic-32fe41c5d304ce68d7d9','period':1,'elapsed_ms':630000,
  'expected':{'club_id':'eastbridge','on_ball_actions':35,'all_on_ball_actions':49,'current_shots':0,'final_third_entries':1,'score':[0,0]},
  'expectation':'Eastbridge dominate recorded action share but have little penetration and no shot. They DO have a final-third entry; saying zero entries or measured time-possession is wrong.',
  'roles':['control']},
 {'id':'turnover_into_equalizer','match_id':'synthetic-32fe41c5d304ce68d7d9','period':1,'elapsed_ms':2096000,
  'expected':{'club_id':'eastbridge','current_shots':2,'previous_shots':0,'score':[1,1],
   'chain_ids':['a00498','a00499','a00500'],'regain_to_shot_ms':7975},
  'expectation':'An incomplete Northport pass, Eastbridge recovery and shot created an equalizer. Explain the transition and restored score parity; do not claim a coordinated press.',
  'roles':['defence','chance']},
 {'id':'focused_player_link','match_id':'synthetic-32fe41c5d304ce68d7d9','period':2,'elapsed_ms':2314000,'focus_player_id':'np10','language':'zh-Hans',
  'expected':{'club_id':'northport','current_shots':1,'previous_shots':2,'score':[2,2],
   'focus_player_id':'np10','focus_passes':6,'focus_shots':1,
   'chain_ids':['a01164','a01165','a01166','a01167','a01168'],'regain_to_shot_ms':13860},
  'expectation':'In Simplified Chinese, relate Isaac Lane’s involvement to a linked transition ending in his off-target shot. Do not claim he scored, or confuse prefix totals with the current window.',
  'roles':['players','defence']},
 {'id':'early_quiet_window','match_id':'wyscout-2058007','period':1,'elapsed_ms':91000,
  'expected':{'club_id':'eastbridge','current_shots':0,'previous_shots':0,'score':[0,0]},
  'expectation':'Abstention or restrained early observations are acceptable. No complete five-minute comparison exists; do not claim sustained dominance, a tactical turning point or a completed trend.',
  'roles':[],'abstention_acceptable':True},
 {'id':'other_archive_chances','match_id':'wyscout-2058007','period':1,'elapsed_ms':1081000,
  'expected':{'club_id':'eastbridge','current_shots':3,'previous_shots':0,'box_shots':2,'score':[0,0]},
  'expectation':'Eastbridge’s increase in shots includes closer opportunities but has not produced a goal. Do not label the geometric estimate calibrated xG or attribute unavailable player speeds.',
  'roles':['chance']},
]
RUBRIC={
 'grounded':'0=wrong entity/time/fact or unsupported physical/causal claim;1=all claims supported or explicitly qualified.',
 'pattern':'0=only narrates an event/stat;1=connects evidence into the expected meaningful pattern, or appropriately abstains in the quiet case.',
 'consequence':'0=no supported significance;1=explains relevance to score, opportunity, progression or player contribution.',
 'alternative':'0=missing/canned/unsupported counterstory;1=plausible bounded alternative or uncertainty tied to this evidence.',
 'watch_next':'0=vague/forecast/order;1=specific observable next check linked to the pattern.',
 'audience':'0=wrong language, unreadable or ignores player focus;1=appropriate language/depth/focus.',
}


def encode(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False)


def write_private(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    os.chmod(path.parent,0o700)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w')as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)


def independent_facts(store,case):
    """Recount original source rows, not production reducer outputs or signals."""
    cutoff=(case['period'],case['elapsed_ms']);latest={}
    for e in store.events(case['match_id']):
        if (e.available_period,e.available_ms)>cutoff:continue
        old=latest.get(e.event_id)
        if old is None or e.revision>old.revision:latest[e.event_id]=e
    rows=[e for e in latest.values()if not e.retracted and (e.period,e.elapsed_ms)<=cutoff]
    p,t=cutoff;cur=[e for e in rows if e.period==p and max(0,t-300000)<e.elapsed_ms<=t]
    old=[e for e in rows if e.period==p and max(0,t-600000)<e.elapsed_ms<=max(0,t-300000)]
    c=case['expected']['club_id'];own=[e for e in cur if e.club_id==c]
    def onball(e):return e.kind in('pass','shot')or e.kind=='carry' and e.outcome in{'controlled','complete','completed','established','successful'}
    shots=[e for e in own if e.kind=='shot' and e.outcome!='own_goal']
    result={'club_id':c,'current_shots':len(shots),'previous_shots':sum(e.kind=='shot' and e.outcome!='own_goal' and e.club_id==c for e in old),
        'box_shots':sum(bool(e.start and e.start.x>=88.5 and 13.84<=e.start.y<=54.16)for e in shots),
        'on_ball_actions':sum(onball(e)for e in own),'all_on_ball_actions':sum(onball(e)for e in cur),
        'final_third_entries':sum(bool(e.kind=='pass'and e.outcome in('complete','completed')and e.start and e.end and e.start.x<70<=e.end.x)for e in own),
        'score':[sum(e.goal_for==club for e in rows)for club in('eastbridge','northport')]}
    if case.get('focus_player_id'):
        pid=case['focus_player_id'];result.update(focus_player_id=pid,focus_passes=sum(e.kind=='pass'and e.player_id==pid for e in cur),focus_shots=sum(e.kind=='shot'and e.player_id==pid for e in cur))
    if 'chain_ids'in case['expected']:
        byid={e.event_id:e for e in rows};chain=[byid[eid]for eid in case['expected']['chain_ids']]
        assert chain[0].kind=='pass'and chain[0].outcome=='incomplete'and chain[1].kind=='recovery'and chain[-1].kind=='shot'
        assert chain[0].club_id!=chain[1].club_id and chain[1].club_id==chain[-1].club_id
        assert 0<=chain[1].elapsed_ms-chain[0].elapsed_ms<=3000
        holder=chain[1].player_id
        for e in chain[2:]:
            assert e.player_id==holder and not e.restart
            if e.kind=='pass':assert e.outcome in('complete','completed')and e.recipient_id;holder=e.recipient_id
        result.update(chain_ids=[e.event_id for e in chain],regain_to_shot_ms=chain[-1].elapsed_ms-chain[1].elapsed_ms)
    assert all(result[k]==v for k,v in case['expected'].items()),f'Source anchors changed: {case["id"]}'
    return {k:result[k]for k in case['expected']}


def prepare():
    career=CareerService(DataStore(ROOT/'fixtures/personalization'));prepared=[]
    for case in CASES:
        facts=independent_facts(career.store,case)
        request=AnalystRequest(cutoff={'period':case['period'],'elapsed_ms':case['elapsed_ms']},language=case.get('language','en'),focus_player_id=case.get('focus_player_id'))
        snapshot=build_snapshot(career,case['match_id'],request);packet=build_dispatch_packet(snapshot)
        parse_packet(encode(packet))
        prepared.append({'case':case,'request':request,'snapshot':snapshot,'packet':packet,'independent_facts':facts})
    return prepared


def evaluation_remaining():
    path=ROOT/'var/footie-evaluation-budget.sqlite3'
    if not path.exists():return {'hourly_remaining':240,'daily_remaining':600}
    with sqlite3.connect(f'file:{path}?mode=ro',uri=True)as db:
        now=time.time();hour=db.execute('SELECT count(*) FROM attempts WHERE at>?',(now-3600,)).fetchone()[0];day=db.execute('SELECT count(*) FROM attempts WHERE at>?',(now-86400,)).fetchone()[0]
    return {'hourly_remaining':max(0,240-hour),'daily_remaining':max(0,600-day)}


def review_scores(path,results):
    if path is None:return {'status':'pending_human_review','rubric':RUBRIC}
    review=json.loads(path.read_text());scored=[]
    for case in CASES:
        row=review.get(case['id']);run=next(r for r in results if r['case_id']==case['id'])
        if not isinstance(row,dict)or set(RUBRIC)-row.keys()or any(type(row[k])is not int or row[k]not in(0,1)for k in RUBRIC)or not isinstance(row.get('rationale'),str)or len(row['rationale'].strip())<20:
            raise ValueError('Each human review needs six binary ratings and a concrete rationale')
        if run['status']in('error','not_run','unavailable'):raise ValueError('Cannot quality-score a missing execution')
        scored.append({'case_id':case['id'],'scores':{k:row[k]for k in RUBRIC},'rationale':row['rationale']})
    return {'status':'human_review_recorded','cases':scored,'points':sum(sum(r['scores'].values())for r in scored),'maximum_points':36,'is_statistical_accuracy_estimate':False}


def adversarial_inputs(packet):
    club='northport';metric_id=f'current:{club}:shots';eid=next(e['id']for e in packet['evidence']if e['club_id']==club)
    common={'role':'chance','headline':'A changing attack','alternative':'The spell may not persist.','watch_next':'Watch where the next attacks finish.','evidence_ids':[eid],'metric_ids':[metric_id],'confidence':'high'}
    return [
        ('wrong_team',{**common,'explanation':'Eastbridge are creating more close-range opportunities than before.'}),
        ('unsupported_off_ball',{**common,'explanation':'Northport’s defensive line has dropped and their fullbacks are staying narrow.'}),
    ]


async def editor_check(provider,manifest,packet,reading):
    import httpx
    reference=manifest['agents']['synthesis']
    checked=FoundryAnalyst(provider.endpoint,reference['name'],reference['version'],provider.manifest_id)
    url=f'{checked.endpoint}/agents/{checked.name}/endpoint/protocols/openai/responses?api-version=v1'
    async with provider.credential()as credential:
        token=await credential.get_token('https://ai.azure.com/.default')
        async with httpx.AsyncClient(timeout=httpx.Timeout(40,connect=10),follow_redirects=False)as client:
            payload={'input':encode({'readings':[reading],'packet':packet,'focus_player_id':None,'depth':'analyst'}),'store':False,'stream':False,'max_output_tokens':1500,
                'agent_reference':{'type':'agent_reference',**manifest['agents']['synthesis']}}
            async with client.stream('POST',url,headers={'Authorization':'Bearer '+token.token,'Content-Type':'application/json'},json=payload)as response:
                response.raise_for_status();body=bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body)>65536:raise ValueError('Editor response too large')
            data=json.loads(body)
            if data.get('status')!='completed':raise ValueError('Editor response incomplete')
            text=''.join(part.get('text','')for item in data.get('output',[])if item.get('type')=='message'for part in item.get('content',[])if part.get('type')=='output_text')
            parsed=Selection.model_validate_json(text)
            return {'decision':parsed.model_dump(),'rejected':parsed.accepted_roles==[]and parsed.selected_role is None,'usage':data.get('usage',{})}


async def run_live(args,prepared,raw_dir):
    from azure.identity.aio import AzureCliCredential
    remaining=evaluation_remaining()
    if min(remaining.values())<32:raise ValueError('Insufficient existing evaluation allowance for conservative32-call reservation; no ceiling raised')
    private=json.loads(args.private_config.read_text());manifest=json.loads(args.manifest.read_text())
    # Main product provider and exact pinned native version, local CLI identity.
    provider=FoundryAnalyst(private['project_endpoint'],manifest['coordinator']['name'],manifest['coordinator']['version'],manifest['manifest_id'],credential_factory=lambda:AzureCliCredential(process_timeout=10))
    allowance=Allowance(SQLiteStore(ROOT/'var/analyst-local-allowance.sqlite3'))
    budget=AttemptBudget(ROOT/'var/footie-evaluation-budget.sqlite3',32,hourly_limit=240,daily_limit=600)
    results=[];adversarial=[];reserved_cents=0
    async def admitted(case_id,calls,operation):
        nonlocal reserved_cents
        key=sha256(encode({'benchmark':args.run_id,'case':case_id,'manifest':manifest['manifest_id']}).encode()).hexdigest()
        job=allowance.reserve(key,time.time())
        if not job.get('admitted'):return {'case_id':case_id,'status':job['status']}
        reserved_cents+=Allowance.RUN_CENTS
        value=None;started=time.monotonic()
        try:
            for _ in range(calls):
                if not budget.reserve():raise RuntimeError('Evaluation allowance exhausted; no provider call sent')
            value=await operation()
            return {'case_id':case_id,'status':value.get('status','complete'),'seconds':round(time.monotonic()-started,3),'result':value}
        except Exception as exc:
            return {'case_id':case_id,'status':'error','seconds':round(time.monotonic()-started,3),'error_type':type(exc).__name__}
        finally:
            allowance.finish(key,job['owner'],value,time.time())
    try:
        for item in prepared:
            case_id=item['case']['id']
            outcome=await admitted(case_id,5,lambda item=item:provider.analyze(item['snapshot'],item['request']))
            write_private(raw_dir/(case_id+'.json'),{'case':item['case'],'packet':item['packet'],'outcome':outcome})
            results.append({k:v for k,v in outcome.items()if k!='result'}|{'execution':outcome.get('result',{}).get('execution'),
                'reading_count':len(outcome.get('result',{}).get('readings',[])),'roles':[r['role']for r in outcome.get('result',{}).get('readings',[])]})
            print(json.dumps({'case_id':case_id,'status':outcome['status'],'seconds':outcome.get('seconds')}),flush=True)
        base=prepared[0]['packet']
        for name,reading in adversarial_inputs(base):
            outcome=await admitted('adversarial_'+name,1,lambda reading=reading:editor_check(provider,manifest,base,reading))
            write_private(raw_dir/('adversarial_'+name+'.json'),{'reading':reading,'outcome':outcome})
            adversarial.append({'case_id':name,'status':outcome['status'],'rejected':outcome.get('result',{}).get('rejected'),'seconds':outcome.get('seconds')})
    finally:budget.close()
    return {'cases':results,'adversarial':adversarial,'evaluation_calls_reserved':budget.used,'admission_cents_reserved':reserved_cents,'manifest_id':manifest['manifest_id']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--azure',action='store_true',help='Explicit paid execution only AFTER parent confirms native smoke passed')
    parser.add_argument('--private-config',type=Path,default=ROOT/'var/analyst-foundry-private.json')
    parser.add_argument('--manifest',type=Path,default=ROOT/'var/analyst-foundry-manifest.json')
    parser.add_argument('--review',type=Path,help='Manually authored scored review JSON after inspecting raw replies')
    parser.add_argument('--review-existing',type=Path,help='Attach manual scoring to an EXISTING public execution report, without model calls')
    parser.add_argument('--run-id',default=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
    args=parser.parse_args()
    if args.review_existing:
        if args.azure or args.review is None:parser.error('--review-existing requires --review and prohibits --azure')
        report=json.loads(args.review_existing.read_text())
        if report.get('mode')!='azure':parser.error('Review only an existing Azure execution report')
        report['quality_review']=review_scores(args.review,report['cases'])
        out=args.review_existing.with_name(args.review_existing.stem+'-reviewed.json')
        out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({'status':'review_recorded','cloud_calls':0,'reviewed_report':str(out)}))
        return
    if args.review:parser.error('Use --review-existing to score saved responses without calling models again')
    if not args.run_id.replace('-','').replace('_','').isalnum():parser.error('Use an alphanumeric run ID')
    prepared=prepare();raw_dir=ROOT/'var/analyst-native-benchmark'/args.run_id
    if args.azure and raw_dir.exists():raise ValueError('Run ID already used; preserve prior raw evidence')
    report={'benchmark':'analyst-native-source-anchored-v1','prepared_at':datetime.now(timezone.utc).isoformat(),'mode':'azure'if args.azure else'offline_preflight',
        'source_manifest_sha256':sha256((ROOT/'fixtures/personalization/manifest.json').read_bytes()).hexdigest(),
        'cases_preselected_before_model_results':True,'not_random_or_statistically_representative':True,
        'maximum_model_calls_reserved':32,'maximum_admission_cents_reserved':80,'existing_evaluation_remaining':evaluation_remaining(),
        'prepared_cases':[{'case_id':i['case']['id'],'match_id':i['case']['match_id'],'cutoff':i['request'].cutoff.model_dump(),'expected':i['independent_facts'],
            'expectation':i['case']['expectation'],'packet_chars':len(encode(i['packet']))}for i in prepared]}
    if args.azure:report.update(asyncio.run(run_live(args,prepared,raw_dir)))
    else:report['cases']=[{'case_id':i['case']['id'],'status':'not_run'}for i in prepared]
    report['quality_review']=review_scores(args.review,report['cases'])
    out=ROOT/'docs/verification'/f'analyst-native-benchmark-{args.run_id}.json';out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'complete','mode':report['mode'],'cases':len(prepared),'cloud_calls':report.get('evaluation_calls_reserved',0),'public_report':str(out.relative_to(ROOT)),'quality_review':report['quality_review']['status']}))


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(json.dumps({'status':'stopped','error_type':type(exc).__name__,'detail':'Benchmark stopped safely; private provider error text is suppressed.'}))
        raise SystemExit(1)from None
