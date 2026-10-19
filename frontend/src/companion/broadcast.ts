import type {Event} from '../types'

export type BroadcastPlayer=(events:Event[],zh:boolean,detailed:boolean,done:()=>void,failed:()=>void)=>()=>void
export const playBroadcast:BroadcastPlayer=(events,zh,detailed,done,failed)=>{
  const controller=new AbortController(), audio=new Audio()
  let stopped=false,url:string|undefined
  const timeout=window.setTimeout(()=>{controller.abort()},8000)
  // The queue may have skipped routine events. Request only the actual narrated action.
  const shot=[...events].reverse().find(e=>e.action.kind==='shot')
  const contiguous=events.every((e,i)=>!i || e.occurrence_order===events[i-1].occurrence_order+1)
  const selected=shot?[shot]:contiguous?events:[events.at(-1)!]
  const last=selected.at(-1)!
  const release=()=>{clearTimeout(timeout);if(url){URL.revokeObjectURL(url);url=undefined}}
  const error=()=>{release();if(!stopped)failed()}
  audio.onended=()=>{release();if(!stopped)done()}
  audio.onerror=error
  fetch('/api/voice/commentary',{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({
    match_id:last.match_id,events:selected.map(e=>e.event_id),revisions:selected.map(e=>e.revision),
    cutoff:last.available_at,language:zh?'zh-Hans':'en',detailed,
  })}).then(async response=>{
    if(!response.ok || !response.headers.get('content-type')?.startsWith('audio/mpeg'))throw Error('Voice unavailable')
    const blob=await response.blob()
    if(stopped)return
    clearTimeout(timeout)
    url=URL.createObjectURL(blob);audio.src=url
    await audio.play()
  }).catch(()=>{if(!stopped)error()})
  return()=>{stopped=true;controller.abort();audio.pause();audio.removeAttribute('src');release()}
}
