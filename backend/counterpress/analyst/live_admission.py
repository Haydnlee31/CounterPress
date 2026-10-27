"""Durable, shared per-match live-analysis cap. Failures remain charged.

Reserve $0.03 before each two-call turn: <=6k input +700 draft + 2,000 review output tokens.
At conservative $1/$4 per million tokens this is <=$0.0228/turn.
90 turns reserve $2.70 per match, across all viewers, preferences and revisions.
This is a model-usage ceiling, not a meter of shared Azure hosting charges.
"""
import json
from uuid import uuid4

class LiveAllowance:
    RUN_CENTS=3
    MATCH_CENTS=270
    TOTAL_CENTS=1200
    LEASE_SECONDS=60
    def __init__(self,store):self.store=store

    def reserve(self,key,now,match_id,scope,cutoff):
        owner=uuid4().hex
        def change(old):
            state={'spent_cents':old.get('spent_cents',0),'matches':old.get('matches',{}),
                   'jobs':{k:v for k,v in old.get('jobs',{}).items() if v['expires']>now},'history':old.get('history',{})}
            if key in state['jobs']:return state,state['jobs'][key]
            spent=state['matches'].get(match_id,0)
            if spent+self.RUN_CENTS>self.MATCH_CENTS or state['spent_cents']+self.RUN_CENTS>self.TOTAL_CENTS:return state,{'status':'budget_limit'}
            if sum(j['status']=='pending' for j in state['jobs'].values())>=2:return state,{'status':'busy'}
            job={'status':'pending','owner':owner,'expires':now+self.LEASE_SECONDS,'scope':scope,'cutoff':cutoff,'match_id':match_id}
            state['matches'][match_id]=spent+self.RUN_CENTS;state['spent_cents']+=self.RUN_CENTS;state['jobs'][key]=job
            history=[m for m in state['history'].get(scope,[]) if (m['cutoff']['period'],m['cutoff']['elapsed_ms'])<(cutoff['period'],cutoff['elapsed_ms'])]
            return state,{**job,'admitted':True,'history':history[-3:]}
        return self.store.transact(change)

    def finish(self,key,owner,result,now):
        if result is not None and len(json.dumps(result).encode())>16000:result=None
        def change(state):
            job=state.get('jobs',{}).get(key)
            if job and job['owner']==owner and job['status']=='pending' and job['expires']>now:
                state['jobs'][key]={**job,'status':'complete' if result is not None else 'unavailable','expires':now+(2592000 if result is not None else 300),'result':result}
                if result and result.get('messages'):
                    scope=job['scope'];history=state.setdefault('history',{})
                    history[scope]=[m for m in history.get(scope,[]) if m['cutoff']!=job['cutoff']]+[{**m,'cutoff':job['cutoff']} for m in result['messages']]
                    history[scope]=sorted(history[scope],key=lambda m:(m['cutoff']['period'],m['cutoff']['elapsed_ms']))[-6:]
                    # Cost counters never expire; only optional conversation context does.
                    if len(history)>32:
                        for old_scope in list(history):
                            if old_scope!=scope:del history[old_scope];break
            while len(json.dumps(state).encode())>1_200_000:
                victim=next((k for k,j in state.get('jobs',{}).items() if j['status']!='pending' and k!=key),None)
                if victim is None:break
                del state['jobs'][victim]
            return state,None
        self.store.transact(change)
