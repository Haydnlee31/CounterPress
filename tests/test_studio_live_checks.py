"""Check live-probe behavior against the transaction service double."""
import importlib.util
from pathlib import Path
import pytest
from counterpress.cosmos_history import CosmosHistoryStore
from test_cosmos_history import AtomicContainer

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('studio_probe',ROOT/'scripts/check_studio_cosmos.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)


def test_probe_is_isolated_durable_and_refuses_reuse():
    container=AtomicContainer()
    seed=probe.check('seed','unit',CosmosHistoryStore(container),ROOT/'fixtures')
    restored=probe.check('verify','unit',CosmosHistoryStore(container),Path('/missing-fixtures'))
    assert seed['durable_decisions']==restored['durable_decisions']==4
    assert restored['fixture_free_restore'] and restored['model_calls']==0
    assert {partition for partition,_ in container.items}=={'verify-studio-unit-increase'}
    with pytest.raises(ValueError,match='already exists'):
        probe.check('seed','unit',CosmosHistoryStore(container),ROOT/'fixtures')
