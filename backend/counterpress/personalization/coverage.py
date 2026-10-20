"""Keep recorded values and their exposure separate from unavailable matches."""
from .metrics import rates


def metric_coverage(entries):
    """Entries contain fixture metadata and one subject's appearance statistics."""
    result={}
    for metric in ('assists','key_passes','saves','recoveries'):
        covered=[]
        for fixture,stats in entries:
            archive=fixture['source_kind']=='adapted_archive'
            known=(fixture.get('assist_basis','unavailable' if archive else 'direct_pass')!='unavailable' if metric=='assists' else
                   fixture.get('shot_assists_complete',not archive) if metric=='key_passes' else not archive)
            if known:covered.append(stats)
        result[metric]={'recorded_matches':len(covered),'total_matches':len(entries),
                        'covered_total':sum(s[metric] for s in covered),
                        'covered_minutes':round(sum(s['minutes'] for s in covered),6)}
    return result


def covered_rates(stats,coverage):
    result=rates(stats)
    minutes=coverage['assists']['covered_minutes']
    result['assists_per90']=round(coverage['assists']['covered_total']*90/minutes,4) if minutes else None
    if coverage['assists']['recorded_matches']!=coverage['assists']['total_matches']:
        result['goal_involvements_per90']=None
    return result
