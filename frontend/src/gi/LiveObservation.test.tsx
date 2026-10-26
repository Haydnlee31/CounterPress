import {act,cleanup,fireEvent,render,screen} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {defaults,preferenceKey} from '../../../integrations/personalization/client'
import {CAREER_CHANGED} from '../football/revisions'
import {completedObservationCutoff,LiveObservation} from './LiveObservation'
import type {TimedAction} from './replay'
import type {FootieContext} from '../assistant/context'
import {AskFootie} from '../assistant/AskFootie'
import {PlaySequence} from './PlaySequence'
import type {GIEvent,GIPlayer} from './data'
import {useState} from 'react'
import {createPortal} from 'react-dom'

const opened=vi.hoisted(()=>vi.fn())
vi.mock('../assistant/AskFootie',()=>({AskFootie:({context,onOpen,label}:{context:FootieContext;onOpen?:()=>void;label?:string})=>{
  const [frozen,setFrozen]=useState<FootieContext|null>(null)
  return <><button onClick={()=>{onOpen?.();opened(context);setFrozen(structuredClone(context))}}>{label??'Ask Footie'}</button>{frozen&&createPortal(<div role="dialog" aria-label="Frozen observation conversation"><span>{frozen.label}</span><span>{frozen.observationId}</span><span>{frozen.cutoff?.elapsed_ms}</span><button onClick={()=>setFrozen(null)}>Close conversation</button></div>,document.body)}</>
}}))
vi.mock('../football/PlayerPeek',()=>({usePlayerPeek:()=>({bind:()=>({}),card:null})}))
const cutoff={period:1 as const,elapsed_ms:600000}
const onOpen=vi.fn()
const props={matchId:'match-one',cutoff,onOpen,children:<p>Original replay footer</p>}
const requests:{url:string;body:Record<string,any>;signal:AbortSignal}[]=[]
function reply(body:Record<string,any>,text='Eastbridge have taken 4 shots, up from 1.',empty=false){
  const end=body.cutoff.elapsed_ms
  return new Response(JSON.stringify({request_id:body.request_id,preferences:body.preferences,match_id:'match-one',cutoff:body.cutoff,through_sequence:42,
    observations:empty?[]:[{id:'shots-one',fingerprint:'a'.repeat(64),kind:'shots_increase',title:'Eastbridge are shooting more',text,club_id:'eastbridge',player_id:null,
      windows:[{period:body.cutoff.period,start_ms:end-360000,end_ms:end-180000,boundary:'(start,end]'},{period:body.cutoff.period,start_ms:end-180000,end_ms:end,boundary:'(start,end]'}]}]}))
}
const settle=()=>act(async()=>{await vi.advanceTimersByTimeAsync(150)})
beforeEach(()=>{
  vi.useFakeTimers();localStorage.clear();sessionStorage.clear();requests.length=0;opened.mockClear();onOpen.mockClear()
  vi.stubGlobal('fetch',vi.fn(async(url:string,init:RequestInit)=>{
    const body=JSON.parse(String(init.body));requests.push({url,body,signal:init.signal as AbortSignal});return reply(body)
  }))
})
afterEach(()=>{cleanup();vi.useRealTimers();vi.unstubAllGlobals();vi.restoreAllMocks()})

it('uses the completed event occurrence clock without jumping to late availability',()=>{
  const actions=[
    {at:0,duration:1000,resolved:.8,event:{period:1,elapsed_ms:600000,available_ms:640000}},
    {at:1000,duration:1000,resolved:.8,event:{period:1,elapsed_ms:603000}},
    {at:2000,duration:1000,resolved:.8,event:{period:2,elapsed_ms:1000}},
  ] as TimedAction[]
  expect(completedObservationCutoff(actions,799)).toBeUndefined()
  expect(completedObservationCutoff(actions,800)).toEqual(cutoff)
  expect(completedObservationCutoff(actions,1799)).toEqual(cutoff)
  expect(completedObservationCutoff(actions,1800)).toEqual({period:1,elapsed_ms:603000})
  expect(completedObservationCutoff(actions,2100)).toBeUndefined()
  expect(completedObservationCutoff(actions,2800)).toEqual({period:2,elapsed_ms:1000})
})

it('shows one quiet card and freezes its evidence, preferences and source cutoff for Ask Footie',async()=>{
  render(<LiveObservation {...props}/>);await settle()
  expect(screen.getByRole('complementary',{name:'Match insight'})).toBeTruthy()
  expect(screen.getByText('7:00 – 10:00')).toBeTruthy()
  expect(screen.getByText('Original replay footer').closest('[hidden]')).toBeTruthy()
  fireEvent.click(screen.getByRole('button',{name:'Ask Footie why'}))
  expect(onOpen).toHaveBeenCalledOnce()
  expect(opened).toHaveBeenCalledWith(expect.objectContaining({matchId:'match-one',cutoff,throughSequence:42,observationId:'shots-one',observationFingerprint:'a'.repeat(64),preferences:defaults()}))
  expect(requests).toHaveLength(1)
  expect(requests[0].body.card_budget).toBe(1)
  expect(requests[0].url).toBe('/api/fan/matches/match-one/observations')
})

it('does not request on animation rerenders and does not run a model automatically',async()=>{
  const {rerender}=render(<LiveObservation {...props}/>);await settle()
  for(let i=0;i<60;i++)rerender(<LiveObservation {...props} cutoff={{...cutoff}} onOpen={()=>{}}/>)
  await settle()
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(opened).not.toHaveBeenCalled()
})

it('preserves the original moment conversation when an observation arrives after opening it',async()=>{
  render(<LiveObservation {...props}><AskFootie context={{label:'Selected pass',question:'What happened?',cutoff}}/></LiveObservation>)
  fireEvent.click(screen.getByRole('button',{name:'Ask Footie'}))
  expect(screen.getByRole('dialog',{name:'Frozen observation conversation'})).toBeTruthy()
  await settle()
  expect(screen.getByRole('complementary',{name:'Match insight'})).toBeTruthy()
  expect(screen.getByRole('dialog',{name:'Frozen observation conversation'}).textContent).toContain('Selected pass')
  expect(screen.queryByRole('button',{name:'Ask Footie'})).toBeNull()
})

it('bridges a short forward refresh with its labelled earlier range, then clears an empty result',async()=>{
  const {rerender}=render(<LiveObservation {...props}/>);await settle()
  vi.mocked(fetch).mockImplementationOnce(async(_url,init)=>reply(JSON.parse(String(init?.body)),'',true))
  rerender(<LiveObservation {...props} cutoff={{period:1,elapsed_ms:603000}}/>)
  expect(screen.getByText('7:00 – 10:00')).toBeTruthy()
  await settle()
  expect(screen.queryByRole('complementary')).toBeNull()
  expect(screen.getByText('Original replay footer')).toBeTruthy()
})

it('clears immediately on backward seeks and ignores late superseded responses even when abort is ignored',async()=>{
  let resolve!:(value:Response)=>void
  vi.mocked(fetch).mockImplementationOnce(async(url,init)=>{
    const body=JSON.parse(String(init?.body));requests.push({url:String(url),body,signal:init?.signal as AbortSignal});return new Promise<Response>(r=>{resolve=r})
  })
  const {rerender}=render(<LiveObservation {...props}/>);await settle()
  const previous=requests[0]
  rerender(<LiveObservation {...props} cutoff={{period:1,elapsed_ms:580000}}/>);await settle()
  expect(previous.signal.aborted).toBe(true)
  await act(async()=>{resolve(reply(previous.body,'FUTURE CLAIM'));await Promise.resolve()})
  expect(screen.queryByText('FUTURE CLAIM')).toBeNull()
  expect(screen.getByText('6:40 – 9:40')).toBeTruthy()
  rerender(<LiveObservation {...props} cutoff={{period:1,elapsed_ms:570000}}/>)
  expect(screen.queryByRole('complementary')).toBeNull()
})

it('never bridges a large forward jump, another match, or the next half',async()=>{
  const {rerender}=render(<LiveObservation {...props}/>);await settle()
  rerender(<LiveObservation {...props} cutoff={{period:1,elapsed_ms:700000}}/>)
  expect(screen.queryByRole('complementary')).toBeNull()
  rerender(<LiveObservation {...props} matchId="match-two"/>)
  expect(screen.queryByRole('complementary')).toBeNull()
  rerender(<LiveObservation {...props} cutoff={{period:2,elapsed_ms:600000}}/>)
  expect(screen.queryByRole('complementary')).toBeNull()
})

it('invalidates for relevant corrections and preference changes, but not unrelated matches',async()=>{
  render(<LiveObservation {...props}/>);await settle()
  fireEvent(window,new CustomEvent(CAREER_CHANGED,{detail:{matches:['other-match'],datasetChanged:false}}))
  expect(screen.getByRole('complementary')).toBeTruthy();await settle();expect(fetch).toHaveBeenCalledTimes(1)
  fireEvent(window,new CustomEvent(CAREER_CHANGED,{detail:{matches:['match-one'],datasetChanged:false}}))
  expect(screen.queryByRole('complementary')).toBeNull();await settle();expect(fetch).toHaveBeenCalledTimes(2)
  localStorage.setItem(preferenceKey,JSON.stringify({...defaults(),language:'zh-Hans'}))
  fireEvent(window,new StorageEvent('storage',{key:preferenceKey}))
  expect(screen.queryByRole('complementary')).toBeNull();await settle()
  expect(screen.getByRole('button',{name:'问问 Footie 为什么'})).toBeTruthy()
  expect(requests.at(-1)?.body.preferences.language).toBe('zh-Hans')
})

it('does not request before enough of the half has played or while hidden',async()=>{
  const {rerender}=render(<LiveObservation {...props} cutoff={{period:1,elapsed_ms:359999}}/>);await settle()
  expect(fetch).not.toHaveBeenCalled()
  rerender(<LiveObservation {...props} visible={false}/>);await settle();expect(fetch).not.toHaveBeenCalled()
  rerender(<LiveObservation {...props}/>);await settle();expect(fetch).toHaveBeenCalledOnce()
  Object.defineProperty(document,'hidden',{configurable:true,value:true})
  fireEvent(document,new Event('visibilitychange'))
  expect(screen.queryByRole('complementary')).toBeNull()
  Object.defineProperty(document,'hidden',{configurable:true,value:false})
  fireEvent(document,new Event('visibilitychange'))
})

it('coalesces rapid seeks, fails closed for a mismatched source and offers a retry',async()=>{
  const {rerender}=render(<LiveObservation {...props}/>)
  for(let i=0;i<20;i++)rerender(<LiveObservation {...props} cutoff={{period:1,elapsed_ms:600000+i*1000}}/>)
  vi.mocked(fetch).mockImplementationOnce(async(_url,init)=>{
    const response=await reply(JSON.parse(String(init?.body))).json();response.match_id='another-match';return new Response(JSON.stringify(response))
  })
  await settle();expect(fetch).toHaveBeenCalledOnce();expect(screen.queryByRole('complementary')).toBeNull()
  fireEvent.click(screen.getByRole('button',{name:'Retry'}));await settle()
  expect(screen.getByRole('complementary')).toBeTruthy()
})

it('follows 2x replay only at completed actions, pauses requests with playback and clears on rewind',async()=>{
  const first:GIEvent={event_id:'first',revision:1,source_order:1,occurrence_order:1,provider_event_id:null,period:1,elapsed_ms:600000,
    available_period:1,available_ms:900000,player_id:'eb09',team_id:4418,kind:'Shot',detail:'Shot',outcome:'goal',start:{x:90,y:34},end:{x:105,y:34},goal_for:4418,tags:[],review:false}
  const second={...first,event_id:'second',source_order:2,occurrence_order:2,elapsed_ms:603000,available_ms:603000}
  const players:GIPlayer[]=[{player_id:'eb09',alias_id:'eb09',provider_player_id:null,team_id:4418}]
  let tick:FrameRequestCallback|undefined,now=0
  vi.spyOn(performance,'now').mockImplementation(()=>now)
  vi.stubGlobal('requestAnimationFrame',vi.fn((cb:FrameRequestCallback)=>{tick=cb;return 1}))
  vi.stubGlobal('cancelAnimationFrame',vi.fn())
  render(<PlaySequence matchId="match-one" events={[first,second]} event={first} players={players} names={new Map([['eb09','Rory Ellis']])} fullMatch/>)
  await settle();expect(fetch).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText('Sequence playback speed'),{target:{value:'2'}})
  fireEvent.click(screen.getByRole('button',{name:'Play match'}))
  for(let i=0;i<40;i++)await act(async()=>{now+=100;tick?.(now);await vi.advanceTimersByTimeAsync(100)})
  await settle()
  expect(requests.map(r=>r.body.cutoff.elapsed_ms)).toEqual([600000,603000])
  expect(screen.getByRole('button',{name:'Replay match'})).toBeTruthy()
  await act(async()=>{await vi.advanceTimersByTimeAsync(10000)})
  expect(fetch).toHaveBeenCalledTimes(2)
  fireEvent.change(screen.getByLabelText('Full match progress'),{target:{value:'0'}})
  expect(screen.queryByRole('complementary')).toBeNull();await settle()
  expect(fetch).toHaveBeenCalledTimes(2)
})

it('keeps the frozen conversation open when a pending forward refresh withdraws the card',async()=>{
  const {rerender}=render(<LiveObservation {...props}/>);await settle()
  vi.mocked(fetch).mockImplementationOnce(async(_url,init)=>reply(JSON.parse(String(init?.body)),'',true))
  rerender(<LiveObservation {...props} cutoff={{period:1,elapsed_ms:603000}}/>)
  fireEvent.click(screen.getByRole('button',{name:'Ask Footie why'}))
  expect(screen.getByRole('dialog',{name:'Frozen observation conversation'})).toBeTruthy()
  await settle()
  expect(screen.queryByRole('complementary')).toBeNull()
  expect(screen.getByRole('dialog',{name:'Frozen observation conversation'})).toBeTruthy()
  expect(screen.getByText('600000')).toBeTruthy()
  expect(screen.getByText('shots-one')).toBeTruthy()
  fireEvent.click(screen.getByRole('button',{name:'Close conversation'}))
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(screen.getByText('Original replay footer')).toBeTruthy()
})

it('preserves the open conversation across source correction invalidation and empty replacement',async()=>{
  render(<LiveObservation {...props}/>);await settle()
  fireEvent.click(screen.getByRole('button',{name:'Ask Footie why'}))
  vi.mocked(fetch).mockImplementationOnce(async(_url,init)=>reply(JSON.parse(String(init?.body)),'',true))
  fireEvent(window,new CustomEvent(CAREER_CHANGED,{detail:{matches:['match-one'],datasetChanged:false}}))
  expect(screen.queryByRole('complementary')).toBeNull()
  expect(screen.getByRole('dialog',{name:'Frozen observation conversation'})).toBeTruthy()
  await settle()
  expect(screen.queryByRole('complementary')).toBeNull()
  expect(screen.getByRole('dialog',{name:'Frozen observation conversation'})).toBeTruthy()
  expect(screen.getByText('shots-one')).toBeTruthy()
})

it.each(['missing-fields','wrong-window','bad-fingerprint','second-card'])('rejects malformed observation %s without crashing or displaying it',async(fault)=>{
  vi.mocked(fetch).mockImplementationOnce(async(_url,init)=>{
    const response=await reply(JSON.parse(String(init?.body))).json()
    if(fault==='missing-fields')response.observations=[{}]
    if(fault==='wrong-window')response.observations[0].windows[1].end_ms+=1
    if(fault==='bad-fingerprint')response.observations[0].fingerprint='unverified'
    if(fault==='second-card')response.observations.push(response.observations[0])
    return new Response(JSON.stringify(response))
  })
  render(<LiveObservation {...props}/>);await settle()
  expect(screen.queryByRole('complementary')).toBeNull()
  expect(screen.getByRole('button',{name:'Retry'})).toBeTruthy()
  expect(screen.getByText('Original replay footer')).toBeTruthy()
})
