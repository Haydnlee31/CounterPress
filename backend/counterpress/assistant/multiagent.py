"""Bounded application-hosted Footie, Match Analyst and Career Analyst.

Only query planning and sentence selection use a model. Task spans are exact
substrings, football reads share one snapshot, and the API rechecks the bundle.
"""
import asyncio
import json
import re
import time
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from typing import Literal

import httpx2
from agent_framework import Agent
from agent_framework.openai import OpenAIChatCompletionClient
from openai import AsyncOpenAI
from pydantic import Field, ValidationError, model_validator
from starlette.concurrency import run_in_threadpool

from counterpress.adaptation.azure import ProviderFailure, model_auth
from counterpress.fan.contracts import FanContract
from .contracts import Plan
from .narrative import StoryPlan, build_claims, default_story, render_story
from .planner import PROMPT, query_schema, prompt_for
from .research import ResearchFailure, ResearchResult
from .service import fingerprint
from .observability import agent_span


PRE_MATCH_QUALIFIER=re.compile(r'\b(?:before|prior to|ahead of|entering)\s+(?:this|the(?: selected)?)\s+match(?:\s+kicked off)?\b|\bbefore\s+(?:kickoff|kick-off)\b|本场比赛开始前|本场比赛之前|开球前',re.I)


class Task(FanContract):
    role: Literal['match', 'career']
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    scope: Literal['selected', 'pre_match'] = 'selected'


class Route(FanContract):
    tasks: list[Task] = Field(min_length=1, max_length=2)

    @model_validator(mode='after')
    def unique_roles(self):
        if len({t.role for t in self.tasks}) != len(self.tasks):
            raise ValueError('One delegation per specialist')
        return self


class Assignment(FanContract):
    role: Literal['match','career']
    question: str = Field(min_length=1,max_length=600)
    scope: Literal['selected','pre_match']


class Delegation(FanContract):
    tasks: list[Assignment] = Field(min_length=1,max_length=2)


def exact_tasks(delegation,question):
    tasks=[]
    for assignment in delegation.tasks:
        if question.count(assignment.question)!=1:
            raise ValueError('Delegation must uniquely quote the original question')
        start=question.index(assignment.question)
        tasks.append(Task(role=assignment.role,start=start,end=start+len(assignment.question),scope=assignment.scope))
    return validate_route(Route(tasks=tasks),question)


def validate_route(route, question):
    tasks = sorted(route.tasks, key=lambda t:t.start)
    cursor = 0
    for task in tasks:
        if task.start < cursor or task.end <= task.start or task.end > len(question):
            raise ValueError('Invalid task span')
        gap = question[cursor:task.start]
        if re.sub(r'\b(?:and|also|then|plus)\b|以及|同时|并且|还有|和|[\s,;?.!&，；。？]', '', gap, flags=re.I):
            raise ValueError('Task omitted part of the question')
        if not question[task.start:task.end].strip():raise ValueError('Empty task')
        cursor = task.end
    if re.sub(r'[\s?.!。？]', '', question[cursor:]):raise ValueError('Task omitted question suffix')
    return tuple(tasks)


class RouteSelection(FanContract):
    route_id: str


def route_candidates(question, *, replay):
    """Enumerate source-bound two-part routes; the model never rewrites a task.

    Candidate boundaries are grammatical conjunctions/punctuation, not known
    football question strings. Preserve every substantive character, and let
    the model select which split and specialist ordering matches the request.
    """
    separator=re.compile(r'(?:,\s*)?\b(?:and|also|then|plus)\b|[;&；。]|以及|同时|并且|还有|和|\.\s+',re.I)
    candidates={}
    for match in list(separator.finditer(question))[:8]:
        left_end=match.start()
        while left_end and question[left_end-1].isspace():left_end-=1
        right_start=match.end()
        while right_start<len(question) and question[right_start].isspace():right_start+=1
        if not left_end or right_start>=len(question):continue
        for roles in (('match','career'),('career','match')):
            tasks=(Task(role=roles[0],start=0,end=left_end,scope='pre_match' if replay and roles[0]=='career' else 'selected'),
                   Task(role=roles[1],start=right_start,end=len(question),scope='pre_match' if replay and roles[1]=='career' else 'selected'))
            try:validate_route(Route(tasks=list(tasks)),question)
            except ValueError:continue
            candidates[f'r{len(candidates)}']=tasks
    return candidates


def specialist_request(service, request, task):
    """A replay's career comparison is strictly pre-match, never end-of-season."""
    body = request.model_copy(update={'question':request.question[task.start:task.end].strip()})
    if task.scope=='pre_match' and (task.role!='career' or not request.playback):
        raise ValueError('Pre-match scope requires a replay career task')
    if task.role == 'career' and request.playback:
        if task.scope!='pre_match':raise ValueError('Career replay scope must explicitly use pre-match history')
        if re.search(r'\b(including|include|after|now|updated|live|through)\b|\b(up to|as of|with this)\b|算上|包括|之后|到现在',body.question,re.I):
            raise ValueError('Career totals including this play are unavailable')
        kickoff = service.store.row(request.match_id)['kickoff']
        cutoff = min(service.scope(request)[0], kickoff)
        # This is deterministic scope normalization, not a model rewrite. The
        # original quoted task remains in the receipt; the removed qualifier is
        # represented by the pinned cutoff and the visible pre-match label.
        question=PRE_MATCH_QUALIFIER.sub('',body.question).strip()
        if not question:raise ValueError('Choose a historical measure')
        if re.search(r'\b(?:this|the selected)\s+(?:match|play|moment|goal)\b|本场|这次|这一刻|这个进球',question,re.I):
            raise ValueError('Current-match statistics cannot become pre-match history')
        body = body.model_copy(update={'question':question,'as_of':cutoff,'match_id':None,
            'playback':None, 'event_id':None, 'event_revision':None})
    return body


def read_bundle(service, request, tasks, plans):
    """Caller holds one store snapshot for all reads; no model calls inside it."""
    if len(tasks) != len(plans) or not 1 <= len(tasks) <= 2:raise ValueError('Invalid evidence bundle')
    parts=[];claims=[];facts=[]
    for task,plan in zip(tasks,plans):
        if task.role == 'match' and plan.operation not in ('match','clarify','unsupported'):
            raise ValueError('Match specialist scope')
        if task.role == 'career' and plan.operation == 'match':raise ValueError('Career specialist scope')
        body=specialist_request(service,request,task)
        part=service.answer(plan,body)
        for claim in build_claims(part,plan,body):
            if task.scope=='pre_match':
                text='Before this match kicked off: '+claim['text']
                claim={**claim,'text':text,'evidence_id':fingerprint({'text':text,'facts':[part['facts'][i] for i in claim['fact_indices']]})}
            claims.append({**claim,'id':f'c{len(claims)}','source_role':task.role,
                'fact_indices':[i+len(facts) for i in claim['fact_indices']]})
        facts.extend(part['facts']);parts.append(part)
    if len(parts)==1:
        answer=dict(parts[0])
    else:
        groups=[]
        for task,part in zip(tasks,parts):
            prefix=('This match' if task.role=='match' else 'Before kickoff' if task.scope=='pre_match' else 'Player history') if request.preferences.language=='en' else ('本场比赛' if task.role=='match' else '开球前' if task.scope=='pre_match' else '球员历史')
            def scoped(group):return {**group,'label':prefix+' · '+group['label']}
            visual=part.get('visual')
            if visual and visual['kind']=='groups':groups.extend(scoped(g) for g in visual['groups'])
            elif visual and visual['kind'] in ('bars','timeline'):groups.append(scoped(visual))
            elif part['facts']:
                # Multi-part charts group like units, never mix goals and percentages.
                for metric in dict.fromkeys(f['metric'] for f in part['facts']):
                    if metric=='selected_action':continue
                    rows=[f for f in part['facts'] if f['metric']==metric]
                    groups.append(scoped({'kind':'bars','label':rows[0]['label'],
                        'items':[{'label':f['subject_name'],'value':f['value'],'unit':f['unit']} for f in rows]}))
        answer={'status':'answered' if any(p['status']=='answered' for p in parts) else parts[0]['status'],
            'title':'The bigger picture' if request.preferences.language=='en' else '一起看这些数据',
            'text':[text for part in parts for text in part['text']], 'facts':facts,
            'actions':list({a['href']:a for p in parts for a in p['actions']}.values()),
            'visual':{'kind':'groups','label':'Match and player context' if request.preferences.language=='en' else '比赛与球员背景','groups':groups} if groups else None}
    if request.playback and any(t.role=='career' for t in tasks):
        answer['text']=[*answer['text'], 'Player history is measured before this match kicked off.' if request.preferences.language=='en' else '球员历史数据截止至本场比赛开球前。']
    return answer,claims


def default_bundle_story(claims,depth):
    roles=list(dict.fromkeys(c.get('source_role') for c in claims))
    if len(roles)<2:return default_story(claims,depth)
    return [default_story([c for c in claims if c.get('source_role')==role],depth)[0] for role in roles]


def validate_bundle_story(selection,claims,depth):
    blocks=render_story(selection,claims,depth)
    if {c.get('source_role') for c in blocks}!={c.get('source_role') for c in claims}:
        raise ValueError('The selected story omits a specialist perspective')
    return blocks


def story_candidates(claims,depth,limit=24):
    """Bounded, prevalidated choices: the model cannot express a broken story.

    A small diversity pool per specialist bounds generation independently of the
    number of facts. Every candidate is checked by the same receipt validator.
    """
    candidates={};seen=set()
    def add(blocks):
        if not blocks or len(candidates)>=limit:return
        ids=tuple(c['id'] for c in blocks)
        if ids in seen:return
        selection=StoryPlan(lead=ids[0],supporting=list(ids[1:]))
        try:validate_bundle_story(selection,claims,depth)
        except ValueError:return
        seen.add(ids);candidates[f'b{len(candidates)}']=selection
    add(default_bundle_story(claims,depth))
    priority={'comparison':0,'moment':0,'rate':1,'figure':2}
    ranked=sorted(claims,key=lambda c:priority[c['kind']])
    roles=list(dict.fromkeys(c['source_role'] for c in ranked))
    pools={role:[c for c in ranked if c['source_role']==role][:6] for role in roles}
    if len(roles)==2:
        left,right=(pools[r] for r in roles)
        pairs=sorted(((i,j) for i in range(len(left)) for j in range(len(right))),key=lambda p:(sum(p),p))
        for i,j in pairs:
            add([left[i],right[j]])
            add([right[j],left[i]])
            if depth=='analyst':
                extra=next((c for c in ranked if c['id'] not in (left[i]['id'],right[j]['id'])),None)
                if extra:add([left[i],right[j],extra])
            if len(candidates)>=limit:break
    else:
        pool=ranked[:8]
        # Preserve single-sentence choices, plus distinct pair/triple summaries.
        for claim in pool:add([claim])
        for i,lead in enumerate(pool):
            supports=[c for c in pool if c['id']!=lead['id']]
            for support in supports[:2]:add([lead,support])
            if depth=='analyst' and len(supports)>1:add([lead,*supports[:2]])
            if len(candidates)>=limit:break
    return candidates


class FollowupSelection(FanContract):
    player_id: str | None


class BundleSelection(FanContract):
    bundle_id: str


@dataclass
class CallBudget:
    reserve: object
    requests: dict = field(default_factory=dict)
    usage: dict = field(default_factory=dict)
    reported_requests: int = 0
    tools: int = 0
    started: float = field(default_factory=time.monotonic)
    stage_timings: list = field(default_factory=list)
    resources: object = field(default=None, repr=False)

    @contextmanager
    def measure(self, stage, role='orchestrator'):
        if stage not in {'initial','context','route','query','tool','followup','synthesize','auth','provider_http'} or role not in {'orchestrator','match','career'}:
            raise ValueError('Unknown timing category')
        started=time.monotonic();status='ok'
        try:yield
        except BaseException as exc:
            status='cancelled' if isinstance(exc,asyncio.CancelledError) else 'error'
            raise
        finally:
            # Relative durations and fixed categories only: no request content,
            # resource addresses, credentials, exception text or entity IDs.
            self.stage_timings.append({'stage':stage,'role':role,
                'started_ms':round((started-self.started)*1000,3),
                'duration_ms':round((time.monotonic()-started)*1000,3),'status':status})

    def request(self, role):
        if sum(self.requests.values()) >= 4:raise ProviderFailure('limited','provider_request_limit')
        if not self.reserve():raise ProviderFailure('limited','model_allowance_exhausted')
        self.requests[role]=self.requests.get(role,0)+1


class CompletionTransport(httpx2.AsyncBaseTransport):
    """Strict output schema at the actual provider boundary; bounded, sanitized errors."""
    def __init__(self, inner, budget, role, schema, name, *, owns_inner=True):
        self.inner,self.budget,self.role,self.schema,self.name=inner,budget,role,schema,name
        self.usage={};self.attempted=False;self.owns_inner=owns_inner

    async def handle_async_request(self, request):
        self.budget.request(self.role)
        self.attempted=True
        payload=json.loads(request.content)
        payload['response_format']={'type':'json_schema','json_schema':{'name':self.name,'strict':True,'schema':self.schema}}
        payload.pop('tools',None);payload.pop('tool_choice',None)
        headers={k:v for k,v in request.headers.items() if k.lower()!='content-length'}
        request=httpx2.Request(request.method,request.url,headers=headers,content=json.dumps(payload).encode(),extensions=request.extensions)
        try:
            with self.budget.measure('provider_http',self.role):
                response=await self.inner.handle_async_request(request)
                try:
                    if response.status_code!=200:raise ProviderFailure('provider_error',f'http_{response.status_code}')
                    raw=bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw)>65536:raise ProviderFailure('invalid','response_too_large')
                    body=json.loads(raw);choice=body['choices'][0]
                    if choice.get('finish_reason')!='stop' or choice['message'].get('refusal'):
                        raise ProviderFailure('invalid','incomplete_response')
                    if choice['message'].get('tool_calls'):raise ProviderFailure('invalid','unexpected_tool_call')
                    usage=body.get('usage',{})
                    if usage:self.budget.reported_requests+=1
                    for key in ('prompt_tokens','completion_tokens','total_tokens'):
                        v=usage.get(key,0)
                        if type(v) is int and v>=0:
                            self.budget.usage[key]=self.budget.usage.get(key,0)+v
                            self.usage[key]=v
                    headers={k:v for k,v in response.headers.items() if k.lower() not in ('content-length','content-encoding','transfer-encoding')}
                    return httpx2.Response(200,headers=headers,content=bytes(raw))
                finally:await response.aclose()
        except httpx2.HTTPError:raise ProviderFailure('provider_error','transport_error') from None
        except (ValueError,KeyError,TypeError,IndexError):raise ProviderFailure('invalid','malformed_response') from None

    async def aclose(self):
        if self.owns_inner:await self.inner.aclose()


class RequestResources:
    """One request owns the pool and credential; stage wrappers only borrow them.

    Each stage still has its own schema, usage counters, SDK client and role.
    The auth lock prevents simultaneous first-token requests from two specialists.
    It never surrounds provider inference or serializes their HTTP requests.
    """
    def __init__(self,auth,transport,budget):
        self.auth,self.transport,self.budget=auth,transport,budget
        self.token_lock=asyncio.Lock()

    def sdk_kwargs(self,role):
        kwargs=self.auth.sdk_kwargs()
        if self.auth.config.auth_mode=='managed_identity':
            async def token():
                with self.budget.measure('auth',role):
                    async with self.token_lock:return await self.auth.token()
            kwargs['api_key']=token
        return kwargs


@asynccontextmanager
async def request_resources(config,transport_factory,budget):
    # No session state lives on MultiAgentResearch, which can serve concurrent
    # requests. AsyncExitStack also unwinds auth if pool construction fails.
    async with AsyncExitStack() as stack:
        auth=await stack.enter_async_context(model_auth(config))
        transport=await stack.enter_async_context(transport_factory())
        resources=RequestResources(auth,transport,budget)
        budget.resources=resources
        try:yield resources
        finally:budget.resources=None


def strict_schema(model):
    schema=model.model_json_schema()
    def visit(node):
        if isinstance(node,dict):
            for key in ('default','minimum','exclusiveMinimum','minItems','maxItems','minLength','maxLength','pattern'):node.pop(key,None)
            if node.get('type')=='object':node['required']=list(node.get('properties',{}))
            for value in node.values():visit(value)
        elif isinstance(node,list):
            for value in node:visit(value)
    visit(schema)
    return schema


class MultiAgentResearch:
    max_requests=4
    deadline_seconds=24

    def __init__(self,config,transport_factory=None,observer=None):
        self.config=config;self.observer=observer
        self.transport_factory=transport_factory or (lambda:httpx2.AsyncHTTPTransport(retries=0))

    def observe(self,event,value):
        if self.observer:self.observer(event,value)

    async def complete(self,budget,role,prompt,data,schema,name):
        stage={'footie_route':'route','footie_query':'query','footie_story':'synthesize','footie_followup':'followup'}[name]
        with budget.measure(stage,role), agent_span({'footie_route':'footie.route','footie_query':'footie.specialist','footie_story':'footie.synthesize','footie_followup':'footie.specialist'}[name],role=role) as span:
            resources=budget.resources
            if resources is None:raise ProviderFailure('invalid','request_resources_unavailable')
            transport=CompletionTransport(resources.transport,budget,role,schema,name,owns_inner=False)
            http=httpx2.AsyncClient(transport=transport,timeout=8,follow_redirects=False)
            try:
                async with http, AsyncOpenAI(**resources.sdk_kwargs(role),
                        base_url=self.config.url.removesuffix('chat/completions'),
                        max_retries=0,http_client=http) as sdk:
                    client=OpenAIChatCompletionClient(model=self.config.deployment,async_client=sdk)
                    agent=Agent(client,name={'orchestrator':'Footie','match':'MatchAnalyst','career':'CareerAnalyst'}[role],
                        instructions=prompt,default_options={'max_tokens':650})
                    response=await agent.run(json.dumps(data))
                    return json.loads(response.text)
            finally:
                span.set_attribute('footie.provider_requests',int(transport.attempted))
                span.set_attribute('gen_ai.usage.input_tokens',transport.usage.get('prompt_tokens',0))
                span.set_attribute('gen_ai.usage.output_tokens',transport.usage.get('completion_tokens',0))

    async def research(self,service,request,reserve):
        budget=CallBudget(reserve)
        try:
            async with asyncio.timeout(self.deadline_seconds), request_resources(self.config,self.transport_factory,budget):
                def initial():
                    with service.store.snapshot():return service.local_plan(request),service.context(request)
                with budget.measure('initial'):
                    local,context=await run_in_threadpool(initial)
                normalized=PRE_MATCH_QUALIFIER.sub('',request.question)
                has_match_question=bool(local.analysis or re.search(r'\b(moment|play|match|game|goal|buildup)\b|这一刻|这次|比赛|这个进球',normalized,re.I))
                pre_match_only=bool(request.playback and normalized!=request.question and not has_match_question)
                compound=bool(not pre_match_only and request.match_id and has_match_question
                    and re.search(r'\b(and|also|plus|then)\b|[;&；。]|\.\s|以及|同时|并且|还有|和',request.question,re.I)
                    and re.search(r'\b(season|career|recent|compare|history|form|assists?|goals|stats|statistics|how many)\b|\b20\d{2}-\d{2}(?!\d)|助攻|赛季|生涯|状态|多少',request.question,re.I))
                if compound:
                    routes=route_candidates(request.question,replay=bool(request.playback))
                    if not routes:raise ProviderFailure('invalid','compound_route_ambiguous')
                    schema=strict_schema(RouteSelection)
                    schema['properties']['route_id']['enum']=[*routes,'clarify']
                    raw=await self.complete(budget,'orchestrator',
                        'Choose a prevalidated route for this question. Match Analyst handles the current play, goal buildup, '
                        'player involvement in this match and changes within this game. Career Analyst handles historical totals, '
                        'seasons, rankings and comparisons. A current-match question plus a historical question needs both. '
                        'Each route preserves the original words exactly; select the correct split and role order. '
                        'During replay, career work is strictly before kickoff. If no route preserves the intended meanings, choose clarify. '
                        'Do not merge separate requests, rewrite a clause, or treat current-game changes as career history.',
                        {'question':request.question,'replay':bool(request.playback),
                         'routes':[{'route_id':key,'tasks':[{'role':t.role,'question':request.question[t.start:t.end],'scope':t.scope} for t in value]} for key,value in routes.items()]},schema,'footie_route')
                    # Legacy receipts/tests remain parseable, but live generation
                    # is constrained to one enumerated route ID above.
                    if 'tasks' in raw:tasks=exact_tasks(Delegation.model_validate(raw),request.question)
                    else:
                        chosen=RouteSelection.model_validate(raw)
                        if chosen.route_id not in routes:raise ProviderFailure('invalid','compound_route_ambiguous')
                        tasks=routes[chosen.route_id]
                    if {t.role for t in tasks}!={'match','career'}:
                        raise ProviderFailure('invalid','compound_route_incomplete')
                else:tasks=(Task(role='career' if pre_match_only else 'match' if local.operation=='match' or request.playback and len(context.get('analysis_options',[]))>1 else 'career',
                    start=0,end=len(request.question),scope='pre_match' if pre_match_only else 'selected'),)
                self.observe('route',{'tasks':[t.model_dump() for t in tasks]})
                def contexts():
                    with service.store.snapshot():
                        prepared=[]
                        for task in tasks:
                            try:
                                body=specialist_request(service,request,task)
                                prepared.append((body,service.context(body)))
                            except (ValueError,KeyError):prepared.append((None,None))
                        return prepared
                with budget.measure('context'):
                    inputs=await run_in_threadpool(contexts)
                async def plan_task(task,body,ctx):
                    if body is None:raise ProviderFailure('invalid','specialist_scope_rejected')
                    schema=query_schema(ctx)
                    allowed=['match','clarify','unsupported'] if task.role=='match' else ['stats','compare','recent','seasons','club_leaders','clarify','unsupported']
                    schema['properties']['operation']['enum']=[op for op in schema['properties']['operation']['enum'] if op in allowed]
                    try:
                        raw=await self.complete(budget,task.role,prompt_for(ctx)+'\nYou are the '+task.role+' specialist. Use only your permitted operations. Return one typed query; never delegate or write answer prose.',
                            {'question':body.question,'context':ctx},schema,'footie_query')
                        self.observe('query_proposal',{'role':task.role,'plan':raw})
                        plan=Plan.model_validate(raw)
                        if plan.investigate_player_id:raise ValueError('Initial query cannot choose a follow-up')
                    except Exception as exc:
                        # Evaluation hook only. Never stringify SDK exceptions,
                        # which can contain private endpoint or response content.
                        category='schema' if isinstance(exc,ValidationError) else 'json' if isinstance(exc,json.JSONDecodeError) else 'provider' if isinstance(exc,ProviderFailure) else 'sdk'
                        diagnostic={'role':task.role,'type':category}
                        if isinstance(exc,ValidationError):diagnostic['codes']=sorted({e['type'] for e in exc.errors(include_url=False,include_context=False,include_input=False)})
                        if isinstance(exc,ProviderFailure) and re.fullmatch(r'http_\d{3}|[a-z_]{1,50}',exc.reason):diagnostic['reason']=exc.reason
                        self.observe('planning_failure',diagnostic)
                        raise
                    self.observe('task_plan',{'role':task.role,'plan':plan.model_dump()})
                    return plan
                results=await asyncio.gather(*(plan_task(t,b,c) for t,(b,c) in zip(tasks,inputs)),return_exceptions=True)
                failures=[];valid_tasks=[];plans=[]
                def execute():
                    with service.store.snapshot():
                        for task,result in zip(tasks,results):
                            if isinstance(result,BaseException):failures.append(task.role+':planning_failed');continue
                            try:
                                if task.role=='match' and result.operation not in ('match','clarify','unsupported'):raise ValueError('Match specialist scope')
                                if task.role=='career' and result.operation=='match':raise ValueError('Career specialist scope')
                                service.validate(result,specialist_request(service,request,task))
                            except (ValueError,KeyError):failures.append(task.role+':scope_rejected');continue
                            valid_tasks.append(task);plans.append(result)
                        if not plans:raise ProviderFailure('invalid','all_specialists_failed')
                        budget.tools=len(plans)
                        with agent_span('footie.tool',role='orchestrator',attributes={'footie.tool_calls':len(plans),'footie.specialist_count':len(plans)}):
                            return read_bundle(service,request,valid_tasks,plans)
                with budget.measure('tool'):
                    answer,claims=await run_in_threadpool(execute)
                # One optional evidence-driven lookup. Leave one request for
                # synthesis; compound questions already consume the four-call
                # envelope and never recurse or borrow another admission budget.
                if len(plans)==1 and plans[0].analysis=='buildup' and sum(budget.requests.values())<=2:
                    def followup_options():
                        with service.store.snapshot():
                            return service.investigation_candidates(plans[0],specialist_request(service,request,valid_tasks[0]))
                    with budget.measure('context','match'):
                        options=await run_in_threadpool(followup_options)
                    if options:
                        try:
                            schema=strict_schema(FollowupSelection)
                            schema['properties']['player_id']['enum']=[None,*[p['player_id'] for p in options]]
                            async with asyncio.timeout(2):
                                raw=await self.complete(budget,'match',
                                    'After inspecting this verified goal buildup, decide whether one focused lookup of a participant’s involvement '
                                    'across this match would help answer the user. Choose a supplied player_id or null to skip. '
                                    'Prefer a named or followed participant when relevant, or repeated involvement worth comparing with their match activity. '
                                    'This follow-up counts their recorded actions up to the current playback cutoff; it cannot establish causation or award assists. '
                                    'Do not choose a participant merely to fill the budget; skip when the existing sequence explains enough.',
                                    {'question':request.question,'observed_buildup':answer['text'],'participants':options},schema,'footie_followup')
                            followup=FollowupSelection.model_validate(raw)
                            if followup.player_id is not None:
                                if followup.player_id not in {p['player_id'] for p in options}:raise ValueError('Unapproved follow-up participant')
                                candidate=plans[0].model_copy(update={'investigate_player_id':followup.player_id})
                                def investigate():
                                    with service.store.snapshot():
                                        with agent_span('footie.tool',role='match',attributes={'footie.tool_calls':1}):
                                            return read_bundle(service,request,valid_tasks,[candidate])
                                with budget.measure('tool','match'):
                                    enriched,enriched_claims=await run_in_threadpool(investigate)
                                plans[0]=candidate;answer,claims=enriched,enriched_claims;budget.tools+=1
                                self.observe('followup',{'selected':True})
                            else:self.observe('followup',{'selected':False})
                        except (TimeoutError,ProviderFailure,ValueError,KeyError):
                            # Optional research failure retains the verified first
                            # answer. API commit still rereads its revision snapshot.
                            self.observe('followup',{'selected':False,'fallback':True})
                if len(plans)>1:
                    failures.extend(task.role+':scope_unavailable' for task,plan in zip(valid_tasks,plans) if plan.operation in ('clarify','unsupported'))
                fallback=default_bundle_story(claims,request.preferences.depth)
                selection=StoryPlan(lead=fallback[0]['id'] if fallback else '',supporting=[c['id'] for c in fallback[1:]])
                selection_mode='calculated'
                if claims:
                    candidates=story_candidates(claims,request.preferences.depth)
                    if not candidates:raise ValueError('No valid story bundle')
                    if len(candidates)==1:
                        # There is no editorial choice to ask the model to make.
                        # Revalidate even this prevalidated candidate so a broken
                        # generator can never bypass mandatory claims or roles.
                        selection=next(iter(candidates.values()))
                        validate_bundle_story(selection,claims,request.preferences.depth)
                        self.observe('selection_source',{'mode':'calculated','reason':'single_candidate'})
                    else:
                        schema=strict_schema(BundleSelection)
                        schema['properties']['bundle_id']['enum']=list(candidates)
                        try:
                            async with asyncio.timeout(5):
                                raw=await self.complete(budget,'orchestrator',
                                    'Choose one approved story bundle that best answers the question. Return its bundle_id only. '
                                'Every bundle already respects audience length, factual evidence and specialist coverage. '
                                'Prefer directly relevant comparisons and distinct requested measures. Do not author prose or change the bundle.',
                                {'question':request.question,'audience':request.preferences.depth,'sentences':claims,
                                 'bundles':[{'bundle_id':key,**value.model_dump()} for key,value in candidates.items()]},schema,'footie_story')
                            self.observe('selection_proposal',raw)
                            selected=BundleSelection.model_validate(raw)
                            selection=candidates[selected.bundle_id]
                            validate_bundle_story(selection,claims,request.preferences.depth)
                            selection_mode='agent_selected'
                        except (TimeoutError,ProviderFailure,ValueError,KeyError):
                            failures.append('orchestrator:selection_failed')
                            selection=StoryPlan(lead=fallback[0]['id'],supporting=[c['id'] for c in fallback[1:]])
                self.observe('selection',selection.model_dump())
                return ResearchResult(plans[0],selection,fingerprint(answer),budget.usage,
                    sum(budget.requests.values()),budget.tools,budget.reported_requests,
                    tasks=tuple(valid_tasks),plans=tuple(plans),partial_failures=tuple(failures),stage_timings=tuple(budget.stage_timings),selection_mode=selection_mode)
        except TimeoutError:raise ResearchFailure('timeout','research_deadline',budget) from None
        except Exception as exc:
            if isinstance(exc,ProviderFailure):raise ResearchFailure(exc.status,exc.reason,budget) from None
            raise ResearchFailure('invalid','multiagent_rejected',budget) from None
