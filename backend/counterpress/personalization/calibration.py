"""Aggregate-only fitting from licensed Wyscout events, rosters and broad roles."""
from collections import Counter, defaultdict
from hashlib import sha256
import json
import math
from random import Random
from statistics import mean, pstdev

VERSION='career-role-calibration-v1'
ROLES={'Goalkeeper':'GK','Defender':'DF','Midfielder':'MF','Forward':'FW'}


def describe(values):
    values=sorted(values)
    if not values: return {'n':0,'mean':0.,'sd':0.,'p10':0.,'p50':0.,'p90':0.}
    return {'n':len(values),'mean':round(mean(values),6),'sd':round(pstdev(values),6),
            **{f'p{q}':round(values[round((len(values)-1)*q/100)],6) for q in (10,50,90)}}


def pass_bucket(start,technique):
    # Wyscout failed-pass endpoints need not be intended targets. Never fit a
    # probability using that post-outcome location: start + declared type only.
    return f'{min(2,int(start[0]/35))}:{technique}'


def pass_type(name):
    return 'cross' if name=='Cross' else 'header' if name=='Head pass' else 'long' if name in ('High pass','Launch') else 'ground'


def shot_bucket(start):
    distance=math.dist(start,(105,34))
    return f'{0 if distance<12 else 1 if distance<20 else 2 if distance<30 else 3}:{int(abs(start[1]-34)<12)}'


def probability(model,kind,start,technique='ground'):
    table=model['pass_probability' if kind=='pass' else 'shot_probability']
    key=pass_bucket(start,technique) if kind=='pass' else shot_bucket(start)
    prior=table['global']['success']/max(1,table['global']['n'])
    cell=table['cells'].get(key,{'n':0,'success':0})
    return max(.01,min(.99,(cell['success']+30*prior)/(cell['n']+30)))


def fit(events,matches,players,seed=20261020):
    ids=sorted(m['wyId'] for m in matches if m['duration']=='Regular')
    Random(seed).shuffle(ids);n=round(.8*len(ids));train=sorted(ids[:n]);held=sorted(ids[n:]);train_set=set(train)
    roles={p['wyId']:ROLES.get(p['role']['name'],'MF') for p in players}
    minutes=Counter();sub_minutes=[];sub_counts=[]
    for match in matches:
        if match['wyId'] not in train_set: continue
        for team in match['teamsData'].values():
            f=team['formation'];starts={p['playerId']:0 for p in f['lineup']};ends={p:90 for p in starts}
            subs=f.get('substitutions') or []
            if not isinstance(subs,list): subs=[]
            sub_counts.append(len([s for s in subs if s['minute']<90]))
            for s in subs:
                at=min(90,s['minute']);ends[s['playerOut']]=at;starts[s['playerIn']]=at;ends[s['playerIn']]=90
                if at<90: sub_minutes.append(at)
            for pid,start in starts.items():minutes[pid]+=max(0,ends.get(pid,90)-start)
    action_counts=[Counter() for _ in range(3)];contexts=defaultdict(Counter);deltas=defaultdict(list)
    role_counts=defaultdict(Counter);individual=defaultdict(Counter);pass_cells=defaultdict(Counter);shot_cells=defaultdict(Counter)
    all_pass=Counter();all_shot=Counter();outcomes=Counter();match_counts=defaultdict(Counter);role_locations=defaultdict(list)
    for e in events:
        if e['matchId'] not in train_set or e['matchPeriod'] not in ('1H','2H') or not e['positions']: continue
        tags={t['id'] for t in e['tags']};role=roles.get(e['playerId'],'MF')
        kind='pass' if e['eventName']=='Pass' else 'shot' if e['eventName']=='Shot' else 'duel' if e['subEventName']=='Ground attacking duel' else 'carry' if e['subEventName'] in ('Acceleration','Touch') else None
        if not kind: continue
        x=e['positions'][0]['x']*1.05;y=e['positions'][0]['y']*.68;z=min(2,int(x/35))
        action_counts[z][kind]+=1;contexts[f'{z}:{int(x>=83)}:{int(abs(y-34)<=14)}'][kind]+=1
        role_counts[role][kind]+=1;individual[e['playerId']][kind]+=1;match_counts[e['matchId']][kind]+=1
        role_locations[role].append((x,y))
        if kind=='pass' and len(e['positions'])>1 and tags&{1801,1802}:
            end=(e['positions'][1]['x']*1.05,e['positions'][1]['y']*.68)
            for axis,delta in [('x',end[0]-x),('y',end[1]-y)]:deltas[f'{z}:{axis}'].append(delta)
            success=int(1801 in tags)
            for cell in (all_pass,pass_cells[pass_bucket((x,y),pass_type(e['subEventName']))]):cell['n']+=1;cell['success']+=success
            individual[e['playerId']]['complete']+=success;match_counts[e['matchId']]['complete']+=success
        if kind=='shot':
            success=int(101 in tags)
            for cell in (all_shot,shot_cells[shot_bucket((x,y))]):cell['n']+=1;cell['success']+=success
            outcome='goal' if success else 'blocked' if 2101 in tags else 'off_target' if tags&set(range(1210,1224)) else 'saved'
            outcomes[outcome]+=1;individual[e['playerId']]['goal']+=success;match_counts[e['matchId']]['goal']+=success
    role_rates={}
    for role in ROLES.values():
        eligible=[p for p in individual if roles.get(p)==role and minutes[p]>=900]
        role_rates[role]={k:describe([individual[p][k]*90/minutes[p] for p in eligible]) for k in ('pass','shot','duel','carry','goal')}
        role_rates[role]['pass_accuracy']=describe([(individual[p]['complete']+30*.8)/(individual[p]['pass']+30) for p in eligible])
    model={'version':VERSION,'seed':seed,'training_match_ids':train,'holdout_match_ids':held,
           'training_event_count':sum(e['matchId'] in train_set for e in events),
           'action_counts':[dict(c) for c in action_counts],'action_contexts':{k:dict(v) for k,v in contexts.items()},
           'pass_deltas':{k:describe(v) for k,v in deltas.items()},'role_action_counts':{k:dict(v) for k,v in role_counts.items()},
           'role_rates':role_rates,'role_locations':{r:{'x':describe([p[0] for p in points]),'y':describe([p[1] for p in points])} for r,points in role_locations.items()},
           'pass_probability':{'global':dict(all_pass),'cells':{k:dict(v) for k,v in pass_cells.items()}},
           'shot_probability':{'global':dict(all_shot),'cells':{k:dict(v) for k,v in shot_cells.items()}},
           'shot_non_goal_outcomes':{k:v for k,v in outcomes.items() if k!='goal'},
           'action_interval_seconds':5400*len(train)/sum(sum(v.values()) for v in action_counts),
           'substitution_minutes':describe(sub_minutes),'substitutions_per_team':describe(sub_counts),
           'source_match_distributions':{k:describe([v[k] for v in match_counts.values()]) for k in ('pass','shot','goal','complete')},
           'shot_hazard_scale':.7}
    return model,evaluate(model,events,roles)


def evaluate(model,events,roles=None):
    held=set(model['holdout_match_ids']);rows=defaultdict(Counter);loss=defaultdict(list);baseline=defaultdict(list)
    bins=defaultdict(lambda:defaultdict(list))
    for e in events:
        if e['matchId'] not in held or e['matchPeriod'] not in ('1H','2H'):continue
        kind='pass' if e['eventName']=='Pass' else 'shot' if e['eventName']=='Shot' else None
        if not kind or not e['positions']:continue
        tags={t['id'] for t in e['tags']};rows[e['matchId']][kind]+=1
        start=(e['positions'][0]['x']*1.05,e['positions'][0]['y']*.68)
        if kind=='pass':
            if len(e['positions'])<2 or not tags&{1801,1802}:continue
            end=(e['positions'][1]['x']*1.05,e['positions'][1]['y']*.68);actual=int(1801 in tags);rows[e['matchId']]['complete']+=actual
        else:end=None;actual=int(101 in tags);rows[e['matchId']]['goal']+=actual
        p=probability(model,kind,start,pass_type(e['subEventName']));table=model['pass_probability' if kind=='pass' else 'shot_probability']['global']
        loss[kind].append((actual-p)**2);baseline[kind].append((actual-table['success']/table['n'])**2)
        bins[kind][str(min(9,int(p*10)))].append((p,actual))
    return {'holdout_matches':len(held),'holdout_distributions':{k:describe([r[k] for r in rows.values()]) for k in ('pass','shot','goal','complete')},
            'brier':{k:{'model':mean(v),'global_baseline':mean(baseline[k]),'n':len(v)} for k,v in loss.items()},
            'reliability':{k:{b:{'n':len(v),'predicted':mean(x[0] for x in v),'observed':mean(x[1] for x in v)} for b,v in cells.items()} for k,cells in bins.items()}}


def main():
    import argparse
    from pathlib import Path
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    paths={k:args.source/f'{k}.json' for k in ('events_England','matches_England','players')}
    data={k:json.loads(v.read_text()) for k,v in paths.items()}
    model,report=fit(data['events_England'],data['matches_England'],data['players'])
    model['provenance']={'authors':'Luca Pappalardo and Emanuele Massucco / Wyscout','license':'CC BY 4.0',
        'urls':['https://doi.org/10.6084/m9.figshare.7770599','https://doi.org/10.6084/m9.figshare.7770422','https://doi.org/10.6084/m9.figshare.7765196'],
        'sha256':{k:sha256(v.read_bytes()).hexdigest() for k,v in paths.items()},'competition':'England 2017/18',
        'changes':'Aggregate fitting only; no source identities or event sequences in generated careers.'}
    args.output.mkdir(parents=True,exist_ok=True)
    for name,value in [('calibration.json',model),('calibration-report.json',report)]:
        (args.output/name).write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps({'training_matches':len(model['training_match_ids']),'held_out':len(model['holdout_match_ids']),**report['brier']}))

if __name__=='__main__':main()
