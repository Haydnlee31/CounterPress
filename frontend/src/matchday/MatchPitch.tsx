import { useEffect, useId, useState } from 'react'
import type { Event } from '../types'
import { clock } from '../types'
import { clubName, initials, playerName } from './identity'
import { actionText, pitchScene } from './pitchScene'

export function MatchPitch({events,language='en',compact=false}:{events:Event[];language?:string;compact?:boolean}) {
  const zh=language==='zh-Hans', t=(en:string,cn:string)=>zh?cn:en
  const [index,setIndex]=useState(0), [progress,setProgress]=useState(0), [playing,setPlaying]=useState(false)
  const [selected,setSelected]=useState<string|null>(null), [reduced,setReduced]=useState(false)
  const id=useId().replaceAll(':','')
  const [portrait,setPortrait]=useState(false)
  useEffect(()=>{
    const query=window.matchMedia?.('(max-width: 640px)')
    if(!query)return
    const update=()=>setPortrait(query.matches); update();query.addEventListener('change',update)
    return()=>query.removeEventListener('change',update)
  },[])
  const signature=events.map(e=>`${e.event_id}:${e.revision}`).join('|')
  useEffect(()=>{setIndex(0);setProgress(0);setPlaying(false);setSelected(null)},[signature])
  useEffect(()=>{
    const query=window.matchMedia?.('(prefers-reduced-motion: reduce)')
    if (!query) return
    const update=()=>{setReduced(query.matches); if(query.matches) setPlaying(false)}
    update();query.addEventListener('change',update);return()=>query.removeEventListener('change',update)
  },[])
  useEffect(()=>{
    if(!playing || reduced || !events.length) return
    let frame:number,previous=performance.now(),value=progress
    const step=(now:number)=>{
      value+=Math.min(now-previous,100)/3200;previous=now
      if(value>=1){value=0;setIndex(i=>(i+1)%events.length)}
      setProgress(value);frame=requestAnimationFrame(step)
    }
    frame=requestAnimationFrame(step);return()=>cancelAnimationFrame(frame)
  },[playing,reduced,signature]) // Progress is owned by the animation until paused.
  const event=events[Math.min(index,Math.max(0,events.length-1))]
  const scene=pitchScene(event,progress)
  const select=(next:number)=>{setPlaying(false);setIndex(next);setProgress(0);setSelected(null)}
  return <section className={`fan-pitch ${compact?'is-compact':''}`} aria-label={t('Match pitch','比赛球场')}>
    <div className="fan-pitch-heading"><div><p className="fan-kicker">{t('ON THE PITCH','球场上')}</p><h2>{t('Watch the play','观看回放')}</h2></div>
      <span className="fan-pitch-time">{event ? clock(event.occurred_at.elapsed_ms,event.occurred_at.period) : '—'}</span></div>
    <div className="fan-pitch-canvas">
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
        {event && <path d={`M${scene.start.x} ${scene.start.y} L${scene.end.x} ${scene.end.y}`} stroke="#f5dc90" strokeWidth=".5" strokeDasharray="1.3 1.3" opacity=".7"/>}
        {scene.players.map(p=><g key={p.player_id} className={`fan-pitch-player ${p.involved?'involved':''} ${p.player_id===selected?'selected':''}`}
          role="button" tabIndex={0} aria-label={`${playerName(p.player_id)}, ${clubName(p.team_id)}`} aria-pressed={selected===p.player_id}
          transform={`translate(${p.x} ${p.y})`} onClick={()=>setSelected(p.player_id)}
          onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();setSelected(p.player_id)}}}>
          <g transform={portrait?"rotate(-90)":undefined}>
          <title>{playerName(p.player_id)} · {clubName(p.team_id)}</title>
          <circle className="player-hit" r={portrait?5.2:4} fill="transparent"/>
          <ellipse cy="2.4" rx="2.8" ry="1" fill="#071c16" opacity=".32"/>
          <circle className="player-halo" r="3.5" fill="none" stroke="#f5d77f" strokeWidth=".5" opacity={p.involved||p.player_id===selected?1:0}/>
          <circle r="2.7" fill={p.team_id==='eastbridge'?'#f2d483':'#d0e6fb'} stroke={p.team_id==='eastbridge'?'#183c2e':'#193f70'} strokeWidth=".65"/>
          <text y=".8" textAnchor="middle" fill={p.team_id==='eastbridge'?'#16382c':'#183d64'} fontSize="2.4" fontWeight="800" pointerEvents="none">{initials(p.player_id)}</text>
          {p.player_id===event?.actor.player_id && <path d={scene.kicking?'M1 2l3 1.4':'M1 2l.8 1'} stroke="#fff4cb" strokeWidth=".9" strokeLinecap="round"/>}
          <g className="player-tooltip" pointerEvents="none"><rect x="-11" y="-8" width="22" height="3.8" rx="1" fill="#0c251f"/><text y="-5.4" textAnchor="middle" fontSize="1.8" fill="white">{playerName(p.player_id)}</text></g>
          </g>
        </g>)}
        <g className="fan-ball" transform={`translate(${scene.ball.x+1.2} ${scene.ball.y+1.2})`} pointerEvents="none">
          <circle cy=".7" r="1.15" fill="#051d16" opacity=".45"/><circle r="1.05" fill="#fffdf0" stroke="#172d25" strokeWidth=".25"/><path d="m0-.5.5.4-.2.6h-.6l-.2-.6Z" fill="#21362d"/>
        </g>
        </g>
      </svg>
    </div>
    <div className="fan-pitch-caption" aria-live={playing?'off':'polite'}><span className="fan-play-dot"/>
      <p>{selected ? `${playerName(selected)} · ${clubName(selected.startsWith('eb')?'eastbridge':'northport')}` : event ? actionText(event,zh) : t('Waiting for the next play','等待下一次进攻')}</p>
      {selected && <button onClick={()=>setSelected(null)}>{t('Back to play','返回回放')}</button>}</div>
    <div className="fan-pitch-controls">
      <button className="fan-primary" disabled={!events.length} onClick={()=>{if(reduced){setProgress(p=>p===0?1:0)}else setPlaying(v=>!v)}}>{reduced?t('Show ball movement','查看传球落点'):playing?t('Pause play','暂停'):t('Play sequence','播放片段')} <span aria-hidden="true">{playing?'Ⅱ':'▶'}</span></button>
      <button className="fan-secondary" disabled={!events.length} onClick={()=>select((index-1+events.length)%events.length)} aria-label={t('Previous play','上一次进攻')}>←</button>
      <button className="fan-secondary" disabled={!events.length} onClick={()=>select((index+1)%events.length)} aria-label={t('Next play','下一次进攻')}>→</button>
      <span>{events.length ? `${index+1} / ${events.length}` : '—'}</span><small>{t('Select a player to see their name','选择球员查看姓名')}</small>
    </div>
  </section>
}
