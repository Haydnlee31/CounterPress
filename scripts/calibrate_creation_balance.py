"""One-dimensional training search with geometry and other rates held fixed."""
import argparse,json
from copy import deepcopy
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from calibrate_player_spatial import sample,assess,load_targets,PARAMETERS,ROOT


def main():
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--role',choices=('GK','DF','MF','FW'));p.add_argument('--factors',type=float,nargs='+',default=[1.,1.1,1.2,1.3])
    p.add_argument('--prefer-role-share',action='store_true',help='Directional correction: maximize the selected role share among candidates whose outfield assist rates remain inside source training intervals')
    args=p.parse_args()
    if args.prefer_role_share and not args.role:p.error('--prefer-role-share requires --role')
    args.output.mkdir(parents=True,exist_ok=True)
    base=json.loads(args.model.read_text());target=load_targets(ROOT/'var/personalization-source',base,args.output)
    models=[];trials=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for i,factor in enumerate(args.factors):
            m=deepcopy(base);m['spatial']['training_seed_range']=[110000,110767]
            m['setup_role_scale']={r:v*(factor if args.role is None or r==args.role else 1) for r,v in base['setup_role_scale'].items()}
            records,rows=sample(m,768,110000,pool);r=assess(m,records,rows,target)
            failures=[f'{g}.{k}' for g in ('core','population') for k,v in r[g].items() if not v['passed']]
            trials.append({'iteration':i,'creation_factor':factor,'creation_role':args.role,'training_moment_loss':r['loss'],'parameters':{k:deepcopy(m[k]) for k in PARAMETERS},'report':r,'failures':failures});models.append(m)
            (args.output/f'candidate-{i:02}.json').write_text(json.dumps(m,indent=2)+'\n')
            (args.output/'trials.json').write_text(json.dumps(trials,indent=2)+'\n')
            print(json.dumps({'factor':factor,'loss':r['loss'],'assists':{k:v['rates']['assists_per90'] for k,v in r['positions']['roles'].items()},'goals_per_match':r['population_observed']['per_match']['goals'],'failures':failures}),flush=True)
    eligible=[i for i,t in enumerate(trials) if not t['failures']]
    if args.prefer_role_share:
        eligible=[i for i in eligible if all(base['position_target']['roles'][role]['ci95']['assists_per90'][0]
            <=trials[i]['report']['positions']['roles'][role]['rates']['assists_per90']
            <=base['position_target']['roles'][role]['ci95']['assists_per90'][1] for role in ('DF','MF','FW'))]
    if not eligible:raise ValueError('No creation candidate passed training core/population checks')
    best=max(eligible,key=lambda i:trials[i]['report']['population_observed']['assist_role_share'][args.role]) if args.prefer_role_share else min(eligible,key=lambda i:trials[i]['training_moment_loss'])
    (args.output/'model.json').write_text(json.dumps(models[best],indent=2)+'\n')
    print(f'Selected creation factor {trials[best]["creation_factor"]}',flush=True)

if __name__=='__main__':main()
