"""Model draft and audit contracts, separate from authoritative football facts."""

from typing import Literal

from counterpress.domain.models import Contract, EvidencePacket, Identifier, MatchTime, NonNegativeInt
from counterpress.replay import display_time

PROMPT_VERSION = "recovery-wording-v1"
MAX_TEXT_LENGTH = 240


class Draft(Contract):
    # All fields required. Keep the provider schema to Azure's basic JSON subset.
    evidence_id: str
    evidence_version: int
    subject_team_id: str
    subject_name: str
    baseline_count: int
    current_count: int
    period: int
    baseline_start_ms: int
    baseline_end_ms: int
    current_start_ms: int
    current_end_ms: int
    expires_at_unix_ms: int
    template: Literal["count_first", "window_first"]


def expected_fields(packet: EvidencePacket, subject_name: str, expires_at: int) -> dict:
    return dict(evidence_id=packet.evidence_id, evidence_version=packet.evidence_version,
                subject_team_id=packet.subject_team_id, subject_name=subject_name,
                baseline_count=packet.baseline.value, current_count=packet.current.value,
                period=packet.cutoff.period,
                baseline_start_ms=packet.baseline.window.start.elapsed_ms,
                baseline_end_ms=packet.baseline.window.end.elapsed_ms,
                current_start_ms=packet.current.window.start.elapsed_ms,
                current_end_ms=packet.current.window.end.elapsed_ms,
                expires_at_unix_ms=expires_at)


def validate_and_render(raw: str, packet: EvidencePacket, subject_name: str, expires_at: int) -> str:
    draft = Draft.model_validate_json(raw)
    if draft.model_dump(exclude={"template"}) != expected_fields(packet, subject_name, expires_at):
        raise ValueError("draft facts or expiry do not match the frozen evidence")
    baseline = f"{display_time(packet.baseline.window.start)}–{display_time(packet.baseline.window.end)}"
    current = f"{display_time(packet.current.window.start)}–{display_time(packet.current.window.end)}"
    # Only a template choice comes from the model; every displayed fact comes from code.
    if draft.template == "count_first":
        text = f"{subject_name}: {packet.current.value} high recoveries in {current}, compared with {packet.baseline.value} in {baseline}."
    else:
        text = f"From {current}, {subject_name} recorded {packet.current.value} high recoveries; the {baseline} window had {packet.baseline.value}."
    if len(text) > MAX_TEXT_LENGTH:
        raise ValueError("approved explanation exceeds the display limit")
    return text


class AdaptationAttempt(Contract):
    attempt_id: Identifier
    status: Literal["accepted", "invalid", "refused", "timeout", "provider_error", "stale", "expired", "unconfigured", "ineligible"]
    evidence_id: str | None
    evidence_version: int | None
    requested_at: MatchTime
    deployment: str | None
    prompt_version: str = PROMPT_VERSION
    started_at_unix_ms: NonNegativeInt
    expires_at_unix_ms: NonNegativeInt
    duration_ms: NonNegativeInt
    provider_requests: Literal[0, 1]
    reason: str
    text: str | None = None


class AdaptationView(Contract):
    attempt_id: Identifier
    evidence_id: str
    evidence_version: int
    text: str
    expires_at_unix_ms: int
