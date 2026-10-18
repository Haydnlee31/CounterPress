"""Versioned event-backed GI reader. No models, media downloads or cloud writes."""
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MATCH_ID = 'wyscout-2058017'


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class Point(Contract):
    x: float = Field(ge=0, le=105)
    y: float = Field(ge=0, le=68)


class Action(Contract):
    event_id: str
    provider_event_id: int
    revision: int = 1
    source_order: int
    occurrence_order: int
    period: Literal[1, 2]
    elapsed_ms: int = Field(ge=0)
    team_id: int
    player_id: str
    kind: str
    detail: str
    outcome: str
    start: Point | None
    end: Point | None
    goal_for: int | None
    review: bool
    tags: tuple[int, ...]


class Player(Contract):
    player_id: str
    provider_player_id: int
    team_id: int
    alias_id: str


class Team(Contract):
    team_id: int
    name: str
    score: int


class Source(Contract):
    provider: str
    source: str
    license: str
    license_url: str
    match_source: str
    source_archive_sha256: str
    fixture_sha256: str
    revision: int
    changes: str


class Match(Contract):
    match_id: str = MATCH_ID
    title: str = 'France v Croatia'
    competition: str = 'World Cup final'
    date: str = '2018-07-15'
    teams: tuple[Team, ...]
    players: tuple[Player, ...]
    events: tuple[Action, ...]
    source: Source
    video_url: str = 'https://www.youtube.com/watch?v=GF-WteOINCc'
    video_alignment: Literal['unverified'] = 'unverified'
    metric_policy: str = 'Passes exclude restarts. Shots include penalties and free-kick shots. Untagged outcomes remain unknown.'


def read_match(root: Path) -> Match:
    source = Source.model_validate_json((root / 'manifest.json').read_text())
    raw = (root / 'france-croatia-2018.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != source.fixture_sha256:
        raise ValueError('GI source checksum mismatch')
    records = json.loads(raw)
    aliases = json.loads((root / 'aliases.json').read_text())
    if len({e['id'] for e in records}) != len(records):
        raise ValueError('Duplicate provider event ID')
    players = tuple(Player(player_id=f'wyscout-player-{pid}', provider_player_id=int(pid), **alias)
                    for pid, alias in aliases.items())
    lookup = {p.provider_player_id: p for p in players}
    events = []
    ordered = sorted(enumerate(records), key=lambda pair: (pair[1]['matchPeriod'], pair[1]['eventSec'], pair[0]))
    for occurrence, (source_order, event) in enumerate(ordered, 1):
        if event['matchId'] != 2058017 or event['matchPeriod'] not in ('1H', '2H'):
            raise ValueError('Unexpected match or period')
        player = lookup[event['playerId']]
        if player.team_id != event['teamId']:
            raise ValueError('Player team mismatch')
        tags = {t['id'] for t in event['tags']}
        shot = event['eventName'] == 'Shot' or event['subEventName'] in ('Penalty', 'Free kick shot')
        outcome = 'unknown'
        goal_for = None
        if 102 in tags:
            outcome = 'own_goal'
            goal_for = 9598 if event['teamId'] == 4418 else 4418
        elif shot:
            outcome = ('goal' if 101 in tags else 'blocked' if 2101 in tags else
                       'off_target' if tags & set(range(1210, 1217)) else
                       'woodwork' if tags & set(range(1217, 1224)) else
                       'on_target' if tags & set(range(1201, 1210)) else 'unknown')
            if outcome == 'goal':
                goal_for = event['teamId']
        elif event['eventName'] == 'Pass':
            outcome = 'complete' if 1801 in tags else 'incomplete' if 1802 in tags else 'unknown'
        def point(index):
            if len(event['positions']) <= index:
                return None
            pos = event['positions'][index]
            return Point(x=round(pos['x'] * 1.05, 4), y=round(pos['y'] * .68, 4))
        events.append(Action(event_id=f'wyscout-{event["id"]}', provider_event_id=event['id'],
                             source_order=source_order + 1, occurrence_order=occurrence,
                             period=int(event['matchPeriod'][0]), elapsed_ms=round(event['eventSec'] * 1000),
                             team_id=event['teamId'], player_id=player.player_id,
                             kind='Shot' if shot else event['eventName'], detail=event['subEventName'],
                             outcome=outcome, start=point(0), end=point(1), goal_for=goal_for,
                             review=2001 in tags, tags=tuple(sorted(tags))))
    teams = tuple(Team(team_id=tid, name=name, score=sum(e.goal_for == tid for e in events))
                  for tid, name in ((4418, 'France'), (9598, 'Croatia')))
    if tuple(t.score for t in teams) != (4, 2):
        raise ValueError('GI score does not reconcile')
    return Match(teams=teams, players=players, events=tuple(events), source=source)
