"""Validate an ordered initial-revision fixture; not a replay engine."""

import argparse
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from counterpress.domain.models import (
    Actor, Contract, DuelDetails, Event, Identifier, InitialState,
    PassDetails, RecoveryDetails,
)


class Pitch(Contract):
    length_m: Literal[105]
    width_m: Literal[68]
    coordinates: Literal["actor_team_attacks_positive_x"]


class Team(Contract):
    team_id: Identifier
    name: str = Field(min_length=1)
    player_ids: tuple[Identifier, ...] = Field(min_length=1)


class PossessionFixture(Contract):
    schema_version: Literal["1.0"]
    synthetic: Literal[True]
    match_id: Identifier
    pitch: Pitch
    teams: tuple[Team, Team]
    initial_state: InitialState
    events: tuple[Event, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def valid_initial_sequence(self) -> Self:
        rosters = {team.team_id: set(team.player_ids) for team in self.teams}
        players = [player for team in self.teams for player in team.player_ids]
        if len(rosters) != 2 or len(players) != len(set(players)):
            raise ValueError("team and player identities must be unique")
        if set(self.initial_state.score) != set(rosters):
            raise ValueError("initial score must name exactly the fixture teams")
        control = self.initial_state.controlled_possession_team_id
        if control not in rosters:
            raise ValueError("initial possession team must be in the fixture")

        def check_actor(actor: Actor) -> None:
            if actor.player_id not in rosters.get(actor.team_id, set()):
                raise ValueError("actor must be a registered player on their team")

        ids: set[str] = set()
        orders: set[int] = set()
        previous_time = self.initial_state.at.key()
        previous_occurrence = (*previous_time, -1)
        previous_availability = previous_time
        previous_sequence = 0
        for event in self.events:
            if event.match_id != self.match_id:
                raise ValueError("event must belong to the fixture match")
            if event.revision != 1:
                raise ValueError("ordered fixture supports initial revisions only")
            if event.event_id in ids or event.occurrence_order in orders:
                raise ValueError("fixture event IDs and occurrence orders must be unique")
            if event.source_delivery_sequence <= previous_sequence:
                raise ValueError("fixture delivery sequences must increase")
            occurrence = (*event.occurred_at.key(), event.occurrence_order)
            if occurrence <= previous_occurrence:
                raise ValueError("fixture occurrence times must be ordered after initial state")
            if event.available_at.key() < previous_availability:
                raise ValueError("fixture availability must follow delivery order")
            check_actor(event.actor)
            action = event.action
            if isinstance(action, PassDetails) and action.recipient:
                check_actor(action.recipient)
            if isinstance(action, DuelDetails):
                check_actor(action.opponent)
                if control not in (event.actor.team_id, action.opponent.team_id):
                    raise ValueError("duel must involve the controlling team")
            elif isinstance(action, RecoveryDetails):
                if action.from_team_id != control:
                    raise ValueError("recovery must name the previous controlling team")
                control = event.actor.team_id
            elif event.actor.team_id != control:
                raise ValueError("pass or carry requires controlled possession")
            ids.add(event.event_id)
            orders.add(event.occurrence_order)
            previous_sequence = event.source_delivery_sequence
            previous_occurrence = occurrence
            previous_availability = event.available_at.key()
        return self


def load_fixture(path: Path) -> PossessionFixture:
    return PossessionFixture.model_validate_json(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    fixture = load_fixture(args.path)
    print(f"VALID: {fixture.match_id} | {len(fixture.events)} synthetic events | pitch 105 x 68 m")
    print("Event IDs: " + ", ".join(event.event_id for event in fixture.events))


if __name__ == "__main__":
    main()
