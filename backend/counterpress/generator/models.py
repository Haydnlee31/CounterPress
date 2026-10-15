"""Private simulator configuration and evaluator-only records."""

from typing import Literal, Self

from pydantic import Field, model_validator

from counterpress.domain.models import Contract, EventReference, Identifier, MatchTime

VERSION = "conditional-possession-v1"
START_MS, END_MS = 180000, 780000


class Tactics(Contract):
    pressure: float = Field(ge=0, le=1, allow_inf_nan=False)
    directness: float = Field(ge=0, le=1, allow_inf_nan=False)
    flank: Literal["left", "centre", "right"]
    escape_skill: float = Field(ge=0, le=1, allow_inf_nan=False)


class Phase(Contract):
    start_ms: int = Field(ge=START_MS, lt=END_MS)
    eastbridge: Tactics
    northport: Tactics


class GeneratorConfig(Contract):
    seed: int = Field(ge=0, le=2**32 - 1)
    phases: tuple[Phase, ...] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def ordered_phases(self) -> Self:
        starts = [phase.start_ms for phase in self.phases]
        if starts[0] != START_MS or starts != sorted(set(starts)):
            raise ValueError("phases must start at 48:00 and have strictly increasing change times")
        return self


class PressureTrial(Contract):
    defending_team_id: Identifier
    start: EventReference
    at: MatchTime
    pressure: float
    outcome: Literal["recovery", "retained", "pending"]
    resolution: EventReference | None


class Evaluation(Contract):
    generator_version: str = VERSION
    match_id: Identifier
    config: GeneratorConfig
    feed_sha256: str
    pressure_trials: tuple[PressureTrial, ...]
    end_state: Literal["controlled", "loose", "restart"]
    coverage_start_ms: int = START_MS
    coverage_end_ms: int = END_MS
    interpretation: str = "Simulator outcomes only; no causal or real-match effectiveness claim."
