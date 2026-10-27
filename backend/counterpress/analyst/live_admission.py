"""Durable, shared per-match live-analysis cap. Failures remain charged.

Reserve $0.03 before each two-call turn: <=6k input and 2,000 output tokens per call.
At conservative $1/$4 per million tokens this is <=$0.028/turn.
At most $2.70 is accounted per match across viewers, preferences and revisions.
Fully metered mini-model calls settle conservatively; uncertain calls keep $0.03.
This is a model-usage ceiling, not a meter of shared Azure hosting charges.
"""
import json
import math
from uuid import uuid4


def accounted_cents(result):
    """Conservative settlement only for fully metered, bounded mini-model calls.

    Missing usage, timeout, cancellation and unknown models keep the reservation.
    Rounded UP at $1/$4 per million; no cached-input discount is assumed.
    This is an allowance accounting bound, never an Azure invoice estimate.
    """
    execution=(result or {}).get('execution',{})
    calls=execution.get('per_role_usage',[])
    if execution.get('model')!='gpt-5-mini' or execution.get('review_model')!='gpt-5-mini':return 3
    if type(execution.get('model_calls')) is not int or execution['model_calls'] not in (1,2) or len(calls)!=execution['model_calls']:return 3
    for call in calls:
        if call.get('usage_complete') is False:return 3
        if any(type(call.get(k)) is not int or not 0<call[k]<=limit for k,limit in (('input_tokens',6000),('output_tokens',2000))):return 3
    inputs=sum(c['input_tokens'] for c in calls);outputs=sum(c['output_tokens'] for c in calls)
    if execution.get('input_tokens')!=inputs or execution.get('output_tokens')!=outputs:return 3
    return min(3,max(1,math.ceil((inputs+4*outputs)/10000)))


def settle_completed(state):
    """Idempotent inside the same CAS transaction as admission/finish.

    Retained legacy records can be settled once. Pruned records, unknown costs,
    and failed calls stay charged. Never reset a match's cumulative allowance.
    """
    for job in state.get('jobs',{}).values():
        if job.get('status')!='complete' or job.get('usage_settled'):continue
        charged=accounted_cents(job.get('result'))
        release=3-charged;match=job.get('match_id')
        if state.get('spent_cents',0)<release or state.get('matches',{}).get(match,0)<release:continue
        state['spent_cents']-=release;state['matches'][match]-=release
        state['released_cents']=state.get('released_cents',0)+release
        job.update(usage_settled=True,reserved_cents=3,accounted_cents=charged)


class LiveAllowance:
    RUN_CENTS=3
    MATCH_CENTS=270
    TOTAL_CENTS=1200
    LEASE_SECONDS=60
    def __init__(self,store):self.store=store

    def grant_match_allowance(self,grant_id,match_id,cents,reason):
        """Admin-only operation; no HTTP route. Requires explicit spend approval.

        At most one extra dollar per match. Historical charges and the shared
        total cap remain unchanged; repeated application of a grant is idempotent.
        """
        if not isinstance(match_id,str) or not 1<=len(match_id)<=120 or not isinstance(grant_id,str) or not 1<=len(grant_id)<=80 or type(cents) is not int or not 1<=cents<=100 or not isinstance(reason,str) or not 1<=len(reason)<=240:
            raise ValueError('invalid_allowance_grant')
        def change(state):
            grants=state.setdefault('approved_grants',{})
            record={'match_id':match_id,'cents':cents,'reason':reason}
            if grant_id in grants:
                if grants[grant_id]!=record:raise ValueError('grant_conflict')
                return state,record
            if len(grants)>=32 or sum(g['cents'] for g in grants.values() if g['match_id']==match_id)+cents>100:
                raise ValueError('grant_limit')
            grants[grant_id]=record
            return state,record
        return self.store.transact(change)

    def reserve(self,key,now,match_id,scope,cutoff):
        owner=uuid4().hex
        def change(old):
            settle_completed(old)
            state={'approved_grants':old.get('approved_grants',{}),'spent_cents':old.get('spent_cents',0),'released_cents':old.get('released_cents',0),'matches':old.get('matches',{}),
                   'jobs':{k:v for k,v in old.get('jobs',{}).items() if v['expires']>now},'history':old.get('history',{}),'turns':old.get('turns',{})}
            if key in state['jobs']:return state,state['jobs'][key]
            spent=state['matches'].get(match_id,0)
            approved=sum(g['cents'] for g in state['approved_grants'].values() if g['match_id']==match_id)
            if spent+self.RUN_CENTS>self.MATCH_CENTS+approved or state['spent_cents']+self.RUN_CENTS>self.TOTAL_CENTS:return state,{'status':'budget_limit'}
            if sum(j['status']=='pending' for j in state['jobs'].values())>=2:return state,{'status':'busy'}
            job={'status':'pending','owner':owner,'expires':now+self.LEASE_SECONDS,'scope':scope,'cutoff':cutoff,'match_id':match_id}
            state['matches'][match_id]=spent+self.RUN_CENTS;state['spent_cents']+=self.RUN_CENTS;state['jobs'][key]=job
            history=[m for m in state['history'].get(scope,[]) if (m['cutoff']['period'],m['cutoff']['elapsed_ms'])<(cutoff['period'],cutoff['elapsed_ms'])]
            attempted=[m for m in state['turns'].get(scope,[]) if (m['cutoff']['period'],m['cutoff']['elapsed_ms'])<(cutoff['period'],cutoff['elapsed_ms'])]
            context=sorted(history[-18:]+attempted[-4:],key=lambda m:(m['cutoff']['period'],m['cutoff']['elapsed_ms']))
            return state,{**job,'admitted':True,'history':context}
        return self.store.transact(change)

    def finish(self,key,owner,result,now):
        if result is not None and len(json.dumps(result).encode())>16000:result=None
        def change(state):
            job=state.get('jobs',{}).get(key)
            if job and job['owner']==owner and job['status']=='pending' and job['expires']>now:
                state['jobs'][key]={**job,'status':'complete' if result is not None else 'unavailable','expires':now+(2592000 if result is not None else 300),'result':result}
                settle_completed(state)
                role=(result or {}).get('execution',{}).get('scheduled_role')
                if role in ('control','players','chance','defence'):
                    scope=job['scope'];turns=state.setdefault('turns',{})
                    turns[scope]=[m for m in turns.get(scope,[]) if m['cutoff']!=job['cutoff']]+[{'role':role,'cutoff':job['cutoff'],'attempt_only':True,'text':''}]
                    turns[scope]=sorted(turns[scope],key=lambda m:(m['cutoff']['period'],m['cutoff']['elapsed_ms']))[-4:]
                    if len(turns)>32:
                        for old_scope in list(turns):
                            if old_scope!=scope:del turns[old_scope];break
                if result and result.get('messages'):
                    scope=job['scope'];history=state.setdefault('history',{})
                    history[scope]=[m for m in history.get(scope,[]) if m['cutoff']!=job['cutoff']]+[{**m,'cutoff':job['cutoff'],**({'memory':result['conversation_memory']} if result.get('conversation_memory') else {})} for m in result['messages']]
                    history[scope]=sorted(history[scope],key=lambda m:(m['cutoff']['period'],m['cutoff']['elapsed_ms']))[-18:]
                    # Cost counters never expire; only optional conversation context does.
                    if len(history)>32:
                        for old_scope in list(history):
                            if old_scope!=scope:del history[old_scope];break
            while len(json.dumps(state).encode())>1_200_000:
                victim=next((k for k,j in state.get('jobs',{}).items() if j['status']!='pending' and k!=key),None)
                if victim is not None:
                    del state['jobs'][victim]
                    continue
                old_scope=next((s for s in state.get('history',{}) if not job or s!=job['scope']),None)
                if old_scope is None:break
                del state['history'][old_scope]
                state.get('turns',{}).pop(old_scope,None)
            return state,None
        self.store.transact(change)
