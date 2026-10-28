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


def test_configuration_patch_restores_known_private_values_without_changing_runtime():
    import pytest
    app = {'properties': {'template': {'containers': [{'env': [{'name': 'COUNTERPRESS_EDITORIAL', 'value': 'off'}]}]},
        'configuration': {'secrets': [{'name': name} for name in deploy.MODEL_SECRETS.values()] + [
            {'name': deploy.MONITOR_SECRET, 'value': 'already-prepared-monitoring'}]}}}
    model = {'AZURE_OPENAI_ENDPOINT': 'https://demo.openai.azure.com',
             'AZURE_OPENAI_DEPLOYMENT': 'test', 'AZURE_OPENAI_API_KEY': 'dummy'}
    original = copy.deepcopy(app)
    restored = deploy.rehydrate_configuration_secrets(app, model)
    assert app == original
    assert restored['properties']['template'] == app['properties']['template']
    values = {s['name']: s['value'] for s in restored['properties']['configuration']['secrets']}
    assert values == {**{name: model[key] for key, name in deploy.MODEL_SECRETS.items()},
                      deploy.MONITOR_SECRET: 'already-prepared-monitoring'}
    with pytest.raises(deploy.DeploymentError): deploy.rehydrate_configuration_secrets(app)
    for entry in ({'name': 'unexpected'}, {'name': 'editorial-key', 'keyVaultUrl': 'unreviewed'}):
        bad = copy.deepcopy(app); bad['properties']['configuration']['secrets'] = [entry]
        with pytest.raises(deploy.DeploymentError): deploy.rehydrate_configuration_secrets(bad, model)


def test_editorial_configuration_update_also_preserves_monitoring_secret():
    import pytest
    app = {'properties': {'template': {'containers': [{'env': []}]},
        'configuration': {'secrets': [{'name': deploy.MONITOR_SECRET}]}}}
    monitoring = {'COUNTERPRESS_AGENT_TRACING': 'azure',
        'APPLICATIONINSIGHTS_CONNECTION_STRING': 'InstrumentationKey=11111111-1111-4111-8111-111111111111;IngestionEndpoint=https://eastus.in.applicationinsights.azure.com/',
        'COUNTERPRESS_AGENT_TRACING_CLIENT_ID': '22222222-2222-4222-8222-222222222222',
        'COUNTERPRESS_AGENT_TRACE_SAMPLE_RATIO': '1.0'}
    restored = deploy.rehydrate_configuration_secrets(app, monitoring=monitoring)
    assert restored['properties']['template'] == app['properties']['template']
    assert restored['properties']['configuration']['secrets'][0]['value'] == monitoring['APPLICATIONINSIGHTS_CONNECTION_STRING']
    with pytest.raises(deploy.DeploymentError): deploy.rehydrate_configuration_secrets(app)


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
    with pytest.raises(deploy.DeploymentError): deploy.assistant_workflow_settings(enabled, 'structured_lookup')
    offline = deploy.assistant_settings(enabled, 'disable')
    rollback = deploy.assistant_workflow_settings(offline, 'structured_lookup')
    env = rollback['properties']['template']['containers'][0]['env']
    assert env[-1] == {'name': 'COUNTERPRESS_ASSISTANT_WORKFLOW', 'value': 'structured_lookup'}
    assert len(env) == 4
    multi = deploy.assistant_workflow_settings(app, 'multiagent')
    assert multi['properties']['template']['containers'][0]['env'][-1]['value'] == 'multiagent'
    for index, value in ((0, 'sqlite'), (1, 'off')):
        bad = copy.deepcopy(app)
        bad['properties']['template']['containers'][0]['env'][index]['value'] = value
        with pytest.raises(deploy.DeploymentError): deploy.assistant_workflow_settings(bad, 'agent')
        with pytest.raises(deploy.DeploymentError): deploy.assistant_workflow_settings(bad, 'multiagent')
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


def test_allowance_is_explicit_bounded_and_requires_durable_admission():
    import pytest
    app = {'properties': {'template': {'containers': [{'env': [
        {'name': 'COUNTERPRESS_STORAGE', 'value': 'cosmos'},
        {'name': 'COUNTERPRESS_ASSISTANT_WORKFLOW', 'value': 'multiagent'}]}]}}}
    original = copy.deepcopy(app)
    assert deploy.assistant_allowance_settings(app, 'preserve') == original
    raised = deploy.assistant_allowance_settings(app, 'pilot125')
    assert app == original
    env = {v['name']: v['value'] for v in raised['properties']['template']['containers'][0]['env']}
    assert env['COUNTERPRESS_ASSISTANT_CALLS_PER_HOUR'] == '120'
    assert env['COUNTERPRESS_ASSISTANT_CALLS_PER_DAY'] == '400'
    restored = deploy.assistant_allowance_settings(raised, 'conservative')
    assert next(v['value'] for v in restored['properties']['template']['containers'][0]['env']
                if v['name'] == 'COUNTERPRESS_ASSISTANT_CALLS_PER_HOUR') == '20'
    for bad in ('unlimited', '1000000'):
        with pytest.raises(deploy.DeploymentError): deploy.assistant_allowance_settings(app, bad)
    app['properties']['template']['containers'][0]['env'][0]['value'] = 'sqlite'
    with pytest.raises(deploy.DeploymentError): deploy.assistant_allowance_settings(app, 'pilot125')


def test_tracing_keeps_connection_private_and_preserves_other_runtime_settings():
    import pytest
    app = {'properties': {'template': {'containers': [{'env': [
        {'name': 'COUNTERPRESS_STORAGE', 'value': 'cosmos'}]}]},
        'configuration': {'secrets': [{'name': 'editorial-key'}]}}}
    settings = {'COUNTERPRESS_AGENT_TRACING': 'azure',
        'APPLICATIONINSIGHTS_CONNECTION_STRING': 'InstrumentationKey=11111111-1111-4111-8111-111111111111;IngestionEndpoint=https://eastus.in.applicationinsights.azure.com/',
        'COUNTERPRESS_AGENT_TRACING_CLIENT_ID': '22222222-2222-4222-8222-222222222222',
        'COUNTERPRESS_AGENT_TRACE_SAMPLE_RATIO': '1.0'}
    original = copy.deepcopy(app)
    enabled = deploy.agent_monitoring_settings(app, 'enable', settings)
    assert app == original
    env = {v['name']: v for v in enabled['properties']['template']['containers'][0]['env']}
    assert env['APPLICATIONINSIGHTS_CONNECTION_STRING'] == {'name': 'APPLICATIONINSIGHTS_CONNECTION_STRING', 'secretRef': deploy.MONITOR_SECRET}
    assert enabled['properties']['configuration']['secrets'][0] == {'name': 'editorial-key'}
    assert deploy.agent_monitoring_settings(enabled, 'preserve') == enabled
    disabled = deploy.agent_monitoring_settings(enabled, 'disable')
    assert disabled['properties']['template']['containers'][0]['env'] == [
        {'name': 'COUNTERPRESS_STORAGE', 'value': 'cosmos'}, {'name': 'COUNTERPRESS_AGENT_TRACING', 'value': 'off'}]
    for bad in (settings | {'unexpected': 'secret'}, settings | {'APPLICATIONINSIGHTS_CONNECTION_STRING': 'InstrumentationKey=bad'},
                settings | {'APPLICATIONINSIGHTS_CONNECTION_STRING': settings['APPLICATIONINSIGHTS_CONNECTION_STRING'].replace('eastus.in.applicationinsights.azure.com', 'untrusted.example')},
                settings | {'COUNTERPRESS_AGENT_TRACE_SAMPLE_RATIO': '0.5'}):
        with pytest.raises(deploy.DeploymentError): deploy.agent_monitoring_settings(app, 'enable', bad)


def career_bridge_app():
    history='11111111-1111-4111-8111-111111111111'
    stream='22222222-2222-4222-8222-222222222222'
    values={'COUNTERPRESS_STORAGE':'cosmos','COUNTERPRESS_STREAMING':'azure','COUNTERPRESS_TELEMETRY':'on',
        'COUNTERPRESS_COSMOS_DATABASE':'counterpress','COUNTERPRESS_COSMOS_CONTAINER':'histories',
        'COUNTERPRESS_COSMOS_ENDPOINT':'https://fixture.documents.azure.com:443/',
        'COUNTERPRESS_COSMOS_CLIENT_ID':history,'COUNTERPRESS_STREAM_CLIENT_ID':stream,
        'COUNTERPRESS_EVENTHUB_NAMESPACE':'fixture.servicebus.windows.net','COUNTERPRESS_EVENTHUB_NAME':'deliveries',
        'COUNTERPRESS_CHECKPOINT_ENDPOINT':'https://fixture.blob.core.windows.net/',
        'COUNTERPRESS_PUBSUB_ENDPOINT':'https://fixture.webpubsub.azure.com',
        'COUNTERPRESS_ASSISTANT_CALLS_PER_HOUR':'120','COUNTERPRESS_ASSISTANT_CALLS_PER_DAY':'400'}
    return {'identity':{'userAssignedIdentities':{'history':{'clientId':history},'stream':{'clientId':stream}}},
        'properties':{'environmentId':'unchanged','configuration':{'secrets':[],
            'activeRevisionsMode':'Single','ingress':{'allowInsecure':False}},
            'template':{'containers':[{'image':'unchanged','env':[{'name':k,'value':v} for k,v in values.items()]}],
                'scale':{'minReplicas':0,'maxReplicas':1,'rules':[{'name':'existing-checkpoint-rule'}]}}}}


def test_career_bridge_only_toggles_activation_and_preserves_existing_resources():
    app=career_bridge_app();original=copy.deepcopy(app)
    assert deploy.career_streaming_settings(app,'preserve')==original
    enabled=deploy.career_streaming_settings(app,'enable')
    assert app==original
    deploy.validate_app(enabled)
    env=enabled['properties']['template']['containers'][0]['env']
    assert env[-1]=={'name':'COUNTERPRESS_CAREER_STREAMING','value':'on'}
    comparable=copy.deepcopy(enabled);comparable['properties']['template']['containers'][0]['env'].pop()
    assert comparable==original  # Includes identities, limits, checkpoint rules and secrets.
    assert deploy.career_streaming_settings(enabled,'enable')==enabled
    disabled=deploy.career_streaming_settings(enabled,'disable')
    assert disabled['properties']['template']['containers'][0]['env'][-1]['value']=='off'
    assert disabled['properties']['configuration']==original['properties']['configuration']


def test_career_bridge_rejects_missing_changed_or_secret_reference_prerequisites():
    import pytest
    original=career_bridge_app()
    for key,bad_value in (
        ('COUNTERPRESS_STORAGE','sqlite'),('COUNTERPRESS_STREAMING','off'),
        ('COUNTERPRESS_COSMOS_DATABASE','other'),('COUNTERPRESS_COSMOS_CONTAINER','other'),
        ('COUNTERPRESS_COSMOS_ENDPOINT','https://untrusted.example'),
        ('COUNTERPRESS_COSMOS_ENDPOINT','https://fixture.documents.azure.com/?private=secret'),
        ('COUNTERPRESS_COSMOS_ENDPOINT','https://fixture.documents.azure.com:8443/'),
        ('COUNTERPRESS_CHECKPOINT_ENDPOINT','http://fixture.blob.core.windows.net'),
        ('COUNTERPRESS_PUBSUB_ENDPOINT','https://fixture.webpubsub.azure.com/unreviewed'),
        ('COUNTERPRESS_EVENTHUB_NAME','other'),('COUNTERPRESS_EVENTHUB_NAMESPACE','unreviewed'),
        ('COUNTERPRESS_COSMOS_CLIENT_ID','33333333-3333-4333-8333-333333333333'),
        ('COUNTERPRESS_STREAM_CLIENT_ID','invalid'),
    ):
        app=copy.deepcopy(original)
        next(e for e in app['properties']['template']['containers'][0]['env'] if e['name']==key)['value']=bad_value
        with pytest.raises(deploy.DeploymentError,match='existing reviewed'):
            deploy.career_streaming_settings(app,'enable')
    for key in ('COUNTERPRESS_COSMOS_CLIENT_ID','COUNTERPRESS_STREAM_CLIENT_ID','COUNTERPRESS_PUBSUB_ENDPOINT'):
        app=copy.deepcopy(original)
        entry=next(e for e in app['properties']['template']['containers'][0]['env'] if e['name']==key)
        entry.pop('value');entry['secretRef']='not-reviewed'
        with pytest.raises(deploy.DeploymentError):deploy.career_streaming_settings(app,'enable')


def test_career_bridge_rejects_shared_index_duplicate_env_and_changed_runtime_bounds():
    import pytest
    for issue in ('disk-index','duplicate-env','missing-identity','multiple-containers','multiple-revisions','scaling'):
        app=career_bridge_app();template=app['properties']['template'];env=template['containers'][0]['env']
        if issue=='disk-index':env.append({'name':'COUNTERPRESS_PROFILE_DB_PATH','value':'/shared/profile.sqlite3'})
        elif issue=='duplicate-env':env.append(copy.deepcopy(env[0]))
        elif issue=='missing-identity':app['identity']['userAssignedIdentities']={}
        elif issue=='multiple-containers':template['containers'].append(copy.deepcopy(template['containers'][0]))
        elif issue=='multiple-revisions':app['properties']['configuration']['activeRevisionsMode']='Multiple'
        elif issue=='scaling':template['scale']['maxReplicas']=2
        with pytest.raises(deploy.DeploymentError):deploy.career_streaming_settings(app,'enable')
    with pytest.raises(deploy.DeploymentError):deploy.career_streaming_settings(career_bridge_app(),'unknown')


def test_career_bridge_enabled_configuration_is_revalidated_on_later_releases():
    import pytest
    app=deploy.career_streaming_settings(career_bridge_app(),'enable')
    app['identity']['userAssignedIdentities']={}
    with pytest.raises(deploy.DeploymentError):deploy.validate_app(app)
    app=career_bridge_app()
    app['properties']['template']['containers'][0]['env'].append({'name':'COUNTERPRESS_CAREER_STREAMING','value':'unexpected'})
    with pytest.raises(AssertionError):deploy.validate_app(app)


def test_production_stream_scopes_accept_absent_or_explicit_defaults_without_changes():
    defaults = {
        'COUNTERPRESS_PUBSUB_HUB': 'counterpress',
        'COUNTERPRESS_CHECKPOINT_CONTAINER': 'eventhub-checkpoints',
        'COUNTERPRESS_QUARANTINE_CONTAINER': 'rejected-deliveries',
    }
    for explicit in (False, True):
        app = career_bridge_app()
        if explicit:
            app['properties']['template']['containers'][0]['env'].extend(
                {'name': name, 'value': value} for name, value in defaults.items())
        original = copy.deepcopy(app)
        deploy.validate_app(app)
        deploy.validate_career_streaming_prerequisites(app)
        assert app == original


def test_production_stream_scopes_reject_verifier_or_ambiguous_overrides_even_when_off():
    import pytest
    defaults = {
        'COUNTERPRESS_PUBSUB_HUB': ('counterpress', 'counterpress_phase4'),
        'COUNTERPRESS_CHECKPOINT_CONTAINER': ('eventhub-checkpoints', 'eventhub-checkpoints-phase4'),
        'COUNTERPRESS_QUARANTINE_CONTAINER': ('rejected-deliveries', 'rejected-deliveries-phase4'),
    }
    for name, (default, isolated) in defaults.items():
        for overrides in (
            [{'name': name, 'value': isolated}],
            [{'name': name, 'value': ''}],
            [{'name': name, 'value': None}],
            [{'name': name, 'secretRef': 'unreviewed'}],
            [{'name': name, 'value': default, 'secretRef': 'unreviewed'}],
            [{'name': name, 'value': isolated}, {'name': name, 'value': default}],
            [{'name': name, 'value': default}, {'name': name, 'value': default}],
        ):
            for bridge in ('off', 'on'):
                app = career_bridge_app()
                app['properties']['template']['containers'][0]['env'].extend([
                    {'name': 'COUNTERPRESS_CAREER_STREAMING', 'value': bridge}, *overrides])
                for validate in (deploy.validate_app, deploy.validate_career_streaming_prerequisites):
                    with pytest.raises(deploy.DeploymentError, match='reviewed defaults'):
                        validate(app)


def test_warm_replica_is_accepted_preserved_and_not_silently_changed():
    app = career_bridge_app()
    app['properties']['template']['scale']['minReplicas'] = 1
    before = copy.deepcopy(app)
    deploy.validate_app(app)
    enabled = deploy.career_streaming_settings(app, 'enable')
    deploy.validate_app(enabled)
    assert app == before
    assert enabled['properties']['template']['scale'] == before['properties']['template']['scale']
    changed = copy.deepcopy(app)
    changed['properties']['template']['scale']['minReplicas'] = 0
    assert deploy.invariants(changed) != deploy.invariants(app)


def test_replica_minimum_rejects_unreviewed_bounds_and_nonintegers():
    import pytest
    for minimum in (-1, 2, None, '1', True, 1.0):
        app = career_bridge_app()
        app['properties']['template']['scale']['minReplicas'] = minimum
        with pytest.raises(AssertionError):
            deploy.validate_app(app)
        with pytest.raises(deploy.DeploymentError):
            deploy.validate_career_streaming_prerequisites(app)
