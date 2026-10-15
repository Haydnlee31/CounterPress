from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from counterpress.api.main import create_app
from counterpress.api.snapshots import SnapshotService
from counterpress.audience import AudienceService, ViewingPreferences
from test_history import updates

ROOT = Path(__file__).resolve().parents[1]


def view(service, at=780000, scenario="increase", **preferences):
    return service.snapshot(scenario, at, preferences=ViewingPreferences(**preferences))


def test_modes_and_languages_keep_authoritative_names_values_windows_and_uncertainty():
    service = SnapshotService(ROOT / "fixtures")
    baseline = view(service)
    for language in ("en", "zh-Hans"):
        for depth in ("analyst", "casual"):
            snapshot = view(service, language=language, depth=depth)
            assert snapshot.insight == baseline.insight and snapshot.evidence == baseline.evidence
            narrative = snapshot.audience.variant
            assert narrative.subject_name == "Eastbridge"
            assert all(value in narrative.explanation for value in ("Eastbridge", "1", "4", "48:00–53:00", "53:00–58:00"))
            assert ("cannot" in narrative.qualification or "does not" in narrative.qualification or "不能" in narrative.qualification)
            assert bool(snapshot.audience.sequence) == (depth == "analyst")
            assert ("x ≥ 70 m" in narrative.explanation) == (depth == "analyst")


def test_selected_player_uses_actual_qualifying_actor_and_keeps_team_totals():
    service = SnapshotService(ROOT / "fixtures")
    snapshot = view(service, player_id="eb09")
    assert [ref.event_id for ref in snapshot.audience.highlighted_events] == ["p064"]
    assert snapshot.audience.selected_event_count == 1 and snapshot.audience.supporting_event_count == 5
    assert [event.event_id for event in snapshot.audience.sequence] == ["p063", "p064", "p065"]
    assert snapshot.insight.facts.baseline_count == 1 and snapshot.insight.facts.current_count == 4
    empty = view(service, player_id="eb04")
    assert empty.audience.state == "no_contribution" and empty.audience.variant is None
    assert empty.audience.highlighted_events == empty.audience.sequence == ()
    # eb04 has other recorded recoveries, but none supports this high-recovery comparison.
    assert any(event.actor.player_id == "eb04" for event in service.history("increase").records)


def test_preferences_rank_only_eligible_stories_and_respect_card_budget():
    service = SnapshotService(ROOT / "fixtures")
    balanced = view(service).audience
    assert view(service, club_id="eastbridge").audience.priority > balanced.priority
    assert view(service, metric_focus="high_recoveries").audience.priority > balanced.priority
    assert view(service, metric_focus="passing").audience.priority < balanced.priority
    assert view(service, club_id="northport").audience.variant is not None
    assert view(service, card_budget=0).audience.state == "budget_hidden"
    assert view(service, scenario="control", club_id="eastbridge", metric_focus="high_recoveries").audience.variant is None
    assert view(service, at=540000, player_id="eb09").audience.state == "collecting"


def test_cache_is_shared_by_variant_not_viewer_or_playhead_and_is_bounded():
    service = SnapshotService(ROOT / "fixtures")
    service.audiences = AudienceService(capacity=2)
    first = view(service).audience.variant
    second = service.snapshot("increase", 780000, scope_id="other-viewer").audience.variant
    assert first is second and len(service.audiences.cache) == 1
    different = view(service, depth="casual").audience.variant
    assert different is not first
    view(service, language="zh-Hans")
    assert len(service.audiences.cache) == 2
    assert first not in service.audiences.cache.values()


def test_correction_invalidates_variants_and_old_playback_cannot_resurrect_them():
    service = SnapshotService(ROOT / "fixtures")
    original = view(service, player_id="eb09").audience.variant
    service.ingest("increase", updates()[:1])
    assert not service.audiences.cache
    changed = view(service, at=785000, player_id="eb09")
    assert changed.audience.variant.revision == 2
    assert changed.insight.facts.current_count == 3
    assert original not in service.audiences.cache.values()
    historical = view(service, player_id="eb09")
    assert historical.insight.facts.current_count == 4
    assert historical.audience.variant.revision == 1
    assert all(key[1] == 2 for key in service.audiences.cache)
    service.ingest("increase", updates()[1:3])
    withdrawn = view(service, at=790000, player_id="eb09")
    assert withdrawn.audience.state == "no_increase" and not service.audiences.cache
    # Historical facts are still available, but never re-enter the current cache.
    view(service, player_id="eb09")
    assert not service.audiences.cache


@pytest.mark.parametrize("query", ["language=zh", "depth=coach", "card_budget=2", "card_budget=-1",
    "club_id=unknown", "player_id=unknown", "metric_focus=pressure"])
def test_invalid_preferences_are_rejected_by_api(query):
    client = TestClient(create_app())
    response = client.get(f"/api/scenarios/increase/snapshot?at_ms=780000&{query}")
    assert response.status_code == 422


def test_api_scopes_remain_separate_and_responses_are_not_http_cached():
    client = TestClient(create_app())
    first = client.get("/api/scenarios/increase/snapshot?at_ms=780000&scope_id=viewer-one&language=zh-Hans&depth=casual&player_id=eb09")
    other = client.get("/api/scenarios/increase/snapshot?at_ms=540000&scope_id=viewer-two")
    assert first.status_code == other.status_code == 200
    assert first.headers["cache-control"] == "no-store"
    assert first.json()["audience"]["preferences"]["player_id"] == "eb09"
    assert other.json()["scope_id"] == "viewer-two" and other.json()["audience"]["variant"] is None
    assert other.json()["audience"]["preferences"]["language"] == "en"
    assert other.json()["evidence"] is None
