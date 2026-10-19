"""Versioned UI boundary, separate from the immutable football event contracts."""
from datetime import datetime, timezone
from typing import Literal, Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from counterpress.domain.models import Identifier


class FanContract(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)


class FanPreferences(FanContract):
    version: Literal[1] = 1
    favorite_club_ids: list[Identifier] = Field(default_factory=list, max_length=4)
    favorite_player_ids: list[Identifier] = Field(default_factory=list, max_length=12)
    primary_club_id: Identifier | None = None
    language: Literal['en', 'zh-Hans'] = 'en'
    depth: Literal['casual', 'analyst'] = 'casual'
    metric_focus: Literal['balanced', 'scoring', 'creating', 'passing', 'defending'] = 'balanced'
    focus_player_id: Identifier | None = None

    @field_validator('version', mode='before')
    @classmethod
    def integer_version(cls, value):
        if type(value) is not int:
            raise ValueError('Preference version must be an integer')
        return value

    @field_validator('favorite_club_ids', 'favorite_player_ids')
    @classmethod
    def unique(cls, ids):
        # Sorting means equivalent choices have the same preference identity.
        if len(ids) != len(set(ids)):
            raise ValueError('Favorites must be unique')
        return sorted(ids)

    @model_validator(mode='after')
    def primary_is_followed(self):
        if self.primary_club_id and self.primary_club_id not in self.favorite_club_ids:
            raise ValueError('The primary club must be a favorite club')
        return self


class FanRequest(FanContract):
    preferences: FanPreferences = Field(default_factory=FanPreferences)
    request_id: Identifier = 'default'


class HistoryRequest(FanRequest):
    as_of: str | None = None
    season: Annotated[str, Field(pattern=r'^20\d{2}-\d{2}$')] | None = None

    @field_validator('as_of')
    @classmethod
    def utc_date(cls, value):
        if value is not None:
            parsed = datetime.strptime(value, '%Y-%m-%dT%H:%M:%SZ')
            if parsed.strftime('%Y-%m-%dT%H:%M:%SZ') != value:
                raise ValueError('Use an exact UTC timestamp')
        return value

    def cutoff(self):
        return self.as_of or datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


class HomeRequest(HistoryRequest):
    limit: int = Field(default=9, ge=1, le=12, strict=True)


class CompareRequest(HistoryRequest):
    player_ids: list[Identifier] = Field(min_length=2, max_length=4)

    @field_validator('player_ids')
    @classmethod
    def unique(cls, ids):
        if len(ids) != len(set(ids)):
            raise ValueError('Choose distinct players')
        return ids


class PlaybackCutoff(FanContract):
    period: Literal[1, 2]
    elapsed_ms: int = Field(ge=0, strict=True)

    @field_validator('period', mode='before')
    @classmethod
    def integer_period(cls, value):
        if type(value) is not int:
            raise ValueError('Period must be an integer')
        return value


class MatchRequest(FanRequest):
    cutoff: PlaybackCutoff
    through_sequence: int | None = Field(default=None, ge=0, strict=True)
    card_budget: int = Field(default=3, ge=0, le=5, strict=True)
