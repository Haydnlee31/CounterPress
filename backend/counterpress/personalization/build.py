"""Reproducibly build careers; source calibration and historical seeds are auditable.

Historical actions are regenerated on demand and checked against event digests.
The compact ledger contains only statistics derived from those exact actions.
"""
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
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
from .realism import population,checks
from .positions import generated_row,summarize,position_checks,formation_reference,ROLES

VERSION='career-world-v3'


def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()


def write_gzip(path,value):
    path.write_bytes(gzip.compress(encode(value),compresslevel=9,mtime=0))


def rounds(ids):
    ring=list(ids);first=[]
    for n in range(len(ring)-1):
        pairs=[(ring[i],ring[-i-1]) if (n+i)%2==0 else (ring[-i-1],ring[i]) for i in range(len(ring)//2)]
        first.append(pairs);ring=[ring[0],ring[-1],*ring[1:-1]]
    return first+[[(b,a) for a,b in pairs] for pairs in first]


def summarize_simulation(args):
    """Workers return canonical reductions; map order preserves deterministic builds."""
    record=simulate(*args)
    summary=reduce_record(record)
    positions=generated_row(record,summary,args[1])
    if args[0].get('spatial'):
        from .analytics import derive
        for pid,data in derive(record,summary).items():positions['players'][pid].update(data['stats'])
    return {'fixture':record.fixture.model_dump(mode='json'),'event_digest':digest(record.events),'summary':summary},positions


def tune(model,players,clubs):
    trials=[];candidates=[];target=model['population_target'];position_target=model['position_target']
    candidate={**model,'tempo_scale':.9,'shot_hazard_scale':.48,'finishing_scale':1.,'form_scale':1.,
               'shot_role_scale':{'GK':1.,'DF':1.8,'MF':1.15,'FW':.85},
               'creator_role_scale':{'GK':.7,'DF':.9,'MF':1.3,'FW':.85},
               'involvement_role_scale':{'GK':10.,'DF':1.,'MF':.8,'FW':1.},
               'duel_role_scale':{'GK':.03,'DF':.8,'MF':.8,'FW':1.8},
               'pass_length_role_scale':{'GK':3.,'DF':.85,'MF':.85,'FW':.75},
               'pass_role_offset':{'GK':.1,'DF':0.,'MF':0.,'FW':-.05},
               'finishing_role_scale':{'GK':1.,'DF':.7,'MF':.8,'FW':1.},
               'setup_role_scale':{r:max(.03,position_target['roles'][r]['rates']['assists_per90']/position_target['roles'][r]['rates']['passes_per90'] /
                   (position_target['roles']['MF']['rates']['assists_per90']/position_target['roles']['MF']['rates']['passes_per90'])) for r in ROLES}}
    parameter_names=('tempo_scale','shot_hazard_scale','finishing_scale','shot_role_scale','creator_role_scale',
                     'involvement_role_scale','duel_role_scale','pass_length_role_scale','pass_role_offset','finishing_role_scale','form_scale','setup_role_scale')
    pass_target=sum(r['counts']['passes'] for r in position_target['roles'].values())/position_target['matches']
    def bound(x,lo,hi):return max(lo,min(hi,x))
    for iteration in range(18):
        rows=[];position_rows=[]
        for i in range(192):
            home=i%12;away=(home+1+(i//12)%11)%12
            r=simulate(candidate,players,clubs[home].club_id,clubs[away].club_id,f'cal-{i}',
                '2026-01-01T15:00:00Z','calibration',10000+i)
            summary=reduce_record(r);rows.append(summary);position_rows.append(generated_row(r,summary,players))
        observed=population(rows,players)
        positions=summarize(position_rows);gates=position_checks(positions,position_target)
        adjusted_target=formation_reference(target,position_target,positions)
        population_gates=checks(observed,adjusted_target)
        loss=mean(((v['actual']-v['target'])/v['absolute_tolerance'])**2 for v in gates.values())
        loss+=sum((observed['per_match'][k]/target['per_match'][k]-1)**2 for k in ('goals','shots'))
        loss+=sum(4*(observed[group][role]-adjusted_target[group][role])**2 for group in ('goal_role_share','assist_role_share') for role in ('DF','MF','FW'))
        # Rare assist rates otherwise contribute little under broad acceptance
        # floors. Fit them more closely without tightening/widening test gates.
        loss+=mean(((positions['roles'][r]['rates']['assists_per90']-position_target['roles'][r]['rates']['assists_per90'])/
                    max(.02,position_target['roles'][r]['rates']['assists_per90']*.25))**2 for r in ('DF','MF','FW'))
        trials.append({'iteration':iteration,'training_moment_loss':loss,'observed':observed,
                       'positions':positions,'position_checks':gates,'population_checks':population_gates,'parameters':{k:candidate[k] for k in parameter_names}})
        candidates.append(candidate)
        print(f'Calibration {iteration}: goals={observed["per_match"]["goals"]:.2f}, loss={loss:.4f}, position failures={sum(not v["passed"] for v in gates.values())}',flush=True)
        a={r:positions['roles'][r]['rates'] for r in ROLES};b={r:position_target['roles'][r]['rates'] for r in ROLES}
        candidate={**candidate,
            'tempo_scale':candidate['tempo_scale']*(observed['per_match']['passes']/pass_target)**.6,
            'shot_hazard_scale':candidate['shot_hazard_scale']*(target['per_match']['shots']/observed['per_match']['shots'])**.7,
            'finishing_scale':candidate['finishing_scale']*((target['per_match']['goals']/target['per_match']['shots'])/(observed['per_match']['goals']/observed['per_match']['shots']))**.5,
            'shot_role_scale':{r:bound(candidate['shot_role_scale'][r]*(b[r]['shots_per90']/max(.01,a[r]['shots_per90']))**.5,.1,8) if r!='GK' else 1 for r in ROLES},
            'finishing_role_scale':{r:bound(candidate['finishing_role_scale'][r]*((b[r]['conversion'] or .1)/max(.02,a[r]['conversion'] or .1))**.35,.2,3) if r!='GK' else 1 for r in ROLES},
            'setup_role_scale':{r:bound(candidate['setup_role_scale'][r]*(b[r]['assists_per90']/max(.001,a[r]['assists_per90']))**.5,.01,8) for r in ROLES},
            'form_scale':bound(candidate['form_scale']*(b['GK']['clean_sheet_rate']/max(.05,a['GK']['clean_sheet_rate']))**.8,.5,3),
            'involvement_role_scale':{r:bound(candidate['involvement_role_scale'][r]*(b[r]['passes_per90']/max(1,a[r]['passes_per90']))**.7,.01,100) for r in ROLES},
            'duel_role_scale':{r:bound(candidate['duel_role_scale'][r]*(b[r]['duels_per90']/max(.01,a[r]['duels_per90']))**.5,.001,8) for r in ROLES},
            'pass_length_role_scale':{r:bound(candidate['pass_length_role_scale'][r]*(b[r]['completed_long_share']/max(.01,a[r]['completed_long_share']))**.3,.2,10) for r in ROLES},
            'pass_role_offset':{r:bound(candidate['pass_role_offset'][r]+.5*(b[r]['pass_completion']-a[r]['pass_completion']),-.2,.3) for r in ROLES}}
    best=min(range(len(trials)),key=lambda i:(sum(not c['passed'] for group in ('position_checks','population_checks') for c in trials[i][group].values()),trials[i]['training_moment_loss']))
    print(f'Selected training candidate {best}',flush=True)
    return candidates[best],trials


def build(root:Path,metadata:Path,output:Path,tuned:Path|None=None,validation_seed=70000,historical_only=False):
    output.mkdir(parents=True,exist_ok=True)
    for name in ('calibration.json','calibration-report.json','metric-definitions.json'):
        source=root/'personalization'/name
        if source.resolve()!=(output/name).resolve():(output/name).write_bytes(source.read_bytes())
    original=json.loads((root/'personalization/calibration.json').read_text());clubs,players=build_registry(original)
    if tuned:
        model=json.loads(tuned.read_text());trials=json.loads(tuned.with_name('trials.json').read_text())
        if any(model.get(k)!=v for k,v in original.items() if k!='shot_hazard_scale'):raise ValueError('Tuned model does not match source calibration')
        if not any(all(model.get(k)==v for k,v in t['parameters'].items()) for t in trials):raise ValueError('Tuned model is absent from training trials')
    else:model,trials=tune(original,players,clubs)
    (output/'model.json').write_text(json.dumps(model,indent=2)+'\n')
    registry={'clubs':[c.model_dump(mode='json') for c in clubs],'players':[p.model_dump(mode='json') for p in players]}
    (output/'registry.json').write_text(json.dumps(registry,indent=2)+'\n')
    ledger=[];totals=Counter();position_rows=[]
    def append(record,keep=False):
        summary=reduce_record(record)
        row={'fixture':record.fixture.model_dump(mode='json'),'event_digest':digest(record.events),'summary':summary}
        ledger.append(row)
        if record.fixture.source_kind=='calibrated_simulation' and not record.fixture.featured:
            position_rows.append(generated_row(record,summary,players))
        for pid,s in summary['players'].items():totals[pid]+=s['goals']
        if keep:write_gzip(output/(record.fixture.match_id+'.json.gz'),record.model_dump(mode='json'))
        return row
    schedule=rounds([c.club_id for c in clubs])
    for year in range(2020,2027):
        # Six completed 22-round seasons, then eight rounds before the showcases.
        first=datetime(year,8,22,15,tzinfo=timezone.utc)
        jobs=[]
        for rn,pairs in enumerate(schedule[:8 if year==2026 else 22],1):
            date=(first+timedelta(days=7*(rn-1))).strftime('%Y-%m-%dT%H:%M:%SZ')
            for game,(home,away) in enumerate(pairs):
                seed=year*10000+rn*10+game;mid=f'career-{year}-r{rn:02}-{game+1}'
                jobs.append((model,players,home,away,mid,date,f'{year}-{str(year+1)[-2:]}',seed))
        with ProcessPoolExecutor(max_workers=4) as pool:
            for row,positions in pool.map(summarize_simulation,jobs,chunksize=6):
                ledger.append(row);position_rows.append(positions)
                for pid,s in row['summary']['players'].items():totals[pid]+=s['goals']
        print(f'Built {year} season: {len(ledger)} historical matches',flush=True)
    for r in existing_records(root,metadata):append(r,True)
    historical_population=population(ledger[:-3],players)
    if historical_only:
        write_gzip(output.parent/'historical-review.json.gz',{'positions':position_rows,'ledger':ledger,'population':historical_population})
        print('Historical review only; no validated manifest or app dataset produced.',flush=True)
        return
    # Independent teams/seeds validate the population; showcase selection uses
    # a separate pool and cannot inflate this benchmark.
    validation_rows=[];validation_positions=[]
    jobs=[(model,players,clubs[i%12].club_id,clubs[(i%12+1+(i//12)%11)%12].club_id,f'validation-{i}',
           '2026-01-01T15:00:00Z','validation',validation_seed+i) for i in range(3000)]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for i,(row,positions) in enumerate(pool.map(summarize_simulation,jobs,chunksize=6),1):
            validation_rows.append(row['summary']);validation_positions.append(positions)
            if i%250==0:print(f'Validated {i}/3000 independent matches',flush=True)
    validation_population=population(validation_rows,players)
    source_report=json.loads((output/'calibration-report.json').read_text());holdout=source_report['population_holdout']
    position_report={'version':'position-audit-v1','source_training':model['position_target'],
                     'source_holdout':source_report['position_holdout'],'historical':summarize(position_rows,bootstrap=400),
                     'validation_batches':[],'seed_ranges':[[validation_seed+i,validation_seed+999+i] for i in (0,1000,2000)],
                     'pooled_validation':summarize(validation_positions,bootstrap=400)}
    position_report['historical_checks']=position_checks(position_report['historical'],position_report['source_holdout'],model['position_target'])
    historical_reference=formation_reference(holdout,position_report['source_holdout'],position_report['historical'],model['population_target'])
    position_report['pooled_checks']=position_checks(position_report['pooled_validation'],position_report['source_holdout'],model['position_target'])
    pooled_reference=formation_reference(holdout,position_report['source_holdout'],position_report['pooled_validation'],model['population_target'])
    position_report['pooled_population_reference']=pooled_reference
    position_report['pooled_population_checks']=checks(validation_population,pooled_reference)
    for i in range(3):
        observed=summarize(validation_positions[1000*i:1000*(i+1)],bootstrap=400)
        reference=formation_reference(holdout,position_report['source_holdout'],observed,model['population_target'])
        position_report['validation_batches'].append({'observed':observed,'checks':position_checks(observed,position_report['source_holdout'],model['position_target']),
            'population_reference':reference,'population_checks':checks(population(validation_rows[1000*i:1000*(i+1)],players),reference)})
    (output/'position-validation.json').write_text(json.dumps(position_report,indent=2)+'\n')
    candidates=[]
    for i in range(100):
        r=simulate(model,players,'southbank','redhaven','career-showcase-southbank-redhaven',
            '2026-10-19T15:00:00Z','2026-27',20000+i,True)
        s=reduce_record(r);clubrows=list(s['clubs'].values())
        counts={k:sum(v[k] for v in clubrows) for k in ('passes','passes_completed','shots','goals')}
        if not 3<=counts['goals']<=5 or not 12<=counts['shots']<=38:continue
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
    files=['registry.json','model.json','ledger.json.gz','highlights.json','calibration.json','calibration-report.json','metric-definitions.json','position-validation.json']+[r['fixture']['match_id']+'.json.gz' for r in ledger if r['fixture']['featured']]
    report={'version':VERSION,'training_matches':304,'held_out_matches':76,'historical_matches':len(ledger)-4,'featured_matches':4,
        'featured_clubs':4,'featured_players':44,'clubs':len(clubs),'players':len(players),
        'total_events':sum(r['summary']['event_count'] for r in ledger),'simulator_tuning':trials,
        'population_validation':{'historical':historical_population,'unselected_3000':validation_population,
            'source_training':model['population_target'],'source_holdout':holdout,
            'historical_reference':historical_reference,
            'historical_checks':checks(historical_population,historical_reference),'validation_checks':position_report['pooled_population_checks'],
            'seed_ranges':{'fitting':model.get('spatial',{}).get('training_seed_range',[10000,10191]),'validation':[validation_seed,validation_seed+2999],'showcase_selection':[20000,20099]}},
        'selected_seed':selected.fixture.seed,'selected_score':selected_row['summary']['score'],
        'career_goal_range':{'min':min(totals.values()),'max':max(totals.values())},
        'model_sha256':sha256(encode(model)).hexdigest(),
        'simulation_sources':{name:sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ('simulation.py','spatial.py','registry.py','metrics.py','contracts.py','positions.py','calibration.py','build.py','imports.py')},
        'files':{f:sha256((output/f).read_bytes()).hexdigest() for f in files},
        'limitations':['One league season calibrates event patterns; multi-year persistence, form and lineup rotation are authored.',
            'Ball flight speeds are authored physics, not measured tracking. Full player occupancy and running distance are unavailable.',
            'Historical fixtures are reproducible from seeds and event digests. Four featured fixtures are materialized.',
            'Source archive assists use explicit provider tags linked to goals. Shot-assist, save and recovery gaps retain coverage.',
            'The showcase is selected from 100 candidates; 3000 fresh independent matches validate the population.',
            'Own-goal frequency and long-term aging, transfers and injuries are not calibrated; source role labels are broad.',
            'Source and generated assist definitions are related but not identical; benchmark tolerances reflect this.']}
    failures=[f'historical.{k}' for k,c in position_report['historical_checks'].items() if not c['passed']]
    failures += [f'population.{k}' for k,c in report['population_validation']['historical_checks'].items() if not c['passed']]
    failures += [f'pooled.{group}.{k}' for group in ('pooled_checks','pooled_population_checks') for k,c in position_report[group].items() if not c['passed']]
    for i,batch in enumerate(position_report['validation_batches']):
        failures += [f'batch{i+1}.{k}' for k,c in batch['checks'].items() if not c['passed']]
    report['validation_warnings']=[f'batch{i+1}.{k}' for i,b in enumerate(position_report['validation_batches']) for k,c in b['population_checks'].items() if not c['passed']]
    report['validation_status']='failed' if failures else 'passed'
    report['validation_failures']=failures
    (output/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('historical_matches','featured_matches','featured_players','total_events','selected_seed','selected_score','career_goal_range')}))
    if failures:raise ValueError(f'Candidate failed {len(failures)} gates; do not publish. See manifest.json validation_failures.')


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--fixtures',type=Path,default=Path('fixtures'))
    p.add_argument('--archive-metadata',type=Path,required=True);p.add_argument('--output',type=Path,default=Path('fixtures/personalization'))
    p.add_argument('--tuned-model',type=Path,help='Reuse a model with its training trials; source calibration must match exactly')
    p.add_argument('--validation-seed',type=int,default=70000,help='Start of 3000 disjoint validation seeds, fixed before validation')
    p.add_argument('--historical-only',action='store_true',help='Produce a read-only historical diagnostic before the expensive validation run; never app-loadable')
    a=p.parse_args();build(a.fixtures,a.archive_metadata,a.output,a.tuned_model,a.validation_seed,a.historical_only)

if __name__=='__main__':main()
