"""Deterministic bilingual pressure presentation with source-linked involvement."""

from typing import Literal

from counterpress.audience import NarrativeVariant, ViewingPreferences
from counterpress.domain.models import Contract, EventReference
from counterpress.pressure_publications import PressureChange
from counterpress.replay import display_time


class PressureView(Contract):
    preferences: ViewingPreferences
    state: Literal["ready", "collecting", "no_eligible", "no_contribution", "budget_hidden"]
    message: str
    publication: PressureChange | None = None
    variant: NarrativeVariant | None = None
    highlighted_events: tuple[EventReference, ...] = ()
    priority: int = 0


def pressure_view(history, changes, prefs, collecting):
    zh = prefs.language == "zh-Hans"
    candidates = []
    for change in changes:
        if change.operation == "withdraw":
            continue
        evidence = change.evidence
        included = set(evidence.baseline.included + evidence.current.included)
        sources = {ref for episode in evidence.episodes if episode.episode_id in included
                   and (change.metric != "pressured_escape" or episode.pressure_events)
                   for ref in episode.source_events}
        records = [event for event in evidence.records if EventReference(event_id=event.event_id, revision=event.revision) in sources]
        # Involvement is an observed actor, not inferred credit for an episode's result.
        selected = [event for event in records if not prefs.player_id or
                    (event.actor.player_id == prefs.player_id and event.actor.team_id == evidence.subject_team_id)]
        if not selected:
            continue
        priority = 10 + (20 if prefs.club_id == evidence.subject_team_id else 0) + (30 if prefs.player_id else 0)
        priority += 10 if prefs.metric_focus == change.metric else -5 if prefs.metric_focus not in ("balanced", change.metric) else 0
        candidates.append((priority, change.insight_id, change, selected))
    common = dict(preferences=prefs)
    if not candidates:
        state = "collecting" if collecting else "no_contribution" if prefs.player_id and any(c.operation != "withdraw" for c in changes) else "no_eligible"
        message = ("等待两个比较时段结束。" if zh else "Waiting for both comparison windows to finish.") if collecting else (
            "没有符合当前偏好的控球过程洞察。" if zh else "No eligible possession-episode insight for these preferences.")
        return PressureView(**common, state=state, message=message)
    priority, _, change, selected = sorted(candidates, key=lambda item: (-item[0], item[2].metric, item[1]))[0]
    if prefs.card_budget == 0:
        return PressureView(**common, state="budget_hidden", message="卡片显示数量设为 0。" if zh else "Card budget is 0.")
    decision, evidence = change.decision, change.evidence
    name = next(team.name for team in history.fixture.teams if team.team_id == evidence.subject_team_id)
    metric = ("压迫暴露比例（争抢代理指标）" if zh else "Pressure exposure (duel proxy)") if change.metric == "pressure_exposure" else (
        "受压后的控球摆脱比例" if zh else "Escape under pressure")
    if change.metric == "possession_without_progression":
        metric = "未形成推进的持续控球比例" if zh else "Possession without progression"
    direction = ("上升" if decision.direction == "increase" else "下降") if zh else decision.direction + "d"
    before = f"{decision.baseline_numerator}/{decision.baseline_denominator}"
    after = f"{decision.current_numerator}/{decision.current_denominator}"
    bw, cw = evidence.baseline.window, evidence.current.window
    baseline = f"({display_time(bw.start)},{display_time(bw.end)}]"
    current = f"({display_time(cw.start)},{display_time(cw.end)}]"
    explanation = f"{name}: {baseline} {before} → {current} {after}."
    qualification = ("防守三区争抢仅作为压迫代理指标；比例变化不能证明战术因果关系。" if zh else
                     "Defensive-third duels are a pressure proxy. Rate changes do not establish tactical causality.")
    if change.metric == "possession_without_progression":
        qualification = ("持续控球期间，观测到的最远向前推进不足 15 米；不代表传球质量或战术价值。" if zh else
                         "Sustained possessions with less than 15 m of observed forward gain. This does not measure passing quality or tactical value.")
    if prefs.depth == "analyst":
        explanation += " 仅统计时段内开始并结束的完整过程。" if zh else " Only episodes beginning and resolving inside each window are counted."
    variant = NarrativeVariant(insight_id=change.insight_id, revision=change.revision, language=prefs.language,
        depth=prefs.depth, club_id=prefs.club_id, player_id=prefs.player_id,
        title=f"{metric} {direction}", explanation=explanation, qualification=qualification, subject_name=name)
    return PressureView(**common, state="ready", publication=change, variant=variant, priority=priority,
        highlighted_events=tuple(EventReference(event_id=event.event_id, revision=event.revision) for event in selected),
        message=("所选球员显示实际事件参与，不代表个人功劳。球队比例不变。" if zh else
                 "Player selection shows recorded involvement, not individual credit. Team rates stay unchanged.") if prefs.player_id else
                ("所有比例均链接至完整过程和事件。" if zh else "Every rate links to complete episodes and source events."))
