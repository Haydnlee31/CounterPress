"""Recorded starting XIs and substitutions, with explicitly bounded minute timing."""
import hashlib
import json
from pathlib import Path


def enrich_lineups(root: Path, players, events, expected_hash: str):
    raw=(root/'lineups.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_hash:
        raise ValueError('GI lineup checksum mismatch')
    data=json.loads(raw)
    lookup={p.provider_player_id:p for p in players}
    changes={p.player_id:dict(starter=False,role={'MD':'MF'}.get(data['roles'][str(p.provider_player_id)],data['roles'][str(p.provider_player_id)])) for p in players}
    def stamp(event):return (event.period,event.elapsed_ms)
    def moment(t):return dict(period=t[0],elapsed_ms=t[1])
    for team in data['teams']:
        starters=team['starters']
        if len(starters)!=11 or len(set(starters))!=11 or any(pid not in lookup for pid in starters):
            raise ValueError('Invalid recorded starting lineup')
        # Stable tactical slots: goalkeeper first, then broad source roles and average touch side.
        def order(pid):
            p=lookup[pid];role=changes[p.player_id]['role']
            ys=[e.start.y for e in events if e.player_id==p.player_id and e.start]
            return ({'GK':0,'DF':1,'MF':2,'FW':3}[role],sum(ys)/len(ys) if ys else 34,pid)
        slots={pid:i for i,pid in enumerate(sorted(starters,key=order))}
        for pid,slot in slots.items():
            role=changes[lookup[pid].player_id]['role']
            peers=sorted((p for p in starters if changes[lookup[p].player_id]['role']==role),key=order)
            rank=peers.index(pid)
            y=34 if len(peers)==1 else 9+50*rank/(len(peers)-1)
            home=dict(x={'GK':5,'DF':23,'MF':43,'FW':67}[role],y=y)
            changes[lookup[pid].player_id].update(starter=True,formation_slot=slot,formation_position=home)
        for sub in team['substitutions']:
            incoming,outgoing=sub['playerIn'],sub['playerOut']
            if incoming not in lookup or outgoing not in slots:raise ValueError('Unknown lineup substitution')
            incoming_events=[stamp(e) for e in events if e.player_id==lookup[incoming].player_id]
            outgoing_events=[stamp(e) for e in events if e.player_id==lookup[outgoing].player_id]
            nominal=(1,sub['minute']*60000) if sub['minute']<=45 else (2,(sub['minute']-45)*60000)
            # A minute-labelled change must not contradict an incoming touch already recorded.
            at=min(nominal,min(incoming_events)) if incoming_events else nominal
            if outgoing_events and max(outgoing_events)>=at:
                last=max(outgoing_events);at=(last[0],last[1]+1)
            if incoming_events and at>min(incoming_events):raise ValueError('Conflicting substitution evidence')
            slot=slots.pop(outgoing);slots[incoming]=slot
            changes[lookup[outgoing].player_id]['left_at']=moment(at)
            changes[lookup[incoming].player_id].update(entered_at=moment(at),formation_slot=slot,formation_position=changes[lookup[outgoing].player_id]['formation_position'])
    return tuple(type(p).model_validate({**p.model_dump(),**changes[p.player_id]}) for p in players)
