"""Position benchmarks with explicit denominators and match-cluster uncertainty.

This is an audit of event statistics, not a tracking or player-rating model.
Source rows contain aggregate counts only; no real identities are published.
"""
from collections import Counter, defaultdict
import math
from random import Random

from .calibration import describe

ROLES = ('GK', 'DF', 'MF', 'FW')
SOURCE_ROLES = {'Goalkeeper': 'GK', 'Defender': 'DF', 'Midfielder': 'MF', 'Forward': 'FW'}
PASS_RESTARTS = {'Goal kick', 'Corner', 'Free Kick', 'Free kick cross'}
RATE_FIELDS = ('passes', 'shots', 'goals', 'assists', 'duels', 'saves', 'goals_conceded')
RATIOS = {
    'pass_completion': ('passes_completed', 'passes_known'),
    'shot_accuracy': ('shots_on_target', 'shots'),
    'conversion': ('goals', 'shots'),
    'duel_win': ('duels_won', 'duels'),
    'save_rate': ('saves', 'shots_faced'),
    'clean_sheet_rate': ('clean_sheets', 'appearances'),
    'completed_long_share': ('completed_long', 'completed_located'),
}


def values(counts):
    result = {k + '_per90': counts.get(k, 0) * 90 / counts['minutes'] for k in RATE_FIELDS} if counts['minutes'] else {}
    result.update({k: counts.get(n, 0) / counts[d] if counts.get(d) else None for k, (n, d) in RATIOS.items()})
    return result


def source_rows(events, matches, players, ids):
    """Passing includes recorded deliveries but excludes throw-ins.

    Unknown restart outcomes are retained as attempts and excluded from accuracy.
    Ground attacking/defending duels count each participant once; tag 703 wins,
    702 draws, 701 loses (accuracy 1801 is NOT synonymous with winning a duel).
    Source save attempts, not inferred residual shot outcomes, identify saves.
    """
    ids = set(ids)
    roles = {p['wyId']: SOURCE_ROLES[p['role']['name']] for p in players}
    groups = defaultdict(list)
    for event in events:
        if event['matchId'] in ids and event['matchPeriod'] in ('1H', '2H'):
            groups[event['matchId']].append(event)
    rows = []
    for match in matches:
        if match['wyId'] not in ids:
            continue
        match_events = groups[match['wyId']]
        data = {}; intervals = {}; clubs = {}
        for club, team in match['teamsData'].items():
            f = team['formation']; starts = {p['playerId']: 0 for p in f['lineup']}; ends = {p: 90 for p in starts}
            substitutions = f.get('substitutions')
            for sub in substitutions if isinstance(substitutions, list) else []:
                at = min(90, sub['minute']); ends[sub['playerOut']] = at
                starts[sub['playerIn']] = at; ends[sub['playerIn']] = 90
            for e in match_events:
                if e['playerId'] in starts and {1701, 1703} & {t['id'] for t in e['tags']}:
                    at = min(45, e['eventSec'] / 60) + (45 if e['matchPeriod'] == '2H' else 0)
                    ends[e['playerId']] = min(ends[e['playerId']], at)
            for pid, start in starts.items():
                minutes = max(0, ends[pid] - start)
                if minutes:
                    data[pid] = Counter(minutes=minutes, appearances=1)
                    intervals[pid] = (start, ends[pid]); clubs[pid] = int(club)
        goals = []
        for e in match_events:
            tags = {t['id'] for t in e['tags']}; subtype = e['subEventName']
            shot = e['eventName'] == 'Shot' or subtype in ('Penalty', 'Free kick shot')
            if shot and 101 in tags or 102 in tags:
                goal_for = e['teamId'] if 102 not in tags else next(int(c) for c in match['teamsData'] if int(c) != e['teamId'])
                at = min(45, e['eventSec'] / 60) + (45 if e['matchPeriod'] == '2H' else 0)
                goals.append((goal_for, at))
            s = data.get(e['playerId'])
            if s is None:
                continue
            if e['eventName'] == 'Pass' or subtype in PASS_RESTARTS:
                s['passes'] += 1
                known = bool(tags & {1801, 1802})
                s['passes_known'] += known; s['passes_completed'] += 1801 in tags
                if 1801 in tags and len(e['positions']) == 2:
                    a, b = e['positions']; distance = math.hypot((b['x'] - a['x']) * 1.05, (b['y'] - a['y']) * .68)
                    s['completed_located'] += 1; s['completed_long'] += distance >= 32
            if shot:
                s['shots'] += 1; s['goals'] += 101 in tags
                s['shots_on_target'] += bool(101 in tags or tags & set(range(1201, 1210))) and 2101 not in tags
            if 301 in tags:
                s['assists'] += 1
            if subtype in ('Ground attacking duel', 'Ground defending duel'):
                s['duels'] += 1; s['duels_won'] += 703 in tags; s['duels_drawn'] += 702 in tags
                if subtype == 'Ground attacking duel':
                    s['attacking_duels'] += 1; s['attacking_duels_won'] += 703 in tags; s['attacking_duels_drawn'] += 702 in tags
            if e['eventName'] == 'Save attempt':
                s['saves'] += 1801 in tags and 101 not in tags
                s['shots_faced'] += 1
        for pid, s in data.items():
            start, end = intervals[pid]
            s['goals_conceded'] = sum(club != clubs[pid] and start <= at <= end for club, at in goals)
            s['clean_sheets'] = int(s['minutes'] >= 60 and s['goals_conceded'] == 0)
        rows.append({'id': str(match['wyId']), 'players': {str(p): dict(s) for p, s in data.items()},
                     'roles': {str(p): roles[p] for p in data}})
    return rows


def generated_row(record, summary, players):
    roles = {p.player_id: p.role for p in players}
    data = {pid: Counter(s) for pid, s in summary['players'].items()}
    for s in data.values():
        s['passes_known'] = s['passes'] - s['passes_unknown']
        s['shots_faced'] = s['saves'] + s['goals_conceded']
    for e in record.events:
        if e.kind == 'pass' and e.outcome == 'completed' and e.start and e.end:
            s = data[e.player_id]; s['completed_located'] += 1
            s['completed_long'] += math.hypot(e.end.x - e.start.x, e.end.y - e.start.y) >= 32
    return {'id': record.fixture.match_id, 'players': {p: dict(s) for p, s in data.items()},
            'roles': {p: roles[p] for p in data}}


def summarize(rows, bootstrap=0, seed=60421):
    totals = {r: Counter() for r in ROLES}; people = defaultdict(Counter); roles = {}; clusters = []
    for row in rows:
        group = {r: Counter() for r in ROLES}
        for pid, counts in row['players'].items():
            role = row['roles'][pid]; roles[pid] = role
            totals[role].update(counts); people[pid].update(counts); group[role].update(counts)
        clusters.append(group)
    result = {'matches': len(rows), 'minimum_distribution_minutes': 900, 'roles': {}}
    for role in ROLES:
        eligible = [values(s) for p, s in people.items() if roles[p] == role and s['minutes'] >= 900]
        result['roles'][role] = {'counts': dict(totals[role]), 'rates': values(totals[role]),
            'players_900_minutes': len(eligible),
            'distributions': {k: describe([s[k] for s in eligible if s.get(k) is not None]) for k in values(totals[role])}}
    if bootstrap:
        rng = Random(seed); samples = {r: defaultdict(list) for r in ROLES}
        # Only these sufficient statistics enter values(). Expanded analytics
        # add many other counts; resampling those would waste work and does not
        # change any interval, draw index, denominator or observed statistic.
        needed = {'minutes', *RATE_FIELDS, *(k for pair in RATIOS.values() for k in pair)}
        bootstrap_clusters = [{r: {k: c[k] for k in needed if k in c} for r, c in group.items()} for group in clusters]
        for _ in range(bootstrap):
            sampled = {r: Counter() for r in ROLES}
            for group in rng.choices(bootstrap_clusters, k=len(bootstrap_clusters)):
                for r in ROLES:
                    sampled[r].update(group[r])
            for r in ROLES:
                for k, v in values(sampled[r]).items():
                    if v is not None: samples[r][k].append(v)
        result['bootstrap'] = {'method': 'whole-match cluster percentile', 'replicates': bootstrap, 'seed': seed, 'level': .95}
        for r in ROLES:
            result['roles'][r]['ci95'] = {k: [sorted(v)[round(.025*(len(v)-1))], sorted(v)[round(.975*(len(v)-1))]] for k, v in samples[r].items()}
    return result


def position_checks(observed, target, distribution_reference=None):
    """Declared engineering envelopes, not p-values or proof of equivalence.

    Fit against training only. CI95 is reported separately, never used to widen
    a failing tolerance. Rare rates need absolute floors; individual tails get
    wider envelopes because league formation and sample sizes differ.
    """
    checks = {}
    for role in ROLES:
        a = observed['roles'][role]; b = target['roles'][role]
        metrics = {'passes_per90': (.20, 2.), 'shots_per90': (.25, .15),
                   'goals_per90': (.30, .04), 'assists_per90': (.35, .04),
                   'duels_per90': (.25, .20), 'pass_completion': (0, .06),
                   'completed_long_share': (0, .08)}
        if role == 'GK':
            metrics.update({'assists_per90': (0, .015), 'saves_per90': (.20, .25), 'goals_conceded_per90': (.20, .20),
                            'save_rate': (0, .08), 'clean_sheet_rate': (0, .09)})
        else:
            metrics.update({'shot_accuracy': (0, .08), 'conversion': (0, .05), 'duel_win': (0, .09)})
        for metric, (relative, floor) in metrics.items():
            actual = a['rates'][metric]; expected = b['rates'][metric]; tolerance = max(floor, abs(expected or 0) * relative)
            checks[f'{role}.{metric}'] = {'actual': actual, 'target': expected, 'absolute_tolerance': tolerance,
                'passed': actual is not None and expected is not None and abs(actual - expected) <= tolerance}
        for metric in ('passes_per90', 'shots_per90'):
            for quantile in ('p10', 'p90'):
                reference = b if b['players_900_minutes'] else (distribution_reference or target)['roles'][role]
                actual = a['distributions'][metric][quantile]; expected = reference['distributions'][metric][quantile]
                tolerance = max(3 if metric == 'passes_per90' else .4, expected * .40)
                checks[f'{role}.{metric}.{quantile}'] = {'actual': actual, 'target': expected, 'absolute_tolerance': tolerance,
                    'reference': 'comparison' if reference is b else 'training_distribution_900_minutes',
                    'passed': a['players_900_minutes'] > 0 and reference['players_900_minutes'] > 0 and abs(actual - expected) <= tolerance}
    return checks


def formation_reference(population_target, source_positions, observed_positions, concentration_reference=None):
    """Direct standardization to simulated minutes; never use simulated outcomes.

    A 4-3-3 assigns more forward minutes than the reference league. Raw goal or
    assist shares confound that exposure with individual scoring/creation rates.
    """
    target = dict(population_target)
    projected = {}
    for group, rate in (('goal_role_share', 'goals_per90'), ('assist_role_share', 'assists_per90')):
        weighted = {r: source_positions['roles'][r]['rates'][rate] * observed_positions['roles'][r]['counts']['minutes'] for r in ROLES}
        projected[group] = sum(weighted.values())
        target[group] = {r: v / sum(weighted.values()) for r, v in weighted.items()}
    # The ratio must use the SAME role exposure as its numerator/denominator.
    # Preserve the reference's own-goal share in the team-goal denominator.
    player_fraction=population_target['per_match'].get('player_goals',population_target['per_match']['goals'])/population_target['per_match']['goals']
    target['assisted_goal_share']=projected['assist_role_share']/projected['goal_role_share']*player_fraction
    if concentration_reference is not None:
        target['average_top_scorer_team_share'] = concentration_reference['average_top_scorer_team_share']
    return target
