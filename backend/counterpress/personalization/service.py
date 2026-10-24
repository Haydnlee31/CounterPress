"""Bounded evidence-bearing reads for future profiles, fan modes and agents."""
from collections import Counter,defaultdict
from datetime import datetime
from hashlib import sha256
import json
from .contracts import Fixture,MatchRecord
from .metrics import RULE_VERSION,add_stats,rates,select_events,goal_milestone,reduce_record
from .coverage import metric_coverage,covered_rates


def match_card(row,summary):
    f=json.loads(row['fixture'])
    return {k:f[k] for k in ('match_id','kickoff','season','home_id','away_id','competition','featured','source_kind','minutes_basis')}|{
        'period_lengths_ms':f['period_lengths_ms'],'score':summary['score'],'replay_available':f['featured'],'event_count':summary['event_count']}


class CareerService:
    def __init__(self,store):self.store=store

    @staticmethod
    def historical_cutoff(row,before):
        if before is None:return None
        f=json.loads(row['fixture']);delta=int((datetime.fromisoformat(before.replace('Z','+00:00'))-datetime.fromisoformat(f['kickoff'].replace('Z','+00:00'))).total_seconds()*1000)
        # Fifteen-minute halftime is an explicit wall-clock mapping convention.
        if delta<sum(f['period_lengths_ms'])+900000:return False
        return (2,delta-f['period_lengths_ms'][0]-900000)

    def profile(self,subject,kind='player',season=None,before=None):
        registry=self.store.players if kind=='player' else self.store.clubs
        if subject not in registry:raise KeyError(subject)
        entity=registry[subject];club=entity.club_id
        rows=self.store.rows(club=club,season=season,before=before)
        key='players' if kind=='player' else 'clubs'
        entries=[];heat=Counter();seasons=defaultdict(list);goals=[]
        for row in rows:
            at=self.historical_cutoff(row,before)
            if at is False:continue
            summary=self.store.summary(row['id'],at,completed=at is not None);stats=summary[key].get(subject)
            if not stats or not stats['appearances']:continue
            entries.append((row,summary,stats));seasons[row['season']].append(stats)
            if kind=='player':heat.update(summary['heatmaps'].get(subject,{}))
            else:
                for pid,h in summary['heatmaps'].items():
                    if self.store.players[pid].club_id==club:heat.update(h)
            goals.extend({'match_id':row['id'],**g} for g in summary['goals'] if (g['player_id']==subject and g['goal_for']==club if kind=='player' else g['goal_for']==club))
        total=add_stats(s for _,_,s in entries);recent=add_stats(s for _,_,s in entries[:5])
        coverage=metric_coverage([(json.loads(r['fixture']),s) for r,_,s in entries])
        refs=[{'match_id':r['id'],'event_digest':self.store.evidence_digest(r['id'],self.historical_cutoff(r,before))} for r,_,_ in entries]
        baseline=sha256(json.dumps({'stats':total,'matches':refs},sort_keys=True).encode()).hexdigest()
        by_season=[]
        for season_name,stats in sorted(seasons.items(),reverse=True):
            sc=metric_coverage([(json.loads(r['fixture']),v) for r,_,v in entries if r['season']==season_name])
            by_season.append({'season':season_name,'totals':add_stats(stats),'rates':covered_rates(add_stats(stats),sc),'metric_coverage':sc})
        insights=[]
        if total['goals']:
            best=max(by_season,key=lambda s:s['totals']['goals'])
            insights.append({'type':'best_scoring_season','subject_id':subject,'season':best['season'],'goals':best['totals']['goals'],
                'match_ids':[r['id'] for r,_,_ in entries if r['season']==best['season']],'rule_version':RULE_VERSION})
        if recent['minutes']>=180 and total['minutes']:
            insights.append({'type':'recent_scoring_rate','matches':min(5,len(entries)),'minutes':recent['minutes'],
                'goals':recent['goals'],'goals_per90':rates(recent)['goals_per90'],'career_goals_per90':rates(total)['goals_per90'],
                'match_ids':[r['id'] for r,_,_ in entries[:5]],'rule_version':RULE_VERSION})
        record=None
        if kind=='club':
            results=Counter('draw' if s['score'][club]==s['score'][r['away'] if r['home']==club else r['home']] else 'win' if s['score'][club]>s['score'][r['away'] if r['home']==club else r['home']] else 'loss' for r,s,_ in entries)
            record={'wins':results['win'],'draws':results['draw'],'losses':results['loss']}
        return {'subject':entity.model_dump(mode='json',exclude={'involvement','passing','finishing'}),'scope':{'season':season,'before':before,'match_count':len(entries),'historical_and_featured':True},
            'totals':total,'rates':covered_rates(total,coverage),'seasons':by_season,'recent_form':{'matches':min(5,len(entries)),'totals':recent,
                'rates':covered_rates(recent,metric_coverage([(json.loads(r['fixture']),s) for r,_,s in entries[:5]]))},
            'record':record,'insights':insights,'heatmap':{'kind':'event_locations','columns':12,'rows':8,'pitch_m':[105,68],
                'coordinates':'subject_club_attacks_positive_x','cells':[{'column':int(k.split(':')[0]),'row':int(k.split(':')[1]),'actions':v} for k,v in sorted(heat.items())],
                'total_actions':sum(heat.values())},
            'coverage':{'xg_shots':total['xg_shots'],'all_shots':total['shots'],'xpass_passes':total['xpass_passes'],'all_passes':total['passes'],
                'metrics':coverage,
                'assists_unavailable_matches':coverage['assists']['total_matches']-coverage['assists']['recorded_matches'],
                'key_passes_unavailable_matches':coverage['key_passes']['total_matches']-coverage['key_passes']['recorded_matches'],
                'saves_unavailable_matches':sum(json.loads(r['fixture'])['source_kind']=='adapted_archive' for r,_,_ in entries),
                'recoveries_unavailable_matches':sum(json.loads(r['fixture'])['source_kind']=='adapted_archive' for r,_,_ in entries),
                'minutes_at_source_minute_precision_matches':sum(json.loads(r['fixture'])['minutes_basis']=='source_lineup_minute_precision' for r,_,_ in entries),
                'tracking_distance_m':None,'tracking_heatmap':None,'speed_basis':'authored_physics_only'},
            'evidence':{'rule_version':RULE_VERSION,'baseline_id':baseline,'matches':refs,'goals':goals}}

    def history(self,subject,kind='player',season=None,before=None,offset=0,limit=20):
        registry=self.store.players if kind=='player' else self.store.clubs
        if subject not in registry:raise KeyError(subject)
        key='players' if kind=='player' else 'clubs';club=registry[subject].club_id;items=[]
        for row in self.store.rows(club=club,season=season,before=before):
            at=self.historical_cutoff(row,before)
            if at is False:continue
            summary=self.store.summary(row['id'],at,completed=at is not None);stats=summary[key].get(subject)
            if stats and stats['appearances']:
                coverage=metric_coverage([(json.loads(row['fixture']),stats)])
                items.append({**match_card(row,summary),'stats':stats,'rates':covered_rates(stats,coverage),'metric_coverage':coverage})
        return {'total':len(items),'offset':offset,'limit':limit,'items':items[offset:offset+limit]}

    def live(self,mid,period,elapsed_ms,player_id=None,sequence=None):
        row=self.store.row(mid);fixture=Fixture.model_validate_json(row['fixture'])
        if elapsed_ms>fixture.period_lengths_ms[period-1]+60000:raise ValueError('Cutoff outside match')
        if player_id and player_id not in {a.player_id for a in fixture.appearances}:raise KeyError(player_id)
        cutoff=(period,elapsed_ms);summary=self.store.summary(mid,cutoff,sequence)
        baseline={};baseline_refs={}
        for club in (fixture.home_id,fixture.away_id):
            for prior in self.store.rows(club=club,before=fixture.kickoff):
                at=self.historical_cutoff(prior,fixture.kickoff)
                if at is False:continue
                ps=self.store.summary(prior['id'],at,completed=True)
                for pid,s in ps['players'].items():
                    if self.store.players[pid].club_id!=club:continue
                    baseline.setdefault(pid,[]).append(s)
                baseline_refs[prior['id']]=self.store.evidence_digest(prior['id'],at)
        before={pid:add_stats(baseline.get(pid,[])) for pid in summary['players']}
        running={pid:s['goals'] for pid,s in before.items()};milestones=[]
        baseline_id=sha256(json.dumps({'rows':baseline_refs,'stats':before},sort_keys=True).encode()).hexdigest()
        for g in summary['goals']:
            if g['goal_for']!=g['club_id']:continue
            pid=g['player_id'];running[pid]+=1;count=running[pid]
            if goal_milestone(count):
                identity=f'{mid}:{pid}:career-goals:{count}'
                milestones.append({'insight_id':identity,'kind':'career_goal_milestone','player_id':pid,'player_name':self.store.players[pid].name,
                    'career_goals':count,'previous_goals':count-1,'event_id':g['event_id'],'event_revision':g['revision'],
                    'available_at':{'period':g['available_period'],'elapsed_ms':g['available_ms']},'baseline_id':baseline_id,
                    'source_reference':g['source_reference'],'rule_version':RULE_VERSION})
        selected=[player_id] if player_id else sorted(before)
        return {'match_id':mid,'cutoff':{'period':period,'elapsed_ms':elapsed_ms},'through_sequence':sequence,
            'score':summary['score'],'event_count':summary['event_count'],'clubs':summary['clubs'],
            'players':{pid:{'match':summary['players'][pid],'career_before':before[pid],
                'career_at_cutoff':add_stats([before[pid],summary['players'][pid]])} for pid in selected},
            'milestones':[m for m in milestones if not player_id or m['player_id']==player_id],
            'baseline':{'id':baseline_id,'before_kickoff':fixture.kickoff,'match_count':len(baseline_refs)},'rule_version':RULE_VERSION}

    def changes(self,mid,period,elapsed_ms,since_sequence):
        old={x['insight_id']:x for x in self.live(mid,period,elapsed_ms,sequence=since_sequence)['milestones']}
        new={x['insight_id']:x for x in self.live(mid,period,elapsed_ms)['milestones']}
        changes=[]
        for key in sorted(old.keys()|new.keys()):
            if key not in new:changes.append({'kind':'withdrawn','insight_id':key,'previous':old[key]})
            elif key not in old:changes.append({'kind':'published','insight_id':key,'insight':new[key]})
            elif old[key]!=new[key]:changes.append({'kind':'updated','insight_id':key,'insight':new[key]})
        return {'match_id':mid,'changes':changes,'since_sequence':since_sequence}

    def window(self,mid,start,end):
        fixture=self.store.original(mid).fixture
        if start>=end or any(t[1]>fixture.period_lengths_ms[t[0]-1] for t in (start,end)):raise ValueError('Invalid comparison window')
        selected=select_events(self.store.events(mid),end)
        record=MatchRecord(fixture=fixture,events=tuple(selected))
        return {'match_id':mid,'window':{'start':{'period':start[0],'elapsed_ms':start[1]},'end':{'period':end[0],'elapsed_ms':end[1]},'boundary':'(start,end]'},
            'summary':reduce_record(record,end,start),'source_events':[{'event_id':e.event_id,'revision':e.revision} for e in selected if start<(e.period,e.elapsed_ms)<=end],
            'context_events':[{'event_id':e.event_id,'revision':e.revision} for e in selected if e.period==start[0] and start[1]-15000<=e.elapsed_ms<=start[1]]}

    def standings(self,season):
        table={c:Counter() for c in self.store.clubs};matches=[]
        for row in self.store.rows(season=season):
            if json.loads(row['fixture'])['competition']!='CounterPress League':continue
            summary=self.store.summary(row['id']);matches.append(row['id'])
            for club,opponent in ((row['home'],row['away']),(row['away'],row['home'])):
                a,b=summary['score'][club],summary['score'][opponent];r=table[club]
                r['played']+=1;r['goals_for']+=a;r['goals_against']+=b
                r['wins' if a>b else 'draws' if a==b else 'losses']+=1;r['points']+=3 if a>b else 1 if a==b else 0
        if not matches:raise KeyError(season)
        ranked=sorted(table,key=lambda c:(-table[c]['points'],-(table[c]['goals_for']-table[c]['goals_against']),-table[c]['goals_for'],c))
        return {'season':season,'competition':'CounterPress League','items':[{'rank':i,'club_id':c,**{k:table[c][k] for k in ('played','wins','draws','losses','goals_for','goals_against','points')}} for i,c in enumerate(ranked,1)],'match_ids':matches}
