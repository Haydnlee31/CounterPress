import {useEffect, useId, useState} from 'react'
import type {ReactNode} from 'react'
import {defaults, preferenceKey, readPreferences, validatePreferences} from '../../../integrations/personalization/client'
import type {Cutoff, FanPreferences} from '../../../integrations/personalization/client'
import {AskFootie} from '../assistant/AskFootie'
import {CAREER_CHANGED} from '../football/revisions'
import type {TimedAction} from './replay'
import './liveObservation.css'

type Observation = {
  id:string; fingerprint:string; kind:string; title:string; text:string;
  club_id:string; player_id:string|null;
  windows:{period:1|2;start_ms:number;end_ms:number;boundary:string}[];
}
type ObservationView = {
  match_id:string; cutoff:Cutoff; through_sequence:number; observations:Observation[];
  request_id:string; preferences:FanPreferences;
}

function validObservation(value:unknown,cutoff:Cutoff):value is Observation{
  if(!value||typeof value!=='object')return false
  const card=value as Observation
  const text=(value:unknown,limit:number)=>typeof value==='string'&&value.trim().length>0&&value.length<=limit
  const id=(value:unknown)=>typeof value==='string'&&/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}$/.test(value)
  return text(card.id,320)&&typeof card.fingerprint==='string'&&/^[a-f0-9]{64}$/.test(card.fingerprint)&&
    ['shots_increase','passing_decline','player_involvement'].includes(card.kind)&&text(card.title,200)&&text(card.text,2000)&&
    id(card.club_id)&&(card.player_id===null||id(card.player_id))&&Array.isArray(card.windows)&&card.windows.length===2&&
    card.windows.every((window,index)=>!!window&&window.period===cutoff.period&&window.boundary==='(start,end]'&&
      Number.isSafeInteger(window.start_ms)&&window.start_ms>=0&&window.start_ms===cutoff.elapsed_ms-(2-index)*180000&&
      Number.isSafeInteger(window.end_ms)&&window.end_ms===cutoff.elapsed_ms-(1-index)*180000)
}

/** The source clock advances only when an action has resolved, never per frame.
 * Do not jump to a late revision's availability time: that would reveal later play.
 */
export function completedObservationCutoff(actions:TimedAction[], clock:number):Cutoff|undefined {
  const current=actions.filter(a=>a.at<=clock).at(-1)
  const completed=actions.filter(a=>a.at+a.duration*a.resolved<=clock).at(-1)
  if(!completed||completed.event.period!==current?.event.period)return
  return {period:completed.event.period,elapsed_ms:completed.event.elapsed_ms}
}

function devicePreferences(){
  try{return readPreferences(window.localStorage).preferences}catch{return defaults()}
}

function clockLabel(ms:number,period:number){
  const seconds=Math.floor(ms/1000),minutes=Math.floor(seconds/60)
  return minutes>=45?`${period===1?45:90}+${minutes-45}:${String(seconds%60).padStart(2,'0')}`:
    `${minutes+(period===2?45:0)}:${String(seconds%60).padStart(2,'0')}`
}

/** One optional insight replaces the quiet replay footer; no extra control row. */
export function LiveObservation({matchId,cutoff,visible=true,onOpen,children}:{
  matchId?:string;cutoff?:Cutoff;visible?:boolean;onOpen:()=>void;children:ReactNode
}){
  const [preferences,setPreferences]=useState(devicePreferences)
  const [revision,setRevision]=useState(0),[retry,setRetry]=useState(0)
  const [tabVisible,setTabVisible]=useState(()=>!document.hidden)
  const [state,setState]=useState<{key:string;scope?:string;view?:ObservationView;failed?:boolean}>({key:''})
  const instance=useId().replace(/[^a-zA-Z0-9]/g,'')
  const prefKey=JSON.stringify(validatePreferences(preferences))
  const period=cutoff?.period,elapsed=cutoff?.elapsed_ms
  const enabled=visible&&tabVisible&&!!matchId&&elapsed!==undefined&&elapsed>=360000
  const scope=JSON.stringify([matchId,period,prefKey,revision,retry])
  const key=JSON.stringify([matchId,period,elapsed,prefKey,revision,retry,enabled])
  useEffect(()=>{
    const storage=(event:StorageEvent)=>{
      if(event.key===preferenceKey||event.key==='counterpress.matchday.preferences.v1'||event.key===null)setPreferences(devicePreferences())
    }
    const update=(event:Event)=>{
      const detail=(event as CustomEvent<{matches:string[];datasetChanged:boolean}>).detail
      if(!detail||detail.datasetChanged||detail.matches.includes(matchId??''))setRevision(v=>v+1)
    }
    const visibility=()=>{setTabVisible(!document.hidden);if(!document.hidden)setPreferences(devicePreferences())}
    window.addEventListener('storage',storage)
    window.addEventListener(CAREER_CHANGED,update)
    document.addEventListener('visibilitychange',visibility)
    return()=>{window.removeEventListener('storage',storage);window.removeEventListener(CAREER_CHANGED,update);document.removeEventListener('visibilitychange',visibility)}
  },[matchId])
  useEffect(()=>{
    if(!enabled)return
    const controller=new AbortController()
    let current=true
    const request_id=`observation-${instance}-${revision}-${retry}`
    // Coalesce scrubbing/rapid switches without waiting for playback to stop.
    const timer=setTimeout(async()=>{
      try{
        const response=await fetch(`/api/fan/matches/${encodeURIComponent(matchId!)}/observations`,{
          method:'POST',headers:{'Content-Type':'application/json'},cache:'no-store',credentials:'omit',signal:controller.signal,
          body:JSON.stringify({preferences,cutoff:{period,elapsed_ms:elapsed},card_budget:1,request_id}),
        })
        if(!response.ok)throw Error('Observation unavailable')
        const view=await response.json() as ObservationView
        if(view.request_id!==request_id||view.match_id!==matchId||view.cutoff?.period!==period||view.cutoff?.elapsed_ms!==elapsed||
          !Number.isSafeInteger(view.through_sequence)||view.through_sequence<0||!Array.isArray(view.observations)||
          view.observations.length>1||!view.observations.every(card=>validObservation(card,view.cutoff))||
          JSON.stringify(validatePreferences(view.preferences))!==prefKey)throw Error('Observation context changed')
        if(current)setState({key,scope,view})
      }catch{if(current&&!controller.signal.aborted)setState({key,failed:true})}
    },120)
    return()=>{current=false;clearTimeout(timer);controller.abort()}
  },[key]) // The key contains the entire viewing context, never animation progress.
  // A labelled earlier range can bridge a short forward refresh without flashing.
  // Backward seeks, half/match/preferences/revision changes invalidate it immediately.
  const age=elapsed===undefined||!state.view?Infinity:elapsed-state.view.cutoff.elapsed_ms
  const forwardBridge=state.scope===scope&&age>=0&&age<=15000
  const view=enabled&&(state.key===key||forwardBridge)?state.view:undefined
  const observation=view?.observations[0],observationWindow=observation?.windows.at(-1)
  const zh=preferences.language==='zh-Hans'
  const showCard=!!(view&&observation&&observationWindow)
  // Keep the launcher mounted even when its card is withdrawn. Its portal owns a
  // frozen conversation, which must survive pending refreshes and corrections.
  return <><div hidden={showCard}>{children}</div><aside hidden={!showCard} className="gi-observation" aria-label={zh?'比赛解读':'Match insight'}>
    <div className="gi-observation-heading"><span>{zh?'三分钟观察':'A 3-MINUTE SNAPSHOT'}</span><span>{observationWindow&&<>{clockLabel(observationWindow.start_ms,observationWindow.period)} – {clockLabel(observationWindow.end_ms,observationWindow.period)}</>}</span></div>
    <div className="gi-observation-body"><div><h3>{observation?.title}</h3><p>{observation?.text}</p></div>
      <AskFootie variant="pitch" label={zh?'问问 Footie 为什么':'Ask Footie why'} onOpen={onOpen} context={{
        label:observation?.title??'Match insight',question:zh?'为什么这段变化重要？':'What is driving this change?',
        matchId:view?.match_id,clubId:observation?.club_id,playerId:observation?.player_id??undefined,
        cutoff:view?.cutoff,throughSequence:view?.through_sequence,observationId:observation?.id,observationFingerprint:observation?.fingerprint,preferences:view?.preferences,
      }}/>
    </div>
  </aside>{enabled&&state.key===key&&state.failed&&<div className="gi-observation-error" role="status"><span>{zh?'暂时无法获取比赛解读':'Match insights are unavailable'}</span><button type="button" onClick={()=>setRetry(n=>n+1)}>{zh?'重试':'Retry'}</button></div>}</>
}
