"""Cheap historical preflight; full event and independent audits remain required."""
import argparse,gzip,json
from collections import Counter,defaultdict
from pathlib import Path
import audit_player_distributions as audit
from counterpress.personalization.positions import summarize,position_checks,formation_reference
from counterpress.personalization.realism import checks


def review(root,baseline):
    data=json.loads(gzip.decompress((root.parent/'historical-review.json.gz').read_bytes()))
    model=json.loads((root/'model.json').read_text());source=json.loads((root/'calibration-report.json').read_text())
    registry=json.loads((root/'registry.json').read_text());people={p['player_id']:p for p in registry['players']}
    for row in data['positions']:row['clubs']={p:people[p]['club_id'] for p in row['players']}
    roles,_,teams,_=audit.totals(data['positions']);positions=summarize(data['positions'])
    core=position_checks(positions,source['position_holdout'],model['position_target'])
    pop=checks(data['population'],formation_reference(source['population_holdout'],source['position_holdout'],positions,model['population_target']))
    reference=json.loads(baseline.read_text());defs={d[0]:d for d in audit.DEFINITIONS}
    flags=[];club_flags=[]
    for m in reference['metric_matrix']:
        d=defs[m['metric']]
        if m['validation']!='external_comparison':continue
        eligible=[role for role,v in m['roles'].items() if v['passed'] is not None]
        for role in eligible:
            v=m['roles'][role];actual=audit.value(roles[role],d)
            if actual is None or abs(actual-v['source_holdout'])>v['tolerance']:flags.append({'role':role,'metric':m['metric'],'actual':actual,'target':v['source_holdout']})
        if d[4] or d[2]=='Goalkeeping':continue
        original=next((c for c in reference['team_role_share_checks'] if c['metric']==m['metric']),None)
        if not original or original['reference_events']<30:continue
        for club in [c['club_id'] for c in registry['clubs'] if c['featured']]:
            group=teams[club]
            projected={r:m['roles'][r]['source_holdout']*group[r]['minutes']/90 for r in eligible}
            counts={r:group[r][d[3]] if d[0]!='goal_involvements' else group[r]['goals']+group[r]['assists'] for r in eligible}
            if sum(counts.values())<30 or not sum(projected.values()):continue
            for role in eligible:
                actual=counts[role]/sum(counts.values());expected=projected[role]/sum(projected.values())
                if abs(actual-expected)>audit.PROTOCOL['team_role_share_absolute_tolerance']:
                    club_flags.append({'club':club,'role':role,'metric':m['metric'],'actual':actual,'target':expected})
    result={'core_flags':{k:v for k,v in core.items() if not v['passed']},'population_flags':{k:v for k,v in pop.items() if not v['passed']},'extended_flags':flags,'club_flags':club_flags}
    (root.parent/'historical-preflight.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result));return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--fixtures',type=Path,required=True);p.add_argument('--baseline',type=Path,default=Path('docs/verification/player-position-audit-before-spatial.json'));a=p.parse_args();review(a.fixtures,a.baseline)
