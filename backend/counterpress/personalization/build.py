"""Reproducibly build careers; source calibration and historical seeds are auditable.

Historical actions are regenerated on demand and checked against event digests.
The compact ledger contains only statistics derived from those exact actions.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import gzip
import json
from pathlib import Path
from statistics import mean
from .calibration import describe
from .imports import existing_records
from .metrics import reduce_record,digest,goal_milestone
from .registry import build_registry
from .simulation import simulate

VERSION='career-world-v1'


def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()


def write_gzip(path,value):
    path.write_bytes(gzip.compress(encode(value),compresslevel=9,mtime=0))


def rounds(ids):
    ring=list(ids);first=[]
    for n in range(len(ring)-1):
        pairs=[(ring[i],ring[-i-1]) if (n+i)%2==0 else (ring[-i-1],ring[i]) for i in range(len(ring)//2)]
        first.append(pairs);ring=[ring[0],ring[-1],*ring[1:-1]]
    return first+[[(b,a) for a,b in pairs] for pairs in first]


def tune(model,players,clubs):
    trials=[]
    for pace in (.9,1.):
        for hazard in (.4,.5,.6):
            candidate={**model,'tempo_scale':pace,'shot_hazard_scale':hazard};rows=[]
            for i in range(24):
                r=simulate(candidate,players,clubs[i%12].club_id,clubs[(i+1)%12].club_id,f'cal-{i}',
                    '2026-01-01T15:00:00Z','calibration',10000+i)
                s=reduce_record(r)['clubs'];rows.append({k:sum(v[k] for v in s.values()) for k in ('passes','shots','goals')})
            means={k:mean(r[k] for r in rows) for k in rows[0]}
            loss=sum(((means[k]-model['source_match_distributions'][source]['mean'])/max(1,model['source_match_distributions'][source]['mean']))**2 for k,source in [('passes','pass'),('shots','shot'),('goals','goal')])
            trials.append({'tempo_scale':pace,'shot_hazard_scale':hazard,'training_moment_loss':loss,'means':means})
    best=min(trials,key=lambda r:r['training_moment_loss'])
    return {**model,'tempo_scale':best['tempo_scale'],'shot_hazard_scale':best['shot_hazard_scale']},trials


def build(root:Path,metadata:Path,output:Path):
    output.mkdir(parents=True,exist_ok=True)
    for name in ('calibration.json','calibration-report.json','metric-definitions.json'):
        source=root/'personalization'/name
        if source.resolve()!=(output/name).resolve():(output/name).write_bytes(source.read_bytes())
    original=json.loads((root/'personalization/calibration.json').read_text());clubs,players=build_registry(original)
    model,trials=tune(original,players,clubs)
    (output/'model.json').write_text(json.dumps(model,indent=2)+'\n')
    registry={'clubs':[c.model_dump(mode='json') for c in clubs],'players':[p.model_dump(mode='json') for p in players]}
    (output/'registry.json').write_text(json.dumps(registry,indent=2)+'\n')
    ledger=[];totals=Counter();validation=[]
    def append(record,keep=False):
        summary=reduce_record(record)
        row={'fixture':record.fixture.model_dump(mode='json'),'event_digest':digest(record.events),'summary':summary}
        ledger.append(row)
        for pid,s in summary['players'].items():totals[pid]+=s['goals']
        if keep:write_gzip(output/(record.fixture.match_id+'.json.gz'),record.model_dump(mode='json'))
        return row
    schedule=rounds([c.club_id for c in clubs])
    for year in range(2020,2027):
        # Six completed 22-round seasons, then eight rounds before the showcases.
        first=datetime(year,8,22,15,tzinfo=timezone.utc)
        for rn,pairs in enumerate(schedule[:8 if year==2026 else 22],1):
            date=(first+timedelta(days=7*(rn-1))).strftime('%Y-%m-%dT%H:%M:%SZ')
            for game,(home,away) in enumerate(pairs):
                seed=year*10000+rn*10+game;mid=f'career-{year}-r{rn:02}-{game+1}'
                r=simulate(model,players,home,away,mid,date,f'{year}-{str(year+1)[-2:]}',seed)
                append(r)
        print(f'Built {year} season: {len(ledger)} historical matches',flush=True)
    for r in existing_records(root,metadata):append(r,True)
    # A separate unselected population validates the generator. Never tune to it.
    candidates=[]
    for i in range(100):
        r=simulate(model,players,'southbank','redhaven','career-showcase-southbank-redhaven',
            '2026-10-19T15:00:00Z','2026-27',20000+i,True)
        s=reduce_record(r);clubrows=list(s['clubs'].values())
        counts={k:sum(v[k] for v in clubrows) for k in ('passes','passes_completed','shots','goals')};validation.append(counts)
        if not 2<=counts['goals']<=5 or not 12<=counts['shots']<=38:continue
        running=totals.copy();milestones=0;lead=0;changes=0;ties=0;score={c:0 for c in s['clubs']}
        for goal in s['goals']:
            running[goal['player_id']]+=1;milestones+=goal_milestone(running[goal['player_id']])
            score[goal['goal_for']]+=1;diff=score['southbank']-score['redhaven'];new=(diff>0)-(diff<0)
            ties+=new==0;changes+=bool(lead and new and lead!=new)
            if new:lead=new
        ranking=5*milestones+3*changes+2*ties-abs(score['southbank']-score['redhaven'])
        candidates.append((ranking,-i,r))
    if not candidates:raise ValueError('No showcase met the declared envelope')
    selected=max(candidates,key=lambda c:c[:2])[2];selected_row=append(selected,True)
    ledger.sort(key=lambda row:(row['fixture']['kickoff'],row['fixture']['match_id']))
    write_gzip(output/'ledger.json.gz',ledger)
    # Exact action ranges ending after a goal, excluding restart; no new stat records.
    clips=[];running={p:totals[p]-s['goals'] for p,s in selected_row['summary']['players'].items()};score={c:0 for c in selected_row['summary']['score']}
    for goal in selected_row['summary']['goals']:
        end=next(i for i,e in enumerate(selected.events) if e.event_id==goal['event_id']);start=end
        while start>0 and end-start<10:
            prior=selected.events[start-1];current=selected.events[start]
            if prior.period!=current.period or prior.kind=='shot' and prior.outcome=='goal' or current.restart:break
            if current.kind=='recovery' and end-start>=2:break
            start-=1
        chosen=selected.events[start:end+1]
        pid=goal['player_id'];club=goal['goal_for'];score[club]+=1;running[pid]+=1
        name=next(p.name for p in players if p.player_id==pid);club_name=next(c.name for c in clubs if c.club_id==club)
        opponent=next(c for c in score if c!=club)
        title=f'{name} brings {club_name} level' if score[club]==score[opponent] else f'{name} puts {club_name} ahead' if score[club]==score[opponent]+1 else f'{name} finds the finish'
        milestone=running[pid] if goal_milestone(running[pid]) else None
        if milestone:title=f'{name} reaches {milestone} career goals'
        clips.append({'highlight_id':f'{selected.fixture.match_id}-{goal["event_id"]}','match_id':selected.fixture.match_id,
            'date':selected.fixture.kickoff[:10],'title':title,'scorer_id':pid,'score_after':dict(score),'career_goal_milestone':milestone,
            'event_ids':[e.event_id for e in chosen],'start':{'period':chosen[0].period,'elapsed_ms':chosen[0].elapsed_ms},
            'end':{'period':chosen[-1].period,'elapsed_ms':max(chosen[-1].available_ms,chosen[-1].elapsed_ms+(chosen[-1].flight_ms or 1000))},'goal_event_id':goal['event_id']})
    (output/'highlights.json').write_text(json.dumps(clips[-3:],indent=2)+'\n')
    files=['registry.json','model.json','ledger.json.gz','highlights.json','calibration.json','calibration-report.json','metric-definitions.json']+[r['fixture']['match_id']+'.json.gz' for r in ledger if r['fixture']['featured']]
    report={'version':VERSION,'training_matches':304,'held_out_matches':76,'historical_matches':len(ledger)-4,'featured_matches':4,
        'featured_clubs':4,'featured_players':44,'clubs':len(clubs),'players':len(players),
        'total_events':sum(r['summary']['event_count'] for r in ledger),'simulator_tuning':trials,
        'validation_100':{k:describe([r[k] for r in validation]) for k in validation[0]},
        'selected_seed':selected.fixture.seed,'selected_score':selected_row['summary']['score'],
        'career_goal_range':{'min':min(totals.values()),'max':max(totals.values())},
        'model_sha256':sha256(encode(model)).hexdigest(),
        'files':{f:sha256((output/f).read_bytes()).hexdigest() for f in files},
        'limitations':['One league season calibrates event patterns; multi-year persistence, form and lineup rotation are authored.',
            'Ball flight speeds are authored physics, not measured tracking. Full player occupancy and running distance are unavailable.',
            'Historical fixtures are reproducible from seeds and event digests. Four featured fixtures are materialized.',
            'Source archive passes lack recipients; archive assists are not inferred. Coverage flags distinguish this from zero.',
            'The showcase is selected for narrative value from 100 untouched candidates; it is not the population benchmark.']}
    (output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('historical_matches','featured_matches','featured_players','total_events','selected_seed','selected_score','career_goal_range')}))


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--fixtures',type=Path,default=Path('fixtures'))
    p.add_argument('--archive-metadata',type=Path,required=True);p.add_argument('--output',type=Path,default=Path('fixtures/personalization'))
    a=p.parse_args();build(a.fixtures,a.archive_metadata,a.output)

if __name__=='__main__':main()
