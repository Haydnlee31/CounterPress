"""Preference-specific projections over one immutable, revision-aware football view.

Preferences are supplied by the caller, never stored or shared by the service.
All methods run under the career store's read/write lock through the API boundary.
"""
from datetime import datetime
import json

from counterpress.assistant.intelligence import goal_buildup
from counterpress.personalization.contracts import Fixture
from counterpress.personalization.metrics import digest, rates, select_events
from counterpress.personalization.coverage import metric_coverage,covered_rates
from counterpress.personalization.service import match_card
from .presentation import VERSION, action, card, fact, fingerprint, metric_tiles, words


class PreferenceError(ValueError):
    pass


class FanService:
    def __init__(self, career, snapshots=None):
        self.career = career
        self.store = career.store
        self.snapshots = snapshots

    def validate(self, preferences):
        clubs = {*preferences.favorite_club_ids}
        players = {*preferences.favorite_player_ids}
        if preferences.focus_player_id:
            players.add(preferences.focus_player_id)
        if not clubs <= self.store.clubs.keys() or not players <= self.store.players.keys():
            raise PreferenceError('Choose registered clubs and players')
        return preferences

    def envelope(self, request):
        p = self.validate(request.preferences)
        return {'version': VERSION, 'request_id': request.request_id,
                'preferences': p.model_dump(), 'preference_id': fingerprint(p.model_dump()),
                'dataset_id': self.store.manifest['files']['ledger.json.gz']}

    def player(self, pid):
        return self.store.players[pid].model_dump(mode='json', exclude={'involvement', 'passing', 'finishing'})

    def relevance(self, player_ids, club_ids, preferences):
        players = sorted(set(player_ids) & set(preferences.favorite_player_ids))
        clubs = sorted(set(club_ids) & set(preferences.favorite_club_ids))
        primary = preferences.primary_club_id in club_ids if preferences.primary_club_id else False
        return {'score': 100 * bool(players) + 40 * primary + 20 * bool(clubs),
                'favorite_player_ids': players, 'favorite_club_ids': clubs,
                'reason': words(preferences, 'Featuring a player you follow', '有你关注的球员参与') if players else
                    words(preferences, 'From a club you follow', '来自你关注的俱乐部') if clubs else
                    words(preferences, 'Around the grounds', '球场动态')}

    def profile(self, subject, kind, request):
        envelope = self.envelope(request)
        p = request.preferences
        cutoff = request.cutoff()
        profile = self.career.profile(subject, kind, request.season, cutoff)
        entity = profile['subject']; name = entity['name']
        scope = {'kind': 'career' if request.season is None else 'season',
                 'season': request.season, 'before': cutoff}
        evidence_id = profile['evidence']['baseline_id']
        cards = []
        for insight in profile['insights']:
            if insight['type'] == 'best_scoring_season':
                season, goals = insight['season'], insight['goals']
                cards.append(card(f'{kind}:{subject}:best-scoring-season', 'best_scoring_season',
                    words(p, 'Best scoring season', '进球最多的赛季'),
                    words(p, f'{name} scored {goals} goals in {season}.', f'{name}在{season}赛季打进{goals}球。'),
                    [fact(kind, subject, 'goals', goals, {**scope, 'kind': 'season', 'season': season}, evidence_id)],
                    {'baseline_id': evidence_id, 'match_ids': insight['match_ids']},
                    action('history', subject, words(p, 'View that season', '查看该赛季'), subject_kind=kind, season=season)))
            elif insight['type'] == 'recent_scoring_rate':
                goals, matches = insight['goals'], insight['matches']
                goal_word='goal' if goals==1 else 'goals'
                appearance_word='appearance' if matches==1 else 'appearances'
                text = words(p, f'{name} has scored {goals} {goal_word} in the last {matches} {appearance_word}.',
                             f'{name}最近{matches}次出场打进{goals}球。')
                facts = [fact(kind, subject, 'goals', goals, {**scope, 'last_appearances': matches}, evidence_id),
                         fact(kind, subject, 'appearances', matches, {**scope, 'last_appearances': matches}, evidence_id)]
                if p.depth == 'analyst':
                    rate = insight['goals_per90']
                    text += words(p, f' That is {rate:.2f} goals per 90 across {insight["minutes"]:g} minutes.',
                                  f'累计出场{insight["minutes"]:g}分钟，每90分钟进球{rate:.2f}个。')
                    facts += [fact(kind, subject, 'goals_per90', rate, {**scope, 'last_appearances': matches}, evidence_id, 'per90'),
                              fact(kind, subject, 'minutes', insight['minutes'], {**scope, 'last_appearances': matches}, evidence_id, 'minutes')]
                cards.append(card(f'{kind}:{subject}:recent-form', 'recent_form', words(p, 'Recent form', '近期状态'), text,
                    facts, {'baseline_id': evidence_id, 'match_ids': insight['match_ids']},
                    action('history', subject, words(p, 'See recent matches', '查看近期比赛'), subject_kind=kind)))
        questions = self.profile_questions(subject, kind, p, profile, cutoff, request.season)
        return {**envelope, 'as_of': cutoff, 'profile': profile, 'presentation': {
            'is_favorite': subject in (p.favorite_player_ids if kind == 'player' else p.favorite_club_ids),
            'tiles': metric_tiles(profile['totals'], profile['rates'], profile['coverage'], p, entity.get('role', 'club')),
            'cards': cards, 'questions': questions,
            'theme_club_id': p.primary_club_id or entity['club_id'],
            'activity_map': {'label': words(p, 'Where the action happens', '参与进攻与争抢的区域'), **profile['heatmap']}}}

    def profile_questions(self, subject, kind, p, profile, cutoff, season):
        questions = []
        if profile['recent_form']['matches']:
            questions.append({'id': f'{kind}:{subject}:form',
                'text': words(p, f'How is {profile["subject"]["name"]} doing lately?', f'{profile["subject"]["name"]}近期表现如何？'),
                'intent': 'recent_form', 'context': {'subject_kind': kind, 'subject_id': subject, 'as_of': cutoff, 'season': season},
                'action': action('history', subject, words(p, 'View recent form', '查看近期状态'), subject_kind=kind),
                'answer_mode': 'data_view'})
        if kind == 'player' and len(profile['seasons']) >= 2:
            questions.append({'id': f'player:{subject}:seasons',
                'text': words(p, 'How do these seasons compare?', '这些赛季的表现有何不同？'),
                'intent': 'season_comparison', 'context': {'subject_kind': kind, 'subject_id': subject, 'as_of': cutoff},
                'action': action('profile', subject, words(p, 'Compare seasons', '比较赛季'), subject_kind=kind),
                'answer_mode': 'data_view'})
        return questions

    def compare(self, request):
        envelope = self.envelope(request); cutoff = request.cutoff()
        # One cutoff for every player, including requests that omit as_of.
        fixed = request.model_copy(update={'as_of': cutoff})
        profiles = [self.profile(pid, 'player', fixed)['profile'] for pid in request.player_ids]
        keys = ('appearances', 'minutes', 'goals', 'assists', 'shots_on_target', 'goals_per90',
                'assists_per90', 'pass_accuracy_pct', 'duel_win_pct', 'saves')
        analytical = request.preferences.model_copy(update={'depth': 'analyst'})
        rows = {p['subject']['player_id']: {r['metric']: r for r in metric_tiles(p['totals'], p['rates'], p['coverage'], analytical, p['subject']['role'])} for p in profiles}
        for tiles in rows.values():
            for tile in tiles.values():
                if tile['unit']=='per90' and (tile['denominator'] or 0)<180:tile['value']=None
        return {**envelope, 'as_of': cutoff, 'season': request.season,
                'players': [p['subject'] for p in profiles],
                'metrics': [{'metric': key, 'label': rows[request.player_ids[0]][key]['label'],
                    'values': {pid: rows[pid][key] for pid in request.player_ids}} for key in keys],
                'same_role': len({p['subject']['role'] for p in profiles}) == 1,
                'rate_comparison_available': all(p['totals']['minutes'] >= 180 for p in profiles),
                'minimum_minutes_for_rate_comparison': 180,
                'evidence': {p['subject']['player_id']: p['evidence'] for p in profiles}}

    def home(self, request):
        envelope = self.envelope(request); p = request.preferences; cutoff = request.cutoff()
        followed = []
        fixed = request.model_copy(update={'as_of': cutoff})
        for pid in p.favorite_player_ids:
            view = self.profile(pid, 'player', fixed)
            followed.append({'player': view['profile']['subject'], 'tiles': view['presentation']['tiles'],
                             'cards': view['presentation']['cards'], 'questions': view['presentation']['questions'],
                             'evidence_id': view['profile']['evidence']['baseline_id']})
        clubs = []
        for cid in p.favorite_club_ids:
            view = self.profile(cid, 'club', fixed)
            clubs.append({'club': view['profile']['subject'], 'record': view['profile']['record'],
                          'tiles': view['presentation']['tiles'], 'evidence_id': view['profile']['evidence']['baseline_id']})
        matches = []
        for row in self.store.rows(featured=True):
            at = self.career.historical_cutoff(row, cutoff)
            if at is False or row['kickoff'] >= cutoff or request.season and row['season'] != request.season:
                continue
            summary = self.store.summary(row['id'], at, completed=True)
            relevance = self.relevance([pid for pid, s in summary['players'].items() if s['appearances']], [row['home'], row['away']], p)
            matches.append({**match_card(row, summary), 'relevance': relevance,
                'action': action('match', row['id'], words(p, 'Open match', '查看比赛'))})
        matches.sort(key=lambda m: (-m['relevance']['score'], -datetime.fromisoformat(m['kickoff'].replace('Z', '+00:00')).timestamp(), m['match_id']))
        from .highlights import highlight_cards
        highlights = highlight_cards(self, p, cutoff, request.season)
        highlights.sort(key=lambda h: (-h['relevance']['score'], h['sort_order'], h['highlight_id']))
        return {**envelope, 'as_of': cutoff, 'season': request.season,
                'theme': self.store.clubs[p.primary_club_id].model_dump() if p.primary_club_id else None,
                'following': {'players': followed, 'clubs': clubs},
                'highlights': highlights[:request.limit], 'highlight_total': len(highlights),
                'matches': matches, 'library_total': len(self.store.rows(featured=True)),
                'onboarding': {'needs_favorites': not p.favorite_player_ids and not p.favorite_club_ids,
                    'title': words(p, 'Follow your football', '关注你的足球世界'),
                    'text': words(p, 'Choose players and clubs to bring their moments closer.', '选择球员和俱乐部，更快找到他们的精彩时刻。')}}

    def buildup_card(self, fixture, events, request, source_id):
        """One short-lived, deterministic insight, never an automatic model call.

        Lifetime follows the goal occurrence, so delayed corrections cannot
        resurrect stale cards. Snapshot replacement withdraws removed goals.
        """
        p = request.preferences
        cutoff = (request.cutoff.period, request.cutoff.elapsed_ms)
        goals = [e for e in events if e.kind == 'shot' and e.outcome == 'goal'
                 and e.goal_for == e.club_id and e.period == cutoff[0]
                 and e.elapsed_ms <= cutoff[1] < min(e.elapsed_ms + 30000, fixture.period_lengths_ms[e.period - 1])]
        if not goals:
            return None
        goal = goals[-1]
        result = goal_buildup(fixture, events, event_id=goal.event_id, cutoff=cutoff,
                              expected_revision=goal.revision)
        if result['status'] != 'available':
            return None
        metrics = result['metrics']
        situation = 'penalty' if goal.penalty else goal.situation
        direct = situation in ('free_kick', 'penalty')
        if not direct and not metrics['completed_passes'] and not metrics['carry_count'] and metrics['regain_to_shot_seconds'] is None:
            return None
        contributions = {c['player_id']: c for c in result['contributions']}
        if p.focus_player_id in contributions:
            favorite = p.focus_player_id if p.focus_player_id != goal.player_id else None
        else:
            favorite = next((pid for pid in p.favorite_player_ids
                             if pid in contributions and pid != goal.player_id), None)
        selected = favorite or goal.player_id
        scorer = self.store.players[goal.player_id].name
        scope = {'kind': 'goal_buildup', 'match_id': fixture.match_id,
                 'event_id': goal.event_id, 'event_revision': goal.revision,
                 'window': result['window'], 'cutoff': request.cutoff.model_dump()}
        audience = fingerprint(p.model_dump())
        refs = result['evidence']
        evidence_id = fingerprint({'rule_version': result['rule_version'], 'events': refs})
        facts = []
        title = words(p, 'How the goal came together', '进球是如何形成的')
        if direct:
            text = words(p, f'{scorer} scored from a {"penalty" if situation == "penalty" else "free kick"}.',
                         f'{scorer}通过{"点球" if situation == "penalty" else "任意球"}破门。')
            facts.append(fact('player', goal.player_id, 'goal_situation', situation, scope, evidence_id, 'category'))
        elif favorite and contributions[favorite]['completed_passes']:
            player = self.store.players[favorite].name
            passes = contributions[favorite]['completed_passes']
            text = words(p, f'{player} completed {passes} {"pass" if passes == 1 else "passes"} in the buildup to {scorer}’s goal.',
                         f'在{scorer}进球前的组织中，{player}完成了{passes}次传球。')
            title = words(p, 'Your player in the buildup', '你关注的球员参与了进攻')
            facts.append(fact('player', favorite, 'buildup_completed_passes', passes, scope, evidence_id))
        elif metrics['regain_to_shot_seconds'] is not None:
            seconds = metrics['regain_to_shot_seconds']
            displayed = round(seconds, 1)
            approximate = displayed != seconds
            text = words(p, f'{scorer} took the scoring shot {"about " if approximate else ""}{displayed:g} seconds after the ball was won back.',
                         f'夺回球权{"约" if approximate else ""}{displayed:g}秒后，{scorer}射门得分。')
            facts.append(fact('club', goal.club_id, 'regain_to_shot_seconds', seconds, scope, evidence_id, 'seconds'))
        elif metrics['completed_passes']:
            passes = metrics['completed_passes']
            text = words(p, f'The buildup to {scorer}’s goal includes {passes} completed {"pass" if passes == 1 else "passes"}.',
                         f'{scorer}进球前的组织包含{passes}次成功传球。')
            facts.append(fact('club', goal.club_id, 'buildup_completed_passes', passes, scope, evidence_id))
        else:
            carrier = next(c for c in result['contributions'] if c['carries'])
            player = self.store.players[carrier['player_id']].name
            text = words(p, f'{player} carried the ball in the buildup to {scorer}’s goal.',
                         f'在{scorer}进球前的组织中，{player}带球推进。')
            facts.append(fact('player', carrier['player_id'], 'buildup_carry_segments', carrier['carries'], scope, evidence_id, 'segments'))
        if p.depth == 'analyst' and not direct:
            duration = metrics['observed_duration_seconds']
            participants = metrics['participant_count']
            text += words(p, f' The recorded sequence spans {duration:g} seconds and involves {participants} players.',
                          f'这段已记录的进攻历时{duration:g}秒，共有{participants}名球员参与。')
            facts += [fact('club', goal.club_id, 'observed_buildup_seconds', duration, scope, evidence_id, 'seconds'),
                      fact('club', goal.club_id, 'buildup_participants', participants, scope, evidence_id, 'players')]
        # A goal card is not itself a reviewed replay binding. Keep navigation
        # to the profile and grounded assistant; their replay resolver separately
        # checks the authored source. This also preserves historical snapshots
        # when a correction exists but is not yet available at this playhead.
        navigation = action('profile', selected, words(p, 'Open player', '查看球员'), subject_kind='player')
        evidence = {'match_id': fixture.match_id, 'event_id': goal.event_id, 'event_revision': goal.revision,
                    'event_digest': source_id, 'evidence_fingerprint': evidence_id, 'events': refs,
                    'rule_version': result['rule_version'], 'source_kind': fixture.source_kind,
                    'occurred_at': {'period': goal.period, 'elapsed_ms': goal.elapsed_ms},
                    'available_at': {'period': goal.available_period, 'elapsed_ms': goal.available_ms},
                    'expires_at': {'period': goal.period, 'elapsed_ms': min(goal.elapsed_ms + 30000, fixture.period_lengths_ms[goal.period - 1])},
                    'audience_id': audience, 'coverage': result['coverage']}
        relevance = self.relevance(list(contributions), [goal.club_id], p)
        output = card(f'{fixture.match_id}:{goal.event_id}:buildup', 'goal_buildup', title, text,
                      facts, evidence, navigation, 170 + relevance['score'])
        output['replay_available'] = False
        output['replay_status'] = 'not_attached'
        output['ask_footie'] = {'match_id': fixture.match_id, 'event_id': goal.event_id,
            'event_revision': goal.revision, 'cutoff': request.cutoff.model_dump(),
            'question': words(p, 'What made that goal happen?', '这粒进球是如何形成的？'),
            'label': words(p, f'{scorer}’s goal', f'{scorer}的进球')}
        return output

    def match(self, mid, request):
        envelope = self.envelope(request); p = request.preferences
        row = self.store.row(mid); fixture = Fixture.model_validate_json(row['fixture'])
        cutoff = (request.cutoff.period, request.cutoff.elapsed_ms)
        if cutoff[1] > fixture.period_lengths_ms[cutoff[0] - 1] + 60000:
            raise PreferenceError('Playback cutoff outside match')
        live = self.career.live(mid, *cutoff, sequence=request.through_sequence)
        events = select_events([e for e in self.store.events(mid) if request.through_sequence is None or e.delivery_sequence <= request.through_sequence], cutoff)
        source_id = digest(events)
        evidence = {'match_id': mid, 'event_digest': source_id, 'baseline_id': live['baseline']['id'],
                    'cutoff': request.cutoff.model_dump(), 'rule_version': live['rule_version']}
        scope = {'kind': 'match', 'match_id': mid, 'cutoff': request.cutoff.model_dump()}
        roster = {a.player_id: a for a in fixture.appearances}
        match_clock = min(sum(fixture.period_lengths_ms), cutoff[1] + (fixture.period_lengths_ms[0] if cutoff[0] == 2 else 0))
        # At the final whistle retain the eleven who finished the match.
        active_clock = min(match_clock, sum(fixture.period_lengths_ms) - 1)
        active = {pid for pid, a in roster.items() if a.start_ms <= active_clock < a.end_ms}
        eligible_favorites = sorted(set(p.favorite_player_ids) & roster.keys(), key=lambda pid: (pid not in active, pid))
        focus = p.focus_player_id or (eligible_favorites[0] if eligible_favorites else None)
        focus_status = 'not_selected' if focus is None else 'not_in_match' if focus not in roster else 'on_pitch' if focus in active else 'substituted' if roster[focus].end_ms <= active_clock else 'not_yet_on'
        lens = {'player_id': focus, 'status': focus_status, 'player': self.player(focus) if focus else None,
                'active_player_ids': sorted(active), 'favorite_active_player_ids': sorted(active & set(p.favorite_player_ids)),
                'involvements': [], 'match_stats': None}
        if focus in roster:
            related = [e for e in events if focus in (e.player_id, e.recipient_id, e.opponent_id, e.goalkeeper_id)]
            lens['involvements'] = [{'event_id': e.event_id, 'revision': e.revision, 'kind': e.kind,
                'period': e.period, 'elapsed_ms': e.elapsed_ms,
                'role': 'actor' if focus == e.player_id else 'recipient' if focus == e.recipient_id else 'opponent' if focus == e.opponent_id else 'goalkeeper'} for e in related[-20:]]
            lens['match_stats'] = live['players'][focus]['match']
        preferred_club = p.primary_club_id if p.primary_club_id in live['score'] else fixture.home_id
        opponent = fixture.away_id if preferred_club == fixture.home_id else fixture.home_id
        name = self.store.clubs[preferred_club].name; other = self.store.clubs[opponent].name
        a, b = live['score'][preferred_club], live['score'][opponent]
        text = words(p, f'{name} and {other} are level at {a}–{b}.' if a == b else
                     f'{name} {"lead" if a > b else "trail"} {other} {a}–{b}.',
                     f'{name}与{other}目前{a}比{b}战平。' if a == b else f'{name}目前{a}比{b}{"领先" if a > b else "落后于"}{other}。')
        candidates = [card(f'{mid}:score', 'score', words(p, 'The match so far', '比赛进展'), text,
            [fact('club', cid, 'goals', value, scope, source_id) for cid, value in live['score'].items()], evidence,
            action('match', mid, words(p, 'Follow the match', '关注比赛')), 100)]
        for m in live['milestones']:
            pid = m['player_id']; count = m['career_goals']; player_name = m['player_name']
            relevance = self.relevance([pid], [self.store.players[pid].club_id], p)
            milestone_scope = {'kind': 'career_at_event', 'match_id': mid, 'event_id': m['event_id'], 'cutoff': m['available_at']}
            milestone_evidence_id = fingerprint({'baseline': m['baseline_id'], 'event_id': m['event_id'], 'revision': m['event_revision']})
            facts = [fact('player', pid, 'goals', count, milestone_scope, milestone_evidence_id),
                     fact('player', pid, 'goals_before_milestone', m['previous_goals'], milestone_scope, milestone_evidence_id)]
            text = words(p, f'{player_name} reaches {count} career goals.', f'{player_name}达成生涯{count}球。')
            if p.depth == 'analyst':
                text += words(p, f' This goal takes the total from {m["previous_goals"]} to {count}.', f'这粒进球将总数从{m["previous_goals"]}提升至{count}。')
            candidates.append(card(m['insight_id'], 'career_goal_milestone', words(p, 'A career landmark', '生涯里程碑'), text,
                facts, {**evidence, 'milestone_evidence_id': milestone_evidence_id, 'event_id': m['event_id'], 'event_revision': m['event_revision'], 'source_reference': m['source_reference']},
                action('moment', mid, words(p, 'Watch the goal', '观看进球'), event_id=m['event_id']), 200 + relevance['score']))
        if focus in roster:
            stats = live['players'][focus]['match']; player_name = self.store.players[focus].name
            coverage = {'assists_unavailable_matches': int(fixture.assist_basis == 'unavailable'),
                        'key_passes_unavailable_matches': int(not fixture.shot_assists_complete),
                        'saves_unavailable_matches': int(fixture.source_kind == 'adapted_archive'),
                        'recoveries_unavailable_matches': int(fixture.source_kind == 'adapted_archive')}
            coverage['metrics']=metric_coverage([(fixture.model_dump(),stats)])
            lens['tiles'] = metric_tiles(stats, covered_rates(stats,coverage['metrics']), coverage, p, self.store.players[focus].role)
            completed, attempted = stats['passes_completed'], stats['passes'] - stats['passes_unknown']
            text = words(p, f'{player_name} has completed {completed} of {attempted} passes with known outcomes.',
                         f'{player_name}在结果已记录的{attempted}次传球中成功{completed}次。')
            if not stats['passes_unknown']:
                text = words(p, f'{player_name} has completed {completed} of {attempted} passes.', f'{player_name}{attempted}次传球成功{completed}次。')
            facts = [fact('player', focus, 'passes_completed', completed, scope, source_id),
                     fact('player', focus, 'passes_with_known_outcomes', attempted, scope, source_id)]
            if p.depth == 'analyst':
                accuracy = rates(stats)['pass_accuracy_pct']
                if accuracy is not None:
                    text += words(p, f' Completion: {accuracy:.1f}%.', f'成功率为{accuracy:.1f}%。')
                    facts.append(fact('player', focus, 'pass_accuracy_pct', accuracy, scope, source_id, 'percent'))
            if stats['minutes'] > 0:
                candidates.append(card(f'{mid}:{focus}:passing', 'player_passing', words(p, 'Your player', '你关注的球员'), text,
                    facts, evidence, action('profile', focus, words(p, 'Open player', '查看球员'), subject_kind='player'),
                    130 + (30 if p.metric_focus == 'passing' else 0)))
            if stats['key_passes'] and fixture.source_kind != 'adapted_archive':
                candidates.append(card(f'{mid}:{focus}:creating', 'player_creating', words(p, 'Making chances', '创造机会'),
                    words(p, f'{player_name} has set up {stats["key_passes"]} shots.', f'{player_name}已创造{stats["key_passes"]}次射门机会。'),
                    [fact('player', focus, 'key_passes', stats['key_passes'], scope, source_id)], evidence,
                    action('profile', focus, words(p, 'Explore player', '查看球员'), subject_kind='player'),
                    120 + (60 if p.metric_focus == 'creating' else 0)))
            if stats['duels'] - stats['duels_unknown'] > 0:
                known = stats['duels'] - stats['duels_unknown']
                candidates.append(card(f'{mid}:{focus}:defending', 'player_duels', words(p, 'Winning the ball', '争夺球权'),
                    words(p, f'{player_name} has won {stats["duels_won"]} of {known} recorded challenges.',
                          f'{player_name}在{known}次结果已记录的争抢中成功{stats["duels_won"]}次。'),
                    [fact('player', focus, 'duels_won', stats['duels_won'], scope, source_id),
                     fact('player', focus, 'duels_with_known_outcomes', known, scope, source_id)], evidence,
                    action('profile', focus, words(p, 'Explore player', '查看球员'), subject_kind='player'),
                    120 + (60 if p.metric_focus == 'defending' else 0)))
        for cid, stats in live['clubs'].items():
            if not stats['shots']:
                continue
            name = self.store.clubs[cid].name
            candidates.append(card(f'{mid}:{cid}:shots', 'club_shots', words(p, 'In front of goal', '门前表现'),
                words(p, f'{name} have put {stats["shots_on_target"]} of {stats["shots"]} shots on target.',
                      f'{name}{stats["shots"]}次射门中有{stats["shots_on_target"]}次射正。'),
                [fact('club', cid, metric, stats[metric], scope, source_id) for metric in ('shots', 'shots_on_target')], evidence,
                action('match', mid, words(p, 'Explore the chances', '查看射门机会')), 60 + self.relevance([], [cid], p)['score'] + (30 if p.metric_focus == 'scoring' else 0)))
        buildup = self.buildup_card(fixture, events, request, source_id) if request.card_budget else None
        if buildup:
            candidates.append(buildup)
        # Explicit viewing intent must survive a match with several milestones;
        # otherwise they can consume the entire card budget and hide the lens.
        focus_kinds={'passing':{'player_passing'},'creating':{'player_creating'},
                     'defending':{'player_duels'},'scoring':{'career_goal_milestone','club_shots'}}.get(p.metric_focus,set())
        candidates.sort(key=lambda c: (c['kind'] not in focus_kinds, -c['priority'], c['id']))
        chosen = candidates[:request.card_budget]
        questions = []
        for c in chosen:
            if c['kind'] == 'career_goal_milestone':
                questions.append({'id': c['id'] + ':why', 'text': words(p, 'Why does this goal matter?', '这粒进球为何重要？'),
                    'intent': 'milestone_context', 'context': {'match_id': mid, 'cutoff': request.cutoff.model_dump(),
                        'player_id': c['facts'][0]['subject_id'], 'insight_id': c['id']},
                    'answer_mode': 'data_view', 'action': c['action']})
        return {**envelope, 'match_id': mid, 'cutoff': request.cutoff.model_dump(),
                'facts': live, 'evidence': evidence, 'focus': lens, 'cards': chosen, 'questions': questions,
                'view_id': fingerprint({'preferences': envelope['preference_id'], 'evidence': evidence,
                    'through_sequence': request.through_sequence, 'card_budget': request.card_budget})}
