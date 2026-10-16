"""Bilingual player attribution views; preferences never alter counts or eligibility."""

from typing import Literal

from counterpress.audience import NarrativeVariant, ViewingPreferences
from counterpress.contribution_publications import ContributionChange
from counterpress.domain.models import Contract, EventReference
from counterpress.replay import display_time


class ContributionView(Contract):
    preferences: ViewingPreferences
    state: Literal['ready', 'collecting', 'no_eligible', 'no_contribution', 'budget_hidden']
    message: str
    publication: ContributionChange | None = None
    variant: NarrativeVariant | None = None
    highlighted_events: tuple[EventReference, ...] = ()
    priority: int = 0


def contribution_view(history, changes, prefs, collecting):
    zh = prefs.language == 'zh-Hans'
    candidates = []
    for change in changes:
        e = change.evidence
        if change.operation == 'withdraw' or prefs.player_id and prefs.player_id != e.subject_player_id:
            continue
        priority = 10 + (20 if prefs.club_id == e.subject_team_id else 0) + (30 if prefs.player_id else 0)
        priority += 10 if prefs.metric_focus == 'player_high_recovery_share' else -5 if prefs.metric_focus != 'balanced' else 0
        candidates.append((priority, change))
    if prefs.card_budget == 0:
        return ContributionView(preferences=prefs, state='budget_hidden', message='卡片显示数量设为 0。' if zh else 'Card budget is 0.')
    if not candidates:
        state = 'collecting' if collecting else 'no_contribution' if prefs.player_id else 'no_eligible'
        message = ('等待两个比较时段结束。' if zh else 'Waiting for both comparison windows to finish.') if collecting else (
            '没有符合条件的球员夺回球权占比增长。' if zh else 'No eligible increase in player high-recovery share.')
        return ContributionView(preferences=prefs, state=state, message=message)
    priority, change = sorted(candidates, key=lambda item: (-item[0], item[1].evidence.subject_player_id, item[1].insight_id))[0]
    e = change.evidence
    name = next(team.name for team in history.fixture.teams if team.team_id == e.subject_team_id)
    before, after = e.baseline, e.current
    fraction = lambda w: f'{w.player_count}/{w.team_count}'
    window = lambda w: f'({display_time(w.window.start)},{display_time(w.window.end)}]'
    explanation = f'{e.subject_player_id} · {name}: {window(before)} {fraction(before)} → {window(after)} {fraction(after)}.'
    if prefs.depth == 'analyst':
        explanation += ' 分母为球队全部符合条件的夺回球权事件；仅归属给实际夺回球权的球员。' if zh else ' Denominators include all qualifying team recoveries; only the recovering actor receives attribution.'
    variant = NarrativeVariant(insight_id=change.insight_id, revision=change.revision, language=prefs.language,
        depth=prefs.depth, club_id=prefs.club_id, player_id=prefs.player_id,
        title='球员前场夺回球权占比增加' if zh else 'Player high-recovery share increased',
        explanation=explanation, subject_name=f'{e.subject_player_id} · {name}',
        qualification='记录事件的占比，不代表球员评分、每分钟表现或战术因果关系。' if zh else
        'A share of recorded events, not a player rating, per-minute performance or tactical causality.')
    return ContributionView(preferences=prefs, state='ready', message='争抢获胜者和接球队员不获得夺回球权归属。' if zh else
        'Duel winners and pass recipients receive no recovery attribution.', publication=change, variant=variant,
        highlighted_events=before.player_events+after.player_events, priority=priority)
