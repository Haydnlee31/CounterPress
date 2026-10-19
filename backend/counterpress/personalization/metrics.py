"""Deterministic accounting shared by career, match and live views."""
from collections import Counter, defaultdict
from hashlib import sha256
import json
import math
from .contracts import Action, Fixture, MatchRecord

RULE_VERSION='career-metrics-v1'


def goal_milestone(count):
    return count in (1,25,75) or count>0 and count%10==0
COUNT_FIELDS=('appearances','starts','minutes','goals','own_goals','assists','shots','shots_on_target','shots_off_target',
              'shots_blocked','passes','passes_completed','passes_unknown','duels','duels_won','duels_unknown','recoveries',
              'saves','goals_conceded','clean_sheets','key_passes','xg_shots','xpass_passes','xpass_completed',
              'located_passes','flight_passes','flight_shots')
SUM_FIELDS=('xg','expected_completions','pass_distance_m','pass_speed_kmh_sum','shot_speed_kmh_sum')


def digest(events):
    return sha256(json.dumps([e.model_dump(mode='json') for e in events],sort_keys=True,separators=(',',':')).encode()).hexdigest()


def select_events(events,cutoff=None):
    latest={}
    for e in events:
        if cutoff is not None and (e.available_period,e.available_ms)>cutoff:continue
        if e.event_id not in latest or latest[e.event_id].revision<e.revision:latest[e.event_id]=e
    return sorted((e for e in latest.values() if not e.retracted),key=lambda e:(e.period,e.elapsed_ms,e.occurrence_order))


def empty():return {k:0 for k in (*COUNT_FIELDS,*SUM_FIELDS)}


def action_metrics(event):
    distance=math.dist((event.start.x,event.start.y),(event.end.x,event.end.y)) if event.start and event.end else None
    speed=round(distance/(event.flight_ms/1000)*3.6,3) if distance is not None and event.flight_ms else None
    return {'pass_distance_m':round(distance,3) if event.kind=='pass' and distance is not None else None,
        'pass_difficulty':round(1-event.completion_probability,6) if event.completion_probability is not None else None,
        'mean_ball_speed_kmh':speed,'mean_shot_speed_kmh':speed if event.kind=='shot' else None,
        'speed_basis':event.telemetry_basis,'expected_goal_probability':event.expected_goal_probability,
        'model_version':event.estimate_version}


def add_stats(rows):
    result=empty()
    for row in rows:
        for k in result:result[k]+=row.get(k,0)
    return {k:round(v,6) if isinstance(v,float) else v for k,v in result.items()}


def rates(stats):
    def divide(n,d,scale=1):return round(n/d*scale,4) if d else None
    known=stats['passes']-stats['passes_unknown']
    return {'goals_per90':divide(stats['goals'],stats['minutes'],90),
        'assists_per90':divide(stats['assists'],stats['minutes'],90),
        'goal_involvements_per90':divide(stats['goals']+stats['assists'],stats['minutes'],90),
        'pass_accuracy_pct':divide(stats['passes_completed'],known,100),
        'shot_conversion_pct':divide(stats['goals'],stats['shots'],100),
        'shot_accuracy_pct':divide(stats['shots_on_target'],stats['shots'],100),
        'duel_win_pct':divide(stats['duels_won'],stats['duels']-stats['duels_unknown'],100),
        'passing_above_expected_per100':divide(stats['xpass_completed']-stats['expected_completions'],stats['xpass_passes'],100),
        'mean_pass_distance_m':divide(stats['pass_distance_m'],stats['located_passes']),
        'mean_pass_speed_kmh':divide(stats['pass_speed_kmh_sum'],stats['flight_passes']),
        'mean_shot_speed_kmh':divide(stats['shot_speed_kmh_sum'],stats['flight_shots'])}


def reduce_record(record: MatchRecord,cutoff=None,window_start=None):
    fixture=record.fixture;events=select_events(record.events,cutoff);players={a.player_id:empty() for a in fixture.appearances}
    maps={pid:Counter() for pid in players};clubs={c:empty() for c in (fixture.home_id,fixture.away_id)}
    score={c:0 for c in clubs};evidence=[];pass_chain=None
    # Unknown future events never enter either the metrics or evidence list.
    elapsed=sum(fixture.period_lengths_ms) if cutoff is None else min(sum(fixture.period_lengths_ms),cutoff[1]+(fixture.period_lengths_ms[0] if cutoff[0]==2 else 0))
    start_clock=0 if window_start is None else window_start[1]+(fixture.period_lengths_ms[0] if window_start[0]==2 else 0)
    for a in fixture.appearances:
        minutes=max(0,min(elapsed,a.end_ms)-max(a.start_ms,start_clock))/60000
        players[a.player_id].update(appearances=int(minutes>0),starts=int(a.starter and minutes>0),minutes=round(minutes,6))
    for e in events:
        row=players[e.player_id];team=clubs[e.club_id];provider=None
        def inc(key,value=1):row[key]+=value;team[key]+=value
        if window_start is not None and (e.period,e.elapsed_ms)<=window_start:
            # Retain lead-in pass context for a shot just inside the window.
            if pass_chain and (e.period!=pass_chain.period or e.club_id!=pass_chain.club_id or e.restart):pass_chain=None
            if e.kind=='pass':pass_chain=e if e.outcome in ('completed','complete') and e.recipient_id else None
            elif e.kind in ('shot','recovery') or e.kind=='duel' and e.outcome=='lost':pass_chain=None
            continue
        if e.start and e.kind in ('pass','shot','carry','duel','recovery'):
            maps[e.player_id][f'{min(11,int(e.start.x/8.75))}:{min(7,int(e.start.y/8.5))}']+=1
        if pass_chain and (e.period!=pass_chain.period or e.club_id!=pass_chain.club_id or e.restart or e.kind=='recovery'):
            pass_chain=None
        if e.kind=='pass':
            inc('passes')
            if e.outcome in ('completed','complete'):inc('passes_completed')
            elif e.outcome not in ('incomplete',):inc('passes_unknown')
            if e.start and e.end:
                inc('located_passes');inc('pass_distance_m',math.dist((e.start.x,e.start.y),(e.end.x,e.end.y)))
            if e.completion_probability is not None:
                inc('expected_completions',e.completion_probability);inc('xpass_passes')
                inc('xpass_completed',int(e.outcome in ('completed','complete')))
            pass_chain=e if e.outcome in ('completed','complete') and e.recipient_id else None
        elif e.kind=='shot' and e.outcome!='own_goal':
            inc('shots')
            if e.outcome in ('goal','saved','on_target'):inc('shots_on_target')
            if e.outcome in ('off_target','woodwork'):inc('shots_off_target')
            if e.outcome=='blocked':inc('shots_blocked')
            if e.expected_goal_probability is not None:inc('xg',e.expected_goal_probability);inc('xg_shots')
            provider=None
            if pass_chain and pass_chain.recipient_id==e.player_id and e.elapsed_ms-pass_chain.elapsed_ms<=15000 and not e.penalty:
                provider=pass_chain
                players[provider.player_id]['key_passes']+=1;clubs[e.club_id]['key_passes']+=1
            if e.outcome=='saved' and e.goalkeeper_id:
                players[e.goalkeeper_id]['saves']+=1
                keeper_club=next(a.club_id for a in fixture.appearances if a.player_id==e.goalkeeper_id);clubs[keeper_club]['saves']+=1
            pass_chain=None
        elif e.kind=='duel':
            inc('duels');inc('duels_won',int(e.outcome=='won'))
            inc('duels_unknown',int(e.outcome not in ('won','lost','draw')))
            if e.opponent_id:
                other=next(a.club_id for a in fixture.appearances if a.player_id==e.opponent_id)
                players[e.opponent_id]['duels']+=1;clubs[other]['duels']+=1
                players[e.opponent_id]['duels_won']+=int(e.outcome=='lost');clubs[other]['duels_won']+=int(e.outcome=='lost')
                players[e.opponent_id]['duels_unknown']+=int(e.outcome not in ('won','lost','draw'));clubs[other]['duels_unknown']+=int(e.outcome not in ('won','lost','draw'))
            if e.outcome=='lost':pass_chain=None
        elif e.kind=='recovery' and not e.restart:inc('recoveries')
        if e.goal_for:
            score[e.goal_for]+=1
            if e.goal_for==e.club_id:inc('goals')
            else:inc('own_goals')
            assisted=None
            if provider and e.goal_for==e.club_id:
                assisted=provider.player_id;players[assisted]['assists']+=1;clubs[e.club_id]['assists']+=1
            evidence.append({'event_id':e.event_id,'revision':e.revision,'period':e.period,'elapsed_ms':e.elapsed_ms,
                'available_period':e.available_period,'available_ms':e.available_ms,'player_id':e.player_id,
                'club_id':e.club_id,'goal_for':e.goal_for,'assist_id':assisted,
                'assist_event_id':provider.event_id if assisted else None,'source_reference':e.source_reference})
        if e.flight_ms and e.start and e.end:
            speed=math.dist((e.start.x,e.start.y),(e.end.x,e.end.y))/(e.flight_ms/1000)*3.6
            inc('flight_passes' if e.kind=='pass' else 'flight_shots')
            inc('pass_speed_kmh_sum' if e.kind=='pass' else 'shot_speed_kmh_sum',speed)
    for club,row in clubs.items():
        opponent=fixture.away_id if club==fixture.home_id else fixture.home_id
        row['appearances']=int(elapsed>start_clock);row['starts']=row['appearances'];row['minutes']=round((elapsed-start_clock)/60000,6)
        row['goals']=score[club]
        row['goals_conceded']=score[opponent];row['clean_sheets']=int(cutoff is None and score[opponent]==0)
    # Team-on-pitch goals conceded for each appearance, independent of player blame.
    for a in fixture.appearances:
        conceded=sum(g['goal_for']!=a.club_id and a.start_ms<=g['elapsed_ms']+(fixture.period_lengths_ms[0] if g['period']==2 else 0)<a.end_ms for g in evidence)
        players[a.player_id]['goals_conceded']=conceded
        players[a.player_id]['clean_sheets']=int(cutoff is None and conceded==0 and players[a.player_id]['minutes']>=60)
    return {'players':{p:add_stats([s]) for p,s in players.items()},'clubs':{p:add_stats([s]) for p,s in clubs.items()},
        'score':score,'heatmaps':{pid:dict(c) for pid,c in maps.items()},'goals':evidence,'event_count':sum(window_start is None or (e.period,e.elapsed_ms)>window_start for e in events),
        'rule_version':RULE_VERSION,'coverage':{'event_locations':sum(sum(m.values()) for m in maps.values()),
            'tracking':'unavailable','ball_speed':'authored_physics' if any(e.flight_ms for e in events) else 'unavailable'}}
