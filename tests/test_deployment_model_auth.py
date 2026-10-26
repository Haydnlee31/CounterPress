"""Template-only model identity migration and explicit retained-key rollback."""
import copy
import importlib.util
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('deploy_model_auth',ROOT/'scripts/deploy_azure.py')
deploy=importlib.util.module_from_spec(spec);spec.loader.exec_module(deploy)
BASE='/subscriptions/11111111-1111-4111-8111-111111111111/resourceGroups/counterpress-dev'
HISTORY=BASE+'/providers/Microsoft.ManagedIdentity/userAssignedIdentities/counterpress-history'
CLIENT='22222222-2222-4222-8222-222222222222'


def fixture():
    env={'COUNTERPRESS_STORAGE':'cosmos','COUNTERPRESS_STREAMING':'azure','COUNTERPRESS_TELEMETRY':'on',
         'COUNTERPRESS_COSMOS_CLIENT_ID':CLIENT,'COUNTERPRESS_ASSISTANT_MODEL':'azure',
         'COUNTERPRESS_ASSISTANT_WORKFLOW':'multiagent','COUNTERPRESS_ASSISTANT_CALLS_PER_HOUR':'120',
         'COUNTERPRESS_ASSISTANT_CALLS_PER_DAY':'400','COUNTERPRESS_EDITORIAL':'entra',
         'COUNTERPRESS_STUDIO':'entra','COUNTERPRESS_STUDIO_CLIENT_ID':CLIENT,'COUNTERPRESS_ENTRA_CLIENT_IDS':CLIENT}
    return {'id':BASE+'/providers/Microsoft.App/containerApps/counterpress',
        'identity':{'type':'UserAssigned','userAssignedIdentities':{HISTORY:{'clientId':CLIENT}}},
        'properties':{'environmentId':'existing-environment',
            'configuration':{'activeRevisionsMode':'Single','ingress':{'allowInsecure':False},
                'secrets':[{'name':name} for name in deploy.MODEL_SECRETS.values()]},
            'template':{'containers':[{'image':'original','env':[{'name':k,'value':v} for k,v in env.items()]+[
                {'name':name,'secretRef':secret} for name,secret in deploy.MODEL_SECRETS.items()]}],
                'scale':{'minReplicas':0,'maxReplicas':1}}}}


def entries(app):return app['properties']['template']['containers'][0]['env']
def environment(app):return {e['name']:e for e in entries(app)}


def test_preserve_is_an_exact_deep_copy_without_inspecting_or_mutating_configuration():
    app={'unrelated':'unchanged'}
    result=deploy.model_authentication_settings(app,'preserve')
    assert result==app and result is not app


def test_migration_and_rollback_change_only_authentication_environment():
    original=fixture();before=copy.deepcopy(original)
    migrated=deploy.model_authentication_settings(original,'managed_identity')
    assert original==before
    env=environment(migrated)
    assert 'AZURE_OPENAI_API_KEY' not in env
    assert env['AZURE_OPENAI_AUTH_MODE']['value']=='managed_identity'
    assert env['AZURE_OPENAI_MANAGED_IDENTITY_CLIENT_ID']['value']==CLIENT
    for key in ('AZURE_OPENAI_ENDPOINT','AZURE_OPENAI_DEPLOYMENT'):
        assert env[key]==environment(original)[key]
    assert migrated['properties']['configuration']==original['properties']['configuration']
    assert migrated['identity']==original['identity']
    assert migrated['properties']['template']['scale']==original['properties']['template']['scale']
    assert deploy.model_authentication_settings(migrated,'managed_identity')==migrated
    deploy.validate_app(migrated)
    assert environment(deploy.assistant_settings(migrated,'enable'))==environment(migrated)
    rolled=deploy.model_authentication_settings(migrated,'api_key')
    renv=environment(rolled)
    assert renv['AZURE_OPENAI_API_KEY']=={'name':'AZURE_OPENAI_API_KEY','secretRef':'editorial-key'}
    assert renv['AZURE_OPENAI_AUTH_MODE']['value']=='api_key'
    assert 'AZURE_OPENAI_MANAGED_IDENTITY_CLIENT_ID' not in renv
    deploy.validate_app(rolled)
    ignored=deploy.MODEL_AUTH_KEYS|{'AZURE_OPENAI_API_KEY'}
    assert {k:v for k,v in renv.items() if k not in ignored}=={k:v for k,v in environment(original).items() if k not in ignored}
    assert rolled['properties']['configuration']==original['properties']['configuration']


@pytest.mark.parametrize('issue',['missing','wrong-name','mismatched-client','duplicate-client','invalid-uuid','noncanonical-uuid','different-group','secret-cosmos-client'])
def test_identity_must_be_explicit_canonical_and_attached_history_identity(issue):
    app=fixture();ids=app['identity']['userAssignedIdentities'];env=environment(app)
    if issue=='missing':ids.clear()
    elif issue=='wrong-name':ids[HISTORY.replace('counterpress-history','unreviewed')]=ids.pop(HISTORY)
    elif issue=='mismatched-client':ids[HISTORY]['clientId']='33333333-3333-4333-8333-333333333333'
    elif issue=='duplicate-client':ids[HISTORY+'-duplicate']={'clientId':CLIENT}
    elif issue=='invalid-uuid':env['COUNTERPRESS_COSMOS_CLIENT_ID']['value']='invalid'
    elif issue=='noncanonical-uuid':env['COUNTERPRESS_COSMOS_CLIENT_ID']['value']='{'+CLIENT+'}'
    elif issue=='different-group':ids[HISTORY.replace('/counterpress-dev/','/other/')]=ids.pop(HISTORY)
    else:env['COUNTERPRESS_COSMOS_CLIENT_ID'].update(secretRef='private')
    with pytest.raises(deploy.DeploymentError):deploy.model_authentication_settings(app,'managed_identity')


@pytest.mark.parametrize('issue',['inline-key','unknown-auth-key','duplicate-key','duplicate-mode','wrong-mode','key-in-mi','wrong-mi-client','no-mi-client','secret-mode','missing-rollback','duplicate-secret'])
def test_malformed_authentication_fails_closed_before_switch_or_activation(issue):
    app=fixture()
    if issue in ('key-in-mi','wrong-mi-client','no-mi-client','secret-mode','missing-rollback'):
        app=deploy.model_authentication_settings(app,'managed_identity')
    env=environment(app)
    if issue=='inline-key':env['AZURE_OPENAI_API_KEY'].update(value='must-not-leak')
    elif issue=='unknown-auth-key':entries(app).append({'name':'AZURE_OPENAI_TOKEN','value':'must-not-leak'})
    elif issue=='duplicate-key':entries(app).append(copy.deepcopy(env['AZURE_OPENAI_API_KEY']))
    elif issue=='duplicate-mode':entries(app).extend([{'name':'AZURE_OPENAI_AUTH_MODE','value':'api_key'}]*2)
    elif issue=='wrong-mode':entries(app).append({'name':'AZURE_OPENAI_AUTH_MODE','value':'default_credential'})
    elif issue=='key-in-mi':entries(app).append({'name':'AZURE_OPENAI_API_KEY','secretRef':'editorial-key'})
    elif issue=='wrong-mi-client':env['AZURE_OPENAI_MANAGED_IDENTITY_CLIENT_ID']['value']='33333333-3333-4333-8333-333333333333'
    elif issue=='no-mi-client':entries(app).remove(env['AZURE_OPENAI_MANAGED_IDENTITY_CLIENT_ID'])
    elif issue=='secret-mode':env['AZURE_OPENAI_AUTH_MODE']['secretRef']='mode-secret'
    elif issue=='missing-rollback':app['properties']['configuration']['secrets']=[s for s in app['properties']['configuration']['secrets'] if s['name']!='editorial-key']
    elif issue=='duplicate-secret':app['properties']['configuration']['secrets'].append({'name':'editorial-key'})
    with pytest.raises(deploy.DeploymentError):deploy.model_authentication_settings(app,'api_key')
    with pytest.raises(AssertionError):deploy.validate_app(app)
    if issue not in ('missing-rollback','duplicate-secret'):
        with pytest.raises(deploy.DeploymentError):deploy.assistant_settings(app,'enable')


def test_editorial_changes_do_not_restore_key_or_break_shared_managed_identity():
    app=deploy.model_authentication_settings(fixture(),'managed_identity')
    disabled=deploy.editorial_settings(app,'disable')
    assert environment(disabled)['COUNTERPRESS_EDITORIAL']['value']=='off'
    assert 'AZURE_OPENAI_API_KEY' not in environment(disabled)
    deploy.validate_app(disabled)
    model={'AZURE_OPENAI_ENDPOINT':'https://fixture.openai.azure.com','AZURE_OPENAI_DEPLOYMENT':'fixture','AZURE_OPENAI_API_KEY':'private-test-key'}
    enabled=deploy.editorial_settings(disabled,'enable',model)
    assert 'AZURE_OPENAI_API_KEY' not in environment(enabled)
    assert environment(enabled)['AZURE_OPENAI_AUTH_MODE']['value']=='managed_identity'
    assert environment(enabled)['AZURE_OPENAI_MANAGED_IDENTITY_CLIENT_ID']['value']==CLIENT
    deploy.validate_app(enabled)
    # Even if both paid features are disabled, re-enabling the editor preserves MI.
    both_off=deploy.assistant_settings(disabled,'disable')
    deploy.validate_app(both_off)
    reenabled=deploy.editorial_settings(both_off,'enable',model)
    assert 'AZURE_OPENAI_API_KEY' not in environment(reenabled)
    deploy.validate_app(reenabled)


def test_editorial_disable_preserves_active_footie_key_references():
    app=deploy.editorial_settings(fixture(),'disable')
    assert environment(app)['AZURE_OPENAI_API_KEY']['secretRef']=='editorial-key'
    deploy.validate_app(app)


def test_workflow_auth_choice_never_requires_configuration_patch_or_role_write():
    workflow=(ROOT/'.github/workflows/deploy.yml').read_text()
    assert 'options: [preserve, managed_identity, api_key]' in workflow
    assert 'CP_MODEL_AUTHENTICATION: ${{ inputs.model_authentication }}' in workflow
    script=(ROOT/'scripts/deploy_azure.py').read_text()
    assert "configuration_update = editorial_mode == 'enable' or tracing_mode == 'enable'" in script
    assert 'model_authentication_settings(expected, authentication_mode)' in script
    assert 'role assignment create' not in workflow and 'role assignment create' not in script


def test_authentication_switch_rejects_unknown_mode_and_mixed_credentials_without_repair():
    app=fixture()
    with pytest.raises(deploy.DeploymentError):deploy.model_authentication_settings(app,'automatic')
    explicit=deploy.model_authentication_settings(app,'api_key')
    deploy.validate_app(explicit)
    entries(explicit).append({'name':'AZURE_OPENAI_MANAGED_IDENTITY_CLIENT_ID','value':CLIENT})
    with pytest.raises(deploy.DeploymentError):deploy.model_authentication_settings(explicit,'managed_identity')
    with pytest.raises(deploy.DeploymentError):deploy.assistant_settings(explicit,'enable')


def test_assistant_activation_rejects_missing_declared_secret_even_in_managed_identity():
    app=deploy.model_authentication_settings(fixture(),'managed_identity')
    app['properties']['configuration']['secrets']=[{'name':'editorial-endpoint'},{'name':'editorial-deployment'}]
    with pytest.raises(deploy.DeploymentError):deploy.assistant_settings(app,'enable')


@pytest.mark.parametrize('authentication', ['api_key', 'managed_identity'])
def test_azure_discussion_activation_preserves_authentication_and_all_other_settings(authentication):
    original = deploy.model_authentication_settings(fixture(), authentication)
    original['properties']['template']['containers'][0]['env'].extend([
        {'name': 'COUNTERPRESS_ANALYST_MODE', 'value': 'foundry'},
        {'name': 'COUNTERPRESS_ANALYST_MANIFEST_ID', 'value': 'a' * 64},
    ])
    before = copy.deepcopy(original)
    enabled = deploy.analyst_settings(original, 'azure_discussion')
    changed = {'COUNTERPRESS_ANALYST_MODE', 'COUNTERPRESS_ANALYST_DISCUSSION'}
    assert [e for e in entries(enabled) if e['name'] not in changed] == [e for e in entries(before) if e['name'] not in changed]
    assert environment(enabled)['COUNTERPRESS_ANALYST_DISCUSSION']['value'] == 'azure'
    assert environment(enabled)['COUNTERPRESS_ANALYST_MODE']['value'] == 'off'
    assert enabled['properties']['configuration'] == before['properties']['configuration']
    assert enabled['identity'] == before['identity']
    assert enabled['properties']['template']['scale'] == before['properties']['template']['scale']
    assert original == before
    deploy.validate_app(enabled)
    disabled = deploy.analyst_settings(enabled, 'disable')
    assert environment(disabled)['COUNTERPRESS_ANALYST_DISCUSSION']['value'] == 'off'
    assert [e for e in entries(disabled) if e['name'] not in changed] == [e for e in entries(before) if e['name'] not in changed]
    assert deploy.analyst_settings(enabled, 'preserve') == enabled


@pytest.mark.parametrize('issue', ['sqlite', 'missing-auth', 'inline-key', 'missing-secret', 'wrong-mi-identity'])
def test_azure_discussion_rejects_unsafe_activation(issue):
    target = fixture()
    env = environment(target)
    if issue == 'sqlite': env['COUNTERPRESS_STORAGE']['value'] = 'sqlite'
    elif issue == 'missing-auth':
        entries(target)[:] = [e for e in entries(target) if not e['name'].startswith('AZURE_OPENAI')]
    elif issue == 'inline-key': env['AZURE_OPENAI_API_KEY'].update(value='never-log-test-value')
    elif issue == 'missing-secret': target['properties']['configuration']['secrets'] = []
    else:
        target = deploy.model_authentication_settings(target, 'managed_identity')
        environment(target)['AZURE_OPENAI_MANAGED_IDENTITY_CLIENT_ID']['value'] = '33333333-3333-4333-8333-333333333333'
    with pytest.raises(deploy.DeploymentError):
        deploy.analyst_settings(target, 'azure_discussion')


def test_existing_azure_discussion_requires_auth_even_when_other_paid_features_off():
    target = fixture()
    entries(target)[:] = [e for e in entries(target) if not e['name'].startswith('AZURE_OPENAI')]
    environment(target)['COUNTERPRESS_EDITORIAL']['value'] = 'off'
    environment(target)['COUNTERPRESS_ASSISTANT_MODEL']['value'] = 'off'
    entries(target).append({'name': 'COUNTERPRESS_ANALYST_DISCUSSION', 'value': 'azure'})
    with pytest.raises(AssertionError, match='Invalid model authentication'):
        deploy.validate_app(target)
