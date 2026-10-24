"""Actual persisted v1 ledgers must remain readable by the rollback release."""
from dataclasses import replace
import json
import sqlite3

import pytest

from counterpress.assistant.admission import (
    Admission, CosmosAdmissionStore, Job, Receipt, SQLiteAdmissionStore,
    State, legacy_state_payload,
)
from counterpress.assistant.contracts import Plan
from counterpress.assistant.multiagent import Task
from counterpress.assistant.narrative import StoryPlan
from counterpress.assistant.research import ResearchResult
from legacy_admission_contract import State as RollbackState
from test_cosmos_history import AtomicContainer


@pytest.fixture(params=['sqlite', 'cosmos'])
def ledger(request, tmp_path):
    if request.param == 'cosmos':
        container = AtomicContainer()
        store = CosmosAdmissionStore(container)
        def read():
            return container.read_item(item='control', partition_key=store.partition)['payload']
    else:
        path = tmp_path / 'admission.sqlite3'
        store = SQLiteAdmissionStore(path)
        def read():
            with sqlite3.connect(path) as db:
                return json.loads(db.execute('SELECT payload FROM assistant_control WHERE id=1').fetchone()[0])
    return Admission(store, hourly_limit=8), read


def result():
    plan = Plan(operation='stats', player_ids=['rh09'], club_id=None, match_id=None,
                metric='goals', per90=False, season=None, comparison_season=None)
    return ResearchResult(plan, StoryPlan(lead='claim_1', supporting=[]), 'a'*64, {}, 2, 1, 2)


def advanced(kind):
    answer = result()
    analysis = answer.plan.model_copy(update={'operation':'match', 'analysis':'buildup'})
    if kind == 'analysis':return replace(answer, plan=analysis)
    if kind == 'investigation':
        return replace(answer, plan=answer.plan.model_copy(update={'investigate_player_id':'rh09'}))
    if kind == 'calculated':return replace(answer, selection_mode='calculated')
    return replace(answer, tasks=(Task(role='career',start=0,end=10), Task(role='match',start=11,end=20)),
                   plans=(answer.plan, analysis))


def decode(payload):
    # JSON validation models the old runtime, including strict tuple decoding.
    return RollbackState.model_validate_json(json.dumps(payload))


def test_legacy_receipt_keeps_cache_and_nested_plans_in_rollback_wire_shape(ledger):
    admission, read = ledger
    answer = result()
    answer = replace(answer, tasks=(Task(role='career', start=0, end=10),), plans=(answer.plan,))
    _, job = admission.reserve('legacy', 100, 4)
    admission.finish('legacy', job.owner, 101, answer)
    raw = read()
    old = decode(raw)
    receipt = raw['jobs']['legacy']['receipt']
    assert 'selection_mode' not in receipt
    for plan in (receipt['plan'], *receipt['plans']):
        assert 'analysis' not in plan and 'investigate_player_id' not in plan
    assert old.weighted == ((100,4),)
    assert old.jobs['legacy'].receipt.plan.metric == 'goals'
    status, cached = admission.reserve('legacy', 102, 4)
    assert status == 'done' and cached.receipt.selection_mode == 'agent_selected'
    assert cached.receipt.plans == answer.plans
    assert decode(read()).weighted == old.weighted


@pytest.mark.parametrize('kind', ['analysis','investigation','calculated','secondary_analysis'])
def test_new_success_omits_only_its_receipt_and_preserves_usage_and_other_lease(ledger, kind):
    admission, read = ledger
    _, pending = admission.reserve('other', 100, 4)
    _, job = admission.reserve('new', 101, 4)
    admission.finish('new', job.owner, 102, advanced(kind))
    old = decode(read())
    assert set(old.jobs) == {'other'}
    assert old.jobs['other'].owner == pending.owner
    assert old.jobs['other'].until == pending.until and old.jobs['other'].state == 'pending'
    assert old.weighted == ((100,4),(101,4))
    assert admission.reserve('new', 103, 4)[0] == 'hourly_limit'
    assert decode(read()).weighted == old.weighted


def test_failed_attempt_retains_cooldown_and_charged_budget_in_old_format(ledger):
    admission, read = ledger
    _, job = admission.reserve('failed', 100, 4)
    admission.finish('failed', job.owner, 101)
    old = decode(read())
    assert old.jobs['failed'].state == 'done' and old.jobs['failed'].receipt is None
    assert old.jobs['failed'].until == 161 and old.weighted == ((100,4),)
    assert admission.reserve('failed', 102, 4)[0] == 'done'
    assert admission.reserve('failed', 161, 4)[0] == 'reserved'
    assert decode(read()).weighted == ((100,4),(161,4))


@pytest.mark.parametrize('guard', ['wrong_owner','expired_lease','replaced_owner'])
def test_stale_owner_cannot_remove_pending_job_with_advanced_result(ledger, guard):
    admission, read = ledger
    _, job = admission.reserve('new', 100, 4)
    owner, now = ('wrong-owner',101) if guard == 'wrong_owner' else (job.owner,121)
    expected = job
    if guard == 'replaced_owner':
        _, expected = admission.reserve('new', 120, 4)
    admission.finish('new', owner, now, advanced('calculated'))
    old = decode(read())
    assert old.jobs['new'].owner == expected.owner and old.jobs['new'].state == 'pending'
    assert old.weighted == (((100,4),(120,4)) if guard == 'replaced_owner' else ((100,4),))


def test_cosmos_conflict_rebuilds_advanced_finish_without_losing_other_reservations():
    container = AtomicContainer()
    store = CosmosAdmissionStore(container)
    admission = Admission(store, hourly_limit=8)
    competing = Admission(CosmosAdmissionStore(container), hourly_limit=8)
    _, job = admission.reserve('new', 100, 4)
    container.before_batch = lambda:competing.reserve('other', 101, 4)
    admission.finish('new', job.owner, 102, advanced('analysis'))
    old = decode(container.read_item(item='control',partition_key=store.partition)['payload'])
    assert set(old.jobs) == {'other'} and old.jobs['other'].state == 'pending'
    assert old.weighted == ((100,4),(101,4))
    assert admission.reserve('new', 103, 4)[0] == 'hourly_limit'


def test_old_decoder_rejects_unstripped_new_fields_and_writer_refuses_semantic_loss():
    answer = result()
    receipt = Receipt(plan=answer.plan, selection=answer.selection, evidence_id=answer.evidence_id)
    state = State(jobs={'cached':Job(owner='owner',until=200,state='done',receipt=receipt)})
    with pytest.raises(ValueError):decode(state.model_dump(mode='json'))
    assert decode(legacy_state_payload(state)).jobs['cached'].receipt.plan.metric == 'goals'
    unsafe = receipt.model_copy(update={'selection_mode':'calculated'})
    with pytest.raises(ValueError,match='incompatible receipt'):
        legacy_state_payload(state.model_copy(update={'jobs':{'cached':Job(owner='owner',until=200,state='done',receipt=unsafe)}}))
