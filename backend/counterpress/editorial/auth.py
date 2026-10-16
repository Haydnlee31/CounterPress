"""Single-tenant Entra delegated access tokens, verified independently of proxy headers."""

from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

import jwt


class AccessDenied(Exception):
    def __init__(self, status=401):
        self.status = status


@dataclass(frozen=True)
class EntraSettings:
    tenant_id: str
    audience: str
    client_ids: tuple[str, ...]

    def __post_init__(self):
        try:
            values = (self.tenant_id, self.audience, *self.client_ids)
            if not self.client_ids or any(str(UUID(v)) != v for v in values):
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise ValueError('Entra tenant, API audience and allowed clients must be canonical UUIDs') from None

    @property
    def issuer(self):
        return f'https://login.microsoftonline.com/{self.tenant_id}/v2.0'


class EntraVerifier:
    def __init__(self, settings: EntraSettings, keys=None):
        self.settings = settings
        # Never use a token-provided URL, tenant or algorithm to choose a key server.
        self.keys = keys or jwt.PyJWKClient(
            f'https://login.microsoftonline.com/{settings.tenant_id}/discovery/v2.0/keys',
            lifespan=300, timeout=3, cooldown_duration=30)

    def verify(self, token: str) -> str:
        try:
            if len(token) > 16384 or token.count('.') != 2:
                raise AccessDenied()
            header = jwt.get_unverified_header(token)
            if header.get('alg') != 'RS256' or not isinstance(header.get('kid'), str):
                raise AccessDenied()
            key = self.keys.get_signing_key_from_jwt(token)
            claims = jwt.decode(token, key.key, algorithms=['RS256'],
                audience=self.settings.audience, issuer=self.settings.issuer,
                options={'require': ['exp', 'iat', 'nbf', 'iss', 'aud', 'tid', 'oid', 'ver', 'azp'],
                         'strict_aud': True})
            if claims['ver'] != '2.0' or claims['tid'] != self.settings.tenant_id:
                raise AccessDenied()
            oid = str(UUID(claims['oid']))
            # Scope excludes ID tokens/app-only tokens; role requires an assigned editor.
            scopes, roles = claims.get('scp'), claims.get('roles')
            if (claims['azp'] not in self.settings.client_ids or not isinstance(scopes, str)
                    or 'Editorial.Run' not in scopes.split() or not isinstance(roles, list)
                    or 'CounterPress.Editor' not in roles):
                raise AccessDenied(403)
            return sha256(f'{self.settings.tenant_id}:{oid}'.encode()).hexdigest()
        except jwt.PyJWKClientConnectionError:
            raise AccessDenied(503) from None
        except (jwt.PyJWTError, ValueError, TypeError, KeyError):
            raise AccessDenied() from None
