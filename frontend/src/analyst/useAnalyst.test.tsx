import {act,cleanup,renderHook} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {useAnalyst} from './useAnalyst'
import type {Cutoff} from './data'
import {CAREER_CHANGED} from '../football/revisions'

const prefs={language:'en' as const,depth:'analyst' as const,focus_player_id:null}
const requests:{url:string;body:any;signal:AbortSignal}[]=[]
const config={available:true,mode:'foundry',roles:[],interval_ms:60000}
const snapshot=(body:any,matchId='match-one')=>({snapshot_id:`s-${body.cutoff.elapsed_ms}`,match_id:matchId,cutoff:body.cutoff,through_sequence:1,clubs:[],players:[],metrics:[],signals:[],evidence:[]})
const analysis=(body:any,status='complete')=>({snapshot_id:`s-${body.cutoff.elapsed_ms}`,cutoff:body.cutoff,mode:'foundry',status,readings:[],summary:status==='complete'?{headline:'Space after the regain',explanation:'The last recovery led straight to a chance.',evidence_ids:[],metric_ids:[]}:null})
const settle=async(ms=250)=>act(async()=>{await vi.advanceTimersByTimeAsync(ms)})
function mockFetch(mode='foundry'){
  vi.stubGlobal('fetch',vi.fn(async(url:string,init?:RequestInit)=>{
    if(url==='/api/analyst/config')return new Response(JSON.stringify({...config,mode}))
    const body=JSON.parse(String(init?.body));requests.push({url,body,signal:init!.signal as AbortSignal})
    return new Response(JSON.stringify(url.endsWith('/snapshot')?snapshot(body,url.includes('match-two')?'match-two':'match-one'):analysis(body)))
  }))
}
beforeEach(()=>{vi.useFakeTimers();requests.length=0;vi.spyOn(document,'hidden','get').mockReturnValue(false);mockFetch()})
afterEach(()=>{cleanup();vi.useRealTimers();vi.unstubAllGlobals();vi.restoreAllMocks()})

it('fetches metrics in fifteen-second buckets and does not pay for render ticks',async()=>{
  const {result,rerender}=renderHook(({cutoff,playing})=>useAnalyst('match-one',cutoff,playing,prefs),{initialProps:{cutoff:{period:1 as const,elapsed_ms:60000},playing:true}})
  await settle();await settle()
  expect(requests.filter(r=>r.url.endsWith('/analysis'))).toHaveLength(1)
  expect(result.current.analysis?.summary?.headline).toBe('Space after the regain')
  for(let n=0;n<60;n++)rerender({cutoff:{period:1,elapsed_ms:60000+n*100},playing:true})
  await settle()
  expect(requests.filter(r=>r.url.endsWith('/analysis'))).toHaveLength(1)
  expect(requests.filter(r=>r.url.endsWith('/snapshot'))).toHaveLength(1)
  rerender({cutoff:{period:1,elapsed_ms:76000},playing:true});await settle()
  expect(requests.filter(r=>r.url.endsWith('/snapshot'))).toHaveLength(2)
  expect(requests.at(-1)!.body.cutoff.elapsed_ms).toBe(75000)
})

it('never dispatches paid analysis while paused or in metrics mode',async()=>{
  const {rerender,unmount}=renderHook(({playing})=>useAnalyst('match-one',{period:1,elapsed_ms:120000},playing,prefs),{initialProps:{playing:false}})
  await settle();await settle(10000)
  expect(requests.some(r=>r.url.endsWith('/analysis'))).toBe(false)
  unmount();requests.length=0;mockFetch('metrics')
  renderHook(()=>useAnalyst('match-one',{period:1,elapsed_ms:120000},true,prefs));await settle();await settle(10000)
  expect(requests.some(r=>r.url.endsWith('/analysis'))).toBe(false)
})

it('clears old insight immediately when seeking backwards, even within one bucket',async()=>{
  const {result,rerender}=renderHook(({cutoff})=>useAnalyst('match-one',cutoff,true,prefs),{initialProps:{cutoff:{period:1 as const,elapsed_ms:125000}}})
  await settle();await settle();expect(result.current.analysis).not.toBeNull()
  rerender({cutoff:{period:1,elapsed_ms:124000}})
  expect(result.current.analysis).toBeNull();expect(result.current.snapshot).toBeNull()
  await settle();expect(requests.filter(r=>r.url.endsWith('/analysis'))).toHaveLength(2)
})

it('ignores an old provider response after a match change, even if abort is ignored',async()=>{
  let resolve!:(r:Response)=>void,oldBody:any
  const ordinary=vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async(url,init)=>{
    if(String(url).endsWith('/analysis')&&String(url).includes('match-one')){oldBody=JSON.parse(String(init?.body));return new Promise(r=>{resolve=r})}
    return ordinary(url,init)
  })
  const {result,rerender}=renderHook(({match})=>useAnalyst(match,{period:1,elapsed_ms:120000},true,prefs),{initialProps:{match:'match-one'}})
  await settle();await settle();expect(resolve).toBeDefined()
  rerender({match:'match-two'});await settle()
  await act(async()=>resolve(new Response(JSON.stringify({...analysis(oldBody),summary:{headline:'Stale old match',explanation:'Old',metric_ids:[],evidence_ids:[]}}))))
  expect(result.current.analysis?.summary?.headline).not.toBe('Stale old match')
  expect(result.current.snapshot?.match_id).toBe('match-two')
})

it('polls a pending packet and stops immediately on pause or hidden tab',async()=>{
  const ordinary=vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async(url,init)=>{
    if(String(url).endsWith('/analysis')){const body=JSON.parse(String(init?.body));requests.push({url:String(url),body,signal:init!.signal as AbortSignal});return new Response(JSON.stringify(analysis(body,'pending')))}
    return ordinary(url,init)
  })
  const {rerender}=renderHook(({playing})=>useAnalyst('match-one',{period:1,elapsed_ms:120000},playing,prefs),{initialProps:{playing:true}})
  await settle();await settle();await settle(3100)
  expect(requests.filter(r=>r.url.endsWith('/analysis'))).toHaveLength(2)
  rerender({playing:false});await settle(10000)
  expect(requests.filter(r=>r.url.endsWith('/analysis'))).toHaveLength(2)
  rerender({playing:true});await settle();const count=requests.length
  vi.spyOn(document,'hidden','get').mockReturnValue(true)
  act(()=>document.dispatchEvent(new Event('visibilitychange')));await settle(10000)
  expect(requests).toHaveLength(count)
})

it('withdraws readings on source corrections and rejects mismatched response cutoffs',async()=>{
  const {result}=renderHook(()=>useAnalyst('match-one',{period:1,elapsed_ms:120000},true,prefs))
  await settle();await settle();expect(result.current.analysis).not.toBeNull()
  act(()=>window.dispatchEvent(new CustomEvent(CAREER_CHANGED,{detail:{matches:['match-one'],datasetChanged:false}})))
  expect(result.current.analysis).toBeNull()
  const ordinary=vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async(url,init)=>String(url).endsWith('/analysis')?new Response(JSON.stringify(analysis({cutoff:{period:2,elapsed_ms:120000}}))):ordinary(url,init))
  await settle();expect(result.current.analysis).toBeNull();expect(result.current.failed).toBe(true)
})

it('does not retry terminal allowance responses or continue polling beyond two minutes',async()=>{
  let status='budget_limit'
  const ordinary=vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async(url,init)=>{
    if(String(url).endsWith('/analysis')){const body=JSON.parse(String(init?.body));requests.push({url:String(url),body,signal:init!.signal as AbortSignal});return new Response(JSON.stringify(analysis(body,status)))}
    return ordinary(url,init)
  })
  const {result,rerender}=renderHook(({cutoff})=>useAnalyst('match-one',cutoff,true,prefs),{initialProps:{cutoff:{period:1 as const,elapsed_ms:120000}}})
  await settle();await settle(150000);expect(requests.filter(r=>r.url.endsWith('/analysis'))).toHaveLength(1)
  expect(result.current.analysis?.status).toBe('budget_limit')
  status='pending';rerender({cutoff:{period:1,elapsed_ms:180000}});await settle();await settle(123000)
  const count=requests.length;expect(result.current.pending).toBe(false)
  await settle(10000);expect(requests).toHaveLength(count)
})

it('finishes an in-flight reading across forward boundaries, then coalesces to the newest window',async()=>{
  let ready=false
  const ordinary=vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async(url,init)=>{
    if(String(url).endsWith('/analysis')){const body=JSON.parse(String(init?.body));requests.push({url:String(url),body,signal:init!.signal as AbortSignal});return new Response(JSON.stringify(analysis(body,ready?'complete':'pending')))}
    return ordinary(url,init)
  })
  const {result,rerender}=renderHook(({cutoff})=>useAnalyst('match-one',cutoff,true,prefs),{initialProps:{cutoff:{period:1 as const,elapsed_ms:60000}}})
  await settle();await settle()
  const first=requests.find(r=>r.url.endsWith('/analysis'))!
  rerender({cutoff:{period:1,elapsed_ms:120000}});await settle()
  rerender({cutoff:{period:1,elapsed_ms:180000}});await settle()
  expect(first.signal.aborted).toBe(false)
  expect(requests.filter(r=>r.url.endsWith('/analysis'))).toHaveLength(1)
  ready=true;await settle(3000)
  expect(result.current.analysis?.cutoff.elapsed_ms).toBe(60000)
  await settle(1000)
  const clocks=requests.filter(r=>r.url.endsWith('/analysis')).map(r=>r.body.cutoff.elapsed_ms)
  expect(clocks).toEqual([60000,60000,180000])
  expect(result.current.analysis?.cutoff.elapsed_ms).toBe(180000)
})
