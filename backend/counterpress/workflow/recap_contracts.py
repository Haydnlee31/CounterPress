"""Editorial choices are model outputs; football facts remain code-owned."""

from typing import Literal
from pydantic import Field, model_validator

from counterpress.audience import ViewingPreferences
from counterpress.domain.models import Contract, Identifier, MatchTime, NonNegativeInt
from counterpress.workflow.contracts import Action, Status

PROMPT_VERSION = 'recap-analyst-producer-v1'


class StoryIdentity(Contract):
    kind: Literal['recovery', 'pressure', 'contribution']
    insight_id: str
    revision: int
    evidence_id: str


class RecapDecision(Contract):
    fingerprint: str
    decision: Literal['accept', 'narrow', 'reject']
    stories: tuple[StoryIdentity, ...]
    reason: Literal['supported_comparisons', 'focused_subset', 'insufficient_evidence']


class RecapChoice(StoryIdentity):
    template: Literal['brief', 'detailed']


class RecapDraft(Contract):
    fingerprint: str
    language: Literal['en', 'zh-Hans']
    heading: Literal['segment_review', 'key_changes']
    stories: tuple[RecapChoice, ...]


class RecapWorkflowAttempt(Contract):
    attempt_id: Identifier
    status: Status
    fingerprint: str
    match_id: Identifier
    preferences: ViewingPreferences
    citations: tuple[StoryIdentity, ...]
    requested_at: MatchTime
    available_at: MatchTime
    source_history_version: NonNegativeInt
    prompt_version: Literal['recap-analyst-producer-v1', 'recap-single-editor-v1'] = PROMPT_VERSION
    started_at_unix_ms: NonNegativeInt
    expires_at_unix_ms: NonNegativeInt
    duration_ms: NonNegativeInt
    analyst_requests: int = Field(ge=0, le=3)
    producer_requests: int = Field(ge=0, le=1)
    provider_requests: int = Field(ge=0, le=4)
    tool_invocations: int = Field(ge=0, le=3)
    actions: tuple[Action, ...]
    reason: str
    draft: RecapDraft | None = None

    @model_validator(mode='after')
    def coherent_output(self):
        if (self.status in ('accepted', 'narrowed')) != (self.draft is not None):
            raise ValueError('only successful attempts contain a presentation draft')
        if self.provider_requests != self.analyst_requests + self.producer_requests:
            raise ValueError('provider counters must agree')
        if self.draft:
            identities = tuple(StoryIdentity.model_validate(c.model_dump(exclude={'template'})) for c in self.draft.stories)
            if (self.draft.fingerprint != self.fingerprint or self.draft.language != self.preferences.language
                    or not 1 <= len(identities) <= 4 or len(set(c.insight_id for c in identities)) != len(identities)
                    or any(c not in self.citations for c in identities)):
                raise ValueError('draft must reference distinct frozen citations and the requested language')
        return self


class RecapWorkflowView(Contract):
    attempt_id: Identifier
    status: Status
    actions: tuple[Action, ...]
    applied: bool = False
    heading: Literal['segment_review', 'key_changes'] | None = None
    expires_at_unix_ms: NonNegativeInt
