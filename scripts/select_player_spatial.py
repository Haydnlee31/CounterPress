"""Re-evaluate training-loss finalists on a larger fitting cohort, never holdout."""
import argparse,json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
from calibrate_player_spatial import sample,assess,load_targets,PARAMETERS,ROOT


def main():
    p=argparse.ArgumentParser();p.add_argument('--candidates',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    trials=json.loads((a.candidates/'trials.json').read_text())
    # Rare fitting flags are retained as diagnostics, not ranked ahead of loss.
    finalists=sorted(trials,key=lambda t:t['training_moment_loss'])[:4]
    candidates=[];review=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for trial in finalists:
            m=json.loads((a.candidates/f'candidate-{trial["iteration"]:02}.json').read_text())
            m['spatial']['training_seed_range']=[110000,110767]
            target=load_targets(ROOT/'var/personalization-source',m,a.output)
            records,rows=sample(m,768,110000,pool);r=assess(m,records,rows,target)
            entry={'iteration':trial['iteration'],'training_moment_loss':r['loss'],'parameters':{k:deepcopy(m[k]) for k in PARAMETERS},'report':r}
            review.append(entry);candidates.append(m)
            print(json.dumps({'candidate':trial['iteration'],'loss':r['loss'],'assists':{k:v['rates']['assists_per90'] for k,v in r['positions']['roles'].items()},'core_failures':[k for k,v in r['core'].items() if not v['passed']],'population_failures':[k for k,v in r['population'].items() if not v['passed']]}),flush=True)
            (a.output/'trials.json').write_text(json.dumps(review,indent=2)+'\n')
        best=min(range(len(review)),key=lambda i:review[i]['training_moment_loss'])
        (a.output/'model.json').write_text(json.dumps(candidates[best],indent=2)+'\n')
    print('Selected expanded-training candidate '+str(review[best]['iteration']),flush=True)

if __name__=='__main__':main()
