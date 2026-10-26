"""A keyless candidate cannot gain live traffic or broaden cleanup's contract."""
import copy

import pytest

from test_staging_guard import Cloud, PRODUCTION, CANDIDATE, RESTORED, IMAGE, staging


HISTORY = '/subscriptions/00000000-0000-4000-8000-000000000001/resourceGroups/test/providers/Microsoft.ManagedIdentity/userAssignedIdentities/counterpress-history'


def model_cloud():
    cloud = Cloud()
    cloud.value['id'] = HISTORY.split('/providers/')[0]+'/providers/Microsoft.App/containerApps/counterpress'
    identities = cloud.value['identity']['userAssignedIdentities']
    identities[HISTORY] = identities.pop('private-history-identity')
    container = cloud.value['properties']['template']['containers'][0]
    container['env'] = [e for e in container['env'] if e['name'] != 'COUNTERPRESS_ASSISTANT_MODEL'] + [
        {'name':'COUNTERPRESS_ASSISTANT_MODEL','value':'azure'},
        {'name':'AZURE_OPENAI_ENDPOINT','secretRef':'editorial-endpoint'},
        {'name':'AZURE_OPENAI_DEPLOYMENT','secretRef':'editorial-deployment'},
        {'name':'AZURE_OPENAI_API_KEY','secretRef':'editorial-key'},
    ]
    cloud.value['properties']['configuration']['secrets'] = [
        {'name':name} for name in ('editorial-key','editorial-endpoint','editorial-deployment')]
    cloud.rows[PRODUCTION] = cloud.row(PRODUCTION, cloud.value['properties']['template'])
    return cloud


def entries(template):return {e['name']:e for e in template['containers'][0]['env']}


def stage_identity(cloud):
    return staging.stage(cloud,IMAGE,'stage-456-1',model_authentication='managed_identity')


def test_identity_candidate_has_no_key_and_cleanup_restores_original_authentication():
    cloud=model_cloud(); before=cloud.app()
    assert stage_identity(cloud)==(PRODUCTION,CANDIDATE)
    candidate=entries(cloud.revision(CANDIDATE)['properties']['template'])
    assert 'AZURE_OPENAI_API_KEY' not in candidate
    assert candidate['AZURE_OPENAI_AUTH_MODE']['value']=='managed_identity'
    assert candidate['AZURE_OPENAI_MANAGED_IDENTITY_CLIENT_ID']['value']==candidate['COUNTERPRESS_COSMOS_CLIENT_ID']['value']
    assert candidate['COUNTERPRESS_STREAMING']['value']=='off'
    assert candidate['COUNTERPRESS_CAREER_STREAMING']['value']=='off'
    assert candidate['COUNTERPRESS_ASSISTANT_CALLS_PER_DAY']['value']=='400'
    assert staging.pinned(cloud.app(),PRODUCTION,CANDIDATE)
    assert cloud.revision(PRODUCTION)['properties']['template']==before['properties']['template']
    assert staging.application_value(cloud.app())==staging.application_value(before)
    staging.cleanup(cloud,PRODUCTION,CANDIDATE)
    assert staging.pinned(cloud.app(),RESTORED)
    assert staging.template_value(cloud.app()['properties']['template'])==staging.template_value(before['properties']['template'])
    assert 'AZURE_OPENAI_API_KEY' in entries(cloud.app()['properties']['template'])
    assert not cloud.revision(CANDIDATE)['properties']['active']
    for operation,payload in cloud.events:
        if operation=='patch':
            assert not {'identity','secrets'} & set(payload)
            for route in payload.get('configuration',{}).get('ingress',{}).get('traffic',[]):
                assert route.get('revisionName')!=CANDIDATE or route['weight']==0


def test_interrupted_identity_candidate_creation_has_a_valid_cleanup_path():
    cloud=model_cloud(); cloud.fail_template=True
    with pytest.raises(staging.DeploymentError):stage_identity(cloud)
    assert staging.pinned(cloud.app(),PRODUCTION)
    cloud.fail_template=False
    staging.cleanup(cloud,PRODUCTION,CANDIDATE)
    assert staging.pinned(cloud.app(),RESTORED)


@pytest.mark.parametrize('entry',[
    {'name':'AZURE_OPENAI_API_KEY','secretRef':'editorial-key'},
    {'name':'AZURE_OPENAI_MANAGED_IDENTITY_CLIENT_ID','value':'22222222-2222-4222-8222-222222222222'},
    {'name':'AZURE_OPENAI_AUTH_MODE','value':'automatic'},
    {'name':'COUNTERPRESS_ASSISTANT_CALLS_PER_DAY','value':'99999'},
    {'name':'UNREVIEWED_SETTING','value':'on'},
])
def test_cleanup_rejects_candidate_auth_or_unrelated_drift_before_mutating(entry):
    cloud=model_cloud(); stage_identity(cloud); cloud.events.clear()
    c=cloud.rows[CANDIDATE]['properties']['template']['containers'][0]
    c['env']=[e for e in c['env'] if e['name']!=entry['name']]+[entry]
    with pytest.raises(staging.DeploymentError,match='reviewed isolated template'):
        staging.cleanup(cloud,PRODUCTION,CANDIDATE)
    assert cloud.events==[]
    assert staging.pinned(cloud.app(),PRODUCTION,CANDIDATE)


def test_missing_history_identity_and_invalid_modes_stop_before_staging_mutations():
    cloud=model_cloud(); del cloud.value['identity']['userAssignedIdentities'][HISTORY]
    with pytest.raises(staging.DeploymentError):stage_identity(cloud)
    assert cloud.events==[]
    for mode in ('api_key','automatic',''):
        cloud=model_cloud()
        with pytest.raises(staging.DeploymentError):
            staging.stage(cloud,IMAGE,'stage-456-1',model_authentication=mode)
        assert cloud.events==[]


def test_preserve_candidate_and_cleanup_keep_an_already_keyless_production_keyless():
    cloud=model_cloud()
    cloud.value=staging.model_authentication_settings(cloud.value,'managed_identity')
    cloud.rows[PRODUCTION]=cloud.row(PRODUCTION,cloud.value['properties']['template'])
    before=copy.deepcopy(cloud.value['properties']['template'])
    staging.stage(cloud,IMAGE,'stage-456-1')
    staging.cleanup(cloud,PRODUCTION,CANDIDATE)
    assert staging.template_value(cloud.app()['properties']['template'])==staging.template_value(before)
    assert 'AZURE_OPENAI_API_KEY' not in entries(cloud.app()['properties']['template'])
