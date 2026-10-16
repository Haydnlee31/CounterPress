"""Small, auditable decisions; model prose is never a source of football facts."""

from typing import Literal
from pydantic import Field

from counterpress.adaptation.contracts import Draft
from counterpress.domain.models import Contract, EventReference, Identifier, MatchTime, NonNegativeInt

PROMPT_VERSION = "analyst-producer-v1"
Candidate = Literal["recovery_increase", "pressure_effectiveness"]
Status = Literal["accepted", "narrowed", "rejected", "invalid", "refused", "timeout",
                 "budget_exhausted", "provider_error", "stale", "expired", "unconfigured", "ineligible"]


class Decision(Contract):
    decision: Literal["accept", "narrow", "reject"]
    story: Literal["recovery_increase", "none"]
    evidence_id: str | None
    evidence_version: int | None
    reason: Literal["supported_count_comparison", "unsupported_tactical_claim", "no_increase", "insufficient_evidence"]


class ProducerDraft(Draft):
    story: Literal["recovery_increase"]
    audience: Literal["general"]


class Action(Contract):
    label: Literal["Requested comparison", "Checked data quality", "Requested event sequence",
                   "Accepted supported comparison", "Narrowed to recovery counts",
                   "Rejected insufficient evidence", "Prepared explanation", "Used factual fallback",
                   "Discarded stale result", "Requested recap evidence", "Checked recap limitations",
                   "Accepted recap stories", "Narrowed recap stories", "Prepared recap"]
    elapsed_ms: NonNegativeInt


class WorkflowAttempt(Contract):
    attempt_id: Identifier
    status: Status
    candidate: Candidate
    evidence_id: str | None
    evidence_version: int | None
    evidence_references: tuple[EventReference, ...] = ()
    requested_at: MatchTime
    available_at: MatchTime
    source_history_version: NonNegativeInt
    deployment: str | None
    prompt_version: str = PROMPT_VERSION
    started_at_unix_ms: NonNegativeInt
    expires_at_unix_ms: NonNegativeInt
    duration_ms: NonNegativeInt
    analyst_requests: int = Field(ge=0, le=3)
    producer_requests: int = Field(ge=0, le=1)
    provider_requests: int = Field(ge=0, le=4)
    tool_invocations: int = Field(ge=0, le=3)
    actions: tuple[Action, ...]
    reason: str
    text: str | None = None


class WorkflowView(Contract):
    attempt_id: Identifier
    status: Status
    actions: tuple[Action, ...]
