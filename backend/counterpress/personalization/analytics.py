"""Derived player analytics. Never changes the calibrated event ledger.

Pitch coordinates attack +x, 105 x 68 m. An action heatmap measures recorded
involvement, not off-ball occupancy. Cached reductions are tied to event digests;
revisions and historical availability cutoffs bypass the initial cache.
"""
from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path
import gzip
import json
import math

from .contracts import MatchRecord
from .metrics import reduce_record, select_events

VERSION = 'player-analytics-v1'


def box(p):
    return p is not None and p.x >= 88.5 and 13.84 <= p.y <= 54.16


def progressive(start, end):
    if not start or not end:
        return False
    gain = math.dist((start.x, start.y), (105, 34)) - math.dist((end.x, end.y), (105, 34))
    threshold = 30 if start.x < 52.5 and end.x < 52.5 else 15 if start.x < 52.5 else 10
    return gain >= threshold - 1e-9


def cell(p):
    return f'{min(11, int(p.x / 8.75))}:{min(7, int(p.y / 8.5))}'


def route_cell(p):
    return f'{min(5, int(p.x / 17.5))}:{min(3, int(p.y / 17))}'


def derive(record, summary=None):
    """One deterministic reduction for all participants in a selected version set."""
    summary = summary or reduce_record(record)
    players = {p: {'stats': Counter(s), 'heat': Counter(), 'defense': Counter(),
                   'routes': Counter(), 'shots': [], 'timing': [0]*6}
               for p, s in summary['players'].items()}
    chain = None
    carry = 0.
    run = None
    events = select_events(record.events)
    by_id = {e.event_id: e for e in events}
    for e in events:
        out = players[e.player_id]
        s = out['stats']
        complete = e.outcome in ('completed', 'complete')
        if e.kind != 'carry' or e.restart:
            run = None
        if e.start and e.kind in ('pass', 'shot', 'carry', 'duel', 'recovery'):
            out['heat'][cell(e.start)] += 1
            s['actions'] += 1
            s['box_actions'] += int(box(e.start))
            s['own_third_actions' if e.start.x < 35 else 'middle_third_actions' if e.start.x < 70 else 'final_third_actions'] += 1
        if chain and (e.period != chain.period or e.club_id != chain.club_id or e.restart or e.kind == 'recovery'):
            chain = None
        if e.kind == 'pass':
            s['passes_incomplete'] += int(e.outcome == 'incomplete')
            if e.start and e.end:
                length = math.dist((e.start.x, e.start.y), (e.end.x, e.end.y))
                s['long_passes'] += int(length >= 32)
                s['long_passes_completed'] += int(length >= 32 and complete)
                s['long_passes_known'] += int(length >= 32 and e.outcome != 'unknown')
                prog = progressive(e.start, e.intended_end or e.end)
                s['progressive_passes'] += int(prog)
                s['progressive_passes_completed'] += int(prog and complete)
                s['progressive_passes_known'] += int(prog and e.outcome != 'unknown')
                s['final_third_entries'] += int(complete and e.start.x < 70 <= e.end.x)
                s['box_entries'] += int(complete and not box(e.start) and box(e.end))
                s['forward_passes' if e.end.x-e.start.x > 5 else 'backward_passes' if e.end.x-e.start.x < -5 else 'lateral_passes'] += 1
                key = f'{route_cell(e.start)}:{route_cell(e.end)}:{e.outcome}:{int(prog)}'
                out['routes'][key] += 1
            s['crosses'] += int(e.technique == 'cross')
            s['crosses_completed'] += int(e.technique == 'cross' and complete)
            s['crosses_known'] += int(e.technique == 'cross' and e.outcome != 'unknown')
            if complete and e.recipient_id:
                players[e.recipient_id]['stats']['passes_received'] += 1
            chain = e if complete and e.recipient_id else None
            carry = 0.
        elif e.kind == 'carry':
            if e.start and e.end and not e.restart:
                distance = math.dist((e.start.x, e.start.y), (e.end.x, e.end.y))
                contiguous = run and run['player'] == e.player_id and run['period'] == e.period and 0 <= e.elapsed_ms-run['at'] <= 10000 and math.dist((e.start.x,e.start.y),run['end']) < .01
                if not contiguous:
                    run = {'player':e.player_id,'period':e.period,'start':e.start,'progressive':False}
                    s['carries'] += 1
                s['carry_distance_m'] += distance
                if not run['progressive'] and progressive(run['start'],e.end):
                    s['progressive_carries'] += 1
                    run['progressive'] = True
                run.update(at=e.elapsed_ms,end=(e.end.x,e.end.y))
                s['carry_box_entries'] += int(not box(e.start) and box(e.end))
                if chain:
                    carry += distance
                    if carry > 10:
                        chain = None
        elif e.kind == 'shot' and e.outcome != 'own_goal':
            s['penalty_shots'] += int(e.penalty)
            s['penalty_goals'] += int(e.penalty and e.outcome == 'goal')
            s['non_penalty_goals'] += int(not e.penalty and e.outcome == 'goal')
            s['headed_shots'] += int(e.technique == 'header')
            s['headed_goals'] += int(e.technique == 'header' and e.outcome == 'goal')
            s['woodwork'] += int(e.outcome == 'woodwork')
            if e.start:
                s['shots_inside_box' if box(e.start) else 'shots_outside_box'] += 1
                s['shot_distance_m'] += math.dist((e.start.x, e.start.y), (105, 34))
                s['located_shots'] += 1
                out['shots'].append({'event_id': e.event_id, 'revision': e.revision,
                    'x': e.start.x, 'y': e.start.y, 'period': e.period, 'elapsed_ms': e.elapsed_ms,
                    'outcome': e.outcome, 'xg': e.expected_goal_probability, 'penalty': e.penalty})
            if e.outcome == 'goal':
                slot = min(2, int(e.elapsed_ms//900000)) + (3 if e.period == 2 else 0)
                out['timing'][slot] += 1
            if e.expected_goal_probability is not None:
                s['xg_goals'] += int(e.outcome == 'goal')
                s['non_penalty_xg'] += 0 if e.penalty else e.expected_goal_probability
            provider = chain if chain and chain.recipient_id == e.player_id and e.elapsed_ms-chain.elapsed_ms <= 15000 and not e.penalty else None
            if record.fixture.assist_basis == 'provider_tags':
                provider = by_id.get(e.credited_assist_event_id)
            if provider and e.expected_goal_probability is not None:
                players[provider.player_id]['stats']['xa'] += e.expected_goal_probability
                players[provider.player_id]['stats']['xa_shots'] += 1
            chain = None
        elif e.kind == 'duel':
            s['duels_lost'] += int(e.outcome == 'lost')
            s['duels_drawn'] += int(e.outcome == 'draw')
            if e.start and e.outcome == 'won':
                out['defense'][cell(e.start)] += 1
            if e.opponent_id:
                other = players[e.opponent_id]
                other['stats']['duels_lost'] += int(e.outcome == 'won')
                other['stats']['duels_drawn'] += int(e.outcome == 'draw')
                if e.start and e.outcome == 'lost':
                    # Opposition coordinates are rotated, including the lateral axis.
                    from counterpress.domain.models import PitchPosition
                    other['defense'][cell(PitchPosition(x=105-e.start.x, y=68-e.start.y))] += 1
            chain = None
        elif e.kind == 'recovery' and not e.restart and e.start:
            out['defense'][cell(e.start)] += 1
            s['high_recoveries'] += int(e.start.x >= 70)
    for a in record.fixture.appearances:
        players[a.player_id]['stats']['own_goals_conceded'] = sum(
            e.outcome == 'own_goal' and e.goal_for != a.club_id and
            a.start_ms <= e.elapsed_ms + (record.fixture.period_lengths_ms[0] if e.period == 2 else 0) < a.end_ms
            for e in events)
    return players


# key, label, category, numerator, denominator (percentage/mean), unit, coverage family
# Counts and estimates can also be viewed per 90 using covered minutes.
DEFINITIONS = [
    ('appearances','Matches','Overview','appearances',None,'count','all'),
    ('starts','Starts','Overview','starts',None,'count','all'),
    ('minutes','Minutes played','Overview','minutes',None,'minutes','all'),
    ('goals','Goals','Shooting','goals',None,'count','all'),
    ('non_penalty_goals','Non-penalty goals','Shooting','non_penalty_goals',None,'count','all'),
    ('shots','Shots','Shooting','shots',None,'count','all'),
    ('shots_on_target','Shots on target','Shooting','shots_on_target',None,'count','all'),
    ('shots_off_target','Shots off target','Shooting','shots_off_target',None,'count','all'),
    ('shots_blocked','Shots blocked','Shooting','shots_blocked',None,'count','all'),
    ('shot_accuracy','Shot accuracy','Shooting','shots_on_target','shots','percent','all'),
    ('conversion','Goal conversion','Shooting','goals','shots','percent','all'),
    ('xg','Expected goals (xG)','Shooting','xg',None,'estimate','xg'),
    ('non_penalty_xg','Non-penalty xG','Shooting','non_penalty_xg',None,'estimate','xg'),
    ('xg_per_shot','xG per shot','Shooting','xg','xg_shots','decimal','xg'),
    ('goals_above_xg','Goals above xG','Shooting','goals_above_xg',None,'estimate','xg'),
    ('shots_inside_box','Shots inside the box','Shooting','shots_inside_box',None,'count','locations'),
    ('shots_outside_box','Shots outside the box','Shooting','shots_outside_box',None,'count','locations'),
    ('shot_distance','Average shot distance','Shooting','shot_distance_m','located_shots','metres','locations'),
    ('penalty_shots','Penalties taken','Shooting','penalty_shots',None,'count','all'),
    ('penalty_goals','Penalties scored','Shooting','penalty_goals',None,'count','all'),
    ('penalty_conversion','Penalty conversion','Shooting','penalty_goals','penalty_shots','percent','all'),
    ('headed_shots','Headed shots','Shooting','headed_shots',None,'count','shot_technique'),
    ('headed_goals','Headed goals','Shooting','headed_goals',None,'count','shot_technique'),
    ('woodwork','Hit the woodwork','Shooting','woodwork',None,'count','woodwork'),
    ('goal_involvements','Goals + assists','Creating','goal_involvements',None,'count','assists'),
    ('assists','Assists','Creating','assists',None,'count','assists'),
    ('key_passes','Shot assists','Creating','key_passes',None,'count','creation'),
    ('xa','Expected assists (xA)','Creating','xa',None,'estimate','xa'),
    ('passes','Pass attempts','Passing','passes',None,'count','all'),
    ('passes_completed','Completed passes','Passing','passes_completed',None,'count','all'),
    ('passes_incomplete','Incomplete passes','Passing','passes_incomplete',None,'count','all'),
    ('pass_accuracy','Pass completion','Passing','passes_completed','known_passes','percent','all'),
    ('expected_completions','Expected completed passes','Passing','expected_completions',None,'estimate','xpass'),
    ('expected_pass_accuracy','Expected pass completion','Passing','expected_completions','xpass_passes','percent','xpass'),
    ('passing_above_expected','Completion above expected','Passing','completion_surplus','xpass_passes','points','xpass'),
    ('mean_pass_speed','Estimated pass speed','Passing','pass_speed_kmh_sum','flight_passes','kmh','flight'),
    ('mean_shot_speed','Estimated shot speed','Shooting','shot_speed_kmh_sum','flight_shots','kmh','flight'),
    ('progressive_passes','Progressive passes attempted','Passing','progressive_passes',None,'count','locations'),
    ('progressive_passes_completed','Progressive passes completed','Passing','progressive_passes_completed',None,'count','locations'),
    ('progressive_accuracy','Progressive pass completion','Passing','progressive_passes_completed','progressive_passes_known','percent','locations'),
    ('final_third_entries','Passes into the final third','Passing','final_third_entries',None,'count','locations'),
    ('box_entries','Passes into the box','Passing','box_entries',None,'count','locations'),
    ('long_passes','Long passes attempted','Passing','long_passes',None,'count','locations'),
    ('long_passes_completed','Long passes completed','Passing','long_passes_completed',None,'count','locations'),
    ('long_accuracy','Long pass completion','Passing','long_passes_completed','long_passes_known','percent','locations'),
    ('forward_passes','Forward passes','Passing','forward_passes',None,'count','locations'),
    ('backward_passes','Backward passes','Passing','backward_passes',None,'count','locations'),
    ('lateral_passes','Sideways passes','Passing','lateral_passes',None,'count','locations'),
    ('pass_distance','Average pass length','Passing','pass_distance_m','located_passes','metres','locations'),
    ('crosses','Crosses attempted','Creating','crosses',None,'count','technique'),
    ('crosses_completed','Crosses completed','Creating','crosses_completed',None,'count','technique'),
    ('cross_accuracy','Cross completion','Creating','crosses_completed','crosses_known','percent','technique'),
    ('passes_received','Passes received','Possession','passes_received',None,'count','recipients'),
    ('actions','Actions on the ball','Possession','actions',None,'count','locations'),
    ('box_actions','Actions in the opposition box','Possession','box_actions',None,'count','locations'),
    ('carries','Carries','Possession','carries',None,'count','carries'),
    ('carry_distance_m','Distance carried with the ball','Possession','carry_distance_m',None,'metres_total','carries'),
    ('progressive_carries','Progressive carries','Possession','progressive_carries',None,'count','carries'),
    ('carry_box_entries','Carries into the box','Possession','carry_box_entries',None,'count','carries'),
    ('duels','Ground challenges','Defending','duels',None,'count','all'),
    ('duels_won','Ground challenges won','Defending','duels_won',None,'count','all'),
    ('duels_lost','Ground challenges lost','Defending','duels_lost',None,'count','all'),
    ('duels_drawn','Ground challenges drawn','Defending','duels_drawn',None,'count','all'),
    ('duel_win_pct','Ground challenge win rate','Defending','duels_won','known_duels','percent','all'),
    ('recoveries','Ball recoveries','Defending','recoveries',None,'count','recoveries'),
    ('high_recoveries','Final-third recoveries','Defending','high_recoveries',None,'count','recoveries'),
    ('saves','Saves','Goalkeeping','saves',None,'count','saves'),
    ('save_pct','Save percentage','Goalkeeping','saves','keeper_shots_faced','percent','saves'),
    ('goals_conceded','Goals conceded','Goalkeeping','goals_conceded',None,'count','all'),
    ('clean_sheets','Clean sheets','Goalkeeping','clean_sheets',None,'count','all'),
    ('clean_sheet_pct','Clean-sheet rate','Goalkeeping','clean_sheets','appearances','percent','all'),
]
DESCRIPTIONS = {
    'progressive_passes': 'Passes moving closer to goal by at least 30m within the own half, 15m across halfway, or 10m in the attacking half. Intended target when recorded, otherwise recorded endpoint.',
    'progressive_passes_completed': 'Completed passes meeting the 30/15/10m progression thresholds.',
    'carries': 'Continuous located carry sequences by the same player, joined only across gaps of at most 10 seconds with matching endpoints. Restarts are excluded.',
    'progressive_carries': 'Continuous carries meeting the same 30/15/10m progression thresholds.',
    'key_passes': 'Passes directly leading to a shot, including goals. The link expires after 15 seconds, a challenge, a restart or more than 10 metres of carrying.',
    'xa': 'Sum of the estimated goal probabilities of directly assisted shots; also called expected assisted goals. Only matches with complete shot-assist and xG coverage contribute.',
    'goals_above_xg': 'Goals minus xG on the same set of shots with a goal-probability estimate.',
    'actions': 'Located passes, shots, carries, challenges and recoveries performed by this player. These are recorded actions, not every physical touch.',
    'box_actions': 'Recorded actions starting inside the opposition penalty area.',
    'long_passes': 'Located passes travelling at least 32 metres.',
    'final_third_entries': 'Completed passes starting outside the attacking third and ending inside it.',
    'box_entries': 'Completed passes starting outside the opposition box and ending inside it.',
    'save_pct': 'Saves divided by saves plus non-own goals conceded while on the pitch, in matches with save coverage.',
    'carry_distance_m': 'Sum of recorded carry segments. This is distance with the ball, not total running distance.',
    'pass_accuracy': 'Completed passes divided by attempts with known outcomes; includes recorded dead-ball passes and excludes throw-ins.',
    'clean_sheets': 'Completed matches with at least 60 player-minutes and no goals conceded while on the pitch.',
    'expected_completions': 'Sum of completion probabilities for passes with a calibrated estimate.',
    'expected_pass_accuracy': 'Mean completion probability across passes with calibrated estimates.',
    'passing_above_expected': 'Actual completion minus expected completion, in percentage points, on the same estimated passes.',
    'mean_pass_speed': 'Mean of each pass distance divided by its authored ball-flight time, in km/h. Synthetic ball physics, not measured tracking.',
    'mean_shot_speed': 'Mean of each shot distance divided by its authored ball-flight time, in km/h. Synthetic ball physics, not radar measurements.',
    'goal_involvements': 'Goals plus assists in matches where assist coverage is available.',
    'xg': 'Sum of pre-shot scoring probabilities from the calibrated event model.',
}


def available(f, family):
    if family in ('shot_technique','woodwork'):
        return False  # The current generator/imports do not distinguish these outcomes.
    generated = f['source_kind'] == 'calibrated_simulation'
    if family in ('technique', 'recipients', 'carries', 'xg', 'xa', 'xpass', 'flight'):
        return generated
    if family == 'creation':
        return f.get('shot_assists_complete', False)
    if family == 'assists':
        return f.get('assist_basis', 'unavailable') != 'unavailable'
    if family in ('saves', 'recoveries'):
        return f['source_kind'] != 'adapted_archive'
    return True


def aggregate(entries):
    """Aggregate with separate exposure for each semantic coverage family."""
    families = {d[6] for d in DEFINITIONS}
    buckets = {k: Counter() for k in families}
    coverage = Counter()
    for f, p in entries:
        for family in families:
            if available(f, family):
                buckets[family].update(p['stats'])
                coverage[family] += 1
    for s in buckets.values():
        s['goal_involvements'] = s['goals'] + s['assists']
        s['completion_surplus'] = s['xpass_completed'] - s['expected_completions']
        s['known_passes'] = s['passes'] - s['passes_unknown']
        s['known_duels'] = s['duels'] - s['duels_unknown']
        s['goals_above_xg'] = s['xg_goals'] - s['xg']
        s['keeper_shots_faced'] = s['saves'] + s['goals_conceded'] - s['own_goals_conceded']
    metrics = []
    for key, label, group, num, denom, unit, family in DEFINITIONS:
        s = buckets[family]
        value = s[num] / s[denom] * (100 if unit in ('percent','points') else 1) if denom and s[denom] else None if denom else s[num]
        if not coverage[family]:
            value = None
        per90 = value * 90 / s['minutes'] if value is not None and not denom and key not in ('appearances', 'starts', 'minutes') and s['minutes'] else None
        metrics.append({'key':key,'label':label,'group':group,'value':round(value,4) if value is not None else None,
            'per90':round(per90,4) if per90 is not None else None,'unit':unit,
            'covered_matches':coverage[family],'total_matches':len(entries),'covered_minutes':round(s['minutes'],2),
            'description':DESCRIPTIONS.get(key, label + ' over the selected matches.')})
    return metrics


def build_artifact(store):
    matches = {}
    for index, row in enumerate(store.rows()):
        record = store.original(row['id'])
        derived = derive(record, json.loads(row['summary']))
        matches[row['id']] = {'digest':row['digest'],'players':derived}
        if (index+1) % 200 == 0:
            print(f'Indexed {index+1} matches', flush=True)
    return {'version':VERSION,'ledger_sha256':store.manifest['files']['ledger.json.gz'],
            'reducer_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),'matches':matches}


class PlayerAnalytics:
    def __init__(self, career):
        self.career = career
        self.store = career.store
        root = self.store.root.parent/'analytics'
        manifest = json.loads((root/'manifest.json').read_text())
        raw = (root/'players.json.gz').read_bytes()
        if sha256(raw).hexdigest() != manifest['sha256']:
            raise ValueError('Player analytics checksum mismatch')
        self.artifact = json.loads(gzip.decompress(raw))
        if (self.artifact['version'] != VERSION or self.artifact['ledger_sha256'] != self.store.manifest['files']['ledger.json.gz']
                or self.artifact['reducer_sha256'] != sha256(Path(__file__).read_bytes()).hexdigest()):
            raise ValueError('Player analytics needs rebuilding for this dataset or reducer')

    def profile(self, pid, season=None, before=None):
        if pid not in self.store.players:
            raise KeyError(pid)
        subject = self.store.players[pid]
        entries = defaultdict(list)
        selected = []
        with self.store.lock:
            revised = {r[0] for r in self.store.db.execute('SELECT DISTINCT match_id FROM career_revisions')}
        for row in self.store.rows(season=season, before=before):
            at = self.career.historical_cutoff(row, before)
            if at is False:
                continue
            f = json.loads(row['fixture'])
            cached = self.artifact['matches'][row['id']]
            if cached['digest'] != row['digest']:
                raise ValueError('Analytics event lineage mismatch')
            complete = at is None or at >= (2, f['period_lengths_ms'][1]+1000)
            data = cached['players']
            if row['id'] in revised or not complete:
                original = self.store.original(row['id'])
                record = MatchRecord(fixture=original.fixture, events=tuple(select_events(self.store.events(row['id']), at)))
                data = derive(record, self.store.summary(row['id'], at, completed=True))
            for player, value in data.items():
                if not value['stats']['appearances']:
                    continue
                if self.store.players[player].role == subject.role or player == pid:
                    entries[player].append((f, value))
                if player == pid:
                    selected.append((f, value))
        metrics = aggregate(selected)
        if subject.role != 'GK':
            metrics = [m for m in metrics if m['group'] != 'Goalkeeping']
        heat, defense, routes = Counter(), Counter(), Counter()
        shots, timing, recent = [], [0]*6, []
        thirds = Counter()
        for f, p in selected:
            heat.update(p['heat']); defense.update(p['defense']); routes.update(p['routes'])
            shots.extend({**s,'match_id':f['match_id'],'date':f['kickoff'][:10]} for s in p['shots'])
            timing = [a+b for a,b in zip(timing,p['timing'])]
            for k in ('own_third_actions','middle_third_actions','final_third_actions'):
                thirds[k] += p['stats'].get(k,0)
            if len(recent) < 10:
                s = p['stats']
                recent.append({'match_id':f['match_id'],'date':f['kickoff'][:10],
                    'opponent_id':f['away_id'] if f['home_id'] == subject.club_id else f['home_id'],
                    'minutes':s['minutes'],'goals':s['goals'],'assists':s['assists'] if available(f,'assists') else None,
                    'xg':s['xg'] if available(f,'xg') else None,'saves':s['saves'] if available(f,'saves') else None,
                    'passes_completed':s['passes_completed'],'duels_won':s['duels_won']})
        def grid(counts):
            return [{'column':int(k.split(':')[0]),'row':int(k.split(':')[1]),'actions':v} for k,v in sorted(counts.items())]
        links = []
        for key, count in sorted(routes.items(),key=lambda kv:(-kv[1],kv[0])):
            x,y,ex,ey,outcome,prog = key.split(':')
            links.append({'x':(int(x)+.5)*17.5,'y':(int(y)+.5)*17,'end_x':(int(ex)+.5)*17.5,'end_y':(int(ey)+.5)*17,
                          'outcome':outcome,'progressive':bool(int(prog)),'count':count})
        keys = ['save_pct','clean_sheet_pct','pass_accuracy','long_accuracy','passes','saves'] if subject.role == 'GK' else ['goals','xa','progressive_passes_completed','pass_accuracy','duels_won','recoveries']
        peers = {p:{m['key']:m for m in aggregate(v)} for p,v in entries.items() if sum(x['stats']['minutes'] for _,x in v)>=900}
        comparisons = []
        for key in keys:
            metric = next(m for m in metrics if m['key']==key)
            rate = metric['per90'] if metric['unit'] != 'percent' else metric['value']
            values = [(v[key]['per90'] if metric['unit']!='percent' else v[key]['value']) for v in peers.values()]
            values = [v for v in values if v is not None]
            rank = None
            if pid in peers and rate is not None and len(values)>=5:
                rank = round(100*(sum(v<rate for v in values)+.5*sum(v==rate for v in values))/len(values))
            comparisons.append({'key':key,'label':metric['label'],'value':rate,'unit':'percent' if metric['unit']=='percent' else 'per90',
                'percentile':rank,'cohort_size':len(values)})
        return {'version':VERSION,'player_id':pid,'role':subject.role,'scope':{'season':season,'before':before,'matches':len(selected)},
            'metrics':metrics,'heatmap':{'columns':12,'rows':8,'cells':grid(heat),'total_actions':sum(heat.values()),'label':'Action heatmap'},
            'defense':grid(defense),'shots':shots,'passing_routes':links,'thirds':dict(thirds),'goal_timing':timing,
            'recent':list(reversed(recent)),'comparison':{'minimum_minutes':900,'role':subject.role,'metrics':comparisons},
            'definitions':{'heatmap':'Recorded action locations, normalized to attack right.',
                'passing_map':'Origin and destination zone centres, aggregated in a 6 by 4 grid; not exact individual trajectories.',
                'comparison':'Percentile among same-position players in this library and selected period, at least 900 minutes. Ties use midrank.',
                'missing':['Continuous tracking and sprint distance','Shot body part and woodwork classification','Aerial duels','Fouls and cards','Interceptions, tackles and clearances as separate event types','Post-shot xG and goals prevented']}}
