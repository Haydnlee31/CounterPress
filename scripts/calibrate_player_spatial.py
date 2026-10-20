"""Fit spatial event preferences on the existing training split only.

The independent audit retains its fixed envelopes and source holdout. Trials,
source hashes and seeds are retained. This script never promotes live fixtures.
"""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
from hashlib import sha256
import json, math
from pathlib import Path
from statistics import mean
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_player_distributions as audit
from counterpress.personalization.analytics import derive, DEFINITIONS
from counterpress.personalization.positions import generated_row, summarize, position_checks, formation_reference, ROLES
from counterpress.personalization.realism import population, checks
from counterpress.personalization.simulation import simulate
from counterpress.personalization.registry import build_registry

ROOT=Path(__file__).resolve().parents[1]
DEFS={d[0]:d for d in DEFINITIONS}
PARAMETERS=('tempo_scale','shot_hazard_scale','finishing_scale','shot_role_scale','creator_role_scale',
    'involvement_role_scale','duel_role_scale','pass_length_role_scale','pass_role_offset',
    'finishing_role_scale','form_scale','setup_role_scale','spatial')

def worker(args):
    model, start, count, seedbase=args
    clubs,players=build_registry(model);meta={p.player_id:p for p in players}
    records=[];rows=[]
    for i in range(start,start+count):
        h=i%12;a=(h+1+(i//12)%11)%12
        record=simulate(model,players,clubs[h].club_id,clubs[a].club_id,f'fit-{i}','2026-01-01T15:00:00Z','spatial-fitting',seedbase+i)
        from counterpress.personalization.metrics import reduce_record
        summary=reduce_record(record);records.append(summary)
        row=generated_row(record,summary,players)
        extra=derive(record,summary)
        for pid, data in extra.items():row['players'][pid].update(data['stats'])
        row['clubs']={p:meta[p].club_id for p in row['players']};rows.append(row)
    return records,rows


def sample(model,n,seedbase,pool):
    records=[];rows=[]
    for a,b in pool.map(worker,[(model,i,min(24,n-i),seedbase) for i in range(0,n,24)]):records.extend(a);rows.extend(b)
    return records,rows


def load_targets(source,model,output):
    path=output/'training-targets.json'
    if path.exists():
        data=json.loads(path.read_text())
        assert data['source_sha256']==model['provenance']['sha256']
        assert data['training_match_ids']==model['training_match_ids']
        return {r:Counter(s) for r,s in data['counts'].items()}
    data={}
    for name in ('events_England','matches_England','players'):
        raw=(source/(name+'.json')).read_bytes()
        assert sha256(raw).hexdigest()==model['provenance']['sha256'][name]
        data[name]=json.loads(raw)
    # No held-out rows are used to estimate spatial targets.
    train_model={**model,'holdout_match_ids':[]}
    rows=audit.source_data(data['events_England'],data['matches_England'],data['players'],train_model)
    target,*_=audit.totals(rows)
    path.write_text(json.dumps({'counts':target,'source_sha256':model['provenance']['sha256'],'training_match_ids':model['training_match_ids']},indent=2)+'\n')
    return target


def bound(v,lo,hi):return max(lo,min(hi,v))

def assess(model,records,rows,targets):
    positions=summarize(rows);core=position_checks(positions,model['position_target'])
    roles,people,teams,meta=audit.totals(rows)
    ext={}
    for d in DEFINITIONS:
        if d[0] not in audit.COMPARABLE:continue
        for r in ROLES:
            if d[2]=='Goalkeeping' and r!='GK' or audit.comparability(targets[r],d):continue
            actual=audit.value(roles[r],d);target=audit.value(targets[r],d)
            if actual is None or target is None:continue
            tol=audit.tolerance(target,d)
            ext[f'{r}.{d[0]}']={'actual':actual,'target':target,'tolerance':tol,'passed':abs(actual-target)<=tol}
    clubs,players=build_registry(model)
    pop=population(records,players);ref=formation_reference(model['population_target'],model['position_target'],positions)
    popchecks=checks(pop,ref)
    loss=mean(((v['actual']-v['target'])/v['absolute_tolerance'])**2 for v in core.values())
    loss+=mean(((v['actual']-v['target'])/v['tolerance'])**2 for v in ext.values())
    loss+=sum(((positions['roles'][r]['rates']['assists_per90']-model['position_target']['roles'][r]['rates']['assists_per90'])/max(.005,model['position_target']['roles'][r]['rates']['assists_per90']*.10))**2 for r in ('DF','MF','FW'))/3
    # Centre this rare aggregate ratio instead of merely accepting a candidate
    # close to its boundary. This changes the training loss, not audit tolerances.
    loss+=((pop['assisted_goal_share']-ref['assisted_goal_share'])/.09)**2
    loss+=mean(((pop['assist_role_share'][r]-ref['assist_role_share'][r])/.05)**2 for r in ('DF','MF','FW'))
    return {'core':core,'extended':ext,'population':popchecks,'loss':loss,'positions':positions,'role_counts':roles,'population_observed':pop}


def update(model,report,targets):
    c=deepcopy(model);sp=c['spatial'];a={r:report['positions']['roles'][r]['rates'] for r in ROLES};b={r:c['position_target']['roles'][r]['rates'] for r in ROLES}
    pt=c['population_target'];pop=report['population_observed'];counts=report['role_counts']
    reference=formation_reference(pt,c['position_target'],report['positions'])
    creation_adjustment=(reference['assisted_goal_share']/max(.01,pop['assisted_goal_share']))**.3
    pass_target=sum(r['counts']['passes'] for r in c['position_target']['roles'].values())/c['position_target']['matches']
    c['tempo_scale']*= (pop['per_match']['passes']/pass_target)**.5
    c['shot_hazard_scale']*=(pt['per_match']['shots']/pop['per_match']['shots'])**.5
    c['finishing_scale']*=((pt['per_match']['goals']/pt['per_match']['shots'])/(pop['per_match']['goals']/pop['per_match']['shots']))**.3
    c['form_scale']=bound(c['form_scale']*(b['GK']['clean_sheet_rate']/max(.05,a['GK']['clean_sheet_rate']))**.4,.5,3)
    for r in ROLES:
        c['involvement_role_scale'][r]=bound(c['involvement_role_scale'][r]*(b[r]['passes_per90']/max(1,a[r]['passes_per90']))**.5,.01,100)
        c['duel_role_scale'][r]=bound(c['duel_role_scale'][r]*(b[r]['duels_per90']/max(.01,a[r]['duels_per90']))**.4,.001,8)
        c['pass_role_offset'][r]=bound(c['pass_role_offset'][r]+.55*(b[r]['pass_completion']-a[r]['pass_completion']),-.3,.4)
        c['setup_role_scale'][r]=bound(c['setup_role_scale'][r]*(b[r]['assists_per90']/max(.001,a[r]['assists_per90']))**.6*creation_adjustment,.01,8)
        if r=='GK':
            c['pass_length_role_scale'][r]=bound(c['pass_length_role_scale'][r]*(b[r]['completed_long_share']/max(.01,a[r]['completed_long_share']))**.3,.2,10)
            continue
        c['shot_role_scale'][r]=bound(c['shot_role_scale'][r]*(b[r]['shots_per90']/max(.01,a[r]['shots_per90']))**.4,.1,8)
        c['finishing_role_scale'][r]=bound(c['finishing_role_scale'][r]*((b[r]['conversion'] or .1)/max(.02,a[r]['conversion'] or .1))**.25,.2,3)
        for metric,param in [('shots_inside_box','shot_inside_scale'),('shots_outside_box','shot_outside_scale')]:
            # Location mix, not a second adjustment of the total shot rate.
            desired=targets[r][metric]/max(1,targets[r]['shots'])
            observed=counts[r][metric]/max(1,counts[r]['shots'])
            sp[param][r]=bound(sp[param][r]*(desired/max(.01,observed))**.6,.15,6)
        for feature,metric in [('progression','progressive_passes_completed'),('third_entry','final_third_entries'),('box_entry','box_entries'),('backward','backward_passes'),('lateral','lateral_passes'),('long','long_passes'),('cross','crosses')]:
            desired=targets[r][metric]/targets[r]['passes'];observed=counts[r][metric]/counts[r]['passes']
            rate=.25 if feature in ('third_entry','box_entry') else .4
            sp['pass_tilts'][r][feature]=bound(sp['pass_tilts'][r].get(feature,0)+rate*math.log(max(.001,desired)/max(.001,observed)),-4,4)
        desired=targets[r]['long_passes_completed']/targets[r]['long_passes_known'];observed=counts[r]['long_passes_completed']/max(1,counts[r]['long_passes_known'])
        sp['long_completion_offset'][r]=bound(sp['long_completion_offset'][r]+.4*(desired-observed),-.3,.4)
        desired=targets[r]['crosses']/targets[r]['passes'];observed=counts[r]['crosses']/counts[r]['passes']
        sp['wide_involvement'][r]=bound(sp['wide_involvement'][r]*(desired/max(.001,observed))**.3,.2,10)
    return c


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'var/spatial-audit-v4/fitting');p.add_argument('--iterations',type=int,default=24);p.add_argument('--matches',type=int,default=768);p.add_argument('--resume',type=Path)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    model=json.loads((args.resume or ROOT/'fixtures/personalization/model.json').read_text())
    if 'spatial' not in model:
        model['spatial']={'version':'spatial-moments-v1','training_seed_range':[110000,110000+args.matches-1],
           'pass_tilts':{r:{} for r in ROLES},'wide_involvement':{r:1. for r in ROLES},
           'shot_inside_scale':{r:1. for r in ROLES},'shot_outside_scale':{r:1. for r in ROLES},
           'long_completion_offset':{r:0. for r in ROLES},'creator_trait_power':.6,'center_role_traits':True,'role_centering_basis':'appearance_minutes'}
    model['spatial']['training_seed_range']=[110000,110000+args.matches-1]
    targets=load_targets(ROOT/'var/personalization-source',model,args.output)
    trials=[];candidates=[]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for iteration in range(args.iterations):
            records,rows=sample(model,args.matches,110000,pool)
            report=assess(model,records,rows,targets)
            failures={g:[k for k,v in report[g].items() if not v['passed']] for g in ('core','extended','population')}
            print(json.dumps({'iteration':iteration,'loss':round(report['loss'],4),'failures':failures}),flush=True)
            trials.append({'iteration':iteration,'training_moment_loss':report['loss'],
                           'parameters':{k:deepcopy(model[k]) for k in PARAMETERS},'failures':failures,'report':report})
            candidates.append(deepcopy(model))
            (args.output/f'candidate-{iteration:02}.json').write_text(json.dumps(model,indent=2)+'\n')
            (args.output/'trials.json').write_text(json.dumps(trials,indent=2)+'\n')
            model=update(model,report,targets)
        best=min(range(len(trials)),key=lambda i:trials[i]['training_moment_loss'])
    (args.output/'model.json').write_text(json.dumps(candidates[best],indent=2)+'\n')
    (args.output/'next.json').write_text(json.dumps(model,indent=2)+'\n')
    print(f'Selected training candidate {best}',flush=True)

if __name__=='__main__':main()
