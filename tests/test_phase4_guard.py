"""Offline isolation guard checks; no Azure/network clients are invoked."""
import copy
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
try:
    spec=importlib.util.spec_from_file_location('phase4_azure',ROOT/'scripts/phase4_azure.py')
    phase4=importlib.util.module_from_spec(spec);spec.loader.exec_module(phase4)
finally:sys.path.pop(0)

IMAGE='sha256:'+'a'*64
BASE='/subscriptions/11111111-1111-4111-8111-111111111111/resourceGroups/counterpress-dev'
CLIENT='22222222-2222-4222-8222-222222222222'


def bundle():
    b={'base':BASE,'app':BASE+'/providers/Microsoft.App/containerApps/counterpress-phase4',
       'identity':BASE+'/providers/Microsoft.ManagedIdentity/userAssignedIdentities/counterpress-phase4',
       'cosmos':BASE+'/providers/Microsoft.DocumentDB/databaseAccounts/cp-test',
       'hub':BASE+'/providers/Microsoft.EventHub/namespaces/cp-test/eventhubs/deliveries-phase4',
       'pubsub':BASE+'/providers/Microsoft.SignalRService/webPubSub/cp-test',
       'environment':BASE+'/providers/Microsoft.App/managedEnvironments/counterpress-env',
       'registry':'test.azurecr.io','pull':BASE+'/providers/Microsoft.ManagedIdentity/userAssignedIdentities/counterpress-pull',
       'endpoints':{'COUNTERPRESS_COSMOS_ENDPOINT':'https://test.documents.azure.com:443/',
                    'COUNTERPRESS_EVENTHUB_NAMESPACE':'test.servicebus.windows.net',
                    'COUNTERPRESS_CHECKPOINT_ENDPOINT':'https://test.blob.core.windows.net/',
                    'COUNTERPRESS_PUBSUB_ENDPOINT':'https://test.webpubsub.azure.com'}}
    b['journal']=b['cosmos']+'/sqlDatabases/counterpress/containers/histories-phase4'
    b['cosmos_scope']=b['cosmos']+'/dbs/counterpress/colls/histories-phase4'
    for key,name in (('checkpoint','eventhub-checkpoints-phase4'),('quarantine','rejected-deliveries-phase4')):
        b[key]=BASE+'/providers/Microsoft.Storage/storageAccounts/test/blobServices/default/containers/'+name
    return b


def fixture():
    b=bundle();identity={'id':b['identity'],'tags':{'purpose':'footie-phase4'},'properties':{'clientId':CLIENT,'principalId':'principal'}}
    env={**phase4.FIXED_ENV,**b['endpoints'],**{k:CLIENT for k in ('COUNTERPRESS_COSMOS_CLIENT_ID','COUNTERPRESS_STREAM_CLIENT_ID','COUNTERPRESS_FEED_CLIENT_ID')}}
    app={'id':b['app'],'tags':{'purpose':'footie-phase4'},'identity':{'userAssignedIdentities':{b['pull']:{},b['identity']:{}}},
         'properties':{'environmentId':b['environment'],'workloadProfileName':'Consumption',
             'configuration':{'activeRevisionsMode':'Single','secrets':[],
                 'ingress':{'external':True,'targetPort':8000,'allowInsecure':False},
                 'registries':[{'server':b['registry'],'identity':b['pull']}]},
             'template':{'containers':[{'name':phase4.APP,'image':b['registry']+'/counterpress@'+IMAGE,
                 'command':phase4.COMMAND,'args':phase4.ARGS,'resources':{'cpu':0.5,'memory':'1Gi'},
                 'env':[{'name':k,'value':v} for k,v in env.items()]}],
                 'scale':{'minReplicas':0,'maxReplicas':1,'rules':[{'name':'http','http':{'metadata':{'concurrentRequests':'10'}}},
                     {'name':'eventhub-phase4','custom':{'identity':b['identity'],'type':'azure-eventhub','metadata':{
                         'eventHubNamespace':'test','eventHubName':'deliveries-phase4','consumerGroup':'$Default',
                         'storageAccountName':'test','blobContainer':'eventhub-checkpoints-phase4','checkpointStrategy':'blobMetadata',
                         'unprocessedEventThreshold':'1','activationUnprocessedEventThreshold':'0'}}}]}}}}
    return app,b,identity


def test_complete_isolated_bundle_and_azure_empty_metadata_are_accepted_without_mutation():
    app,b,identity=fixture();before=copy.deepcopy(app)
    assert phase4.validate_test_app(app,b,identity,IMAGE)
    assert app==before
    app['properties']['configuration']['registries'][0].update(username=None,passwordSecretRef='')
    app['properties']['template']['containers'][0]['env'][0]['secretRef']=None
    assert phase4.validate_test_app(app,b,identity,IMAGE)


@pytest.mark.parametrize('key,value',[
    ('COUNTERPRESS_COSMOS_CONTAINER','histories'),('COUNTERPRESS_COSMOS_DATABASE','other'),
    ('COUNTERPRESS_EVENTHUB_NAME','deliveries'),('COUNTERPRESS_PUBSUB_HUB','counterpress'),
    ('COUNTERPRESS_CHECKPOINT_CONTAINER','eventhub-checkpoints'),('COUNTERPRESS_QUARANTINE_CONTAINER','rejected-deliveries'),
    ('COUNTERPRESS_COSMOS_CLIENT_ID','production-identity'),('COUNTERPRESS_FEED_CLIENT_ID','production-identity'),
    ('COUNTERPRESS_ASSISTANT_MODEL','azure'),('COUNTERPRESS_EDITORIAL','entra'),
    ('COUNTERPRESS_COSMOS_AUTH','azure-cli'),('COUNTERPRESS_PROFILE_DB_PATH','/shared/index.db'),
    ('COUNTERPRESS_COSMOS_ENDPOINT','https://other.documents.azure.com'),
    ('COUNTERPRESS_EVENTHUB_NAMESPACE','other.servicebus.windows.net'),
])
def test_every_mixed_production_test_bundle_is_rejected(key,value):
    app,b,i=fixture();env=app['properties']['template']['containers'][0]['env']
    next(e for e in env if e['name']==key)['value']=value
    with pytest.raises(phase4.DeploymentError):phase4.validate_test_app(app,b,i,IMAGE)


@pytest.mark.parametrize('issue',['extra-env','secret','default-app','extra-identity','wrong-registry','mutable-image','public-factory','scaling','consumer','checkpoint','mode'])
def test_runtime_drift_cannot_pass_isolation_proof(issue):
    app,b,i=fixture();p=app['properties'];c=p['template']['containers'][0]
    if issue=='extra-env':c['env'].append({'name':'AZURE_OPENAI_API_KEY','value':'canary'})
    elif issue=='secret':p['configuration']['secrets']=[{'name':'unreviewed'}]
    elif issue=='default-app':app['id']=app['id'].removesuffix('-phase4')
    elif issue=='extra-identity':app['identity']['userAssignedIdentities']['production-history']={}
    elif issue=='wrong-registry':p['configuration']['registries'][0]['server']='other.azurecr.io'
    elif issue=='mutable-image':c['image']='test.azurecr.io/counterpress:latest'
    elif issue=='public-factory':c['args']=['counterpress.api.main:app']
    elif issue=='scaling':p['template']['scale']['maxReplicas']=2
    elif issue=='consumer':p['template']['scale']['rules'][1]['custom']['metadata']['eventHubName']='deliveries'
    elif issue=='checkpoint':p['template']['scale']['rules'][1]['custom']['metadata']['blobContainer']='eventhub-checkpoints'
    elif issue=='mode':p['configuration']['activeRevisionsMode']='Multiple'
    with pytest.raises(phase4.DeploymentError):phase4.validate_test_app(app,b,i,IMAGE)


def test_preview_and_cleanup_targets_never_allow_shared_parent_or_production_resources():
    b=bundle()
    for key in ('app','identity','journal','hub','checkpoint','quarantine'):
        assert phase4.allowed_target(b[key],b)
    for bad in (b['base'],b['cosmos'],b['pubsub'],b['environment'],b['pull'],
                b['app'].removesuffix('-phase4'),b['journal'].removesuffix('-phase4'),b['hub'].removesuffix('-phase4')):
        assert not phase4.allowed_target(bad,b)
        with pytest.raises(phase4.DeploymentError):phase4.check_what_if({'changes':[{'resourceId':bad,'changeType':'Modify'}]},b)
    role=phase4.cleanup_manifest(b)[2]
    assert phase4.allowed_target(role,b)
    assert phase4.check_what_if({'changes':[{'resourceId':role,'changeType':'Create'}]},b)=={'Create':1}
    for kind in ('Modify','Delete','Deploy'):
        with pytest.raises(phase4.DeploymentError):phase4.check_what_if({'changes':[{'resourceId':role,'changeType':kind}]},b)


def test_identity_proof_rejects_extra_permissions_and_wrong_cosmos_scope(monkeypatch):
    app,b,i=fixture()
    roles=[{'id':'role-'+str(n),'principalId':'principal','scope':scope,'roleDefinitionId':'/roles/'+rid}
        for n,(scope,rid) in enumerate(((b['hub'],phase4.ROLE_IDS['receiver']),(b['hub'],phase4.ROLE_IDS['sender']),
             (b['checkpoint'],phase4.ROLE_IDS['blob']),(b['quarantine'],phase4.ROLE_IDS['blob']),(b['pubsub'],phase4.ROLE_IDS['pubsub'])))]
    assignment={'id':'cosmos-role','properties':{'principalId':'principal','scope':b['cosmos_scope'],'roleDefinitionId':'/role'}}
    definition={'properties':{'permissions':[{'dataActions':['Microsoft.DocumentDB/databaseAccounts/readMetadata',
        *['Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers/items/'+x for x in ('read','create','replace')]]}]}}
    def fake(*args,**kwargs):
        if args[0]=='role':return roles
        if 'sqlRoleAssignments?' in args[-1]:return {'value':[assignment]}
        return definition
    monkeypatch.setattr(phase4,'az',fake)
    assert len(phase4.verify_access(b,i))==6
    for role in roles:
        role['scope']=role['scope'].upper();role['roleDefinitionId']=role['roleDefinitionId'].upper()
    assignment['properties']['scope']=b['cosmos'].upper()+'/dbs/counterpress/colls/histories-phase4'
    assert len(phase4.verify_access(b,i))==6
    assignment['properties']['scope']=b['cosmos_scope'].upper()
    with pytest.raises(phase4.DeploymentError):phase4.verify_access(b,i)
    assignment['properties']['scope']=b['cosmos_scope']
    roles.append({'id':'broad','principalId':'principal','scope':BASE,'roleDefinitionId':'/roles/owner'})
    with pytest.raises(phase4.DeploymentError):phase4.verify_access(b,i)
    roles.pop();assignment['properties']['scope']=b['cosmos']+'/dbs/counterpress/colls/histories'
    with pytest.raises(phase4.DeploymentError):phase4.verify_access(b,i)


def test_workflow_is_main_only_ci_gated_build_without_deployment_or_added_privileges():
    text=(ROOT/'.github/workflows/phase4.yml').read_text()
    assert "github.ref == 'refs/heads/main'" in text and 'group: counterpress-azure-deployment' in text
    assert 'environment: azure-demo' in text and 'timeout-minutes: 20' in text
    assert 'deploy_azure.py check-ci' in text and 'phase4_azure.py publish' in text
    assert 'phase4_azure.py deploy' not in text and 'role assignment' not in text
    assert 'CP_EDITORIAL_MODEL' not in text and 'upload-artifact' not in text
    assert '--network none --read-only' in text


def test_template_uses_only_existing_service_tiers_and_no_model_secrets():
    text=(ROOT/'infra/phase4.bicep').read_text()
    for value in phase4.FIXED_ENV.values():assert value in text
    assert "counterpress.api.phase4:create_app" in text and 'secrets: []' in text
    assert 'AZURE_OPENAI' not in text and 'useEditorial' not in text
    assert "maxReplicas: 1" in text and "minReplicas: 0" in text
    assert 'output cleanupIds array' in text


def test_only_exact_deterministic_assignment_ids_are_allowed():
    b=bundle();ids=phase4.cleanup_manifest(b)
    assert len(ids)==len(set(ids))==12
    assert ids[0]==b['app'] and ids[-1]==b['identity']
    for key in ('pubsub','hub','checkpoint'):
        arbitrary=b[key]+'/providers/Microsoft.Authorization/roleAssignments/33333333-3333-4333-8333-333333333333'
        assert not phase4.allowed_target(arbitrary,b)
    assert not phase4.allowed_target(b['cosmos']+'/sqlRoleAssignments/33333333-3333-4333-8333-333333333333',b)
    bad={'resourceId':ids[2],'changeType':'Create','after':{'properties':{'roleDefinitionId':'/roles/owner'}}}
    with pytest.raises(phase4.DeploymentError):phase4.check_what_if({'changes':[bad]},b)


def test_fresh_plan_rejects_any_preexisting_test_resource_or_assignment(monkeypatch):
    b=bundle()
    for existing in phase4.cleanup_manifest(b):
        monkeypatch.setattr(phase4,'read_target',lambda resource,bundle: {} if resource==existing else None)
        with pytest.raises(phase4.DeploymentError):phase4.require_fresh_targets(b)
    monkeypatch.setattr(phase4,'read_target',lambda *args:None)
    phase4.require_fresh_targets(b)


def test_cleanup_of_partial_create_is_safe_resumable_and_checks_every_role_owner(monkeypatch):
    from argparse import Namespace
    app,b,i=fixture();expires='2026-10-26T04:00:00+00:00'
    app['tags']['expiresOn']=expires;i['tags']['expiresOn']=expires
    ids=phase4.cleanup_manifest(b)
    state={'cleanup_ids':ids,'absent_targets':ids,'deploy_attempted':True,
           'expires_on':expires,'image_digest':IMAGE}
    resources={b['identity']:i,ids[2]:{'properties':{'principalId':'principal'}},b['hub']:{'id':b['hub']}}
    deleted=[];saved=[]
    monkeypatch.setattr(phase4,'read_target',lambda resource,bundle:resources.get(resource))
    monkeypatch.setattr(phase4,'ensure_production',lambda s:None)
    monkeypatch.setattr(phase4,'require_terminal_deployment',lambda s:None)
    monkeypatch.setattr(phase4,'private_file',lambda path,s:saved.append(copy.deepcopy(s)))
    def remove(*args,**kwargs):
        rid=args[args.index('--url')+1].split('?')[0];deleted.append(rid);resources.pop(rid,None)
    monkeypatch.setattr(phase4,'az',remove)
    args=Namespace(apply=True,discard_test_data=True,state='/private/tmp/unit-test-unused.json')
    # Foreign principal blocks even on a resumed cleanup; do not trust only receipt IDs.
    state['cleanup_started']=True;state['cleanup_pending']=list(ids)
    resources[ids[2]]['properties']['principalId']='foreign'
    with pytest.raises(phase4.DeploymentError):phase4.cleanup(state,b,args)
    assert not deleted
    resources[ids[2]]['properties']['principalId']='principal'
    phase4.cleanup(state,b,args)
    assert deleted==[ids[2],b['hub'],b['identity']]
    assert state['cleanup_pending']==[] and resources=={}
    phase4.cleanup(state,b,args)  # completed receipt remains idempotent
    assert len(deleted)==3


def test_receipt_cannot_replace_role_ids_or_skip_initial_absence_proof(monkeypatch):
    from argparse import Namespace
    b=bundle();ids=phase4.cleanup_manifest(b)
    monkeypatch.setattr(phase4,'require_terminal_deployment',lambda s:None)
    args=Namespace(apply=True,discard_test_data=True,state='/private/tmp/unused.json')
    state={'cleanup_ids':ids,'absent_targets':ids,'deploy_attempted':True}
    for bad in (state|{'absent_targets':[]},state|{'deploy_attempted':False},
                state|{'cleanup_ids':ids[:-1]+[b['pull']]}):
        with pytest.raises(phase4.DeploymentError):phase4.cleanup(bad,b,args)


def test_plan_binds_build_commit_digest_and_deploy_rechecks_template_bytes():
    text=(ROOT/'scripts/phase4_azure.py').read_text()
    assert "'--image','counterpress:phase4-'+args.commit" in text
    assert "found['digest']==args.image_digest" in text
    assert "'build_commit':args.commit" in text
    assert "state.get('template_sha256')==template_digest()" in text
    assert "state['deploy_attempted']=True;private_file(args.state,state)" in text


def test_cleanup_waits_for_terminal_matching_arm_deployment(monkeypatch):
    state={'image_digest':IMAGE,'expires_on':'future','location':'region'}
    properties={'provisioningState':'Succeeded','parameters':{
        'imageDigest':{'value':IMAGE},'expiresOn':{'value':'future'},'location':{'value':'region'}}}
    monkeypatch.setattr(phase4,'az',lambda *args,**kwargs:{'properties':properties})
    for status in ('Succeeded','Failed','Canceled'):
        properties['provisioningState']=status;phase4.require_terminal_deployment(state)
    for status in ('Running','Accepted','Deleting',None):
        properties['provisioningState']=status
        with pytest.raises(phase4.DeploymentError):phase4.require_terminal_deployment(state)
    properties['provisioningState']='Succeeded';properties['parameters']['imageDigest']['value']='another-deployment'
    with pytest.raises(phase4.DeploymentError):phase4.require_terminal_deployment(state)
    monkeypatch.setattr(phase4,'az',lambda *args,**kwargs:None)
    with pytest.raises(phase4.DeploymentError):phase4.require_terminal_deployment(state)


def test_resource_absence_uses_exact_observed_azure_code_not_message_substrings(monkeypatch):
    from types import SimpleNamespace
    for code in ('ResourceNotFound','NotFound','RoleAssignmentNotFound','DeploymentNotFound','EntityNotFound','ContainerNotFound'):
        stderr=f'ERROR: ({code}) Private details omitted.\nCode: {code}\nMessage: Missing resource.\n'
        assert phase4.missing_resource_error(stderr)
        monkeypatch.setattr(phase4.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=3,stdout='',stderr=stderr))
        assert phase4.az('resource','show',missing=True) is None
        with pytest.raises(phase4.DeploymentError):phase4.az('resource','show')
    for stderr in (
        'ERROR: (AuthorizationFailed) Cannot read RoleAssignmentNotFound.\nCode: AuthorizationFailed\n',
        'ERROR: (BadRequest) Expected ResourceNotFound but request invalid.',
        'ERROR: (NotFound) Ambiguous wrapper.\nCode: AuthorizationFailed\n',
        'ERROR: Connection failed while checking ResourceNotFound.',
        'ERROR: (ResourceNotFoundUnexpected) Something failed.',
    ):
        assert not phase4.missing_resource_error(stderr)
        monkeypatch.setattr(phase4.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=3,stdout='',stderr=stderr))
        with pytest.raises(phase4.DeploymentError):phase4.az('resource','show',missing=True)


def test_preview_requests_machine_readable_what_if(monkeypatch):
    b=bundle();calls=[]
    state={'image_digest':IMAGE,'expires_on':'future','location':'region'}
    def fake(*args,**kwargs):
        calls.append(args)
        return {'changes':[{'resourceId':resource,'changeType':'Create'} for resource in phase4.cleanup_manifest(b)]}
    monkeypatch.setattr(phase4,'az',fake)
    monkeypatch.setattr(phase4,'ensure_production',lambda s:None)
    assert phase4.preview(None,state,b)=={'Create':12}
    assert '--no-pretty-print' in calls[0]


def test_arm_id_casing_is_accepted_but_different_resources_are_rejected():
    app,b,i=fixture()
    app['id']=app['id'].upper();i['id']=i['id'].upper()
    p=app['properties'];p['environmentId']=p['environmentId'].upper()
    p['configuration']['registries'][0]['identity']=b['pull'].upper()
    app['identity']['userAssignedIdentities']={key.upper():value for key,value in app['identity']['userAssignedIdentities'].items()}
    p['template']['scale']['rules'][1]['custom']['identity']=b['identity'].upper()
    assert phase4.validate_test_app(app,b,i,IMAGE)
    for key in ('app','identity','hub','journal','checkpoint','quarantine'):
        assert phase4.allowed_target(b[key].upper(),b)
        assert phase4.resource_version(b[key].upper(),b)==phase4.resource_version(b[key],b)
        assert not phase4.allowed_target(b[key].upper()+'-OTHER',b)
    p['environmentId']+='-OTHER'
    with pytest.raises(phase4.DeploymentError):phase4.validate_test_app(app,b,i,IMAGE)
    p['environmentId']=b['environment'];i['id']+='-OTHER'
    with pytest.raises(phase4.DeploymentError):phase4.validate_test_app(app,b,i,IMAGE)


def test_preview_role_and_cosmos_checks_cannot_be_bypassed_by_arm_id_casing():
    b=bundle();ids=phase4.cleanup_manifest(b)
    def preview(rid,props):return {'changes':[{'resourceId':rid.upper(),'changeType':'Create','after':{'properties':props}}]}
    assert phase4.check_what_if(preview(ids[2],{'roleDefinitionId':'/roles/'+phase4.ROLE_IDS['receiver'].upper()}),b)=={'Create':1}
    with pytest.raises(phase4.DeploymentError):phase4.check_what_if(preview(ids[2],{'roleDefinitionId':'/roles/owner'}),b)
    scope=b['cosmos'].upper()+'/dbs/counterpress/colls/histories-phase4'
    assert phase4.check_what_if(preview(ids[1],{'scope':scope}),b)=={'Create':1}
    for bad in (scope.upper(),scope.replace('histories-phase4','histories'),scope.replace('CP-TEST','OTHER')):
        with pytest.raises(phase4.DeploymentError):phase4.check_what_if(preview(ids[1],{'scope':bad}),b)


def test_compiled_cleanup_outputs_do_not_reference_resource_copy_indices(tmp_path):
    """Reproduce the ARM output-evaluation bug after actual Bicep lowering."""
    import os
    import shutil
    import subprocess
    binary=shutil.which('bicep') or str(Path.home()/'.azure/bin/bicep')
    if not Path(binary).is_file():pytest.skip('Bicep compiler not installed')
    output=tmp_path/'phase4.json'
    env={**os.environ,'DOTNET_BUNDLE_EXTRACT_BASE_DIR':str(tmp_path/'dotnet')}
    subprocess.run([binary,'build',str(ROOT/'infra/phase4.bicep'),'--outfile',str(output)],check=True,capture_output=True,env=env)
    template=json.loads(output.read_text());ids=template['outputs']['cleanupIds']['value']
    assert len(ids)==12
    assert 'copyindex(' not in json.dumps(template['outputs']).lower()
    assert ids[8]=="[variables('checkpointId')]" and ids[9]=="[variables('quarantineId')]"
    for name,destination in (('checkpointId','eventhub-checkpoints-phase4'),('quarantineId','rejected-deliveries-phase4')):
        assert destination in template['variables'][name]
        assert 'copyindex(' not in template['variables'][name].lower()
    # Role resources must retain their resource copy loop; only output lowering changes.
    assert any(resource.get('copy',{}).get('name')=='blobRoles' for resource in template['resources'])
