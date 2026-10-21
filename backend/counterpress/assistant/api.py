"""Bounded local assistant. Model interpretation is explicit opt-in, off in hosted defaults."""
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

log=logging.getLogger('uvicorn.error.footie')


def install_assistant(app,career_service,planner=None,narrator=None):
    if planner is None and os.environ.get('COUNTERPRESS_ASSISTANT_MODEL')=='azure':
        config=load_config()
        if config:
            planner=AzurePlanner(config)
            narrator=narrator or AzureNarrator(config)
    router=APIRouter(prefix='/api/fan/assistant',tags=['Football assistant'])
    calls=deque();model_calls=deque();gate=asyncio.Semaphore(2)
    def reserve_model_call():
        now=time.monotonic()
        while model_calls and now-model_calls[0]>=3600:model_calls.popleft()
        if len(model_calls)>=20:return False
        model_calls.append(now)
        return True
    @lru_cache(maxsize=1)
    def service():return AssistantService(career_service())

    @router.get('/config')
    def config():
        return {'available':True,'natural_language':planner is not None,'narrative_selection':narrator is not None,'name':'Footie','storage':'session',
                'max_question_characters':600,'model_requests_per_hour':20 if planner or narrator else 0}

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
        mode='lookup';usage={};reason=None
        try:
            s=service();FanService(s.career).validate(body.preferences)
            local=s.local_plan(body);plan=local
            if planner and not UNSUPPORTED.search(body.question):
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
                    try:return s.answer(plan,body),plan
                    except (ValueError,KeyError):return s.answer(blank('clarify'),body),blank('clarify')
            answer,plan=await run_in_threadpool(execute)
            claims=build_claims(answer,plan,body)
            story=default_story(claims,body.preferences.depth)
            story_mode='calculated';story_reason=None;story_usage={}
            if narrator and claims and mode!='lookup_fallback':
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
                fresh,fresh_plan=await run_in_threadpool(execute)
                if fingerprint(fresh)!=fingerprint(answer):
                    answer,plan=fresh,fresh_plan
                    claims=build_claims(answer,plan,body)
                    story=default_story(claims,body.preferences.depth)
                    story_mode='calculated';story_reason='records_changed'
            answer['narrative']={'mode':story_mode,'blocks':story,'fallback_reason':story_reason}
            answer.update({'request_id':request_id,'plan':plan.model_dump(),'as_of':s.scope(body)[0],
                'mode':mode,'fallback_reason':reason,'answer_id':fingerprint({'plan':plan.model_dump(),'facts':answer['facts']}),
                'suggestions':suggestions(s,body,plan)})
            # Operational fields only: never prompts, credentials, endpoints or conversation bodies.
            log.info('assistant_request %s',json.dumps({'request_id':request_id,'mode':mode,'operation':plan.operation,'status':answer['status'],
                'duration_ms':round((time.monotonic()-started)*1000),'usage':usage,'fallback':reason,
                'narrative_mode':story_mode,'narrative_fallback':story_reason,'narrative_usage':story_usage}))
            return answer
        except PreferenceError:raise HTTPException(422,'Choose valid player and club preferences.') from None
        except (OSError,sqlite3.Error,ValueError,KeyError,HistoryStorageError):raise HTTPException(503,'The match records are temporarily unavailable. Please try again.') from None

    app.include_router(router)
    app.state.assistant_service=service


def suggestions(service,body,plan):
    if plan.player_ids:
        name=service.store.players[plan.player_ids[0]].name
        return [f'How is {name} doing recently?',f'How many assists does {name} have?',f'Compare {name} this season and last season']
    if plan.club_id:return [f'Who leads {service.store.clubs[plan.club_id].name} in goals?',f'Who leads {service.store.clubs[plan.club_id].name} in assists?']
    return ['How many goals does Mateo Cross have?','Who leads Redhaven in assists?','Compare Rory Ellis and Dario Voss in goals per 90']
