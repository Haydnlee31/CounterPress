"""Bounded, source-scoped memory of conclusions, not a second source of facts."""
import hashlib
import json
import re
from typing import Literal

Topic = Literal['sterile_circulation','territorial_progress','chance_creation','finishing',
                'ball_winning','defensive_exposure','player_link_play','player_chance_involvement','score_vs_play']


def memories(history):
    return [m['memory'] for m in history if m.get('memory') and not m.get('attempt_only')]


def public_memory(history):
    # Repetition checks use all retained records; the model gets a short recent
    # brief plus older topic/subject keys, without copying past statistics as facts.
    latest={}
    for m in memories(history):
        key=(m['topic'],m['subject_id'])
        latest.pop(key,None);latest[key]=m
    rows=list(latest.values())
    return [{'id':m['id'],'topic':m['topic'],'subject_id':m['subject_id'],
             'takeaway':m['takeaway'][:140] if i>=len(rows)-4 else ''}
            for i,m in enumerate(rows)]


def conclusion(review, draft, source, history, references=None):
    references=references or {}
    topic=review.topic
    # Observed cross-role paraphrases of this one conclusion must share a key.
    shot_cited=any(e['kind']=='shot' and e['id'] in draft.evidence_ids for e in source['evidence'])
    if not shot_cited and re.search(r'\b(?:circulat\w*|recycl\w*|possession|pass(?:es|ing)?|recovery|recoveries|build-up|moved play)\b',draft.text,re.I) and re.search(
        r'without (?:threat|danger|penetration)|not (?:progress|produc|creat|threaten)|no (?:shot|box entr|penetration)|haven.t (?:produced|created|turned)|failed to (?:threaten|progress|create)|limited end product|harmless|not progressive',draft.text,re.I):
        topic='sterile_circulation'
    clubs={c['club_id'] for c in source['clubs']}
    players={p['player_id']:p for p in source['players']}
    subject=review.subject_id
    if subject not in clubs|players.keys():raise ValueError('unknown_conclusion_subject')
    # A quiet player's circulation and his club's circulation are the same
    # takeaway. Changing speaker or player name cannot make it new.
    if topic not in ('player_link_play','player_chance_involvement') and subject in players:
        subject=players[subject]['club_id']
    cited=[m for m in source['metrics'] if m['id'] in draft.metric_ids]
    events=[e for e in source['evidence'] if e['id'] in draft.evidence_ids]
    if not any(subject in (m.get('club_id'),m.get('player_id')) for m in cited) and not any(subject in (e.get('club_id'),e.get('goal_for'),e.get('player_id'),e.get('recipient_id')) for e in events):
        raise ValueError('uncited_conclusion_subject')
    old=next((m for m in reversed(memories(history)) if m['topic']==topic and m['subject_id']==subject),None)
    if review.novelty=='repetition':raise ValueError('repeated_conclusion')
    if old:
        if review.prior_memory_id!=old['id']:raise ValueError('uncompared_conclusion')
        if review.novelty=='first':raise ValueError('repeated_conclusion')
        score_changed=old.get('score')!=source['score']
        if topic=='sterile_circulation' and not score_changed:raise ValueError('repeated_conclusion')
        decisive=any(e['kind'] in ('shot','save') and references.get(e['id'],e['id']) not in old.get('evidence_ids',[]) for e in events)
        if review.novelty=='new_outcome' and not (decisive or score_changed):raise ValueError('no_new_outcome')
    elif review.prior_memory_id is not None:
        # References may only name actual earlier memory, never invented IDs.
        if review.prior_memory_id not in {m['id'] for m in memories(history)}:raise ValueError('unknown_memory_reference')
    # Retain mechanism and trend direction to distinguish a real development
    # from another count update or another instance of the same passing pattern.
    mechanism=sorted({(e['kind'],e.get('outcome'),e.get('from_area'),e.get('to_area'),e.get('ball_direction')) for e in events},key=str)
    trends={}
    for a in cited:
        b=next((m for m in source['metrics'] if m['window']=='previous' and a['window']=='current' and m['key']==a['key'] and m.get('club_id')==a.get('club_id') and m.get('player_id')==a.get('player_id')),None)
        if b and type(a.get('value')) in (int,float) and type(b.get('value')) in (int,float):
            trends[a['key']]=(a['value']>b['value'])-(a['value']<b['value'])
    mechanism=json.loads(json.dumps(mechanism))
    if old and not score_changed:
        if review.novelty=='new_mechanism' and mechanism==old.get('mechanism'):raise ValueError('repeated_mechanism')
        if review.novelty=='reversal' and not any(k in old.get('trends',{}) and v and v==-old['trends'][k] for k,v in trends.items()):raise ValueError('unsupported_reversal')
    identity=json.dumps([source['match_id'],source['cutoff'],topic,subject],sort_keys=True)
    return {'id':'memory-'+hashlib.sha256(identity.encode()).hexdigest()[:12],
            'topic':topic,'subject_id':subject,'takeaway':review.new_reading[:240],
            'score':source['score'],'mechanism':mechanism,'trends':trends,
            'evidence_ids':[references.get(i,i) for i in draft.evidence_ids],'novelty':review.novelty}


def compact_context(config,prompt,data,schema,name,tokens,limit=6000):
    """Losslessly compact memory field names only when the request is near its cap.

    The final transport guard still measures actual bytes. Evidence, candidates
    and memory values are never dropped. Older dialogue can roll off only when
    it is not the target of a proposed reply; the latest message always remains.
    """
    import tiktoken
    payload={'model':config.deployment,'messages':[{'role':'system','content':prompt},
        {'role':'user','content':json.dumps(data,ensure_ascii=False)}],
        'response_format':{'type':'json_schema','json_schema':{'name':name,'strict':True,'schema':schema}},
        'max_completion_tokens':tokens,'stream':False,'reasoning_effort':'low'}
    size=len(tiktoken.get_encoding('o200k_base').encode(json.dumps(payload,ensure_ascii=False,separators=(',',':')),disallowed_special=()))+768
    rows=data.get('source',{}).get('conversation_memory')
    if size<limit-200 or not isinstance(rows,list) or not rows:return data
    columns=['id','topic','subject_id','takeaway']
    result={**data,'source':{**data['source'],'conversation_memory':{
        'columns':columns,'rows':[[m[k] for k in columns] for m in rows]}}}
    # Omit notes about metrics absent from this specialist's evidence packet.
    keys={m['key'] for m in data['source'].get('metrics',[])}
    if 'metric_notes' in result['source']:
        result['source']['metric_notes']={k:v for k,v in data['source']['metric_notes'].items() if k in keys}
    protected={c.get('reply_to') for c in data.get('candidates',[])}
    protected.add((data['source'].get('reply_assignment') or {}).get('role'))
    dialogue=list(data.get('conversation',[]))
    while len(dialogue)>1:
        payload['messages'][1]['content']=json.dumps(result,ensure_ascii=False)
        if len(tiktoken.get_encoding('o200k_base').encode(json.dumps(payload,ensure_ascii=False,separators=(',',':')),disallowed_special=()))+768<=limit-100:break
        index=next((i for i,m in enumerate(dialogue[:-1]) if m['role'] not in protected),None)
        if index is None:break
        dialogue.pop(index);result['conversation']=list(dialogue)
    return result
