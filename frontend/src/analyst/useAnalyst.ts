import {useEffect,useRef,useState} from 'react'
import {CAREER_CHANGED} from '../football/revisions'
import {before,bucket,sameCutoff,validateAnalysis,validateSnapshot} from './data'
import type {Analysis,AnalystConfig,Cutoff,Preferences,Snapshot} from './data'

/** One shared packet per source-clock bucket. Rendering frames never call a model. */
export function useAnalyst(matchId:string,cutoff:Cutoff,playing:boolean,preferences:Preferences){
  const [config,setConfig]=useState<AnalystConfig|null>(null)
  const [visible,setVisible]=useState(()=>!document.hidden)
  const [revision,setRevision]=useState(0)
  const [retry,setRetry]=useState(0)
  const [metrics,setMetrics]=useState<{scope:string;view?:Snapshot;failed?:boolean}>({scope:''})
  const [intel,setIntel]=useState<{scope:string;view?:Analysis;pending?:boolean;failed?:boolean}>({scope:''})
  const epoch=useRef(0),previous=useRef({matchId,cutoff,prefs:JSON.stringify(preferences)})
  const prefs=JSON.stringify(preferences)
  if(previous.current.matchId!==matchId||previous.current.prefs!==prefs||before(cutoff,previous.current.cutoff)||cutoff.period!==previous.current.cutoff.period)epoch.current++
  previous.current={matchId,cutoff,prefs}
  const scope=JSON.stringify([matchId,prefs,revision,epoch.current])
  const metricCutoff=bucket(cutoff,15000)
  const interval=Math.max(60000,config?.interval_ms??60000)
  const currentScope=useRef(scope);currentScope.current=scope
  const latestCutoff=useRef(cutoff);latestCutoff.current=cutoff
  useEffect(()=>{
    const controller=new AbortController()
    fetch('/api/analyst/config',{signal:controller.signal}).then(r=>{if(!r.ok)throw Error();return r.json()}).then(c=>{
      if(!controller.signal.aborted&&c&&['foundry','metrics'].includes(c.mode)&&Number.isFinite(c.interval_ms)&&Array.isArray(c.roles))setConfig(c)
    }).catch(()=>{})
    return()=>controller.abort()
  },[])
  useEffect(()=>{
    const change=()=>setVisible(!document.hidden)
    const corrected=(event:Event)=>{const d=(event as CustomEvent<{matches:string[];datasetChanged:boolean}>).detail;if(!d||d.datasetChanged||d.matches.includes(matchId))setRevision(n=>n+1)}
    document.addEventListener('visibilitychange',change);window.addEventListener(CAREER_CHANGED,corrected)
    return()=>{document.removeEventListener('visibilitychange',change);window.removeEventListener(CAREER_CHANGED,corrected)}
  },[matchId])
  useEffect(()=>{
    if(!visible)return
    let active=true;const controller=new AbortController()
    const at={period:metricCutoff.period,elapsed_ms:metricCutoff.elapsed_ms}
    const timer=setTimeout(()=>{
      fetch(`/api/analyst/matches/${encodeURIComponent(matchId)}/snapshot`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cutoff:at,...preferences}),signal:controller.signal}).then(r=>{if(!r.ok)throw Error();return r.json()}).then(view=>{
        if(!validateSnapshot(view,matchId,at))throw Error()
        if(active&&currentScope.current===scope)setMetrics({scope,view})
      }).catch(e=>{if(active&&e.name!=='AbortError'&&currentScope.current===scope)setMetrics({scope,failed:true})})
    },100)
    return()=>{active=false;clearTimeout(timer);controller.abort()}
  },[matchId,metricCutoff.period,metricCutoff.elapsed_ms,scope,visible,retry])
  // A forward source-clock boundary does not cancel a running Foundry turn.
  // Finish it, then coalesce all skipped buckets into the newest eligible one.
  useEffect(()=>{
    if(!visible||!playing||config?.mode!=='foundry'||!config.available)return
    let active=true,timer:ReturnType<typeof setTimeout>|undefined,lastAttempt:Cutoff|undefined
    const controller=new AbortController()
    const schedule=(fn:()=>void,delay:number)=>{if(active)timer=setTimeout(fn,delay)}
    function next(){
      if(!active)return
      const at=bucket(latestCutoff.current,interval)
      if(at.elapsed_ms<interval||lastAttempt&&sameCutoff(at,lastAttempt)){schedule(next,1000);return}
      lastAttempt=at
      setIntel(old=>({scope,view:old.scope===scope?old.view:undefined,pending:true}))
      void request(at,Date.now())
    }
    async function request(at:Cutoff,start:number){
      try{
        const response=await fetch(`/api/analyst/matches/${encodeURIComponent(matchId)}/analysis`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cutoff:at,...preferences}),signal:controller.signal})
        if(!response.ok)throw Error()
        const view=await response.json()
        if(!validateAnalysis(view,at,matchId))throw Error()
        if(!active||currentScope.current!==scope||before(latestCutoff.current,at))return
        if(view.status==='pending'){
          if(Date.now()-start<120000){schedule(()=>void request(at,start),3000);return}
          setIntel(old=>({scope,view:old.scope===scope?old.view:undefined,failed:true,pending:false}))
        }else setIntel({scope,view,pending:false})
        // An exhausted allowance is terminal for this viewing run; manual retry
        // or a fresh session can check it later without a request every minute.
        if(!['hourly_limit','daily_limit','budget_limit','disabled'].includes(view.status))schedule(next,1000)
      }catch(e){if(active&&!controller.signal.aborted&&currentScope.current===scope){setIntel(old=>({scope,view:old.scope===scope?old.view:undefined,failed:true,pending:false}));schedule(next,1000)}}
    }
    schedule(next,200)
    return()=>{active=false;clearTimeout(timer);controller.abort()}
  },[matchId,scope,visible,playing,config?.mode,config?.available,interval,retry])
  const snapshot=metrics.scope===scope&&metrics.view&&!before(cutoff,metrics.view.cutoff)?metrics.view:null
  const analysis=intel.scope===scope&&intel.view&&!before(cutoff,intel.view.cutoff)&&cutoff.period===intel.view.cutoff.period&&cutoff.elapsed_ms-intel.view.cutoff.elapsed_ms<=180000?intel.view:null
  return {config,snapshot,analysis,pending:playing&&visible&&intel.scope===scope&&!!intel.pending,failed:intel.scope===scope&&intel.failed,metricsFailed:metrics.scope===scope&&metrics.failed,refresh:()=>setRetry(n=>n+1)}
}
