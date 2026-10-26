"""Immutable cutoff-bound snapshots and bounded specialist evidence packets."""
from hashlib import sha256
import json

from counterpress.personalization.contracts import Fixture, MatchRecord
from counterpress.personalization.metrics import select_events, reduce_record
from .contracts import AnalystRequest, MATCH_IDS, ROLES, TRIGGER_TYPES
from .candidates import build_candidates
from .metrics import VERSION, METHODS, COMPLETE, CONTROLLED, geometric_xg, metric_rows, threat, turns


def _hash(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def _eid(e): return f'{e.event_id}:r{e.revision}'


def _signals(events, current, previous, rows, fixture, names, request):
    result=[]
    index={r['id']:r for r in rows}
    def v(c,key,w='current'):
        return index.get(f'{w}:{c}:{key}',{}).get('value')
    def add(key,club,title,detail,role,proof,keys,salience=.65):
        refs=list(dict.fromkeys(_eid(e) for e in proof))[-12:]
        mids=[f'{w}:{club}:{k}' for w,k in keys]
        if not refs or any(mid not in index for mid in mids): return
        result.append({'id':f'{key}:{club}', 'title':title,'detail':detail,'evidence_ids':refs,
            'metric_ids':mids,'role':role,'salience':salience})
    complete_windows=request.cutoff.elapsed_ms>=600000
    for club in (fixture.home_id,fixture.away_id):
        own=[e for e in current if e.club_id==club]
        shots=[e for e in own if e.kind=='shot' and e.outcome!='own_goal']
        before=[e for e in previous if e.club_id==club and e.kind=='shot' and e.outcome!='own_goal']
        inside=[e for e in shots if e.start and e.start.x>=88.5 and 13.84<=e.start.y<=54.16]
        if complete_windows and len(shots)>=3 and len(shots)>=len(before)+2 and len(inside)>=2:
            add('closer_chances',club,f'{names[club]} are creating more shooting opportunities',
                f'{len(shots)} shots in the last five minutes versus {len(before)} before; {len(inside)} came from inside the box. The higher shot count includes attempts from inside the box. Watch whether the next attacks keep reaching the box.',
                'chance',shots+before,[('current','shots'),('previous','shots'),('current','shot_map')],.85)
        if len(shots)>=3 and len([e for e in shots if e.start])==len(shots) and not inside:
            add('outside_shots',club,f'{names[club]} are shooting from distance',
                f'All {len(shots)} recent shots came from outside the box. Shot volume alone is not evidence of closer chances; watch for a pass or carry into the box.',
                'chance',shots,[('current','shots'),('current','shot_map')],.7)
        if sum(e.kind in ('pass','shot') or e.kind=='carry' and e.outcome in CONTROLLED for e in own)>=12 and (v(club,'event_share') or 0)>=65 and not shots and v(club,'final_third_entries')==0:
            add('control_without_entry',club,f'{names[club]} have activity, but little penetration',
                'They have at least 65% of recorded on-ball actions in this window, but no shots or completed passes crossing into the final third. This is an action-share comparison, not possession time. Watch for a forward entry.',
                'control',own,[('current','event_share'),('current','shots'),('current','final_third_entries')],.72)
        if complete_windows:
            a,b=v(club,'pass_accuracy'),v(club,'pass_accuracy','previous')
            ca=index[f'current:{club}:pass_accuracy'].get('coverage',{})
            cb=index[f'previous:{club}:pass_accuracy'].get('coverage',{})
            if a is not None and b is not None and ca.get('numerator',0)>=10 and cb.get('numerator',0)>=10 and a<=b-15 and ca.get('numerator')==ca.get('denominator') and cb.get('numerator')==cb.get('denominator'):
                add('passing_fell',club,f'{names[club]} are losing fluency',
                    f'Pass completion has fallen from {b:.1f}% to {a:.1f}% across two five-minute windows. The lower success rate means fewer attempted passes reach a teammate; watch whether the next possessions restore continuity.',
                    'control',[e for e in own if e.kind=='pass' and e.outcome=='incomplete'],[('current','pass_accuracy'),('previous','pass_accuracy')],.78)
        # Strict contiguous regained-possession chain; actors must link, never infer through a gap/restart/duel.
        for lost,recovery in (turns(current) if fixture.source_kind!='adapted_archive' else []):
            if recovery.club_id!=club: continue
            start=current.index(recovery); chain=[lost,recovery]; holder=recovery.player_id
            for e in current[start+1:]:
                if e.period!=recovery.period or e.elapsed_ms-recovery.elapsed_ms>15000 or e.restart or e.club_id!=club or e.player_id!=holder: break
                chain.append(e)
                if e.kind=='shot' and e.outcome!='own_goal':
                    add('turnover_chance',club,f'{names[club]} turned a loose pass into a chance',
                        f'An opponent’s incomplete pass was followed by a recovery and a linked shot within {(e.elapsed_ms-recovery.elapsed_ms)/1000:g} seconds. That sequence shows a dangerous transition, rather than sustained pressure. Watch whether the opponent protects the next pass.',
                        'defence',chain,[('current','verified_turnovers'),('current','shots')],.9)
                    break
                if e.kind=='pass' and e.outcome in COMPLETE and e.recipient_id: holder=e.recipient_id
                elif e.kind=='carry' and e.outcome in CONTROLLED: pass
                else: break
        focused=[e for e in own if e.player_id==request.focus_player_id]
        if request.focus_player_id and len(focused)>=5 and any(e.kind=='shot' for e in focused):
            add('focus_involvement',club,'Your followed player is involved in the attack',
                f'The followed player has {len(focused)} recorded actions in this window, including a shot. That links involvement to a shooting opportunity; watch whether teammates continue finding them.',
                'players',focused,[('current','on_ball_actions'),('current','shots')],.7)
    return sorted(result,key=lambda r:(-r['salience'],r['id']))[:8]


def build_snapshot(career, match_id: str, request: AnalystRequest) -> dict:
    """Build from one consistent store read. Raises KeyError/ValueError for invalid scope.

    Delivery caps apply BEFORE latest-revision selection. Availability and occurrence
    must both be at/before cutoff. No model, network or cloud mutation occurs here.
    """
    if match_id not in MATCH_IDS: raise KeyError('Match not available in Analyst Mode')
    if not isinstance(request,AnalystRequest): request=AnalystRequest.model_validate(request)
    store=career.store
    with store.snapshot():
        fixture=Fixture.model_validate_json(store.row(match_id)['fixture'])
        cutoff=(request.cutoff.period,request.cutoff.elapsed_ms)
        if cutoff[1]>fixture.period_lengths_ms[cutoff[0]-1]: raise ValueError('Cutoff outside period')
        roster={a.player_id:a for a in fixture.appearances}
        if request.focus_player_id and request.focus_player_id not in roster: raise ValueError('Focus player outside match')
        raw=list(store.events(match_id))
        if request.through_sequence is not None and request.through_sequence>max((e.delivery_sequence for e in raw),default=0):
            raise ValueError('Delivery sequence outside received history')
        capped=[e for e in raw if request.through_sequence is None or e.delivery_sequence<=request.through_sequence]
        events=[e for e in select_events(capped,cutoff) if (e.period,e.elapsed_ms)<=cutoff]
        through=max((e.delivery_sequence for e in capped if (e.available_period,e.available_ms)<=cutoff),default=0)
        clubs=[{'club_id':c,'name':store.clubs[c].name} for c in (fixture.home_id,fixture.away_id)]
        players=[{'player_id':pid,'name':store.players[pid].name,'role':getattr(store.players[pid],'role',None),'club_id':a.club_id} for pid,a in roster.items()]
    period,end=cutoff
    windows={'prefix':{'period':None,'start_ms':0,'end_ms':sum(fixture.period_lengths_ms[:period-1])+end,'boundary':'through_cutoff'},
        'current':{'period':period,'start_ms':max(0,end-300000),'end_ms':end,'boundary':'(start,end]'},
        'previous':{'period':period,'start_ms':max(0,end-600000),'end_ms':max(0,end-300000),'boundary':'(start,end]'}}
    scopes={'prefix':events}
    for w in ('current','previous'):
        span=windows[w]
        scopes[w]=[e for e in events if e.period==period and span['start_ms']<e.elapsed_ms<=span['end_ms']]
    rows=[]
    record=MatchRecord(fixture=fixture,events=tuple(events))
    # Existing assist accounting is reused, keeping source awards and sequence rules consistent.
    for w,selected in scopes.items():
        span=windows[w];duration=span['end_ms']-span['start_ms']
        summary=reduce_record(record,cutoff,None if w=='prefix' else (period,span['start_ms']))
        if w=='previous':
            summary=reduce_record(record,(period,span['end_ms']),(period,span['start_ms']))
        for club in (fixture.home_id,fixture.away_id):
            rows.extend(metric_rows(selected,club_id=club,window=w,duration_ms=duration,all_events=selected,source_kind=fixture.source_kind))
            for key,label in [('assists','Assists'),('key_passes','Shot-creating passes'),('saves','Saves')]:
                available=fixture.assist_basis!='unavailable' if key=='assists' else fixture.shot_assists_complete if key=='key_passes' else fixture.source_kind!='adapted_archive'
                rows.append({'id':f'{w}:{club}:{key}','key':key,'window':w,'club_id':club,'label':label,'unit':'count','basis':'recorded_events' if available else 'unavailable','status':'available' if available else 'unavailable','value':summary['clubs'][club][key] if available else None,'role':'chance' if key!='saves' else 'defence','method':'counts'})
        if w=='prefix':
            for p in players:
                rows.extend(metric_rows(selected,club_id=p['club_id'],player_id=p['player_id'],window=w,duration_ms=duration,all_events=selected,source_kind=fixture.source_kind))
                for key,label in [('assists','Assists'),('key_passes','Shot-creating passes'),('saves','Saves')]:
                    available=fixture.assist_basis!='unavailable' if key=='assists' else fixture.shot_assists_complete if key=='key_passes' else fixture.source_kind!='adapted_archive'
                    rows.append({'id':f'{w}:{p["player_id"]}:{key}','key':key,'window':w,'club_id':p['club_id'],'player_id':p['player_id'],'label':label,'unit':'count','basis':'recorded_events' if available else 'unavailable','status':'available' if available else 'unavailable','value':summary['players'][p['player_id']][key] if available else None,'role':'players','method':'counts'})
        if w=='current':
            for p in players:
                for metric in metric_rows(selected,club_id=p['club_id'],player_id=p['player_id'],window=w,duration_ms=duration,all_events=selected,source_kind=fixture.source_kind):
                    if metric['key'] in {'on_ball_actions','shots'}: rows.append(metric)
        for row in rows:
            if row['window']==w and row['key']=='duels_won':
                row['value']=(summary['players'][row['player_id']] if row.get('player_id') else summary['clubs'][row['club_id']])['duels_won']
        a=threat([e for e in selected if e.club_id==fixture.home_id]);b=threat([e for e in selected if e.club_id==fixture.away_id])
        rows.append({'id':f'{w}:match:momentum','key':'momentum','window':w,'label':'Threat balance','unit':'index','basis':'uncalibrated_heuristic','status':'available' if selected else 'unavailable','value':round((a-b)/(a+b+1),6) if selected else None,'role':'control','method':'momentum'})
    score={c:sum(e.goal_for==c for e in events) for c in (fixture.home_id,fixture.away_id)}
    candidates=build_candidates(fixture=fixture,events=events,request=request,rows=rows,players=players,clubs=clubs,score=score,windows=windows)
    original_signals=_signals(events,scopes['current'],scopes['previous'],rows,fixture,{c['club_id']:c['name'] for c in clubs},request)
    signals=[{'id':'support:'+c['id'],'role':c['role'],'title':c['reading']['headline'],'detail':c['reading']['explanation'],'evidence_ids':c['reading']['evidence_ids'],'metric_ids':c['reading']['metric_ids'],'salience':.95}for c in candidates]
    candidate_refs={ref for c in candidates for ref in c['reading']['evidence_ids']}
    for sig in original_signals:
        if len(candidate_refs|set(sig['evidence_ids']))<=64:
            signals.append(sig);candidate_refs.update(sig['evidence_ids'])
    wanted={ref for s in signals for ref in s['evidence_ids']}
    selected_evidence=[e for e in events if _eid(e) in wanted]
    if len(selected_evidence)>64:raise ValueError('Candidate evidence exceeds bounded snapshot')
    for e in reversed(events):
        if len(selected_evidence)>=64:break
        if _eid(e) not in wanted:selected_evidence.append(e);wanted.add(_eid(e))
    selected_evidence.sort(key=lambda e:(e.period,e.elapsed_ms,e.occurrence_order))
    evidence=[{'id':_eid(e),**{k:getattr(e,k) for k in ('event_id','revision','delivery_sequence','period','elapsed_ms','available_period','available_ms','club_id','player_id','kind','outcome')},'start':e.start.model_dump() if e.start else None,'end':e.end.model_dump() if e.end else None} for e in selected_evidence]
    triggers=_triggers(scopes,rows,fixture,request)
    result={'match_id':match_id,'cutoff':request.cutoff.model_dump(),'through_sequence':through,
        'language':request.language,'depth':request.depth,'focus_player_id':request.focus_player_id,
        'momentum':momentum_series(capped,fixture,request),'clubs':clubs,'score':score,'players':players,'candidates':candidates,'period_lengths_ms':{str(i+1):v for i,v in enumerate(fixture.period_lengths_ms)},'metrics':rows,'evidence':evidence,'signals':signals,
        'windows':windows,'methods':dict(METHODS),'triggers':triggers,
        'coverage':{'visible_events':len(events),'evidence_events':len(evidence),'tracking':'unavailable','source_kind':fixture.source_kind},'metric_version':VERSION}
    result['snapshot_id']=_hash({'version':VERSION,'request':request.model_dump()|{'through_sequence':through},'fixture':fixture.model_dump(mode='json'),'events':[e.model_dump(mode='json') for e in events],'through_sequence':through})
    return result


def build_agent_packet(snapshot:dict, role:str) -> dict:
    """Small, role-scoped packet; excludes full shot maps and team/player heatmaps."""
    if role not in ROLES:raise ValueError('Unknown specialist role')
    signals=[s for s in snapshot['signals'] if s['role']==role]
    required={m for s in signals for m in s['metric_ids']}
    metrics=[m for m in snapshot['metrics'] if m['id'] in required or (m['role']==role and not isinstance(m['value'],dict) and (not m.get('player_id') or m['player_id']==snapshot.get('focus_player_id')))]
    # Required objects retain exact supporting evidence; other large spatial objects stay in UI response.
    selected_ids={r for s in signals for r in s['evidence_ids']}
    evidence=[e for e in snapshot['evidence'] if e['id'] in selected_ids]
    evidence.extend(e for e in snapshot['evidence'] if e['id'] not in selected_ids)
    result={k:snapshot[k] for k in ('snapshot_id','match_id','cutoff','through_sequence','language','depth','focus_player_id','clubs','score','players','windows','metric_version')}
    result.update(role=role,metrics=metrics,evidence=evidence[:64],signals=signals,
        methods={k:v for k,v in snapshot['methods'].items() if k in {m.get('method') for m in metrics}})
    return result


def _triggers(scopes,rows,fixture,request):
    """Reference-family coverage without claiming unsupported event subtypes."""
    index={m['id']:m for m in rows}
    def val(w,c,k):return index.get(f'{w}:{c}:{k}',{}).get('value')
    recent=scopes['current'];prefix=scopes['prefix'];period=request.cutoff.period;ms=request.cutoff.elapsed_ms
    goals=[e for e in recent if e.goal_for and e.elapsed_ms>=ms-30000]
    completed=[e for e in recent if e.kind=='pass' and e.outcome in COMPLETE]
    combo=0;longest=0;last=None
    for e in recent:
        linked=last and e.club_id==last.club_id and e.period==last.period and not e.restart and e.player_id==last.recipient_id and e.elapsed_ms-last.elapsed_ms<=15000
        if e.kind=='pass' and e.outcome in COMPLETE and e.recipient_id:
            combo=combo+1 if linked else 1;last=e;longest=max(longest,combo)
        else:combo=0;last=None
    from .metrics import difficulty,distance
    statuses={
        'pass_combo':('available',longest>=12,'At least 12 recipient-linked completed passes, with no restart or interruption.'),
        'great_pass':('available',any((difficulty(e) or 0)>=.68 and (distance(e) or 0)>=32 for e in completed),'Completed pass length at least32m and geometry difficulty at least.68; uncalibrated heuristic.'),
        'big_chance':('available',any(e.kind=='shot' and e.outcome not in {'goal','own_goal'} and e.expected_goal_probability is not None and e.expected_goal_probability>=.22 for e in recent),'Authored source xG at least.22 for a non-goal shot; geometry estimate is never substituted.'),
        'goal':('available',bool(goals),'A visible scoring event within30 seconds; contextual signals still require more than event narration.'),
        'pressure_spike':('unsupported',False,'Current canonical recoveries/duels do not establish the specific tackle/interception trigger.'),
        'card':('unsupported',False,'No canonical authoritative card events.'),
        'substitution':('unsupported',False,'Appearance intervals are metadata, not revisioned substitution events.'),
        'half_time':('available',period==1 and ms==fixture.period_lengths_ms[0],'Explicit end of first period.'),
        'full_time':('available',period==2 and ms==fixture.period_lengths_ms[1],'Explicit end of final period.'),
        'stat_check':('available',True,'Requested as-of snapshot; no automatic model dispatch.'),
        'milestone':('available',any(sum(e.kind=='pass' and e.player_id==p.player_id for e in prefix) in {50,75,100} for p in fixture.appearances),'Recorded match-pass milestones50/75/100, not career milestones.'),
    }
    a=val('current','match','momentum');b=val('previous','match','momentum')
    statuses['momentum_swing']=('available',ms>=600000 and a is not None and b is not None and (a>=.35 and b<.35 or a<=-.35 and b>-.35),'Two complete same-half five-minute threat windows crossing±.35; uncalibrated.')
    shift=False
    for c in (fixture.home_id,fixture.away_id):
        a=val('current',c,'tempo');b=val('previous',c,'tempo')
        if ms>=900000 and a is not None and b and (a/b>1.3 or a/b<.72):shift=True
    statuses['tempo_shift']=('available',shift,'After15 minutes in the half: distinct on-ball action-rate ratio>1.3 or<.72 versus previous five minutes.')
    chaos=val('current',fixture.home_id,'chaos')
    statuses['chaos_phase']=('available' if chaos is not None else 'insufficient_data',ms>=300000 and chaos is not None and chaos>.6,'Verified turnover index above.6 in a complete five-minute window; not emotional match chaos.')
    statuses['control_phase']=('available',ms>=300000 and any((val('current',c,'event_share') or 0)>=68 for c in (fixture.home_id,fixture.away_id)),'At least68% of on-ball event actions; explicitly not time possession.')
    return [{'id':t,'status':statuses[t][0],'active':statuses[t][1],'reason':statuses[t][2]} for t in TRIGGER_TYPES]


def build_dispatch_packet(snapshot:dict) -> dict:
    """Bounded candidate-selection context; exact facts and prose never truncated."""
    candidates=snapshot.get('candidates',[])
    if len(candidates)>8:raise ValueError('Too many grounded candidates')
    required={mid for c in candidates for mid in c['reading']['metric_ids']}
    references={eid for c in candidates for eid in c['reading']['evidence_ids']}
    metrics=[m for m in snapshot['metrics'] if m['id'] in required]
    evidence=[e for e in snapshot['evidence'] if e['id'] in references]
    if len(evidence)>64 or len(required)!=len(metrics) or len(references)!=len(evidence):raise ValueError('Incomplete candidate support')
    # No candidates is an honest abstention; expose compact numeric context for
    # diagnostics, but native runtime must not request model work for it.
    if not candidates:
        metrics=[m for m in snapshot['metrics'] if m['window']=='current'and not m.get('player_id')and m['key']in {'shots','on_ball_actions','final_third_entries'}]
        evidence=snapshot['evidence'][-4:]
    people={e['player_id']for e in evidence}|{m['player_id']for m in metrics if m.get('player_id')}
    if snapshot.get('focus_player_id'):people.add(snapshot['focus_player_id'])
    fields=('id','key','window','club_id','player_id','label','unit','basis','status','value','role','coverage','subject','method','event_id')
    result={k:snapshot[k]for k in ('snapshot_id','match_id','cutoff','through_sequence','language','depth','focus_player_id','clubs','score','windows','period_lengths_ms')}
    result.update(candidates=candidates,players=[p for p in snapshot['players']if p['player_id']in people],
        metrics=[{k:m[k]for k in fields if k in m}for m in metrics],evidence=evidence,
        signals=[{'id':'support:'+c['id'],'role':c['role'],'metric_ids':c['reading']['metric_ids'],'evidence_ids':c['reading']['evidence_ids']}for c in candidates],
        methods={k:v for k,v in snapshot['methods'].items()if k in {m.get('method')for m in metrics}|{'turnover','tracking','compound_event_facts'}})
    raw=json.dumps(result,ensure_ascii=False,separators=(',',':'),allow_nan=False)
    if len(raw)>24000 or len(raw.encode())>32000:raise ValueError('Analyst dispatch packet exceeds bounded context')
    return result


def momentum_series(events, fixture, request):
    """Causal minute samples; five-minute windows never cross a half."""
    points=[]
    for period in range(1, request.cutoff.period+1):
        end=request.cutoff.elapsed_ms if period==request.cutoff.period else fixture.period_lengths_ms[period-1]
        for ms in range(60000,end+1,60000):
            selected=[e for e in select_events(events,(period,ms)) if e.period==period and max(0,ms-300000)<e.elapsed_ms<=ms and (e.available_period,e.available_ms)<=(period,ms)]
            a=threat([e for e in selected if e.club_id==fixture.home_id]);b=threat([e for e in selected if e.club_id==fixture.away_id])
            points.append({'period':period,'elapsed_ms':ms,'value':round((a-b)/(a+b+1),6)})
    return points
