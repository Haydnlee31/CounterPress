"""Aggregate-calibrated full matches. No raw action sequences are replayed."""
from collections import Counter, defaultdict
from hashlib import sha256
import json
import math
from random import Random
from statistics import mean, pstdev

from counterpress.domain.models import (Actor, CarryDetails, DuelDetails, Event, InitialState,
    MatchTime, PassDetails, PitchPosition, RecoveryDetails, ShotDetails)
from counterpress.fixture import Pitch, PossessionFixture, Team

VERSION = 'aggregate-possession-v1'


def category(e):
    if e['eventName'] == 'Pass': return 'pass'
    if e['eventName'] == 'Shot': return 'shot'
    if e['subEventName'] == 'Ground attacking duel': return 'duel'
    if e['subEventName'] in ('Acceleration', 'Touch'): return 'carry'
    return None


def zone(x): return min(2, int(x / 35))

def summary(values):
    return {'n':len(values),'mean':round(mean(values),5) if values else 0,
            'sd':round(pstdev(values),5) if values else 0}


def metrics(records):
    passes=[e for e in records if e['eventName']=='Pass']
    shots=[e for e in records if e['eventName']=='Shot']
    return {'passes':len(passes),'pass_completion':sum(any(t['id']==1801 for t in e['tags']) for e in passes)/max(1,len(passes)),
            'shots':len(shots),'goals':sum(any(t['id']==101 for t in e['tags']) for e in shots)}


def fit(records, match_ids):
    """Fit only listed matches; aggregate counts and moments, never store source trajectories."""
    selected=[e for e in records if e['matchId'] in set(match_ids)]
    contexts=defaultdict(Counter)
    counts=[Counter() for _ in range(3)];deltas=defaultdict(list);completion=defaultdict(Counter)
    shots=defaultdict(Counter);segments=[];segment=0;previous=None
    for e in sorted(selected,key=lambda e:(e['matchId'],e['matchPeriod'],e['eventSec'],e['id'])):
        kind=category(e)
        if not kind or not e['positions']:continue
        x=e['positions'][0]['x']*1.05;y=e['positions'][0]['y']*.68;z=zone(x)
        counts[z][kind]+=1
        contexts[f'{z}:{int(x>=83)}:{int(abs(y-34)<=14)}'][kind]+=1
        tags={t['id'] for t in e['tags']}
        group=(e['matchId'],e['matchPeriod'],e['teamId'])
        if group!=previous:
            if segment:segments.append(segment)
            segment=0;previous=group
        segment+=1
        if kind=='pass' and len(e['positions'])>1:
            dx=e['positions'][1]['x']*1.05-x;dy=e['positions'][1]['y']*.68-y
            deltas[f'{z}:x'].append(dx);deltas[f'{z}:y'].append(dy)
            bucket=f'{z}:{int(math.hypot(dx,dy)>=25)}'
            if tags & {1801,1802}:completion[bucket]['complete' if 1801 in tags else 'incomplete']+=1
        if kind=='shot':
            bucket=f'{int(x>=83)}:{int(abs(y-34)<=14)}'
            outcome='goal' if 101 in tags else 'blocked' if 2101 in tags else 'off_target' if tags & set(range(1210,1224)) else 'saved'
            shots[bucket][outcome]+=1
    if segment:segments.append(segment)
    total=sum(sum(c.values()) for c in counts)
    return {'version':VERSION,'fit_match_ids':match_ids,'source_event_count':len(selected),
            'action_counts':[dict(c) for c in counts],'action_contexts':dict(contexts),'pass_deltas':{k:summary(v) for k,v in deltas.items()},
            'pass_outcomes':dict(completion),'shot_outcomes':dict(shots),
            'controlled_action_runs':summary(segments),'action_interval_seconds':5400*len(match_ids)/total,
            'match_metrics':[metrics([e for e in selected if e['matchId']==mid]) for mid in match_ids]}


def generate_full(model, seed):
    if model['version']!=VERSION:raise ValueError('Unsupported calibration model')
    rng=Random(seed)
    digest=sha256(json.dumps({'model':model,'seed':seed},sort_keys=True).encode()).hexdigest()
    match_id='synthetic-'+digest[:20]
    roster={t:tuple(f'{prefix}{n:02}' for n in range(1,12)) for t,prefix in [('eastbridge','eb'),('northport','np')]}
    teams=tuple(Team(team_id=t,name=t.title(),player_ids=ids) for t,ids in roster.items())
    events=[];score={t:0 for t in roster};holder=Actor(team_id='eastbridge',player_id='eb09');ball=(52.5,34.0)
    # Small per-match style differences; these are design controls, not learned player ability.
    directness={t:rng.uniform(-1.5,1.5) for t in roster}
    period=1;elapsed=0
    def other(t):return 'northport' if t=='eastbridge' else 'eastbridge'
    def point(p):return PitchPosition(x=round(max(0,min(105,p[0])),3),y=round(max(0,min(68,p[1])),3))
    def actor(t,exclude=None,keeper=False):
        ids=[p for p in roster[t] if p!=exclude and (keeper or not p.endswith('01'))]
        return Actor(team_id=t,player_id=roster[t][0] if keeper else rng.choice(ids))
    def emit(action):
        i=len(events)+1
        events.append(Event(match_id=match_id,event_id=f'a{i:05}',revision=1,source_delivery_sequence=i,
            occurrence_order=i,occurred_at=MatchTime(period=period,elapsed_ms=elapsed),
            available_at=MatchTime(period=period,elapsed_ms=elapsed+100),actor=holder,position=point(ball),action=action))
    def travel_time():
        if not events:return 0
        previous=events[-1]
        end=getattr(previous.action,'end_position',None)
        if end is None:return 0
        speed={'pass':25,'carry':7,'shot':35}.get(previous.action.kind,25)
        return math.ceil(math.hypot(end.x-previous.position.x,end.y-previous.position.y)/speed*1000)
    def switch(origin='open_play',restart=None,keeper=False):
        nonlocal holder,ball,elapsed
        old=holder.team_id;holder=actor(other(old),keeper=keeper)
        ball=restart if restart else (105-ball[0],68-ball[1]);elapsed+=max(700,travel_time())
        emit(RecoveryDetails(kind='recovery',from_team_id=old,control='established',origin=origin))
    for period in (1,2):
        elapsed=1000
        if period==2:
            if holder.team_id!='northport':switch('restart',(52.5,34.0))
            else:ball=(52.5,34.0)
        emit(CarryDetails(kind='carry',end_position=point(ball)))
        # Two 45-minute halves. Stop creating possessions near the boundary; never squeeze a finish.
        while elapsed<2690000:
            interval=model['action_interval_seconds']
            elapsed+=max(1200,travel_time(),int(rng.gammavariate(3,interval/3)*1000))
            if elapsed>2690000:break
            x,y=ball;z=zone(x);counts=model['action_counts'][z]
            context=model['action_contexts'].get(f'{z}:{int(x>=83)}:{int(abs(y-34)<=14)}',{})
            weights=[context.get(k,0)+10*counts.get(k,0)/sum(counts.values()) for k in ('pass','carry','duel','shot')]
            # Trailing teams take slightly more risks late in a match.
            chasing=period==2 and elapsed>1800000 and score[holder.team_id]<score[other(holder.team_id)]
            weights[3]*=model.get('shot_hazard_scale',1.0)*(1.12 if chasing else 1)
            if x<65:weights[3]=0
            kind=rng.choices(('pass','carry','duel','shot'),weights)[0]
            if kind=='pass':
                dx=model['pass_deltas'][f'{z}:x'];dy=model['pass_deltas'][f'{z}:y']
                # Truncated displacement sampling avoids clipping normal tails onto touchlines.
                for _ in range(50):
                    ex=x+rng.gauss(dx['mean']+directness[holder.team_id],dx['sd'])
                    ey=y+rng.gauss(dy['mean'],dy['sd'])
                    if 1<ex<104 and 1<ey<67:break
                end=point((max(1,min(104,ex)),max(1,min(67,ey))))
                bucket=f'{z}:{int(math.hypot(end.x-x,end.y-y)>=25)}';c=model['pass_outcomes'].get(bucket,{})
                prob=(c.get('complete',0)+8)/(sum(c.values())+10)
                completed=0<end.x<105 and 0<end.y<68 and rng.random()<prob
                recipient=actor(holder.team_id,holder.player_id) if completed else None
                emit(PassDetails(kind='pass',outcome='completed' if completed else 'incomplete',end_position=end,recipient=recipient))
                ball=(end.x,end.y)
                if completed:holder=recipient
                else:
                    outside=end.x in (0,105) or end.y in (0,68)
                    if outside:elapsed+=rng.randint(7000,13000)
                    switch('restart' if outside else 'open_play')
            elif kind=='carry':
                end=point((x+rng.uniform(-2,8),y+rng.uniform(-5,5)))
                emit(CarryDetails(kind='carry',end_position=end));ball=(end.x,end.y)
            elif kind=='duel':
                opponent=actor(other(holder.team_id));lost=rng.random()<.48
                emit(DuelDetails(kind='duel',opponent=opponent,outcome='lost' if lost else 'won'))
                if lost:
                    old=holder.team_id;holder=opponent;ball=(105-x,68-y);elapsed+=700
                    emit(RecoveryDetails(kind='recovery',from_team_id=old,control='established',origin='open_play'))
            else:
                bucket=f'{int(x>=83)}:{int(abs(y-34)<=14)}';c=model['shot_outcomes'].get(bucket,{})
                outcomes=('goal','saved','off_target','blocked')
                # Global empirical prior stabilizes sparse shot zones.
                global_counts=Counter()
                for values in model['shot_outcomes'].values():global_counts.update(values)
                weights=[c.get(k,0)+10*global_counts[k]/max(1,sum(global_counts.values())) for k in outcomes]
                outcome=rng.choices(outcomes,weights)[0]
                endpoint=point((105,rng.uniform(31,37) if outcome!='off_target' else rng.choice((25,43))))
                keeper=actor(other(holder.team_id),keeper=True) if outcome=='saved' else None
                rebound=point((max(65,x-rng.uniform(1,8)),y+rng.uniform(-4,4))) if outcome=='blocked' else None
                emit(ShotDetails(kind='shot',outcome=outcome,end_position=rebound or endpoint,goalkeeper=keeper,rebound_position=rebound))
                if outcome=='goal':
                    score[holder.team_id]+=1;elapsed+=rng.randint(18000,30000);switch('restart',(52.5,34.0))
                elif outcome=='blocked':
                    ball=(rebound.x,rebound.y)
                    if rng.random()<.5:switch()
                    else:holder=actor(holder.team_id)
                else:
                    ball=(endpoint.x,endpoint.y);elapsed+=rng.randint(6000,12000)
                    switch('restart',(5.5,34.0),keeper=True)
    feed=PossessionFixture(schema_version='1.0',synthetic=True,match_id=match_id,
        pitch=Pitch(length_m=105,width_m=68,coordinates='actor_team_attacks_positive_x'),teams=teams,
        initial_state=InitialState(at=MatchTime(period=1,elapsed_ms=0),score={'eastbridge':0,'northport':0},controlled_possession_team_id='eastbridge'),events=tuple(events))
    return feed


def generated_metrics(feed):
    passes=[e for e in feed.events if e.action.kind=='pass'];shots=[e for e in feed.events if e.action.kind=='shot']
    return {'passes':len(passes),'pass_completion':sum(e.action.outcome=='completed' for e in passes)/max(1,len(passes)),
            'shots':len(shots),'goals':sum(e.action.outcome=='goal' for e in shots)}


def main():
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--seed',type=int,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    feed=generate_full(json.loads(args.model.read_text()),args.seed)
    with args.output.open('x') as output:output.write(feed.model_dump_json(indent=2)+'\n')
    print(json.dumps({'match_id':feed.match_id,'events':len(feed.events),**generated_metrics(feed)}))

if __name__=='__main__':main()
