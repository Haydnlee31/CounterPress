"""Normalize the three existing library matches without counting highlights twice."""
from pathlib import Path
import json
from .contracts import Action, Appearance, Fixture, MatchRecord
from counterpress.fixture import load_fixture
from counterpress.gi.service import read_match


def native_record(feed,fixture):
    events=[]
    for e in feed.events:
        a=e.action
        events.append(Action(match_id=e.match_id,event_id=e.event_id,revision=e.revision,
            delivery_sequence=e.source_delivery_sequence,occurrence_order=e.occurrence_order,
            period=e.occurred_at.period,elapsed_ms=e.occurred_at.elapsed_ms,
            available_period=e.available_at.period,available_ms=e.available_at.elapsed_ms,
            club_id=e.actor.team_id,player_id=e.actor.player_id,kind=a.kind,outcome=getattr(a,'outcome','established'),
            start=e.position,end=getattr(a,'end_position',None),recipient_id=a.recipient.player_id if getattr(a,'recipient',None) else None,
            opponent_id=a.opponent.player_id if getattr(a,'opponent',None) else None,
            goalkeeper_id=a.goalkeeper.player_id if getattr(a,'goalkeeper',None) else None,
            goal_for=e.actor.team_id if a.kind=='shot' and a.outcome=='goal' else None,
            restart=getattr(a,'origin',None)=='restart',penalty=getattr(a,'situation',None)=='penalty',
            technique=getattr(a,'technique','ground'),source_reference=f'native:{e.match_id}:{e.event_id}:{e.revision}'))
    return MatchRecord(fixture=fixture,events=tuple(events))


def existing_records(root,metadata_path):
    """Original participation uses licensed lineup/substitution metadata."""
    metadata={m['wyId']:m for m in json.loads(metadata_path.read_text())}
    records=[]
    for match_id in ('wyscout-2058017','wyscout-2058007'):
        match=read_match(root/'gi',match_id);aliases={p.player_id:p.alias_id for p in match.players}
        clubs={4418:'eastbridge',9598:'northport'}
        lengths=tuple(max(2700000,max(e.elapsed_ms for e in match.events if e.period==p)+1) for p in (1,2))
        source=metadata[int(match_id.split('-')[1])];starts={};ends={}
        for team in source['teamsData'].values():
            formation=team['formation']
            for p in formation['lineup']:starts[p['playerId']]=0;ends[p['playerId']]=sum(lengths)
            for sub in formation.get('substitutions') or []:
                minute=sub['minute'];at=minute*60000 if minute<=45 else lengths[0]+(minute-45)*60000
                starts[sub['playerIn']]=at;ends[sub['playerIn']]=sum(lengths);ends[sub['playerOut']]=at
        # Substitution metadata is minute-precision. Expand only to include the
        # player's actual event boundary, without inventing second-precision logs.
        appearances=[]
        for p in match.players:
            actions=[e for e in match.events if e.player_id==p.player_id]
            at=[e.elapsed_ms+(lengths[0] if e.period==2 else 0) for e in actions]
            start=min(starts[p.provider_player_id],min(at));end=max(ends[p.provider_player_id],max(at)+1)
            appearances.append(Appearance(player_id=p.alias_id,club_id=clubs[p.team_id],start_ms=start,end_ms=min(sum(lengths),end),starter=start==0))
        fixture=Fixture(match_id=match_id,season='2026-27',kickoff=f'{match.display_date}T15:00:00Z',home_id='eastbridge',away_id='northport',
            competition='CounterPress Showcase Cup',featured=True,source_kind='adapted_archive',minutes_basis='source_lineup_minute_precision',appearances=tuple(appearances),period_lengths_ms=lengths,
            assist_basis='provider_tags',shot_assists_complete=False)
        credits={}
        for index,action in enumerate(match.events):
            if 301 not in action.tags:continue
            # The provider explicitly awarded this assist. Link its next goal;
            # intervening duel/deflection tags are not invented possession losses.
            following=next((g for g in match.events[index+1:] if g.period==action.period and g.goal_for),None)
            if not following or following.goal_for!=action.team_id or following.player_id==action.player_id or not 0<following.elapsed_ms-action.elapsed_ms<=15000:
                raise ValueError('Unresolved source assist; review archive rather than guess')
            if following.event_id in credits:raise ValueError('Multiple assists for one goal')
            credits[following.event_id]=action.event_id
        events=[]
        for e in match.events:
            kind=e.kind.lower() if e.kind.lower() in ('pass','shot','duel','carry','recovery','pressure') else 'carry' if e.detail in ('Acceleration','Touch') else 'other'
            outcome={'complete':'complete','own_goal':'own_goal'}.get(e.outcome,e.outcome)
            if kind=='duel' and outcome!='own_goal':
                outcome='won' if 703 in e.tags else 'lost' if 701 in e.tags else 'draw' if 702 in e.tags else 'unknown'
            events.append(Action(match_id=match_id,event_id=e.event_id,revision=e.revision,delivery_sequence=e.source_order,
                occurrence_order=e.occurrence_order,period=e.period,elapsed_ms=e.elapsed_ms,available_period=e.period,available_ms=e.elapsed_ms,
                club_id=clubs[e.team_id],player_id=aliases[e.player_id],kind=kind,outcome=outcome,
                start=e.start.model_dump() if e.start else None,end=e.end.model_dump() if e.end else None,
                goal_for=clubs[e.goal_for] if e.goal_for else None,penalty=e.detail=='Penalty',
                credited_assist_event_id=credits.get(e.event_id),
                source_reference=f'wyscout:{e.provider_event_id}:cc-by-4.0'))
        records.append(MatchRecord(fixture=fixture,events=tuple(events)))
    feed=load_fixture(root/'gi/synthetic/events.json')
    fixture=Fixture(match_id=feed.match_id,season='2026-27',kickoff='2026-10-18T15:00:00Z',home_id='eastbridge',away_id='northport',
        competition='CounterPress Showcase Cup',featured=True,source_kind='legacy_simulation',
        appearances=tuple(Appearance(player_id=p,club_id=t.team_id,start_ms=0,end_ms=5400000,starter=True) for t in feed.teams for p in t.player_ids))
    records.append(native_record(feed,fixture))
    return records
