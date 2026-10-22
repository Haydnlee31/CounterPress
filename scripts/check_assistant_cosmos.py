"""Explicit Cosmos admission verification in an isolated partition; no AI calls.

Run seed then verify in a fresh process with the same scope. Private Cosmos
settings are supplied through the existing server environment. Test record stays
isolated for audit; it does not touch match data or the production control item.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
from threading import Barrier
from time import time

from azure.cosmos.exceptions import CosmosHttpResponseError

from counterpress.assistant.admission import Admission, CosmosAdmissionStore
from counterpress.assistant.narrative import StoryPlan
from counterpress.assistant.research import ResearchResult
from counterpress.assistant.service import blank
from counterpress.storage import configured_store
from check_editorial_cosmos import RacingContainer


def scoped(container,scope):
    store=CosmosAdmissionStore(container)
    store.partition='verify-assistant-'+scope
    return Admission(store)


def seed(container,scope):
    admission=scoped(container,scope)
    try:container.read_item(item='control',partition_key=admission.store.partition)
    except CosmosHttpResponseError as exc:
        if exc.status_code!=404:raise
    else:raise ValueError('Use a fresh verification scope')
    now=time();barrier=Barrier(2);conflicts=[]
    def reserve(_):return scoped(RacingContainer(container,barrier,conflicts),scope).reserve('duplicate',now)
    with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(reserve,range(2)))
    assert sorted(s for s,_ in outcomes)==['pending','reserved'] and conflicts
    owner=next(j.owner for s,j in outcomes if s=='reserved')
    receipt=ResearchResult(blank('stats',player_ids=['rh09']),StoryPlan(lead='c0',supporting=[]),'a'*64,{},0,0,0)
    admission.finish('duplicate',owner,now+1,receipt)
    status,cached=scoped(container,scope).reserve('duplicate',now+2)
    assert status=='done' and cached.receipt.evidence_id=='a'*64
    for i in range(9):
        status,job=scoped(container,scope).reserve('attempt-'+str(i),now+3+i)
        assert status=='reserved'
        admission.finish('attempt-'+str(i),job.owner,now+3+i)
    assert scoped(container,scope).reserve('over-limit',now+15)[0]=='hourly_limit'
    return {'status':'passed','real_conflict_statuses':sorted(conflicts),
        'duplicate_admitted_once':True,'typed_receipt_restored':True,
        'reserved_provider_slots':20,'quota_enforced':True,'external_model_calls':0,
        'scope':'isolated verification partition','clock':'controlled timestamps around current time'}


def verify(container,scope):
    admission=scoped(container,scope)
    state=admission.store.transact(lambda state:state)
    assert len(state.reservations)==10
    assert state.jobs['duplicate'].receipt.selection.lead=='c0'
    # Check at the recorded test instant, so this is reproducible after the hour.
    assert admission.reserve('fresh-process',max(state.reservations)+1)[0]=='hourly_limit'
    return {'status':'passed','fresh_process_quota_preserved':True,
        'typed_receipt_restored':True,'external_model_calls':0,
        'clock':'recorded test timestamp','scope':'isolated verification partition'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=['seed','verify'])
    parser.add_argument('--scope',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not re.fullmatch('[a-z0-9-]{1,32}',args.scope):parser.error('Use a bounded lowercase verification scope')
    if args.output.exists():parser.error('Preserve previous results; choose a new output path')
    if os.environ.get('COUNTERPRESS_STORAGE')!='cosmos':parser.error('This explicit check requires Cosmos storage')
    try:
        container=configured_store(':memory:').container
        report=(seed if args.phase=='seed' else verify)(container,args.scope)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2)+'\n')
        print('PASS: Cosmos assistant '+args.phase+'; isolated record, zero model calls.')
        return 0
    except Exception as exc:
        cause=exc;status=None
        while cause:
            status=getattr(cause,'status_code',None) or status
            cause=cause.__context__
        report={'status':'failed','phase':args.phase,'error_type':type(exc).__name__,
            'http_status':status,'external_model_calls':0,'scope':'isolated verification partition'}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2)+'\n')
        print(f'FAIL: Cosmos assistant {args.phase}; {type(exc).__name__}, HTTP {status}. Private diagnostics withheld.')
        return 1


if __name__=='__main__':raise SystemExit(main())
