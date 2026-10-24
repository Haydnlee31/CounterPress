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
    env = [dict(name=k,value=v) for k,v in {
        'COUNTERPRESS_STORAGE':'cosmos','COUNTERPRESS_STREAMING':'azure',
        'COUNTERPRESS_CAREER_STREAMING':'on','COUNTERPRESS_TELEMETRY':'on',
        'COUNTERPRESS_ASSISTANT_MODEL':'off','COUNTERPRESS_ASSISTANT_WORKFLOW':'multiagent',
        'COUNTERPRESS_ASSISTANT_CALLS_PER_HOUR':'120','COUNTERPRESS_ASSISTANT_CALLS_PER_DAY':'400',
        'COUNTERPRESS_COSMOS_ENDPOINT':'https://privatecanary.documents.azure.com',
        'COUNTERPRESS_COSMOS_CONTAINER':'histories',
    }.items()] + [{'name':'PRIVATE_REFERENCE','secretRef':'private-secret'}]
    template = {'revisionSuffix':'gh-123-1','containers':[{'name':'counterpress',
        'image':'privatecanary.azurecr.io/counterpress@sha256:'+'a'*64,
        'resources':{'cpu':0.5,'memory':'1Gi'},'env':env}],
        'scale':{'minReplicas':0,'maxReplicas':1,'rules':[
            {'name':'http','http':{'metadata':{'concurrentRequests':'10'}}},
            {'name':'eventhub','custom':{'type':'azure-eventhub','metadata':{'consumerGroup':'$Default'}}}]}}
    return {'id':'/privatecanary/resource','identity':{'type':'UserAssigned','userAssignedIdentities':{'private-identity':{}}},
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


def test_cleanup_restores_original_image_before_single_and_never_promotes_candidate():
    cloud = Cloud();original = cloud.app()['properties']['template'];run_stage(cloud);cloud.events.clear()
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
    monkeypatch.setattr(staging,'run',command)
    with pytest.raises(staging.DeploymentError):azure.patch(staging.routing(PRODUCTION))
    assert observed and not observed[0].exists()
    with pytest.raises(staging.DeploymentError,match='Unexpected app-scoped'):
        azure.patch({'configuration':{'secrets':[]}})
    assert len(observed) == 1
