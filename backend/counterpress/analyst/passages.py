"""Bounded passages derived from the complete, already cutoff-filtered event stream.

Never stitch the sparse evidence shortlist into a possession. Recipient links,
restarts, intervening opponents and missing outcomes define the boundaries.
These are observed on-ball sequences, not reconstructed off-ball tracking.
"""
from .metrics import COMPLETE, CONTROLLED


def reference(event):
    return f'{event.event_id}:r{event.revision}'


def build_passages(events, cutoff, focus=None):
    groups=[]; chain=[]; links=[]; truncated=False

    def finish(ending):
        nonlocal chain,links,truncated
        if len(chain)>=2:
            groups.append({'id':'passage:'+reference(chain[0])+':'+reference(chain[-1]),
                'club_id':chain[0].club_id,'period':chain[0].period,
                'start_ms':chain[0].elapsed_ms,'end_ms':chain[-1].elapsed_ms,
                'evidence_ids':[reference(e) for e in chain],
                'links':list(links),'ending':ending,'start_truncated':truncated,
                'player_ids':list(dict.fromkeys(e.player_id for e in chain))})
        chain=[];links=[];truncated=False

    for e in events:
        if e.period!=cutoff.period or e.elapsed_ms<=max(0,cutoff.elapsed_ms-300000):
            continue
        if chain:
            previous=chain[-1]
            if (e.restart or e.club_id!=previous.club_id or e.occurrence_order!=previous.occurrence_order+1 or e.elapsed_ms-previous.elapsed_ms>12000):
                finish('opponent_action' if e.club_id!=previous.club_id else 'boundary')
            elif previous.kind=='pass' and previous.recipient_id and previous.recipient_id!=e.player_id:
                finish('recipient_mismatch')
            elif previous.kind in ('carry','recovery','duel') and previous.player_id!=e.player_id:
                finish('holder_changed')
        eligible=(e.goal_for or e.kind in ('pass','shot','recovery') or e.kind=='carry' and e.outcome in CONTROLLED or e.kind=='duel' and e.outcome=='won')
        if not eligible:
            finish('boundary');continue
        if chain:
            previous=chain[-1]
            links.append('recipient' if previous.kind=='pass' and previous.recipient_id==e.player_id else 'same_holder' if previous.kind!='pass' and previous.player_id==e.player_id else 'team_order_only')
        if not chain:truncated=not e.restart and e.kind not in ('recovery','duel')
        chain.append(e)
        if len(chain)>7:
            chain=chain[-7:];links=links[-6:];truncated=True
        if e.goal_for or e.kind=='shot': finish('shot')
        elif e.kind=='pass' and e.outcome not in COMPLETE: finish('incomplete_pass' if e.outcome=='incomplete' else 'unknown_outcome')
    finish('ongoing')
    # Keep distinct recent passages: a focused contribution, a shot, and the latest.
    picked=[]
    for candidates in ([p for p in groups if focus in p['player_ids']] if focus else [],[p for p in groups if p['ending']=='shot'],groups):
        if candidates:
            item=candidates[-1]
            if item not in picked:picked.append(item)
    return sorted(picked,key=lambda p:p['end_ms'])
