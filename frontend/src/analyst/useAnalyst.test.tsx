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

it('recovers configuration after an explicit retry without paying while its availability is unknown',async()=>{
  const ordinary=vi.mocked(fetch).getMockImplementation()!
  let fail=true
  vi.mocked(fetch).mockImplementation(async(url,init)=>String(url)==='/api/analyst/config'&&fail?new Response('Unavailable',{status:503}):ordinary(url,init))
  const {result}=renderHook(()=>useAnalyst('match-one',{period:1,elapsed_ms:120000},true,prefs))
  await settle();expect(result.current.configFailed).toBe(true)
  expect(requests.some(r=>r.url.endsWith('/analysis'))).toBe(false)
  expect(result.current.snapshot).not.toBeNull()
  fail=false;act(()=>result.current.retryConfig());await settle();await settle()
  expect(result.current.configFailed).toBe(false)
  expect(requests.filter(r=>r.url.endsWith('/analysis'))).toHaveLength(1)
})

it('invalidates and submits the selected language, depth and player focus as one new scope',async()=>{
  const {result,rerender}=renderHook(({preferences})=>useAnalyst('match-one',{period:1,elapsed_ms:120000},true,preferences),{initialProps:{preferences:prefs as import('./data').Preferences}})
  await settle();await settle();expect(result.current.analysis).not.toBeNull()
  const changed={language:'zh-Hans' as const,depth:'casual' as const,focus_player_id:'eb09'}
  rerender({preferences:changed});expect(result.current.analysis).toBeNull()
  await settle()
  const last=requests.filter(r=>r.url.endsWith('/analysis')).at(-1)!
  expect(last.body).toEqual({cutoff:{period:1,elapsed_ms:120000},...changed})
})

it('runs one manual discussion while paused and clears it on rewind without paying again',async()=>{
  vi.stubGlobal('fetch',vi.fn(async(url:string,init?:RequestInit)=>{
    if(url==='/api/analyst/config')return new Response(JSON.stringify({...config,mode:'metrics',available:false,discussion_available:true}))
    const body=JSON.parse(String(init?.body));requests.push({url,body,signal:init!.signal as AbortSignal})
    return new Response(JSON.stringify(url.endsWith('/snapshot')?snapshot(body):{...analysis(body),messages:[{id:'control',role:'control',text:'Activity is increasing.',reply_to:null,relation:'observation',metric_ids:[],evidence_ids:[]}]}))
  }))
  const {result,rerender}=renderHook(({cutoff})=>useAnalyst('match-one',cutoff,false,prefs),{initialProps:{cutoff:{period:1 as const,elapsed_ms:120000}}})
  await settle();expect(requests.filter(r=>r.url.endsWith('/discussion'))).toHaveLength(0)
  act(()=>result.current.requestDiscussion());await settle();await settle()
  expect(requests.filter(r=>r.url.endsWith('/discussion'))).toHaveLength(1)
  expect(result.current.rounds).toHaveLength(1)
  rerender({cutoff:{period:1,elapsed_ms:60000}});await settle(5000)
  expect(result.current.rounds).toHaveLength(0)
  expect(requests.filter(r=>r.url.endsWith('/discussion'))).toHaveLength(1)
})

it('keeps statistics and configuration retries separate from paid discussion intent',async()=>{
  const ordinary=vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async(url,init)=>String(url)==='/api/analyst/config'?new Response(JSON.stringify({...config,discussion_available:true})):ordinary(url,init))
  const {result}=renderHook(()=>useAnalyst('match-one',{period:1,elapsed_ms:120000},false,prefs))
  await settle()
  act(()=>result.current.retrySnapshot());await settle()
  act(()=>result.current.retryConfig());await settle(5000)
  expect(requests.filter(r=>!r.url.endsWith('/snapshot'))).toHaveLength(0)
  expect(requests.filter(r=>r.url.endsWith('/snapshot'))).toHaveLength(2)
})

it('cancels a paused manual round on an explicit forward seek and ignores late results',async()=>{
  let resolve!:(r:Response)=>void,oldBody:any,signal:AbortSignal|undefined
  const ordinary=vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async(url,init)=>{
    if(String(url)==='/api/analyst/config')return new Response(JSON.stringify({...config,discussion_available:true}))
    if(String(url).endsWith('/discussion')){oldBody=JSON.parse(String(init?.body));signal=init?.signal as AbortSignal;return new Promise(r=>{resolve=r})}
    return ordinary(url,init)
  })
  const {result,rerender}=renderHook(({ms,seek})=>useAnalyst('match-one',{period:1,elapsed_ms:ms},false,prefs,seek),{initialProps:{ms:120000,seek:0}})
  await settle();act(()=>result.current.requestDiscussion());await settle()
  expect(signal?.aborted).toBe(false)
  rerender({ms:240000,seek:1});await settle()
  expect(signal?.aborted).toBe(true)
  await act(async()=>resolve(new Response(JSON.stringify({...analysis(oldBody),messages:[{id:'control',role:'control',text:'Old scope',reply_to:null,relation:'observation',metric_ids:[],evidence_ids:[]}]}))))
  expect(result.current.rounds).toHaveLength(0);expect(result.current.pending).toBe(false)
})

it('releases the pending UI on pause and sends a cancellation for the abandoned viewing session',async()=>{
  const ordinary=vi.mocked(fetch).getMockImplementation()!,cancelled:string[]=[]
  vi.mocked(fetch).mockImplementation(async(url,init)=>{
    if(String(url)==='/api/analyst/config')return new Response(JSON.stringify({...config,cancellation_available:true}))
    if(String(url).endsWith('/cancel')){cancelled.push(String(url));return new Response('{}')}
    if(String(url).endsWith('/analysis'))return new Response(JSON.stringify(analysis(JSON.parse(String(init?.body)),'pending')))
    return ordinary(url,init)
  })
  const {result,rerender}=renderHook(({playing})=>useAnalyst('match-one',{period:1,elapsed_ms:120000},playing,prefs),{initialProps:{playing:true}})
  await settle();await settle();expect(result.current.pending).toBe(true)
  rerender({playing:false});await settle()
  expect(result.current.pending).toBe(false);expect(cancelled).toHaveLength(1)
})

it('recovers from a stalled request without leaving discussion pending forever',async()=>{
  const ordinary=vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async(url,init)=>{
    if(String(url).endsWith('/analysis'))return new Promise((_,reject)=>init?.signal?.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError'))))
    return ordinary(url,init)
  })
  const {result}=renderHook(()=>useAnalyst('match-one',{period:1,elapsed_ms:120000},true,prefs))
  await settle();await settle();expect(result.current.pending).toBe(true)
  await settle(16000)
  expect(result.current.pending).toBe(false);expect(result.current.failed).toBe(true)
})

it('rejects malformed or future discussion evidence before it reaches the conversation',async()=>{
  const ordinary=vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async(url,init)=>{
    if(String(url).endsWith('/analysis'))return new Response(JSON.stringify({...analysis(JSON.parse(String(init?.body))),evidence:[{id:'future',event_id:'future',kind:'pass',outcome:'complete',revision:1,period:1,elapsed_ms:180000}]}))
    return ordinary(url,init)
  })
  const {result}=renderHook(()=>useAnalyst('match-one',{period:1,elapsed_ms:120000},true,prefs))
  await settle();await settle()
  expect(result.current.analysis).toBeNull();expect(result.current.failed).toBe(true)
})

it('publishes successive live specialist turns, polls each second and coalesces fast-forward time',async()=>{
  const ordinary=vi.mocked(fetch).getMockImplementation()!,polls=new Map<number,number>()
  vi.mocked(fetch).mockImplementation(async(url,init)=>{
    if(String(url)==='/api/analyst/config')return new Response(JSON.stringify({...config,discussion_available:true,discussion_style:'live'}))
    if(String(url).endsWith('/discussion')){
      const body=JSON.parse(String(init?.body)),t=body.cutoff.elapsed_ms,n=(polls.get(t)??0)+1;polls.set(t,n)
      requests.push({url:String(url),body,signal:init!.signal as AbortSignal})
      return new Response(JSON.stringify({...analysis(body,n===1?'pending':'complete'),messages:n===1?[]:[{id:'control',role:'control',text:`Reviewed turn ${t}`,reply_to:null,relation:'observation',metric_ids:[],evidence_ids:[],verified_by:'footie'}]}))
    }
    return ordinary(url,init)
  })
  const {result,rerender}=renderHook(({ms})=>useAnalyst('match-one',{period:1,elapsed_ms:ms},true,prefs),{initialProps:{ms:60000}})
  await settle();await settle();expect(result.current.pending).toBe(true)
  rerender({ms:180000});await settle(1100)
  expect(result.current.rounds).toHaveLength(1)
  await settle(2200)
  expect(result.current.rounds).toHaveLength(2)
  expect([...polls.keys()]).toEqual([60000,180000])
  expect(result.current.rounds.map(r=>r.cutoff.elapsed_ms)).toEqual([60000,180000])
})


it('publishes slow statistics during fast forward playback and coalesces skipped buckets',async()=>{
  let resolve!:(r:Response)=>void,firstBody:any,signal:AbortSignal|undefined
  const ordinary=vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async(url,init)=>{
    if(String(url).endsWith('/snapshot')&&!resolve){firstBody=JSON.parse(String(init?.body));signal=init?.signal as AbortSignal;requests.push({url:String(url),body:firstBody,signal});return new Promise(r=>{resolve=r})}
    return ordinary(url,init)
  })
  const {result,rerender}=renderHook(({cutoff,seek})=>useAnalyst('match-one',cutoff,false,prefs,seek),{initialProps:{cutoff:{period:1 as const,elapsed_ms:60000},seek:0}})
  await settle()
  for(const elapsed_ms of [75000,90000,105000,120000]){rerender({cutoff:{period:1,elapsed_ms},seek:0});await settle(500)}
  expect(signal!.aborted).toBe(false)
  expect(requests.filter(r=>r.url.endsWith('/snapshot'))).toHaveLength(1)
  await act(async()=>resolve(new Response(JSON.stringify(snapshot(firstBody)))))
  expect(result.current.snapshot?.cutoff.elapsed_ms).toBe(60000)
  await settle()
  expect(requests.filter(r=>r.url.endsWith('/snapshot')).map(r=>r.body.cutoff.elapsed_ms)).toEqual([60000,120000])
  expect(result.current.snapshot?.cutoff.elapsed_ms).toBe(120000)
})

it('aborts a slow statistics request on explicit seek and rejects its late response',async()=>{
  let resolve!:(r:Response)=>void,firstBody:any,signal:AbortSignal|undefined
  const ordinary=vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async(url,init)=>{
    if(String(url).endsWith('/snapshot')&&!resolve){firstBody=JSON.parse(String(init?.body));signal=init?.signal as AbortSignal;return new Promise(r=>{resolve=r})}
    return ordinary(url,init)
  })
  const {result,rerender}=renderHook(({cutoff,seek})=>useAnalyst('match-one',cutoff,false,prefs,seek),{initialProps:{cutoff:{period:1 as const,elapsed_ms:60000},seek:0}})
  await settle();rerender({cutoff:{period:1,elapsed_ms:180000},seek:1});expect(signal!.aborted).toBe(true)
  await settle();expect(result.current.snapshot?.cutoff.elapsed_ms).toBe(180000)
  await act(async()=>resolve(new Response(JSON.stringify(snapshot(firstBody)))))
  expect(result.current.snapshot?.cutoff.elapsed_ms).toBe(180000)
})

it('keeps an unavailable discussion marked failed when its old packet expires, then clears failure on a successful retry',async()=>{
 const ordinary=vi.mocked(fetch).getMockImplementation()!
 let unavailable=true
 vi.mocked(fetch).mockImplementation(async(url,init)=>String(url).endsWith('/analysis')&&unavailable?new Response(JSON.stringify(analysis(JSON.parse(String(init?.body)),'unavailable'))):ordinary(url,init))
 const {result,rerender}=renderHook(({cutoff,playing})=>useAnalyst('match-one',cutoff,playing,prefs),{initialProps:{cutoff:{period:1 as const,elapsed_ms:120000},playing:true}})
 await settle();await settle()
 expect(result.current.failed).toBe(true)
 rerender({cutoff:{period:1,elapsed_ms:360000},playing:false})
 expect(result.current.analysis).toBeNull()
 expect(result.current.failed).toBe(true)
 unavailable=false
 act(()=>result.current.requestDiscussion());await settle();await settle()
 expect(result.current.failed).toBe(false)
 expect(result.current.analysis?.status).toBe('complete')
})

it.each(['hourly_limit','daily_limit','budget_limit','disabled'])('retains %s independently of packet freshness and clears it on match change',status=>{
 return (async()=>{
  const ordinary=vi.mocked(fetch).getMockImplementation()!
  vi.mocked(fetch).mockImplementation(async(url,init)=>String(url).endsWith('/analysis')?new Response(JSON.stringify(analysis(JSON.parse(String(init?.body)),status))):ordinary(url,init))
  const {result,rerender}=renderHook(({match,cutoff,playing})=>useAnalyst(match,cutoff,playing,prefs),{initialProps:{match:'match-one',cutoff:{period:1 as const,elapsed_ms:120000},playing:true}})
  await settle();await settle()
  rerender({match:'match-one',cutoff:{period:1,elapsed_ms:360000},playing:false})
  expect(result.current.analysis).toBeNull()
  expect(result.current.discussionStatus).toBe(status)
  rerender({match:'match-two',cutoff:{period:1,elapsed_ms:0},playing:false})
  expect(result.current.discussionStatus).toBeUndefined()
 })()
})
