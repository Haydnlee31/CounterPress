"""Catch portal-invalid targets that still allow SDK credential lookup."""
import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    'configure_agent_monitoring',
    Path(__file__).resolve().parents[1] / 'scripts/configure_agent_monitoring.py',
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

RESOURCE = '/subscriptions/test/resourceGroups/test/providers/Microsoft.Insights/components/agents'


def connection(target=RESOURCE):
    return {'category': 'AppInsights', 'authType': 'ApiKey', 'target': target,
            'metadata': {'ResourceId': RESOURCE},
            'credentials': {'key': 'InstrumentationKey=private-canary'}}


def test_accepts_matching_arm_resource_id_case_insensitively():
    module.validate_monitoring_connection(connection(RESOURCE.upper()), RESOURCE)


@pytest.mark.parametrize('target', [
    'InstrumentationKey=private-canary;IngestionEndpoint=https://private-canary.example/',
    'http://private-canary.example/', 'https://private-canary.example/',
    RESOURCE + '-wrong', '',
])
def test_rejects_invalid_portal_target_without_leaking_it(target):
    with pytest.raises(RuntimeError) as error:
        module.validate_monitoring_connection(connection(target), RESOURCE)
    assert 'private-canary' not in str(error.value)


@pytest.mark.parametrize('field,value', [('category', 'AzureOpenAI'), ('authType', 'None'),
                                         ('metadata', {'ResourceId': RESOURCE + '-wrong'})])
def test_rejects_wrong_connection_binding(field, value):
    properties = connection()
    properties[field] = value
    with pytest.raises(RuntimeError):
        module.validate_monitoring_connection(properties, RESOURCE)
