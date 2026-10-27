"""Bounded assistant; Azure interpretation and agent research are explicit runtime modes."""
import asyncio,json,logging,os,sqlite3,time
from collections import deque
from functools import lru_cache
from uuid import uuid4
from fastapi import APIRouter,HTTPException,Request
from starlette.concurrency import run_in_threadpool
from counterpress.adaptation.azure import load_config,ProviderFailure
from counterpress.fan.service import FanService,PreferenceError
from counterpress.history import HistoryStorageError
from .contracts import AskRequest
from .planner import AzurePlanner
from .service import AssistantService,UNSUPPORTED,blank,fingerprint
from .narrative import AzureNarrator,build_claims,default_story,render_story
from .observability import agent_span
from .observation import pinned_observation

log=logging.getLogger('uvicorn.error.footie')


def install_assistant(app,career_service,planner=None,narrator=None,researcher=None,history_store=None):
    if planner is None and os.environ.get('COUNTERPRESS_ASSISTANT_MODEL')=='azure':
        config=load_config()
        if config:
            if os.environ.get('COUNTERPRESS_ASSISTANT_WORKFLOW') in ('agent','multiagent'):
                from .research import ResearchAgent
                from .admission import shared_researcher
                from .planner import PROMPT, MATCH_PROMPT
                workflow=os.environ.get('COUNTERPRESS_ASSISTANT_WORKFLOW')
                if workflow=='multiagent':
                    from .multiagent import MultiAgentResearch
                    engine=MultiAgentResearch(config)
                else:engine=ResearchAgent(config)
                researcher=researcher or shared_researcher(engine,history_store,
                    fingerprint({'workflow':'bounded-research-v8-intelligence-'+workflow,'prompt':PROMPT+'\n'+MATCH_PROMPT,'deployment':config.deployment}))
            else:
                planner=AzurePlanner(config)
                narrator=narrator or AzureNarrator(config)
    summary_config=load_config() if os.environ.get('COUNTERPRESS_ASSISTANT_MODEL')=='azure' else None
    router=APIRouter(prefix='/api/fan/assistant',tags=['Football assistant'])
    from counterpress.usage_policy import usage_caps_enabled
    from .admission import configured_limits
    hourly_limit,_=configured_limits()
    calls=deque();model_calls=deque();gate=asyncio.Semaphore(2)
    def reserve_model_call():
        now=time.monotonic()
        while model_calls and now-model_calls[0]>=3600:model_calls.popleft()
        if usage_caps_enabled() and len(model_calls)>=hourly_limit:return False
        model_calls.append(now)
        return True
    @lru_cache(maxsize=1)
    def service():return AssistantService(career_service())

    def require_current_observation(s, body):
        # A card's source ceiling is a precondition, not a claim that every
        # research tool can reconstruct an arbitrary historical delivery stream.
        # Refuse before inference (and again before returning) when newer known
        # actions could change the selected moment, including same-time revisions.
        if body.through_sequence is None:return
        cutoff=(body.playback.period,body.playback.elapsed_ms)
        events=s.store.events(body.match_id)
        past_ids={e.event_id for e in events if e.delivery_sequence<=body.through_sequence
                  and (e.period,e.elapsed_ms)<=cutoff}
        if any(e.delivery_sequence>body.through_sequence
               and (e.available_period,e.available_ms)<=cutoff
               and (e.event_id in past_ids or (e.period,e.elapsed_ms)<=cutoff)
               for e in events):
            raise HTTPException(409,'This moment has changed. Review its update before asking Footie.')
        if body.observation_id:
            try:pinned_observation(s,body)
            except (ValueError,KeyError):
                raise HTTPException(409,'This observation has changed. Return to the replay and review the update before asking Footie.') from None

    @router.get('/config')
    def config():
        return {'available':True,'natural_language':planner is not None or researcher is not None,'narrative_selection':narrator is not None or researcher is not None,'workflow':'multiagent' if researcher and getattr(researcher,'max_requests',2)==4 else 'agent' if researcher else 'structured_lookup','name':'Footie','storage':'session',
                'max_question_characters':600,'model_requests_per_hour':(hourly_limit if usage_caps_enabled() else None) if planner or narrator or researcher else 0}

    @router.get('/moment')
    def moment(match_id:str,event_id:str,revision:int,resolved:bool):
        """Resolve legacy presentation clocks to canonical availability; no inference."""
        s=service()
        try:
            with s.store.snapshot():
                try:
                    if not s.store.row(match_id)['featured']:raise KeyError()
                    event=next(e for e in s.store.events(match_id) if e.event_id==event_id and e.revision==revision and not e.retracted)
                except (KeyError,StopIteration):raise HTTPException(404,'Reopen the moment from the match.') from None
                cutoff={'period':event.available_period,'elapsed_ms':event.available_ms} if resolved else {'period':event.period,'elapsed_ms':max(0,event.elapsed_ms-1)}
                return {'match_id':match_id,'event_id':event_id,'event_revision':revision,'cutoff':cutoff}
        except (OSError,sqlite3.Error,ValueError,HistoryStorageError):
            raise HTTPException(503,'The match records are temporarily unavailable. Please try again.') from None

    @router.post('/summary')
    async def highlight_summary(body:AskRequest,request:Request):
        from .highlight_summary import write_verified_summary,enrich_evidence,SummaryRejected
        from counterpress.personalization.metrics import select_events
        origin=request.headers.get('origin');base=str(request.base_url).rstrip('/')
        if origin and origin not in {base,base.replace('http://','https://',1)}:
            raise HTTPException(403,'Open the summary from Footie.')
        if not summary_config:raise HTTPException(503,'AI summaries are temporarily unavailable.')
        if not body.match_id or not body.event_id or body.event_revision is None or not body.playback:
            raise HTTPException(422,'Select a specific moment first.')
        now=time.monotonic()
        while calls and now-calls[0]>=60:calls.popleft()
        if len(calls)>=30:raise HTTPException(429,'Please try again shortly.')
        calls.append(now)
        def packet():
            s=service()
            with s.store.snapshot():
                if not s.store.row(body.match_id)['featured']:raise HTTPException(404,'Moment unavailable.')
                visible=select_events(s.store.events(body.match_id),(body.playback.period,body.playback.elapsed_ms))
                event=next((e for e in visible if e.event_id==body.event_id),None)
                if not event or event.revision!=body.event_revision or (body.playback.period,body.playback.elapsed_ms)!=(event.available_period,event.available_ms):raise HTTPException(409,'The moment has changed. Reopen it.')
                rows=[e for e in visible if e.period==event.period and event.elapsed_ms-20000<e.elapsed_ms<=event.elapsed_ms][-30:]
                # End at the selected action, including same-clock occurrence order.
                rows=[e for e in rows if (e.elapsed_ms,e.occurrence_order)<=(event.elapsed_ms,event.occurrence_order)]
                live=s.career.live(body.match_id,event.available_period,event.available_ms)
                score=dict(live['score'])
                for later in visible:
                    if later.goal_for and (later.period,later.elapsed_ms,later.occurrence_order)>(event.period,event.elapsed_ms,event.occurrence_order):score[later.goal_for]-=1
                people={pid for e in rows for pid in (e.player_id,e.recipient_id,e.goalkeeper_id,e.opponent_id) if pid}
                return {'context':{'selected_event_id':event.event_id,'score_after':score,
                    'scope':'Recorded actions in the 20 seconds ending at the selected moment; not the whole match.',
                    'players':{pid:s.store.players[pid].name for pid in people},
                    'clubs':{c:s.store.clubs[c].name for c in live['score']},'pitch':'105 by 68 metres, acting team attacks positive x'},
                    'events':[e.model_dump(mode='json') for e in rows]}
        try:
            evidence=await run_in_threadpool(packet)
            async with asyncio.timeout(75):
                async with gate:
                    try:result=await write_verified_summary(summary_config,enrich_evidence(evidence),reserve_model_call)
                    except SummaryRejected as rejected:
                        result=await write_verified_summary(summary_config,enrich_evidence(evidence),reserve_model_call,feedback={'draft':rejected.draft,'issues':rejected.issues})
            if fingerprint(await run_in_threadpool(packet))!=fingerprint(evidence):
                raise HTTPException(409,'The moment changed while its summary was being written.')
            return {**result,'request_id':uuid4().hex,'source_fingerprint':fingerprint(evidence)}
        except ProviderFailure as exc:
            raise HTTPException(429 if exc.reason=='summary_limit' else 503,'The summary could not finish. Please try again.') from None
        except (ValueError,KeyError,TimeoutError,OSError,sqlite3.Error,HistoryStorageError):
            raise HTTPException(503,'The summary could not be verified. Please try again.') from None

    @router.post('/ask')
    async def ask(body:AskRequest,request:Request):
        # Prevent cross-site browser POSTs from triggering paid interpretation.
        origin=request.headers.get('origin')
        base=str(request.base_url).rstrip('/')
        # Azure ingress terminates TLS before the HTTP application hop. Accept
        # only the HTTPS spelling of this same authority, never forwarded hosts.
        allowed_origins={base}
        if base.startswith('http://'):
            allowed_origins.add('https://'+base[len('http://'):])
        if origin and origin not in allowed_origins:
            raise HTTPException(403,'Open the assistant from CounterPress.')
        now=time.monotonic()
        while calls and now-calls[0]>=60:calls.popleft()
        if len(calls)>=30:raise HTTPException(429,'Please wait a moment before asking again.',headers={'Retry-After':'60'})
        calls.append(now);started=now;request_id=uuid4().hex
        mode='lookup';usage={};reason=None;research=None;research_counts={'requests':0,'tools':0,'unreported_usage_attempts':0}
        with agent_span('footie.request',role='orchestrator',attributes={'footie.request_id':request_id,
                'footie.workflow':'multiagent' if getattr(researcher,'max_requests',2)==4 else 'agent' if researcher else 'structured_lookup'}) as span:
            try:
                s=service();FanService(s.career).validate(body.preferences)
                if body.through_sequence is not None:
                    with s.store.snapshot():require_current_observation(s,body)
                local=s.local_plan(body);plan=local
                if researcher and not UNSUPPORTED.search(body.question):
                    def reserve_research_call():
                        accepted=reserve_model_call()
                        if accepted:
                            research_counts['requests']+=1
                            research_counts['unreported_usage_attempts']+=1
                        return accepted
                    try:
                        async with asyncio.timeout(getattr(researcher,'deadline_seconds',12)+2):
                            async with gate:research=await researcher.research(s,body,reserve_research_call)
                        span.set_attribute('footie.provider_requests',research.requests)
                        span.set_attribute('footie.tool_calls',research.tools)
                        span.set_attribute('footie.cached',research.cached)
                        span.set_attribute('footie.partial',bool(research.partial_failures))
                        span.set_attribute('gen_ai.usage.input_tokens',research.usage.get('prompt_tokens',0))
                        span.set_attribute('gen_ai.usage.output_tokens',research.usage.get('completion_tokens',0))
                        plan=research.plan;usage=research.usage;mode='azure_agent'
                        research_counts={'requests':research.requests,'tools':research.tools,'unreported_usage_attempts':research.requests-research.reported_requests,
                                         'cached':research.cached}
                    except (TimeoutError,ProviderFailure,ValueError,KeyError) as exc:
                        plan=blank('clarify') if isinstance(exc,ProviderFailure) and exc.reason=='compound_route_ambiguous' else local
                        mode='lookup_fallback';usage=getattr(exc,'usage',{})
                        research_counts={'requests':getattr(exc,'requests',research_counts['requests']),'tools':getattr(exc,'tools',0),
                                         'unreported_usage_attempts':getattr(exc,'requests',research_counts['requests'])-getattr(exc,'reported_requests',0)}
                        reason='timeout' if isinstance(exc,TimeoutError) else exc.reason if isinstance(exc,ProviderFailure) else 'plan_rejected'
                elif planner and not UNSUPPORTED.search(body.question):
                    if reserve_model_call():
                        try:
                            async with asyncio.timeout(10):
                                async with gate:plan,usage=await planner.plan(body.question,s.context(body))
                            s.validate(plan,body);mode='azure'
                        except (TimeoutError,ProviderFailure,ValueError,KeyError) as exc:
                            plan=local;mode='lookup_fallback'
                            reason='timeout' if isinstance(exc,TimeoutError) else exc.status if isinstance(exc,ProviderFailure) else 'plan_rejected'
                    else:mode='lookup_fallback';reason='hourly_limit'
                def execute():
                    # Keep compound reads in one revision snapshot; never hold during a model call.
                    with s.store.snapshot():
                        require_current_observation(s,body)
                        if research and research.tasks:
                            from .multiagent import read_bundle
                            with agent_span('footie.validate',role='orchestrator'):
                                answer,claims=read_bundle(s,body,research.tasks,research.plans)
                            return answer,research.plan,claims
                        try:
                            answer=s.answer(plan,body)
                            return answer,plan,build_claims(answer,plan,body)
                        except (ValueError,KeyError):return s.answer(blank('clarify'),body),blank('clarify'),[]
                answer,plan,claims=await run_in_threadpool(execute)
                story=default_story(claims,body.preferences.depth)
                if research and research.tasks:
                    from .multiagent import default_bundle_story
                    story=default_bundle_story(claims,body.preferences.depth)
                story_mode='calculated';story_reason=None;story_usage={}
                if research:
                    if fingerprint(answer)==research.evidence_id:
                        try:
                            if research.tasks:
                                from .multiagent import validate_bundle_story
                                story=validate_bundle_story(research.selection,claims,body.preferences.depth) if claims else []
                            else:story=render_story(research.selection,claims,body.preferences.depth) if claims else []
                            story_mode='calculated' if 'orchestrator:selection_failed' in research.partial_failures else getattr(research,'selection_mode','agent_selected')
                            if 'orchestrator:selection_failed' in research.partial_failures:story_reason='selection_failed'
                        except ValueError:
                            story=default_bundle_story(claims,body.preferences.depth) if research.tasks else default_story(claims,body.preferences.depth)
                            story_mode='calculated';story_reason='stale_selection'
                    else:story_reason='records_changed'
                    if research.partial_failures:
                        answer['research']={'partial':True,'unavailable':[r.split(':')[0] for r in research.partial_failures]}
                        if any(not r.startswith('orchestrator:') for r in research.partial_failures):
                            answer['text'].append('Part of this question could not be checked. These results cover the available records.' if body.preferences.language=='en' else '部分问题暂时无法核实，以下结果仅涵盖可用记录。')
                            # Existing UI collapses text when a selected story exists.
                            # Show the full available answer and missing-scope notice.
                            story=[];story_mode='calculated';story_reason='partial_research'
                if not researcher and narrator and claims and mode!='lookup_fallback':
                    if reserve_model_call():
                        try:
                            async with asyncio.timeout(6):
                                async with gate:
                                    selection,story_usage=await narrator.explain(body.question,claims,body.preferences.depth)
                            story=render_story(selection,claims,body.preferences.depth);story_mode='azure_selected'
                        except (TimeoutError,ProviderFailure,ValueError,KeyError) as exc:
                            story_reason='timeout' if isinstance(exc,TimeoutError) else exc.status if isinstance(exc,ProviderFailure) else 'story_rejected'
                    else:story_reason='hourly_limit'
                    # A correction may arrive while Azure is selecting a story. Re-read under
                    # the revision lock before returning; never combine old prose with new facts.
                    fresh,fresh_plan,fresh_claims=await run_in_threadpool(execute)
                    if fingerprint(fresh)!=fingerprint(answer):
                        answer,plan=fresh,fresh_plan
                        claims=build_claims(answer,plan,body)
                        story=default_story(claims,body.preferences.depth)
                        story_mode='calculated';story_reason='records_changed'
                if researcher and mode=='lookup_fallback' and answer['status']=='answered':
                    # A direct lookup can cover only one clause of a compound
                    # question. Do not present it as completed investigation or
                    # hide the limitation beneath a selected narrative.
                    answer['text'].append(
                        'I could not complete the full analysis. These direct statistics may answer only part of your question.'
                        if body.preferences.language=='en' else
                        '我未能完成全部分析。这些直接查询的统计数据可能只回答了你问题的一部分。')
                    answer['research']={'partial':True,'unavailable':['orchestrator']}
                    story=[];story_mode='calculated';story_reason='research_unavailable'
                answer['narrative']={'mode':story_mode,'blocks':story,'fallback_reason':story_reason}
                # The legacy UI sends one previous_plan. A compound receipt cannot
                # fit it: clear that slot instead of silently retaining one half.
                incomplete_lookup=researcher and mode=='lookup_fallback' and answer['status']=='answered'
                conversation_plan=blank('clarify') if incomplete_lookup or research and (len(research.plans)>1 or any(not r.startswith('orchestrator:') for r in research.partial_failures)) else plan
                answer.update({'request_id':request_id,'plan':conversation_plan.model_dump(),'as_of':s.scope(body)[0],
                    'mode':mode,'fallback_reason':reason,'answer_id':fingerprint({'plan':plan.model_dump(),'facts':answer['facts']}),
                    'suggestions':suggestions(s,body,plan)})
                # Operational fields only: never prompts, credentials, endpoints or conversation bodies.
                log.info('assistant_request %s',json.dumps({'request_id':request_id,'mode':mode,'operation':plan.operation,'status':answer['status'],
                    'duration_ms':round((time.monotonic()-started)*1000),'usage':usage,'fallback':reason,
                    'narrative_mode':story_mode,'narrative_fallback':story_reason,'narrative_usage':story_usage,
                    'research':research_counts}))
                span.set_attribute('footie.operation','compound' if research and len(research.plans)>1 else plan.operation)
                span.set_attribute('footie.status','partial' if research and research.partial_failures else 'fallback' if mode=='lookup_fallback' else 'ok' if answer['status']=='answered' else answer['status'])
                # A sole valid summary (or ordinary direct lookup) is an
                # intentional calculated answer, not an AI failure.
                span.set_attribute('footie.fallback',mode=='lookup_fallback' or story_reason is not None)
                span.set_attribute('footie.provider_requests',research_counts['requests'])
                span.set_attribute('footie.tool_calls',research_counts['tools'])
                return answer
            except PreferenceError:raise HTTPException(422,'Choose valid player and club preferences.') from None
            except (OSError,sqlite3.Error,ValueError,KeyError,HistoryStorageError):raise HTTPException(503,'The match records are temporarily unavailable. Please try again.') from None

    app.include_router(router)
    app.state.assistant_service=service


def suggestions(service,body,plan):
    if body.match_id and body.playback:
        at=(body.playback.period,body.playback.elapsed_ms)
        from counterpress.personalization.metrics import select_events
        try:selected=select_events(service.store.events(body.match_id),at)
        except (KeyError,ValueError):return []
        event=next((e for e in selected if e.event_id==body.event_id),None) if body.event_id else None
        suggestions=[]
        if plan.analysis!='buildup' and event and event.outcome=='goal' and event.revision==body.event_revision:
            suggestions.append('What made that goal happen?')
        pid=body.player_id or (event.player_id if event else None)
        if pid in service.store.players and plan.analysis!='player_performance':suggestions.append(f'How is {service.store.players[pid].name} doing in this match?')
        if plan.analysis!='match_changes':suggestions.append('What has changed in this match?')
        return suggestions[:2]
    if plan.player_ids:
        name=service.store.players[plan.player_ids[0]].name
        return [f'How is {name} doing recently?',f'How many assists does {name} have?',f'Compare {name} this season and last season']
    if plan.club_id:return [f'Who leads {service.store.clubs[plan.club_id].name} in goals?',f'Who leads {service.store.clubs[plan.club_id].name} in assists?']
    return ['How many goals does Mateo Cross have?','Who leads Redhaven in assists?','Compare Rory Ellis and Dario Voss in goals per 90']
