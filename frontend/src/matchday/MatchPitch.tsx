import { useEffect, useId, useState } from 'react'
import type { Event } from '../types'
import { clock } from '../types'
import { clubName, initials, playerName } from './identity'
import { actionLabel, actionText, BALL_FOCUS_RADIUS, pitchScene, pitchZone, recipient } from './pitchScene'
import { ClubCrest } from './ClubCrest'

export function MatchPitch({events,language='en',compact=false,fromStart=false,onPlayhead}:{events:Event[];language?:string;compact?:boolean;fromStart?:boolean;onPlayhead?:(value:{index:number;resolved:boolean})=>void}) {
  const zh=language==='zh-Hans', t=(en:string,cn:string)=>zh?cn:en
  const [index,setIndex]=useState(fromStart?0:Math.max(0,events.length-1)), [progress,setProgress]=useState(0), [playing,setPlaying]=useState(false)
  const [selected,setSelected]=useState<string|null>(null), [reduced,setReduced]=useState(false)
  const id=useId().replaceAll(':','')
  const [portrait,setPortrait]=useState(false)
  const [focusBall,setFocusBall]=useState(!compact)
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
    if(!playing || reduced || !events.length) return
    let frame:number,previous=performance.now(),value=progress,current=index
    const step=(now:number)=>{
      const duration=fromStart ? Math.max(1000,Math.min(3200,(events[current+1]?.occurred_at.elapsed_ms ?? events[current].occurred_at.elapsed_ms+2500)-events[current].occurred_at.elapsed_ms)) : 3200
      value+=Math.min(now-previous,100)/duration;previous=now
      if(value>=1){
        if(current>=events.length-1){setProgress(1);setPlaying(false);return}
        value=0;current++;setIndex(current);setSelected(null)
      }
      setProgress(value);frame=requestAnimationFrame(step)
    }
    frame=requestAnimationFrame(step);return()=>cancelAnimationFrame(frame)
  },[playing,reduced,signature]) // Progress is owned by the animation until paused.
  const event=events[Math.min(index,Math.max(0,events.length-1))]
  const resolved=progress >= (event?.action.kind === 'shot' ? .6 : .8)
  useEffect(()=>{onPlayhead?.({index,resolved})},[index,resolved,onPlayhead,signature])
  const scene=pitchScene(event,progress)
  const goal=event?.action.kind==='shot'&&event.action.outcome==='goal'&&resolved
  const history=events.slice(Math.max(0,index-4),index+1).map((record,i)=>({record,index:Math.max(0,index-4)+i})).reverse()
  const target=recipient(event)
  const startPlayback=()=>{
    if(reduced){setProgress(p=>p===0?1:0);return}
    if(!playing && (index===events.length-1 || progress>=1)){setIndex(0);setProgress(0);setSelected(null)}
    setPlaying(v=>!v)
  }
  const select=(next:number)=>{setPlaying(false);setIndex(next);setProgress(0);setSelected(null)}
  return <section className={`fan-pitch ${compact?'is-compact':''}`} aria-label={t('Match pitch','比赛球场')}>
    <div className="fan-pitch-heading"><div><p className="fan-kicker">{t('ON THE PITCH','球场上')}</p><h2>{t('Watch the play','观看回放')}</h2></div>
      <div className="fan-tracker-clock"><span>{t(playing?'Playing':'Replay',playing?'播放中':'回放')}</span><span className="fan-pitch-time">{event ? clock(event.occurred_at.elapsed_ms,event.occurred_at.period) : '—'}</span></div></div>
    <div className="fan-pitch-toolbar">
      <div className="fan-pitch-view" role="group" aria-label={t('Pitch view','球场视图')}>
        <button aria-pressed={focusBall} onClick={()=>setFocusBall(true)}>{t('Near the ball','球附近')}</button>
        <button aria-pressed={!focusBall} onClick={()=>setFocusBall(false)}>{t('All players','所有球员')}</button>
      </div>
      <span>{focusBall?t('26 m spotlight · tap any player','26米聚焦 · 点击球员'):t('Both teams · tap any player','双方阵容 · 点击球员')}</span>
    </div>
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
        {focusBall && <circle className="fan-ball-spotlight" cx={scene.ball.x} cy={scene.ball.y} r={BALL_FOCUS_RADIUS} fill="#e8e6b5" fillOpacity=".07" stroke="#e4dc96" strokeOpacity=".3" strokeWidth=".3"/>}
        {event && <path d={`M${scene.start.x} ${scene.start.y} L${scene.end.x} ${scene.end.y}`} stroke="#f5dc90" strokeWidth=".5" strokeDasharray="1.3 1.3" opacity=".7"/>}
        {scene.players.map(p=>{
          const distant=focusBall && !p.involved && p.player_id!==selected && Math.hypot(p.x-scene.ball.x,p.y-scene.ball.y)>BALL_FOCUS_RADIUS
          return <g key={p.player_id} className={`fan-pitch-player ${distant?'is-distant':''} ${p.involved?'involved':''} ${p.player_id===selected?'selected':''}`}
          data-player-id={p.player_id}
          role="button" tabIndex={0} aria-label={`${playerName(p.player_id)}, ${clubName(p.team_id)}`} aria-pressed={selected===p.player_id}
          transform={`translate(${p.x} ${p.y})`} onClick={()=>setSelected(p.player_id)}
          onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();setSelected(p.player_id)}}}>
          <g transform={portrait?"rotate(-90)":undefined}>
          <title>{playerName(p.player_id)} · {clubName(p.team_id)}</title>
          <circle className="player-hit" r={portrait?5.2:4} fill="transparent"/>
          <ellipse className="player-shadow" cy="2.4" rx="2.8" ry="1" fill="#071c16" opacity=".32"/>
          <circle className="player-halo" r="3.5" fill="none" stroke="#f5d77f" strokeWidth=".5" opacity={p.involved||p.player_id===selected?1:0}/>
          <circle className="player-disc" r={distant?1.2:2.7} fill={p.team_id==='eastbridge'?'#f2d483':'#d0e6fb'} stroke={p.team_id==='eastbridge'?'#183c2e':'#193f70'} strokeWidth=".65"/>
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
          <button aria-current={at===index?'step':undefined} onClick={()=>select(at)} aria-label={`${t('Replay','回放')} ${clock(record.occurred_at.elapsed_ms,record.occurred_at.period)}: ${actionText(record,zh)}`}>
            <span className="fan-feed-meta"><time>{clock(record.occurred_at.elapsed_ms,record.occurred_at.period)}</time><span>{at===index?t('On the pitch','球场上'):clubName(record.actor.team_id)}</span></span>
            <strong>{actionText(record,zh)}</strong>
          </button>
        </li>)}</ol>
        <button className="fan-latest-play" disabled={!events.length || index===events.length-1} onClick={()=>select(events.length-1)}>{t('Latest play','最新进攻')} <span aria-hidden="true">↗</span></button>
      </aside>}
    </div>
    <div className="fan-pitch-caption" aria-live={playing?'off':'polite'}><span className="fan-play-dot"/>
      <p>{selected ? `${playerName(selected)} · ${clubName(selected.startsWith('eb')?'eastbridge':'northport')}` : event ? (event.action.kind==='shot'&&!resolved ? t(`${playerName(event.actor.player_id)} lines up the shot…`,`${playerName(event.actor.player_id)}准备射门…`) : actionText(event,zh)) : t('Waiting for the next play','等待下一次进攻')}</p>
      {selected && <button onClick={()=>setSelected(null)}>{t('Back to play','返回回放')}</button>}</div>
    <div className="fan-pitch-controls">
      <button className="fan-primary" disabled={!events.length} onClick={startPlayback}>{reduced?t('Show ball movement','查看传球落点'):playing?t('Pause play','暂停'):t('Play sequence','播放片段')} <span aria-hidden="true">{playing?'Ⅱ':'▶'}</span></button>
      <button className="fan-secondary" disabled={!events.length || index===0} onClick={()=>select(index-1)} aria-label={t('Previous play','上一次进攻')}>←</button>
      <button className="fan-secondary" disabled={!events.length || index===events.length-1} onClick={()=>select(index+1)} aria-label={t('Next play','下一次进攻')}>→</button>
      <span>{events.length ? `${index+1} / ${events.length}` : '—'}</span><small>{t('Select a player to see their name','选择球员查看姓名')}</small>
    </div>
  </section>
}
