"""Offline staging state-machine checks. These tests never access Azure."""
import copy
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
try:
    spec = importlib.util.spec_from_file_location('stage_azure',ROOT/'scripts/stage_azure.py')
    staging = importlib.util.module_from_spec(spec);spec.loader.exec_module(staging)
finally:sys.path.pop(0)

PRODUCTION = 'counterpress--gh-123-1'
CANDIDATE = 'counterpress--stage-456-1'
RESTORED = 'counterpress--restore-456-1'
IMAGE = 'privatecanary.azurecr.io/counterpress@sha256:'+'b'*64


def fixture():
    history_client = '11111111-1111-4111-8111-111111111111'
    stream_client = '22222222-2222-4222-8222-222222222222'
    env = [dict(name=k,value=v) for k,v in {
        'COUNTERPRESS_STORAGE':'cosmos','COUNTERPRESS_STREAMING':'azure',
        'COUNTERPRESS_CAREER_STREAMING':'on','COUNTERPRESS_TELEMETRY':'on',
        'COUNTERPRESS_ASSISTANT_MODEL':'off','COUNTERPRESS_ASSISTANT_WORKFLOW':'multiagent',
        'COUNTERPRESS_ASSISTANT_CALLS_PER_HOUR':'120','COUNTERPRESS_ASSISTANT_CALLS_PER_DAY':'400',
        'COUNTERPRESS_COSMOS_ENDPOINT':'https://privatecanary.documents.azure.com:443/',
        'COUNTERPRESS_COSMOS_DATABASE':'counterpress',
        'COUNTERPRESS_COSMOS_CONTAINER':'histories',
        'COUNTERPRESS_COSMOS_CLIENT_ID':history_client,
        'COUNTERPRESS_STREAM_CLIENT_ID':stream_client,
        'COUNTERPRESS_EVENTHUB_NAMESPACE':'privatecanary.servicebus.windows.net',
        'COUNTERPRESS_EVENTHUB_NAME':'deliveries',
        'COUNTERPRESS_CHECKPOINT_ENDPOINT':'https://privatecanary.blob.core.windows.net/',
        'COUNTERPRESS_PUBSUB_ENDPOINT':'https://privatecanary.webpubsub.azure.com',
    }.items()] + [{'name':'PRIVATE_REFERENCE','secretRef':'private-secret'}]
    template = {'revisionSuffix':'gh-123-1','containers':[{'name':'counterpress',
        'image':'privatecanary.azurecr.io/counterpress@sha256:'+'a'*64,
        'resources':{'cpu':0.5,'memory':'1Gi'},'env':env}],
        'scale':{'minReplicas':0,'maxReplicas':1,'rules':[
            {'name':'http','http':{'metadata':{'concurrentRequests':'10'}}},
            {'name':'eventhub','custom':{'type':'azure-eventhub','metadata':{'consumerGroup':'$Default'}}}]}}
    return {'id':'/privatecanary/resource','identity':{'type':'UserAssigned','userAssignedIdentities':{
        'private-history-identity':{'clientId':history_client},
        'private-stream-identity':{'clientId':stream_client}}},
        'properties':{'environmentId':'private-environment','workloadProfileName':'Consumption',
            'latestRevisionName':PRODUCTION,'latestReadyRevisionName':PRODUCTION,'provisioningState':'Succeeded',
            'template':template,'configuration':{'activeRevisionsMode':'Single','maxInactiveRevisions':1,
                'secrets':[{'name':'editorial-key'}],
                'ingress':{'external':True,'allowInsecure':False,'targetPort':8000,
                    'traffic':[{'latestRevision':True,'weight':100}]}}}}


def merge(target, patch):
    for k,v in patch.items():
        if isinstance(v,dict):merge(target.setdefault(k,{}),v)
        else:target[k] = copy.deepcopy(v)


class Cloud(staging.Azure):
    def __init__(self):
        self.value = fixture();self.events = [];self.fail_template = False;self.hidden = 0
        self.rows = {PRODUCTION:self.row(PRODUCTION,self.value['properties']['template'])}

    def row(self,name,template):
        return {'name':name,'properties':{'active':True,'provisioningState':'Provisioned',
            'healthState':'Healthy','template':copy.deepcopy(template)}}

    def app(self):return copy.deepcopy(self.value)

    def revisions(self):
        if self.hidden:
            self.hidden -= 1
            return [copy.deepcopy(r) for n,r in self.rows.items() if n != CANDIDATE]
        return list(copy.deepcopy(self.rows).values())

    def revision(self,name):return copy.deepcopy(self.rows[name])

    def patch(self,properties):
        self.events.append(('patch',copy.deepcopy(properties)))
        # Every mutation must preserve the production image behind positive traffic.
        if 'template' in properties:
            t = properties['template'];name = 'counterpress--'+t['revisionSuffix']
            self.rows[name] = self.row(name,t)
            self.value['properties'].update(latestRevisionName=name,latestReadyRevisionName=name)
        merge(self.value['properties'],properties)
        if self.value['properties']['configuration']['activeRevisionsMode'] == 'Single':
            for name,row in self.rows.items():row['properties']['active'] = name == self.value['properties']['latestRevisionName']
        if 'template' in properties and self.fail_template:raise staging.DeploymentError('simulated interruption')

    def wait(self,predicate,message):
        for _ in range(4):
            if predicate():return
        raise staging.DeploymentError(message)

    def deactivate(self,name):
        self.events.append(('deactivate',name));self.rows[name]['properties']['active'] = False


def run_stage(cloud):return staging.stage(cloud,IMAGE,'stage-456-1')


def test_stage_pins_before_template_and_preserves_shared_settings_and_secrets(capsys):
    cloud = Cloud();before = cloud.app()
    assert run_stage(cloud) == (PRODUCTION,CANDIDATE)
    assert cloud.events[0] == ('patch',staging.routing(PRODUCTION))
    assert 'template' in cloud.events[1][1]
    assert staging.pinned(cloud.app(),PRODUCTION,CANDIDATE)
    assert staging.application_value(cloud.app()) == staging.application_value(before)
    c = cloud.revision(CANDIDATE)['properties']['template']
    env = {e['name']:e for e in c['containers'][0]['env']}
    assert env['COUNTERPRESS_STREAMING']['value'] == 'off'
    assert env['COUNTERPRESS_CAREER_STREAMING']['value'] == 'off'
    assert env['COUNTERPRESS_ASSISTANT_CALLS_PER_HOUR']['value'] == '120'
    assert env['COUNTERPRESS_ASSISTANT_CALLS_PER_DAY']['value'] == '400'
    assert env['PRIVATE_REFERENCE'] == {'name':'PRIVATE_REFERENCE','secretRef':'private-secret'}
    assert c['scale']['maxReplicas'] == 1 and c['scale']['minReplicas'] == 0
    assert [r['name'] for r in c['scale']['rules']] == ['http']
    assert cloud.revision(PRODUCTION)['properties']['template'] == before['properties']['template']
    assert 'privatecanary' not in capsys.readouterr().out
    # Configuration PATCH never sends secrets, identity, registry or application endpoints.
    assert all(set(p.get('configuration',{})) <= {'activeRevisionsMode','ingress'}
               for kind,p in cloud.events if kind == 'patch')


@pytest.mark.parametrize('minimum', [0, 1])
def test_cleanup_restores_original_image_before_single_and_never_promotes_candidate(minimum):
    cloud = Cloud()
    cloud.value['properties']['template']['scale']['minReplicas'] = minimum
    cloud.rows[PRODUCTION]['properties']['template']['scale']['minReplicas'] = minimum
    original = cloud.app()['properties']['template'];run_stage(cloud);cloud.events.clear()
    staging.cleanup(cloud,PRODUCTION,CANDIDATE)
    final = cloud.app()
    assert final['properties']['configuration']['activeRevisionsMode'] == 'Single'
    assert staging.pinned(final,RESTORED)
    assert staging.template_value(final['properties']['template']) == staging.template_value(original)
    assert not cloud.revision(CANDIDATE)['properties']['active']
    assert final['properties']['latestReadyRevisionName'] == RESTORED
    assert cloud.events[0] == ('patch',staging.routing(PRODUCTION))
    assert 'template' in cloud.events[1][1]
    deactivate = next(i for i,e in enumerate(cloud.events) if e[0] == 'deactivate')
    single = next(i for i,e in enumerate(cloud.events) if e[0] == 'patch' and
                  e[1].get('configuration',{}).get('activeRevisionsMode') == 'Single')
    assert deactivate < single
    for kind,p in cloud.events:
        if kind == 'patch':
            for route in p.get('configuration',{}).get('ingress',{}).get('traffic',[]):
                assert route.get('revisionName') != CANDIDATE or route['weight'] == 0
    cloud.events.clear();staging.cleanup(cloud,PRODUCTION,CANDIDATE)
    assert not cloud.events


def test_candidate_creation_interruption_keeps_original_pinned_and_cleanup_recovers():
    cloud = Cloud();cloud.fail_template = True
    with pytest.raises(staging.DeploymentError):run_stage(cloud)
    assert staging.pinned(cloud.app(),PRODUCTION)
    cloud.fail_template = False;staging.cleanup(cloud,PRODUCTION,CANDIDATE)
    assert staging.pinned(cloud.app(),RESTORED)


def test_failure_before_candidate_can_return_to_single_without_a_new_revision():
    cloud = Cloud();cloud.patch(staging.routing(PRODUCTION));cloud.events.clear()
    staging.cleanup(cloud,PRODUCTION,CANDIDATE)
    assert cloud.app()['properties']['configuration']['activeRevisionsMode'] == 'Single'
    assert set(cloud.rows) == {PRODUCTION}


def test_eventual_revision_visibility_is_polled_without_ignoring_read_errors():
    cloud = Cloud()
    original_patch = cloud.patch
    def patch(p):
        original_patch(p)
        if 'template' in p:cloud.hidden = 2
    cloud.patch = patch
    run_stage(cloud)
    assert staging.pinned(cloud.app(),PRODUCTION,CANDIDATE)


@pytest.mark.parametrize('change', ['scale','unready','traffic','active_other','unknown_scaler','identity_drift'])
def test_unsafe_initial_state_or_pin_drift_cannot_create_candidate(change):
    cloud = Cloud();p = cloud.value['properties']
    if change == 'scale':p['template']['scale']['maxReplicas'] = 2
    if change == 'unready':p['latestReadyRevisionName'] = 'counterpress--old'
    if change == 'traffic':p['configuration']['ingress']['traffic'][0]['weight'] = 80
    if change == 'active_other':cloud.rows['counterpress--other'] = cloud.row('counterpress--other',p['template'])
    if change == 'unknown_scaler':
        p['template']['scale']['rules'].append({'name':'other','custom':{'type':'cron'}})
        cloud.rows[PRODUCTION] = cloud.row(PRODUCTION,p['template'])
    if change == 'identity_drift':
        patch = cloud.patch
        def changed(props):
            patch(props);cloud.value['identity'] = {}
        cloud.patch = changed
    with pytest.raises((staging.DeploymentError,AssertionError)):run_stage(cloud)
    assert CANDIDATE not in cloud.rows


@pytest.mark.parametrize('change',['candidate_budget','candidate_stream','candidate_image','production_traffic','other_latest','other_active'])
def test_cleanup_rejects_unreviewed_changes_before_mutating(change):
    cloud = Cloud();run_stage(cloud);cloud.events.clear()
    c = cloud.rows[CANDIDATE]['properties']['template']
    if change == 'candidate_budget':c['containers'][0]['env'].append({'name':'UNREVIEWED','value':'yes'})
    if change == 'candidate_stream':
        next(e for e in c['containers'][0]['env'] if e['name']=='COUNTERPRESS_STREAMING')['value'] = 'azure'
    if change == 'candidate_image':c['containers'][0]['image'] = IMAGE.replace('privatecanary','different')
    if change == 'production_traffic':cloud.value['properties']['configuration']['ingress']['traffic'] = [{'revisionName':CANDIDATE,'weight':100}]
    if change == 'other_latest':cloud.value['properties']['latestRevisionName'] = 'counterpress--other'
    if change == 'other_active':cloud.rows['counterpress--other'] = cloud.row('counterpress--other',c)
    with pytest.raises((staging.DeploymentError,AssertionError)):staging.cleanup(cloud,PRODUCTION,CANDIDATE)
    assert not cloud.events


def test_restoration_interruption_is_resumable_without_recreating_or_promoting_candidate():
    cloud = Cloud();run_stage(cloud);cloud.fail_template = True
    with pytest.raises(staging.DeploymentError):staging.cleanup(cloud,PRODUCTION,CANDIDATE)
    assert staging.pinned(cloud.app(),PRODUCTION)
    assert RESTORED in cloud.rows
    cloud.fail_template = False;cloud.events.clear();staging.cleanup(cloud,PRODUCTION,CANDIDATE)
    assert not any(k=='patch' and 'template' in p for k,p in cloud.events)
    assert staging.pinned(cloud.app(),RESTORED)


def test_candidate_unhealthy_cannot_be_advertised_as_ready():
    cloud = Cloud();patch = cloud.patch
    def unhealthy(p):
        patch(p)
        if CANDIDATE in cloud.rows:cloud.rows[CANDIDATE]['properties']['healthState'] = 'Unhealthy'
    cloud.patch = unhealthy
    with pytest.raises(staging.DeploymentError):run_stage(cloud)
    assert staging.pinned(cloud.app(),PRODUCTION)


def test_workflow_reuses_production_lock_and_emergency_cleanup_has_no_ci_or_build_dependency():
    text = (ROOT/'.github/workflows/stage.yml').read_text()
    assert 'group: counterpress-azure-deployment' in text
    assert 'cancel-in-progress: false' in text
    assert 'environment: azure-demo' in text and "github.ref == 'refs/heads/main'" in text
    assert text.count("if: inputs.operation == 'stage'") == 4
    assert "if: inputs.operation == 'cleanup'" in text
    assert 'persist-credentials: false' in text
    assert 'id-token: write' in text and 'azure/login@7184910d9eb2b1c5e48f7073824a90609bb9b6d6' in text
    assert 'upload-artifact' not in text and 'CP_EDITORIAL_MODEL' not in text
    # User-provided revision strings enter quoted shell variables, never shell source.
    assert '--production "$CP_PRODUCTION_REVISION" --candidate "$CP_CANDIDATE_REVISION"' in text


def test_revision_read_permission_failure_stops_before_any_application_mutation():
    cloud = Cloud()
    def denied():raise staging.DeploymentError('revision read denied')
    cloud.revisions = denied
    with pytest.raises(staging.DeploymentError,match='revision read denied'):run_stage(cloud)
    assert not cloud.events


def test_unhealthy_restoration_never_receives_traffic_or_switches_to_single():
    cloud = Cloud();run_stage(cloud)
    patch = cloud.patch
    def unhealthy(p):
        patch(p)
        if RESTORED in cloud.rows:cloud.rows[RESTORED]['properties']['healthState'] = 'Unhealthy'
    cloud.patch = unhealthy
    with pytest.raises(staging.DeploymentError):staging.cleanup(cloud,PRODUCTION,CANDIDATE)
    assert staging.pinned(cloud.app(),PRODUCTION)
    assert cloud.app()['properties']['configuration']['activeRevisionsMode'] == 'Multiple'
    assert cloud.rows[CANDIDATE]['properties']['active']


def test_real_patch_uses_private_temporary_merge_document_and_removes_it_on_failure(monkeypatch,tmp_path):
    import json
    import stat
    azure = staging.Azure({'resource_group':'counterpress-dev','registry_name':'privatecanary'})
    monkeypatch.setattr(azure,'app',fixture)
    monkeypatch.setenv('RUNNER_TEMP',str(tmp_path))
    observed = []
    def command(args,**kwargs):
        assert args[:4] == ['az','rest','--method','patch']
        path = Path(args[args.index('--body')+1][1:]);observed.append(path)
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert json.loads(path.read_text()) == {'properties':staging.routing(PRODUCTION)}
        raise staging.DeploymentError('simulated Azure failure')
    monkeypatch.setattr(staging.subprocess,'run',command)
    with pytest.raises(staging.DeploymentError):azure.patch(staging.routing(PRODUCTION))
    assert observed and not observed[0].exists()
    with pytest.raises(staging.DeploymentError,match='Unexpected app-scoped'):
        azure.patch({'configuration':{'secrets':[]}})
    assert len(observed) == 1


def azure_read_shapes():
    """Sanitized structural regression for actual app/revision reads, 24 Oct 2026."""
    revision = fixture()['properties']['template']
    revision['scale'].update(cooldownPeriod=None,pollingInterval=None)
    application = copy.deepcopy(revision)
    application['containers'][0]['resources']['ephemeralStorage'] = '2Gi'
    application['scale'].update(cooldownPeriod=300,pollingInterval=30)
    application['scale']['rules'].reverse()
    for entry in application['containers'][0]['env']:
        if entry.get('secretRef'):entry['value'] = ''
    return application,revision


def test_known_azure_default_serializations_compare_equal_without_mutating_source():
    app,revision = azure_read_shapes()
    before = copy.deepcopy((app,revision))
    assert staging.template_value(app) == staging.template_value(revision)
    assert (app,revision) == before
    missing = copy.deepcopy(revision)
    missing['scale'].pop('cooldownPeriod');missing['scale'].pop('pollingInterval')
    for e in missing['containers'][0]['env']:
        if e.get('secretRef'):e['value'] = None
    missing['containers'][0]['resources']['ephemeralStorage'] = None
    assert staging.template_value(app) == staging.template_value(missing)


@pytest.mark.parametrize('change', ['storage','cpu','memory','cooldown','polling','replicas',
    'secret_value','secret_ref','literal_empty','scaler_identity','scaler_threshold','probe','budget'])
def test_normalization_retains_meaningful_configuration_differences(change):
    app,revision = azure_read_shapes()
    resources = app['containers'][0]['resources'];env = app['containers'][0]['env'];scale = app['scale']
    if change == 'storage':resources['ephemeralStorage'] = '4Gi'
    if change == 'cpu':resources['cpu'] = 1
    if change == 'memory':resources['memory'] = '2Gi'
    if change == 'cooldown':scale['cooldownPeriod'] = 301
    if change == 'polling':scale['pollingInterval'] = 31
    if change == 'replicas':scale['maxReplicas'] = 2
    if change == 'secret_value':next(e for e in env if e.get('secretRef'))['value'] = 'nonempty-canary'
    if change == 'secret_ref':next(e for e in env if e.get('secretRef'))['secretRef'] = 'changed'
    if change == 'literal_empty':
        env.append({'name':'LITERAL','value':''});revision['containers'][0]['env'].append({'name':'LITERAL'})
    if change == 'scaler_identity':next(r for r in scale['rules'] if 'custom' in r)['custom']['identity'] = 'changed'
    if change == 'scaler_threshold':next(r for r in scale['rules'] if 'http' in r)['http']['metadata']['concurrentRequests'] = '11'
    if change == 'probe':app['containers'][0]['probes'] = [{'type':'Readiness','httpGet':{'path':'/different'}}]
    if change == 'budget':next(e for e in env if e['name']=='COUNTERPRESS_ASSISTANT_CALLS_PER_DAY')['value'] = '600'
    assert staging.template_value(app) != staging.template_value(revision)


@pytest.mark.parametrize('change', ['second_container','init_container','different_cpu','different_memory'])
def test_storage_default_is_not_inferred_outside_reviewed_replica_shape(change):
    app,revision = azure_read_shapes()
    for template in (app,revision):
        if change == 'second_container':template['containers'].append({'name':'sidecar','resources':{'cpu':0.25,'memory':'0.5Gi'},'env':[]})
        if change == 'init_container':template['initContainers'] = [{'name':'init','resources':{'cpu':0.25,'memory':'0.5Gi'}}]
        if change == 'different_cpu':template['containers'][0]['resources']['cpu'] = 1
        if change == 'different_memory':template['containers'][0]['resources']['memory'] = '2Gi'
    assert staging.template_value(app) != staging.template_value(revision)


def test_duplicate_rule_names_are_rejected_instead_of_sorted_as_equivalent():
    template = fixture()['properties']['template']
    template['scale']['rules'][1]['name'] = 'http'
    with pytest.raises(staging.DeploymentError,match='distinct names'):staging.template_value(template)


def test_stage_and_cleanup_accept_real_azure_readback_defaults_but_preserve_original_template():
    cloud = Cloud();application,revision = azure_read_shapes()
    cloud.value['properties']['template'] = application
    cloud.rows[PRODUCTION] = cloud.row(PRODUCTION,revision)
    run_stage(cloud)
    staged = cloud.rows[CANDIDATE]['properties']['template']
    # Comparison normalization must not invent values in the actual PATCH.
    assert 'ephemeralStorage' not in staged['containers'][0]['resources']
    assert staged['scale']['cooldownPeriod'] is None
    staging.cleanup(cloud,PRODUCTION,CANDIDATE)
    restored = cloud.rows[RESTORED]['properties']['template']
    assert staging.template_value(restored) == staging.template_value(revision)
    assert restored['scale'] == revision['scale']


def test_storage_default_inference_cannot_authorize_a_different_workload_profile():
    cloud = Cloud();cloud.value['properties']['workloadProfileName'] = 'Dedicated'
    with pytest.raises(staging.DeploymentError,match='Consumption'):run_stage(cloud)
    assert not cloud.events
    cloud = Cloud();run_stage(cloud);cloud.events.clear()
    cloud.value['properties']['workloadProfileName'] = 'Dedicated'
    with pytest.raises(staging.DeploymentError,match='Consumption'):staging.cleanup(cloud,PRODUCTION,CANDIDATE)
    assert not cloud.events


LOCK_ERROR = 'ERROR: Conflict({"error":{"code":"ContainerAppOperationInProgress","message":"privatecanary endpoint token"}})'


def patch_transport(monkeypatch,tmp_path,responses,change=None):
    from types import SimpleNamespace
    azure = staging.Azure({'resource_group':'counterpress-dev','registry_name':'privatecanary'})
    state = fixture();calls=[];sleeps=[];reads=[]
    def app():
        reads.append(True)
        if len(reads)>1 and change:change(state)
        return copy.deepcopy(state)
    def command(args,**kwargs):
        path=Path(args[args.index('--body')+1][1:]);calls.append((path,kwargs))
        result=responses[min(len(calls)-1,len(responses)-1)]
        if isinstance(result,Exception):raise result
        return SimpleNamespace(returncode=result[0],stderr=result[1],stdout='privatecanary response')
    monkeypatch.setattr(azure,'app',app)
    monkeypatch.setattr(staging.subprocess,'run',command)
    monkeypatch.setattr(staging.time,'sleep',sleeps.append)
    monkeypatch.setenv('RUNNER_TEMP',str(tmp_path))
    return azure,state,calls,sleeps,reads


def test_operation_in_progress_retries_same_private_patch_after_rechecking_state(monkeypatch,tmp_path,capsys):
    azure,state,calls,sleeps,reads=patch_transport(monkeypatch,tmp_path,[(1,LOCK_ERROR),(0,'')])
    azure.patch(staging.routing(PRODUCTION))
    assert len(calls)==2 and len(reads)==2 and sleeps==[5]
    assert calls[0][0]==calls[1][0] and not calls[0][0].exists()
    assert all(c[1]['timeout']<=60 for c in calls)
    assert 'privatecanary' not in capsys.readouterr().out


@pytest.mark.parametrize('stderr',[
    'ERROR: Forbidden({"error":{"code":"ContainerAppOperationInProgress"}})',
    'ERROR: Conflict({"error":{"code":"OtherConflict"}})',
    'ERROR: Conflict({"error":{"code":"OtherConflict","message":"ContainerAppOperationInProgress"}})',
    'ERROR: Conflict({"message":"ContainerAppOperationInProgress"})',
    'ERROR: Conflict(not JSON)',
    'ERROR: ContainerAppOperationInProgress',
])
def test_other_errors_never_retry_or_expose_private_details(monkeypatch,tmp_path,stderr):
    azure,state,calls,sleeps,reads=patch_transport(monkeypatch,tmp_path,[(1,stderr)])
    with pytest.raises(staging.DeploymentError,match='private details omitted') as failure:
        azure.patch(staging.routing(PRODUCTION))
    assert len(calls)==1 and sleeps==[] and len(reads)==1
    assert 'ContainerAppOperationInProgress' not in str(failure.value)
    assert not calls[0][0].exists()


@pytest.mark.parametrize('change',['identity','routing','mode','template','latest','suffix','secrets','budget'])
def test_management_lock_retry_aborts_on_control_plane_drift(monkeypatch,tmp_path,change):
    def mutate(state):
        p=state['properties']
        if change=='identity':state['identity']={}
        if change=='routing':p['configuration']['ingress']['traffic']=[{'revisionName':CANDIDATE,'weight':100}]
        if change=='mode':p['configuration']['activeRevisionsMode']='Multiple'
        if change=='template':p['template']['containers'][0]['image']=IMAGE
        if change=='latest':p['latestRevisionName']=CANDIDATE
        if change=='suffix':p['template']['revisionSuffix']='other'
        if change=='secrets':p['configuration']['secrets'].append({'name':'other'})
        if change=='budget':p['template']['containers'][0]['env'].append({'name':'NEW_BUDGET','value':'999'})
    azure,state,calls,sleeps,reads=patch_transport(monkeypatch,tmp_path,[(1,LOCK_ERROR)],mutate)
    with pytest.raises(staging.DeploymentError,match='Application changed'):
        azure.patch(staging.routing(PRODUCTION))
    assert len(calls)==1 and len(reads)==2 and not calls[0][0].exists()


def test_lock_retries_are_bounded_and_do_not_retry_timeouts(monkeypatch,tmp_path):
    azure,state,calls,sleeps,reads=patch_transport(monkeypatch,tmp_path,[(1,LOCK_ERROR)])
    with pytest.raises(staging.DeploymentError,match='lock did not clear'):
        azure.patch(staging.routing(PRODUCTION))
    assert len(calls)==6 and sleeps==[5]*5 and not calls[0][0].exists()
    azure,state,calls,sleeps,reads=patch_transport(monkeypatch,tmp_path,[staging.subprocess.TimeoutExpired('privatecanary',60)])
    with pytest.raises(staging.DeploymentError,match='inspect before retrying'):
        azure.patch(staging.routing(PRODUCTION))
    assert len(calls)==1 and sleeps==[] and not calls[0][0].exists()


def test_lock_retry_deadline_and_failed_state_read_both_stop_before_resending(monkeypatch,tmp_path):
    azure,state,calls,sleeps,reads=patch_transport(monkeypatch,tmp_path,[(1,LOCK_ERROR)])
    clock=iter([0,0,181]);monkeypatch.setattr(staging.time,'monotonic',lambda:next(clock))
    with pytest.raises(staging.DeploymentError,match='lock did not clear'):
        azure.patch(staging.routing(PRODUCTION))
    assert len(calls)==1 and not calls[0][0].exists()
    monkeypatch.setattr(staging.time,'monotonic',lambda:0)
    azure,state,calls,sleeps,reads=patch_transport(monkeypatch,tmp_path,[(1,LOCK_ERROR)])
    app=azure.app
    def failing_read():
        if reads:raise staging.DeploymentError('Metadata read unavailable')
        return app()
    monkeypatch.setattr(azure,'app',failing_read)
    with pytest.raises(staging.DeploymentError,match='Metadata read unavailable'):
        azure.patch(staging.routing(PRODUCTION))
    assert len(calls)==1 and not calls[0][0].exists()


def test_noop_routing_does_not_reacquire_management_lock(monkeypatch,tmp_path):
    azure,state,calls,sleeps,reads=patch_transport(monkeypatch,tmp_path,[(0,'')])
    merge(state['properties'],staging.routing(PRODUCTION))
    azure.patch(staging.routing(PRODUCTION))
    assert calls==[] and sleeps==[] and list(tmp_path.iterdir())==[]


def test_background_provisioning_status_progress_is_not_configuration_drift(monkeypatch,tmp_path):
    def progress(state):state['properties']['provisioningState']='Updating'
    azure,state,calls,sleeps,reads=patch_transport(monkeypatch,tmp_path,[(1,LOCK_ERROR),(0,'')],progress)
    azure.patch(staging.routing(PRODUCTION))
    assert len(calls)==2


def test_staging_preserves_warm_minimum_without_mutating_source():
    app = fixture()
    original = app['properties']['template']
    original['scale']['minReplicas'] = 1
    before = copy.deepcopy(original)
    staged = staging.staging_template(original, IMAGE, 'stage-warm')
    assert original == before
    assert staged['scale']['minReplicas'] == 1
    assert staged['scale']['maxReplicas'] == 1
    assert staged['containers'][0]['env'] != before['containers'][0]['env']
    assert all('http' in rule for rule in staged['scale']['rules'])


@pytest.mark.parametrize('minimum', [-1, 2, None, '1', True, 1.0])
def test_staging_rejects_unreviewed_replica_minimum(minimum):
    original = fixture()['properties']['template']
    original['scale']['minReplicas'] = minimum
    with pytest.raises(staging.DeploymentError):
        staging.staging_template(original, IMAGE, 'stage-invalid')


def test_warm_azure_generated_revision_can_be_staged_with_exact_traffic_pin():
    app = fixture()
    properties = app['properties']
    properties['template']['scale']['minReplicas'] = 1
    properties['latestRevisionName'] = properties['latestReadyRevisionName'] = 'counterpress--0000008'
    properties['configuration']['ingress']['traffic'] = [{'revisionName': 'counterpress--0000008', 'weight': 100}]
    assert staging.validate_production(app) == 'counterpress--0000008'
    properties['configuration']['ingress']['traffic'][0]['revisionName'] = PRODUCTION
    with pytest.raises(staging.DeploymentError):
        staging.validate_production(app)
