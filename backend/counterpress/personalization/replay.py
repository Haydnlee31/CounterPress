"""Export generated featured matches into the existing Event v1 pitch contract."""
from counterpress.domain.models import Actor,Event,InitialState,MatchTime,PassDetails,ShotDetails,CarryDetails,DuelDetails,RecoveryDetails
from counterpress.fixture import PossessionFixture,Pitch,Team


def native_feed(record,clubs):
    if record.fixture.source_kind=='adapted_archive':raise ValueError('Use the archive replay endpoint for source matches')
    f=record.fixture;events=[];control=f.home_id
    for e in record.events:
        if e.retracted:continue
        actor=Actor(team_id=e.club_id,player_id=e.player_id)
        def add(action,event_id,at,order):
            events.append(Event(match_id=f.match_id,event_id=event_id,revision=1,source_delivery_sequence=len(events)+1,
                occurrence_order=order,occurred_at=MatchTime(period=e.period,elapsed_ms=at),
                available_at=MatchTime(period=e.period,elapsed_ms=max(at,e.available_ms)),actor=actor,position=e.start,action=action))
        if e.kind!='recovery' and e.club_id!=control:
            # Event v1 requires an explicit change of control at second-half kickoff.
            if e.period!=2 or e.elapsed_ms!=1000:raise ValueError('Unexpected possession discontinuity')
            add(RecoveryDetails(kind='recovery',from_team_id=control,control='established',origin='restart'),
                'period-two-kickoff',e.elapsed_ms-1,e.occurrence_order*2-1)
            control=e.club_id
        opponent=f.away_id if e.club_id==f.home_id else f.home_id
        if e.kind=='pass':
            action=PassDetails(kind='pass',outcome=e.outcome,end_position=e.end,
                recipient=Actor(team_id=e.club_id,player_id=e.recipient_id) if e.recipient_id else None,
                technique=e.technique if e.technique in ('ground','cross','header') else 'ground')
        elif e.kind=='shot':
            action=ShotDetails(kind='shot',outcome=e.outcome,end_position=e.end,situation='penalty' if e.penalty else 'open_play',
                goalkeeper=Actor(team_id=opponent,player_id=e.goalkeeper_id) if e.goalkeeper_id else None,
                rebound_position=e.end if e.outcome=='blocked' else None)
        elif e.kind=='carry':action=CarryDetails(kind='carry',end_position=e.end)
        elif e.kind=='duel':action=DuelDetails(kind='duel',opponent=Actor(team_id=opponent,player_id=e.opponent_id),outcome=e.outcome)
        elif e.kind=='recovery':
            action=RecoveryDetails(kind='recovery',from_team_id=control,control='established',origin='restart' if e.restart else 'open_play');control=e.club_id
        else:raise ValueError('Event kind not supported by pitch replay v1')
        add(action,e.event_id,e.elapsed_ms,e.occurrence_order*2)
    return PossessionFixture(schema_version='1.0',synthetic=True,match_id=f.match_id,
        pitch=Pitch(length_m=105,width_m=68,coordinates='actor_team_attacks_positive_x'),
        teams=tuple(Team(team_id=c,name=clubs[c].name,player_ids=tuple(a.player_id for a in f.appearances if a.club_id==c)) for c in (f.home_id,f.away_id)),
        initial_state=InitialState(at=MatchTime(period=1,elapsed_ms=0),score={f.home_id:0,f.away_id:0},controlled_possession_team_id=f.home_id),events=tuple(events))


def highlight_feed(feed,clip):
    ids=set(clip['event_ids']);events=tuple(e for e in feed.events if e.event_id in ids)
    if len(events)!=len(ids) or not events:raise ValueError('Invalid highlight references')
    score=dict(feed.initial_state.score);control=feed.initial_state.controlled_possession_team_id
    for e in feed.events:
        if e.event_id==events[0].event_id:break
        if e.action.kind=='recovery':control=e.actor.team_id
        if e.action.kind=='shot' and e.action.outcome=='goal':score[e.actor.team_id]+=1
    first=events[0]
    return PossessionFixture(schema_version='1.0',synthetic=True,match_id=feed.match_id,pitch=feed.pitch,teams=feed.teams,
        initial_state=InitialState(at=MatchTime(period=first.occurred_at.period,elapsed_ms=max(0,first.occurred_at.elapsed_ms-1)),score=score,controlled_possession_team_id=control),events=events)
