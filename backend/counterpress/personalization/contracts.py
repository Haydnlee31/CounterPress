"""Additive career contracts; existing replay Event v1 is unchanged.

All coordinates attack +x on a 105 x 68 m pitch. Times are milliseconds
within a period. No estimated quantity is labelled as a measured quantity.
"""
from typing import Literal, Self
from pydantic import Field, model_validator
from counterpress.domain.models import Contract, Identifier, PitchPosition


class Club(Contract):
    club_id: Identifier
    name: str
    short_name: str
    featured: bool
    primary_color: str


class Player(Contract):
    player_id: Identifier
    club_id: Identifier
    name: str
    role: Literal['GK', 'DF', 'MF', 'FW']
    number: int = Field(ge=1, le=99)
    featured: bool
    star: bool = False
    birth_year: int = Field(ge=1970, le=2010)
    debut_year: int = 2020
    # Persistent simulated traits; fitted role distributions, not ratings of real people.
    involvement: float = Field(gt=0, le=4)
    passing: float = Field(ge=-.2, le=.2)
    finishing: float = Field(gt=0, le=3)


class Appearance(Contract):
    player_id: Identifier
    club_id: Identifier
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    starter: bool

    @model_validator(mode='after')
    def interval(self) -> Self:
        if self.end_ms <= self.start_ms: raise ValueError('Empty appearance')
        return self


class Fixture(Contract):
    match_id: Identifier
    season: str
    kickoff: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')
    home_id: Identifier
    away_id: Identifier
    competition: str
    featured: bool = False
    source_kind: Literal['calibrated_simulation', 'adapted_archive', 'legacy_simulation']
    minutes_basis: Literal['simulated_intervals', 'source_lineup_minute_precision'] = 'simulated_intervals'
    appearances: tuple[Appearance, ...]
    period_lengths_ms: tuple[int, int] = (2700000, 2700000)
    calibration_version: str | None = None
    seed: int | None = None

    @model_validator(mode='after')
    def lineup(self) -> Self:
        if self.home_id == self.away_id: raise ValueError('A club cannot play itself')
        if any(p<=0 or p>3600000 for p in self.period_lengths_ms):raise ValueError('Invalid regulation period duration')
        ids=[a.player_id for a in self.appearances]
        if len(ids)!=len(set(ids)): raise ValueError('Duplicate appearance')
        if any(a.club_id not in (self.home_id,self.away_id) or a.end_ms>sum(self.period_lengths_ms) for a in self.appearances):
            raise ValueError('Appearance outside fixture')
        return self


class Action(Contract):
    match_id: Identifier
    event_id: Identifier
    revision: int = Field(ge=1)
    delivery_sequence: int = Field(ge=1)
    occurrence_order: int = Field(ge=0)
    period: Literal[1, 2]
    elapsed_ms: int = Field(ge=0)
    available_period: Literal[1, 2]
    available_ms: int = Field(ge=0)
    club_id: Identifier
    player_id: Identifier
    kind: Literal['pass', 'shot', 'carry', 'duel', 'recovery', 'pressure', 'other']
    outcome: str
    start: PitchPosition | None = None
    end: PitchPosition | None = None
    recipient_id: Identifier | None = None
    opponent_id: Identifier | None = None
    goalkeeper_id: Identifier | None = None
    goal_for: Identifier | None = None
    restart: bool = False
    penalty: bool = False
    technique: Literal['ground', 'cross', 'header', 'long'] = 'ground'
    intended_end: PitchPosition | None = None
    flight_ms: int | None = Field(default=None, ge=1, le=30000)
    completion_probability: float | None = Field(default=None, gt=0, lt=1)
    expected_goal_probability: float | None = Field(default=None, gt=0, lt=1)
    estimate_version: str | None = None
    telemetry_basis: Literal['authored_physics', 'unavailable'] = 'unavailable'
    source_reference: str
    retracted: bool = False

    @model_validator(mode='after')
    def coherence(self) -> Self:
        if (self.available_period,self.available_ms)<(self.period,self.elapsed_ms):
            raise ValueError('Availability precedes occurrence')
        if self.kind=='pass' and self.outcome=='completed' and not self.recipient_id:
            # Legacy archive passes can lack recipients: they have a distinct outcome.
            raise ValueError('Generated completed pass needs a recipient')
        if self.recipient_id==self.player_id: raise ValueError('Self pass')
        if self.goal_for and (self.outcome not in ('goal','own_goal') or (self.goal_for==self.club_id)!=(self.outcome=='goal')):
            raise ValueError('Scoring outcome and beneficiary disagree')
        if self.outcome in ('goal','own_goal') and self.goal_for is None:raise ValueError('Goal needs a beneficiary')
        if self.kind=='pass' and self.outcome not in ('completed','complete','incomplete','unknown'):
            raise ValueError('Invalid pass outcome')
        if self.completion_probability is not None and (self.kind!='pass' or self.intended_end is None or not self.estimate_version):
            raise ValueError('Pass estimate requires intended target and model version')
        if self.expected_goal_probability is not None and (self.kind!='shot' or not self.estimate_version):
            raise ValueError('Shot estimate requires model version')
        if self.flight_ms is not None and (self.kind not in ('pass','shot') or not self.start or not self.end or self.telemetry_basis!='authored_physics'):
            raise ValueError('Flight time requires explicit synthetic geometry')
        if self.flight_ms and self.available_period==self.period and self.available_ms<self.elapsed_ms+self.flight_ms:
            raise ValueError('Outcome cannot be available before ball arrival')
        return self


class MatchRecord(Contract):
    fixture: Fixture
    events: tuple[Action, ...]

    @model_validator(mode='after')
    def references(self) -> Self:
        members={a.player_id:a for a in self.fixture.appearances}
        seen=set();orders=set();sequences=set()
        for e in self.events:
            if e.match_id!=self.fixture.match_id: raise ValueError('Wrong match')
            if e.elapsed_ms>self.fixture.period_lengths_ms[e.period-1]:raise ValueError('Event outside period')
            a=members.get(e.player_id)
            if not a or a.club_id!=e.club_id: raise ValueError('Unregistered actor')
            clock=e.elapsed_ms+(self.fixture.period_lengths_ms[0] if e.period==2 else 0)
            if not a.start_ms<=clock<=a.end_ms: raise ValueError('Actor outside appearance')
            for pid,same in ((e.recipient_id,True),(e.opponent_id,False),(e.goalkeeper_id,False)):
                if pid and (pid not in members or (members[pid].club_id==e.club_id)!=same):
                    raise ValueError('Invalid related actor')
                if pid and not members[pid].start_ms<=clock<=members[pid].end_ms:raise ValueError('Related actor outside appearance')
            if e.goal_for and e.goal_for not in (self.fixture.home_id,self.fixture.away_id): raise ValueError('Invalid scoring club')
            if e.event_id in seen or e.occurrence_order in orders or e.delivery_sequence in sequences:
                raise ValueError('Duplicate initial event identity/order/sequence')
            seen.add(e.event_id);orders.add(e.occurrence_order);sequences.add(e.delivery_sequence)
        return self
