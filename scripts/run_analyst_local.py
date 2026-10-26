"""Local Analyst UI; native inference requires an explicit verified private config."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8018)
    parser.add_argument('--foundry-config', type=Path, help='Private verified activation JSON; never commit this file')
    parser.add_argument('--discussion', action='store_true', help='Run the new bounded analyst group chat with existing Azure model settings')
    args = parser.parse_args()
    env = dict(os.environ)
    env['COUNTERPRESS_ANALYST_MODE'] = 'off'
    env['COUNTERPRESS_AGENT_TRACING'] = 'off'
    env['COUNTERPRESS_CAREER_STREAMING'] = 'off'
    if args.discussion:
        env['COUNTERPRESS_ANALYST_DISCUSSION'] = 'azure'
        env['COUNTERPRESS_ANALYST_LEDGER_PATH'] = str(Path('var/analyst-local-allowance.sqlite3').resolve())
    if args.foundry_config:
        try:
            config = json.loads(args.foundry_config.read_text())
            required = {'project_endpoint', 'agent_name', 'agent_version', 'manifest_id', 'verified'}
            if set(config) - {'protocol'} != required or config['verified'] is not True or config.get('protocol','candidate-v1') not in ('candidate-v1','roundtable-v2'):
                raise ValueError()
            from counterpress.analyst.provider import FoundryAnalyst
            FoundryAnalyst(*(config[key] for key in ('project_endpoint', 'agent_name', 'agent_version', 'manifest_id')))
        except (OSError, ValueError, TypeError):
            raise SystemExit('A complete, verified private native configuration is required.') from None
        env.update({'COUNTERPRESS_ANALYST_' + key.upper(): config[key] for key in required - {'verified'}})
        env['COUNTERPRESS_ANALYST_MODE'] = 'foundry' if config.get('protocol') != 'roundtable-v2' else 'off'
        if config.get('protocol') == 'roundtable-v2': env['COUNTERPRESS_ANALYST_DISCUSSION'] = 'foundry'
        env['COUNTERPRESS_ANALYST_LEDGER_PATH'] = str(Path('var/analyst-local-allowance.sqlite3').resolve())
        # The local developer uses Azure CLI sign-in, never the app's managed identity.
        env.pop('AZURE_OPENAI_MANAGED_IDENTITY_CLIENT_ID', None)
        env.pop('AZURE_CLIENT_ID', None)
    raise SystemExit(subprocess.call([sys.executable, 'scripts/run_footie_local.py', '--port', str(args.port)] + (['--azure'] if args.discussion else []), env=env))


if __name__ == '__main__':
    main()
