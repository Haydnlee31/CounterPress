"""Role-conditioned possession simulation with explicit synthetic flight times.

Source patterns are fitted; lineup rotation, development, form and physics are
documented design assumptions. A seed fixes a match independently of build order.
"""
import math
from random import Random
from .calibration import probability
from .contracts import Action, Appearance, Fixture, MatchRecord
from counterpress.domain.models import PitchPosition
from .spatial import pass_target, in_box


def point(x,y):
    return PitchPosition(x=round(max(0.,min(105.,x)),3),y=round(max(0.,min(68.,y)),3))


def simulate(model,players,home,away,match_id,kickoff,season,seed,featured=False):
    rng=Random(seed);squads={c:[p for p in players if p.club_id==c] for c in (home,away)}
    # Separate individual variation within a role from the source-fitted role
    # volume. Otherwise one lucky squad-wide trait draw permanently inflates
    # that position's share across every season. Legacy models are unchanged.
    centers={}
    if model.get('spatial',{}).get('center_role_traits') and model['spatial'].get('role_centering_basis')!='appearance_minutes':
        for club,squad in squads.items():
            for role in ('GK','DF','MF','FW'):
                group=[p for p in squad if p.role==role]
                centers[(club,role)]={
                    'involvement':sum(p.involvement*p.creating**.35 for p in group)/len(group),
                    'shooting':sum(p.shooting for p in group)/len(group),
                    'finishing':sum(p.finishing for p in group)/len(group),
                    'creating':sum(p.creating**model['spatial'].get('creator_trait_power',1) for p in group)/len(group)}
    def center(player,trait):return centers.get((player.club_id,player.role),{}).get(trait,1)
    appearances=[]
    for club,squad in squads.items():
        starters=list(squad[:11]);bench=list(squad[11:])
        # Modest rotation with like-for-like broad roles, fixed before kickoff.
        for replacement in list(bench):
            if replacement.role!='GK' and rng.random()<.14:
                old=rng.choice([p for p in starters if p.role==replacement.role])
                starters[starters.index(old)]=replacement;bench.remove(replacement);bench.append(old)
        ends={p.player_id:5400000 for p in starters};starts={p.player_id:0 for p in starters}
        for incoming in bench:
            if incoming.role=='GK':continue
            if rng.random()>.85:continue
            eligible=[p for p in starters if p.role==incoming.role and ends[p.player_id]==5400000]
            if not eligible:continue
            outgoing=rng.choice(eligible)
            dist=model['substitution_minutes'];minute=round(max(46,min(88,rng.gauss(dist['mean'],dist['sd']))))
            at=minute*60000;ends[outgoing.player_id]=at;starts[incoming.player_id]=at;ends[incoming.player_id]=5400000
        appearances.extend(Appearance(player_id=pid,club_id=club,start_ms=start,end_ms=ends[pid],starter=start==0) for pid,start in starts.items())
    if model.get('spatial',{}).get('role_centering_basis')=='appearance_minutes':
        exposure={a.player_id:a.end_ms-a.start_ms for a in appearances}
        for club,squad in squads.items():
            for role in ('GK','DF','MF','FW'):
                group=[p for p in squad if p.role==role and exposure.get(p.player_id,0)>0]
                total=sum(exposure[p.player_id] for p in group)
                if not total:continue
                centers[(club,role)]={name:sum(fn(p)*exposure[p.player_id] for p in group)/total for name,fn in (
                    ('involvement',lambda p:p.involvement*p.creating**.35),
                    ('shooting',lambda p:p.shooting),('finishing',lambda p:p.finishing),
                    ('creating',lambda p:p.creating**model['spatial'].get('creator_trait_power',1)))}
    by_id={p.player_id:p for squad in squads.values() for p in squad};by_appearance={a.player_id:a for a in appearances}
    form_sigma=model.get('form_sigma',.08)*model.get('form_scale',1)
    form={c:rng.lognormvariate(-form_sigma**2/2,form_sigma) for c in squads}
    tempo=rng.lognormvariate(-.10**2/2,.10)*model.get('tempo_scale',1.)
    fixture=Fixture(match_id=match_id,season=season,kickoff=kickoff,home_id=home,away_id=away,
        competition='CounterPress League' if not featured else 'CounterPress Showcase Cup',featured=featured,
        source_kind='calibrated_simulation',appearances=tuple(appearances),calibration_version=model['version'],seed=seed)
    events=[];score={c:0 for c in squads};period=1;elapsed=1000;ball=(52.5,34.);last_flight=0
    shot_setup=None;setup_carry=0.

    def clock():return elapsed+(period-1)*2700000
    def active(club):return [by_id[a.player_id] for a in appearances if a.club_id==club and a.start_ms<=clock()<a.end_ms]
    def other(club):return away if club==home else home
    def actor(club,x=52.5,exclude=None,keeper=False,contest=False,y=None):
        candidates=[p for p in active(club) if p.player_id!=exclude]
        if keeper:return next(p for p in candidates if p.role=='GK')
        if model.get('position_target'):
            candidates=[p for p in candidates if p.role!='GK' or x<=25]
        anchors={'GK':10,'DF':32,'MF':58,'FW':80}
        widths={r:40 for r in anchors}
        if model.get('position_target'):
            anchors={r:model['role_locations'][r]['x']['mean'] for r in anchors}
            widths={r:max(12,model['role_locations'][r]['x']['sd']*1.4) for r in anchors}
        advanced=min(1,max(0,(x-35)/35)) if model.get('position_target') else 1
        weights=[p.involvement*p.creating**(.35 if model.get('position_target') else 1)*model.get('creator_role_scale',{}).get(p.role,1)**advanced*math.exp(-((x-anchors[p.role])/widths[p.role])**2)*(.18 if p.role=='GK' else 1)
                 *model.get('involvement_role_scale',{}).get(p.role,1)
                 *(model.get('duel_role_scale',{}).get(p.role,1) if contest else 1) for p in candidates]
        if centers:weights=[w/center(p,'involvement') for p,w in zip(candidates,weights)]
        if model.get('spatial') and x>70 and abs((ball[1] if y is None else y)-34)>16 and not contest:
            weights=[w*model['spatial']['wide_involvement'].get(p.role,1) for p,w in zip(candidates,weights)]
        return rng.choices(candidates,weights)[0]
    holder=actor(home)

    def emit(kind,outcome,**kwargs):
        nonlocal last_flight,holder,shot_setup,setup_carry
        if holder.player_id not in {p.player_id for p in active(holder.club_id)}:holder=actor(holder.club_id,ball[0])
        n=len(events)+1
        event=Action(match_id=match_id,event_id=f'e{n:05}',revision=1,delivery_sequence=n,occurrence_order=n,
            period=period,elapsed_ms=elapsed,available_period=period,available_ms=elapsed+(kwargs.get('flight_ms') or 0)+100,
            club_id=holder.club_id,player_id=holder.player_id,kind=kind,outcome=outcome,start=point(*ball),
            source_reference=f'counterpress:{model["version"]}:{seed}:e{n:05}',**kwargs)
        events.append(event);last_flight=event.flight_ms or 0
        if shot_setup and (event.period!=shot_setup.period or event.club_id!=shot_setup.club_id or event.restart):shot_setup=None
        if kind=='pass':
            shot_setup=event if outcome=='completed' else None;setup_carry=0.
        elif kind=='carry' and shot_setup and event.start and event.end:
            setup_carry+=math.dist((event.start.x,event.start.y),(event.end.x,event.end.y))
            if setup_carry>10:shot_setup=None
        elif kind in ('duel','shot','recovery'):shot_setup=None
        return event
    def switch(restart=False,spot=None,keeper=False):
        nonlocal holder,ball,elapsed
        target=other(holder.club_id);elapsed+=max(600,last_flight)
        ball=spot or (105-ball[0],68-ball[1]);holder=actor(target,ball[0],keeper=keeper)
        emit('recovery','established',restart=restart)
    def specialist(club,role_weights,creator=False,exclude=None):
        candidates=[p for p in active(club) if p.player_id!=exclude]
        # Normalize within role so formation size does not multiply its fitted share.
        totals={r:sum((p.creating if creator else p.shooting) for p in candidates if p.role==r) for r in ('GK','DF','MF','FW')}
        return rng.choices(candidates,[role_weights.get(p.role,0)*(p.creating if creator else p.shooting)/max(.01,totals[p.role]) for p in candidates])[0]
    def shoot(situation='open_play'):
        nonlocal ball,elapsed,holder,last_flight
        x,y=ball
        source=model.get('population_target',{}).get('situations',{}).get(situation)
        base=source['conversion'] if source and situation!='open_play' else probability(model,'shot',ball)
        conversion=min(.90,base*holder.finishing/center(holder,'finishing')*form[holder.club_id]*model.get('finishing_scale',1.)*model.get('finishing_role_scale',{}).get(holder.role,1))
        if rng.random()<conversion:outcome='goal'
        else:
            table=model.get('shot_non_goal_outcomes_by_role',{}).get(holder.role,model['shot_non_goal_outcomes']);outcome=rng.choices(list(table),list(table.values()))[0]
        endpoint=point(105,rng.uniform(31,37) if outcome in ('goal','saved') else rng.choice((26,42)))
        if outcome=='blocked':endpoint=point(min(103,x+rng.uniform(2,8)),y+rng.uniform(-3,3))
        speed=max(12,min(35,rng.gauss(24,4)));flight=max(100,math.ceil(math.dist(ball,(endpoint.x,endpoint.y))/speed*1000))
        keeper=actor(other(holder.club_id),keeper=True)
        emit('shot',outcome,end=endpoint,goal_for=holder.club_id if outcome=='goal' else None,goalkeeper_id=keeper.player_id,
            flight_ms=flight,expected_goal_probability=round(base,6),estimate_version=model['version'],telemetry_basis='authored_physics',
            penalty=situation=='penalty',situation=situation)
        ball=(endpoint.x,endpoint.y)
        if outcome=='goal':score[holder.club_id]+=1;elapsed+=rng.randint(18000,28000);switch(True,(52.5,34.))
        elif outcome=='blocked':
            if rng.random()<.5:switch()
            else:holder=actor(holder.club_id,ball[0])
        else:elapsed+=rng.randint(6000,10000);switch(True,(5.5,34.),keeper=True)
    for period in (1,2):
        elapsed=1000;ball=(52.5,34.);holder=actor(home if period==1 else away)
        emit('carry','controlled',end=point(*ball),restart=True)
        pieces=[];population_target=model.get('population_target',{})
        for situation,source in population_target.get('situations',{}).items():
            if situation=='open_play':continue
            frequency=population_target['per_match']['corners'] if situation=='corner' else source['shots_per_match']
            scheduled=rng.expovariate(frequency/5400000)
            while scheduled<2640000:
                pieces.append((scheduled,situation));scheduled+=rng.expovariate(frequency/5400000)
        pieces.sort(reverse=True)
        while elapsed<2670000:
            elapsed+=max(1100,last_flight,int(rng.gammavariate(3,model['action_interval_seconds']*tempo/3)*1000))
            if elapsed>=2670000:break
            if holder.player_id not in {p.player_id for p in active(holder.club_id)}:holder=actor(holder.club_id,ball[0])
            if pieces and pieces[-1][0]<=elapsed and elapsed<2640000:
                _,situation=pieces.pop();source=population_target['situations'][situation];club=holder.club_id
                if situation=='corner':
                    holder=specialist(club,population_target['assist_role_share'],creator=True);ball=(104.,rng.choice((1.,67.)))
                    emit('carry','controlled',end=point(*ball),restart=True,situation='corner');elapsed+=1000
                    recipient=specialist(club,source['shot_roles'],exclude=holder.player_id)
                    endpoint=point(rng.uniform(92,100),rng.uniform(28,40));length=math.dist(ball,(endpoint.x,endpoint.y));flight=math.ceil(length/18*1000)
                    complete=rng.random()<.65
                    emit('pass','completed' if complete else 'incomplete',end=endpoint,intended_end=endpoint,recipient_id=recipient.player_id if complete else None,
                         technique='cross',flight_ms=flight,completion_probability=.65,estimate_version=model['version'],telemetry_basis='authored_physics',situation='corner')
                    ball=(endpoint.x,endpoint.y)
                    if not complete:switch();continue
                    holder=recipient;elapsed+=flight+350
                    if rng.random()<min(1,source['shots_per_match']/max(.01,population_target['per_match']['corners']*.65)):shoot('corner')
                else:
                    holder=specialist(club,source['shot_roles']);ball=(94.,34.) if situation=='penalty' else (rng.uniform(76,84),rng.uniform(26,42))
                    emit('carry','controlled',end=point(*ball),restart=True,situation=situation);elapsed+=1200;shoot(situation)
                continue
            x,y=ball;z=min(2,int(x/35));kinds=('pass','carry','duel','shot');counts=model['action_counts'][z]
            ctx=model['action_contexts'].get(f'{z}:{int(x>=83)}:{int(abs(y-34)<=14)}',{})
            weights=[ctx.get(k,0)+10*counts.get(k,0)/max(1,sum(counts.values())) for k in kinds]
            # Role shot involvement is fitted per90; persistent traits control individual variation.
            shot_rates=model['role_rates'];reference=sum(shot_rates[r]['shot']['mean'] for r in ('DF','MF','FW'))/3
            weights[3]*=max(.03,shot_rates[holder.role]['shot']['mean']/max(.1,reference))*holder.shooting/center(holder,'shooting')*model.get('shot_role_scale',{}).get(holder.role,1)*model.get('shot_hazard_scale',.7)
            # A creator's pass changes the next shot opportunity, rather than
            # merely increasing their number of touches. Only causal, intact
            # direct-pass chains can apply this training-fitted role effect.
            if shot_setup and shot_setup.period==period and shot_setup.recipient_id==holder.player_id and elapsed-shot_setup.elapsed_ms<=15000:
                provider=by_id[shot_setup.player_id]
                weights[3]*=model.get('setup_role_scale',{}).get(provider.role,1)*provider.creating**model.get('spatial',{}).get('creator_trait_power',1)/center(provider,'creating')
            if model.get('spatial'):
                weights[3]*=model['spatial']['shot_inside_scale'][holder.role] if in_box(ball) else model['spatial']['shot_outside_scale'][holder.role]
            weights[2]*=model.get('duel_role_scale',{}).get(holder.role,1)
            if x<60 or holder.role=='GK':weights[3]=0
            if period==2 and elapsed>2100000 and score[holder.club_id]<score[other(holder.club_id)]:weights[3]*=1.12
            kind=rng.choices(kinds,weights)[0]
            if kind=='pass':
                dx=model['pass_deltas'][f'{z}:x'];dy=model['pass_deltas'][f'{z}:y']
                for _ in range(50):
                    scale=model.get('pass_length_role_scale',{}).get(holder.role,1)
                    ex=x+rng.gauss(dx['mean'],dx['sd'])*scale;ey=y+rng.gauss(dy['mean'],dy['sd'])*scale
                    if 1<ex<104 and 1<ey<67:break
                target=point(max(1,min(104,ex)),max(1,min(67,ey)))
                if model.get('spatial'):
                    target=point(*pass_target(model,holder.role,ball,rng))
                # Keeper distribution normally reaches the build-up/middle
                # zones; the former unbounded Gaussian made routine passes
                # jump straight into shooting positions.
                if holder.role=='GK' and model.get('position_target'):target=point(min(70,target.x),target.y)
                length=math.dist(ball,(target.x,target.y))
                technique='cross' if x>75 and abs(y-34)>18 and abs(target.y-34)<14 else 'long' if length>32 else 'ground'
                p=max(.05,min(.98,probability(model,'pass',ball,technique)+holder.passing+model.get('pass_role_offset',{}).get(holder.role,0)))
                if model.get('spatial'):
                    p=max(.05,min(.98,p+model['spatial']['long_completion_offset'][holder.role]*(length>=32)))
                complete=rng.random()<p;recipient=actor(holder.club_id,target.x,exclude=holder.player_id,y=target.y) if complete else None
                speed=max(7,min(25,rng.gauss(15 if technique=='ground' else 20,3)))
                flight=max(100,math.ceil(length/speed*1000))
                emit('pass','completed' if complete else 'incomplete',end=target,intended_end=target,recipient_id=recipient.player_id if recipient else None,
                    technique=technique,flight_ms=flight,completion_probability=round(p,6),estimate_version=model['version'],telemetry_basis='authored_physics')
                ball=(target.x,target.y)
                if complete:holder=recipient
                else:switch()
            elif kind=='carry':
                end=point(x+rng.uniform(-2,8),y+rng.uniform(-5,5));emit('carry','controlled',end=end);ball=(end.x,end.y)
                last_flight=math.ceil(math.dist((x,y),ball)/5.5*1000)
            elif kind=='duel':
                opponent=actor(other(holder.club_id),105-x,contest=True)
                outcomes=model.get('duel_outcomes',{'lost':.48,'won':.52});outcome=rng.choices(list(outcomes),list(outcomes.values()))[0]
                emit('duel',outcome,opponent_id=opponent.player_id)
                if outcome=='lost':
                    holder=opponent;ball=(105-x,68-y);elapsed+=600;emit('recovery','established')
            else:shoot()
    return MatchRecord(fixture=fixture,events=tuple(events))
