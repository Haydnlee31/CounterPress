"""A pinned live observation is evidence, never a client-authored model prompt."""
import re

from counterpress.fan.contracts import MatchRequest
from counterpress.personalization.contracts import Fixture


def observation_question(request):
    """Only the selected passage uses the card's window; other tools retain scope.

    A subsequent whole-match, goal or named-player question must not silently
    inherit a three-minute comparison. Unsupported questions still pass through
    the assistant's ordinary intent and safety checks.
    """
    return bool(request.observation_id and re.fullmatch(
        r'(?:what (?:has )?changed in this passage of play|'
        r'why does this (?:change|observation|insight) matter|'
        r'why(?: does it matter)?|what is driving this change|'
        r'explain this (?:observation|insight)|'
        r'这段比赛发生了什么变化|为什么这段变化重要)[?.!？。]*',
        request.question.strip(), re.I))


def pinned_observation(service, request):
    """Caller holds the source snapshot. Recompute; never trust submitted facts."""
    from counterpress.fan.service import FanService

    if not request.observation_id:
        return None
    result = FanService(service.career).observations(request.match_id, MatchRequest(
        preferences=request.preferences, cutoff=request.playback,
        through_sequence=request.through_sequence, card_budget=5))
    candidate = next((row for row in result['observations'] if row['id'] == request.observation_id), None)
    if candidate is None or candidate['fingerprint'] != request.observation_fingerprint:
        raise ValueError('The selected observation has changed')
    return candidate


def observation_answer(service, request):
    """Verified counts and exact windows for both structured and model workflows."""
    from counterpress.fan.observations import RULE_VERSION

    row = pinned_observation(service, request)
    fixture = Fixture.model_validate_json(service.store.row(request.match_id)['fixture'])
    zh = request.preferences.language == 'zh-Hans'
    t = lambda en, cn: cn if zh else en
    metrics = row['metrics']
    subject_id = row['player_id'] or row['club_id']
    subject_kind = 'player' if row['player_id'] else 'club'
    registry = service.store.players if row['player_id'] else service.store.clubs
    name = registry[subject_id].name
    labels = {
        'shots': ('Shots', '射门'),
        'pass_completion_pct': ('Pass completion', '传球成功率'),
        'recorded_on_ball_actions': ('Recorded on-ball actions', '记录中的有球动作'),
    }
    metric_label = t(*labels[metrics['metric']])

    def clock(ms):
        # Explicit half labels avoid treating 1st-half added time as 2nd-half time.
        seconds = ms // 1000
        return f'{seconds // 60}:{seconds % 60:02d}'

    windows = row['windows']
    half = t('First half' if windows[0]['period'] == 1 else 'Second half',
             '上半场' if windows[0]['period'] == 1 else '下半场')
    times = [f'{clock(w["start_ms"])}–{clock(w["end_ms"])}' for w in windows]
    evidence = {'match_id': request.match_id, 'observation_id': row['id'],
                'observation_fingerprint': row['fingerprint'], 'reducer_version': RULE_VERSION,
                'through_sequence': request.through_sequence, 'events': row['evidence'],
                'source_kind': fixture.source_kind, 'sample_sizes': metrics['sample_sizes']}
    scope = {'match_id': request.match_id, 'cutoff': request.playback.model_dump(),
             'as_of': service.scope(request)[0], 'window': 'rolling_observation',
             'time_label': f'{half} · {clock(request.playback.elapsed_ms)}'}
    facts = []
    for index, key in enumerate(('before', 'after')):
        value_fact = {'subject_id': subject_id, 'subject_kind': subject_kind, 'subject_name': name,
            'metric': metrics['metric'], 'label': metric_label, 'value': metrics[key], 'unit': metrics['unit'],
            'scope': {**scope, 'observation_window': windows[index], 'window_label': f'{half} · {times[index]}'},
            'coverage': None, 'evidence': evidence, 'href': f'#football/{subject_kind}/{subject_id}'}
        facts.append(value_fact)
        if metrics['metric'] == 'pass_completion_pct':
            for metric, label, values in (
                    ('completed_passes', t('Completed passes', '成功传球'), metrics['completed']),
                    ('passes', t('Pass attempts', '传球尝试'), metrics['attempted'])):
                facts.append({**value_fact, 'metric': metric, 'label': label,
                              'value': values[index], 'unit': 'count'})
    values = [metrics['before'], metrics['after']]
    interpretation = row.get('interpretation')
    text = [f'{row.get("summary", row["text"])} {half} · {times[0]} → {times[1]}.']
    if interpretation:
        # Its own references may include the opposing team's regained possession
        # or an earlier goal, beyond the original club's comparison evidence.
        text.insert(0, interpretation['text'])
        for item in interpretation['facts']:
            kind = item.get('subject_kind', subject_kind)
            entity = item.get('subject_id', subject_id)
            entities = service.store.players if kind == 'player' else service.store.clubs
            if kind not in ('club', 'player') or entity not in entities:
                raise ValueError('Invalid diagnostic subject')
            window = item.get('scope_window', 'after')
            if window not in ('before', 'after', 'at_cutoff'):
                raise ValueError('Invalid diagnostic window')
            diagnostic_scope = {**scope, 'window': 'match_at_cutoff' if window == 'at_cutoff' else 'rolling_observation',
                                'window_label': scope['time_label']}
            if window != 'at_cutoff':
                index = 0 if window == 'before' else 1
                diagnostic_scope.update(observation_window=windows[index], window_label=f'{half} · {times[index]}')
            facts.append({'subject_id': entity, 'subject_kind': kind, 'subject_name': entities[entity].name,
                'metric': item['metric'], 'label': item['label'], 'value': item['value'], 'unit': item['unit'],
                'scope': diagnostic_scope, 'coverage': None,
                'evidence': {**evidence, 'events': interpretation['evidence'],
                             'interpretation_kind': interpretation['kind']},
                'href': f'#football/{kind}/{entity}'})
    return {'status': 'answered', 'title': row['title'],
            'text': text, 'observation_interpretation': bool(interpretation),
            'facts': facts, 'actions': [], 'visual': {'kind': 'bars',
                'label': f'{name} · {metric_label}',
                'items': [{'label': f'{half} · {label}', 'value': value, 'unit': metrics['unit']}
                          for label, value in zip(times, values)]}}
