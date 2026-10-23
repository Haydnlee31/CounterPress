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
from urllib.parse import urlsplit


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
    # Azure never returns secret values. Compare names/Key Vault metadata only.
    config['secrets'] = config.get('secrets') or []
    for secret in config['secrets']:
        secret.pop('value', None)
    if 'secrets' in config:
        config['secrets'].sort(key=lambda secret: secret['name'])
    return {'template':template, 'configuration':config,
            'identity':app['identity'], 'environmentId':properties['environmentId']}


STUDIO_KEYS = {'COUNTERPRESS_STUDIO', 'COUNTERPRESS_STUDIO_CLIENT_ID',
               'COUNTERPRESS_ENTRA_TENANT_ID', 'COUNTERPRESS_ENTRA_AUDIENCE'}

MODEL_SECRETS = {'AZURE_OPENAI_ENDPOINT': 'editorial-endpoint',
                 'AZURE_OPENAI_DEPLOYMENT': 'editorial-deployment',
                 'AZURE_OPENAI_API_KEY': 'editorial-key'}
MONITOR_SECRET = 'agent-monitor-connection'
MONITOR_KEYS = {'COUNTERPRESS_AGENT_TRACING', 'APPLICATIONINSIGHTS_CONNECTION_STRING',
                'COUNTERPRESS_AGENT_TRACING_CLIENT_ID', 'COUNTERPRESS_AGENT_TRACE_SAMPLE_RATIO'}


def model_reference(item, name, secret):
    """Azure may serialize an unused value beside a secretRef as null or ''."""
    return (isinstance(item, dict)
            and set(item) <= {'name', 'secretRef', 'value'}
            and item.get('name') == name and item.get('secretRef') == secret
            and item.get('value') in (None, ''))


def editorial_settings(app, mode, model=None):
    """Explicit opt-in on existing resources; model values only in app secrets."""
    result = copy.deepcopy(app)
    if mode == 'preserve':
        return result
    if mode not in ('enable', 'disable'):
        raise DeploymentError('Unknown editorial deployment mode')
    container = result['properties']['template']['containers'][0]
    env = {v['name']: v.get('value') for v in container.get('env', [])}
    additions = [{'name': 'COUNTERPRESS_EDITORIAL', 'value': 'off'}]
    if mode == 'enable':
        if env.get('COUNTERPRESS_STUDIO') != 'entra':
            raise DeploymentError('Editorial activation requires Studio')
        validate_model_settings(model)
        client = env.get('COUNTERPRESS_STUDIO_CLIENT_ID')
        if not client or str(UUID(client)) != client:
            raise DeploymentError('Studio client must be configured')
        additions = [{'name': 'COUNTERPRESS_EDITORIAL', 'value': 'entra'},
                     {'name': 'COUNTERPRESS_ENTRA_CLIENT_IDS', 'value': client},
                     *[{'name': name, 'secretRef': secret} for name, secret in MODEL_SECRETS.items()]]
        config = result['properties']['configuration']
        config['secrets'] = [s for s in (config.get('secrets') or []) if s['name'] not in MODEL_SECRETS.values()] + [
            {'name': secret, 'value': model[name]} for name, secret in MODEL_SECRETS.items()]
    removed = {*MODEL_SECRETS, 'COUNTERPRESS_EDITORIAL', 'COUNTERPRESS_ENTRA_CLIENT_IDS'}
    container['env'] = [v for v in container.get('env', []) if v['name'] not in removed] + additions
    return result


def validate_model_settings(model):
    if not isinstance(model, dict) or set(model) != set(MODEL_SECRETS):
        raise DeploymentError('Private model settings are incomplete')
    if not all(isinstance(v, str) and v.strip() and '\n' not in v and '\r' not in v for v in model.values()):
        raise DeploymentError('Private model settings are invalid')
    url = urlsplit(model['AZURE_OPENAI_ENDPOINT'])
    if (url.scheme != 'https' or not url.hostname or not url.hostname.endswith(('.openai.azure.com', '.services.ai.azure.com'))
            or url.port not in (None, 443) or url.username or url.password or url.query or url.fragment
            or url.path.rstrip('/') not in ('', '/openai/v1')):
        raise DeploymentError('Private model destination is invalid')


def rehydrate_configuration_secrets(app, model=None, monitoring=None):
    """Do not depend on ARM preserving secret values omitted from a configuration PATCH.

    Restore known values from reviewed GitHub configuration and monitoring metadata,
    never by listing the application's secret values. Runtime settings stay unchanged.
    """
    result = copy.deepcopy(app)
    secrets = result['properties']['configuration'].get('secrets') or []
    missing = [s for s in secrets if not s.get('value')]
    if any(set(s) != {'name'} for s in missing):
        raise DeploymentError('Unexpected secret representation; configuration update stopped')
    names = {s['name'] for s in missing}
    if names - set(MODEL_SECRETS.values()) - {MONITOR_SECRET}:
        raise DeploymentError('Unknown secret; configuration update stopped')
    values = {}
    if names & set(MODEL_SECRETS.values()):
        validate_model_settings(model)
        values.update({secret: model[key] for key, secret in MODEL_SECRETS.items()})
    if MONITOR_SECRET in names:
        validated = agent_monitoring_settings(app, 'enable', monitoring)
        values[MONITOR_SECRET] = next(s['value'] for s in validated['properties']['configuration']['secrets']
                                      if s['name'] == MONITOR_SECRET)
    for secret in missing:
        secret['value'] = values[secret['name']]
    return result


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


def assistant_settings(app, mode):
    """Reuse existing secret references; do not provision or copy credentials."""
    result = copy.deepcopy(app)
    if mode == 'preserve':
        return result
    if mode not in ('enable', 'disable'):
        raise DeploymentError('Unknown assistant deployment mode')
    container = result['properties']['template']['containers'][0]
    env = {v['name']: v for v in container.get('env', [])}
    if mode == 'enable' and any(
        not model_reference(env.get(name), name, secret)
        for name, secret in MODEL_SECRETS.items()
    ):
        raise DeploymentError('Footie requires existing model secret references')
    container['env'] = [v for v in container.get('env', []) if v['name'] != 'COUNTERPRESS_ASSISTANT_MODEL'] + [
        {'name': 'COUNTERPRESS_ASSISTANT_MODEL', 'value': 'azure' if mode == 'enable' else 'off'}]
    return result


def assistant_workflow_settings(app, mode):
    """Explicit agent activation/rollback; preserve the current workflow by default."""
    result = copy.deepcopy(app)
    if mode == 'preserve':
        return result
    if mode not in ('agent', 'multiagent', 'structured_lookup'):
        raise DeploymentError('Unknown assistant workflow')
    container = result['properties']['template']['containers'][0]
    env = {v['name']: v.get('value') for v in container.get('env', [])}
    if mode in ('agent', 'multiagent') and (env.get('COUNTERPRESS_ASSISTANT_MODEL') != 'azure'
                            or env.get('COUNTERPRESS_STORAGE') != 'cosmos'):
        raise DeploymentError('Agent workflow requires Azure inference and shared Cosmos admission')
    if mode == 'structured_lookup' and env.get('COUNTERPRESS_ASSISTANT_MODEL') == 'azure':
        raise DeploymentError('Use agent for bounded paid rollback, or disable inference for structured lookup')
    container['env'] = [v for v in container.get('env', [])
                        if v['name'] != 'COUNTERPRESS_ASSISTANT_WORKFLOW'] + [
        {'name': 'COUNTERPRESS_ASSISTANT_WORKFLOW', 'value': mode}]
    return result


def assistant_allowance_settings(app, mode):
    """Named, reviewed call envelopes; never accept an arbitrary unlimited budget."""
    result = copy.deepcopy(app)
    if mode == 'preserve':
        return result
    if mode not in ('pilot125', 'conservative'):
        raise DeploymentError('Unknown assistant allowance')
    container = result['properties']['template']['containers'][0]
    env = {v['name']: v.get('value') for v in container.get('env', [])}
    if env.get('COUNTERPRESS_STORAGE') != 'cosmos' or env.get('COUNTERPRESS_ASSISTANT_WORKFLOW') not in ('agent', 'multiagent'):
        raise DeploymentError('Paid allowance requires durable agent admission')
    values = {'COUNTERPRESS_ASSISTANT_CALLS_PER_HOUR': '120' if mode == 'pilot125' else '20',
              'COUNTERPRESS_ASSISTANT_CALLS_PER_DAY': '400'}
    container['env'] = [v for v in container.get('env', []) if v['name'] not in values] + [
        {'name': key, 'value': value} for key, value in values.items()]
    return result


def validate_app(app):
    p=app['properties'];container=p['template']['containers'][0]
    env={v['name']:v.get('value') for v in container.get('env',[])}
    assert env.get('COUNTERPRESS_STORAGE')=='cosmos'
    assert env.get('COUNTERPRESS_STREAMING')=='azure'
    assert env.get('COUNTERPRESS_TELEMETRY')=='on'
    secrets = {s['name'] for s in (p['configuration'].get('secrets') or [])}
    assert secrets <= set(MODEL_SECRETS.values()) | {MONITOR_SECRET}
    assert env.get('COUNTERPRESS_EDITORIAL', 'off') in ('off', 'entra')
    model_env = {v['name']: v for v in container.get('env', []) if v['name'].startswith('AZURE_OPENAI')}
    if env.get('COUNTERPRESS_EDITORIAL', 'off') == 'entra':
        assert env.get('COUNTERPRESS_STUDIO') == 'entra'
        assert env.get('COUNTERPRESS_ENTRA_CLIENT_IDS') == env['COUNTERPRESS_STUDIO_CLIENT_ID']
        assert set(model_env) == set(MODEL_SECRETS) and set(MODEL_SECRETS.values()) <= secrets
        assert all(model_reference(model_env[k], k, v) for k, v in MODEL_SECRETS.items())
    else:
        assert not model_env
    assert env.get('COUNTERPRESS_ASSISTANT_MODEL', 'off') in ('off', 'azure')
    assert env.get('COUNTERPRESS_ASSISTANT_WORKFLOW', 'structured_lookup') in ('structured_lookup', 'agent', 'multiagent')
    if env.get('COUNTERPRESS_ASSISTANT_MODEL') == 'azure':
        assert set(model_env) == set(MODEL_SECRETS)
        if env.get('COUNTERPRESS_ASSISTANT_CALLS_PER_HOUR'):
            assert env.get('COUNTERPRESS_ASSISTANT_WORKFLOW') in ('agent', 'multiagent')
    assert env.get('COUNTERPRESS_STUDIO', 'off') in ('off', 'entra')
    assert env.get('COUNTERPRESS_AGENT_TRACING', 'off') in ('off', 'azure')
    if env.get('COUNTERPRESS_AGENT_TRACING') == 'azure':
        entries = {v['name']: v for v in container.get('env', [])}
        assert MONITOR_SECRET in secrets
        assert model_reference(entries.get('APPLICATIONINSIGHTS_CONNECTION_STRING'),
                               'APPLICATIONINSIGHTS_CONNECTION_STRING', MONITOR_SECRET)
        assert str(UUID(env['COUNTERPRESS_AGENT_TRACING_CLIENT_ID'])) == env['COUNTERPRESS_AGENT_TRACING_CLIENT_ID']
        assert env.get('COUNTERPRESS_AGENT_TRACE_SAMPLE_RATIO') == '1.0'
    assert p['configuration']['activeRevisionsMode']=='Single'
    assert p['template']['scale']['minReplicas']==0 and p['template']['scale']['maxReplicas']==1
    assert p['configuration']['ingress']['allowInsecure'] is False


def agent_monitoring_settings(app, mode, settings=None):
    result = copy.deepcopy(app)
    if mode == 'preserve': return result
    if mode not in ('enable', 'disable'): raise DeploymentError('Unknown agent tracing mode')
    container = result['properties']['template']['containers'][0]
    additions = [{'name': 'COUNTERPRESS_AGENT_TRACING', 'value': 'off'}]
    if mode == 'enable':
        if not isinstance(settings, dict) or set(settings) != MONITOR_KEYS:
            raise DeploymentError('Incomplete monitoring configuration')
        if settings['COUNTERPRESS_AGENT_TRACING'] != 'azure' or settings['COUNTERPRESS_AGENT_TRACE_SAMPLE_RATIO'] != '1.0':
            raise DeploymentError('Invalid tracing mode')
        try:
            client = settings['COUNTERPRESS_AGENT_TRACING_CLIENT_ID']
            assert str(UUID(client)) == client
            connection = settings['APPLICATIONINSIGHTS_CONNECTION_STRING']
            assert isinstance(connection, str) and '\n' not in connection and '\r' not in connection
            items = [item.split('=', 1) for item in connection.strip(';').split(';')]
            fields = dict(items)
            assert len(fields) == len(items)
            assert set(fields) <= {'InstrumentationKey', 'IngestionEndpoint', 'LiveEndpoint', 'ApplicationId'}
            UUID(fields['InstrumentationKey'])
            destination = urlsplit(fields['IngestionEndpoint'])
            assert destination.scheme == 'https' and destination.hostname.endswith('.in.applicationinsights.azure.com')
            assert not destination.username and not destination.password and not destination.query and not destination.fragment
            assert destination.port in (None, 443) and destination.path in ('', '/')
        except (AssertionError, ValueError, TypeError, KeyError, AttributeError):
            raise DeploymentError('Invalid private monitoring settings') from None
        additions = [{'name': key, 'value': value} for key, value in settings.items()
                     if key != 'APPLICATIONINSIGHTS_CONNECTION_STRING'] + [
                         {'name': 'APPLICATIONINSIGHTS_CONNECTION_STRING', 'secretRef': MONITOR_SECRET}]
        config = result['properties']['configuration']
        config['secrets'] = [s for s in (config.get('secrets') or []) if s['name'] != MONITOR_SECRET] + [
            {'name': MONITOR_SECRET, 'value': connection}]
    container['env'] = [v for v in container.get('env', []) if v['name'] not in MONITOR_KEYS] + additions
    return result


def read_monitoring_settings(group):
    insights = run(['az', 'resource', 'show', '-g', group, '-n', 'counterpress-agents',
                    '--resource-type', 'Microsoft.Insights/components', '--api-version', '2020-02-02', '-o', 'json'], parse=True)
    if not insights['properties'].get('DisableLocalAuth'):
        raise DeploymentError('Tracing requires Entra-authenticated ingestion')
    identity = run(['az', 'identity', 'show', '-g', group, '-n', 'counterpress-history', '-o', 'json'], parse=True)
    return {'COUNTERPRESS_AGENT_TRACING': 'azure',
            'APPLICATIONINSIGHTS_CONNECTION_STRING': insights['properties']['ConnectionString'],
            'COUNTERPRESS_AGENT_TRACING_CLIENT_ID': identity['clientId'],
            'COUNTERPRESS_AGENT_TRACE_SAMPLE_RATIO': '1.0'}


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
    editorial_mode=os.environ.get('CP_EDITORIAL_MODE', 'preserve')
    tracing_mode = os.environ.get('CP_ASSISTANT_TRACING', 'preserve')
    configuration_update = editorial_mode == 'enable' or tracing_mode == 'enable'
    model=json.loads(os.environ['CP_EDITORIAL_MODEL']) if configuration_update else None
    if model:
        validate_model_settings(model)
        for value in model.values():
            if isinstance(value, str):print('::add-mask::'+value, flush=True)
    expected=editorial_settings(expected, editorial_mode, model)
    expected=assistant_settings(expected, os.environ.get('CP_ASSISTANT_MODE', 'preserve'))
    expected=assistant_workflow_settings(expected, os.environ.get('CP_ASSISTANT_WORKFLOW', 'preserve'))
    expected=assistant_allowance_settings(expected, os.environ.get('CP_ASSISTANT_ALLOWANCE', 'preserve'))
    has_monitoring = any(s['name'] == MONITOR_SECRET for s in expected['properties']['configuration'].get('secrets') or [])
    monitoring = read_monitoring_settings(group) if tracing_mode == 'enable' or configuration_update and has_monitoring else None
    if monitoring:
        for key in ('APPLICATIONINSIGHTS_CONNECTION_STRING', 'COUNTERPRESS_AGENT_TRACING_CLIENT_ID'):
            print('::add-mask::'+monitoring[key], flush=True)
    expected = agent_monitoring_settings(expected, tracing_mode, monitoring)
    if configuration_update:
        expected = rehydrate_configuration_secrets(expected, model, monitoring)
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
    properties={'template':template}
    if configuration_update:
        properties['configuration'] = expected['properties']['configuration']
    payload_path=Path(os.environ['RUNNER_TEMP'], 'counterpress-update.json')
    payload_path.touch(mode=0o600)
    payload_path.write_text(json.dumps({'properties':properties}))
    run(['az','rest','--method','patch','--url',before['id']+'?api-version=2025-07-01',
         '--body','@'+str(payload_path),'--only-show-errors','-o','json'],timeout=300)
    payload_path.unlink()
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
                    f'Public HTTPS smoke and historical correction checks passed. Studio mode: {mode}. Editorial mode: {editorial_mode}. Cosmos, streaming, telemetry, identities and scale limits preserved.\n')


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
