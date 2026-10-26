"""No live Azure access: validate output semantics and fail-closed entry point."""
import asyncio
import importlib.util
import json
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('phase4_checkpoint_check',ROOT/'scripts/check_phase4_checkpoint.py')
check=importlib.util.module_from_spec(spec);spec.loader.exec_module(check)


@pytest.mark.parametrize('last,checkpoint,expected',[(-1,None,True),(0,None,False),(4,3,False),(4,4,True)])
def test_checkpoint_matches_actual_partition_head(last,checkpoint,expected):
    rows=[] if checkpoint is None else [{'partition_id':'0','sequence_number':checkpoint}]
    result=check.summarize(['0'],[{'id':'0','last_enqueued_sequence_number':last}],rows)
    assert result=={'checkpoint_sequence':-1 if checkpoint is None else checkpoint,
                   'last_enqueued_sequence':last,'partition_count':1,'caught_up':expected}


@pytest.mark.parametrize('fault',['extra_partition','wrong_partition','future_checkpoint','boolean','duplicate'])
def test_unexpected_storage_state_cannot_claim_caught_up(fault):
    ids=['0'];properties=[{'id':'0','last_enqueued_sequence_number':4}]
    rows=[{'partition_id':'0','sequence_number':4}]
    if fault=='extra_partition':ids.append('1')
    elif fault=='wrong_partition':rows[0]['partition_id']='private-identifier'
    elif fault=='future_checkpoint':rows[0]['sequence_number']=5
    elif fault=='boolean':rows[0]['sequence_number']=True
    else:rows.append(rows[0].copy())
    with pytest.raises(ValueError):check.summarize(ids,properties,rows)


def test_configuration_guard_runs_before_cloud_client_creation(monkeypatch):
    from counterpress.api import phase4
    called=[]
    def reject():called.append(True);raise ValueError('not isolated')
    monkeypatch.setattr(phase4,'validate_environment',reject)
    with pytest.raises(ValueError,match='not isolated'):asyncio.run(check.inspect_once())
    assert called==[True]


def test_sdk_error_is_not_printed(capsys,monkeypatch):
    async def fail():raise RuntimeError('https://private.invalid?access_token=never-print')
    monkeypatch.setattr(check,'inspect_once',fail)
    assert check.main()==2
    output=capsys.readouterr().out
    assert json.loads(output)==check.EMPTY
    assert 'private' not in output and 'token' not in output
