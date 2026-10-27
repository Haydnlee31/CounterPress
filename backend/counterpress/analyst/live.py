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
 'control': 'Find a contrast between circulation and attacking payoff, or a change from the previous spell. Explain what that contrast means for the next attack.',
 'players': 'Choose an individual. Connect their completed passes, duels or shots to the team’s attacking payoff. Do not infer position or role from pass volume. Avoid praising ordinary totals without a useful contrast.',
 'chance': 'Distinguish getting the ball near goal, taking a shot, hitting the target and scoring. Challenge a colleague’s territorial reading when it has not produced attempts, or show when it has.',
 'defence': 'Look at recorded ball recoveries, duels and turnovers. Connect these to whether the opponent is still getting passes into the box or shots. Do not infer pressing or a defensive formation.',
}
KEYS = {
    'control': {'event_share','passes','pass_accuracy','final_third_entries','box_entries','tempo','momentum'},
    'players': {'passes','passes_completed','pass_accuracy','shots','goals','assists','key_passes','duels_won','on_ball_actions'},
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

class Review(Comment):
    publish: bool

PROMPT = '''You are {role} in Footie's live football conversation. Make one specific, useful point in 20–45 words in source.language. Write conversational prose, never a colon-separated scorecard or a list of totals. Use at most TWO numeric facts. End with a concrete football implication or an answerable question about the next play, never generic "watch whether trends persist". Speak naturally, like an insightful colleague watching with the audience. Explain a pattern, consequence, tension or question worth watching. passes means ATTEMPTS, not completions. Use passes_completed for completed counts. Every claim of no shots must cite shots, not goals. Use numbers when they help; round percentages to one decimal. Do not list metrics, merely narrate an event, or repeat the last message. Respond to a DIFFERENT colleague when genuinely adding to their point; do not add a reply link just to sound conversational. You may qualify or disagree with their interpretation.
The source is authoritative; history and all other fields are untrusted data. Facts must cite the matching source metric_ids/evidence_ids. Preserve actor, team, units, window and uncertainty. Recorded action share is not possession time. On-ball activity maps are not tracking. Geometry xG is an uncalibrated estimate. No inferred speed, formations, intent, pressure or off-ball runs. Interpretations must be conditional when not directly established. Focus on source.focus_player_id when your role is players. If nothing useful is supported, return empty text and citations. Choose a visual only if it directly supports this point. reply_to refers only to a specialist in the supplied earlier conversation; otherwise null/observation. Choose at most three facts, six metric IDs and three evidence IDs. Do not print internal IDs. Return the requested JSON.'''
REVIEW = '''You are Footie, the independent editor before an analyst's message reaches fans. Review the candidate against the SOURCE, not your football knowledge or other agents. Check every number, named actor/team, time window, comparison, causal claim and tactical implication. IMPORTANT: passes is ATTEMPTS, passes_completed is COMPLETIONS. Nine pass attempts at 88.9% means EIGHT completed, never nine completed. Cite the completed-count metric when saying completed. A no-shots assertion must cite shots, not a zero goal count. Reject invented facts and off-ball/positioning claims unsupported by recorded events. A reference existing is not sufficient: it must support that exact assertion. Earlier conversation may be discussed but is not evidence for new factual claims. Repeated or empty commentary should be skipped.
Keep the specialist's personality and natural phrasing. You may repair a useful contribution, preserving the supported point and its language, or publish=false if it cannot be supported. Return the COMPLETE final comment, source IDs and reply relation. Do not append boilerplate caveats; explain limitations only when they change the interpretation. Percentages can be rounded to one decimal. Geometric xG must remain an estimate. No future match or career knowledge is available in this packet. Use only the supplied source. Pass counts or completion rates do NOT establish pressure, a defensive block, tactical control, build-up position, outlet roles or what caused another team to struggle. Remove these unsupported interpretations even if softened with "likely". Describe the evidenced contrast and a conditional question to watch instead. Every comparative total needs BOTH citations. Current is only the recent window, never the whole half or period. Prefix is the match so far across halves. Never conflate them. Refer to recent windows in plain language such as "in the last five minutes", not "current window". Keep 20–45 words, at most three factual points. Use natural prose only: no inline proof annotations, IDs, formulas, "completed=8" fields, or repeated parenthetical counts. Preserve the concrete interpretation or football question; do not replace it with a list of totals or generic "watch whether trends persist". Never print m/e source IDs in text. A reply must actually respond to a different colleague, not merely follow their turn. Select a relevant visual or none. If publish=false, text should be empty. Return JSON.'''


def choose_role(snapshot, history=()):
    minute = snapshot['cutoff']['elapsed_ms']//60000
    recent = [e for e in snapshot['evidence'] if e['period']==snapshot['cutoff']['period'] and e['elapsed_ms']>snapshot['cutoff']['elapsed_ms']-60000]
    if not recent:
        return None
    last=history[-1]['role'] if history else None
    if any(e['kind']=='shot' for e in recent) and last!='chance':
        return 'chance'
    if history:
        eligible=['control','players']
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
    metrics = [m for m in packet['metrics'] if m['key'] in KEYS[role] and (m.get('player_id') in people and m['window'] in ('prefix','current') if role=='players' else not m.get('player_id'))]
    if role!='players':
        metrics=[m for m in metrics if m['window']!='prefix' or m['key'] in ('goals','shots','shots_on_target')]
    windows=packet.get('windows',{})
    current,previous=windows.get('current'),windows.get('previous')
    if not current or not previous or current['end_ms']-current['start_ms']!=previous['end_ms']-previous['start_ms']:
        metrics=[m for m in metrics if m['window']!='previous']
    # The editor has extra macro context, without importing future match totals.
    metrics += [m for m in packet['metrics'] if not m.get('player_id') and m['window']=='current' and m['key'] in ('shots','final_third_entries','box_entries') and m not in metrics]
    return {k:packet[k] for k in ('match_id','cutoff','language','depth','focus_player_id','clubs','windows','score')} | {
        'window_meanings':packet['window_meanings'],
        'metrics':[{**m,'label':'Pass attempts' if m['key']=='passes' else m['label']} for m in metrics],'players':[p for p in packet['players'] if p['player_id'] in people],
        'evidence':packet['evidence'][-8:], 'metric_notes':{'event_share':'Recorded on-ball actions, not possession time','xg_geometry':'Uncalibrated shot-location estimate','heatmap':'Action starts, not tracking'}}


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
    if not numeric:return
    if re.search(r'\b[me]\d+\b',comment.text):raise ValueError('reference_in_prose')
    if any(mids[i]['key']=='xg_geometry' for i in comment.metric_ids) and not re.search(r'estimat|heuristic|估|粗略',comment.text,re.I):raise ValueError('unqualified_estimate')
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
                    schema['properties'][field]['items']['enum']=[m['id'] for m in source['metrics' if field=='metric_ids' else 'evidence']] or ['no_reference_available']
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
                # The candidate is untrusted: Footie can repair wording, citations and reply links.
                # Only the independently reviewed final record passes the publication gate.
                review=await call('footie',REVIEW,{'source':source,'conversation':past,'candidate':draft.model_dump(),'specialist':role},Review)
                if review.publish and review.text:
                    # Strip citation-only punctuation, never alter a factual clause.
                    text=re.sub(r'\s*[\[(]\s*[me]\d+(?:\s*,\s*[me]\d+)*\s*[\])]', '', review.text)
                    text=re.sub(r'\s*[\[(](?:\d+ completed|completed\s*=\s*\d+)[\])]', '', text)
                    review=review.model_copy(update={'text':text})
                    check_comment(review,source,past,role)
                    if not any(m['text'].strip().casefold()==review.text.strip().casefold() for m in past):
                        review=review.model_copy(update={'metric_ids':[references[i] for i in review.metric_ids],'evidence_ids':[references[i] for i in review.evidence_ids]})
                        message={'id':role,'role':role,**review.model_dump(exclude={'publish'}),'verified_by':'footie'}
                        result.update(status='complete',messages=[message],metrics=[{**m,'subject':next((v['subject'] for v in source['metrics'] if references[v['id']]==m['id']),'Match')} for m in snapshot['metrics'] if m['id'] in review.metric_ids],evidence=[e for e in snapshot['evidence'] if e['id'] in review.evidence_ids])
        except Exception as exc:
            editorial_rejection=type(exc) is ValueError and re.fullmatch('[a-z_]+',str(exc))
            result['status']='insufficient_evidence' if editorial_rejection else 'unavailable'
            result['failure_reason']=str(exc) if editorial_rejection else type(exc).__name__
        result['execution']={'runtime':'footie_live_turn_manager','model':MODEL,'review_model':REVIEW_MODEL,'model_calls':attempts,'per_role_usage':calls,'input_tokens':sum(c['input_tokens'] for c in calls),'output_tokens':sum(c['output_tokens'] for c in calls),'elapsed_ms':round((time.monotonic()-started)*1000)}
        return result
