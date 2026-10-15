"""Bound one asynchronous request and commit only against unchanged evidence."""

import asyncio
from collections.abc import Callable
from time import perf_counter, time
from uuid import uuid4

from counterpress.adaptation.azure import DraftProvider, ProviderFailure
from counterpress.adaptation.contracts import AdaptationAttempt, validate_and_render
from counterpress.api.snapshots import SnapshotService
from counterpress.history import History


def utc_ms() -> int:
    return int(time() * 1000)


class AdaptationService:
    def __init__(self, snapshots: SnapshotService, provider: DraftProvider | None, *,
                 timeout_seconds: float = 8, ttl_ms: int = 60000, now: Callable[[], int] = utc_ms):
        if not 0 < timeout_seconds <= 8 or not 0 < ttl_ms <= 60000:
            raise ValueError("deadline must be at most eight seconds and expiry at most sixty seconds")
        self.snapshots, self.provider = snapshots, provider
        self.timeout_seconds, self.ttl_ms, self.now = timeout_seconds, ttl_ms, now

    async def adapt(self, scenario_id: str, at_ms: int) -> AdaptationAttempt:
        snapshot = self.snapshots.snapshot(scenario_id, at_ms)
        packet = snapshot.evidence.packet if snapshot.evidence else None
        started, timer = self.now(), perf_counter()
        expires = started + self.ttl_ms
        history = self.snapshots.history(scenario_id)
        current = history.changes[-1] if history.changes else None
        requests, text = 0, None
        if packet is None:
            status, reason = "ineligible", "no_supported_increase"
        elif current is None or current.insight is None or current.evidence.packet != packet:
            status, reason = "stale", "evidence_superseded_before_request"
        elif self.provider is None:
            status, reason = "unconfigured", "azure_not_configured"
        else:
            subject_name = next(team.name for team in history.fixture.teams if team.team_id == packet.subject_team_id)
            requests = 1
            try:
                # No database transaction spans the network call. Calculations continue normally.
                async with asyncio.timeout(self.timeout_seconds):
                    raw = await self.provider.generate(packet, subject_name, expires)
                text = validate_and_render(raw, packet, subject_name, expires)
                status, reason = "accepted", "validated_approved_wording"
            except TimeoutError:
                status, reason = "timeout", "total_deadline_exceeded"
            except ProviderFailure as exc:
                status, reason = exc.status, exc.reason
            except ValueError:
                status, reason = "invalid", "draft_validation_failed"

        def commit(latest: History | None) -> History:
            nonlocal status, reason, text
            assert latest is not None
            current = latest.changes[-1] if latest.changes else None
            if status == "accepted":
                if current is None or current.insight is None or current.evidence.packet != packet:
                    status, reason, text = "stale", "evidence_changed_before_commit", None
                elif self.now() >= expires:
                    status, reason, text = "expired", "expired_before_commit", None
            attempt = AdaptationAttempt(
                attempt_id=f"adapt-{uuid4()}", status=status, reason=reason,
                evidence_id=packet.evidence_id if packet else None,
                evidence_version=packet.evidence_version if packet else None,
                requested_at=snapshot.state.at, deployment=self.provider.deployment if self.provider else None,
                started_at_unix_ms=started, expires_at_unix_ms=expires,
                duration_ms=max(0, round((perf_counter() - timer) * 1000)), provider_requests=requests, text=text,
            )
            return latest.model_copy(update={"adaptations": (*latest.adaptations, attempt)})

        return self.snapshots.store.transact(scenario_id, commit).adaptations[-1]
