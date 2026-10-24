"""Frozen admission decoder from git revision 7ce9b8 for rollback wire tests.

Plan, Receipt, Job, State, StoryPlan, Task and Identifier are frozen from that revision.
The strict base configuration is frozen too, so new runtime validators cannot
silently teach this decoder to accept the new fields under test.
"""
import math
from typing import Annotated, Literal
from pydantic import BaseModel,ConfigDict,Field,field_validator,model_validator
Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}$")]

class Contract(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True,frozen=True)

FanContract=Contract

class StoryPlan(FanContract):
    lead: str
    supporting: list[str] = Field(max_length=2)

class Task(FanContract):
    role: Literal['match', 'career']
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    scope: Literal['selected', 'pre_match'] = 'selected'

class Plan(FanContract):
    operation: Literal['stats','compare','recent','seasons','club_leaders','match','unsupported','clarify']
    player_ids: list[Identifier] = Field(max_length=4)
    club_id: Identifier | None
    match_id: Identifier | None
    metric: str
    additional_metrics: list[str] = Field(default_factory=list, max_length=2)
    per90: bool
    season: str | None
    comparison_season: str | None

    @model_validator(mode='after')
    def distinct_metrics(self):
        metrics = [self.metric, *self.additional_metrics]
        if len(set(metrics)) != len(metrics):
            raise ValueError('Choose up to three distinct measures')
        if self.additional_metrics and self.operation not in ('stats', 'compare', 'recent', 'seasons', 'club_leaders'):
            raise ValueError('This operation does not support multiple measures')
        return self

    @field_validator('player_ids')
    @classmethod
    def bounded_players(cls, value):
        if len(value)>4 or len(set(value))!=len(value):raise ValueError('Choose up to four distinct players')
        return value


class Receipt(Contract):
    plan: Plan
    selection: StoryPlan
    evidence_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    # Typed task boundaries contain offsets only, never question strings.
    tasks: tuple[Task, ...] = Field(default=(),max_length=2)
    plans: tuple[Plan, ...] = Field(default=(),max_length=2)
    partial_failures: tuple[str, ...] = Field(default=(),max_length=3)

    @model_validator(mode='after')
    def bundle_shape(self):
        if len(self.tasks)!=len(self.plans) or self.plans and self.plans[0]!=self.plan:
            raise ValueError('Invalid cached evidence bundle')
        if len({t.role for t in self.tasks})!=len(self.tasks):raise ValueError('Repeated cached specialist')
        if any(r not in ('match:planning_failed','career:planning_failed','match:scope_rejected','career:scope_rejected','match:scope_unavailable','career:scope_unavailable','orchestrator:selection_failed') for r in self.partial_failures):
            raise ValueError('Invalid partial outcome')
        return self


class Job(Contract):
    owner: str
    until: float
    state: Literal['pending', 'done'] = 'pending'
    receipt: Receipt | None = None


class State(Contract):
    version: Literal[1] = 1
    # Two slots per admitted research job; at most twenty in the rolling hour.
    reservations: tuple[float, ...] = Field(default=(), max_length=10)
    # Legacy entries each mean two slots. New weighted records retain 24 hours.
    weighted: tuple[tuple[float,int], ...] = Field(default=(),max_length=1000)
    jobs: dict[str, Job] = Field(default_factory=dict, max_length=1000)

    @model_validator(mode='after')
    def valid_reservations(self):
        if any(not math.isfinite(at) for at in self.reservations) or any(not math.isfinite(at) or n not in (2,4) for at,n in self.weighted):
            raise ValueError('Invalid reservation')
        return self
