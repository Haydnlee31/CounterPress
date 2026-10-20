"""Explain exactly the selected canonical event, at its available revision."""
from math import hypot
from counterpress.fan.contracts import PlaybackCutoff
from counterpress.personalization.metrics import select_events


def moment_answer(service,plan,request):
    at=request.playback
    events=select_events(service.store.events(plan.match_id),(at.period,at.elapsed_ms))
    event=next((e for e in events if e.event_id==request.event_id),None)
    def unavailable(message):
        return {'status':'clarify','title':'About this moment','text':[message],'facts':[],'actions':[],'visual':None}
    if event is None:
        known=[e for e in service.store.events(plan.match_id) if e.event_id==request.event_id]
        if known and all((e.available_period,e.available_ms)>(at.period,at.elapsed_ms) for e in known):
            return unavailable('This action is still unfolding. Resume the play and ask again when it finishes.')
        return unavailable('This moment is no longer available in this version of the match. Close Footie and reopen the moment.')
    if event.revision!=request.event_revision:
        return unavailable('This moment has been updated. Close Footie and reload the match before asking again.')
    if event.goal_for:
        # An explicit old goal must never become the latest goal at a later cutoff.
        scoped=request.model_copy(update={'playback':PlaybackCutoff(period=event.available_period,elapsed_ms=event.available_ms)})
        return service.match_answer(plan,scoped)
    player=service.store.players[event.player_id]
    name=player.name
    labels={
        ('pass','completed'):('Completed passes','completed the pass'),
        ('pass','complete'):('Completed passes','completed the pass'),
        ('pass','incomplete'):('Unsuccessful passes','couldn’t complete the pass'),
        ('shot','saved'):('Shots saved','had the shot saved'),
        ('shot','off_target'):('Shots off target','sent the shot off target'),
        ('shot','blocked'):('Shots blocked','had the shot blocked'),
        ('shot','woodwork'):('Shots hitting the woodwork','hit the woodwork'),
        ('shot','on_target'):('Shots on target','put the shot on target'),
        ('duel','won'):('Duels won','won the challenge'),
        ('duel','lost'):('Duels lost','lost the challenge'),
    }
    label,verb=labels.get((event.kind,event.outcome),{
        'pass':('Pass attempts','attempted a pass'),'shot':('Shots','took a shot'),
        'carry':('Carries','carried the ball'),'recovery':('Recoveries','won possession'),
        'duel':('Challenges','challenged for the ball'),'pressure':('Pressure events','applied pressure'),
    }.get(event.kind,('Recorded actions','was involved in the play')))
    text=f'{name} {verb}'
    if event.kind=='pass' and event.outcome in ('complete','completed') and event.recipient_id:
        text+=f" to {service.store.players[event.recipient_id].name}"
    scope={'match_id':plan.match_id,'cutoff':at.model_dump(),'window':'selected_event'}
    evidence={'match_id':plan.match_id,'event_id':event.event_id,'revision':event.revision,
              'event_digest':service.store.evidence_digest(plan.match_id,(at.period,at.elapsed_ms))}
    base={'subject_id':event.player_id,'subject_kind':'player','subject_name':name,'scope':scope,'coverage':None,
          'evidence':evidence,'href':f'#football/player/{event.player_id}'}
    facts=[{**base,'metric':'selected_action','label':label,'value':1,'unit':'count'}]
    paragraphs=[text+'.']
    if event.kind=='pass' and event.start and event.end:
        distance=round(hypot(event.end.x-event.start.x,event.end.y-event.start.y),1)
        paragraphs.append(f'The recorded pass travelled {distance:g} metres between its start and end locations.')
        facts.append({**base,'metric':'pass_distance_m','label':'Pass distance','value':distance,'unit':'metres'})
    return {'status':'answered','title':'About this moment','text':paragraphs,'facts':facts,'visual':None,'actions':[]}
