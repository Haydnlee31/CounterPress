"""Bounded demo histories, committed atomically with an optimistic version head.

Two items share /scenario_id: a small head for polling and the complete history.
This deliberately rejects oversized histories rather than splitting a commit.
"""

import json
import re
from collections import OrderedDict
from collections.abc import Callable
from threading import RLock
from uuid import uuid4

from azure.core.exceptions import AzureError
from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosBatchOperationError

from counterpress.history import History, HistoryStorageError, validate_history_update

MAX_HISTORY_BYTES = 1_800_000  # Below Cosmos's 2 MB item AND batch limits.
MAX_ATTEMPTS = 4


class CosmosHistoryStore:
    def __init__(self, container):
        self.container = container
        self._lock = RLock()
        self._cache: OrderedDict[str, tuple[str, History]] = OrderedDict()

    @staticmethod
    def _key(scenario_id: str) -> None:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}", scenario_id):
            raise ValueError("invalid history scope")

    def _remember(self, scenario_id: str, version: str, history: History) -> None:
        self._cache[scenario_id] = (version, history)
        self._cache.move_to_end(scenario_id)
        if len(self._cache) > 16:
            self._cache.popitem(last=False)

    def _load(self, scenario_id: str) -> tuple[dict | None, History | None]:
        for _ in range(MAX_ATTEMPTS):
            try:
                head = self.container.read_item(item="head", partition_key=scenario_id)
            except CosmosHttpResponseError as error:
                if error.status_code == 404:
                    return None, None
                raise
            if (head.get("schema") != 1 or head.get("scenario_id") != scenario_id
                    or not head.get("version") or not head.get("_etag")):
                raise HistoryStorageError("History metadata is invalid.")
            cached = self._cache.get(scenario_id)
            if cached and cached[0] == head["version"]:
                return head, cached[1]
            body = self.container.read_item(item="history", partition_key=scenario_id)
            # A concurrent atomic commit may land between our two reads.
            if body.get("version") != head["version"]:
                continue
            if body.get("schema") != 1 or body.get("scenario_id") != scenario_id or "payload" not in body:
                raise HistoryStorageError("History payload is invalid.")
            history = History.model_validate_json(json.dumps(body["payload"]))
            validate_history_update(None, history)
            self._remember(scenario_id, head["version"], history)
            return head, history
        raise HistoryStorageError("History changed during reading; retry later.")

    def read(self, scenario_id: str) -> History | None:
        self._key(scenario_id)
        with self._lock:
            try:
                return self._load(scenario_id)[1]
            except (AzureError, KeyError):
                raise HistoryStorageError("Cloud history could not be read.") from None

    def transact(self, scenario_id: str, build: Callable[[History | None], History]) -> History:
        self._key(scenario_id)
        with self._lock:
            try:
                for _ in range(MAX_ATTEMPTS):
                    head, previous = self._load(scenario_id)
                    result = build(previous)
                    validate_history_update(previous, result)
                    if result == previous:
                        return result
                    version = uuid4().hex
                    common = {"scenario_id": scenario_id, "schema": 1, "version": version}
                    body = {"id": "history", **common, "payload": result.model_dump(mode="json")}
                    if len(json.dumps(body, ensure_ascii=True).encode("utf-8")) > MAX_HISTORY_BYTES:
                        raise ValueError("Demo history exceeds the safe atomic size limit; segment storage before growing this match.")
                    new_head = {"id": "head", **common}
                    if head is None:
                        operations = [("create", (new_head,), {}), ("create", (body,), {})]
                    else:
                        operations = [
                            ("replace", ("head", new_head), {"if_match_etag": head["_etag"]}),
                            ("replace", ("history", body), {}),
                        ]
                    try:
                        self.container.execute_item_batch(batch_operations=operations, partition_key=scenario_id)
                    except (CosmosBatchOperationError, CosmosHttpResponseError) as error:
                        if error.status_code in (409, 412):
                            # Re-read and rebuild from the winner; never retry an old body.
                            self._cache.pop(scenario_id, None)
                            continue
                        raise
                    self._remember(scenario_id, version, result)
                    return result
                raise HistoryStorageError("Cloud history write conflicted; retry later.")
            except AzureError:
                raise HistoryStorageError("Cloud history could not be committed.") from None
