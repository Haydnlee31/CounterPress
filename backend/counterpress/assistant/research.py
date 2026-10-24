"""Opt-in single-agent research using one typed, bounded read tool.

Two provider turns maximum: select a query, then select verified sentence IDs.
The agent never calculates/display-authors facts. API commit rereads the evidence.
"""
import asyncio
import json
from dataclasses import dataclass
from typing import Literal

import httpx2
from agent_framework import Agent, tool
from agent_framework.openai import OpenAIChatCompletionClient
from openai import AsyncOpenAI
from starlette.concurrency import run_in_threadpool

from counterpress.adaptation.azure import ProviderFailure, model_auth
from counterpress.workflow.budget import Budget, GuardedTransport, ToolGuard
from .contracts import Plan
from .narrative import StoryPlan, build_claims, render_story
from .planner import PROMPT, query_schema, prompt_for
from .service import fingerprint


class ResearchBudget(Budget):
    def __init__(self, reserve, seconds=12):
        super().__init__(seconds)
        self.reserve = reserve
        self.usage = {}
        self.reported_requests = 0

    def request(self, role):
        self.check()
        if sum(self.requests.values()) >= 2:
            self.fail('budget_exhausted', 'provider_request_limit')
        if not self.reserve():
            self.fail('hourly_limit', 'model_allowance_exhausted')
        self.requests[role] += 1

    def invoke_tool(self):
        self.check()
        if self.tools >= 1:
            self.fail('budget_exhausted', 'tool_invocation_limit')
        self.tools += 1


class ResearchTransport(GuardedTransport):
    def __init__(self, budget, role, inner, claim_ids, schema, observer=None, supporting_limit=1):
        super().__init__(budget, role, inner)
        self.claim_ids = claim_ids
        self.schema = schema
        self.observer = observer
        self.supporting_limit = supporting_limit

    async def handle_async_request(self, request):
        # Bind the second-turn schema to the actual tool receipt. A static string
        # schema lets a provider return prose despite an ID-only instruction.
        payload = json.loads(request.content)
        for item in payload.get('tools',[]):
            if item.get('function',{}).get('name')=='read_football_records':
                item['function']['parameters']=self.schema
                item['function']['strict']=True
        ids = self.claim_ids()
        if ids is not None:
            payload['tool_choice'] = 'none'
            payload['response_format'] = {'type':'json_schema','json_schema':{
                'name':'verified_story_selection','strict':True,'schema':{
                    'type':'object','additionalProperties':False,'required':['lead','supporting'],
                    'properties':{'lead':{'type':'string','enum':ids or ['']},
                        'supporting':{'type':'array','maxItems':self.supporting_limit if ids else 0,
                            'items':{'type':'string','enum':ids or ['']}}}}}}
        else:
            payload.pop('response_format', None)
            payload['tool_choice'] = {'type':'function','function':{'name':'read_football_records'}}
        headers = {k:v for k,v in request.headers.items() if k.lower()!='content-length'}
        request = httpx2.Request(request.method,request.url,headers=headers,
                                 content=json.dumps(payload).encode(),extensions=request.extensions)
        response = await super().handle_async_request(request)
        body = json.loads(await response.aread())
        if body.get('usage'):self.budget.reported_requests += 1
        for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
            value = body.get('usage', {}).get(key, 0)
            if type(value) is int and value >= 0:
                self.budget.usage[key] = self.budget.usage.get(key, 0) + value
        if ids is None:
            calls = body['choices'][0]['message'].get('tool_calls', [])
            if len(calls) != 1 or calls[0].get('function', {}).get('name') != 'read_football_records':
                self.budget.fail('invalid', 'query_tool_required')
            try:
                arguments = json.loads(calls[0]['function']['arguments'])
                if self.observer:self.observer('arguments', arguments)
                Plan.model_validate(arguments)
            except (ValueError, KeyError, TypeError):
                self.budget.fail('invalid', 'query_schema_rejected')
        return response


@dataclass(frozen=True)
class ResearchResult:
    plan: Plan
    selection: StoryPlan
    evidence_id: str
    usage: dict
    requests: int
    tools: int
    reported_requests: int
    cached: bool = False
    tasks: tuple = ()
    plans: tuple[Plan, ...] = ()
    partial_failures: tuple[str, ...] = ()
    stage_timings: tuple[dict, ...] = ()
    selection_mode: Literal['agent_selected','calculated'] = 'agent_selected'


class ResearchFailure(ProviderFailure):
    def __init__(self, status, reason, budget):
        super().__init__(status, reason)
        self.usage = dict(budget.usage)
        self.requests = sum(budget.requests.values())
        self.tools = budget.tools
        self.reported_requests = budget.reported_requests
        self.stage_timings = tuple(getattr(budget, 'stage_timings', ()))


class ResearchAgent:
    max_requests = 2
    deadline_seconds = 12
    def __init__(self, config, transport_factory=None, observer=None):
        self.config = config
        self.observer = observer
        self.transport_factory = transport_factory or (lambda: httpx2.AsyncHTTPTransport(retries=0))

    async def research(self, service, request, reserve):
        budget = ResearchBudget(reserve)
        receipt = None
        stage = 'provider'

        @tool(schema=Plan)
        async def read_football_records(**arguments) -> str:
            """Read a validated player/club metric, comparison, recent form, season, ranking or match moment.

            Supply every requested metric (at most three) and preserve selected scope.
            Returns approved sentences and compact facts. No SQL, code, writes or web access.
            """
            nonlocal receipt, stage
            stage = 'query_validation'
            plan = Plan.model_validate(arguments)
            if self.observer:self.observer('plan',plan.model_dump())
            def read():
                with service.store.snapshot():
                    try:
                        return service.answer(plan, request)
                    except (ValueError, KeyError):
                        budget.fail('invalid', 'query_scope_rejected')
            answer = await run_in_threadpool(read)
            budget.check()
            claims = build_claims(answer, plan, request)
            receipt = (plan, answer, claims)
            stage = 'provider'
            # Source digests remain in the authoritative answer; sending all event
            # references back to the model adds cost without improving its task.
            return json.dumps({'status': answer['status'], 'sentences': claims,
                               'instruction': 'Select sentence IDs only. With no sentences use lead="", supporting=[].'})

        try:
            async with asyncio.timeout(12):
                http = httpx2.AsyncClient(transport=ResearchTransport(budget, 'analyst', self.transport_factory(),
                        lambda:[c['id'] for c in receipt[2]] if receipt is not None else None,
                        query_schema(service.context(request)), self.observer,
                        supporting_limit=2 if request.preferences.depth=='analyst' else 1),
                                         timeout=8, follow_redirects=False)
                async with http, model_auth(self.config) as auth, AsyncOpenAI(**auth.sdk_kwargs(),
                        base_url=self.config.url.removesuffix('chat/completions'),
                        max_retries=0, http_client=http) as sdk:
                    client = OpenAIChatCompletionClient(model=self.config.deployment, async_client=sdk,
                        function_invocation_configuration={'max_iterations': 2, 'max_function_calls': 1,
                            'max_duration_seconds': 12, 'allow_concurrent_invocation': False,
                            'terminate_on_unknown_calls': True, 'include_detailed_errors': False})
                    agent = Agent(client, name='FootieResearch', middleware=[ToolGuard(budget)],
                        instructions=prompt_for(service.context(request)).replace('Return a read-only query plan, never an answer.',
                            'Call read_football_records exactly once with a read-only query plan.') +
                            '\nCall read_football_records exactly once with the query plan. After the tool: return ONLY a StoryPlan choosing its verified sentence IDs. '
                            'Do not write answer prose. Casual audiences get at most two IDs in total, '
                            'analysts three. Prefer comparisons, represent different requested metrics, '
                            'and never repeat IDs. With no sentences use lead="", supporting=[].',
                        tools=[read_football_records],
                        default_options={'response_format': StoryPlan, 'max_tokens': 650})
                    result = await agent.run(json.dumps({'question': request.question,
                        'context': service.context(request), 'audience': request.preferences.depth}))
                    budget.check()
                    stage = 'read_receipt'
                    if receipt is None:
                        raise ValueError('No validated read receipt')
                    plan, answer, claims = receipt
                    stage = 'story_schema'
                    selection = StoryPlan.model_validate_json(result.text)
                    if self.observer:self.observer('selection',selection.model_dump())
                    stage = 'story_validation'
                    if claims:
                        render_story(selection, claims, request.preferences.depth)
                    elif selection.lead or selection.supporting:
                        raise ValueError('Unbound narrative')
                    return ResearchResult(plan, selection, fingerprint(answer), budget.usage,
                                          sum(budget.requests.values()), budget.tools, budget.reported_requests)
        except TimeoutError:
            raise ResearchFailure('timeout', 'research_deadline', budget) from None
        except Exception as exc:
            failure = budget.failure or (exc if isinstance(exc, ProviderFailure) else None)
            if failure:
                raise ResearchFailure(failure.status, failure.reason, budget) from None
            # Framework/SDK errors may contain model text or private configuration.
            raise ResearchFailure('invalid', stage+'_rejected', budget) from None
