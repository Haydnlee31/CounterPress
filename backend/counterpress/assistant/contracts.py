from typing import Literal
from pydantic import Field, field_validator, model_validator
from counterpress.fan.contracts import FanContract, HistoryRequest, PlaybackCutoff
from counterpress.domain.models import Identifier


class Plan(FanContract):
    operation: Literal['stats','compare','recent','seasons','club_leaders','match','unsupported','clarify']
    player_ids: list[Identifier]
    club_id: Identifier | None
    match_id: Identifier | None
    metric: str
    per90: bool
    season: str | None
    comparison_season: str | None

    @field_validator('player_ids')
    @classmethod
    def bounded_players(cls, value):
        if len(value)>4 or len(set(value))!=len(value):raise ValueError('Choose up to four distinct players')
        return value


class AskRequest(HistoryRequest):
    question: str = Field(min_length=1,max_length=600)
    player_id: Identifier | None = None
    club_id: Identifier | None = None
    match_id: Identifier | None = None
    playback: PlaybackCutoff | None = Field(default=None, alias="cutoff")
    previous_plan: Plan | None = None
    event_id: Identifier | None = None
    event_revision: int | None = Field(default=None,ge=1)

    @model_validator(mode='after')
    def moment_scope(self):
        if self.event_id is not None or self.event_revision is not None:
            if not self.event_id or self.event_revision is None or not self.match_id or not self.playback:
                raise ValueError('A moment requires its event, revision, match and playback time')
        return self

    @field_validator('question')
    @classmethod
    def nonempty(cls,value):
        if not value.strip():raise ValueError('Ask a football question')
        return value.strip()
