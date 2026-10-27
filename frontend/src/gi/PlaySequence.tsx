import {ClubCrest} from '../matchday/ClubCrest'
import {PitchInk} from '../highlights/PitchInk'
import type {Stroke} from '../highlights/collection'
import {usePlayerPeek} from '../football/PlayerPeek'
import {useReplaySpeed} from '../football/useReplaySpeed'
import { useEffect, useMemo, useRef, useState } from 'react'
import { outcomeText,matchClock } from './data'
import type { GIEvent,GIPlayer } from './data'
import { playTimeline,replayFrame,sceneRoster,sequenceEvents,positionedActions } from './replay'
import {PitchIdentity,PitchFaceToggle,usePitchFaces} from '../football/PitchIdentity'
import {discipline} from './discipline'
import {AskFootie} from '../assistant/AskFootie'
import {momentContext} from '../assistant/context'
import {LiveObservation,completedObservationCutoff} from './LiveObservation'
export type ReplayPlayback = {cutoff:{period:1|2;elapsed_ms:number};playing:boolean}
export function PlaySequence({events,event,names,players,matchId,fullMatch=false,autoAdvance=false,onAutoAdvanceChange,onComplete,visible=true,sequenceFloor=0,onPlaybackChange,hideObservation=false,analystPlayback=false,seekTo,onSeek,annotations,focusPlayerId}:{events:GIEvent[];event:GIEvent;names:Map<string,string>;players:GIPlayer[];matchId?:string;fullMatch?:boolean;autoAdvance?:boolean;onAutoAdvanceChange?:(value:boolean)=>void;onComplete?:()=>void;visible?:boolean;sequenceFloor?:number;onPlaybackChange?:(value:ReplayPlayback)=>void;hideObservation?:boolean;analystPlayback?:boolean;seekTo?:{eventId:string;revision:number;requestId:number};onSeek?:(reason:'timeline'|'evidence')=>void;annotations?:{strokes:Stroke[];change:(strokes:Stroke[])=>void};focusPlayerId?:string|null}) {
  const sequence=useMemo(()=>sequenceEvents(events,event).filter(e=>events.findIndex(x=>x.event_id===e.event_id)>=sequenceFloor),[events,event,sequenceFloor])
  const actions=useMemo(()=>positionedActions(fullMatch?events:sequence,fullMatch?4418:event.team_id),[events,event,fullMatch,sequence])

  const timeline=useMemo(()=>playTimeline(actions,players,fullMatch?4418:event.team_id),[actions,players,fullMatch,event.team_id])
  const duration=timeline.duration
  const [progress,setProgress]=useState(0),[playing,setPlaying]=useState(()=>!fullMatch&&!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)
  const [savedSpeed,setSavedSpeed]=useReplaySpeed(),[fastSpeed,setFastSpeed]=useState(1),[faces,setFaces]=usePitchFaces()
  const speed=analystPlayback?fastSpeed:savedSpeed,setSpeed=analystPlayback?setFastSpeed:setSavedSpeed
  const [drawing,setDrawing]=useState(false)
  const peek=usePlayerPeek(undefined,visible&&!drawing)
  const [portrait,setPortrait]=useState(false)
  useEffect(()=>{const q=window.matchMedia?.('(max-width: 640px)');if(!q)return;const update=()=>setPortrait(q.matches);update();q.addEventListener('change',update);return()=>q.removeEventListener('change',update)},[])
  const complete=useRef(onComplete);complete.current=onComplete
  useEffect(()=>{if(!visible)setPlaying(false)},[visible])
  useEffect(()=>{
    if(!playing||!visible)return
    let previous=performance.now(),frame:number
    const tick=(now:number)=>{const delta=now-previous;previous=now
      if(!document.hidden)setProgress(p=>Math.min(1,p+Math.min(delta,100)*speed/duration))
      frame=requestAnimationFrame(tick)
    }
    frame=requestAnimationFrame(tick);const hidden=()=>{if(document.hidden)setPlaying(false)};document.addEventListener('visibilitychange',hidden);return()=>{cancelAnimationFrame(frame);document.removeEventListener('visibilitychange',hidden)}
  },[playing,duration,speed,visible])
  useEffect(()=>{if(progress>=1&&playing){setPlaying(false);if(autoAdvance&&!fullMatch)complete.current?.()}},[progress,playing,autoAdvance,fullMatch])
  const seekCallback=useRef(onSeek);seekCallback.current=onSeek
  useEffect(()=>{
    if(!seekTo)return
    const action=timeline.actions.find(a=>a.event.event_id===seekTo.eventId&&a.event.revision===seekTo.revision)
    if(!action)return
    setPlaying(false)
    setProgress(Math.min(1,(action.at+action.duration*action.resolved+.01)/duration))
    seekCallback.current?.('evidence')
  },[seekTo?.requestId,seekTo?.eventId,seekTo?.revision,timeline,duration])
  const clock=progress*duration
  const observationCutoff=completedObservationCutoff(timeline.actions,clock)
  const activeAction=timeline.actions.filter(a=>a.at<=clock).at(-1)
  const playbackCallback=useRef(onPlaybackChange);playbackCallback.current=onPlaybackChange
  const completedPeriod=observationCutoff?.period??activeAction?.event.period??1
  const completedMs=observationCutoff?.elapsed_ms??0
  useEffect(()=>{playbackCallback.current?.({cutoff:{period:completedPeriod,elapsed_ms:completedMs},playing:playing&&visible})},[completedPeriod,completedMs,playing,visible])
  const phaseAt=activeAction?Math.min(1,(clock-activeAction.at)/activeAction.duration):0
  const cutoff=activeAction?{period:activeAction.event.period,elapsed_ms:activeAction.event.elapsed_ms+(phaseAt>=activeAction.resolved?0:-1)}:undefined
  const cards=discipline(events,cutoff)
  const dismissed=new Set(cards.players.filter(p=>p.sentOff).map(p=>p.player_id))
  const roster=sceneRoster(players,events,activeAction?.event??event).filter(p=>!dismissed.has(p.player_id))
  const {active,ball,ballHeight,opacity,transition,phase,players:scene}=replayFrame(timeline,clock,roster,fullMatch?4418:event.team_id)
  const score=[4418,9598].map(team=>timeline.actions.filter(a=>a.event.goal_for===team&&a.at+a.duration*a.resolved<=clock).length)
  const replayFooter=<div className="gi-replay-footer"><p className="gi-replay-caption" aria-live="off">{transition?'Play resumes':active?`${names.get(active.event.player_id)} · ${outcomeText(active.event)}`:'Following the play'}{progress>=1?' · Full sequence':''}</p>
    {matchId&&active&&<AskFootie variant="pitch" context={momentContext(matchId,{event_id:active.event.event_id,revision:active.event.revision,occurred_at:{period:active.event.period,elapsed_ms:active.event.elapsed_ms},available_at:{period:active.event.available_period??active.event.period,elapsed_ms:active.event.available_ms??active.event.elapsed_ms}},phase>=active.resolved,`${names.get(active.event.player_id)??'Player'} · ${outcomeText(active.event)}`)} onOpen={()=>setPlaying(false)}/>}</div>
  return <div className="gi-replay">
    {fullMatch&&!analystPlayback&&<div className="gi-replay-prelude"><span className="gi-watch-score">Eastbridge <strong>{score[0]} – {score[1]}</strong> Northport · {active?matchClock(active.event):'0:00'}</span><p className="gi-watch-note">Continuous replay · breaks between actions skipped</p></div>}
    {annotations&&<div className="hl-ink-tools" role="group" aria-label="Pitch annotations"><button aria-pressed={drawing} onClick={()=>{setDrawing(!drawing);setPlaying(false)}}>✎ {drawing?'Finish drawing':'Red pen'}</button><button disabled={!annotations.strokes.length} onClick={()=>annotations.change(annotations.strokes.slice(0,-1))}>Undo last stroke</button><button disabled={!annotations.strokes.length} onClick={()=>annotations.change([])}>Clear</button>{annotations.strokes.length>0&&<label>Saved frame<select aria-label="Annotated frame" value={annotations.strokes.some(s=>Math.abs(s.at-progress)<.002)?String(annotations.strokes.find(s=>Math.abs(s.at-progress)<.002)!.at):''} onChange={e=>{if(e.target.value){setPlaying(false);setProgress(Number(e.target.value))}}}><option value="">Choose a frame</option>{[...new Set(annotations.strokes.map(s=>s.at))].map(at=><option key={at} value={at}>{(at*duration/1000).toFixed(1)}s</option>)}</select></label>}<small>{drawing?(annotations.strokes.length>=30?'30-stroke limit reached. Undo a stroke to continue.':'Draw on the paused pitch. Notes stay with this frame.'):'Pause anywhere to mark a run, pass or position.'}</small></div>}
    <div className={analystPlayback?"an-score-stage":undefined}>
    {analystPlayback&&<div className="an-score-club an-score-home"><ClubCrest club="eastbridge"/><span>Eastbridge</span><strong aria-label={`Eastbridge ${score[0]} goals`}>{score[0]}</strong></div>}
    <svg className="gi-pitch" viewBox={portrait?"-5 -5 78 115":"-5 -5 115 78"} role="img" aria-label={fullMatch?"Full match replay, Eastbridge attacking right":"Match replay, selected team attacking right"}>
      <defs><radialGradient id="gi-spotlight"><stop stopColor="#fff" stopOpacity=".2"/><stop offset="1" stopColor="#fff" stopOpacity="0"/></radialGradient></defs>
      <g transform={portrait?"translate(68 0) rotate(90)":undefined}>
      <rect x="-5" y="-5" width="115" height="78" rx="3" fill="#153e35"/>
      {Array.from({length:7},(_,i)=><rect key={i} x={i*15} width="15" height="68" fill={i%2?'#ffffff08':'transparent'}/>)}
      <g fill="none" stroke="#ffffff65" strokeWidth=".35"><rect width="105" height="68"/><path d="M52.5 0V68M0 13.84H16.5V54.16H0M105 13.84H88.5V54.16H105M0 24.84H5.5V43.16H0M105 24.84H99.5V43.16H105M-2 30.34H0M-2 30.34V37.66H0M105 30.34H107V37.66H105"/><circle cx="52.5" cy="34" r="9.15"/></g>
      <text x="52" y="-1.5" textAnchor="middle" fill="#fff" fontSize="2">{fullMatch?'EASTBRIDGE →   ·   ← NORTHPORT':'ATTACKING DIRECTION →'}</text>
      <g opacity={opacity} pointerEvents={opacity<.5?'none':undefined} data-replay-scene="true" data-evidence-event={active?.event.event_id===seekTo?.eventId?seekTo?.eventId:undefined}>
      <circle cx={ball.x} cy={ball.y} r="15" fill="url(#gi-spotlight)"/>
      {[...scene].sort((a,b)=>Number(a.highlighted)-Number(b.highlighted)).map(p=>{
        const pos=p,highlighted=p.highlighted,color=p.team_id===4418?'#e7c771':'#a9d5f7'
        return <g key={p.player_id} {...peek.bind(p.alias_id,names.get(p.player_id)??p.alias_id)} tabIndex={0} role="group" aria-label={names.get(p.player_id)??p.alias_id} className="gi-replay-player" data-active={highlighted} data-followed={p.alias_id===focusPlayerId||p.player_id===focusPlayerId}>
          {(p.alias_id===focusPlayerId||p.player_id===focusPlayerId)&&<g className="gi-followed-player"><circle cx={pos.x} cy={pos.y} r="5.4" fill="none" stroke="#fffdf0" strokeWidth=".7"/><text transform={portrait?`rotate(-90 ${pos.x} ${pos.y})`:undefined} x={pos.x} y={pos.y+7.8} textAnchor="middle" fill="#fffdf0" stroke="#153e35" strokeWidth=".65" paintOrder="stroke" fontSize="2.4">{names.get(p.player_id)??p.alias_id}</text></g>}
          {highlighted&&<><circle cx={pos.x} cy={pos.y} r="4.3" fill="none" stroke={color} strokeWidth=".45" strokeDasharray="1.5 .8"/><path d={`M${pos.x-1} ${pos.y-6}L${pos.x} ${pos.y-4.8}L${pos.x+1} ${pos.y-6}`} fill={color}/></>}
          <circle cx={pos.x} cy={pos.y+.45} r="2.4" fill="#0005"/>
          <g transform={`translate(${pos.x} ${pos.y})`}><g transform={portrait?"rotate(-90)":undefined}><PitchIdentity playerId={p.alias_id} name={names.get(p.player_id)??p.alias_id} color={color} r={faces?highlighted?3.5:3:highlighted?2.7:2.2} faces={faces}/>{cards.players.some(c=>c.player_id===p.player_id&&c.yellows>0)&&<rect x="2" y="-3.5" width="1.3" height="1.9" rx=".2" fill="#f3cf4a" stroke="#173d32" strokeWidth=".2"/>}</g></g>
          <circle cx={pos.x} cy={pos.y} r={faces?3.5:2.7} fill="transparent" pointerEvents="all"/>
        </g>
      })}
      {ballHeight>.2&&<ellipse cx={ball.x} cy={ball.y} rx="1.3" ry=".55" fill="#0005"/>}
      <circle data-replay-ball="true" cx={ball.x} cy={ball.y-ballHeight*.65} r={1.05+ballHeight*.09} fill="white" stroke="#102d27" strokeWidth=".35"/>
      </g>
      {annotations&&<PitchInk strokes={annotations.strokes} at={progress} enabled={drawing} playing={playing} onStroke={stroke=>annotations.change([...annotations.strokes,stroke])}/>}
      </g>
    </svg>
    {analystPlayback&&<div className="an-score-club an-score-away"><ClubCrest club="northport"/><span>Northport</span><strong aria-label={`Northport ${score[1]} goals`}>{score[1]}</strong></div>}
    </div>
    {analystPlayback&&<div className="an-match-clock"><span>{active?.event.period===2?'Second half':'First half'}</span><time aria-label="Match clock">{active?matchClock(active.event):'0:00'}</time></div>}
    <div className="gi-replay-dock"><div className="gi-playback"><button onClick={()=>{setDrawing(false);if(progress>=1){onSeek?.('timeline');setProgress(0);setPlaying(true)}else setPlaying(!playing)}}>{progress>=1?fullMatch?'Replay match':'Replay sequence':playing?'Pause':fullMatch?'Play match':'Resume'}</button><input type="range" aria-label={fullMatch?"Full match progress":"Play sequence progress"} min="0" max="1" step={fullMatch?'any':'.001'} value={progress} onChange={e=>{onSeek?.('timeline');setPlaying(false);setProgress(Number(e.target.value))}}/><span hidden={analystPlayback}>{fullMatch?`${Math.floor(clock/60000)}:${String(Math.floor(clock/1000)%60).padStart(2,'0')} / ${Math.floor(duration/60000)}:${String(Math.ceil(duration/1000)%60).padStart(2,'0')}`:`${Math.floor(clock/1000)} / ${Math.ceil(duration/1000)}s`}</span></div>
    <div className="gi-replay-tools">
      <label className="gi-speed"><span>Speed</span><select aria-label="Sequence playback speed" value={speed} onChange={e=>setSpeed(Number(e.target.value))}>{(analystPlayback?[1,2,5,10]:[.5,1,1.5,2]).map(n=><option key={n} value={n}>{n}×</option>)}</select></label>
      <PitchFaceToggle faces={faces} change={setFaces}/>
      {!fullMatch&&onAutoAdvanceChange&&<label className="gi-auto-toggle"><input aria-label="Auto-play next sequence" type="checkbox" checked={autoAdvance} onChange={e=>onAutoAdvanceChange(e.target.checked)}/><span className="gi-switch-track" aria-hidden="true"/><span>Auto-play</span></label>}
    </div>
    {cards.players.length>0&&<details className="gi-card-disclosure"><summary><span className="gi-card-summary"><i className="card-yellow"/>{cards.players.filter(p=>p.yellows>0).length} booked{dismissed.size>0&&<> · <i className="card-red"/>{dismissed.size} sent off</>}</span><span aria-hidden="true">⌄</span></summary><div className="gi-live-cards" aria-label="Cards at this point in the match">{cards.players.map(p=><span key={p.player_id}><i className={p.sentOff?'card-red':'card-yellow'}/>{names.get(p.player_id)} · {p.sentOff?'Sent off':'On a yellow'}</span>)}</div></details>}
    {hideObservation?replayFooter:<LiveObservation matchId={matchId} cutoff={observationCutoff} visible={visible} onOpen={()=>setPlaying(false)}>{replayFooter}</LiveObservation>}</div>
    {peek.card}
  </div>
}
