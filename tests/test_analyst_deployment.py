import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('deploy_analyst', Path(__file__).resolve().parents[1] / 'scripts/deploy_azure.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


def app():
    return {'properties': {'template': {'containers': [{'image': 'original', 'env': [
        {'name': 'COUNTERPRESS_STORAGE', 'value': 'cosmos'},
        {'name': 'COUNTERPRESS_ASSISTANT_MODEL', 'value': 'azure'},
        {'name': 'AZURE_OPENAI_API_KEY', 'secretRef': 'retained-model-key'}]}]}}}


def config():
    return {'project_endpoint': 'https://unit-test.services.ai.azure.com/api/projects/test',
            'agent_name': 'FootieAnalystDirector', 'agent_version': '1', 'manifest_id': 'a' * 64, 'verified': True}


def test_native_enable_preserves_existing_footie_and_secrets():
    before = app()
    after = deploy.analyst_settings(before, 'enable', config())
    env = after['properties']['template']['containers'][0]['env']
    assert all(e in env for e in before['properties']['template']['containers'][0]['env'])
    assert {'name': 'COUNTERPRESS_ANALYST_MODE', 'value': 'foundry'} in env
    assert before == app()
    assert deploy.analyst_settings(before, 'preserve') == before
    disabled = deploy.analyst_settings(after, 'disable')
    assert {'name': 'COUNTERPRESS_ANALYST_MODE', 'value': 'off'} in disabled['properties']['template']['containers'][0]['env']


@pytest.mark.parametrize('change', ['unverified', 'http', 'host', 'unpinned', 'storage'])
def test_native_activation_requires_verified_safe_configuration(change):
    cfg = config(); target = app()
    if change == 'unverified': cfg['verified'] = False
    if change == 'http': cfg['project_endpoint'] = cfg['project_endpoint'].replace('https:', 'http:')
    if change == 'host': cfg['project_endpoint'] = 'https://attacker.example/api/projects/test'
    if change == 'unpinned': cfg['agent_version'] = ''
    if change == 'storage': target['properties']['template']['containers'][0]['env'][0]['value'] = 'sqlite'
    with pytest.raises(deploy.DeploymentError): deploy.analyst_settings(target, 'enable', cfg)


def test_discussion_activation_and_rollback_are_explicit():
 enabled=deploy.analyst_settings(app(),'enable',{**config(),'protocol':'roundtable-v2'})
 env=enabled['properties']['template']['containers'][0]['env']
 assert {'name':'COUNTERPRESS_ANALYST_DISCUSSION','value':'foundry'} in env
 assert {'name':'COUNTERPRESS_ANALYST_MODE','value':'off'} in env
 disabled=deploy.analyst_settings(enabled,'disable')
 assert {'name':'COUNTERPRESS_ANALYST_DISCUSSION','value':'off'} in disabled['properties']['template']['containers'][0]['env']


@pytest.mark.parametrize('mode', ['azure', 'foundry'])
def test_postdeploy_probe_requires_available_discussion_without_generating(mode):
    env = {'COUNTERPRESS_ANALYST_MODE': 'off', 'COUNTERPRESS_ANALYST_DISCUSSION': mode}
    ready = {'discussion_available': True, 'discussion_runtime': 'microsoft_agent_framework', 'available': False, 'mode': 'metrics'}
    deploy.verify_analyst_status(env, ready)
    for status in ({}, {**ready, 'discussion_available': False}, {**ready, 'discussion_runtime': None}):
        with pytest.raises(deploy.DeploymentError):
            deploy.verify_analyst_status(env, status)


def test_postdeploy_probe_checks_disabled_and_legacy_paths():
    deploy.verify_analyst_status({}, {'discussion_available': False})
    with pytest.raises(deploy.DeploymentError):
        deploy.verify_analyst_status({}, {'discussion_available': True})
    env = {'COUNTERPRESS_ANALYST_MODE': 'foundry'}
    deploy.verify_analyst_status(env, {'available': True, 'mode': 'foundry'})
    with pytest.raises(deploy.DeploymentError):
        deploy.verify_analyst_status(env, {'available': False, 'mode': 'metrics'})
