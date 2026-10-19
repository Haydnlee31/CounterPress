"""Role-conditioned possession simulation with explicit synthetic flight times.

Source patterns are fitted; lineup rotation, development, form and physics are
documented design assumptions. A seed fixes a match independently of build order.
"""
import math
from random import Random
from .calibration import probability
from .contracts import Action, Appearance, Fixture, MatchRecord
from counterpress.domain.models import PitchPosition


def point(x,y):
    return PitchPosition(x=round(max(0.,min(105.,x)),3),y=round(max(0.,min(68.,y)),3))


def simulate(model,players,home,away,match_id,kickoff,season,seed,featured=False):
    rng=Random(seed);squads={c:[p for p in players if p.club_id==c] for c in (home,away)}
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
    by_id={p.player_id:p for squad in squads.values() for p in squad};by_appearance={a.player_id:a for a in appearances}
    form={c:rng.lognormvariate(-.08**2/2,.08) for c in squads}
    tempo=rng.lognormvariate(-.10**2/2,.10)*model.get('tempo_scale',1.)
    fixture=Fixture(match_id=match_id,season=season,kickoff=kickoff,home_id=home,away_id=away,
        competition='CounterPress League' if not featured else 'CounterPress Showcase Cup',featured=featured,
        source_kind='calibrated_simulation',appearances=tuple(appearances),calibration_version=model['version'],seed=seed)
    events=[];score={c:0 for c in squads};period=1;elapsed=1000;ball=(52.5,34.);last_flight=0

    def clock():return elapsed+(period-1)*2700000
    def active(club):return [by_id[a.player_id] for a in appearances if a.club_id==club and a.start_ms<=clock()<a.end_ms]
    def other(club):return away if club==home else home
    def actor(club,x=52.5,exclude=None,keeper=False):
        candidates=[p for p in active(club) if p.player_id!=exclude]
        if keeper:return next(p for p in candidates if p.role=='GK')
        anchors={'GK':10,'DF':32,'MF':58,'FW':80}
        weights=[p.involvement*math.exp(-((x-anchors[p.role])/40)**2)*(.18 if p.role=='GK' else 1) for p in candidates]
        return rng.choices(candidates,weights)[0]
    holder=actor(home)

    def emit(kind,outcome,**kwargs):
        nonlocal last_flight,holder
        if holder.player_id not in {p.player_id for p in active(holder.club_id)}:holder=actor(holder.club_id,ball[0])
        n=len(events)+1
        event=Action(match_id=match_id,event_id=f'e{n:05}',revision=1,delivery_sequence=n,occurrence_order=n,
            period=period,elapsed_ms=elapsed,available_period=period,available_ms=elapsed+(kwargs.get('flight_ms') or 0)+100,
            club_id=holder.club_id,player_id=holder.player_id,kind=kind,outcome=outcome,start=point(*ball),
            source_reference=f'counterpress:{model["version"]}:{seed}:e{n:05}',**kwargs)
        events.append(event);last_flight=event.flight_ms or 0
        return event
    def switch(restart=False,spot=None,keeper=False):
        nonlocal holder,ball,elapsed
        target=other(holder.club_id);elapsed+=max(600,last_flight)
        ball=spot or (105-ball[0],68-ball[1]);holder=actor(target,ball[0],keeper=keeper)
        emit('recovery','established',restart=restart)
    for period in (1,2):
        elapsed=1000;ball=(52.5,34.);holder=actor(home if period==1 else away)
        emit('carry','controlled',end=point(*ball),restart=True)
        while elapsed<2670000:
            elapsed+=max(1100,last_flight,int(rng.gammavariate(3,model['action_interval_seconds']*tempo/3)*1000))
            if elapsed>=2670000:break
            if holder.player_id not in {p.player_id for p in active(holder.club_id)}:holder=actor(holder.club_id,ball[0])
            x,y=ball;z=min(2,int(x/35));kinds=('pass','carry','duel','shot');counts=model['action_counts'][z]
            ctx=model['action_contexts'].get(f'{z}:{int(x>=83)}:{int(abs(y-34)<=14)}',{})
            weights=[ctx.get(k,0)+10*counts.get(k,0)/max(1,sum(counts.values())) for k in kinds]
            # Role shot involvement is fitted per90; persistent traits control individual variation.
            shot_rates=model['role_rates'];reference=sum(shot_rates[r]['shot']['mean'] for r in ('DF','MF','FW'))/3
            weights[3]*=max(.03,shot_rates[holder.role]['shot']['mean']/max(.1,reference))*holder.involvement*model.get('shot_hazard_scale',.7)
            if x<60:weights[3]=0
            if period==2 and elapsed>2100000 and score[holder.club_id]<score[other(holder.club_id)]:weights[3]*=1.12
            kind=rng.choices(kinds,weights)[0]
            if kind=='pass':
                dx=model['pass_deltas'][f'{z}:x'];dy=model['pass_deltas'][f'{z}:y']
                for _ in range(50):
                    ex=x+rng.gauss(dx['mean'],dx['sd']);ey=y+rng.gauss(dy['mean'],dy['sd'])
                    if 1<ex<104 and 1<ey<67:break
                target=point(max(1,min(104,ex)),max(1,min(67,ey)))
                length=math.dist(ball,(target.x,target.y))
                technique='cross' if x>75 and abs(y-34)>18 and abs(target.y-34)<14 else 'long' if length>32 else 'ground'
                p=max(.05,min(.98,probability(model,'pass',ball,technique)+holder.passing))
                complete=rng.random()<p;recipient=actor(holder.club_id,target.x,exclude=holder.player_id) if complete else None
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
                opponent=actor(other(holder.club_id),105-x);lost=rng.random()<.48
                emit('duel','lost' if lost else 'won',opponent_id=opponent.player_id)
                if lost:
                    holder=opponent;ball=(105-x,68-y);elapsed+=600;emit('recovery','established')
            else:
                base=probability(model,'shot',ball);conversion=min(.85,base*holder.finishing*form[holder.club_id])
                if rng.random()<conversion:outcome='goal'
                else:
                    table=model['shot_non_goal_outcomes'];outcome=rng.choices(list(table),list(table.values()))[0]
                endpoint=point(105,rng.uniform(31,37) if outcome in ('goal','saved') else rng.choice((26,42)))
                if outcome=='blocked':endpoint=point(min(103,x+rng.uniform(2,8)),y+rng.uniform(-3,3))
                speed=max(12,min(35,rng.gauss(24,4)));flight=max(100,math.ceil(math.dist(ball,(endpoint.x,endpoint.y))/speed*1000))
                keeper=actor(other(holder.club_id),keeper=True)
                emit('shot',outcome,end=endpoint,goal_for=holder.club_id if outcome=='goal' else None,goalkeeper_id=keeper.player_id,
                    flight_ms=flight,expected_goal_probability=round(base,6),estimate_version=model['version'],telemetry_basis='authored_physics')
                ball=(endpoint.x,endpoint.y)
                if outcome=='goal':score[holder.club_id]+=1;elapsed+=rng.randint(18000,28000);switch(True,(52.5,34.))
                elif outcome=='blocked':
                    if rng.random()<.5:switch()
                    else:holder=actor(holder.club_id,ball[0])
                else:elapsed+=rng.randint(6000,10000);switch(True,(5.5,34.),keeper=True)
    return MatchRecord(fixture=fixture,events=tuple(events))
