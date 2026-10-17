"""Append-only review decisions; no dependency on presentation or history."""
from typing import Literal
from pydantic import Field
from counterpress.domain.models import Contract, Identifier


class ReviewDecision(Contract):
    decision_id: Identifier
    fingerprint: str = Field(pattern=r'^[a-f0-9]{64}$')
    actor: str = Field(pattern=r'^[a-f0-9]{64}$')
    decision: Literal['approve', 'revoke']
    at_unix_ms: int = Field(ge=0)
