"""Independent position/team audit of the full analytics catalogue.

Read-only. Does not fit the generator or publish source identities.
Version 1.2 adds explicit source-supported club-style adjudication after review.
Engineering envelopes are diagnostics, not proof of
statistical equivalence. All source inputs must match the existing provenance.
"""
from collections import Counter,defaultdict
from hashlib import sha256
from pathlib import Path
import argparse,gzip,json,math,sys
from random import Random

ROOT=Path(__file__).resolve().parents[1]
from counterpress.personalization.analytics import DEFINITIONS
from counterpress.personalization.positions import source_rows,position_checks,summarize
from counterpress.personalization.calibration import probability,pass_type

# Original numerical envelopes retained; the v1.2 adjudication revision is explicit.
PROTOCOL={
 'version':'extended-position-review-v1.2','minimum_individual_minutes':900,
 'rate_relative_tolerance':.35,'rate_absolute_floor_per90':.30,
 'percentage_absolute_tolerance_points':10,'mean_relative_tolerance':.25,
 'mean_distance_absolute_floor_m':3,'team_role_share_absolute_tolerance':.12,
 'individual_reference_quantiles':[.01,.99],'individual_envelope_expansion':.25,
 'minimum_source_pass_coverage':.95,'minimum_ratio_denominator':30,
 'minimum_individual_ratio_denominator':30,'minimum_reference_players':10,
 'bootstrap_replicates':400,'bootstrap_seed':20261021,
 'team_style_adjudication':{'source':'training clubs only','minimum_clubs':10,'minimum_matches_per_club':20,
    'minimum_metric_events_per_club':20,'quantiles':[.1,.9],
    'rule':'Retain every original +/-12pp flag; adjudicate only flags inside the empirical central 80% of exposure-standardized real-club shares. Other flags remain failures.',
    'revision':'Added after inspecting club-level failures; numerical envelopes unchanged. This is an acceptance-method revision, not a blind protocol.'},
}
# Comparable source definitions; exclude event types that the old source release
# does not measure in the same way. Model-based fields are reviewed separately.
GEOMETRY_KEYS={'progressive_passes_completed','final_third_entries','box_entries','long_passes','long_passes_completed','long_accuracy','forward_passes','backward_passes','lateral_passes','pass_distance'}
COMPLETION_KEYS={'passes_completed','passes_incomplete','progressive_passes_completed','long_passes_completed','final_third_entries','box_entries'}
COMPARABLE={
 'goals','non_penalty_goals','shots','shots_on_target','shots_off_target','shots_blocked',
 'shot_accuracy','conversion','shots_inside_box','shots_outside_box','shot_distance',
 'penalty_shots','penalty_goals','penalty_conversion','assists','goal_involvements',
 'passes','passes_completed','passes_incomplete','pass_accuracy','progressive_passes_completed',
 'final_third_entries','box_entries','long_passes','long_passes_completed','long_accuracy',
 'forward_passes','backward_passes','lateral_passes','pass_distance','crosses','crosses_completed','cross_accuracy',
 'duels','duels_won','duels_lost','duels_drawn','duel_win_pct','saves','save_pct','goals_conceded','clean_sheets','clean_sheet_pct'}
CAVEATS={
 'progressive_passes':'Failed source endpoints do not reliably identify intended targets; only completed progression is comparable.',
 'progressive_accuracy':'Attempted-progression denominator is not comparable without intended targets.',
 'key_passes':'Provider clear-chance tags and reconstructed direct shot assists are not equivalent.',
 'xa':'Derived from the CounterPress shot model and direct-pass chains, not a like-for-like source xA observation.',
 'passes_received':'The historical source has no explicit recipient IDs.',
 'actions':'Provider event coverage differs; this is not conventional touches.',
 'box_actions':'Provider event coverage differs; this is not conventional touches in the box.',
 'carries':'Sparse source accelerations/touches are not the same as continuous synthetic carry episodes.',
 'carry_distance_m':'No matched source continuous carry tracks.',
 'progressive_carries':'No matched source continuous carry tracks.',
 'carry_box_entries':'No matched source continuous carry tracks.',
 'recoveries':'Legacy source lacks equivalent explicit recovery ownership records.',
 'high_recoveries':'Legacy source lacks equivalent explicit recovery ownership records.',
 'mean_pass_speed':'Authored synthetic flight times, not externally measured speeds.',
 'mean_shot_speed':'Authored synthetic flight times, not externally measured speeds.',
 'headed_shots':'Unsupported and withheld from UI.', 'headed_goals':'Unsupported and withheld from UI.',
 'woodwork':'Unsupported and withheld from UI.',
 'appearances':'Schedule/participation bookkeeping, not an event rate to fit.',
 'starts':'Schedule/participation bookkeeping, not an event rate to fit.',
 'minutes':'Appearance exposure, not an event rate to fit.',
}
MODEL_KEYS={'xg','non_penalty_xg','xg_per_shot','goals_above_xg','expected_completions','expected_pass_accuracy','passing_above_expected'}


def q(values,p):
    a=sorted(values)
    if not a:return None
    x=(len(a)-1)*p;i=int(x)
    return a[i]+(a[min(i+1,len(a)-1)]-a[i])*(x-i)


def inside(p):return p[0]>=88.5 and 13.84<=p[1]<=54.16


def prog(a,b):
    threshold=30 if max(a[0],b[0])<52.5 else 15 if a[0]<52.5 else 10
    return math.hypot(105-a[0],34-a[1])-math.hypot(105-b[0],34-b[1])>=threshold-1e-9


def value(s,d):
    key,_,_,num,den,unit,_=d
    c=Counter(s)
    c['known_passes']=c['passes']-c['passes_unknown']
    c['known_duels']=c['duels']-c['duels_unknown']
    c['goal_involvements']=c['goals']+c['assists']
    c['goals_above_xg']=c['xg_goals']-c['xg']
    c['completion_surplus']=c['xpass_completed']-c['expected_completions']
    c['keeper_shots_faced']=c['saves']+c['goals_conceded']-c['own_goals_conceded']
    if den:return c[num]/c[den]*(100 if unit in ('percent','points') else 1) if c[den] else None
    if key in ('appearances','starts','minutes'):return c[num]
    return c[num]*90/c['minutes'] if c['minutes'] else None


def tolerance(target,d):
    if d[5] in ('percent','points'):return PROTOCOL['percentage_absolute_tolerance_points']
    if d[4]:return max(PROTOCOL['mean_distance_absolute_floor_m'] if d[5]=='metres' else .04,abs(target)*PROTOCOL['mean_relative_tolerance'])
    return max(PROTOCOL['rate_absolute_floor_per90'],abs(target)*PROTOCOL['rate_relative_tolerance'])


def denominator(s,d):
    key=d[4]
    if key=='known_passes':return s['passes']-s['passes_unknown']
    if key=='known_duels':return s['duels']-s['duels_unknown']
    if key=='keeper_shots_faced':return s['saves']+s['goals_conceded']-s['own_goals_conceded']
    return s[key] if key else None


def comparability(s,d):
    if d[0] in COMPLETION_KEYS and s['passes'] and (s['passes']-s['passes_unknown'])/s['passes']<PROTOCOL['minimum_source_pass_coverage']:
        return 'Source pass-outcome coverage below 95%; count rates are not comparable.'
    if d[0] in GEOMETRY_KEYS and s['passes'] and s['located_passes']/s['passes']<PROTOCOL['minimum_source_pass_coverage']:
        return 'Source reliable pass-geometry coverage below 95%; goal-kick corner sentinel origins excluded.'
    if d[4] and (denominator(s,d) or 0)<PROTOCOL['minimum_ratio_denominator']:
        return 'Source denominator below 30 observations.'
    return None


def bootstrap_reference(rows):
    clusters=[]
    for row in rows:
        grouped={r:Counter() for r in ('GK','DF','MF','FW')}
        for pid,v in row['players'].items():grouped[row['roles'][pid]].update(v)
        clusters.append(grouped)
    rng=Random(PROTOCOL['bootstrap_seed']);samples=defaultdict(list)
    for _ in range(PROTOCOL['bootstrap_replicates']):
        pooled={r:Counter() for r in ('GK','DF','MF','FW')}
        for group in rng.choices(clusters,k=len(clusters)):
            for r,c in group.items():pooled[r].update(c)
        for d in DEFINITIONS:
            if d[0] not in COMPARABLE:continue
            for r,c in pooled.items():
                if d[2]=='Goalkeeping' and r!='GK':continue
                v=value(c,d)
                if v is not None:samples[(d[0],r)].append(v)
    return {key:[q(v,.025),q(v,.975)] for key,v in samples.items()}


def source_data(events,matches,players,model):
    rows=source_rows(events,matches,players,model['training_match_ids']+model['holdout_match_ids'])
    by_id={int(r['id']):r for r in rows};meta={m['wyId']:m for m in matches}
    for row in rows:
        row['clubs']={str(p['playerId']):club for club,t in meta[int(row['id'])]['teamsData'].items() for p in t['formation']['lineup']+t['formation']['bench']}
        row['players']={pid:Counter(s) for pid,s in row['players'].items()}
        for s in row['players'].values():
            s['passes_unknown']=s['passes']-s['passes_known']
            s['passes_incomplete']=s['passes_known']-s['passes_completed']
            s['duels_lost']=0;s['duels_unknown']=0
    for e in events:
        row=by_id.get(e['matchId']);pid=str(e['playerId'])
        if not row or pid not in row['players'] or e['matchPeriod'] not in ('1H','2H'):continue
        s=row['players'][pid];tags={t['id'] for t in e['tags']};sub=e['subEventName']
        coords=[(p['x']*1.05,p['y']*.68) for p in e['positions']]
        ispass=e['eventName']=='Pass' or sub in ('Goal kick','Corner','Free Kick','Free kick cross')
        if sub in ('Ground attacking duel','Ground defending duel'):
            s['duels_lost']+=int(701 in tags)
            s['duels_unknown']+=int(not tags&{701,702,703})
        if ispass and sub!='Goal kick' and len(coords)==2:
            a,b=coords;length=math.dist(a,b);complete=1801 in tags;known=bool(tags&{1801,1802})
            s['located_passes']+=1;s['pass_distance_m']+=length
            s['long_passes']+=int(length>=32);s['long_passes_completed']+=int(length>=32 and complete);s['long_passes_known']+=int(length>=32 and known)
            s['progressive_passes_completed']+=int(complete and prog(a,b))
            s['final_third_entries']+=int(complete and a[0]<70<=b[0]);s['box_entries']+=int(complete and not inside(a) and inside(b))
            s['forward_passes' if b[0]-a[0]>5 else 'backward_passes' if b[0]-a[0]<-5 else 'lateral_passes']+=1
            cross=sub in ('Cross','Free kick cross') or sub=='Corner' and inside(b)
            s['crosses']+=int(cross);s['crosses_completed']+=int(cross and complete);s['crosses_known']+=int(cross and known)
            s['pass_origin_x_sum']+=a[0];s['pass_origin_y_sum']+=a[1]
            s['pass_origins_own_third']+=int(a[0]<35)
            if known:
                s['expected_completions']+=probability(model,'pass',a,pass_type(sub));s['xpass_passes']+=1;s['xpass_completed']+=int(complete)
        shot=e['eventName']=='Shot' or sub in ('Penalty','Free kick shot')
        if shot:
            goal=101 in tags;penalty=sub=='Penalty'
            s['penalty_shots']+=penalty;s['penalty_goals']+=int(penalty and goal);s['non_penalty_goals']+=int(not penalty and goal)
            blocked=2101 in tags;on_target=bool(goal or tags&set(range(1201,1210))) and not blocked
            s['shots_blocked']+=blocked;s['shots_off_target']+=int(not blocked and not on_target)
            if coords:
                a=coords[0];s['shots_inside_box' if inside(a) else 'shots_outside_box']+=1
                s['located_shots']+=1;s['shot_distance_m']+=math.hypot(105-a[0],34-a[1])
                xg=probability(model,'shot',a);s['xg']+=xg;s['xg_shots']+=1;s['xg_goals']+=goal;s['non_penalty_xg']+=0 if penalty else xg
        if 102 in tags:
            for keeper,counts in row['players'].items():
                if row['roles'][keeper]=='GK' and row['clubs'].get(keeper)==str(e['teamId']):counts['own_goals_conceded']+=1
    return rows


def totals(rows):
    roles={r:Counter() for r in ('GK','DF','MF','FW')};people=defaultdict(Counter);teams=defaultdict(lambda:defaultdict(Counter));person_meta={}
    for row in rows:
        for pid,s in row['players'].items():
            role=row['roles'][pid];club=row['clubs'][pid]
            roles[role].update(s);people[pid].update(s);teams[club][role].update(s);person_meta[pid]={'role':role,'club':club}
    return roles,people,teams,person_meta


def extended_checks(role_counts,reference):
    """Apply the same declared envelopes to an independent simulation population."""
    checks={}
    for d in DEFINITIONS:
        if d[0] not in COMPARABLE:continue
        for role,counts in role_counts.items():
            if d[2]=='Goalkeeping' and role!='GK' or comparability(reference[role],d):continue
            actual=value(Counter(counts),d);target=value(reference[role],d)
            if actual is None or target is None:continue
            envelope=tolerance(target,d)
            checks[f'{role}.{d[0]}']={'actual':actual,'target':target,'tolerance':envelope,'passed':abs(actual-target)<=envelope}
    return checks


def club_style_reference(teams,match_counts,d,minutes,eligible):
    """Real-team style variation, standardized to the same role exposure.

    These empirical ranges are not confidence intervals or proof of equivalence.
    Sparse source teams/metrics cannot adjudicate a failed mean-share check.
    """
    spec=PROTOCOL['team_style_adjudication'];shares={r:[] for r in eligible}
    for club,groups in teams.items():
        if match_counts[club]<spec['minimum_matches_per_club']:continue
        if any(not groups[r]['minutes'] or comparability(groups[r],d) for r in eligible):continue
        counts={r:groups[r]['goals']+groups[r]['assists'] if d[0]=='goal_involvements' else groups[r][d[3]] for r in eligible}
        if sum(counts.values())<spec['minimum_metric_events_per_club']:continue
        projected={r:counts[r]/groups[r]['minutes']*minutes[r] for r in eligible}
        total=sum(projected.values())
        if not total:continue
        for role in eligible:shares[role].append(projected[role]/total)
    return {r:{'source_clubs':len(values),'central_80_range':[q(values,p) for p in spec['quantiles']],
               'eligible':len(values)>=spec['minimum_clubs'],'source':'training_only'} for r,values in shares.items()}


def audit(source_path,output,root=None,analytics_path=None):
    root=root or ROOT/'fixtures/personalization'
    analytics_path=analytics_path or ROOT/'fixtures/analytics/players.json.gz'
    model=json.loads((root/'model.json').read_text())
    source={}
    for name in ('events_England','matches_England','players'):
        raw=(source_path/(name+'.json')).read_bytes()
        if sha256(raw).hexdigest()!=model['provenance']['sha256'][name]:raise ValueError('Source provenance mismatch: '+name)
        source[name]=json.loads(raw)
    source_rows_all=source_data(source['events_England'],source['matches_England'],source['players'],model)
    train=[r for r in source_rows_all if int(r['id']) in model['training_match_ids']]
    held=[r for r in source_rows_all if int(r['id']) in model['holdout_match_ids']]
    reference,people,source_teams,meta=totals(train);holdout,*_=totals(held)
    source_club_matches=Counter(club for row in train for club in set(row['clubs'].values()))
    artifact=json.loads(gzip.decompress(analytics_path.read_bytes()))
    ledger=json.loads(gzip.decompress((root/'ledger.json.gz').read_bytes()))
    registry=json.loads((root/'registry.json').read_text());player_meta={p['player_id']:p for p in registry['players']}
    generated=[];errors=[];checked=0
    for row in ledger:
        f=row['fixture'];item=artifact['matches'][f['match_id']]
        assert item['digest']==row['event_digest']
        for pid,p in item['players'].items():
            s=Counter(p['stats']);checked+=1
            equations={
              'passes_partition':s['passes']==s['passes_completed']+s['passes_incomplete']+s['passes_unknown'],
              'shot_partition':s['shots']==s['shots_on_target']+s['shots_off_target']+s['shots_blocked'],
              'duel_partition':s['duels']==s['duels_won']+s['duels_lost']+s['duels_drawn']+s['duels_unknown'],
              'penalty_partition':s['goals']==s['penalty_goals']+s['non_penalty_goals'],
              'heatmap':s['actions']==sum(p['heat'].values()),
              'territory':s['actions']==s['own_third_actions']+s['middle_third_actions']+s['final_third_actions'],
              'shotmap':len(p['shots'])==s['shots_inside_box']+s['shots_outside_box'],
              'goal_timing':sum(p['timing'])==s['goals'],
              'passing_routes':sum(p['routes'].values())==s['located_passes'],
              'pass_directions':s['forward_passes']+s['backward_passes']+s['lateral_passes']==s['located_passes'],
              'subset_counts':all(s[a]<=s[b] for a,b in [('goals','shots'),('saves','saves'),('penalty_goals','penalty_shots'),('progressive_passes_completed','passes_completed'),('box_entries','passes_completed'),('final_third_entries','passes_completed'),('crosses_completed','crosses'),('long_passes_completed','long_passes'),('progressive_carries','carries')]),
              'nonnegative_counts':all(v>=0 and math.isfinite(v) for v in s.values()),
            }
            errors.extend({'match':f['match_id'],'player':pid,'check':k} for k,v in equations.items() if not v)
        if f['source_kind']=='calibrated_simulation':
            generated.append({'id':f['match_id'],'players':{p:dict(v['stats']) for p,v in item['players'].items()},
                'roles':{p:player_meta[p]['role'] for p in item['players']},'clubs':{p:player_meta[p]['club_id'] for p in item['players']}})
    observed,subjects,teams,subjects_meta=totals(generated)
    intervals=bootstrap_reference(held)
    matrix=[];club_flags=[];individual_flags=[];club_checks=[]
    for row in generated:
        for st in row['players'].values():
            st['passes_known']=st['passes']-st['passes_unknown']
            st['shots_faced']=st['saves']+st['goals_conceded']-st.get('own_goals_conceded',0)
            st['completed_long']=st.get('long_passes_completed',0)
            st['completed_located']=st['passes_completed']
    baseline_report=json.loads((root/'calibration-report.json').read_text())
    core_checks=position_checks(summarize(generated),baseline_report['position_holdout'],model['position_target'])
    for d in DEFINITIONS:
        key=d[0];status='external_comparison' if key in COMPARABLE else 'model_diagnostic' if key in MODEL_KEYS else 'not_external'
        row={'metric':key,'label':d[1],'category':d[2],'validation':status,'note':CAVEATS.get(key),'roles':{}}
        for role in observed:
            if d[2]=='Goalkeeping' and role!='GK':continue
            actual=value(observed[role],d);target=value(holdout[role],d);training=value(reference[role],d)
            reason=comparability(holdout[role],d) if status=='external_comparison' else None
            tolerance_value=tolerance(target,d) if target is not None and status=='external_comparison' and reason is None else None
            eligible=[value(s,d) for p,s in people.items() if meta[p]['role']==role and s['minutes']>=900 and (not d[4] or (denominator(s,d) or 0)>=30)]
            eligible=[v for v in eligible if v is not None]
            ours=[value(s,d) for p,s in subjects.items() if subjects_meta[p]['role']==role and s['minutes']>=900]
            ours=[v for v in ours if v is not None]
            passed=abs(actual-target)<=tolerance_value if actual is not None and target is not None and tolerance_value is not None else None
            row['roles'][role]={'observed':actual,'source_holdout':target if status!='not_external' else None,'source_training':training if status!='not_external' else None,
                'tolerance':tolerance_value,'passed':passed,'comparison_limit':reason,
                'source_holdout_ci95':intervals.get((key,role)) if status=='external_comparison' and reason is None else None,'individual_p10_p50_p90':[q(ours,v) for v in (.1,.5,.9)],
                'source_individual_p10_p50_p90':[q(eligible,v) for v in (.1,.5,.9)] if status=='external_comparison' else None}
            if status=='external_comparison' and len(eligible)>=10 and reason is None:
                lo,hi=q(eligible,.01),q(eligible,.99);extra=max(.3,(hi-lo)*.25) if d[5]!='percent' else 5
                for p,s in subjects.items():
                    if not player_meta[p]['featured'] or subjects_meta[p]['role']!=role or s['minutes']<900 or d[4] and (denominator(s,d) or 0)<30:continue
                    v=value(s,d)
                    if v is not None and (v<lo-extra or v>hi+extra):
                        individual_flags.append({'player':p,'role':role,'metric':key,'value':v,'reference_envelope':[lo-extra,hi+extra]})
        matrix.append(row)
        if status=='external_comparison' and not d[4] and d[2]!='Goalkeeping':
            for club,groups in teams.items():
                if club not in {c['club_id'] for c in registry['clubs'] if c['featured']}:continue
                comparable_roles=[r for r in observed if comparability(holdout[r],d) is None]
                styles=club_style_reference(source_teams,source_club_matches,d,{r:groups[r]['minutes'] for r in comparable_roles},comparable_roles)
                projected={r:(value(holdout[r],d) or 0)*groups[r]['minutes']/90 for r in comparable_roles}
                total=sum(groups[r][d[3]] if key!='goal_involvements' else groups[r]['goals']+groups[r]['assists'] for r in comparable_roles)
                for r in comparable_roles:
                    numerator=groups[r][d[3]] if key!='goal_involvements' else groups[r]['goals']+groups[r]['assists']
                    expected=projected[r]/sum(projected.values()) if sum(projected.values()) else None
                    share=numerator/total if total else None
                    reference_count=sum(holdout[role][d[3]] if key!='goal_involvements' else holdout[role]['goals']+holdout[role]['assists'] for role in comparable_roles)
                    valid=reference_count>=30 and total>=30
                    check={'club':club,'role':r,'metric':key,'share':share,'reference_share':expected,'tolerance':.12,'included_roles':comparable_roles,
                           'reference_events':reference_count,'observed_events':total,
                           'passed':abs(share-expected)<=.12 if valid and share is not None and expected is not None else None}
                    club_checks.append(check)
                    if check['passed'] is False:
                        style=styles[r];lo,hi=style['central_80_range']
                        check['source_style_reference']=style
                        check['source_supported_style']=bool(style['eligible'] and lo<=share<=hi)
                        club_flags.append(check)
    team_reconciliation=[]
    for row in ledger:
        f=row['fixture'];players=artifact['matches'][f['match_id']]['players']
        for club in (f['home_id'],f['away_id']):
            own=Counter();opponent=Counter()
            for pid,v in players.items():(own if player_meta[pid]['club_id']==club else opponent).update(v['stats'])
            checks={'goal_conservation':own['goals']+opponent['own_goals']==row['summary']['score'][club],
                'assists_le_goals':own['assists']<=own['goals'],
                'shot_assists_le_shots':own['key_passes']<=own['shots'],
                'xa_le_xg':own['xa']<=own['xg']+1e-5}
            if f['source_kind']=='calibrated_simulation':
                checks.update({'received_passes':own['passes_received']==own['passes_completed'],
                    'duel_symmetry':own['duels_won']==opponent['duels_lost'],
                    'draw_symmetry':own['duels_drawn']==opponent['duels_drawn'],
                    'save_shot_conservation':opponent['shots_on_target']==own['saves']+opponent['goals']})
            team_reconciliation.extend({'match':f['match_id'],'club':club,'check':k} for k,v in checks.items() if not v)
    report={'protocol':PROTOCOL,'source':{'training_matches':len(train),'holdout_matches':len(held),'reused_holdout':True,'competition':'England 2017/18','provenance':model['provenance']},
      'dataset':{'matches':len(ledger),'calibrated_matches':len(generated),'player_match_rows':checked,'featured_players':44,'metric_definitions':len(DEFINITIONS)},
      'arithmetic_errors':errors,'team_reconciliation_errors':team_reconciliation,'core_position_checks':core_checks,
      'metric_matrix':matrix,'team_role_share_checks':club_checks,'team_role_share_flags':club_flags,'individual_flags':individual_flags,
      'reviewed_team_style_variations':[c for c in club_flags if c['source_supported_style']],
      'unresolved_team_role_share_flags':[c for c in club_flags if not c['source_supported_style']],
      'population_flags':[{'metric':r['metric'],'role':role,**v} for r in matrix for role,v in r['roles'].items() if v['passed'] is False],
      'unbenchmarked_metrics':[r['metric'] for r in matrix if r['validation']=='not_external'],
      'model_diagnostics':[r['metric'] for r in matrix if r['validation']=='model_diagnostic'],
      'source_quality':{'goal_kick_origin_values':[[0,0],[100,100]],'goal_kick_geometry_excluded':True,
          'goal_kick_outcomes':'All source goal kicks lack completion tags; missing is not failure.',
          'protocol_revision':'v1.1 corrects source geometry/outcome comparability and minimum denominator eligibility; numeric tolerance envelopes are unchanged from v1. Initial results retained in ignored var/player-position-audit-initial.json.'},
      'featured_club_position_values':{club:{role:{d[0]:value(groups[role],d) for d in DEFINITIONS if d[2]!='Goalkeeping' or role=='GK'} for role in observed} for club,groups in teams.items() if club in {c['club_id'] for c in registry['clubs'] if c['featured']}},
      'featured_profiles':{p:{'name':player_meta[p]['name'],'role':subjects_meta[p]['role'],'club':subjects_meta[p]['club'],'minutes':s['minutes'],
          'values':{d[0]:value(s,d) for d in DEFINITIONS if d[0] in COMPARABLE|MODEL_KEYS}} for p,s in subjects.items() if player_meta[p]['featured']},
      'prior_position_report_sha256':sha256((root/'position-validation.json').read_bytes()).hexdigest(),
      'analytics_sha256':sha256(analytics_path.read_bytes()).hexdigest(),
      'input_sha256':{name:sha256((root/name).read_bytes()).hexdigest() for name in ('model.json','ledger.json.gz','registry.json')}}
    report['status']='needs_recalibration' if report['population_flags'] or report['unresolved_team_role_share_flags'] or individual_flags or errors or team_reconciliation or not all(v['passed'] for v in core_checks.values()) else 'passed_with_coverage_limits'
    if model.get('spatial'):
        independent=json.loads((root/'position-validation.json').read_text())
        populations={'pooled':independent['pooled_validation'],**{f'batch{i+1}':b['observed'] for i,b in enumerate(independent['validation_batches'])}}
        report['independent_simulation_checks']={name:extended_checks({r:v['counts'] for r,v in pop['roles'].items()},holdout) for name,pop in populations.items()}
        report['independent_simulation_flags']=[f'{name}.{key}' for name,checks in report['independent_simulation_checks'].items() for key,v in checks.items() if not v['passed']]
        report['independent_seed_ranges']=independent['seed_ranges']
        if report['independent_simulation_flags']:report['status']='needs_recalibration'
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'matches':len(ledger),'player_match_rows':checked,'metrics':len(DEFINITIONS),'arithmetic_errors':len(errors),'team_reconciliation_errors':len(team_reconciliation),
        'core_position_passed':sum(v['passed'] for v in core_checks.values()),'core_position_checks':len(core_checks),
        'external_role_checks':sum(v['passed'] is not None for r in matrix for v in r['roles'].values()),'population_flags':len(report['population_flags']),
        'team_role_share_flags':len(club_flags),'reviewed_team_style_variations':len(report['reviewed_team_style_variations']),
        'unresolved_team_role_share_flags':len(report['unresolved_team_role_share_flags']),
        'individual_flags':len(individual_flags),'independent_flags':len(report.get('independent_simulation_flags',[])),
        'report':str(output.relative_to(ROOT)),'status':report['status']}))
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--strict',action='store_true',help='Exit 1 when the report has unresolved flags.')
    parser.add_argument('--fixtures',type=Path,default=ROOT/'fixtures/personalization')
    parser.add_argument('--analytics',type=Path,default=ROOT/'fixtures/analytics/players.json.gz')
    parser.add_argument('--output',type=Path,default=ROOT/'docs/verification/player-position-audit.json')
    args=parser.parse_args()
    result=audit(ROOT/'var/personalization-source',args.output.resolve(),args.fixtures,args.analytics)
    sys.exit(1 if args.strict and result['status']=='needs_recalibration' else 0)
