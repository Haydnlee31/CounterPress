"""Fast editorial turns: one scheduled specialist, then Footie's publication gate.

Only accepted, source-pinned messages enter shared history. No generated prose
is streamed before review. The manager coalesces source minutes; it never queues
old frames or grants the model access to future events.
"""
import hashlib
import json
import math
from pathlib import Path
import re
import time
from typing import Literal

from opentelemetry import trace
from pydantic import BaseModel, ConfigDict, Field

from .discussion import packet_for, strict_schema

MODEL = 'gpt-4.1-mini'
REVIEW_MODEL = 'gpt-5-mini'
REVIEW_OUTPUT_LIMIT = 2000
INPUT_LIMIT = 6000
OUTPUT_LIMIT = 700
FOCUS = {
 'control': 'Explain a change between comparable spells or a mismatch between passing volume and entries or shots. Lead with what changed and why that changes the reading of the match, not a list of totals.',
 'players': 'Respect the supplied player role. For a defender or goalkeeper, recoveries, duels and distribution can matter without shots or assists. For an attacker, consider chance involvement. Use recent versus previous contributions or a specific recorded action to explain what is distinctive. A selected player is an observation focus, not someone to blame for every team event. Do not invent their positioning or tactical assignment. Skip ordinary unchanged pass totals and lists of zero goals, shots or assists.',
 'chance': 'Distinguish getting the ball near goal, taking a shot, hitting the target and scoring. Challenge a colleague’s territorial reading when it has not produced attempts, or show when it has.',
 'defence': 'Look at recorded ball recoveries, duels and turnovers. Connect these to whether the opponent is still getting passes into the box or shots. Do not infer pressing or a defensive formation.',
}
KEYS = {
    'control': {'event_share','passes','pass_accuracy','final_third_entries','box_entries','tempo','momentum'},
    'players': {'passes','passes_completed','pass_accuracy','shots','goals','assists','key_passes','duels_won','recoveries','saves','on_ball_actions'},
    'chance': {'shots','shots_on_target','goals','xg_authored','box_entries'},
    'defence': {'recoveries','duels_won','verified_turnovers','saves'},
}

class Comment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(max_length=600)
    metric_ids: list[str] = Field(max_length=12)
    evidence_ids: list[str] = Field(max_length=8)
    reply_to: Literal['control','players','chance','defence'] | None
    relation: Literal['observation','builds_on','qualifies','challenges']
    visual: Literal['none','momentum','shot_map','heatmap','pass_routes']

class EditorialDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    added_value: Literal['change','contrast','sequence','none']
    new_reading: str = Field(description='What this adds beyond the preceding conversation, not just a changed total. Empty if it repeats a point.')
    unsupported_premises: list[str] = Field(max_length=4)
    publish: bool


class Review(EditorialDecision):
    """Verdict only: the reviewer cannot invent a new, unreviewed final comment."""
    pass


PROMPT = '''You are the {role} in a live football conversation. The audience already sees the statistics cards. Add one useful reading of what is changing; do not read those cards aloud. Write 1–2 short, natural sentences, usually 15–35 words, with at most one numerical comparison. A conclusion is enough; no compulsory question. Reply to a colleague's football point only if adding something genuinely new. Do not announce analyst roles or the review process.
SOURCE is the only factual authority. Cite exact metrics and actions. Preserve the player, club, unit and time window. Compare only equal current/previous windows. Passes are attempts, completed passes are completions. On-ball actions count passes, shots and carries; they exclude defensive actions. A quiet defender is not necessarily playing badly. Small samples do not establish form, ability or quality. Focus on the selected player only for the players role. Other analysts follow their own speciality.
Discuss recorded changes and contrasts, not invented causes, positions, pressure, possession time, intent or off-ball movement. Do not blame a player or demand goals from a defender. Avoid grand claims such as collapsed, decisive, error-free, no influence, or no attacking output. If there is nothing worth adding, use empty text and citations. No IDs or proof annotations in prose. Use source.language. Return JSON.'''
REVIEW = '''You are Footie, the independent publication checker. Decide whether this EXACT candidate should reach fans. Do not write replacement commentary. Source is the only factual authority; earlier conversation is context, never evidence.
Check each claim and citation: quantity, player, club, unit, period, window, comparison and sample size. Pass counts are attempts, not completions. Current and previous can be compared only if equally sized; prefix is the match total, never the preceding spell. On-ball actions count passes, shots and carries, not recoveries, duels or saves. Low on-ball activity does not establish poor defending or overall influence. One failed pass does not establish poor quality. No invented causes, pressure, possession time, off-ball positioning, blame or coaching prescriptions. Aggregate recoveries cannot be said to have caused fewer entries. Reject unsupported performance absolutes or dramatic claims such as error-free, collapsed, no influence or no attacking output.
The audience sees the numbers already. Check that the draft adds a useful change, contrast or linked sequence, not just a statistical inventory. Check against EACH prior comment: updated counts supporting the same old conclusion are repetition. New wording is not a new insight. In new_reading briefly explain the new understanding, or leave it empty if repetitive. In unsupported_premises identify any unsupported claim remaining in the candidate. Do not silently fix one in your mind and approve a different reading. Publish only if the candidate itself is supported and adds value. A plain useful sentence is enough; do not demand a question or boilerplate caveat. Return ONLY the verdict fields.'''


def choose_role(snapshot, history=()):
    minute = snapshot['cutoff']['elapsed_ms']//60000
    recent = [e for e in snapshot['evidence'] if e['period']==snapshot['cutoff']['period'] and e['elapsed_ms']>snapshot['cutoff']['elapsed_ms']-60000]
    if not recent:
        return None
    last=history[-1]['role'] if history else None
    if any(e['kind']=='shot' for e in recent) and last!='chance':
        return 'chance'
    if history:
        eligible=['control']
        focus=snapshot.get('focus_player_id')
        last_player=next((m.get('cutoff') for m in reversed(history) if m['role']=='players'),None)
        # Do not spend a turn recycling a focused player's unchanged totals.
        if not focus or any(e['player_id']==focus and (not last_player or (e['period'],e['elapsed_ms'])>(last_player['period'],last_player['elapsed_ms'])) for e in snapshot['evidence'] if e['period']==snapshot['cutoff']['period'] and e['elapsed_ms']>snapshot['cutoff']['elapsed_ms']-300000):
            eligible.append('players')
        if any(e['kind'] in ('duel','recovery','save') for e in recent):eligible.append('defence')
        if any(e['kind']=='shot' for e in recent):eligible.append('chance')
        # Fast replay skips clock minutes; recency, not minute modulo, prevents starvation.
        last_seen={m['role']:i for i,m in enumerate(history)}
        return min((r for r in eligible if r!=last),key=lambda r:last_seen.get(r,-1),default=eligible[0])
    focus = snapshot.get('focus_player_id')
    if focus and minute%2 and any(e['player_id']==focus for e in recent):
        return 'players'
    role = ('control','players','defence','chance')[minute%4]
    if role=='chance': role='players'
    if role=='defence' and not any(e['kind'] in ('duel','recovery','save') for e in recent): role='control'
    return role


def live_packet(snapshot, role):
    packet = packet_for(snapshot)
    focus = snapshot.get('focus_player_id')
    leaders = sorted([m for m in packet['metrics'] if m.get('player_id') and m['key']=='on_ball_actions' and m['window']=='prefix'], key=lambda m:m['value'], reverse=True)[:2]
    people = {focus} if focus else {m['player_id'] for m in leaders}
    metrics = [m for m in packet['metrics'] if m['key'] in KEYS[role] and (m.get('player_id') in people and m['window'] in ('prefix','current','previous') if role=='players' else not m.get('player_id'))]
    if role!='players':
        metrics=[m for m in metrics if m['window']!='prefix' or m['key'] in ('goals','shots','shots_on_target')]
    windows=packet.get('windows',{})
    current,previous=windows.get('current'),windows.get('previous')
    if not current or not previous or current['end_ms']-current['start_ms']!=previous['end_ms']-previous['start_ms']:
        metrics=[m for m in metrics if m['window']!='previous']
    # The editor has extra macro context, without importing future match totals.
    metrics += [m for m in packet['metrics'] if not m.get('player_id') and m['window']=='current' and m['key'] in ('shots','final_third_entries','box_entries') and m not in metrics]
    # Keep the focused player's latest actions visible even during a long spell
    # from the other side. These still obey snapshot availability/revision limits.
    evidence=packet['evidence'][-8:]
    if role=='players' and focus:
        own=[e for e in snapshot['evidence'] if e['player_id']==focus][-4:]
        evidence=sorted({e['id']:e for e in own+packet['evidence'][-4:]}.values(),key=lambda e:(e['period'],e['elapsed_ms']))
    return {k:packet[k] for k in ('match_id','cutoff','language','depth','focus_player_id','clubs','windows','score')} | {
        'window_meanings':packet['window_meanings'],
        'metrics':[{**m,'label':'Pass attempts' if m['key']=='passes' else m['label']} for m in metrics],'players':[p for p in packet['players'] if p['player_id'] in people],
        'evidence':evidence, 'metric_notes':{'event_share':'Recorded on-ball actions, not possession time','xg_geometry':'Uncalibrated shot-location estimate','heatmap':'Action starts, not tracking','on_ball_actions':'Passes, shots and controlled carries only; excludes recoveries, duels and saves. Not overall involvement.'}}


def check_comment(comment, packet, history, role, *, numeric=True):
    mids={m['id']:m for m in packet['metrics']}; eids={e['id'] for e in packet['evidence']}
    if len(set(comment.metric_ids))!=len(comment.metric_ids) or len(set(comment.evidence_ids))!=len(comment.evidence_ids): raise ValueError('duplicate_reference')
    if not set(comment.metric_ids)<=mids.keys() or not set(comment.evidence_ids)<=eids: raise ValueError('unknown_reference')
    if comment.text and not(comment.metric_ids or comment.evidence_ids): raise ValueError('uncited_comment')
    if comment.reply_to==role or comment.reply_to not in {None}|{m['role'] for m in history}: raise ValueError('unknown_reply')
    if (comment.reply_to is None)!=(comment.relation=='observation'): raise ValueError('invalid_relation')
    if role=='players' and comment.text:
        focus=packet.get('focus_player_id')
        if not any(mids[i].get('player_id') and (not focus or mids[i]['player_id']==focus) for i in comment.metric_ids): raise ValueError('missing_player_reference')
    # Actor attribution and trend windows must survive even an over-permissive editor.
    cited=[mids[i] for i in comment.metric_ids]
    evidence=[e for e in packet['evidence'] if e['id'] in comment.evidence_ids]
    for club in packet.get('clubs',[]):
        if re.search(r'(?<!\w)'+re.escape(club['name'])+r'(?!\w)',comment.text,re.I):
            if not any(m.get('club_id')==club['club_id'] and not m.get('player_id') for m in cited) and not any(e.get('club_id')==club['club_id'] for e in evidence):
                raise ValueError('missing_club_reference')
    for player in packet.get('players',[]):
        names={player['name'],player['name'].split()[-1]}
        if any(len(n)>=4 and re.search(r'(?<!\w)'+re.escape(n)+r'(?!\w)',comment.text,re.I) for n in names):
            if not any(m.get('player_id')==player['player_id'] for m in cited) and not any(e.get('player_id')==player['player_id'] for e in evidence):
                raise ValueError('missing_actor_reference')
    if re.search(r'\b(fell|rose|increased|decreased|declined|reduced|improved)\b|上升|下降|增加|减少',comment.text,re.I):
        pairs=[(a,b) for a in cited for b in cited if a['window']=='current' and b['window']=='previous' and a['key']==b['key'] and a.get('player_id')==b.get('player_id') and a.get('club_id')==b.get('club_id')]
        windows=packet.get('windows',{})
        current,previous=windows.get('current'),windows.get('previous')
        if not pairs or not current or not previous or current['end_ms']-current['start_ms']!=previous['end_ms']-previous['start_ms']: raise ValueError('unsupported_trend')
        values=[(a['value'],b['value']) for a,b in pairs if type(a.get('value')) in (int,float) and type(b.get('value')) in (int,float)]
        if re.search(r'\b(fell|decreased|declined|reduced)\b|下降|减少',comment.text,re.I) and not any(a<b for a,b in values): raise ValueError('unsupported_decline')
        if re.search(r'\b(rose|increased)\b|上升|增加',comment.text,re.I) and not any(a>b for a,b in values): raise ValueError('unsupported_increase')
    if not numeric:return
    if re.search(r'\b[me]\d+\b',comment.text):raise ValueError('reference_in_prose')
    if any(mids[i]['key']=='xg_geometry' for i in comment.metric_ids) and not re.search(r'estimat|heuristic|估|粗略',comment.text,re.I):raise ValueError('unqualified_estimate')
    # Aggregate counts do not identify a causal mechanism or an individual's
    # all-round performance. These are observed false-positive editorial cases.
    if re.search(r'\b(recoveries|turnovers|duels|pass completion)\b[^.!?;]*\b(restricted|prevented|forced|caused|ensured)\b',comment.text,re.I):
        raise ValueError('aggregate_causal_claim')
    if re.search(r'\b(error[‐‑–-]?free|no attacking output|no influence|no impact)\b',comment.text,re.I):
        raise ValueError('unsupported_performance_absolute')
    # Numeric membership is an extra check, not a substitute for Footie's semantic review.
    allowed=set()
    for metric_id in comment.metric_ids:
        window=packet.get('windows',{}).get(mids[metric_id]['window'])
        if window:
            allowed.add((window['end_ms']-window['start_ms'])/60000)
    cited=[mids[i] for i in comment.metric_ids]
    for m in cited:
        value=m.get('value')
        if type(value) in (int,float) and math.isfinite(value):allowed.update((float(value),round(value),round(value,1),round(value,2)))
    for a in cited:
        for b in cited:
            if a['key']==b['key'] and a.get('player_id')==b.get('player_id') and a.get('club_id')==b.get('club_id') and {a['window'],b['window']}=={'current','previous'} and type(a['value']) in (int,float) and type(b['value']) in (int,float):
                allowed.update((round(abs(a['value']-b['value']),1),round(abs(a['value']-b['value']),2)))
    numbers=[float(x) for x in re.findall(r'(?<![\w])\d+(?:\.\d+)?',comment.text)]
    if any(not any(abs(n-v)<.001 for v in allowed) for n in numbers):raise ValueError('unsupported_number')


def guard_live_request(body):
    import tiktoken
    from counterpress.adaptation.azure import ProviderFailure
    # Includes the serialized response schema and a provider framing reserve.
    if len(tiktoken.get_encoding('o200k_base').encode(body.decode(),disallowed_special=()))+768>INPUT_LIMIT:
        raise ProviderFailure('invalid','live_input_budget_exceeded')


class AzureLiveDiscussion:
    live = True
    def __init__(self,config,transport=None):
        self.config=config.model_copy(update={'deployment':MODEL});self.transport=transport
        self.manifest_id=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

    async def analyze(self,snapshot,request,history=()):
        from counterpress.assistant.planner import structured_request
        role=choose_role(snapshot,history); started=time.monotonic();calls=[];attempts=0
        result={k:snapshot[k] for k in ('snapshot_id','match_id','cutoff','through_sequence')}|{'status':'insufficient_evidence','messages':[],'readings':[],'summary':None,'metrics':[],'evidence':[],'protocol':'live-desk-v1'}
        if role is None:return result
        source=live_packet(snapshot,role)
        # Short source-local IDs prevent copying errors; canonical IDs never change.
        references={}
        for field,prefix in (('metrics','m'),('evidence','e')):
            rows=[]
            for i,item in enumerate(source[field],1):
                ref=f'{prefix}{i}';references[ref]=item['id'];rows.append({**item,'id':ref})
            source[field]=rows
        past=[{k:m[k] for k in ('role','text','cutoff')} for m in history[-3:]]
        async def call(name,prompt,data,model):
            nonlocal attempts
            attempts+=1
            with trace.get_tracer(__name__).start_as_current_span('footie.analyst.live.'+name) as span:
                span.set_attribute('footie.snapshot_id',snapshot['snapshot_id']);span.set_attribute('footie.role',name)
                schema=strict_schema(model)
                for field in ('metric_ids','evidence_ids'):
                    if field not in schema['properties']: continue
                    schema['properties'][field]['items']['enum']=[m['id'] for m in source['metrics' if field=='metric_ids' else 'evidence']] or ['no_reference_available']
                if 'reply_to' in schema['properties']:
                    schema['properties']['reply_to']={'enum':[None]+sorted({m['role'] for m in past if m['role']!=role})}
                config=self.config.model_copy(update={'deployment':REVIEW_MODEL}) if name=='footie' else self.config
                span.set_attribute('gen_ai.operation.name','chat');span.set_attribute('gen_ai.provider.name','azure.ai.openai');span.set_attribute('gen_ai.request.model',config.deployment)
                raw,usage=await structured_request(config,self.transport,prompt,data,schema,'live_'+name,REVIEW_OUTPUT_LIMIT if name=='footie' else OUTPUT_LIMIT,18 if name=='footie' else 10,reasoning_effort='low' if name=='footie' else None,request_guard=guard_live_request)
                span.set_attribute('gen_ai.usage.input_tokens',usage.get('prompt_tokens',0));span.set_attribute('gen_ai.usage.output_tokens',usage.get('completion_tokens',0))
                calls.append({'role':name,'input_tokens':usage.get('prompt_tokens',0),'output_tokens':usage.get('completion_tokens',0)})
                return model.model_validate_json(raw)
        try:
            draft=await call(role,PROMPT.format(role=role)+'\nYOUR SPECIALISM: '+FOCUS[role],{'source':source,'conversation':past},Comment)
            if draft.text:
                # Normalize presentation metadata BEFORE the review. The exact
                # reviewed prose and citations are the only version published.
                text=re.sub(r'\s*[\[(]\s*[me]\d+(?:\s*,\s*[me]\d+)*\s*[\])]', '', draft.text)
                draft=draft.model_copy(update={'text':text})
                if draft.reply_to is None or draft.relation=='observation':
                    draft=draft.model_copy(update={'reply_to':None,'relation':'observation'})
                review=await call('footie',REVIEW,{'source':source,'conversation':past,'candidate':draft.model_dump(),'specialist':role},Review)
                if review.publish and review.added_value!='none' and review.new_reading.strip() and not review.unsupported_premises:
                    check_comment(draft,source,past,role)
                    if not any(m['text'].strip().casefold()==draft.text.strip().casefold() for m in past):
                        draft=draft.model_copy(update={'metric_ids':[references[i] for i in draft.metric_ids],'evidence_ids':[references[i] for i in draft.evidence_ids]})
                        message={'id':role,'role':role,**draft.model_dump(),'verified_by':'footie'}
                        result.update(status='complete',messages=[message],metrics=[{**m,'subject':next((v['subject'] for v in source['metrics'] if references[v['id']]==m['id']),'Match')} for m in snapshot['metrics'] if m['id'] in draft.metric_ids],evidence=[e for e in snapshot['evidence'] if e['id'] in draft.evidence_ids])

        except Exception as exc:
            editorial_rejection=type(exc) is ValueError and re.fullmatch('[a-z_]+',str(exc))
            result['status']='insufficient_evidence' if editorial_rejection else 'unavailable'
            result['failure_reason']=str(exc) if editorial_rejection else type(exc).__name__
        result['execution']={'runtime':'footie_live_turn_manager','model':MODEL,'review_model':REVIEW_MODEL,'model_calls':attempts,'per_role_usage':calls,'input_tokens':sum(c['input_tokens'] for c in calls),'output_tokens':sum(c['output_tokens'] for c in calls),'elapsed_ms':round((time.monotonic()-started)*1000)}
        return result
