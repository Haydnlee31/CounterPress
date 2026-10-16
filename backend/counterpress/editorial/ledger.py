"""Atomic shared admission: no refund, no automatic lifetime quota reset, no model I/O in transactions."""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Literal
from uuid import uuid4

from pydantic import Field
from azure.core.exceptions import AzureError
from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosBatchOperationError

from counterpress.domain.models import Contract
from counterpress.history import HistoryStorageError


class Limits(Contract):
    lifetime: int = Field(default=100, ge=1, le=100)
    daily: int = Field(default=20, ge=1, le=20)
    per_editor_daily: int = Field(default=5, ge=1, le=5)
    concurrent: int = Field(default=2, ge=1, le=2)


class Job(Contract):
    owner: str
    lease_until: int
    state: Literal['pending', 'done'] = 'pending'
    dispatched: bool = False
    cache_until: int = 0
    attempt_id: str | None = None


class LedgerState(Contract):
    schema_version: Literal[1] = 1
    limits: Limits
    admitted: int = Field(default=0, ge=0, le=100)
    days: dict[str, int] = Field(default_factory=dict)
    editors: dict[str, int] = Field(default_factory=dict)
    jobs: dict[str, Job] = Field(default_factory=dict)


class SQLiteLedgerStore:
    def __init__(self, path):
        self.path, self.lock, self.memory = str(path), RLock(), None

    def transact(self, build):
        with self.lock:
            if self.path != ':memory:':
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            connection = self.memory or sqlite3.connect(self.path, timeout=5, check_same_thread=False)
            if self.path == ':memory:':
                self.memory = connection
            try:
                connection.execute('CREATE TABLE IF NOT EXISTS editorial_control (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)')
                connection.execute('BEGIN IMMEDIATE')
                row = connection.execute('SELECT payload FROM editorial_control WHERE id=1').fetchone()
                result = build(LedgerState.model_validate_json(row[0]) if row else None)
                connection.execute('INSERT INTO editorial_control VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',
                                   (result.model_dump_json(),))
                connection.commit()
                return result
            except Exception:
                connection.rollback()
                raise
            finally:
                if self.path != ':memory:':
                    connection.close()


class CosmosLedgerStore:
    """One global control item in the existing /scenario_id container. ETag CAS, no cache."""
    partition = 'editorial-control-v1'

    def __init__(self, container):
        self.container = container

    def transact(self, build):
        try:
            for _ in range(4):
                try:
                    old = self.container.read_item(item='editorial-control', partition_key=self.partition)
                except CosmosHttpResponseError as exc:
                    if exc.status_code != 404:
                        raise
                    old = None
                state = LedgerState.model_validate(old['payload']) if old else None
                result = build(state)
                if result == state:
                    return result
                body = {'id': 'editorial-control', 'scenario_id': self.partition,
                        'payload': result.model_dump(mode='json')}
                operation = ('replace', ('editorial-control', body), {'if_match_etag': old['_etag']}) if old else ('create', (body,), {})
                try:
                    self.container.execute_item_batch(batch_operations=[operation], partition_key=self.partition)
                    return result
                except (CosmosHttpResponseError, CosmosBatchOperationError) as exc:
                    if exc.status_code not in (409, 412):
                        raise
            raise HistoryStorageError('Editorial admission is busy.')
        except (AzureError, KeyError):
            raise HistoryStorageError('Editorial admission is unavailable.') from None


class Ledger:
    def __init__(self, store, limits=Limits()):
        self.store, self.limits = store, limits

    def _state(self, previous):
        state = previous or LedgerState(limits=self.limits)
        if state.limits != self.limits:
            raise HistoryStorageError('Editorial policy changed; operator review required.')
        return state

    def reserve(self, key, editor, now):
        owner = uuid4().hex
        day = datetime.fromtimestamp(now / 1000, timezone.utc).date().isoformat()
        editor_day = f'{day}:{editor}'
        outcome = None

        def build(previous):
            nonlocal outcome
            state = self._state(previous)
            job = state.jobs.get(key)
            if job and job.state == 'pending' and now < job.lease_until:
                outcome = ('pending', job)
                return state
            if job and job.state == 'done' and now < job.cache_until:
                outcome = ('cached', job)
                return state
            if (state.admitted >= self.limits.lifetime or state.days.get(day, 0) >= self.limits.daily
                    or state.editors.get(editor_day, 0) >= self.limits.per_editor_daily):
                outcome = ('quota_exceeded', None)
                return state
            if sum(j.state == 'pending' and now < j.lease_until for j in state.jobs.values()) >= self.limits.concurrent:
                outcome = ('busy', None)
                return state
            job = Job(owner=owner, lease_until=now + 30000)
            outcome = ('reserved', job)
            # At most 100 lifetime admissions bounds this document without dropping counters.
            return state.model_copy(update={
                'admitted': state.admitted + 1, 'days': {**state.days, day: state.days.get(day, 0) + 1},
                'editors': {**state.editors, editor_day: state.editors.get(editor_day, 0) + 1},
                'jobs': {**state.jobs, key: job}})

        self.store.transact(build)
        return outcome

    def dispatch(self, key, owner, now):
        allowed = False

        def build(previous):
            nonlocal allowed
            state = self._state(previous)
            job = state.jobs.get(key)
            allowed = bool(job and job.owner == owner and job.state == 'pending'
                           and now < job.lease_until and not job.dispatched)
            return state.model_copy(update={'jobs': {**state.jobs, key: job.model_copy(update={'dispatched': True})}}) if allowed else state

        self.store.transact(build)
        return allowed

    def finish(self, key, owner, now, attempt=None):
        def build(previous):
            state = self._state(previous)
            job = state.jobs.get(key)
            if not job or job.owner != owner or job.state != 'pending':
                return state
            expiry = min(now + 60000, attempt.expires_at_unix_ms) if attempt else now + 30000
            return state.model_copy(update={'jobs': {**state.jobs, key: job.model_copy(update={
                'state': 'done', 'cache_until': expiry, 'attempt_id': attempt.attempt_id if attempt else None})}})
        self.store.transact(build)
