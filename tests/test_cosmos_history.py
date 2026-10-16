"""Contract tests with a transactional service double; live checks are separate."""

from copy import deepcopy
from pathlib import Path

import pytest
from azure.cosmos.exceptions import CosmosBatchOperationError, CosmosHttpResponseError

from counterpress.api.main import create_app
from counterpress.api.snapshots import SCENARIOS, SnapshotService
from counterpress.cosmos_history import CosmosHistoryStore, MAX_ATTEMPTS
from counterpress.history import HistoryStorageError
from test_history import updates
from test_snapshot_api import request

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class AtomicContainer:
    """Models ETag preconditions and all-or-nothing batches, not Azure availability."""
    def __init__(self):
        self.items = {}
        self.reads = []
        self.batches = 0
        self.before_batch = None
        self.after_head = None
        self.failure = None

    def read_item(self, *, item, partition_key):
        self.reads.append((partition_key, item))
        if self.failure:
            raise CosmosHttpResponseError(status_code=self.failure, message="private endpoint canary")
        if (partition_key, item) not in self.items:
            raise CosmosHttpResponseError(status_code=404)
        result = deepcopy(self.items[partition_key, item])
        if item == "head" and self.after_head:
            hook, self.after_head = self.after_head, None
            hook()
        return result

    def execute_item_batch(self, *, batch_operations, partition_key):
        self.batches += 1
        if self.before_batch:
            hook, self.before_batch = self.before_batch, None
            hook()
        candidate = deepcopy(self.items)
        for index, (operation, args, options) in enumerate(batch_operations):
            body = args[0] if operation == "create" else args[1]
            key = (partition_key, body["id"])
            assert body["scenario_id"] == partition_key
            status = None
            if operation == "create" and key in candidate:
                status = 409
            if operation == "replace" and key not in candidate:
                status = 404
            if options.get("if_match_etag") and candidate[key]["_etag"] != options["if_match_etag"]:
                status = 412
            if status:
                raise CosmosBatchOperationError(error_index=index, status_code=status, headers={})
            candidate[key] = deepcopy(body) | {"_etag": str(self.batches)}
        self.items = candidate
        return [{"statusCode": 200} for _ in batch_operations]


def service(container, fixtures=FIXTURES):
    return SnapshotService(fixtures, CosmosHistoryStore(container))


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_all_scenario_histories_and_evidence_survive_a_fresh_store_without_fixtures(tmp_path, scenario):
    container = AtomicContainer()
    original = service(container).snapshot(scenario, 780000)
    restored = service(container, tmp_path / "no-fixtures").snapshot(scenario, 780000)
    assert restored == original
    assert container.batches == 1


def test_corrections_withdrawals_and_duplicate_replay_survive_restart(tmp_path):
    container = AtomicContainer()
    first = service(container)
    before = first.snapshot("increase", 780000)
    committed = first.ingest("increase", updates())
    assert [c.operation for c in committed.changes] == ["create", "update", "withdraw", "create"]
    restarted = service(container, tmp_path / "no-fixtures")
    for at, count, revision in [(780000, 4, 1), (785000, 3, 2), (790000, None, 3), (795000, 2, 4)]:
        snapshot = restarted.snapshot("increase", at)
        assert snapshot.lifecycle.revision == revision
        assert (snapshot.insight.facts.current_count if snapshot.insight else None) == count
    assert restarted.evidence("increase", 1, 795000) == before.evidence
    writes = container.batches
    assert restarted.ingest("increase", updates()) == committed
    assert container.batches == writes


def test_conflicting_seed_and_correction_writers_rebuild_from_winner():
    container = AtomicContainer()
    first, second = service(container), service(container)
    container.before_batch = lambda: second.history("increase")
    first.history("increase")
    container.before_batch = lambda: second.ingest("increase", updates())
    result = first.ingest("increase", updates())
    assert len(result.records) == 93
    assert len(result.changes) == 4
    assert service(container).history("increase") == result


def test_concurrent_distinct_changes_are_not_lost():
    container = AtomicContainer()
    store = service(container).store
    original = service(container).history("increase")
    other = CosmosHistoryStore(container)
    def increment(previous):
        return previous.model_copy(update={"episode_rules_version": previous.episode_rules_version + 1})
    container.before_batch = lambda: other.transact("increase", increment)
    result = store.transact("increase", increment)
    assert result.episode_rules_version == original.episode_rules_version + 2


def test_read_retries_a_commit_between_head_and_body():
    container = AtomicContainer()
    writer = service(container)
    writer.history("increase")
    container.after_head = lambda: writer.ingest("increase", updates())
    result = CosmosHistoryStore(container).read("increase")
    assert len(result.records) == 93 and result.changes[-1].revision == 4


def test_polling_reads_only_small_head_until_another_writer_commits():
    container = AtomicContainer()
    first = service(container)
    first.history("increase")
    container.reads.clear()
    for _ in range(5):
        first.snapshot("increase", 780000)
    assert container.reads == [("increase", "head")] * 5
    service(container).ingest("increase", updates())
    container.reads.clear()
    assert first.snapshot("increase", 795000).insight.facts.current_count == 2
    assert container.reads == [("increase", "head"), ("increase", "history")]


@pytest.mark.parametrize("mutation", ["rewrite", "duplicate", "oversize"])
def test_invalid_or_oversized_history_leaves_both_items_unchanged(monkeypatch, mutation):
    container = AtomicContainer()
    store = service(container).store
    before = service(container).history("increase")
    persisted = deepcopy(container.items)
    if mutation == "rewrite":
        build = lambda old: old.model_copy(update={"records": old.records[:-1]})
    elif mutation == "duplicate":
        build = lambda old: old.model_copy(update={"records": (*old.records, old.records[0])})
    else:
        monkeypatch.setattr("counterpress.cosmos_history.MAX_HISTORY_BYTES", 10)
        build = lambda old: old.model_copy(update={"episode_rules_version": old.episode_rules_version + 1})
    with pytest.raises(ValueError):
        store.transact("increase", build)
    assert container.items == persisted
    assert store.read("increase") == before


def test_batch_failure_rolls_back_head_when_history_create_conflicts():
    container = AtomicContainer()
    original = service(AtomicContainer()).history("increase")
    container.items["increase", "history"] = {"id": "history", "scenario_id": "increase", "_etag": "old"}
    before = deepcopy(container.items)
    with pytest.raises(HistoryStorageError, match="conflicted"):
        CosmosHistoryStore(container).transact("increase", lambda old: original)
    assert container.items == before and container.batches == MAX_ATTEMPTS


@pytest.mark.parametrize("status", [403, 429, 503])
def test_cloud_failure_is_sanitized_and_does_not_fall_back_to_fixtures(status):
    container = AtomicContainer()
    store = CosmosHistoryStore(container)
    service(container).history("increase")
    store.read("increase")  # A cached history must not hide a failed version read.
    container.failure = status
    app = create_app(store=store)
    assert request(app, "/health").status_code == 200
    for path in ("/ready", "/api/scenarios", "/api/scenarios/increase/snapshot?at_ms=780000"):
        response = request(app, path)
        assert response.status_code == 503
        assert "private endpoint canary" not in response.text


def test_storage_configuration_fails_closed(monkeypatch):
    from counterpress.storage import configured_store
    monkeypatch.setenv("COUNTERPRESS_STORAGE", "cosmos")
    monkeypatch.delenv("COUNTERPRESS_COSMOS_ENDPOINT", raising=False)
    with pytest.raises(ValueError, match="HTTPS"):
        configured_store(":memory:")
    monkeypatch.setenv("COUNTERPRESS_STORAGE", "typo")
    with pytest.raises(ValueError, match="sqlite or cosmos"):
        configured_store(":memory:")


def test_live_check_logic_requires_persisted_state_in_verify_phase():
    from counterpress.cosmos_check import check
    container = AtomicContainer()
    assert check("seed", "offline-test", CosmosHistoryStore(container), FIXTURES).startswith("PASS:")
    assert check("verify", "offline-test", CosmosHistoryStore(container), Path("/missing")).startswith("PASS:")
    with pytest.raises(FileNotFoundError):
        check("verify", "wrong-scope", CosmosHistoryStore(container), Path("/missing"))
