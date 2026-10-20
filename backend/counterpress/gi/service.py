"""Versioned event-backed GI reader. No models, media downloads or cloud writes."""
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MATCH_ID = 'wyscout-2058017'
MATCHES = {
    'synthetic-32fe41c5d304ce68d7d9': {'synthetic': True},
    MATCH_ID: dict(folder='', fixture='france-croatia-2018.json', provider_id=2058017,
        team_map={4418: 4418, 9598: 9598}, score=(4, 2), date='2018-07-15',
        display_date='2026-10-16', source_label='France–Croatia, 2018', headline='Six goals. Eastbridge take it.',
        summary='Northport had more shots. Eastbridge finished with the victory.',
        video='https://www.youtube.com/watch?v=GF-WteOINCc'),
    'wyscout-2058007': dict(folder='comeback', fixture='events.json', provider_id=2058007,
        team_map={5629: 4418, 12913: 9598}, score=(3, 2), date='2018-07-02',
        display_date='2026-10-17', source_label='Belgium–Japan, 2018', headline='Back from two down.',
        summary='Northport led by two. Eastbridge scored three second-half goals to turn the match around.',
        video='https://www.plus.fifa.com/en/content/belgium-v-japan-round-of-16-2018-fifa-world-cup-russia-full-match-replay/91f25d3d-d996-4a3f-a880-5b592de4c13e'),
}


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class Point(Contract):
    x: float = Field(ge=0, le=105)
    y: float = Field(ge=0, le=68)


class Action(Contract):
    event_id: str
    provider_event_id: int | None
    revision: int = 1
    source_order: int
    occurrence_order: int
    period: Literal[1, 2]
    elapsed_ms: int = Field(ge=0)
    available_period: Literal[1,2] | None = None
    available_ms: int | None = Field(default=None,ge=0)
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
    provider_player_id: int | None
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
    alias_sha256: str | None = None
    revision: int
    changes: str


class Match(Contract):
    match_id: str = MATCH_ID
    synthetic: bool = False
    title: str = 'Eastbridge v Northport'
    display_date: str = '2026-10-18'
    source_label: str
    headline: str
    summary: str
    competition: str = 'World Cup final'
    date: str = '2018-07-15'
    teams: tuple[Team, ...]
    players: tuple[Player, ...]
    events: tuple[Action, ...]
    source: Source
    video_url: str | None = 'https://www.youtube.com/watch?v=GF-WteOINCc'
    video_alignment: Literal['unverified'] = 'unverified'
    metric_policy: str = 'Passes exclude restarts. Shots include penalties and free-kick shots. Untagged outcomes remain unknown.'


def read_match(root: Path, match_id: str = MATCH_ID) -> Match:
    config = MATCHES[match_id]
    if config.get('synthetic'):
        from counterpress.gi.synthetic import read_synthetic
        return read_synthetic(root, match_id)
    root = root / config['folder']
    source = Source.model_validate_json((root / 'manifest.json').read_text())
    raw = (root / config['fixture']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != source.fixture_sha256:
        raise ValueError('GI source checksum mismatch')
    records = json.loads(raw)
    alias_bytes=(root / 'aliases.json').read_bytes()
    if source.alias_sha256 and hashlib.sha256(alias_bytes).hexdigest()!=source.alias_sha256:
        raise ValueError('GI alias checksum mismatch')
    aliases = json.loads(alias_bytes)
    if len({e['id'] for e in records}) != len(records):
        raise ValueError('Duplicate provider event ID')
    players = tuple(Player(player_id=f'wyscout-player-{pid}', provider_player_id=int(pid), **alias)
                    for pid, alias in aliases.items())
    lookup = {p.provider_player_id: p for p in players}
    events = []
    ordered = sorted(enumerate(records), key=lambda pair: (pair[1]['matchPeriod'], pair[1]['eventSec'], pair[0]))
    for occurrence, (source_order, event) in enumerate(ordered, 1):
        if event['matchId'] != config['provider_id'] or event['matchPeriod'] not in ('1H', '2H'):
            raise ValueError('Unexpected match or period')
        player = lookup[event['playerId']]
        team_id = config['team_map'][event['teamId']]
        if player.team_id != team_id:
            raise ValueError('Player team mismatch')
        tags = {t['id'] for t in event['tags']}
        shot = event['eventName'] == 'Shot' or event['subEventName'] in ('Penalty', 'Free kick shot')
        outcome = 'unknown'
        goal_for = None
        if 102 in tags:
            outcome = 'own_goal'
            goal_for = 9598 if team_id == 4418 else 4418
        elif shot:
            outcome = ('goal' if 101 in tags else 'blocked' if 2101 in tags else
                       'off_target' if tags & set(range(1210, 1217)) else
                       'woodwork' if tags & set(range(1217, 1224)) else
                       'on_target' if tags & set(range(1201, 1210)) else 'unknown')
            if outcome == 'goal':
                goal_for = team_id
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
                             team_id=team_id, player_id=player.player_id,
                             kind='Shot' if shot else event['eventName'], detail=event['subEventName'],
                             outcome=outcome, start=point(0), end=point(1), goal_for=goal_for,
                             review=2001 in tags, tags=tuple(sorted(tags))))
    teams = tuple(Team(team_id=tid, name=name, score=sum(e.goal_for == tid for e in events))
                  for tid, name in ((4418, 'Eastbridge'), (9598, 'Northport')))
    if tuple(t.score for t in teams) != config['score']:
        raise ValueError('GI score does not reconcile')
    return Match(match_id=match_id, teams=teams, players=players, events=tuple(events), source=source,
                 date=config['date'], display_date=config['display_date'], competition='Match archive', source_label=config['source_label'],
                 headline=config['headline'], summary=config['summary'], video_url=config['video'])
