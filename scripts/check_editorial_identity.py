"""Explicit local Entra sign-in check. Tokens stay in memory; no model calls.

Run from the repository root with uv run --frozen python
scripts/check_editorial_identity.py --config var/editorial-entra.json.
The private config contains tenant_id, api_client_id and client_client_id.
"""

import argparse
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import msal

from counterpress.api.main import create_app
from counterpress.api.snapshots import SnapshotService
from counterpress.editorial.auth import AccessDenied, EntraSettings, EntraVerifier
from counterpress.editorial.ledger import Ledger, SQLiteLedgerStore
from counterpress.editorial.service import EditorialController
from counterpress.history import SQLiteHistoryStore


async def check(token, settings, *, verifier=None):
    verifier = verifier or EntraVerifier(settings)
    actor = await asyncio.to_thread(verifier.verify, token)
    assert len(actor) == 64
    snapshots = SnapshotService(Path('fixtures'), SQLiteHistoryStore(':memory:'))
    # No real model configuration is loaded, and transport construction is forbidden.
    def forbidden():
        raise AssertionError('Identity verification must never dispatch model work')
    config = SimpleNamespace(endpoint='not-configured', deployment='not-configured')
    control = EditorialController(snapshots, config, Ledger(SQLiteLedgerStore(':memory:')),
                                  transport_factory=forbidden)
    app = create_app(store=snapshots.store, editorial=(control, verifier))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://local-check') as client:
        path = '/api/editorial/increase/context'
        assert (await client.post(path, json={'at_ms': 780000})).status_code == 401
        assert (await client.post(path, json={'at_ms': 780000},
                                 headers={'Authorization': 'Bearer invalid'})).status_code == 401
        headers = {'Authorization': 'Bearer '+token}
        response = await client.post(path, json={'at_ms': 780000}, headers=headers)
        assert response.status_code == 200 and response.json()['eligible']
        assert response.headers['cache-control'] == 'no-store'
        context = await client.post(path, json={'at_ms': 540000}, headers=headers)
        result = await client.post('/api/editorial/increase/run', headers=headers,
            json={'at_ms': 540000, 'fingerprint': context.json()['fingerprint']})
        assert result.status_code == 200 and result.json()['status'] == 'ineligible'
    # The same signed token is denied when its authorized client is not allowed.
    denied_settings = EntraSettings(settings.tenant_id, settings.audience, (settings.audience,))
    denied = EntraVerifier(denied_settings, keys=verifier.keys)
    try:
        await asyncio.to_thread(denied.verify, token)
    except AccessDenied as exc:
        assert exc.status == 403
    else:
        raise AssertionError('Disallowed client was accepted')
    return {'signed_token_verified': True, 'authorized_context_http': 200,
            'missing_token_http': 401, 'invalid_token_http': 401,
            'disallowed_client_status': 403, 'ineligible_request': 'free_factual_fallback',
            'model_calls': 0, 'api_location': 'local ASGI', 'hosted_activation': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('var/editorial-identity-result.json'))
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text())
        settings = EntraSettings(config['tenant_id'], config['api_client_id'], (config['client_client_id'],))
        app = msal.PublicClientApplication(config['client_client_id'],
            authority=f'https://login.microsoftonline.com/{settings.tenant_id}')
        print('Complete the Microsoft sign-in opened in your browser. Tokens will remain in memory.', flush=True)
        result = app.acquire_token_interactive(scopes=[f'api://{settings.audience}/Editorial.Run'],
            timeout=600, prompt='select_account',
            success_template='CounterPress sign-in complete. You can close this tab and return to Codex.',
            error_template='CounterPress sign-in could not complete. Return to Codex for the next step.')
        if 'access_token' not in result:
            codes = [v for v in result.get('error_codes', []) if isinstance(v, int)]
            print('Sign-in did not complete. Microsoft error codes:', codes, flush=True)
            return 1
        report = asyncio.run(check(result['access_token'], settings))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2)+'\n')
        print('PASS: real Entra token, local API authorization, denial checks and zero model calls.', flush=True)
        return 0
    except Exception:
        print('FAIL: identity check did not complete; no private diagnostics printed.', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
