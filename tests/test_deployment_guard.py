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
