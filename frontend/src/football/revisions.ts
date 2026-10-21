/** Revision messages are hints. Only a successful authoritative poll changes views. */
export const CAREER_CHANGED='footie:records-changed'
export type CareerRevision={dataset:string;generation:number;enabled:boolean;matches:Record<string,number>}
let epoch=0
export const careerEpoch=()=>epoch
export const onCareerChange=(listener:()=>void)=>{
  window.addEventListener(CAREER_CHANGED,listener)
  return()=>window.removeEventListener(CAREER_CHANGED,listener)
}

export function watchCareerRevisions(){
  let stopped=false,pending=false,again=false,previous:CareerRevision|undefined,socket:WebSocket|null=null
  let reconnectAt=0
  const abort=new AbortController()
  const valid=(s:CareerRevision)=>s&&/^[a-f0-9]{64}$/.test(s.dataset)&&Number.isSafeInteger(s.generation)&&s.generation>=0&&typeof s.enabled==='boolean'&&s.matches&&typeof s.matches==='object'&&!Array.isArray(s.matches)&&Object.values(s.matches).every(v=>Number.isSafeInteger(v)&&v>=0)
  async function connect(dataset:string){
    if(stopped||socket||Date.now()<reconnectAt)return
    reconnectAt=Date.now()+60000
    try{
      const response=await fetch('/api/data/revisions/negotiate',{signal:abort.signal,cache:'no-store',credentials:'omit'})
      if(!response.ok)return
      const config=await response.json()
      if(stopped||!config.enabled)return
      const url=new URL(config.url)
      if(url.protocol!=='wss:'||!url.hostname.endsWith('.webpubsub.azure.com')||url.username||url.password)return
      const current=new WebSocket(url.href);socket=current
      current.onopen=()=>{if(!stopped)void poll()}
      current.onmessage=event=>{
        if(stopped||socket!==current||typeof event.data!=='string'||event.data.length>4096)return
        try{
          const hint=JSON.parse(event.data)
          if(hint.type==='career.changed'&&hint.schema_version===1&&hint.dataset===dataset&&Number.isSafeInteger(hint.generation)&&hint.generation>(previous?.generation??-1))void poll()
        }catch{/* An invalid notification cannot change facts. */}
      }
      current.onerror=()=>current.close()
      current.onclose=()=>{if(socket===current)socket=null}
    }catch{/* Polling continues through service outages. */}
  }
  async function poll(){
    if(stopped||document.hidden)return
    if(pending){again=true;return}
    pending=true
    try{
      const response=await fetch('/api/data/revisions',{signal:abort.signal,cache:'no-store',credentials:'omit'})
      if(!response.ok)return
      const state=await response.json() as CareerRevision
      if(stopped||!valid(state))return
      if(previous&&state.dataset===previous.dataset&&state.generation<previous.generation)return
      const changed=previous?(state.dataset!==previous.dataset||state.generation!==previous.generation):state.generation>0
      const matches=Object.keys(state.matches).filter(id=>state.matches[id]!==previous?.matches[id])
      const datasetChanged=!!previous&&state.dataset!==previous.dataset
      if(datasetChanged){socket?.close();socket=null;reconnectAt=0}
      previous=state
      if(changed){epoch++;window.dispatchEvent(new CustomEvent(CAREER_CHANGED,{detail:{matches,datasetChanged}}))}
      if(state.enabled)void connect(state.dataset)
    }catch{/* Keep the last confirmed revision; do not invent a successful refresh. */}
    finally{pending=false;if(again&&!stopped){again=false;void poll()}}
  }
  const visible=()=>{if(!document.hidden)void poll()}
  document.addEventListener('visibilitychange',visible)
  // A small point-read heartbeat recovers missed push notifications and reconnects.
  const timer=setInterval(()=>{if(previous?.enabled!==false)void poll()},15000)
  void poll()
  return()=>{stopped=true;abort.abort();clearInterval(timer);socket?.close();document.removeEventListener('visibilitychange',visible)}
}
