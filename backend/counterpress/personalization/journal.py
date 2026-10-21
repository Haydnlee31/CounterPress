"""Bounded, dataset-pinned correction journal; base match artifacts stay immutable.

Cosmos uses the existing /scenario_id container and point reads only. Both backends
run the builder against the latest committed frame, before making an atomic commit.
"""
import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Annotated

from pydantic import Field
from counterpress.domain.models import Contract, NonNegativeInt
from counterpress.history import HistoryStorageError
from .contracts import Action

Dataset = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
MAX_JOURNAL_BYTES = 1_800_000


class Frame(Contract):
    dataset: Dataset
    generation: NonNegativeInt = 0
    actions: tuple[Action, ...] = ()


def advance(previous, actions):
    actions = tuple(actions)
    if actions == previous.actions:
        return previous
    if actions[:len(previous.actions)] != previous.actions:
        raise ValueError('Correction history is append only')
    result = Frame(dataset=previous.dataset, generation=previous.generation + 1, actions=actions)
    if len(result.model_dump_json().encode()) > MAX_JOURNAL_BYTES - 2000:
        raise ValueError('Correction journal is full; segment storage before adding events')
    return result


def decode(payload, dataset):
    try:
        frame = Frame.model_validate_json(payload)
        if frame.dataset != dataset:
            raise ValueError('Wrong dataset')
        return frame
    except ValueError:
        raise HistoryStorageError('Career correction history failed validation') from None


class SQLiteCareerJournal:
    def __init__(self, path):
        if str(path) != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=10)
        self.db.execute('CREATE TABLE IF NOT EXISTS career_journal(dataset TEXT PRIMARY KEY,payload TEXT NOT NULL)')
        self.db.commit()

    def _read(self, dataset):
        row = self.db.execute('SELECT payload FROM career_journal WHERE dataset=?', (dataset,)).fetchone()
        return decode(row[0], dataset) if row else Frame(dataset=dataset)

    def read(self, dataset):
        with self.lock:
            try:
                return self._read(dataset)
            except sqlite3.Error:
                raise HistoryStorageError('Career correction history could not be read') from None

    def transact(self, dataset, build):
        with self.lock:
            try:
                self.db.execute('BEGIN IMMEDIATE')
                previous = self._read(dataset)
                result = advance(previous, build(previous))
                if result != previous:
                    self.db.execute('INSERT OR REPLACE INTO career_journal VALUES(?,?)',
                                    (dataset, result.model_dump_json()))
                self.db.commit()
                return result
            except BaseException as error:
                self.db.rollback()
                if isinstance(error, sqlite3.Error):
                    raise HistoryStorageError('Career correction history could not be committed') from None
                raise

    def close(self):
        self.db.close()


class CosmosCareerJournal:
    def __init__(self, container):
        self.container = container
        self.lock = RLock()
        self.cache = None

    def _read(self, dataset):
        from azure.cosmos.exceptions import CosmosHttpResponseError
        partition = 'career-' + dataset
        for _ in range(4):
            try:
                head = self.container.read_item(item='head', partition_key=partition)
            except CosmosHttpResponseError as error:
                if error.status_code == 404:
                    return None, Frame(dataset=dataset)
                raise
            if (head.get('schema') != 'career.v1' or head.get('scenario_id') != partition
                    or not head.get('_etag') or type(head.get('generation')) is not int or head['generation'] < 1):
                raise HistoryStorageError('Career correction metadata failed validation')
            if self.cache and self.cache[:2] == (dataset, head['generation']):
                return head, self.cache[2]
            body = self.container.read_item(item='corrections', partition_key=partition)
            if body.get('generation') != head['generation']:
                continue
            if body.get('schema') != 'career.v1' or body.get('scenario_id') != partition:
                raise HistoryStorageError('Career correction payload failed validation')
            frame = decode(json.dumps(body.get('payload')), dataset)
            if frame.generation != head['generation']:
                raise HistoryStorageError('Career correction version failed validation')
            self.cache = (dataset, frame.generation, frame)
            return head, frame
        raise HistoryStorageError('Career corrections changed during reading; retry later')

    def read(self, dataset):
        from azure.core.exceptions import AzureError
        Frame(dataset=dataset)  # Validate before constructing a partition key.
        with self.lock:
            try:
                return self._read(dataset)[1]
            except AzureError:
                raise HistoryStorageError('Career correction history could not be read') from None

    def transact(self, dataset, build):
        from azure.core.exceptions import AzureError
        from azure.cosmos.exceptions import CosmosHttpResponseError, CosmosBatchOperationError
        Frame(dataset=dataset)
        partition = 'career-' + dataset
        with self.lock:
            try:
                for _ in range(4):
                    head, previous = self._read(dataset)
                    result = advance(previous, build(previous))
                    if result == previous:
                        return result
                    common = {'scenario_id': partition, 'schema': 'career.v1', 'generation': result.generation}
                    new_head = {'id': 'head', **common}
                    body = {'id': 'corrections', **common, 'payload': result.model_dump(mode='json')}
                    if len(json.dumps(body, ensure_ascii=True).encode()) > MAX_JOURNAL_BYTES:
                        raise ValueError('Correction journal is full; segment storage before adding events')
                    operations = [('create', (new_head,), {}), ('create', (body,), {})] if head is None else [
                        ('replace', ('head', new_head), {'if_match_etag': head['_etag']}),
                        ('replace', ('corrections', body), {})]
                    try:
                        self.container.execute_item_batch(batch_operations=operations, partition_key=partition)
                    except (CosmosHttpResponseError, CosmosBatchOperationError) as error:
                        if error.status_code in (409, 412):
                            self.cache = None
                            continue
                        raise
                    self.cache = (dataset, result.generation, result)
                    return result
                raise HistoryStorageError('Career correction write conflicted; retry later')
            except AzureError:
                raise HistoryStorageError('Career correction history could not be committed') from None
