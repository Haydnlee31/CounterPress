import {act,cleanup,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {CAREER_CHANGED,watchCareerRevisions} from './revisions'
import {useResource} from './data'
const dataset='a'.repeat(64)
const response=(value:unknown)=>new Response(JSON.stringify(value))
let state={dataset,generation:0,enabled:true,matches:{} as Record<string,number>}
let sockets:Socket[]=[]
class Socket{
 onopen:(()=>void)|null=null;onmessage:((e:{data:string})=>void)|null=null;onerror:(()=>void)|null=null;onclose:(()=>void)|null=null
 constructor(public url:string){sockets.push(this)}
 close(){this.onclose?.()}
}
beforeEach(()=>{
 state={dataset,generation:0,enabled:true,matches:{}};sockets=[]
 vi.stubGlobal('WebSocket',Socket)
 vi.stubGlobal('fetch',vi.fn(async(url:string)=>response(url.endsWith('negotiate')?{enabled:true,url:'wss://test.webpubsub.azure.com/client?access_token=not-a-real-token'}:state)))
})
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks()})
it('treats push as a hint, rejects wrong scopes and catches up after reconnect',async()=>{
 const changed=vi.fn();window.addEventListener(CAREER_CHANGED,changed)
 const stop=watchCareerRevisions()
 try{
  await waitFor(()=>expect(sockets.length).toBe(1))
  const socket=sockets[0]
  socket.onmessage?.({data:JSON.stringify({type:'career.changed',schema_version:1,dataset:'b'.repeat(64),generation:1})})
  expect(changed).not.toHaveBeenCalled()
  // A valid hint without a durable commit must not invalidate any statistics.
  socket.onmessage?.({data:JSON.stringify({type:'career.changed',schema_version:1,dataset,generation:99})})
  await waitFor(()=>expect(vi.mocked(fetch).mock.calls.length).toBe(3))
  expect(changed).not.toHaveBeenCalled()
  state={...state,generation:2,matches:{match:2}}
  socket.onopen?.()
  await waitFor(()=>expect(changed).toHaveBeenCalledTimes(1))
  expect(changed.mock.calls[0][0].detail.matches).toEqual(['match'])
  socket.onmessage?.({data:'invalid json'})
  socket.onmessage?.({data:JSON.stringify({type:'career.changed',schema_version:1,dataset,generation:1})})
  expect(changed).toHaveBeenCalledTimes(1)
 }finally{stop();window.removeEventListener(CAREER_CHANGED,changed)}
})
it('ignores a late response after cleanup',async()=>{
 let finish!:(r:Response)=>void
 vi.mocked(fetch).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}))
 const changed=vi.fn();window.addEventListener(CAREER_CHANGED,changed)
 const stop=watchCareerRevisions();stop()
 finish(response({...state,generation:1,matches:{match:1}}))
 await new Promise(resolve=>setTimeout(resolve,0))
 expect(changed).not.toHaveBeenCalled();expect(sockets).toHaveLength(0)
 window.removeEventListener(CAREER_CHANGED,changed)
})
it('aborts stale resource reads, leaves unrelated replay and static registry alone',async()=>{
 const loads:((v:string)=>void)[]=[],signals:AbortSignal[]=[]
 const load=vi.fn((signal:AbortSignal)=>{signals.push(signal);return new Promise<string>(resolve=>loads.push(resolve))})
 const other=vi.fn(async()=>'other replay'),registry=vi.fn(async()=>'registry')
 function View(){
  const a=useResource('profile',load),b=useResource('replay',other,'unaffected'),c=useResource('world',registry,false)
  return <div>{a.data??'updating'} {b.data} {c.data}</div>
 }
 render(<View/>);await screen.findByText(/other replay registry/)
 act(()=>{window.dispatchEvent(new CustomEvent(CAREER_CHANGED,{detail:{matches:['changed'],datasetChanged:false}}))})
 expect(signals[0].aborted).toBe(true)
 await act(async()=>{loads[0]('stale');loads[1]('current')})
 expect(screen.queryByText(/stale/)).toBeNull();expect(screen.getByText(/current/)).toBeTruthy()
 expect(other).toHaveBeenCalledTimes(1);expect(registry).toHaveBeenCalledTimes(1)
 act(()=>{window.dispatchEvent(new CustomEvent(CAREER_CHANGED,{detail:{matches:[],datasetChanged:true}}))})
 await waitFor(()=>expect(registry).toHaveBeenCalledTimes(2))
 expect(other).toHaveBeenCalledTimes(2)
})
