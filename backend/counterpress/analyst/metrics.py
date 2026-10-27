"""Deterministic event metrics. No animation coordinates or inferred tracking.

Every coordinate already attacks +x; comparisons use (start,end] within a half.
Estimates are explicitly separate from authored probabilities and measurements.
"""
from collections import Counter
import math

VERSION = 'analyst-event-metrics-v2-grounded-candidates'
COMPLETE = {'complete', 'completed'}
CONTROLLED = {'complete', 'completed', 'controlled', 'established', 'successful'}
ON_BALL = {'pass', 'shot', 'carry'}

# Human-readable method registry also supplies all reference metric families.
METHODS = {
    'compound_event_facts': 'Versioned exact counts/geometry and recipient-linked recovery-to-shot relations from visible canonical events. Event score facts are anchored immediately after the cited shot. No model computes these facts.',
    'counts': 'Counts of visible, latest-revision canonical events; unknown outcomes stay unknown.',
    'pass_accuracy': 'Completed passes / passes with known outcomes; unknown passes excluded from denominator.',
    'event_share': 'Share of pass, shot and controlled-carry events, not time in possession.',
    'geometry': 'Euclidean endpoints on a 105 by 68 metre pitch; each club attacks positive x.',
    'final_third': 'Completed passes crossing x=70 from below; carries reported separately.',
    'heatmap': '12 by 8 bins of recorded on-ball action starts, not off-ball occupancy.',
    'xg_geometry': 'Uncalibrated location heuristic v1: sigmoid(-1.3 + 1.8*goal_angle_rad - .075*goal_distance_m - .5*header). Not a fitted xG model.',
    'difficulty_geometry': 'Uncalibrated geometry difficulty v1: .65*min(distance/60,1) + .35*min(max(forward_progression,0)/40,1). No pressure estimate.',
    'authored_probability': 'Probability stored in a source event, with source estimate_version; missing probabilities excluded.',
    'speed': 'Authored ball-flight endpoint distance / authored duration *3.6; never a player speed or tracked ball speed.',
    'momentum': 'Five-minute signed threat balance (home-away)/(home+away+1); threat=positive completed-pass progression/105 + positive controlled-carry progression/105 + shot geometry estimate. Uncalibrated, recomputed per snapshot.',
    'tempo': 'Distinct visible on-ball actions per minute; current and previous five-minute windows, never duplicate internal contributions.',
    'turnover': 'Count assigned to the RECOVERING club: opponent incomplete pass followed within3seconds by this club recovery. These are balls WON, not this club losses; no gaps/restarts/cross-half joins.',
    'chaos': 'Uncalibrated verified-turnover index min(1, turnovers per minute / 3).',
    'tracking': 'Unavailable: no continuous player tracking; distance, sprints, player speed and off-ball heatmaps are not estimated from replay animation.',
    'ppda': 'Unavailable: current canonical schema does not consistently distinguish tackles, interceptions and fouls; generic duels are not substitutes.',
    'discipline': 'Unavailable in this canonical action schema: no authoritative foul/card/corner event family.',
    'ranking': 'Unavailable: no validated cross-position performance rating; inspect individual event statistics instead.',
    'auto_eventing': 'Unavailable: this pipeline consumes canonical events; no video classifier or ground-truth detection run.',
}


def distance(e):
    return math.dist((e.start.x, e.start.y), (e.end.x, e.end.y)) if e.start and e.end else None


def geometric_xg(e):
    if not e.start or e.kind != 'shot' or e.outcome == 'own_goal':
        return None
    dx = 105-e.start.x
    a = math.atan2(37.66-e.start.y, max(dx, 1e-6))
    b = math.atan2(30.34-e.start.y, max(dx, 1e-6))
    angle = abs(a-b)
    z = -1.3 + 1.8*angle - .075*math.hypot(dx, 34-e.start.y) - (.5 if e.technique == 'header' else 0)
    return 1/(1+math.exp(-z))


def difficulty(e):
    d = distance(e)
    return None if d is None else .65*min(d/60, 1)+.35*min(max(e.end.x-e.start.x, 0)/40, 1)


def turns(events):
    return [(a, b) for a, b in zip(events, events[1:])
            if a.kind == 'pass' and a.outcome == 'incomplete' and b.kind == 'recovery'
            and a.club_id != b.club_id and a.period == b.period
            and 0 <= b.elapsed_ms-a.elapsed_ms <= 3000 and not (a.restart or b.restart)]


def heatmap(events):
    bins = Counter((min(11, int(e.start.x/8.75)), min(7, int(e.start.y/8.5)))
        for e in events if e.start and (e.kind in ('pass', 'shot') or e.kind == 'carry' and e.outcome in CONTROLLED))
    return {'columns': 12, 'rows': 8, 'pitch_m': [105, 68], 'attacking_direction': 'positive_x',
        'cells': [{'column': x, 'row': y, 'count': n} for (x, y), n in sorted(bins.items())]}


def threat(events):
    value = 0.
    for e in events:
        if e.kind == 'shot': value += geometric_xg(e) or 0
        elif e.start and e.end and (e.kind == 'pass' and e.outcome in COMPLETE or e.kind == 'carry' and e.outcome in CONTROLLED):
            value += max(0, e.end.x-e.start.x)/105
    return value


def metric_rows(events, *, club_id, window, duration_ms, all_events, source_kind, player_id=None):
    """One scope's event metrics. This reducer does not select revisions/cutoffs."""
    own = [e for e in events if e.club_id == club_id and (player_id is None or e.player_id == player_id)]
    prefix = f'{window}:{player_id or club_id}'
    rows = []
    def add(key, label, value, *, unit='count', basis='recorded_events', role='control', n=None, d=None, status=None, method='counts'):
        if isinstance(value, float): value = round(value, 6)
        row = {'id': f'{prefix}:{key}', 'key': key, 'window': window, 'club_id': club_id,
            'label': label, 'unit': unit, 'basis': basis, 'role': role, 'value': value,
            'status': status or ('unavailable' if value is None else 'partial' if n is not None and d is not None and n < d else 'available'),
            'method': method}
        if basis in {'heuristic', 'uncalibrated_heuristic'}:
            row['estimate_version'] = VERSION
            row['confidence'] = 'uncalibrated'
        if player_id is not None:
            row['player_id'] = player_id
            row['role'] = 'players'
        if key=='verified_turnovers':row['subject']='recovering_club_not_losing_club'
        if n is not None and d is not None: row['coverage'] = {'numerator': n, 'denominator': d}
        rows.append(row)
    passes = [e for e in own if e.kind == 'pass']
    good = [e for e in passes if e.outcome in COMPLETE]
    known = [e for e in passes if e.outcome in COMPLETE | {'incomplete'}]
    shots = [e for e in own if e.kind == 'shot' and e.outcome != 'own_goal']
    carries = [e for e in own if e.kind == 'carry' and e.outcome in CONTROLLED]
    onball = [e for e in own if e.kind in ('pass', 'shot') or e in carries]
    total_onball = sum(e.kind in ('pass', 'shot') or e.kind == 'carry' and e.outcome in CONTROLLED for e in all_events)
    for key,label,value,role in (
        ('actions','Recorded actions',len(own),'players'), ('on_ball_actions','On-ball actions',len(onball),'players'),
        ('passes','Passes',len(passes),'control'),('passes_completed','Completed passes',len(good),'control'),
        ('passes_unknown','Passes with unknown outcome',len(passes)-len(known),'control'),
        ('shots','Shots',len(shots),'chance'),('shots_on_target','Shots on target',sum(e.outcome in {'goal','saved','on_target'} for e in shots),'chance'),
        ('goals','Goals',sum(e.goal_for == club_id and (player_id is None or e.player_id==player_id and e.club_id==club_id) for e in events),'chance'),
        ('duels_won','Duels won',sum(e.kind=='duel' and e.outcome=='won' for e in own),'defence'),
        ('final_third_entries','Final-third pass entries',sum(bool(e.start and e.end and e.start.x<70<=e.end.x) for e in good),'control'),
        ('box_entries','Passes into the box',sum(bool(e.start and e.end and e.end.x>=88.5 and 13.84<=e.end.y<=54.16 and not(e.start.x>=88.5 and 13.84<=e.start.y<=54.16)) for e in good),'control')):
        add(key,label,value,role=role)
    add('pass_accuracy','Pass completion',len(good)/len(known)*100 if known else None,unit='percent',n=len(known),d=len(passes),method='pass_accuracy')
    add('event_share','Share of on-ball actions',len(onball)/total_onball*100 if total_onball else None,unit='percent',basis='event_share_proxy',method='event_share')
    add('possession_seconds','Time in possession',None,unit='seconds',basis='unavailable',method='tracking')
    located = [e for e in good if distance(e) is not None]
    add('completed_pass_distance','Completed-pass distance',sum(distance(e) for e in located) if located or not good else None,unit='metres',n=len(located),d=len(good),method='geometry')
    add('pass_progression','Completed-pass forward progression',sum(max(0,e.end.x-e.start.x) for e in located) if located or not good else None,unit='metres',n=len(located),d=len(good),method='geometry')
    add('carry_progression','Forward carry progression',sum(e.end.x-e.start.x for e in carries if e.start and e.end) if any(e.start and e.end for e in carries) else None,unit='metres',n=sum(bool(e.start and e.end) for e in carries),d=len(carries),method='geometry')
    add('heatmap','On-ball locations',heatmap(own),unit='event_bins',method='heatmap')
    add('pass_routes','Pass routes',{'passes':[{'event_id':e.event_id,'start':e.start.model_dump(),'end':e.end.model_dump(),'outcome':e.outcome,'recipient_id':e.recipient_id,'distance_m':round(distance(e),6),'forward_m':round(e.end.x-e.start.x,6)} for e in passes if e.start and e.end]},unit='locations',method='geometry')
    add('tempo','On-ball actions per minute',len(onball)/(duration_ms/60000) if duration_ms else None,unit='actions_per_minute',method='tempo')
    for key,label,kind in [('recoveries','Recoveries','recovery'),('pressures','Pressure events','pressure')]:
        add(key,label,sum(e.kind==kind and not e.restart for e in own) if source_kind != 'adapted_archive' else None,role='defence',basis='recorded_events' if source_kind!='adapted_archive' else 'unavailable')
    t = [pair for pair in turns(events) if pair[1].club_id==club_id and (player_id is None or pair[1].player_id==player_id)]
    add('verified_turnovers','Recoveries after opponent incomplete passes',len(t) if source_kind!='adapted_archive' else None,role='defence',method='turnover')
    add('chaos','Turnover intensity',min(1,len(turns(events))/(duration_ms/60000)/3) if duration_ms and source_kind!='adapted_archive' else None,unit='index',basis='heuristic',method='chaos')
    xg = [e.expected_goal_probability for e in shots if e.expected_goal_probability is not None]
    gxg = [geometric_xg(e) for e in shots if geometric_xg(e) is not None]
    add('xg_authored','Authored expected goals',sum(xg) if xg else None,unit='expected_goals',basis='authored_model',role='chance',n=len(xg),d=len(shots),method='authored_probability')
    add('xg_geometry','Shot-location estimate',sum(gxg) if gxg else None,unit='expected_goals',basis='uncalibrated_heuristic',role='chance',n=len(gxg),d=len(shots),method='xg_geometry')
    add('shot_map','Shot map',{'shots':[{'event_id':e.event_id,'x':e.start.x,'y':e.start.y,'outcome':e.outcome,'end':e.end.model_dump() if e.end else None,'distance_m':round(math.hypot(105-e.start.x,34-e.start.y),6),'technique':e.technique,'xg_authored':e.expected_goal_probability,'xg_geometry':round(geometric_xg(e),6)} for e in shots if e.start]},unit='locations',role='chance',method='geometry')
    for key,label,source in [('pass_speed','Fastest authored pass','pass'),('shot_speed','Fastest authored shot','shot')]:
        eligible = passes if source=='pass' else shots
        speeds = [distance(e)/(e.flight_ms/1000)*3.6 for e in eligible if e.telemetry_basis=='authored_physics' and e.flight_ms and distance(e) is not None]
        add(key,label,max(speeds) if speeds else None,unit='km/h',basis='authored_physics',role='chance' if source=='shot' else 'control',n=len(speeds),d=len(eligible),method='speed')
    authored = [1-e.completion_probability for e in passes if e.completion_probability is not None]
    geo = [difficulty(e) for e in passes if difficulty(e) is not None]
    hard = [difficulty(e) for e in good if difficulty(e) is not None]
    add('pass_difficulty_authored','Mean authored pass difficulty',sum(authored)/len(authored) if authored else None,unit='index',basis='authored_model',n=len(authored),d=len(passes),method='authored_probability')
    add('pass_difficulty_geometry','Mean geometric pass difficulty',sum(geo)/len(geo) if geo else None,unit='index',basis='uncalibrated_heuristic',n=len(geo),d=len(passes),method='difficulty_geometry')
    add('hardest_completed_pass','Hardest completed pass geometry',max(hard) if hard else None,unit='index',basis='uncalibrated_heuristic',n=len(hard),d=len(good),method='difficulty_geometry')
    for key,label,unit,method,role in (
        ('tackles_won','Tackles won','count','ppda','defence'),('interceptions','Interceptions','count','ppda','defence'),
        ('fouls','Fouls','count','discipline','defence'),('yellow_cards','Yellow cards','count','discipline','defence'),('red_cards','Red cards','count','discipline','defence'),
        ('corners','Corners','count','discipline','control'),('ppda','Passes per defensive action','ratio','ppda','defence'),
        ('player_distance','Player distance covered','km','tracking','players'),('player_top_speed','Top player speed','km/h','tracking','players'),
        ('sprints','Sprints','count','tracking','players'),('performance_rating','Player performance rating','rating','ranking','players'),
        ('detection_precision','Auto-event detection precision','percent','auto_eventing','control'),('detection_recall','Auto-event detection recall','percent','auto_eventing','control')):
        add(key,label,None,unit=unit,basis='unavailable',method=method,role=role)
    return rows
