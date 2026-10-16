"""Explicit live durability check in an isolated verification partition.

Run seed, restart the hosted revision, then verify with the same scope. No keys,
resource URLs or source payloads are printed. Verification data is retained.
"""

import argparse
import os
from pathlib import Path

from pydantic import TypeAdapter

from counterpress.api.snapshots import SnapshotService
from counterpress.domain.models import Event
from counterpress.storage import configured_store


class ScopedStore:
    def __init__(self, store, scope):
        self.store, self.scope = store, scope

    def read(self, scenario_id):
        return self.store.read(f"verify-{self.scope}-{scenario_id}")

    def transact(self, scenario_id, build):
        return self.store.transact(f"verify-{self.scope}-{scenario_id}", build)


def check(phase, scope, store, fixtures):
    scoped = ScopedStore(store, scope)
    if phase == "seed":
        service = SnapshotService(fixtures, scoped)
        assert service.snapshot("increase", 780000).insight.facts.current_count == 4
        revisions = TypeAdapter(tuple[Event, ...]).validate_json(
            (fixtures / "faults/recovery_corrections.json").read_text())
        history = service.ingest("increase", revisions)
        assert len(history.records) == 93
        assert [c.operation for c in history.changes] == ["create", "update", "withdraw", "create"]
        assert service.ingest("increase", revisions) == history
    # A fresh service must restore history without ever opening fixture files.
    service = SnapshotService(Path("/nonexistent-counterpress-verification-fixtures"), scoped)
    for at, count, revision in [(780000, 4, 1), (785000, 3, 2), (790000, None, 3), (795000, 2, 4)]:
        snapshot = service.snapshot("increase", at)
        assert snapshot.lifecycle.revision == revision
        assert (snapshot.insight.facts.current_count if snapshot.insight else None) == count
    assert service.evidence("increase", 1, 795000).packet.current.value == 4
    return "PASS: 93 source records, create/update/withdraw/create, historical 4/3/none/2, immutable evidence, fixture-free recovery"


def main():
    import re
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("seed", "verify"))
    parser.add_argument("--scope", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9-]{1,40}", args.scope):
        parser.error("scope must be 1–40 lowercase letters, digits or hyphens")
    if os.environ.get("COUNTERPRESS_STORAGE") != "cosmos":
        parser.error("live verification requires explicit Cosmos storage")
    try:
        store = configured_store(":memory:")
        fixtures = Path(os.environ.get("COUNTERPRESS_FIXTURE_DIR", "fixtures"))
        print(check(args.phase, args.scope, store, fixtures), flush=True)
    except Exception:
        parser.exit(1, "FAIL: cloud durability verification did not complete; no private diagnostics printed.\n")


if __name__ == "__main__":
    main()
