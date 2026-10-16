import asyncio
import importlib.util
from pathlib import Path
from threading import RLock

from cryptography.hazmat.primitives.asymmetric import rsa
import pytest

from counterpress.cosmos_history import CosmosHistoryStore
from test_cosmos_history import AtomicContainer
from test_editorial_controls import SETTINGS, token, verifier

ROOT = Path(__file__).resolve().parents[1]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LockedContainer(AtomicContainer):
    def __init__(self):
        super().__init__()
        self.lock = RLock()

    def execute_item_batch(self, **kwargs):
        with self.lock:
            return super().execute_item_batch(**kwargs)


def test_cosmos_live_probe_logic_checks_conflicts_restart_and_revision_invalidation():
    check = script('check_editorial_cosmos')
    container = LockedContainer()
    result = check.seed('offline-test', CosmosHistoryStore(container), ROOT/'fixtures')
    assert result['real_cosmos_conflict_statuses'] == [409]
    assert result['external_model_calls'] == 0
    restored = check.verify('offline-test', CosmosHistoryStore(container))
    assert restored['fresh_process_quota_preserved'] and restored['historical_counts'] == [4, 3, None, 2]
    with pytest.raises(ValueError, match='fresh verification scope'):
        check.seed('offline-test', CosmosHistoryStore(container), ROOT/'fixtures')
    assert all(scope.startswith('verify-') for scope, item in container.items)


def test_identity_probe_exercises_real_verifier_without_provider_credentials():
    check = script('check_editorial_identity')
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    result = asyncio.run(check.check(token(key), SETTINGS, verifier=verifier(key)))
    assert result['model_calls'] == 0
    assert result['authorized_context_http'] == 200
    assert result['disallowed_client_status'] == 403
