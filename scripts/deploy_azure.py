"""Guarded image/Studio deployment after exact-commit CI; never print resolved Azure config."""
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.request import urlopen
from uuid import UUID


class DeploymentError(RuntimeError):
    pass


def run(args, *, parse=False, timeout=180):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise DeploymentError('Command failed: '+Path(args[0]).name+' '+args[1])
    return json.loads(result.stdout) if parse else result.stdout.strip()


def check_ci(payload, sha):
    candidates = [r for r in payload.get('workflow_runs', [])
                  if r.get('head_sha') == sha and r.get('head_branch') == 'main'
                  and r.get('event') == 'push' and r.get('path') == '.github/workflows/ci.yml']
    latest = max(candidates, key=lambda r: (r.get('id', 0), r.get('run_attempt', 0)), default={})
    return latest.get('conclusion') == 'success'



def invariants(app):
    properties = app['properties']
    template = copy.deepcopy(properties['template'])
    template.pop('revisionSuffix', None)
    assert len(template['containers']) == 1
    template['containers'][0].pop('image')
    config = copy.deepcopy(properties['configuration'])
    config.get('ingress', {}).pop('traffic', None)
    return {'template':template, 'configuration':config,
            'identity':app['identity'], 'environmentId':properties['environmentId']}


STUDIO_KEYS = {'COUNTERPRESS_STUDIO', 'COUNTERPRESS_STUDIO_CLIENT_ID',
               'COUNTERPRESS_ENTRA_TENANT_ID', 'COUNTERPRESS_ENTRA_AUDIENCE'}


def studio_template(template, mode, identity=None):
    """Only these four reviewed settings may change; never insert model secrets."""
    if mode not in ('preserve', 'enable', 'disable'):
        raise DeploymentError('Unknown Studio deployment mode')
    result = copy.deepcopy(template)
    if mode == 'preserve':
        return result
    values = {'COUNTERPRESS_STUDIO': 'off'}
    if mode == 'enable':
        if not isinstance(identity, dict) or set(identity) != {'tenant_id', 'api_client_id', 'client_id'}:
            raise DeploymentError('Studio identity configuration is incomplete')
        try:
            if any(str(UUID(value)) != value for value in identity.values()):
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise DeploymentError('Studio identity configuration is invalid') from None
        values = {'COUNTERPRESS_STUDIO': 'entra', 'COUNTERPRESS_STUDIO_CLIENT_ID': identity['client_id'],
                  'COUNTERPRESS_ENTRA_TENANT_ID': identity['tenant_id'], 'COUNTERPRESS_ENTRA_AUDIENCE': identity['api_client_id']}
    containers = result['containers']
    if len(containers) != 1:
        raise DeploymentError('Expected one application container')
    env = containers[0].get('env', [])
    # Shared API identity settings must not be silently replaced under a running editor.
    if next((v.get('value') for v in env if v['name'] == 'COUNTERPRESS_EDITORIAL'), 'off') != 'off':
        raise DeploymentError('Studio configuration requires the paid editorial API to remain off')
    containers[0]['env'] = [v for v in env if v['name'] not in STUDIO_KEYS] + [
        {'name': key, 'value': value} for key, value in values.items()]
    return result


def revision_is_ready(app, revision):
    p = app['properties']
    return (p.get('latestRevisionName') == revision
            and p.get('latestReadyRevisionName') == revision
            and p.get('provisioningState') == 'Succeeded')


def validate_app(app):
    p=app['properties'];container=p['template']['containers'][0]
    env={v['name']:v.get('value') for v in container.get('env',[])}
    assert env.get('COUNTERPRESS_STORAGE')=='cosmos'
    assert env.get('COUNTERPRESS_STREAMING')=='azure'
    assert env.get('COUNTERPRESS_TELEMETRY')=='on'
    assert not p['configuration'].get('secrets')
    assert not any(k.startswith('AZURE_OPENAI') for k in env)
    assert env.get('COUNTERPRESS_EDITORIAL', 'off') == 'off'
    assert env.get('COUNTERPRESS_STUDIO', 'off') in ('off', 'entra')
    assert p['configuration']['activeRevisionsMode']=='Single'
    assert p['template']['scale']['minReplicas']==0 and p['template']['scale']['maxReplicas']==1
    assert p['configuration']['ingress']['allowInsecure'] is False


def require_ci():
    sha=os.environ['GITHUB_SHA'];repo=os.environ['GITHUB_REPOSITORY']
    assert re.fullmatch(r'[0-9a-f]{40}',sha)
    assert repo=='Haydnlee31/CounterPress' and os.environ['GITHUB_REF']=='refs/heads/main'
    head=run(['gh','api',f'repos/{repo}/git/ref/heads/main'],parse=True)
    if head['object']['sha']!=sha:raise DeploymentError('Main changed; dispatch the current main commit')
    payload=run(['gh','api',f'repos/{repo}/actions/workflows/ci.yml/runs?head_sha={sha}&event=push&per_page=100'],parse=True)
    if not check_ci(payload,sha):raise DeploymentError('Successful main CI is required for this exact commit')
    print('PASS: protected main head has successful exact-commit CI',flush=True)


def deploy():
    require_ci()  # Recheck after the image build, before any Azure mutation.
    cfg=json.loads(os.environ['CP_AZURE_TARGET'])
    for value in cfg.values():
        if isinstance(value,str):print('::add-mask::'+value,flush=True)
    sha=os.environ['GITHUB_SHA'];registry=cfg['registry_name'];group=cfg['resource_group']
    assert re.fullmatch(r'[a-zA-Z0-9]+',registry)
    common=['--name','counterpress','--resource-group',group,'--only-show-errors','-o','json']
    def app():return run(['az','containerapp','show',*common],parse=True)
    before=app();validate_app(before)
    mode=os.environ.get('CP_STUDIO_MODE', 'preserve')
    identity=json.loads(os.environ['CP_STUDIO_IDENTITY']) if mode == 'enable' else None
    if identity:
        for value in identity.values():
            if isinstance(value, str):print('::add-mask::'+value, flush=True)
    expected=copy.deepcopy(before)
    expected['properties']['template']=studio_template(before['properties']['template'], mode, identity)
    validate_app(expected)
    baseline=invariants(expected)
    old_image=before['properties']['template']['containers'][0]['image']
    host=run(['az','acr','show','--name',registry,'--query','loginServer','-o','tsv','--only-show-errors'])
    print('::add-mask::'+host,flush=True)
    assert host==registry+'.azurecr.io' and old_image.startswith(host+'/counterpress@sha256:')
    run(['az','acr','login','--name',registry,'--only-show-errors'])
    tag=f'{host}/counterpress:{sha}'
    run(['docker','tag','counterpress:deploy',tag]);run(['docker','push',tag],timeout=600)
    digest=run(['az','acr','repository','show','--name',registry,'--image','counterpress:'+sha,'--query','digest','-o','tsv','--only-show-errors'])
    assert re.fullmatch(r'sha256:[0-9a-f]{64}',digest)
    image=f'{host}/counterpress@{digest}'
    # Private runner-local record; never upload app settings or raw Azure responses.
    Path(os.environ['RUNNER_TEMP'],'counterpress-rollback.json').write_text(json.dumps({'image':old_image, 'template':before['properties']['template']}))
    print('Deploy phase: updating the existing app image',flush=True)
    template=copy.deepcopy(expected['properties']['template'])
    template['containers'][0]['image']=image
    template['revisionSuffix']='gh-'+os.environ['GITHUB_RUN_ID']+'-'+os.environ['GITHUB_RUN_ATTEMPT']
    body=json.dumps({'properties':{'template':template}})
    run(['az','rest','--method','patch','--url',before['id']+'?api-version=2025-07-01',
         '--body',body,'--only-show-errors','-o','json'],timeout=300)
    print('Deploy phase: waiting for the requested revision',flush=True)
    for _ in range(36):
        current=app();p=current['properties']
        if revision_is_ready(current, 'counterpress--'+template['revisionSuffix']):break
        time.sleep(5)
    else:raise DeploymentError('New revision did not become ready; use the documented rollback')
    validate_app(current)
    assert invariants(current)==baseline, 'Deployment changed unreviewed runtime configuration'
    assert p['template']['containers'][0]['image']==image
    url='https://'+p['configuration']['ingress']['fqdn']
    current_env={v['name']:v.get('value') for v in p['template']['containers'][0].get('env', [])}
    enabled=current_env.get('COUNTERPRESS_STUDIO')=='entra'
    run([sys.executable,'scripts/container_smoke.py',url,*(['--studio-enabled'] if enabled else [])],timeout=240)
    for at,count in [(780000,4),(785000,3),(790000,None),(795000,2)]:
        with urlopen(url+f'/api/scenarios/stream-recovery/snapshot?at_ms={at}',timeout=30) as r:
            snapshot=json.load(r)
        assert (snapshot['insight']['facts']['current_count'] if snapshot['insight'] else None)==count
    print('PASS: OIDC deployment; Cosmos, streaming, identities and scaling preserved; Studio mode '+mode,flush=True)
    print('PASS: public HTTPS smoke and historical streaming corrections',flush=True)
    summary=os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary,'a') as f:
            f.write(f'## Verified CounterPress deployment\n\nCommit: `{sha}`\n\nImage digest: `{digest}`\n\n'
                    f'Public HTTPS smoke and historical correction checks passed. Studio mode: {mode}. Paid editorial API remains off. Cosmos, streaming, telemetry, identities and scale limits preserved.\n')


if __name__=='__main__':
    try:
        if sys.argv[1:] == ['check-ci']:require_ci()
        elif sys.argv[1:] == ['deploy']:deploy()
        else:raise DeploymentError('Expected check-ci or deploy')
    except DeploymentError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except Exception:
        # No subprocess stderr, SDK exception strings or settings in public logs.
        print('Deployment stopped: a CI, configuration, Azure operation or verification check failed. See the runbook.',file=sys.stderr)
        sys.exit(1)
