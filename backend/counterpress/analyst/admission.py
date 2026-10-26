"""Separate durable Analyst allowance. Reservations survive crashes and failures.

One reservation covers at most five native model calls plus a short hosted
session. This is a conservative spend allowance, not an Azure billing meter.
The existing Footie budget/ledger is deliberately untouched.
"""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from counterpress.history import HistoryStorageError


class SQLiteStore:
    def __init__(self, path):
        if str(path) == ':memory:':
            raise ValueError('Analyst admission requires durable storage')
        self.path = str(path)

    def transact(self, change):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        try:
            with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
                db.execute('CREATE TABLE IF NOT EXISTS analyst_control (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)')
                db.execute('BEGIN IMMEDIATE')
                row = db.execute('SELECT payload FROM analyst_control WHERE id=1').fetchone()
                state = json.loads(row[0]) if row else {}
                updated, result = change(state)
                db.execute('INSERT OR REPLACE INTO analyst_control VALUES (1,?)', (json.dumps(updated),))
                return result
        except (sqlite3.Error, ValueError):
            raise HistoryStorageError('Analyst allowance unavailable') from None


class CosmosStore:
    partition = 'analyst-control-v1'

    def __init__(self, container):
        self.container = container

    def transact(self, change):
        from azure.core.exceptions import AzureError
        from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosBatchOperationError
        try:
            for _ in range(4):
                try:
                    old = self.container.read_item('control', partition_key=self.partition)
                except CosmosHttpResponseError as exc:
                    if exc.status_code != 404:
                        raise
                    old = None
                state, result = change(old['payload'] if old else {})
                body = {'id': 'control', 'scenario_id': self.partition, 'payload': state}
                if len(json.dumps(body).encode()) > 1_500_000:
                    raise HistoryStorageError('Analyst allowance storage full')
                op = ('replace', ('control', body), {'if_match_etag': old['_etag']}) if old else ('create', (body,), {})
                try:
                    self.container.execute_item_batch(batch_operations=[op], partition_key=self.partition)
                    return result
                except (CosmosHttpResponseError, CosmosBatchOperationError) as exc:
                    if exc.status_code not in (409, 412):
                        raise
            raise HistoryStorageError('Analyst allowance busy')
        except (AzureError, ValueError, KeyError):
            raise HistoryStorageError('Analyst allowance unavailable') from None


class Allowance:
    # $30 of the $200 total is the maximum reserved by this independent pilot.
    # $0.10/run is deliberately above the bounded token + session estimate.
    RUN_CENTS = 10
    TOTAL_CENTS = 3000
    # A ninety-minute replay at 2x can cross ninety source-minute windows in
    # forty-five minutes. Permit that session without raising the lifetime cap.
    MAX_HOURLY = 120
    MAX_DAILY = 200
    LEASE_SECONDS = 180

    def __init__(self, store):
        self.store = store

    def reserve(self, key, now):
        owner = uuid4().hex
        def change(old):
            state = {'spent_cents': old.get('spent_cents', 0),
                     'reservations': [t for t in old.get('reservations', []) if t > now - 86400],
                     'jobs': {k: v for k, v in old.get('jobs', {}).items() if v['expires'] > now}}
            if key in state['jobs']:
                return state, state['jobs'][key]
            reason = ('budget_limit' if state['spent_cents'] + self.RUN_CENTS > self.TOTAL_CENTS else
                      'daily_limit' if len(state['reservations']) >= self.MAX_DAILY else
                      'hourly_limit' if sum(t > now - 3600 for t in state['reservations']) >= self.MAX_HOURLY else
                      'busy' if sum(j['status'] == 'pending' for j in state['jobs'].values()) >= 2 else None)
            if reason:
                return state, {'status': reason}
            job = {'status': 'pending', 'owner': owner, 'expires': now + self.LEASE_SECONDS}
            state['spent_cents'] += self.RUN_CENTS
            state['reservations'].append(now)
            state['jobs'][key] = job
            return state, {**job, 'admitted': True}
        return self.store.transact(change)

    def finish(self, key, owner, result, now):
        # Cache bounded output for repeated viewers. No failure refunds; retry
        # only after cooldown, so a broken provider cannot drain the allowance.
        if result is not None and len(json.dumps(result).encode()) > 16000:
            result = None
        def change(state):
            job = state.get('jobs', {}).get(key)
            if job and job['owner'] == owner and job['status'] == 'pending' and job['expires'] > now:
                state['jobs'][key] = {'status': 'complete' if result is not None else 'unavailable',
                                     'owner': owner, 'expires': now + (3600 if result is not None else 300),
                                     'result': result}
            return state, None
        self.store.transact(change)
