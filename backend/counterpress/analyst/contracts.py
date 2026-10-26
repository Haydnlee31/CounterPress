"""Strict public inputs and stable metric families for Analyst Mode."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

Role = Literal['chance', 'defence', 'control', 'players']
ROLES = ('chance', 'defence', 'control', 'players')
MATCH_IDS = ('wyscout-2058017', 'wyscout-2058007', 'synthetic-32fe41c5d304ce68d7d9')


class AnalystCutoff(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    period: Literal[1, 2]
    elapsed_ms: int = Field(ge=0, le=3600000, strict=True)

    @field_validator('period', mode='before')
    @classmethod
    def exact_period(cls, value):
        if type(value) is not int:
            raise ValueError('Period must be an integer')
        return value


class AnalystRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    cutoff: AnalystCutoff
    through_sequence: int | None = Field(default=None, ge=0, le=2147483647, strict=True)
    language: Literal['en', 'zh-Hans'] = 'en'
    depth: Literal['casual', 'analyst'] = 'analyst'
    focus_player_id: str | None = Field(default=None, min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')


TRIGGER_TYPES = ('pass_combo', 'great_pass', 'big_chance', 'goal', 'pressure_spike',
    'card', 'substitution', 'half_time', 'full_time', 'momentum_swing', 'tempo_shift',
    'chaos_phase', 'control_phase', 'stat_check', 'milestone')
