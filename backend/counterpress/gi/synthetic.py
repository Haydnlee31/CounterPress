"""Display adapter for a native synthetic Event feed; never invent provider identities."""
import hashlib
import json
from pathlib import Path
from counterpress.fixture import load_fixture
from counterpress.gi.service import Action, Match, Player, Point, Source, Team


def read_synthetic(root: Path, match_id: str) -> Match:
    folder=root/'synthetic'
    source=Source.model_validate_json((folder/'manifest.json').read_text())
    path=folder/'events.json'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=source.fixture_sha256:
        raise ValueError('Synthetic source checksum mismatch')
    feed=load_fixture(path)
    if feed.match_id!=match_id:raise ValueError('Synthetic match ID mismatch')
    ids={'eastbridge':4418,'northport':9598}
    roles={p['player_id']:p['role'] for p in json.loads((root.parent/'personalization'/'registry.json').read_text())['players']}
    players=tuple(Player(player_id=pid,provider_player_id=None,team_id=ids[t.team_id],alias_id=pid,role=roles.get(pid),formation_slot=int(pid[2:])-1) for t in feed.teams for pid in t.player_ids)
    events=[]
    for e in feed.events:
        a=e.action;kind=a.kind;end=getattr(a,'end_position',None)
        outcome=getattr(a,'outcome','unknown')
        detail={'carry':'Acceleration','duel':'Ground attacking duel','recovery':'Possession won','pass':'Simple pass','shot':'Shot'}[kind]
        if kind=='recovery' and a.origin=='restart':detail='Restart'
        events.append(Action(event_id=e.event_id,revision=e.revision,provider_event_id=None,source_order=e.source_delivery_sequence,
            available_period=e.available_at.period,available_ms=e.available_at.elapsed_ms,
            occurrence_order=e.occurrence_order,period=e.occurred_at.period,elapsed_ms=e.occurred_at.elapsed_ms,
            team_id=ids[e.actor.team_id],player_id=e.actor.player_id,kind=kind.title(),detail=detail,
            outcome={'completed':'complete','saved':'on_target'}.get(outcome,outcome),
            start=Point(x=e.position.x,y=e.position.y),end=Point(x=end.x,y=end.y) if end else None,
            goal_for=ids[e.actor.team_id] if kind=='shot' and outcome=='goal' else None,
            review=kind in ('pass','duel') and outcome in ('incomplete','lost') and e.position.x<35,tags=()))
    teams=tuple(Team(team_id=ids[t.team_id],name=t.name,score=sum(e.goal_for==ids[t.team_id] for e in events)) for t in feed.teams)
    return Match(match_id=match_id,synthetic=True,source_label='CounterPress aggregate-calibrated simulation',
        headline='Level again at 75′.',summary='Northport struck first. Eastbridge turned it around, before Northport found the equalizer.',
        teams=teams,players=players,events=tuple(events),source=source,video_url=None,date='',competition='CounterPress fixtures')
