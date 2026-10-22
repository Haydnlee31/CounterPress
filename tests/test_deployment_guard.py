"""Regression checks for deployment privilege and configuration boundaries."""
import copy
import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('deploy',Path(__file__).resolve().parents[1]/'scripts/deploy_azure.py')
deploy=importlib.util.module_from_spec(spec);spec.loader.exec_module(deploy)


def test_ci_requires_matching_main_push_from_ci_workflow():
    run={'head_sha':'a'*40,'head_branch':'main','event':'push','conclusion':'success','path':'.github/workflows/ci.yml'}
    assert deploy.check_ci({'workflow_runs':[run]},'a'*40)
    for key,value in [('head_sha','b'*40),('head_branch','feature'),('event','pull_request'),('conclusion','failure'),('path','.github/workflows/deploy.yml')]:
        assert not deploy.check_ci({'workflow_runs':[run|{key:value}]},'a'*40)


def test_image_only_invariants_detect_storage_scaling_and_identity_drift():
    app={'identity':{'type':'UserAssigned','userAssignedIdentities':{'test':{}}},
         'properties':{'environmentId':'test-env','template':{'containers':[{'image':'old','env':[{'name':'COUNTERPRESS_STORAGE','value':'cosmos'}]}],
                        'scale':{'maxReplicas':1}},'configuration':{'ingress':{'external':True,'traffic':[]}}}}
    newer=copy.deepcopy(app);newer['properties']['template']['containers'][0]['image']='new'
    newer['properties']['template']['revisionSuffix']='generated'
    assert deploy.invariants(app)==deploy.invariants(newer)
    for change in ['storage','scaling','identity']:
        altered=copy.deepcopy(newer)
        if change=='storage':altered['properties']['template']['containers'][0]['env'][0]['value']='sqlite'
        if change=='scaling':altered['properties']['template']['scale']['maxReplicas']=2
        if change=='identity':altered['identity']['userAssignedIdentities']={}
        assert deploy.invariants(app)!=deploy.invariants(altered)


def test_newer_failed_ci_cannot_be_hidden_by_an_older_success():
    run={'head_sha':'a'*40,'head_branch':'main','event':'push','conclusion':'success','path':'.github/workflows/ci.yml','id':1}
    assert not deploy.check_ci({'workflow_runs':[run,run|{'id':2,'conclusion':'failure'}]},'a'*40)
    assert not deploy.check_ci({'workflow_runs':[run,run|{'id':2,'conclusion':None}]},'a'*40)


def test_previous_ready_revision_cannot_satisfy_new_image_readiness():
    app={'properties':{'latestRevisionName':'old','latestReadyRevisionName':'old','provisioningState':'Succeeded'}}
    assert not deploy.revision_is_ready(app,'new')
    app['properties']['latestRevisionName']='new'
    assert not deploy.revision_is_ready(app,'new')
    app['properties']['latestReadyRevisionName']='new'
    assert deploy.revision_is_ready(app,'new')
    app['properties']['provisioningState']='Updating'
    assert not deploy.revision_is_ready(app,'new')


def test_studio_activation_changes_only_four_identity_settings_and_preserves_bounds():
    identity = dict(tenant_id='11111111-1111-4111-8111-111111111111',
                    api_client_id='22222222-2222-4222-8222-222222222222',
                    client_id='33333333-3333-4333-8333-333333333333')
    template={'containers':[{'image':'unchanged','env':[{'name':'COUNTERPRESS_STORAGE','value':'cosmos'},
        {'name':'COUNTERPRESS_EDITORIAL','value':'off'}]}], 'scale':{'minReplicas':0,'maxReplicas':1}}
    old=copy.deepcopy(template)
    enabled=deploy.studio_template(template,'enable',identity)
    assert template == old and enabled['scale'] == old['scale']
    env={v['name']:v['value'] for v in enabled['containers'][0]['env']}
    assert env['COUNTERPRESS_STUDIO']=='entra' and env['COUNTERPRESS_STORAGE']=='cosmos'
    assert env['COUNTERPRESS_EDITORIAL']=='off' and len(env)==6
    assert deploy.studio_template(enabled,'preserve')==enabled
    disabled=deploy.studio_template(enabled,'disable')
    assert disabled['containers'][0]['env']==[*template['containers'][0]['env'],{'name':'COUNTERPRESS_STUDIO','value':'off'}]


def test_studio_activation_rejects_unexpected_secrets_invalid_identity_and_active_ai():
    import pytest
    template={'containers':[{'env':[]}]}
    for identity in (None,{}, {'tenant_id':'bad','api_client_id':'bad','client_id':'bad'},
                     {'tenant_id':None,'api_client_id':None,'client_id':None}, {'api_key':'forbidden'}):
        with pytest.raises(deploy.DeploymentError):deploy.studio_template(template,'enable',identity)
    with pytest.raises(deploy.DeploymentError):deploy.studio_template(template,'unexpected')
    with pytest.raises(deploy.DeploymentError):
        deploy.studio_template({'containers':[{'env':[{'name':'COUNTERPRESS_EDITORIAL','value':'entra'}]}]},'disable')


def test_editorial_activation_keeps_model_values_out_of_environment_and_supports_disable():
    import pytest
    client = '33333333-3333-4333-8333-333333333333'
    app = {'properties': {'template': {'containers': [{'env': [
        {'name': 'COUNTERPRESS_STUDIO', 'value': 'entra'},
        {'name': 'COUNTERPRESS_STUDIO_CLIENT_ID', 'value': client},
        {'name': 'COUNTERPRESS_EDITORIAL', 'value': 'off'}]}]}, 'configuration': {'secrets': None}}}
    model = {'AZURE_OPENAI_ENDPOINT': 'https://'+'demo.openai.azure.com',
             'AZURE_OPENAI_DEPLOYMENT': 'test', 'AZURE_OPENAI_API_KEY': 'dummy'}
    original = copy.deepcopy(app)
    enabled = deploy.editorial_settings(app, 'enable', model)
    assert app == original
    env = {v['name']: v for v in enabled['properties']['template']['containers'][0]['env']}
    assert env['COUNTERPRESS_ENTRA_CLIENT_IDS']['value'] == client
    assert all(env[k] == {'name': k, 'secretRef': v} for k,v in deploy.MODEL_SECRETS.items())
    assert len(enabled['properties']['configuration']['secrets']) == 3
    disabled = deploy.editorial_settings(enabled, 'disable')
    names = {v['name'] for v in disabled['properties']['template']['containers'][0]['env']}
    assert not names & set(deploy.MODEL_SECRETS)
    assert deploy.editorial_settings(enabled, 'preserve') == enabled
    for bad in (None, {}, model | {'extra': 'no'}, model | {'AZURE_OPENAI_ENDPOINT': 'http://invalid.example'}):
        with pytest.raises(deploy.DeploymentError): deploy.editorial_settings(app, 'enable', bad)


def test_azure_null_secret_collection_is_equivalent_to_empty_list():
    app = {'identity': {}, 'properties': {'environmentId': 'test',
        'template': {'containers': [{'image': 'test', 'env': [
            {'name': 'COUNTERPRESS_STORAGE', 'value': 'cosmos'},
            {'name': 'COUNTERPRESS_STREAMING', 'value': 'azure'},
            {'name': 'COUNTERPRESS_TELEMETRY', 'value': 'on'}]}],
            'scale': {'minReplicas': 0, 'maxReplicas': 1}},
        'configuration': {'secrets': None, 'activeRevisionsMode': 'Single', 'ingress': {'allowInsecure': False}}}}
    deploy.validate_app(app)
    empty = copy.deepcopy(app); empty['properties']['configuration']['secrets'] = []
    assert deploy.invariants(app) == deploy.invariants(empty)


def test_footie_activation_reuses_only_existing_secret_references():
    import pytest
    app = {'properties': {'template': {'containers': [{'env': [
        {'name': name, 'secretRef': secret} for name, secret in deploy.MODEL_SECRETS.items()
    ]}]}}}
    original = copy.deepcopy(app)
    enabled = deploy.assistant_settings(app, 'enable')
    assert app == original
    env = enabled['properties']['template']['containers'][0]['env']
    assert env[:-1] == original['properties']['template']['containers'][0]['env']
    assert env[-1] == {'name': 'COUNTERPRESS_ASSISTANT_MODEL', 'value': 'azure'}
    assert deploy.assistant_settings(enabled, 'preserve') == enabled
    assert deploy.assistant_settings(enabled, 'disable')['properties']['template']['containers'][0]['env'][-1]['value'] == 'off'
    for bad in ([], [{'name': name, 'value': 'must-not-use-inline'} for name in deploy.MODEL_SECRETS]):
        with pytest.raises(deploy.DeploymentError):
            deploy.assistant_settings({'properties': {'template': {'containers': [{'env': bad}]}}}, 'enable')
    with pytest.raises(deploy.DeploymentError):
        deploy.assistant_settings(app, 'unknown')


def test_agent_activation_requires_shared_storage_and_supports_explicit_rollback():
    import pytest
    app = {'properties': {'template': {'containers': [{'image': 'same', 'env': [
        {'name': 'COUNTERPRESS_STORAGE', 'value': 'cosmos'},
        {'name': 'COUNTERPRESS_ASSISTANT_MODEL', 'value': 'azure'},
        {'name': 'AZURE_OPENAI_API_KEY', 'secretRef': 'existing'}]}]}}}
    original = copy.deepcopy(app)
    enabled = deploy.assistant_workflow_settings(app, 'agent')
    assert app == original
    assert enabled['properties']['template']['containers'][0]['env'][:-1] == app['properties']['template']['containers'][0]['env']
    assert deploy.assistant_workflow_settings(enabled, 'preserve') == enabled
    rollback = deploy.assistant_workflow_settings(enabled, 'structured_lookup')
    env = rollback['properties']['template']['containers'][0]['env']
    assert env[-1] == {'name': 'COUNTERPRESS_ASSISTANT_WORKFLOW', 'value': 'structured_lookup'}
    assert len(env) == 4
    for index, value in ((0, 'sqlite'), (1, 'off')):
        bad = copy.deepcopy(app)
        bad['properties']['template']['containers'][0]['env'][index]['value'] = value
        with pytest.raises(deploy.DeploymentError): deploy.assistant_workflow_settings(bad, 'agent')
    with pytest.raises(deploy.DeploymentError): deploy.assistant_workflow_settings(app, 'unknown')


def test_azure_empty_inline_field_keeps_secret_reference_guard_strict():
    import pytest
    app = {'identity': {}, 'properties': {'environmentId': 'test',
        'template': {'containers': [{'image': 'test', 'env': [
            {'name': 'COUNTERPRESS_STORAGE', 'value': 'cosmos'},
            {'name': 'COUNTERPRESS_STREAMING', 'value': 'azure'},
            {'name': 'COUNTERPRESS_TELEMETRY', 'value': 'on'},
            {'name': 'COUNTERPRESS_EDITORIAL', 'value': 'entra'},
            {'name': 'COUNTERPRESS_STUDIO', 'value': 'entra'},
            {'name': 'COUNTERPRESS_STUDIO_CLIENT_ID', 'value': 'test-client'},
            {'name': 'COUNTERPRESS_ENTRA_CLIENT_IDS', 'value': 'test-client'},
            *[{'name': name, 'secretRef': secret} for name, secret in deploy.MODEL_SECRETS.items()]]}],
            'scale': {'minReplicas': 0, 'maxReplicas': 1}},
        'configuration': {'secrets': [{'name': s} for s in deploy.MODEL_SECRETS.values()],
            'activeRevisionsMode': 'Single', 'ingress': {'allowInsecure': False}}}}
    for value in (None, ''):
        returned = copy.deepcopy(app)
        for item in returned['properties']['template']['containers'][0]['env']:
            if 'secretRef' in item: item['value'] = value
        original = copy.deepcopy(returned)
        deploy.validate_app(returned)
        deploy.validate_app(deploy.assistant_settings(returned, 'enable'))
        assert returned == original  # Validate the API representation; never rewrite secrets.
    for changes in ({'value': 'inline-canary'}, {'value': ' '}, {'value': False},
                    {'secretRef': 'unexpected'}, {'unexpected': ''}):
        bad = copy.deepcopy(returned)
        bad['properties']['template']['containers'][0]['env'][-1].update(changes)
        with pytest.raises(AssertionError): deploy.validate_app(bad)
        with pytest.raises(deploy.DeploymentError): deploy.assistant_settings(bad, 'enable')
