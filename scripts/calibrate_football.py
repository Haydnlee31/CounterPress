"""Fit 15 whole matches, compare five held-out matches, and select a new synthetic showcase."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from random import Random
from statistics import mean
from counterpress.generator.calibrated import fit, generate_full, generated_metrics, metrics


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--events',type=Path,required=True)
    parser.add_argument('--matches',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise SystemExit('Choose a new output directory')
    events=json.loads(args.events.read_text());matches=json.loads(args.matches.read_text())
    eligible=sorted((m for m in matches if m['duration']=='Regular' and m['wyId'] not in {2058007,2058017}),key=lambda m:m['wyId'])
    rng=Random(20261018);rng.shuffle(eligible)
    # Equal coverage of quiet, ordinary and high-scoring matches; not a population-frequency estimate.
    groups=[[],[],[]]
    for m in eligible:
        total=sum(t['score'] for t in m['teamsData'].values())
        groups[0 if total<=1 else 1 if total<=3 else 2].append(m)
    training=[m for group in groups for m in group[:5]]
    train_ids=[m['wyId'] for m in training]
    holdout=[m for m in eligible if m['wyId'] not in train_ids][:5]
    model=fit(events,train_ids)
    # Simulation-based moment matching uses training means only and separate calibration seeds.
    target={k:mean(r[k] for r in model['match_metrics']) for k in ('shots','goals')}
    calibration=[]
    for scale in (.45,.6,.75,1.0):
        trial={**model,'shot_hazard_scale':scale}
        samples=[generated_metrics(generate_full(trial,seed)) for seed in range(1000,1012)]
        averages={k:mean(r[k] for r in samples) for k in target}
        loss=sum(((averages[k]-target[k])/max(1,target[k]))**2 for k in target)
        calibration.append({'scale':scale,'training_moment_loss':loss,'means':averages})
    model['shot_hazard_scale']=min(calibration,key=lambda item:item['training_moment_loss'])['scale']
    runs=[generate_full(model,seed) for seed in range(100)]
    results=[generated_metrics(feed) for feed in runs]
    # Entertainment selects a sample; it never edits its events or forces a goal.
    candidates=[i for i,r in enumerate(results) if 2<=r['goals']<=5 and 12<=r['shots']<=38 and 500<=r['passes']<=1200]
    def excitement(i):
        score={'eastbridge':0,'northport':0};ties=changes=0;lead=0;late=0
        for e in runs[i].events:
            if e.action.kind!='shot' or e.action.outcome!='goal':continue
            score[e.actor.team_id]+=1;diff=score['eastbridge']-score['northport'];new=(diff>0)-(diff<0)
            ties+=new==0;changes+=bool(new and lead and new!=lead)
            if new:lead=new
            late+=e.occurred_at.period==2 and e.occurred_at.elapsed_ms>2100000
        return 3*changes+2*ties+late-abs(score['eastbridge']-score['northport'])
    if not candidates:raise SystemExit('No candidate meets the predeclared plausibility envelope; inspect calibration')
    selected=max(candidates,key=lambda i:(excitement(i),-i))
    held=[metrics([e for e in events if e['matchId']==m['wyId']]) for m in holdout]
    def describe(rows):return {k:{'mean':mean(r[k] for r in rows),'min':min(r[k] for r in rows),'max':max(r[k] for r in rows)} for k in rows[0]}
    report={'version':model['version'],'selection_seed':20261018,'training_matches':[{'id':m['wyId'],'label':m['label']} for m in training],
        'holdout_matches':[{'id':m['wyId'],'label':m['label']} for m in holdout],
        'source':{'authors':'Luca Pappalardo and Emanuele Massucco / Wyscout','url':'https://doi.org/10.6084/m9.figshare.7770599','license':'CC BY 4.0','events_sha256':sha256(args.events.read_bytes()).hexdigest()},
        'training':describe(model['match_metrics']),'holdout':describe(held),'generated_100':describe(results),
        'selected_seed':selected,'selected_metrics':results[selected],'candidate_count':len(candidates),
        'calibration_trials':calibration,'limitations':['Single 2018 international tournament, not all football.','Score-stratified sample overrepresents high-scoring games.','Event-derived action runs are not measured possession duration.','Carry geometry, duel success, team style and late risk are authored priors.','On-target non-goal shots are simplified to saves in the simulator; not a source save measurement.','Showcase selection biases excitement; generated_100 is the unselected distribution.']}
    args.output.mkdir(parents=True)
    for name,value in [('model.json',model),('report.json',report)]: (args.output/name).write_text(json.dumps(value,indent=2)+'\n')
    (args.output/'match.json').write_text(runs[selected].model_dump_json(indent=2)+'\n')
    print(json.dumps({'fit_matches':len(training),'held_out':len(holdout),'generated':100,'selected_seed':selected,'selected':results[selected],'comparison':{'training':report['training'],'generated':report['generated_100']}},indent=2))

if __name__=='__main__':main()
