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
MODEL_AUTH_KEYS = {'AZURE_OPENAI_AUTH_MODE', 'AZURE_OPENAI_MANAGED_IDENTITY_CLIENT_ID'}
MONITOR_SECRET = 'agent-monitor-connection'
MONITOR_KEYS = {'COUNTERPRESS_AGENT_TRACING', 'APPLICATIONINSIGHTS_CONNECTION_STRING',
                'COUNTERPRESS_AGENT_TRACING_CLIENT_ID', 'COUNTERPRESS_AGENT_TRACE_SAMPLE_RATIO'}


def model_reference(item, name, secret):
    """Azure may serialize an unused value beside a secretRef as null or ''."""
    return (isinstance(item, dict)
            and set(item) <= {'name', 'secretRef', 'value'}
            and item.get('name') == name and item.get('secretRef') == secret
            and item.get('value') in (None, ''))


def model_environment(app):
    containers = app['properties']['template']['containers']
    if len(containers) != 1:
        raise DeploymentError('Expected one application container')
    entries = containers[0].get('env', [])
    env = {entry['name']: entry for entry in entries}
    if len(env) != len(entries):
        raise DeploymentError('Duplicate environment settings are not accepted')
    model = {name: entry for name, entry in env.items() if name.startswith('AZURE_OPENAI')}
    if set(model) - set(MODEL_SECRETS) - MODEL_AUTH_KEYS:
        raise DeploymentError('Unknown model authentication setting')
    return env, model


def literal_setting(entry, name):
    if (not isinstance(entry, dict) or entry.get('name') != name
            or set(entry) - {'name', 'value', 'secretRef'} or entry.get('secretRef') not in (None, '')
            or not isinstance(entry.get('value'), str) or not entry['value']):
        raise DeploymentError('Authentication settings must be explicit server literals')
    return entry['value']


def history_model_identity(app, env):
    """Use the already-attached history identity; never infer a credential chain."""
    client = literal_setting(env.get('COUNTERPRESS_COSMOS_CLIENT_ID'), 'COUNTERPRESS_COSMOS_CLIENT_ID')
    try:
        if str(UUID(client)) != client:raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise DeploymentError('The history identity client ID must be canonical') from None
    identities = app.get('identity', {}).get('userAssignedIdentities', {})
    matches = [resource for resource, value in identities.items() if value.get('clientId') == client]
    suffix = '/providers/microsoft.managedidentity/userassignedidentities/counterpress-history'
    if (len(matches) != 1 or not matches[0].casefold().endswith(suffix)
            or not re.fullmatch(r'/subscriptions/[0-9a-f-]{36}/resourcegroups/[^/]+/providers/microsoft\.managedidentity/userassignedidentities/counterpress-history', matches[0], re.I)):
        raise DeploymentError('Model authentication requires the attached history identity')
    if app.get('id') and matches[0].casefold().split('/providers/')[0] != app['id'].casefold().split('/providers/')[0]:
        raise DeploymentError('History identity must remain in the application resource group')
    return client


def validate_model_authentication(app, *, required=True, check_secrets=False):
    env, model = model_environment(app)
    if not model and not required:return 'api_key'
    mode = literal_setting(model['AZURE_OPENAI_AUTH_MODE'], 'AZURE_OPENAI_AUTH_MODE') if 'AZURE_OPENAI_AUTH_MODE' in model else 'api_key'
    if mode not in ('api_key', 'managed_identity'):
        raise DeploymentError('Unknown model authentication mode')
    expected = set(MODEL_SECRETS)
    if mode == 'managed_identity':
        expected.remove('AZURE_OPENAI_API_KEY')
        expected |= MODEL_AUTH_KEYS
        client = literal_setting(model.get('AZURE_OPENAI_MANAGED_IDENTITY_CLIENT_ID'), 'AZURE_OPENAI_MANAGED_IDENTITY_CLIENT_ID')
        if client != history_model_identity(app, env):
            raise DeploymentError('Model identity must match the attached history identity')
    elif 'AZURE_OPENAI_AUTH_MODE' in model:
        expected.add('AZURE_OPENAI_AUTH_MODE')
    if set(model) != expected:
        raise DeploymentError('Model authentication fields do not match the selected mode')
    references = {name: secret for name, secret in MODEL_SECRETS.items() if name in expected}
    if any(not model_reference(model[name], name, secret) for name, secret in references.items()):
        raise DeploymentError('Footie requires existing model secret references')
    if check_secrets:
        entries = app['properties']['configuration'].get('secrets') or []
        names = {entry['name'] for entry in entries}
        if len(names) != len(entries) or not set(MODEL_SECRETS.values()) <= names:
            raise DeploymentError('Referenced model secrets are missing or duplicated')
    return mode


def model_authentication_settings(app, mode):
    """Template-only authentication switch, retaining the existing rollback key."""
    result = copy.deepcopy(app)
    if mode == 'preserve':return result
    if mode not in ('managed_identity', 'api_key'):
        raise DeploymentError('Unknown model authentication deployment mode')
    validate_model_authentication(result, check_secrets=True)
    env, _ = model_environment(result)
    secrets = {entry['name'] for entry in result['properties']['configuration'].get('secrets') or []}
    if not set(MODEL_SECRETS.values()) <= secrets:
        raise DeploymentError('Authentication switching requires the existing rollback secrets')
    additions = [{'name': 'AZURE_OPENAI_AUTH_MODE', 'value': mode}]
    if mode == 'managed_identity':
        additions.append({'name': 'AZURE_OPENAI_MANAGED_IDENTITY_CLIENT_ID', 'value': history_model_identity(result, env)})
    else:
        additions.append({'name': 'AZURE_OPENAI_API_KEY', 'secretRef': MODEL_SECRETS['AZURE_OPENAI_API_KEY']})
    container = result['properties']['template']['containers'][0]
    container['env'] = [entry for entry in container.get('env', [])
                        if entry['name'] not in MODEL_AUTH_KEYS | {'AZURE_OPENAI_API_KEY'}] + additions
    validate_model_authentication(result, check_secrets=True)
    return result


def editorial_settings(app, mode, model=None):
    """Explicit opt-in on existing resources; model values only in app secrets."""
    result = copy.deepcopy(app)
    if mode == 'preserve':
        return result
    if mode not in ('enable', 'disable'):
        raise DeploymentError('Unknown editorial deployment mode')
    container = result['properties']['template']['containers'][0]
    env = {v['name']: v.get('value') for v in container.get('env', [])}
    _, existing_model = model_environment(result)
    authentication = validate_model_authentication(result) if existing_model else 'api_key'
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
                     *[{'name': name, 'secretRef': secret} for name, secret in MODEL_SECRETS.items()
                       if name != 'AZURE_OPENAI_API_KEY' or authentication == 'api_key']]
        config = result['properties']['configuration']
        config['secrets'] = [s for s in (config.get('secrets') or []) if s['name'] not in MODEL_SECRETS.values()] + [
            {'name': secret, 'value': model[name]} for name, secret in MODEL_SECRETS.items()]
    removed = {*MODEL_SECRETS, 'COUNTERPRESS_EDITORIAL', 'COUNTERPRESS_ENTRA_CLIENT_IDS'}
    if mode == 'disable' and (authentication == 'managed_identity' or env.get('COUNTERPRESS_ASSISTANT_MODEL') == 'azure'):
        removed -= set(MODEL_SECRETS)  # Shared inference retains its explicit authentication mode.
    elif mode == 'disable':
        removed |= MODEL_AUTH_KEYS
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
    if mode == 'enable':validate_model_authentication(result, check_secrets='configuration' in result['properties'])
    container['env'] = [v for v in container.get('env', []) if v['name'] != 'COUNTERPRESS_ASSISTANT_MODEL'] + [
        {'name': 'COUNTERPRESS_ASSISTANT_MODEL', 'value': 'azure' if mode == 'enable' else 'off'}]
    return result


def analyst_settings(app, mode, configuration=None):
    """Explicit Analyst activation; preserve existing model auth and native pins."""
    result = copy.deepcopy(app)
    if mode == 'preserve':
        return result
    if mode not in ('enable', 'azure_discussion', 'disable'):
        raise DeploymentError('Unknown Analyst deployment mode')
    container = result['properties']['template']['containers'][0]
    entries = container.get('env', [])
    values = {'COUNTERPRESS_ANALYST_MODE': 'off', 'COUNTERPRESS_ANALYST_DISCUSSION': 'off'}
    if mode in ('enable', 'azure_discussion'):
        env = {e['name']: e.get('value') for e in entries}
        if env.get('COUNTERPRESS_STORAGE') != 'cosmos':
            raise DeploymentError('Analyst requires shared Cosmos admission')
    if mode == 'azure_discussion':
        validate_model_authentication(result, check_secrets=True)
        values['COUNTERPRESS_ANALYST_DISCUSSION'] = 'azure'
    if mode == 'enable':
        from urllib.parse import urlsplit
        config = configuration or {}
        required = {'project_endpoint', 'agent_name', 'agent_version', 'manifest_id', 'verified'}
        if set(config) - {'protocol'} != required or config.get('verified') is not True or config.get('protocol','candidate-v1') not in ('candidate-v1','roundtable-v2'):
            raise DeploymentError('Native Analyst requires a verified pinned manifest')
        url = urlsplit(config['project_endpoint'])
        if (url.scheme != 'https' or not url.hostname or not url.hostname.endswith('.services.ai.azure.com')
                or url.username or url.password or url.query or url.fragment or url.port not in (None, 443)
                or not re.fullmatch(r'/api/projects/[A-Za-z0-9_-]+/?', url.path)):
            raise DeploymentError('Invalid native project configuration')
        if (not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', config['agent_name'])
                or not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', config['agent_version'])
                or not re.fullmatch(r'[a-f0-9]{64}', config['manifest_id'])):
            raise DeploymentError('Invalid native agent pin')
        values = {'COUNTERPRESS_ANALYST_MODE': 'off' if config.get('protocol')=='roundtable-v2' else 'foundry',
            'COUNTERPRESS_ANALYST_DISCUSSION': 'foundry' if config.get('protocol')=='roundtable-v2' else 'off', **{
            'COUNTERPRESS_ANALYST_' + key.upper(): config[key]
            for key in ('project_endpoint', 'agent_name', 'agent_version', 'manifest_id')}}
    container['env'] = [e for e in entries if e['name'] not in values] + [
        {'name': key, 'value': value} for key, value in values.items()]
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


def validate_production_stream_scopes(entries):
    """The production release path must never adopt verifier destinations."""
    defaults = {
        'COUNTERPRESS_PUBSUB_HUB': 'counterpress',
        'COUNTERPRESS_CHECKPOINT_CONTAINER': 'eventhub-checkpoints',
        'COUNTERPRESS_QUARANTINE_CONTAINER': 'rejected-deliveries',
    }
    for name, expected in defaults.items():
        matching = [entry for entry in entries if entry.get('name') == name]
        if (len(matching) > 1 or any(
                entry.get('value') != expected or 'secretRef' in entry
                for entry in matching)):
            raise DeploymentError('Production streaming destinations must retain reviewed defaults')


def validate_career_streaming_prerequisites(app):
    """Validate existing wiring only; never create identities, stores or credentials."""
    try:
        properties = app['properties']
        containers = properties['template']['containers']
        if len(containers) != 1:
            raise ValueError
        entries = containers[0].get('env', [])
        validate_production_stream_scopes(entries)
        env = {entry['name']: entry.get('value') for entry in entries}
        if len(env) != len(entries):
            raise ValueError
        if (env.get('COUNTERPRESS_STORAGE') != 'cosmos'
                or env.get('COUNTERPRESS_STREAMING') != 'azure'
                or env.get('COUNTERPRESS_COSMOS_DATABASE') != 'counterpress'
                or env.get('COUNTERPRESS_COSMOS_CONTAINER') != 'histories'
                or env.get('COUNTERPRESS_PROFILE_DB_PATH', ':memory:') != ':memory:'):
            raise ValueError
        for key, suffix, ports in (
            ('COUNTERPRESS_COSMOS_ENDPOINT', '.documents.azure.com', (None, 443)),
            ('COUNTERPRESS_CHECKPOINT_ENDPOINT', '.blob.core.windows.net', (None,)),
            ('COUNTERPRESS_PUBSUB_ENDPOINT', '.webpubsub.azure.com', (None,)),
        ):
            value = env[key]
            if not isinstance(value, str) or any(c.isspace() for c in value):
                raise ValueError
            parsed = urlsplit(value)
            if (parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith(suffix)
                    or parsed.port not in ports or parsed.username or parsed.password
                    or parsed.query or parsed.fragment or parsed.path not in ('', '/')):
                raise ValueError
        if (not re.fullmatch(r'[a-zA-Z0-9-]+\.servicebus\.windows\.net', env['COUNTERPRESS_EVENTHUB_NAMESPACE'])
                or env.get('COUNTERPRESS_EVENTHUB_NAME') != 'deliveries'):
            raise ValueError
        attached = app['identity']['userAssignedIdentities']
        client_ids = {value.get('clientId') for value in attached.values()}
        for key in ('COUNTERPRESS_COSMOS_CLIENT_ID', 'COUNTERPRESS_STREAM_CLIENT_ID'):
            client = env[key]
            if str(UUID(client)) != client or client not in client_ids:
                raise ValueError
        scale = properties['template']['scale']
        if (properties['configuration']['activeRevisionsMode'] != 'Single'
                or scale.get('minReplicas') != 0 or scale.get('maxReplicas') != 1):
            raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError):
        raise DeploymentError('Career streaming requires existing reviewed Cosmos, streaming and attached identities') from None


def career_streaming_settings(app, mode):
    """Only toggle bridge activation; preserve journal, secrets and every other setting.

    Operators must stop producers and drain pending career deliveries before
    disabling. A configuration guard cannot establish partition-drain state.
    """
    result = copy.deepcopy(app)
    if mode == 'preserve':
        return result
    if mode not in ('enable', 'disable'):
        raise DeploymentError('Unknown career streaming mode')
    if mode == 'enable':
        validate_career_streaming_prerequisites(result)
    container = result['properties']['template']['containers'][0]
    container['env'] = [entry for entry in container.get('env', [])
                        if entry['name'] != 'COUNTERPRESS_CAREER_STREAMING'] + [
        {'name': 'COUNTERPRESS_CAREER_STREAMING', 'value': 'on' if mode == 'enable' else 'off'}]
    return result


def validate_app(app):
    p=app['properties'];container=p['template']['containers'][0]
    validate_production_stream_scopes(container.get('env', []))
    env={v['name']:v.get('value') for v in container.get('env',[])}
    assert env.get('COUNTERPRESS_STORAGE')=='cosmos'
    assert env.get('COUNTERPRESS_STREAMING')=='azure'
    assert env.get('COUNTERPRESS_TELEMETRY')=='on'
    assert env.get('COUNTERPRESS_CAREER_STREAMING', 'off') in ('off', 'on')
    if env.get('COUNTERPRESS_CAREER_STREAMING') == 'on':
        validate_career_streaming_prerequisites(app)
    secrets = {s['name'] for s in (p['configuration'].get('secrets') or [])}
    assert secrets <= set(MODEL_SECRETS.values()) | {MONITOR_SECRET}
    assert env.get('COUNTERPRESS_EDITORIAL', 'off') in ('off', 'entra')
    try:
        validate_model_authentication(app, required=env.get('COUNTERPRESS_EDITORIAL') == 'entra'
            or env.get('COUNTERPRESS_ASSISTANT_MODEL') == 'azure'
            or env.get('COUNTERPRESS_ANALYST_DISCUSSION') == 'azure', check_secrets=True)
    except DeploymentError:
        raise AssertionError('Invalid model authentication configuration') from None
    if env.get('COUNTERPRESS_EDITORIAL', 'off') == 'entra':
        assert env.get('COUNTERPRESS_STUDIO') == 'entra'
        assert env.get('COUNTERPRESS_ENTRA_CLIENT_IDS') == env['COUNTERPRESS_STUDIO_CLIENT_ID']
    assert env.get('COUNTERPRESS_ANALYST_MODE', 'off') in ('off', 'foundry')
    assert env.get('COUNTERPRESS_ANALYST_DISCUSSION', 'off') in ('off', 'azure', 'foundry')
    assert not (env.get('COUNTERPRESS_ANALYST_MODE') == 'foundry'
                and env.get('COUNTERPRESS_ANALYST_DISCUSSION', 'off') != 'off')
    assert env.get('COUNTERPRESS_ASSISTANT_MODEL', 'off') in ('off', 'azure')
    assert env.get('COUNTERPRESS_ASSISTANT_WORKFLOW', 'structured_lookup') in ('structured_lookup', 'agent', 'multiagent')
    if env.get('COUNTERPRESS_ASSISTANT_MODEL') == 'azure':
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



def verify_analyst_status(env, status):
    """Read-only post-deploy probe: never dispatch a paid discussion."""
    discussion = env.get('COUNTERPRESS_ANALYST_DISCUSSION')
    if discussion in ('azure', 'foundry'):
        expected_runtime = 'footie_live_turn_manager' if discussion == 'azure' else 'microsoft_agent_framework'
        if (status.get('discussion_available') is not True
                or status.get('discussion_runtime') != expected_runtime):
            raise DeploymentError('Analyst discussion unavailable; check model configuration and durable admission')
        if discussion == 'azure' and (status.get('discussion_style') != 'live'
                or status.get('match_model_allowance_usd') != 2.7):
            raise DeploymentError('Live Analyst configuration does not match the reviewed per-match allowance')
    elif status.get('discussion_available') is True:
        raise DeploymentError('Unexpected Analyst discussion activation')
    if env.get('COUNTERPRESS_ANALYST_MODE') == 'foundry':
        if status.get('available') is not True or status.get('mode') != 'foundry':
            raise DeploymentError('Native Analyst configuration unavailable')


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
    authentication_mode=os.environ.get('CP_MODEL_AUTHENTICATION', 'preserve')
    expected=model_authentication_settings(expected, authentication_mode)
    expected=assistant_settings(expected, os.environ.get('CP_ASSISTANT_MODE', 'preserve'))
    expected=assistant_workflow_settings(expected, os.environ.get('CP_ASSISTANT_WORKFLOW', 'preserve'))
    expected=assistant_allowance_settings(expected, os.environ.get('CP_ASSISTANT_ALLOWANCE', 'preserve'))
    analyst_mode = os.environ.get('CP_ANALYST_MODE', 'preserve')
    analyst_config = json.loads(os.environ.get('CP_ANALYST_FOUNDRY') or '{}') if analyst_mode == 'enable' else None
    if analyst_config:
        for value in analyst_config.values():
            if isinstance(value, str): print('::add-mask::' + value, flush=True)
    expected=analyst_settings(expected, analyst_mode, analyst_config)
    career_mode = os.environ.get('CP_CAREER_STREAMING', 'preserve')
    expected=career_streaming_settings(expected, career_mode)
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
    with urlopen(url+'/api/analyst/config',timeout=30) as response:
        analyst_status=json.load(response)
    verify_analyst_status(current_env, analyst_status)
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
                    f'Public HTTPS smoke and historical correction checks passed. Studio mode: {mode}. Editorial mode: {editorial_mode}. Model authentication: {authentication_mode}. Career streaming mode: {career_mode}. Cosmos, streaming, telemetry, identities and scale limits preserved.\n')


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
