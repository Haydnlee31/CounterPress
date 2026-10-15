"""Reusable bilingual presentation variants; preferences never create football facts."""

from collections import OrderedDict
from threading import RLock
from typing import Literal

from pydantic import Field

from counterpress.domain.models import Contract, Event, EventReference, Identifier, Insight
from counterpress.history import EvidenceBundle, History
from counterpress.replay import display_time


class PreferenceError(ValueError):
    pass


class ViewingPreferences(Contract):
    language: Literal["en", "zh-Hans"] = "en"
    depth: Literal["analyst", "casual"] = "analyst"
    club_id: Identifier | None = None
    player_id: Identifier | None = None
    metric_focus: Literal["balanced", "high_recoveries", "passing", "pressure_exposure", "pressured_escape", "possession_without_progression"] = "balanced"
    card_budget: int = Field(default=1, ge=0, le=1)


class NarrativeVariant(Contract):
    insight_id: Identifier
    revision: int
    language: Literal["en", "zh-Hans"]
    depth: Literal["analyst", "casual"]
    club_id: Identifier | None
    player_id: Identifier | None
    title: str
    explanation: str
    qualification: str
    subject_name: str


class AudienceView(Contract):
    preferences: ViewingPreferences
    state: Literal["ready", "collecting", "no_increase", "no_contribution", "budget_hidden"]
    message: str
    variant: NarrativeVariant | None = None
    priority: int = 0
    highlighted_events: tuple[EventReference, ...] = ()
    sequence: tuple[Event, ...] = ()
    supporting_event_count: int = 0
    selected_event_count: int = 0


def render_variant(insight: Insight, name: str, prefs: ViewingPreferences) -> NarrativeVariant:
    facts = insight.facts
    baseline = f"{display_time(facts.baseline_window.start)}–{display_time(facts.baseline_window.end)}"
    current = f"{display_time(facts.current_window.start)}–{display_time(facts.current_window.end)}"
    before, after = facts.baseline_count, facts.current_count
    if prefs.language == "zh-Hans":
        title = "前场夺回球权次数增加"
        explanation = (f"{name} 在 {current} 前场夺回球权 {after} 次，前一时段 {baseline} 为 {before} 次。")
        if prefs.depth == "analyst":
            explanation += "统计范围为运动战中在进攻方向 x ≥ 70 m 处建立控球的事件；不含争抢和重新开球。"
        qualification = "仅比较已记录的夺回球权事件，不能据此判断压迫是否有效。"
    else:
        title = "High recoveries increased"
        explanation = f"{name}: {after} high recoveries in {current}, compared with {before} in {baseline}."
        if prefs.depth == "analyst":
            explanation += " Counted: established open-play control at x ≥ 70 m in the attacking direction; duels and restarts excluded."
        qualification = "A comparison of recorded recoveries. It does not establish whether pressure was effective."
    return NarrativeVariant(insight_id=insight.insight_id, revision=insight.revision,
        language=prefs.language, depth=prefs.depth, club_id=prefs.club_id, player_id=prefs.player_id,
        title=title, explanation=explanation, qualification=qualification, subject_name=name)


class AudienceService:
    """Bounded process-local cache without viewer IDs, playheads, or model calls."""

    def __init__(self, capacity: int = 128):
        self.capacity = capacity
        self.cache: OrderedDict[tuple, NarrativeVariant] = OrderedDict()
        self.latest: dict[str, int] = {}
        self.lock = RLock()

    def variant(self, history: History, insight: Insight, prefs: ViewingPreferences) -> NarrativeVariant:
        name = next(team.name for team in history.fixture.teams if team.team_id == insight.facts.subject_team_id)
        key = (insight.insight_id, insight.revision, prefs.language, prefs.depth, prefs.club_id, prefs.player_id)
        with self.lock:
            cacheable = self.latest.get(insight.insight_id) == insight.revision
            if cacheable and key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
            result = render_variant(insight, name, prefs)
            if cacheable:
                self.cache[key] = result
                while len(self.cache) > self.capacity:
                    self.cache.popitem(last=False)
            return result

    def invalidate(self, history: History) -> None:
        # Never let an older in-flight read roll cache invalidation back to an earlier revision.
        if history.changes:
            latest = history.changes[-1]
            with self.lock:
                known = self.latest.get(latest.insight_id, 0)
                if latest.revision > known:
                    self.latest[latest.insight_id] = latest.revision
                    for key in list(self.cache):
                        if key[0] == latest.insight_id:
                            del self.cache[key]

    def build(self, history: History, insight: Insight | None, evidence: EvidenceBundle | None,
              events: tuple[Event, ...], prefs: ViewingPreferences, collecting: bool) -> AudienceView:
        teams = {team.team_id: team for team in history.fixture.teams}
        players = {player: team.team_id for team in history.fixture.teams for player in team.player_ids}
        if prefs.club_id and prefs.club_id not in teams or prefs.player_id and prefs.player_id not in players:
            raise PreferenceError("unknown club or player preference")
        self.invalidate(history)
        zh = prefs.language == "zh-Hans"
        state = "collecting" if collecting else "no_increase"
        message = ("等待两个比较时段结束。" if zh else "Waiting for both comparison windows to finish.") if collecting else (
            "没有符合条件的增长洞察。" if zh else "No eligible increase insight.")
        if insight is None or evidence is None:
            return AudienceView(preferences=prefs, state=state, message=message)
        selected = tuple(event for event in evidence.records if not prefs.player_id or event.actor.player_id == prefs.player_id)
        common = dict(preferences=prefs, supporting_event_count=len(evidence.records), selected_event_count=len(selected))
        if not selected:
            return AudienceView(**common, state="no_contribution", message=(
                "所选球员在此洞察中没有符合条件的夺回球权事件。" if zh else
                "The selected player has no qualifying recovery contribution to this insight."))
        if prefs.card_budget == 0:
            return AudienceView(**common, state="budget_hidden", message=(
                "卡片显示数量设为 0；比赛事实仍然可用。" if zh else "Card budget is 0; match facts remain available."))
        refs = tuple(EventReference(event_id=event.event_id, revision=event.revision) for event in selected)
        identities = {(ref.event_id, ref.revision) for ref in refs}
        positions = {index for index, event in enumerate(events) if (event.event_id, event.revision) in identities}
        neighbors = {index + offset for index in positions for offset in (-1, 0, 1)}
        sequence = tuple(event for index, event in enumerate(events) if index in neighbors) if prefs.depth == "analyst" else ()
        # The snapshot service compares this priority with eligible pressure stories.
        priority = 10 + (20 if prefs.club_id == insight.facts.subject_team_id else 0)
        priority += 30 if prefs.player_id else 0
        priority += 10 if prefs.metric_focus == "high_recoveries" else -5 if prefs.metric_focus != "balanced" else 0
        return AudienceView(**common, state="ready", message=(
            "偏好对符合条件的洞察排序；比赛事实保持不变。" if zh else
            "Preferences rank eligible insights; match facts remain unchanged."),
            priority=priority, variant=self.variant(history, insight, prefs), highlighted_events=refs, sequence=sequence)
