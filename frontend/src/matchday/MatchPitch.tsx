import { useEffect, useId, useState } from 'react'
import type { Event } from '../types'
import { replayClock } from '../matchday/replayGallery'
import { clubName, initials, playerName } from './identity'
import { playDuration, actionLabel, sequenceScene, pitchZone, recipient, fieldPoint } from './pitchScene'
import { LiveCompanion } from '../companion/LiveCompanion'
import { cue } from '../companion/evidence'
import {useHighlightTrack} from '../companion/useHighlightTrack'
import {TrackPlayer,trackPosition,trackTime} from '../companion/highlightTrack'
import { ClubCrest } from './ClubCrest'
import {AskFootie} from '../assistant/AskFootie'
import {matchdayContext} from '../assistant/context'

export function MatchPitch({events,language='en',compact=false,fromStart=false,onPlayhead,seekTo,onPlayerSelect,selectedPlayer,routes=[],companion=false,playback,assistantMatchId,onAssistantOpen}:{events:Event[];language?:string;compact?:boolean;fromStart?:boolean;onPlayhead?:(value:{index:number;resolved:boolean})=>void;seekTo?:{index:number;version:number};onPlayerSelect?:(id:string|null)=>void;selectedPlayer?:string|null;routes?:Event[];companion?:boolean;assistantMatchId?:string;onAssistantOpen?:()=>void;playback?:{index:number;progress:number;playing:boolean}}) {
  const zh=language==='zh-Hans', t=(en:string,cn:string)=>zh?cn:en
  const [localIndex,setIndex]=useState(fromStart?0:Math.max(0,events.length-1)), [localProgress,setProgress]=useState(0), [localPlaying,setPlaying]=useState(false)
  const index=playback?.index??localIndex, progress=playback?.progress??localProgress, playing=playback?.playing??localPlaying
  const [localSelected,setSelected]=useState<string|null>(null), [reduced,setReduced]=useState(false)
  const selected=selectedPlayer===undefined?localSelected:selectedPlayer
  const id=useId().replaceAll(':','')
  const [portrait,setPortrait]=useState(false)
  const [speed,setSpeed]=useState(1)
  const [speechEpoch,setSpeechEpoch]=useState(0)
  const voice=useHighlightTrack(events,language,fromStart,companion&&!playback,()=>{
    setPlaying(false);setIndex(0);setProgress(0);setSpeechEpoch(v=>v+1)
  })
  useEffect(()=>{
    const hidden=()=>{if(document.hidden)setPlaying(false)}
    document.addEventListener('visibilitychange',hidden)
    return()=>document.removeEventListener('visibilitychange',hidden)
  },[])
  useEffect(()=>{
    if (!seekTo || !events.length) return
    setSpeechEpoch(v=>v+1)
    setIndex(Math.max(0,Math.min(events.length-1,seekTo.index)))
    setProgress(0);setPlaying(false);setSelected(null)
  },[seekTo])
  const selectPlayer=(player:string)=>{setSelected(player);if(onPlayerSelect){setPlaying(false);onPlayerSelect(player)}}
  useEffect(()=>{
    const query=window.matchMedia?.('(max-width: 640px)')
    if(!query)return
    const update=()=>setPortrait(query.matches); update();query.addEventListener('change',update)
    return()=>query.removeEventListener('change',update)
  },[])
  const signature=events.map(e=>`${e.match_id}:${e.event_id}:${e.revision}`).join('|')
  useEffect(()=>{setIndex(fromStart?0:Math.max(0,events.length-1));setProgress(0);setPlaying(false);setSelected(null)},[signature,fromStart])
  useEffect(()=>{
    const query=window.matchMedia?.('(prefers-reduced-motion: reduce)')
    if (!query) return
    const update=()=>{setReduced(query.matches); if(query.matches) setPlaying(false)}
    update();query.addEventListener('change',update);return()=>query.removeEventListener('change',update)
  },[])
  useEffect(()=>{
    if(playback || !playing || (reduced&&!voice.track) || !events.length) return
    if(voice.preparing)return
    if(voice.track && voice.context.current){
      const track=voice.track
      const offset=trackTime(track,index,progress)
      const player=new TrackPlayer(track,offset,speed)
      let frame:number,stopped=false
      const externalPause=()=>{if(!stopped&&!track.audio.ended)setPlaying(false)}
      track.audio.addEventListener('pause',externalPause)
      const step=()=>{
        const at=player.position(),position=trackPosition(track,at)
        setIndex(position.index);setProgress(position.progress)
        if(player.ended()){setIndex(events.length-1);setProgress(1);setPlaying(false);return}
        frame=requestAnimationFrame(step)
      }
      void player.start().then(()=>{if(!stopped)frame=requestAnimationFrame(step);else player.stop()}).catch(()=>setPlaying(false))
      return()=>{stopped=true;track.audio.removeEventListener('pause',externalPause);cancelAnimationFrame(frame);player.stop()}
    }
    let frame:number,previous=performance.now(),value=progress,current=index
    const step=(now:number)=>{
      const duration=fromStart ? playDuration(events[current],events[current+1]) : 3200
      value+=Math.min(now-previous,100)*speed/duration;previous=now
      if(value>=1){
        if(current>=events.length-1){setProgress(1);setPlaying(false);return}
        value=0;current++;setIndex(current);setSelected(null)
      }
      setProgress(value);frame=requestAnimationFrame(step)
    }
    frame=requestAnimationFrame(step);return()=>cancelAnimationFrame(frame)
  },[playing,reduced,signature,speed,voice.track,voice.preparing]) // Progress is owned by the animation until paused.
  const event=events[Math.min(index,Math.max(0,events.length-1))]
  const resolved=progress >= (event?.action.kind === 'shot' ? .6 : .8)
  useEffect(()=>{onPlayhead?.({index,resolved})},[index,resolved,onPlayhead,signature])
  const scene=sequenceScene(events,index,reduced && (playback||voice.track)?(resolved?1:0):progress,fromStart)
  const goal=event?.action.kind==='shot'&&event.action.outcome==='goal'&&resolved
  const history=events.slice(Math.max(0,index-4),index+1).map((record,i)=>({record,index:Math.max(0,index-4)+i})).reverse()
  const target=recipient(event)
  const narration=(record:Event,at:number)=>cue(record,at!==index || resolved,zh)
  const startPlayback=()=>{
    void voice.resume()?.catch(()=>setPlaying(false))
    if(reduced&&!voice.track){setProgress(p=>p===0?1:0);return}
    if(!playing && (index===events.length-1 && (progress>=1 || (!fromStart && progress===0)))){setSpeechEpoch(v=>v+1);setIndex(0);setProgress(0);setSelected(null)}
    setPlaying(v=>!v)
  }
  const select=(next:number)=>{setSpeechEpoch(v=>v+1);setPlaying(false);setIndex(next);setProgress(0);setSelected(null)}
  return <section className={`fan-pitch ${compact?'is-compact':''}`} aria-label={t('Match pitch','比赛球场')}>
    <div className="fan-pitch-heading"><div><p className="fan-kicker">{t('ON THE PITCH','球场上')}</p><h2>{playback?t('On the pitch','球场上'):t('Watch the play','观看回放')}</h2></div>
      <div className="fan-tracker-clock"><span>{t(playing?'Playing':'Replay',playing?'播放中':'回放')}</span><span className="fan-pitch-time">{event ? replayClock(event) : '—'}</span></div></div>
    {!playback && <div className="fan-pitch-controls">
      <button className="fan-primary" disabled={!events.length || voice.preparing} onClick={startPlayback}>{voice.preparing?t('Preparing commentary…','准备解说…'):reduced&&!voice.track?t('Show ball movement','查看传球落点'):playing?t('Pause play','暂停'):fromStart?t('Play highlight','播放集锦'):t('Play sequence','播放片段')} <span aria-hidden="true">{playing?'Ⅱ':'▶'}</span></button>
      <button className="fan-secondary" disabled={!events.length || index===0} onClick={()=>select(index-1)} aria-label={t('Previous play','上一次进攻')}>←</button>
      <button className="fan-secondary" disabled={!events.length || index===events.length-1} onClick={()=>select(index+1)} aria-label={t('Next play','下一次进攻')}>→</button>
      <span>{events.length ? `${index+1} / ${events.length}` : '—'}</span>
      <button className="fan-secondary" onClick={()=>select(0)} disabled={!events.length}>{t('Restart','重新开始')} ↺</button>
      <label className="fan-speed">{t('Speed','速度')} <select aria-label={t('Pitch replay speed','球场回放速度')} value={speed} onChange={e=>setSpeed(Number(e.target.value))}><option value="0.5">0.5×</option><option value="1">1×</option><option value="1.5">1.5×</option></select></label>
      <label className="fan-pitch-scrubber"><span className="sr-only">{t('Replay position','回放位置')}</span><input type="range" aria-label={t('Replay position','回放位置')} min="0" max={Math.max(1,events.length*100)} step="1" value={index*100+progress*100} disabled={!events.length} aria-valuetext={t(`Play ${index+1} of ${events.length}`,`第${index+1}次，共${events.length}次`)} onChange={e=>{const value=Number(e.target.value)/100;setSpeechEpoch(v=>v+1);setPlaying(false);setIndex(Math.min(events.length-1,Math.floor(value)));setProgress(value>=events.length?1:value%1);setSelected(null)}}/></label>
    </div>}
    {assistantMatchId&&event&&<AskFootie context={matchdayContext(assistantMatchId,event,resolved,`Eastbridge × Northport · ${replayClock(event)}`)} onOpen={()=>{setPlaying(false);onAssistantOpen?.()}}/>}
    <div className="fan-tracker-grid">
      {!compact && <aside className="fan-play-board" aria-label={t('Current play','当前进攻')}>
        <p className="fan-kicker">{t('IN THE ACTION','焦点球员')}</p>
        {event && <><ClubCrest club={event.actor.team_id}/><span className="fan-board-club">{clubName(event.actor.team_id)}</span>
          <strong className="fan-board-name">{playerName(event.actor.player_id)}</strong>
          <span className="fan-board-action">{actionLabel(event,zh)}</span>
          <div className="fan-board-location"><span>{t('Where','位置')}</span><strong>{pitchZone(event,zh)}</strong></div>
          {target && <div className="fan-board-recipient"><span>{t('To','传向')}</span><strong>{playerName(target)}</strong></div>}
          <div className="fan-board-key"><span className="fan-team-dot eastbridge"/> Eastbridge<br/><span className="fan-team-dot northport"/> Northport</div>
        </>}
      </aside>}
      <div className={`fan-pitch-canvas ${goal?'has-goal':''}`}>
      {goal && <div className="fan-goal-banner" role="status">{t('GOAL!','进球！')} <span>{playerName(event.actor.player_id)}</span></div>}
      <svg viewBox={portrait?"-7 -5 82 115":"-5 -7 115 82"} aria-label={t('Interactive football pitch','互动足球场')} role="group">
        <defs><pattern id={`${id}-grass`} width="21" height="68" patternUnits="userSpaceOnUse"><rect width="21" height="68" fill="#285e4a"/><rect width="10.5" height="68" fill="#2d6851"/></pattern></defs>
        <g transform={portrait?"translate(68 0) rotate(90)":undefined}>
        <rect x="-5" y="-7" width="115" height="82" rx="3" fill="#173d32"/>
        <rect width="105" height="68" fill={`url(#${id}-grass)`}/>
        <g fill="none" stroke="#d9ead4" strokeOpacity=".55" strokeWidth=".35">
          <rect width="105" height="68"/><path d="M52.5 0v68 M0 13.84h16.5v40.32H0 M105 13.84H88.5v40.32H105 M0 24.84h5.5v18.32H0 M105 24.84h-5.5v18.32H105 M-2 30.34H0v7.32h-2Z M105 30.34h2v7.32h-2Z"/>
          <circle cx="52.5" cy="34" r="9.15"/><circle cx="52.5" cy="34" r=".55" fill="#d9ead4"/>
          <path d="M16.5 26.7a9.15 9.15 0 0 1 0 14.6 M88.5 26.7a9.15 9.15 0 0 0 0 14.6"/>
        </g>
        <text x="3" y="-2.5" fill="#cce3d2" fontSize="1.8" letterSpacing=".5">EASTBRIDGE →</text>
        <text x="102" y="-2.5" textAnchor="end" fill="#cce3d2" fontSize="1.8" letterSpacing=".5">← NORTHPORT</text>
        <g className="explore-routes" pointerEvents="none" aria-hidden="true">{routes.filter(e=>e.action.kind==='pass').map(e=>{
          const end=e.action.end_position as {x:number;y:number}|undefined
          if(!end || !Number.isFinite(end.x) || !Number.isFinite(end.y)) return null
          const a=fieldPoint(e.position,e.actor.team_id), b=fieldPoint(end,e.actor.team_id)
          return <g key={e.event_id}><path d={`M${a.x} ${a.y}L${b.x} ${b.y}`} stroke="#f5dc90" strokeWidth=".65" opacity=".65"/><circle cx={b.x} cy={b.y} r="1" fill="#f5dc90" opacity=".8"/></g>
        })}</g>
        {event && <path d={`M${scene.start.x} ${scene.start.y} L${scene.end.x} ${scene.end.y}`} stroke="#f5dc90" strokeWidth=".5" strokeDasharray="1.3 1.3" opacity=".7"/>}
        {[...scene.players].sort((a,b)=>Number(a.involved||a.player_id===selected)-Number(b.involved||b.player_id===selected)).map(p=>{
          return <g key={p.player_id} className={`fan-pitch-player ${p.involved?'involved':''} ${p.player_id===selected?'selected':''}`}
          data-player-id={p.player_id}
          role="button" tabIndex={0} aria-label={`${playerName(p.player_id)}, ${clubName(p.team_id)}`} aria-pressed={selected===p.player_id}
          transform={`translate(${p.x} ${p.y})`} onClick={()=>selectPlayer(p.player_id)}
          onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();selectPlayer(p.player_id)}}}>
          <g transform={portrait?"rotate(-90)":undefined}>
          <title>{playerName(p.player_id)} · {clubName(p.team_id)}</title>
          <circle className="player-hit" r={portrait?5.2:4} fill="transparent"/>
          <ellipse className="player-shadow" cy="2.4" rx="2.8" ry="1" fill="#071c16" opacity=".32"/>
          <circle className="player-halo" r="3.5" fill="none" stroke="#f5d77f" strokeWidth=".5" opacity={p.involved||p.player_id===selected?1:0}/>
          <circle className="player-disc" r={2.7} fill={p.team_id==='eastbridge'?'#f2d483':'#d0e6fb'} stroke={p.team_id==='eastbridge'?'#183c2e':'#193f70'} strokeWidth=".65"/>
          <text className="player-initials" y=".8" textAnchor="middle" fill={p.team_id==='eastbridge'?'#16382c':'#183d64'} fontSize="2.4" fontWeight="800" pointerEvents="none">{initials(p.player_id)}</text>
          {p.player_id===event?.actor.player_id && <path d={scene.kicking?'M1 2l3 1.4':'M1 2l.8 1'} stroke="#fff4cb" strokeWidth=".9" strokeLinecap="round"/>}
          <g className="player-tooltip" pointerEvents="none"><rect x="-11" y="-8" width="22" height="3.8" rx="1" fill="#0c251f"/><text y="-5.4" textAnchor="middle" fontSize="1.8" fill="white">{playerName(p.player_id)}</text></g>
          </g>
        </g>})}
        <g className="fan-ball" transform={`translate(${scene.ball.x} ${scene.ball.y})`} pointerEvents="none">
          <circle cy=".7" r="1.15" fill="#051d16" opacity=".45"/><circle r="1.05" fill="#fffdf0" stroke="#172d25" strokeWidth=".25"/><path d="m0-.5.5.4-.2.6h-.6l-.2-.6Z" fill="#21362d"/>
        </g>
        </g>
      </svg>
      </div>
      {!compact && <aside className="fan-commentary" aria-label={t('Match commentary','比赛解说')}>
        <div className="fan-commentary-heading"><h3>{t('Match commentary','比赛解说')}</h3><span>{t('Play by play','逐次回放')}</span></div>
        <ol>{history.map(({record,index:at})=><li key={`${record.event_id}:${record.revision}`}>
          <button aria-current={at===index?'step':undefined} disabled={!!playback} onClick={()=>select(at)} aria-label={`${t('Replay','回放')} ${replayClock(record)}: ${narration(record,at)}`}>
            <span className="fan-feed-meta"><time>{replayClock(record)}</time><span>{at===index?t('On the pitch','球场上'):clubName(record.actor.team_id)}</span></span>
            <strong>{narration(record,at)}</strong>
          </button>
        </li>)}</ol>
        <button className="fan-latest-play" disabled={!events.length || index===events.length-1} onClick={()=>select(events.length-1)}>{t('Latest play','最新进攻')} <span aria-hidden="true">↗</span></button>
      </aside>}
    </div>
    <div className="fan-pitch-caption" aria-live={playing?'off':'polite'}><span className="fan-play-dot"/>
      <p>{selected ? `${playerName(selected)} · ${clubName(selected.startsWith('eb')?'eastbridge':'northport')}` : event ? cue(event,resolved,zh) : t('Waiting for the next play','等待下一次进攻')}</p>
      {selected && <button onClick={()=>{setSelected(null);onPlayerSelect?.(null)}}>{t('Back to play','返回回放')}</button>}</div>

    {companion && <LiveCompanion narration={{available:voice.available,listen:voice.listen,status:voice.preparing?'loading':voice.status,progress:voice.progress,toggle:voice.toggle,text:voice.track?.markers.slice().reverse().find(m=>m.position<=index+progress)?.text}} speechEpoch={speechEpoch} events={events} index={index} resolved={resolved} playing={playing || (reduced && resolved)} finished={progress>=1 && index===events.length-1} language={language}/>}
  </section>
}
