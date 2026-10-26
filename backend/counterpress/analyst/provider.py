"""Native Foundry Responses transport. No model calls occur in this process.

Every invocation gets a fresh, named hosted session; the native director owns
specialist fan-out. Knowing the session ID before sending permits cleanup even
when a response times out. No conversation survives a playback seek.
"""
import asyncio
import json
import os
import re
from typing import Literal
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field


class Reading(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    role: Literal['chance', 'defence', 'control', 'players']
    headline: str = Field(min_length=1, max_length=100)
    explanation: str = Field(min_length=1, max_length=550)
    alternative: str = Field(min_length=1, max_length=240)
    watch_next: str = Field(min_length=1, max_length=240)
    evidence_ids: list[str] = Field(min_length=1, max_length=8)
    metric_ids: list[str] = Field(min_length=1, max_length=8)
    confidence: Literal['low', 'medium', 'high']


def validate_result(result, packet):
    if not isinstance(result, dict):
        raise ValueError('Invalid Analyst result')
    for key in ('snapshot_id', 'match_id', 'cutoff', 'through_sequence'):
        if result.get(key) != packet[key]:
            raise ValueError('Analyst result belongs to another snapshot')
    if result.get('status') not in ('complete', 'partial', 'insufficient_evidence'):
        raise ValueError('Invalid Analyst status')
    rows = result.get('readings')
    if not isinstance(rows, list) or len(rows) > 4:
        raise ValueError('Invalid Analyst readings')
    readings = [Reading.model_validate(row).model_dump() for row in rows]
    if len({r['role'] for r in readings}) != len(readings):
        raise ValueError('Repeated specialist')
    evidence = {e['id'] for e in packet['evidence']}
    metrics = {m['id']: m for m in packet['metrics']}
    for reading in readings:
        if not set(reading['evidence_ids']) <= evidence or not set(reading['metric_ids']) <= metrics.keys():
            raise ValueError('Unknown evidence')
        compound = {mid for signal in packet.get('signals', []) if signal.get('role') == reading['role']
                    for mid in signal.get('metric_ids', [])}
        if any(metrics[mid].get('status') == 'unavailable' or metrics[mid].get('value') is None
               or (metrics[mid].get('role') != reading['role'] and mid not in compound) for mid in reading['metric_ids']):
            raise ValueError('Unsupported metric')
    summary = result.get('summary')
    # The native editor chooses an already-validated reading. No extra claims.
    if summary is not None and summary not in [
        {k: r[k] for k in ('headline', 'explanation', 'evidence_ids', 'metric_ids')} for r in readings
    ]:
        raise ValueError('Unverified summary')
    if bool(readings) == (result['status'] == 'insufficient_evidence'):
        raise ValueError('Inconsistent Analyst result')
    usage = result.get('usage', {})
    if not isinstance(usage, dict) or type(usage.get('model_calls', 0)) is not int or not 0 <= usage.get('model_calls', 0) <= 5:
        raise ValueError('Invalid native execution receipt')
    return {k: result[k] for k in ('snapshot_id', 'match_id', 'cutoff', 'through_sequence', 'status')} | {
        'readings': readings, 'summary': summary,
        'execution': {'runtime': 'foundry_hosted', 'model_calls': usage.get('model_calls', 0)}}


class FoundryAnalyst:
    def __init__(self, endpoint, name, version, manifest_id, credential_factory=None, client_factory=None):
        url = urlsplit(endpoint)
        if (url.scheme != 'https' or not url.hostname or not url.hostname.endswith('.services.ai.azure.com')
                or url.username or url.password or url.query or url.fragment or url.port not in (None, 443)
                or not re.fullmatch(r'/api/projects/[A-Za-z0-9_-]+/?', url.path)):
            raise ValueError('Invalid HTTPS Foundry project configuration')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', name) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', version):
            raise ValueError('Invalid pinned native agent version')
        if not re.fullmatch(r'[a-f0-9]{64}', manifest_id):
            raise ValueError('A reviewed native agent manifest is required')
        self.endpoint, self.name, self.version, self.manifest_id = endpoint.rstrip('/'), name, version, manifest_id
        self.credential_factory = credential_factory
        self.client_factory = client_factory or httpx.AsyncClient

    @classmethod
    def from_env(cls):
        return cls(*(os.environ.get('COUNTERPRESS_ANALYST_' + name, '') for name in
                     ('PROJECT_ENDPOINT', 'AGENT_NAME', 'AGENT_VERSION', 'MANIFEST_ID')))

    def credential(self):
        if self.credential_factory:
            return self.credential_factory()
        from azure.identity.aio import ManagedIdentityCredential, AzureCliCredential
        client_id = os.environ.get('AZURE_OPENAI_MANAGED_IDENTITY_CLIENT_ID') or os.environ.get('AZURE_CLIENT_ID')
        return ManagedIdentityCredential(client_id=client_id) if client_id else AzureCliCredential(process_timeout=10)

    async def analyze(self, snapshot, request):
        from .service import build_dispatch_packet
        packet = build_dispatch_packet(snapshot)
        packet.update(language=request.language, depth=request.depth, focus_player_id=request.focus_player_id)
        raw = json.dumps(packet, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        if len(raw) > 24000:
            raise ValueError('Analyst packet exceeds native limit')
        session_id = str(uuid4())
        async with self.credential() as credential:
            token = await credential.get_token('https://ai.azure.com/.default')
            async with self.client_factory(timeout=httpx.Timeout(115, connect=10), follow_redirects=False) as client:
                headers = {'Authorization': 'Bearer ' + token.token, 'Content-Type': 'application/json'}
                try:
                    payload = {'input': raw, 'stream': False, 'store': False,
                               'agent_reference': {'type': 'agent_reference', 'name': self.name, 'version': self.version},
                               'agent_session_id': session_id}
                    url = f'{self.endpoint}/agents/{self.name}/endpoint/protocols/openai/responses?api-version=v1'
                    async with client.stream('POST', url,
                                             headers=headers, json=payload) as response:
                        response.raise_for_status()
                        content = bytearray()
                        async for chunk in response.aiter_bytes():
                            content.extend(chunk)
                            if len(content) > 65536:
                                raise ValueError('Native response too large')
                    data = json.loads(content)
                    if data.get('status') != 'completed':
                        raise ValueError('Native response incomplete')
                    text = ''.join(part.get('text', '') for item in data.get('output', [])
                                   if item.get('type') == 'message' for part in item.get('content', [])
                                   if part.get('type') == 'output_text')
                    return validate_result(json.loads(text), packet)
                finally:
                    # Stop/delete use a known ID even if inference times out.
                    base = f'{self.endpoint}/agents/{self.name}/endpoint/sessions/{session_id}'
                    async def cleanup():
                        for method, suffix in (('POST', ':stop'), ('DELETE', '')):
                            try:
                                await client.request(method, base + suffix + '?api-version=v1', headers=headers, timeout=4)
                            except (httpx.HTTPError, asyncio.CancelledError):
                                pass  # Configured two-minute idle timeout is the backstop.
                    cleanup_task = asyncio.create_task(cleanup())
                    try:
                        await asyncio.shield(cleanup_task)
                    except asyncio.CancelledError:
                        # Keep the HTTP client open until bounded cleanup ends.
                        await cleanup_task
                        raise
