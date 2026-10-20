"""Aggregate source benchmarks and population checks, separate from accounting."""
from collections import Counter,defaultdict
from statistics import mean

ROLES={'Goalkeeper':'GK','Defender':'DF','Midfielder':'MF','Forward':'FW'}


def source_population(events,matches,players,ids):
    ids=set(ids);roles={p['wyId']:ROLES[p['role']['name']] for p in players}
    groups=defaultdict(list)
    for e in events:
        if e['matchId'] in ids and e['matchPeriod'] in ('1H','2H'):groups[(e['matchId'],e['matchPeriod'])].append(e)
    totals=Counter();goal_roles=Counter();assist_roles=Counter();situations=defaultdict(Counter);team_scorers=defaultdict(Counter)
    for group in groups.values():
        corner=None
        for e in sorted(group,key=lambda e:e['eventSec']):
            tags={t['id'] for t in e['tags']};role=roles.get(e['playerId'],'MF')
            if e['subEventName']=='Corner':corner=e;totals['corners']+=1
            if 301 in tags:totals['assists']+=1;assist_roles[role]+=1
            if e['eventName']!='Shot' and e['subEventName'] not in ('Penalty','Free kick shot'):continue
            kind='penalty' if e['subEventName']=='Penalty' else 'free_kick' if e['subEventName']=='Free kick shot' else 'corner' if corner and corner['teamId']==e['teamId'] and 0<e['eventSec']-corner['eventSec']<=15 else 'open_play'
            totals['shots']+=1;situations[kind]['shots']+=1;situations[kind]['role_'+role]+=1
            if 101 in tags:
                totals['player_goals']+=1;goal_roles[role]+=1;situations[kind]['goals']+=1
                team_scorers[e['teamId']][e['playerId']]+=1
            corner=None
    totals['goals']=sum(t['score'] for m in matches if m['wyId'] in ids for t in m['teamsData'].values())
    return {'matches':len(ids),'per_match':{k:round(v/len(ids),6) for k,v in totals.items()},
        'average_top_scorer_team_share':mean(max(c.values())/sum(c.values()) for c in team_scorers.values()),
        'assisted_goal_share':totals['assists']/totals['goals'],
        'goal_role_share':{r:goal_roles[r]/sum(goal_roles.values()) for r in ROLES.values()},
        'assist_role_share':{r:assist_roles[r]/sum(assist_roles.values()) for r in ROLES.values()},
        'situations':{k:{'shots_per_match':v['shots']/len(ids),'conversion':v['goals']/v['shots'],
                         'shot_roles':{r:v['role_'+r]/v['shots'] for r in ROLES.values()}} for k,v in situations.items()}}


def population(rows,players):
    roles={p.player_id:p.role for p in players};goals=Counter();assists=Counter();counts=[];individual=defaultdict(Counter)
    team_scorers=defaultdict(Counter)
    clubs={p.player_id:p.club_id for p in players}
    for row in rows:
        summary=row.get('summary',row)
        counts.append({'goals':sum(summary['score'].values()),'shots':sum(p['shots'] for p in summary['players'].values()),
                       'passes':sum(p['passes'] for p in summary['players'].values())})
        for pid,s in summary['players'].items():
            goals[roles[pid]]+=s['goals'];assists[roles[pid]]+=s['assists'];individual[pid].update(s)
            team_scorers[(row.get('fixture',{}).get('season','population'),clubs[pid])][pid]+=s['goals']
    total_goals=sum(c['goals'] for c in counts)
    team_shares=[max(c.values())/sum(c.values()) for c in team_scorers.values() if sum(c.values())]
    return {'matches':len(rows),'per_match':{k:round(mean(c[k] for c in counts),6) for k in counts[0]},
        'assisted_goal_share':sum(assists.values())/max(1,total_goals),
        'goal_role_share':{r:goals[r]/max(1,sum(goals.values())) for r in ROLES.values()},
        'assist_role_share':{r:assists[r]/max(1,sum(assists.values())) for r in ROLES.values()},
        'average_top_scorer_team_share':mean(team_shares) if team_shares else 0,
        'maximum_player_goals_per90_900_minutes':max((s['goals']*90/s['minutes'] for s in individual.values() if s['minutes']>=900),default=0)}


def checks(observed,target):
    # Broad, declared tolerances allow a different fictional league and sampling
    # variation. They are not tests that every match looks like the mean.
    checks={}
    for metric,tolerance in [('goals',.15),('shots',.2)]:
        actual=observed['per_match'][metric];expected=target['per_match'][metric]
        checks[metric+'_per_match']={'actual':actual,'target':expected,'relative_tolerance':tolerance,'passed':abs(actual/expected-1)<=tolerance}
    for group,tolerance in [('goal_role_share',.085),('assist_role_share',.10)]:
        for role in ('DF','MF','FW'):
            actual=observed[group][role];expected=target[group][role]
            checks[group+'_'+role]={'actual':actual,'target':expected,'absolute_tolerance':tolerance,'passed':abs(actual-expected)<=tolerance}
    actual=observed['assisted_goal_share'];expected=target['assisted_goal_share']
    checks['assisted_goal_share']={'actual':actual,'target':expected,'absolute_tolerance':.09,'passed':abs(actual-expected)<=.09}
    actual=observed['average_top_scorer_team_share'];expected=target['average_top_scorer_team_share']
    checks['top_scorer_team_share']={'actual':actual,'target':expected,'absolute_tolerance':.12,'passed':abs(actual-expected)<=.12}
    return checks
