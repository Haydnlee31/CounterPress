"""Register ACA-hosted Footie agents and prepare private runtime tracing settings.

No model calls or Container App changes. Registration is metadata-only in Foundry.
Run with `uv run --extra foundry-admin python scripts/configure_agent_monitoring.py`.
Never print the SDK/CLI response, destination, connection string or exception body.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess


AGENTS = {
    'footie-orchestrator': 'Footie orchestrates bounded football research in Azure Container Apps.',
    'footie-match-analyst': 'Match specialist queries recorded match evidence at the playback cutoff.',
    'footie-career-analyst': 'Career specialist queries deterministic player and club statistics.',
}


def azure_json(*args):
    result = subprocess.run(['az', *args, '-o', 'json'], capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError('Azure metadata request failed; inspect authorized resource access')
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resource-group', default='counterpress-dev')
    parser.add_argument('--foundry-account', default='counterpress-dev-01')
    parser.add_argument('--foundry-project', default='CounterPress')
    parser.add_argument('--name-prefix', default='counterpress')
    parser.add_argument('--register', action='store_true', help='Create missing external agent records')
    parser.add_argument('--runtime-config', type=Path,
                        help='Write a new mode600 file for controlled runtime diagnostics')
    args = parser.parse_args()
    subscription = azure_json('account', 'show')['id']
    base = f'/subscriptions/{subscription}/resourceGroups/{args.resource_group}/providers/'
    project_id = base + f'Microsoft.CognitiveServices/accounts/{args.foundry_account}/projects/{args.foundry_project}'
    project = azure_json('resource', 'show', '--ids', project_id, '--api-version', '2025-06-01')
    endpoint = project['properties']['endpoints']['AI Foundry API']
    insights_id = base + f'Microsoft.Insights/components/{args.name_prefix}-agents'
    insights = azure_json('resource', 'show', '--ids', insights_id, '--api-version', '2020-02-02')
    connection = insights['properties']['ConnectionString']
    if not insights['properties'].get('DisableLocalAuth'):
        raise RuntimeError('App Insights must require Entra-authenticated ingestion')
    identity = azure_json('identity', 'show', '-g', args.resource_group, '-n', args.name_prefix + '-history')
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import ExternalAgentDefinition
    from azure.core.exceptions import ResourceNotFoundError
    from azure.identity import AzureCliCredential
    with AzureCliCredential() as credential, AIProjectClient(
        endpoint=endpoint, credential=credential, allow_preview=True,
    ) as client:
        # Verify the project actually resolves this monitoring component.
        linked = client.telemetry.get_application_insights_connection_string()
        if linked != connection:
            raise RuntimeError('Foundry monitoring connection does not match App Insights')
        print('Foundry monitoring connection verified')
        for name, description in AGENTS.items():
            try:
                existing = client.agents.get(name)
            except ResourceNotFoundError:
                if not args.register:
                    print(f'{name}: not registered')
                    continue
                existing = client.agents.create_version(agent_name=name, description=description,
                    definition=ExternalAgentDefinition(otel_agent_id=name))
            definition = (existing.definition if hasattr(existing, 'definition')
                          else existing.versions.latest.definition)
            if definition.kind != 'external' or definition.otel_agent_id != name:
                raise RuntimeError('Existing registration identity does not match expected Footie agent')
            print(f'{name}: external registration verified')
    if args.runtime_config:
        payload = {
            'COUNTERPRESS_AGENT_TRACING': 'azure',
            'APPLICATIONINSIGHTS_CONNECTION_STRING': connection,
            'COUNTERPRESS_AGENT_TRACING_CLIENT_ID': identity['clientId'],
            'COUNTERPRESS_AGENT_TRACE_SAMPLE_RATIO': '1.0',
        }
        fd = os.open(args.runtime_config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as output:
            json.dump(payload, output)
        print('Private runtime settings prepared; values omitted')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Monitoring setup failed; no private response or exception details were printed.') from None
