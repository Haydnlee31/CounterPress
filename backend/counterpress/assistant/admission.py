"""Shared, bounded admission for the opt-in research workflow.

Reserve both possible provider requests before work. Never refund failed/unknown
usage. Persist only hashed query keys and typed plans/claim IDs, not user text.
"""
import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import Field
from starlette.concurrency import run_in_threadpool

from counterpress.adaptation.azure import ProviderFailure
from counterpress.domain.models import Contract
from counterpress.history import HistoryStorageError
from .contracts import Plan
from .narrative import StoryPlan
from .research import ResearchResult
from .service import fingerprint


class Receipt(Contract):
    plan: Plan
    selection: StoryPlan
    evidence_id: str = Field(pattern=r'^[a-f0-9]{64}$')


class Job(Contract):
    owner: str
    until: float
    state: Literal['pending', 'done'] = 'pending'
    receipt: Receipt | None = None


class State(Contract):
    version: Literal[1] = 1
    # Two slots per admitted research job; at most twenty in the rolling hour.
    reservations: tuple[float, ...] = Field(default=(), max_length=10)
    jobs: dict[str, Job] = Field(default_factory=dict, max_length=10)


class SQLiteAdmissionStore:
    def __init__(self, path):
        if str(path) == ':memory:':
            raise ValueError('Agent admission requires durable storage')
        self.path = str(path)

    def transact(self, build):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        try:
            with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
                db.execute('CREATE TABLE IF NOT EXISTS assistant_control (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)')
                db.execute('BEGIN IMMEDIATE')
                row = db.execute('SELECT payload FROM assistant_control WHERE id=1').fetchone()
                state = State.model_validate_json(row[0]) if row else State()
                updated = build(state)
                db.execute('INSERT OR REPLACE INTO assistant_control VALUES (1, ?)', (updated.model_dump_json(),))
                return updated
        except (sqlite3.Error, ValueError):
            raise HistoryStorageError('Assistant admission is unavailable') from None


class CosmosAdmissionStore:
    partition = 'assistant-control-v1'

    def __init__(self, container):
        self.container = container

    def transact(self, build):
        from azure.core.exceptions import AzureError
        from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosBatchOperationError
        try:
            for _ in range(4):
                try:
                    old = self.container.read_item(item='control', partition_key=self.partition)
                except CosmosHttpResponseError as exc:
                    if exc.status_code != 404:raise
                    old = None
                state = State.model_validate_json(json.dumps(old['payload'])) if old else State()
                updated = build(state)
                if old and updated == state:return updated
                body = {'id':'control', 'scenario_id':self.partition, 'payload':updated.model_dump(mode='json')}
                operation = ('replace', ('control', body), {'if_match_etag':old['_etag']}) if old else ('create', (body,), {})
                try:
                    self.container.execute_item_batch(batch_operations=[operation], partition_key=self.partition)
                    return updated
                except (CosmosHttpResponseError, CosmosBatchOperationError) as exc:
                    if exc.status_code not in (409, 412):raise
            raise HistoryStorageError('Assistant admission is busy')
        except (AzureError, ValueError, KeyError):
            raise HistoryStorageError('Assistant admission is unavailable') from None


class Admission:
    def __init__(self, store):self.store = store

    def reserve(self, key, now):
        owner = uuid4().hex
        outcome = None
        def build(previous):
            nonlocal outcome
            reservations = tuple(at for at in previous.reservations if at > now - 3600)
            jobs = {k:j for k,j in previous.jobs.items() if j.until > now}
            state = State(reservations=reservations, jobs=jobs)
            job = jobs.get(key)
            if job:
                outcome = (job.state, job)
            elif len(reservations) >= 10:
                outcome = ('hourly_limit', None)
            elif sum(j.state == 'pending' for j in jobs.values()) >= 2:
                outcome = ('busy', None)
            else:
                job = Job(owner=owner, until=now+20)
                outcome = ('reserved', job)
                state = State(reservations=(*reservations, now), jobs={**jobs, key:job})
            return state
        self.store.transact(build)
        return outcome

    def finish(self, key, owner, now, result=None):
        def build(state):
            job = state.jobs.get(key)
            if not job or job.owner != owner or job.state != 'pending' or job.until <= now:
                return state
            receipt = Receipt(plan=result.plan, selection=result.selection, evidence_id=result.evidence_id) if result else None
            return state.model_copy(update={'jobs':{**state.jobs, key:Job(owner=owner, until=now+60,
                state='done', receipt=receipt)}})
        self.store.transact(build)


class SharedResearcher:
    def __init__(self, inner, admission, namespace, clock=time.time):
        self.inner, self.admission, self.namespace, self.clock = inner, admission, namespace, clock

    async def research(self, service, request, reserve):
        def key_for_snapshot():
            with service.store.snapshot():
                revisions = [tuple(row) for row in service.store.db.execute(
                    'SELECT match_id,event_id,revision,sequence FROM career_revisions ORDER BY match_id,event_id,revision')]
                return fingerprint({'namespace':self.namespace, 'dataset':service.store.dataset,
                    'revisions':revisions, 'request':request.model_dump(mode='json')})
        try:
            key = await run_in_threadpool(key_for_snapshot)
            outcome, job = await run_in_threadpool(self.admission.reserve, key, self.clock())
        except (HistoryStorageError, OSError, sqlite3.Error, ValueError):
            raise ProviderFailure('unavailable', 'admission_unavailable') from None
        if outcome == 'done':
            if job.receipt:
                r = job.receipt
                return ResearchResult(r.plan, r.selection, r.evidence_id, {}, 0, 0, 0, cached=True)
            raise ProviderFailure('limited', 'recent_attempt_failed')
        if outcome != 'reserved':raise ProviderFailure('limited', outcome)
        result = None
        attempts = 0
        def bounded_reserve():
            nonlocal attempts
            if attempts >= 2 or self.clock() >= job.until:return False
            if not reserve():return False
            attempts += 1
            return True
        try:
            result = await self.inner.research(service, request, bounded_reserve)
            return result
        finally:
            # Cancellation/crash cannot refund slots. An abandoned lease expires;
            # an available receipt is always revalidated by the API before display.
            try:
                await run_in_threadpool(self.admission.finish, key, job.owner, self.clock(), result)
            except (HistoryStorageError, OSError, sqlite3.Error, ValueError):
                pass


def shared_researcher(inner, history_store, namespace):
    from counterpress.cosmos_history import CosmosHistoryStore
    from counterpress.history import SQLiteHistoryStore
    if isinstance(history_store, CosmosHistoryStore):
        store = CosmosAdmissionStore(history_store.container)
    elif isinstance(history_store, SQLiteHistoryStore):
        store = SQLiteAdmissionStore(history_store.path)
    else:raise ValueError('Agent activation requires durable shared admission')
    return SharedResearcher(inner, Admission(store), namespace)
