"""Football diagnostics over observed actions, with explicit supporting evidence.

No inferred off-ball shape, pressure, assist credit or expected-goals values.
Linked attacks require known recipients; chronology alone is not possession.
"""
from collections import Counter
from math import dist

from counterpress.assistant.intelligence import SUCCESS, RECOVERED
from .presentation import fingerprint, words


def reference(e):
    return {key: value for key, value in e.model_dump(mode='json').items()
            if key in {'match_id', 'event_id', 'revision', 'delivery_sequence', 'period',
                       'elapsed_ms', 'available_period', 'available_ms', 'source_reference',
                       'club_id', 'player_id', 'recipient_id', 'kind', 'outcome', 'start', 'end',
                       'restart', 'goal_for'}}


def shot_path(events, index, start_ms):
    """A contiguous, recipient-verified suffix, bounded to fifteen seconds."""
    shot = events[index]
    chain = [shot]
    if shot.restart or shot.penalty:
        return chain
    holder = shot.player_id
    for e in reversed(events[:index]):
        if e.period != shot.period or e.elapsed_ms <= start_ms or shot.elapsed_ms - e.elapsed_ms > 15000:
            break
        if e.kind == 'pressure':
            continue
        if e.club_id != shot.club_id:
            break
        if e.kind == 'pass':
            if e.outcome not in SUCCESS or e.recipient_id != holder:
                break
        elif e.kind == 'carry':
            if e.player_id != holder or e.outcome not in {'controlled', 'completed', 'complete', 'established', 'successful'}:
                break
        elif e.kind == 'recovery':
            if e.player_id != holder or e.outcome not in RECOVERED:
                break
        else:
            break
        chain.append(e)
        holder = e.player_id
        if e.restart or e.kind == 'recovery':
            break
    return list(reversed(chain))


def inside_box(e):
    return bool(e.start and e.start.x >= 88.5 and 13.84 <= e.start.y <= 54.16)


def long_pass(e):
    return bool(e.start and e.end and dist((e.start.x, e.start.y), (e.end.x, e.end.y)) >= 30)


def interpret_candidates(fixture, events, candidates, preferences, club_names, player_names):
    """Return only observations with an explanation beyond the changed count.

    Count evidence is retained separately from diagnostic/score evidence. Both
    are covered by the new fingerprint and rechecked when the viewer asks why.
    """
    output = []
    t = lambda en, zh: words(preferences, en, zh)
    for row in candidates:
        cid, pid = row['club_id'], row['player_id']
        name = club_names[cid]
        opponent = fixture.away_id if cid == fixture.home_id else fixture.home_id
        a, b = row['windows']
        groups = [[e for e in events if e.club_id == cid and e.period == w['period']
                   and w['start_ms'] < e.elapsed_ms <= w['end_ms']] for w in (a, b)]
        current = groups[1]
        shots = [[e for e in group if e.kind == 'shot' and e.outcome != 'own_goal'] for group in groups]
        paths = [shot_path(events, i, b['start_ms']) for i, e in enumerate(events)
                 if e.kind == 'shot' and e.outcome != 'own_goal' and e.period == b['period']
                 and b['start_ms'] < e.elapsed_ms <= b['end_ms']]
        facts, used = [], []
        diagnostic = None

        def fact(metric, label, value, *, subject=None, player=False, scope='after'):
            facts.append({'metric': metric, 'label': label, 'value': value, 'unit': 'count',
                          'subject_id': subject or cid, 'subject_kind': 'player' if player else 'club',
                          'scope_window': scope})

        def choose(kind, headline, text, evidence):
            nonlocal diagnostic
            diagnostic = {'kind': kind, 'headline': headline, 'text': text}
            used.extend(evidence)

        if row['kind'] == 'shots_increase':
            quick = [p for p in paths if p[-1].club_id == cid and p[0].kind == 'recovery'
                     and not p[0].restart and len(p) > 1]
            located = all(e.start for group in shots for e in group)
            boxes = [sum(inside_box(e) for e in group) for group in shots]
            on_target = [sum(e.outcome in {'goal', 'saved', 'on_target'} for e in group) for group in shots]
            known_outcomes = all(e.outcome in {'goal', 'saved', 'on_target', 'blocked', 'off_target'} for group in shots for e in group)
            if len(quick) >= 2:
                choose('regain_chances', t('Winning it back is creating chances', '夺回球权后迅速制造机会'),
                    t(f'{name} turned {len(quick)} ball recoveries into shots within 15 seconds. Winning it back is giving them a quick route to goal.',
                      f'{name}有{len(quick)}次夺回球权后在15秒内完成射门，抢回球权成为快速制造机会的途径。'),
                    [e for p in quick for e in p])
                fact('regain_to_shot_count', t('Shots within 15 seconds of a regain', '夺回球权15秒内射门'), len(quick))
            elif located and boxes[1] >= 2 and boxes[1] - boxes[0] >= 2:
                choose('closer_chances', t('More chances inside the box', '禁区内机会增多'),
                    t(f'{name} are finding more shots inside the penalty area: {boxes[1]} attempts, compared with {boxes[0]} in the previous spell.',
                      f'{name}本时段有{boxes[1]}次禁区内射门，此前时段为{boxes[0]}次。'), shots[0] + shots[1])
                for scope, n in zip(('before', 'after'), boxes):
                    fact('shots_inside_box', t('Shots inside the penalty area', '禁区内射门'), n, scope=scope)
            elif located and boxes[1] == 0:
                choose('range_without_box_chances', t('More shots, still from range', '射门增多，但仍是远射'),
                    t(f'All {len(shots[1])} of {name}’s recent shots came from outside the box. The extra attempts have not brought a shot from inside the area.',
                      f'{name}最近{len(shots[1])}次射门全部来自禁区外，增加的射门仍未进入禁区。'), shots[1])
                fact('shots_outside_box', t('Shots outside the penalty area', '禁区外射门'), len(shots[1]))
                fact('shots_inside_box', t('Shots inside the penalty area', '禁区内射门'), 0)
            elif known_outcomes and on_target[1] == 0:
                choose('no_shots_on_target', t('More attempts, none on target', '射门增多，但尚未射正'),
                    t(f'None of {name}’s {len(shots[1])} recent shots were on target: they were blocked or missed. The rise in attempts has not yet produced a shot on target.',
                      f'{name}最近{len(shots[1])}次射门都被封堵或偏出，射门增加尚未带来射正。'), shots[1])
                fact('shots_on_target', t('Shots on target', '射正'), 0)
            elif known_outcomes and on_target[1] >= 2 and on_target[1] - on_target[0] >= 2:
                choose('shots_testing_goal', t('The extra shots are finding the target', '增加的射门正在命中目标'),
                    t(f'{name} have put {on_target[1]} shots on target, up from {on_target[0]}. Their increase in attempts is also bringing more shots on target.',
                      f'{name}射正次数由{on_target[0]}次增加到{on_target[1]}次，增加的射门也带来更多射正。'), shots[0] + shots[1])
                for scope, n in zip(('before', 'after'), on_target):
                    fact('shots_on_target', t('Shots on target', '射正'), n, scope=scope)

        elif row['kind'] == 'passing_decline':
            failed = [e for e in current if e.kind == 'pass' and e.outcome == 'incomplete']
            danger = []
            for path in paths:
                regain = path[0]
                if regain.club_id != opponent or regain.kind != 'recovery' or regain.restart or len(path) < 2:
                    continue
                prior = next((e for e in reversed(events[:events.index(regain)]) if e.kind != 'pressure'), None)
                if prior and prior in failed and 0 <= regain.elapsed_ms - prior.elapsed_ms <= 3000 and path[-1].elapsed_ms - prior.elapsed_ms <= 15000:
                    danger.append([prior, *path])
            passes = [e for e in current if e.kind == 'pass']
            located = all(e.start and e.end for e in passes)
            long = [e for e in passes if long_pass(e)]
            short = [e for e in passes if not long_pass(e)]
            lost_long = [e for e in long if e.outcome == 'incomplete']
            deep = [e for e in failed if e.start and e.start.x < 52.5]
            handoffs = []
            for mistake in deep:
                following = next((e for e in events[events.index(mistake)+1:] if e.kind != 'pressure'), None)
                if (following and following.period == mistake.period and following.club_id == opponent
                        and following.kind == 'pass' and following.outcome in SUCCESS and not following.restart
                        and 0 <= following.elapsed_ms - mistake.elapsed_ms <= 5000
                        and mistake.end and following.start and following.start.x >= 52.5
                        and dist((105-mistake.end.x, 68-mistake.end.y),
                                 (following.start.x, following.start.y)) <= 5):
                    handoffs.append([mistake, following])
            if danger:
                rival = club_names[opponent]
                verb = 'was' if len(danger) == 1 else 'were'
                choose('mistakes_to_opponent_shots', t('Misplaced passes are leading to chances', '传球失误后出现对手射门'),
                    t(f'{len(danger)} of {name}’s failed passes {verb} followed by {rival} winning the ball and shooting within 15 seconds. The misplaced passes are opening a route to goal for the opposition.',
                      f'{name}有{len(danger)}次传球失误后，{rival}夺回球权并在15秒内射门，这些失误已带来对手的射门机会。'), [e for p in danger for e in p])
                fact('opponent_shots_after_failed_pass', t('Shots after the opponent’s failed pass', '对方传球失误后的射门'), len(danger), subject=opponent)
            elif located and len(lost_long) >= 2 and len(lost_long) * 3 >= len(failed) * 2:
                comparison = t(f', compared with {sum(e.outcome in SUCCESS for e in short)} of {len(short)} shorter passes.', f'，较短传球{len(short)}次成功{sum(e.outcome in SUCCESS for e in short)}次。') if short else '。' if preferences.language == 'zh-Hans' else '.'
                choose('long_pass_failures', t('The long passes are breaking down', '长传频频失误'),
                    t(f'Passes of at least 30 metres account for {len(lost_long)} of {name}’s {len(failed)} failed passes. {len(long)-len(lost_long)} of {len(long)} long passes reached a teammate{comparison}',
                      f'{name}{len(failed)}次失败传球中有{len(lost_long)}次是至少30米的长传；长传{len(long)}次成功{len(long)-len(lost_long)}次{comparison}'), passes)
                for metric, label, value in [('failed_long_passes', 'Failed long passes', len(lost_long)), ('failed_passes', 'Failed passes', len(failed)),
                        ('long_pass_attempts', 'Long pass attempts', len(long)), ('long_passes_completed', 'Completed long passes', len(long)-len(lost_long)),
                        ('short_pass_attempts', 'Shorter pass attempts', len(short)), ('short_passes_completed', 'Completed shorter passes', sum(e.outcome in SUCCESS for e in short))]:
                    fact(metric, label, value)
            elif failed and all(e.start for e in failed) and len(deep) >= 2 and len(deep) * 3 >= len(failed) * 2 and handoffs:
                rival = club_names[opponent]
                choose('deep_pass_failures', t(f'Errors are giving {rival} territory', f'失误让{rival}获得前场球权'),
                    t(f'{len(deep)} of {name}’s {len(failed)} failed passes started in their own half. After {len(handoffs)} of those errors, {rival} made the next completed pass from {name}’s half.',
                      f'{name}{len(failed)}次失败传球中有{len(deep)}次从本方半场发起，其中{len(handoffs)}次之后，{rival}紧接着在{name}半场完成传球。'), failed + [e for pair in handoffs for e in pair])
                fact('own_half_failed_passes', t('Failed passes starting in own half', '本方半场发起的失败传球'), len(deep))
                fact('failed_passes', t('Failed passes', '失败传球'), len(failed))
                fact('completed_passes_after_opponent_error', t('Completed attacking-half passes after an opponent error', '对手失误后的前场成功传球'), len(handoffs), subject=opponent)

        elif row['kind'] == 'player_involvement':
            appearance = next(ap for ap in fixture.appearances if ap.player_id == pid)
            offset = fixture.period_lengths_ms[0] if b['period'] == 2 else 0
            if appearance.start_ms > offset + a['start_ms'] or appearance.end_ms < offset + b['end_ms']:
                continue  # Do not compare a substitute's partial and full exposure.
            person = player_names[pid]
            own = [[e for e in group if e.player_id == pid and e.kind in {'pass', 'carry', 'shot', 'recovery'}] for group in groups]
            creation = [p for p in paths if p[-1].club_id == cid and any(e.player_id == pid for e in p[:-1])]
            entries = [[e for e in group if e.kind == 'pass' and e.outcome in SUCCESS and e.start and e.end and e.start.x < 70 <= e.end.x] for group in own]
            deep = [e for e in own[1] if e.start and e.start.x < 52.5]
            if creation:
                choose('player_chance_contribution', t(f'{person} is helping create the shots', f'{person}参与制造射门'),
                    t(f'{person} was involved before the shot in {len(creation)} of {name}’s {len(shots[1])} recent shooting moves. The extra involvement is connected to chances.',
                      f'{name}最近{len(shots[1])}次射门中，{person}在{len(creation)}次射门前的连续进攻中参与传球、带球或夺回球权，参与增多与机会相连。'), [e for p in creation for e in p])
                fact('shot_buildups_involved', t('Shooting moves involved in before the shot', '射门前参与的进攻次数'), len(creation), subject=pid, player=True)
            elif len(entries[1]) >= 2 and len(entries[1]) > len(entries[0]) and all(e.start and e.end for group in own for e in group if e.kind == 'pass'):
                choose('player_final_third_entries', t(f'{person} is moving play forward', f'{person}推动进攻向前'),
                    t(f'{person} completed {len(entries[1])} passes from outside the final third into it, compared with {len(entries[0])} before. The extra involvement is moving the ball into attacking territory.',
                      f'{person}从进攻三区外传入三区的成功传球由{len(entries[0])}次增至{len(entries[1])}次，增加的参与正在推动进攻。'), own[0] + own[1])
                for scope, count in zip(('before', 'after'), map(len, entries)):
                    fact('final_third_entries', t('Completed passes entering the final third', '传入进攻三区的成功传球'), count, subject=pid, player=True, scope=scope)
            elif all(e.start for e in own[1]) and len(deep) >= 4 and len(deep) / len(own[1]) >= .8:
                choose('player_deep_involvement', t(f'{person} is getting involved deeper', f'{person}更多参与后场活动'),
                    t(f'{len(deep)} of {person}’s {len(own[1])} recent on-ball actions started in their own half. Their increased involvement is concentrated deeper on the pitch.',
                      f'{person}最近{len(own[1])}次有球动作中有{len(deep)}次始于本方半场，参与集中在更靠后的区域。'), own[1])
                fact('own_half_actions', t('Actions starting in own half', '本方半场有球动作'), len(deep), subject=pid, player=True)

        if diagnostic is None:
            continue
        goals = [e for e in events if e.goal_for]
        score = Counter(e.goal_for for e in goals)
        score_text = ''
        if score[cid] < score[opponent]:
            score_text = t(f'{name} are chasing the game at {score[cid]}–{score[opponent]}. ', f'{name}目前以{score[cid]}比{score[opponent]}落后。')
        elif score[cid] > score[opponent] and row['kind'] == 'passing_decline':
            score_text = t(f'{name} lead {score[cid]}–{score[opponent]}. ', f'{name}目前以{score[cid]}比{score[opponent]}领先。')
        if score_text:
            used.extend(goals)
            fact('goals_for', t('Goals for at this point', '此时本队进球'), score[cid], scope='at_cutoff')
            fact('goals_against', t('Goals conceded at this point', '此时对手进球'), score[opponent], scope='at_cutoff')
        diagnostic['text'] = score_text + diagnostic['text']
        diagnostic['facts'] = facts
        diagnostic['evidence'] = [reference(e) for e in {e.event_id: e for e in used}.values()]
        diagnostic['context'] = {'score_for': score[cid], 'score_against': score[opponent],
                                 'period': b['period'], 'elapsed_ms': b['end_ms']}
        enriched = {**row, 'summary': row['text'], 'title': diagnostic['headline'],
                    'text': diagnostic['text'], 'interpretation': diagnostic}
        # Concrete chance consequences outrank activity alone, while retaining
        # the existing club/player preference contribution to the ranking.
        weight = {'mistakes_to_opponent_shots': 90, 'regain_chances': 70,
                  'closer_chances': 50, 'player_chance_contribution': 50,
                  'player_final_third_entries': 30, 'deep_pass_failures': 25,
                  'long_pass_failures': 15, 'range_without_box_chances': 20,
                  'no_shots_on_target': 20, 'shots_testing_goal': 25,
                  'player_deep_involvement': -30}
        enriched['priority'] += weight[diagnostic['kind']]
        enriched['fingerprint'] = fingerprint({'rule_version': 'live-observations-v2-diagnostics',
            'preferences': preferences.model_dump(), 'observation': {k:v for k,v in enriched.items() if k != 'fingerprint'}})
        output.append(enriched)
    return sorted(output, key=lambda row: (-row['priority'], row['id']))
