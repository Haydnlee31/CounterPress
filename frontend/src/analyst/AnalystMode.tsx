import {FootieLoader} from '../shell/FootieLoader'
import {useCallback,useEffect,useMemo,useRef,useState} from 'react'
import {AppHeader} from '../shell/AppHeader'
import {PlaySequence} from '../gi/PlaySequence'
import type {ReplayPlayback} from '../gi/PlaySequence'
import {alias} from '../gi/data'
import type {GIMatch} from '../gi/data'
import {currentMatchId,matchDate,matchLibrary} from '../gi/catalog'
import {readPreferences} from '../../../integrations/personalization/client'
import {clockLabel} from './data'
import {ContextualInsight} from './ContextualInsight'
import {AnalystConversation,SpecialistDesks} from './AnalystRoom'
import {MetricBoard} from './MetricBoard'
import type {Evidence,Preferences,Role} from './data'
import {useAnalyst} from './useAnalyst'
import '../matchday/matchday.css'
import '../gi/gi.css'
import './analyst.css'

function initialPreferences():Preferences{
  try{const p=readPreferences(localStorage).preferences;return {language:p.language,depth:'analyst',focus_player_id:p.focus_player_id??null}}
  catch{return {language:'en',depth:'analyst',focus_player_id:null}}
}

export default function AnalystMode(){
  const [matchId,setMatchId]=useState<string>(currentMatchId)
  const [match,setMatch]=useState<GIMatch|null>(null),[matchError,setMatchError]=useState(false),[attempt,setAttempt]=useState(0)
  const [preferences,setPreferences]=useState(initialPreferences)
  const [playback,setPlayback]=useState<ReplayPlayback>({cutoff:{period:1,elapsed_ms:0},playing:false})
  const [lens,setLens]=useState<Role|null>(null)
  const detailRef=useRef<HTMLDialogElement>(null),pitchRef=useRef<HTMLElement>(null),detailOpener=useRef<HTMLElement|null>(null)
  const [seekEpoch,setSeekEpoch]=useState(0)
  const [selectedEvidence,setSelectedEvidence]=useState<(Evidence&{requestId:number})|null>(null)
  const onSeek=useCallback((reason:'timeline'|'evidence')=>{if(reason==='timeline')setSelectedEvidence(null);setSeekEpoch(n=>n+1);setPlayback(p=>({...p,playing:false}))},[])
  useEffect(()=>{if(lens){detailRef.current?.showModal?.();detailRef.current?.focus({preventScroll:true})}},[lens])
  const focusPlayer=match?.match_id===matchId&&match.players.some(p=>p.alias_id===preferences.focus_player_id||p.player_id===preferences.focus_player_id)?preferences.focus_player_id:null
  const scopedPreferences={...preferences,focus_player_id:focusPlayer}
  const {rounds=[],config,configFailed,snapshot,analysis,pending,failed,metricsFailed,retryConfig,retrySnapshot,requestDiscussion}=useAnalyst(matchId,playback.cutoff,playback.playing,scopedPreferences,seekEpoch)
  const names=useMemo(()=>new Map(match?.players.map(p=>[p.player_id,alias(p)])),[match])
  const onPlayback=useCallback((value:ReplayPlayback)=>setPlayback(old=>old.playing===value.playing&&old.cutoff.period===value.cutoff.period&&old.cutoff.elapsed_ms===value.cutoff.elapsed_ms?old:value),[])
  useEffect(()=>{let active=true;const controller=new AbortController();setMatch(null);setMatchError(false)
    fetch(`/api/gi/matches/${encodeURIComponent(matchId)}`,{signal:controller.signal}).then(r=>{if(!r.ok)throw Error();return r.json()}).then(value=>{if(active){if(value.match_id!==matchId||!Array.isArray(value.events)||!value.events.length)throw Error();setMatch(value)}}).catch(e=>{if(active&&e.name!=='AbortError')setMatchError(true)})
    return()=>{active=false;controller.abort()}
  },[matchId,attempt])
  function closeDetails(){detailRef.current?.close();setLens(null);detailOpener.current?.focus({preventScroll:true})}
  function chooseMatch(value:string){setSelectedEvidence(null);setPlayback({cutoff:{period:1,elapsed_ms:0},playing:false});setMatchId(value);setPreferences(p=>({...p,focus_player_id:null}));const url=new URL(location.href);url.searchParams.set('match',value);history.replaceState(null,'',url)}
  const conversation=<AnalystConversation rounds={rounds} pending={pending} failed={failed} available={!!config?.discussion_available} playing={playback.playing} ready={playback.cutoff.elapsed_ms>=60000} analysis={analysis} live={config?.discussion_style==='live'} refresh={requestDiscussion} onEvidence={e=>{setSelectedEvidence({...e,requestId:(selectedEvidence?.requestId??0)+1});pitchRef.current?.focus({preventScroll:true});pitchRef.current?.scrollIntoView({block:'start',behavior:'smooth'})}}/>
  const headerContext=<div className="an-header-context"><h1>Analyst Mode</h1><label className="an-match-picker"><span className="an-sr-only">Choose a match</span><select aria-label="Choose a match" value={matchId} onChange={e=>chooseMatch(e.target.value)}>{matchLibrary.map(m=><option value={m.id} key={m.id}>Eastbridge × Northport · {matchDate(m.date)}</option>)}</select></label><label className="an-language"><span className="an-sr-only">Language</span><select aria-label="Analysis language" value={preferences.language} onChange={e=>setPreferences(p=>({...p,language:e.target.value as Preferences['language']}))}><option value="en">English</option><option value="zh-Hans">简体中文</option></select></label></div>
  return <div className="analyst-mode matchday"><a className="fan-skip" href="#analyst-main">Skip to Analyst Mode</a><AppHeader active="gi" hideContext brandContext={headerContext}/>
    <main id="analyst-main" className="an-main" tabIndex={-1}>
      <SpecialistDesks snapshot={snapshot} rounds={rounds} focusPlayerId={focusPlayer} setFocus={value=>setPreferences(p=>({...p,focus_player_id:value}))} open={role=>{detailOpener.current=document.activeElement as HTMLElement;setLens(role)}} conversation={<>{conversation}<ContextualInsight snapshot={snapshot} rounds={rounds} focusPlayerId={focusPlayer}/></>} pitch={<section ref={pitchRef} tabIndex={-1} className="an-watch-layout" aria-label="Full match and analysis"><div className="an-pitch-panel">
        {matchError?<div className="an-replay-error" role="alert"><h2>The match couldn’t load.</h2><button onClick={()=>setAttempt(n=>n+1)}>Try again</button></div>:match?<PlaySequence key={matchId} matchId={matchId} events={match.events} event={match.events[0]} names={names} players={match.players} fullMatch analystPlayback hideObservation focusPlayerId={focusPlayer} onPlaybackChange={onPlayback} onSeek={onSeek} seekTo={selectedEvidence?{eventId:selectedEvidence.event_id,revision:selectedEvidence.revision,requestId:selectedEvidence.requestId}:undefined}/>:<div className="an-replay-loading"><FootieLoader dark label={preferences.language==='zh-Hans'?'正在打开比赛…':'Opening the match…'} language={preferences.language}/></div>}
      </div></section>}/>

      {selectedEvidence&&<p className="an-evidence-location" role="status">Selected evidence: {selectedEvidence.kind} at {clockLabel(selectedEvidence)}.</p>}
      {configFailed&&<div className="an-notice" role="status">Live analysis availability couldn’t be checked. Statistics are still available. <button onClick={retryConfig}>Check again</button></div>}

      {metricsFailed?<div className="an-notice" role="status">The statistics couldn’t refresh. <button onClick={retrySnapshot}>Try again</button></div>:null}
      {lens&&<dialog ref={detailRef} tabIndex={-1} className="an-expanded-stats" aria-label="Explore the evidence" onCancel={e=>{e.preventDefault();closeDetails()}}><div className="an-detail-top"><h2>Explore the evidence</h2><button onClick={closeDetails}>Close details ×</button></div><MetricBoard key={matchId} snapshot={snapshot} lens={lens} focusPlayerId={focusPlayer}/></dialog>}
      <footer className="an-footer"><span>{snapshot?`Statistics through ${clockLabel(snapshot.cutoff)}`:'Statistics update with completed play'}</span><a href={`?match=${encodeURIComponent(matchId)}#gi`}>Open Match Centre ↗</a></footer>
      {match?.source&&<details className="an-sources"><summary>Data sources</summary><p>{match.source.provider} · {match.source_label}. {match.source.changes} <a href={match.source.license_url} target="_blank" rel="noreferrer">{match.source.license}</a></p></details>}
    </main>
  </div>
}
