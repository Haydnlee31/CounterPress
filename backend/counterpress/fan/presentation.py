"""Reviewed fan wording. Statistics and chart values never come from model prose."""
from hashlib import sha256
import json


VERSION = 'fan-personalization-v1'


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def words(preferences, en, zh):
    return zh if preferences.language == 'zh-Hans' else en


LABELS = {
    'appearances': ('Matches', '出场', 'count'),
    'minutes': ('Minutes played', '出场分钟', 'minutes'),
    'goals': ('Goals', '进球', 'count'),
    'assists': ('Assists', '助攻', 'count'),
    'shots': ('Shots', '射门', 'count'),
    'shots_on_target': ('Shots on target', '射正', 'count'),
    'passes': ('Passes attempted', '传球尝试', 'count'),
    'passes_completed': ('Completed passes', '成功传球', 'count'),
    'recoveries': ('Ball recoveries', '夺回球权', 'count'),
    'duels_won': ('Challenges won', '争抢成功', 'count'),
    'saves': ('Saves', '扑救', 'count'),
    'clean_sheets': ('Clean sheets', '零封', 'count'),
    'goals_conceded': ('Goals conceded', '失球', 'count'),
    'key_passes': ('Passes leading to a shot', '形成射门的传球', 'count'),
    'goals_per90': ('Goals per 90 minutes', '每90分钟进球', 'per90'),
    'assists_per90': ('Assists per 90 minutes', '每90分钟助攻', 'per90'),
    'pass_accuracy_pct': ('Pass completion', '传球成功率', 'percent'),
    'shot_accuracy_pct': ('Shots on target rate', '射正率', 'percent'),
    'duel_win_pct': ('Challenges won rate', '争抢成功率', 'percent'),
    'xg': ('Expected goals', '预期进球', 'estimate'),
    'passing_above_expected_per100': ('Passing above expected per 100', '每100次传球超出预期的成功次数', 'estimate'),
}
CASUAL = {
    'GK': ('appearances', 'minutes', 'saves', 'clean_sheets', 'goals_conceded', 'pass_accuracy_pct'),
    'DF': ('appearances', 'minutes', 'duels_won', 'recoveries', 'goals', 'pass_accuracy_pct'),
    'MF': ('appearances', 'goals', 'assists', 'key_passes', 'passes_completed', 'pass_accuracy_pct'),
    'FW': ('appearances', 'goals', 'assists', 'shots_on_target', 'goals_per90', 'pass_accuracy_pct'),
    'club': ('appearances', 'goals', 'goals_conceded', 'clean_sheets', 'shots_on_target', 'pass_accuracy_pct'),
}
FOCUS = {
    'balanced': (), 'scoring': ('goals', 'shots_on_target', 'goals_per90'),
    'creating': ('assists', 'key_passes', 'assists_per90'),
    'passing': ('passes_completed', 'passes', 'pass_accuracy_pct'),
    'defending': ('duels_won', 'recoveries', 'saves'),
}


def metric_tiles(stats, rate_values, coverage, preferences, role='FW'):
    keys = list(dict.fromkeys((*FOCUS[preferences.metric_focus], *CASUAL[role])))
    if preferences.depth == 'analyst':
        keys = list(dict.fromkeys((*keys, *LABELS)))
    else:
        keys = keys[:6]
    output = []
    for key in keys:
        en, zh, unit = LABELS[key]
        value = rate_values.get(key) if key in rate_values else stats.get(key)
        missing = 0
        if key in ('assists', 'assists_per90'):
            missing = coverage.get('assists_unavailable_matches', 0)
        elif key == 'key_passes':
            missing = coverage.get('key_passes_unavailable_matches', coverage.get('assists_unavailable_matches', 0))
        elif key in ('saves', 'recoveries'):
            missing = coverage.get(key + '_unavailable_matches', 0)
        status = 'partial' if missing else 'available' if value is not None else 'unavailable'
        detail=coverage.get('metrics',{}).get('assists' if key=='assists_per90' else key)
        coverage_label=None
        if detail and detail['recorded_matches']<detail['total_matches']:
            covered,total=detail['recorded_matches'],detail['total_matches']
            coverage_label=words(preferences,f'{covered} of {total} matches',f'已记录 {covered}/{total} 场')
            # Explicit provider awards may supply a lower bound even where full
            # shot-assist coverage is absent. A missing zero is never observed zero.
            if not covered and (not value or unit=='per90'):status='unavailable'
        if key == 'xg' and stats['xg_shots'] != stats['shots']:
            status = 'partial' if stats['xg_shots'] else 'unavailable'
        if key == 'passing_above_expected_per100' and stats['xpass_passes'] != stats['passes']:
            status = 'partial' if stats['xpass_passes'] else 'unavailable'
        output.append({'metric': key, 'label': words(preferences, en, zh),
                       'value': None if status == 'unavailable' else value,
                       'unit': unit, 'coverage': status,
                       'coverage_label':coverage_label,
                       'denominator': detail['covered_minutes'] if unit=='per90' and detail else stats['minutes'] if unit == 'per90' else
                           stats['passes'] - stats['passes_unknown'] if key == 'pass_accuracy_pct' else
                           stats['shots'] if key == 'shot_accuracy_pct' else
                           stats['duels'] - stats['duels_unknown'] if key == 'duel_win_pct' else None})
    return output


def action(kind, subject_id, label, **extra):
    # Semantic navigation targets let the colleague own routes and layout.
    return {'kind': kind, 'subject_id': subject_id, 'label': label, **extra}


def fact(subject_kind, subject_id, metric, value, scope, evidence_id, unit='count'):
    return {'subject_kind': subject_kind, 'subject_id': subject_id, 'metric': metric,
            'value': value, 'unit': unit, 'scope': scope, 'evidence_id': evidence_id}


def card(identity, kind, title, text, facts, evidence, navigation, priority=0):
    return {'id': identity, 'kind': kind, 'title': title, 'text': text, 'facts': facts,
            'evidence': evidence, 'action': navigation, 'priority': priority,
            'content_version': fingerprint({'facts': facts, 'evidence': evidence})}
