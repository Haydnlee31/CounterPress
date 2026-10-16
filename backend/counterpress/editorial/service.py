"""Explicit single-editor requests with shared admission and revision-bound reuse."""

import asyncio
from contextlib import suppress
from hashlib import sha256
import json
from typing import Literal

import httpx2
from pydantic import Field

from counterpress.adaptation.azure import ProviderFailure
from counterpress.adaptation.service import utc_ms
from counterpress.audience import ViewingPreferences
from counterpress.domain.models import Contract
from counterpress.recaps import SegmentRecap
from counterpress.recap_adaptation import fingerprint
from counterpress.workflow.recap_contracts import RecapWorkflowView
from counterpress.workflow.single_editor import SingleEditorService


class ContextRequest(Contract):
    at_ms: int = Field(ge=180000)
    preferences: ViewingPreferences = ViewingPreferences()


class EditorialRequest(ContextRequest):
    fingerprint: str = Field(pattern=r'^[a-f0-9]{64}$')


class EditorialContext(Contract):
    fingerprint: str
    eligible: bool
    recap: SegmentRecap


class EditorialResult(Contract):
    status: Literal['completed', 'cached', 'pending', 'ineligible', 'stale', 'quota_exceeded', 'busy', 'fallback']
    fingerprint: str
    recap: SegmentRecap
    workflow: RecapWorkflowView | None = None


def snapshot_context(snapshot):
    return EditorialContext(
        fingerprint=fingerprint(snapshot.recap, snapshot.state.score, snapshot.history_version),
        eligible=snapshot.recap.state == 'ready' and snapshot.recap.cutoff == snapshot.replay_end,
        recap=snapshot.recap)


class AdmittedTransport(httpx2.AsyncBaseTransport):
    def __init__(self, controller, scenario, request, key, owner, inner):
        self.controller, self.scenario, self.request = controller, scenario, request
        self.key, self.owner, self.inner = key, owner, inner

    async def handle_async_request(self, request):
        # A strict payload ceiling makes the lifetime request allowance bounded.
        body = json.loads(request.content)
        limit = body.get('max_completion_tokens', body.get('max_tokens'))
        if len(request.content) > 65536 or type(limit) is not int or not 0 < limit <= 650 or body.get('stream'):
            raise ProviderFailure('budget_exhausted', 'editorial_payload_limit')
        context = await self.controller.context(self.scenario, self.request.at_ms, self.request.preferences)
        if not context.eligible or context.fingerprint != self.request.fingerprint:
            raise ProviderFailure('stale', 'evidence_changed_before_dispatch')
        allowed = await asyncio.to_thread(self.controller.ledger.dispatch, self.key, self.owner, self.controller.now())
        if not allowed:
            raise ProviderFailure('budget_exhausted', 'editorial_lease_unavailable')
        return await self.inner.handle_async_request(request)

    async def aclose(self):
        await self.inner.aclose()


class RevisionBoundEditor(SingleEditorService):
    def __init__(self, *args, expected, **kwargs):
        super().__init__(*args, **kwargs)
        self.expected = expected

    async def _graph(self, scenario, history, recap, score, key, budget):
        if key != self.expected:
            raise ProviderFailure('stale', 'evidence_changed_before_start')
        return await super()._graph(scenario, history, recap, score, key, budget)


class EditorialController:
    def __init__(self, snapshots, config, ledger, *, transport_factory=None, now=utc_ms, poll_seconds=.25):
        self.snapshots, self.config, self.ledger, self.now = snapshots, config, ledger, now
        self.transport_factory = transport_factory or (lambda: httpx2.AsyncHTTPTransport(retries=0))
        self.poll_seconds = poll_seconds
        # A deployment change cannot reuse old wording; quota remains global.
        self.variant = sha256(f'{SingleEditorService.prompt_version}:{config.endpoint}:{config.deployment}'.encode()).hexdigest()

    async def snapshot(self, scenario, at_ms, prefs):
        return await asyncio.to_thread(self.snapshots.snapshot, scenario, at_ms, preferences=prefs)

    async def context(self, scenario, at_ms, prefs):
        return snapshot_context(await self.snapshot(scenario, at_ms, prefs))

    async def _result(self, status, scenario, request, attempt_id=None):
        snapshot = await self.snapshot(scenario, request.at_ms, request.preferences)
        context = snapshot_context(snapshot)
        if context.fingerprint != request.fingerprint:
            status = 'stale'
        # Read from canonical history, never trust a ledger entry as presentation evidence.
        view = snapshot.recap_workflow
        applied = (status in ('completed', 'cached') and view and view.applied
                   and view.attempt_id == attempt_id)
        return EditorialResult(status=status, fingerprint=context.fingerprint,
            recap=snapshot.adapted_recap if applied else snapshot.recap,
            workflow=view if view and view.attempt_id == attempt_id else None)

    async def run(self, scenario, request: EditorialRequest, editor: str):
        context = await self.context(scenario, request.at_ms, request.preferences)
        if context.fingerprint != request.fingerprint:
            return await self._result('stale', scenario, request)
        if not context.eligible:
            return await self._result('ineligible', scenario, request)
        key = sha256(f'{scenario}:{self.variant}:{context.fingerprint}'.encode()).hexdigest()
        status, job = await asyncio.to_thread(self.ledger.reserve, key, editor, self.now())
        if status != 'reserved':
            return await self._result(status, scenario, request, job.attempt_id if job else None)
        attempt = None
        task = None
        outcome = 'fallback'
        try:
            service = RevisionBoundEditor(self.snapshots, self.config, expected=request.fingerprint,
                transport_factory=lambda: AdmittedTransport(self, scenario, request, key, job.owner, self.transport_factory()))
            task = asyncio.create_task(service.run(scenario, request.at_ms, request.preferences))
            while not task.done():
                done, _ = await asyncio.wait({task}, timeout=self.poll_seconds)
                if done:
                    break
                current = await self.context(scenario, request.at_ms, request.preferences)
                if current.fingerprint != request.fingerprint:
                    outcome = 'stale'
                    break
            if task.done():
                attempt = task.result()
                outcome = 'completed' if attempt.status in ('accepted', 'narrowed') else 'stale' if attempt.status == 'stale' else 'fallback'
        finally:
            if task and not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            # Unknown/aborted provider usage is never refunded. Crash recovery uses the lease.
            await asyncio.to_thread(self.ledger.finish, key, job.owner, self.now(), attempt)
        return await self._result(outcome, scenario, request, attempt.attempt_id if attempt else None)
