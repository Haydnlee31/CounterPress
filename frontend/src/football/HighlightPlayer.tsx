import {useEffect,useMemo,useRef,useState} from 'react'
import type {FanPreferences} from '../../../integrations/personalization/client'
import {createFanClient} from '../../../integrations/personalization/client'
import {contextKey,getData,shortName,useFan,useResource} from './data'
import type {Highlight,LiveView,Replay,World} from './data'
import {highlightFrame,highlightTimeline,sourceCutoff} from './replay'
import {Badge} from './visuals'
import {AskFootie} from '../assistant/AskFootie'
import {momentContext} from '../assistant/context'

export function HighlightPlayer({highlight,world,prefs,update,close}:{highlight:Highlight;world:World;prefs:FanPreferences;update:(p:FanPreferences)=>void;close:()=>void}){
  const dialog=useRef<HTMLDialogElement>(null),zh=prefs.language==='zh-Hans'
  useEffect(()=>{
    const el=dialog.current!,old=document.body.style.overflow;el.showModal();document.body.style.overflow='hidden'
    return()=>{el.close();document.body.style.overflow=old}
  },[])
  const resource=useResource(`highlight:${highlight.highlight_id}`,async signal=>{
    const replay=await getData<Replay>(highlight.action.replay_url!,signal),client=createFanClient()
    signal.addEventListener('abort',client.cancel,{once:true})
    try{const initial=await client.match(replay.match_id,sourceCutoff(replay.events[0],false),prefs) as LiveView;return {replay,initial}}
    finally{client.cancel();signal.removeEventListener('abort',client.cancel)}
  })
  return <dialog ref={dialog} className="fh-replay-dialog" aria-labelledby="fh-replay-title" onCancel={close} onClick={e=>{if(e.target===e.currentTarget)close()}}>
    <div className="fh-replay-top"><div><p className="fh-eyebrow">{zh?'精彩片段':'HIGHLIGHT'}</p><h2 id="fh-replay-title">{highlight.title}</h2></div><button className="fh-close" aria-label="Close highlight" onClick={close}>×</button></div>
    {resource.error?<div className="fh-empty" role="alert"><p>{zh?'暂时无法播放，请重试。':'This highlight couldn’t be loaded.'}</p><button className="fh-button" onClick={resource.retry}>{zh?'重试':'Try again'}</button></div>:!resource.data?<p className="fh-loading" role="status">{zh?'正在打开球场…':'Opening the pitch…'}</p>:<ReplayContent {...resource.data} world={world} prefs={prefs} update={update}/>}
  </dialog>
}
function ReplayContent({replay,initial,world,prefs,update}:{replay:Replay;initial:LiveView;world:World;prefs:FanPreferences;update:(p:FanPreferences)=>void}){
  const timeline=useMemo(()=>highlightTimeline(replay),[replay]),[at,setAt]=useState(0),[playing,setPlaying]=useState(()=>!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)
  const zh=prefs.language==='zh-Hans',t=(en:string,cn:string)=>zh?cn:en
  useEffect(()=>{
    if(!playing)return
    let previous=performance.now(),frameId:number
    const tick=(now:number)=>{const delta=Math.min(100,now-previous);previous=now;setAt(v=>Math.min(timeline.duration,v+delta));frameId=requestAnimationFrame(tick)}
    frameId=requestAnimationFrame(tick)
    const hidden=()=>{if(document.hidden)setPlaying(false)};document.addEventListener('visibilitychange',hidden)
    return()=>{cancelAnimationFrame(frameId);document.removeEventListener('visibilitychange',hidden)}
  },[playing,timeline.duration])
  useEffect(()=>{if(at>=timeline.duration)setPlaying(false)},[at,timeline.duration])
  const frame=highlightFrame(replay,timeline,at,world.players,initial.focus.active_player_ids)
  const focus=initial.focus.active_player_ids.includes(prefs.focus_player_id??'')?prefs.focus_player_id!:prefs.favorite_player_ids.find(id=>initial.focus.active_player_ids.includes(id))??replay.events[0].actor.player_id
  const livePrefs=useMemo(()=>({...prefs,focus_player_id:focus}),[prefs,focus])
  const live=useFan<LiveView>(`live:${replay.match_id}:${frame.cutoff.period}:${frame.cutoff.elapsed_ms}:${contextKey(livePrefs,'')}`,client=>client.match(replay.match_id,frame.cutoff,livePrefs,{card_budget:3}))
  const names=new Map(world.players.map(p=>[p.player_id,p.name])),home=replay.teams[0],away=replay.teams[1]
  const club=(id:string)=>world.catalog.clubs.find(c=>c.club_id===id)!
  const clock=`${(frame.source.occurred_at.period===2?45:0)+Math.floor(frame.source.occurred_at.elapsed_ms/60000)}:${String(Math.floor(frame.source.occurred_at.elapsed_ms/1000)%60).padStart(2,'0')}`
  // Local source events provide the scoreboard while insight requests catch up.
  const score={...replay.initial_state.score}
  replay.events.forEach(e=>{if(e.action.outcome==='goal'&&(e.available_at.period<frame.cutoff.period||e.available_at.period===frame.cutoff.period&&e.available_at.elapsed_ms<=frame.cutoff.elapsed_ms))score[e.actor.team_id]++})
  const completed=frame.phase>=.8,name=names.get(frame.source.actor.player_id)
  const labels:Record<string,string>={pass:t('plays the pass','传球'),carry:t('carries the ball','带球推进'),shot:completed&&frame.source.action.outcome==='goal'?t('scores!','射门得分！'):t('takes the shot','射门'),duel:t('challenges for the ball','争抢球权'),recovery:t('wins it back','赢回球权')}
  return <><div className="fh-replay-score"><span><Badge club={club(home.team_id)}/>{home.name}</span><strong>{score[home.team_id]} <em>–</em> {score[away.team_id]}<small>{clock}</small></strong><span>{away.name}<Badge club={club(away.team_id)}/></span></div>
    <div className="fh-replay-layout"><div><svg className="fh-replay-pitch" viewBox="-5 -6 115 80" role="group" aria-label="Highlight pitch with all active players">
      <rect x="-5" y="-6" width="115" height="80" rx="3" fill="#153e35"/>{Array.from({length:10},(_,i)=><rect key={i} x={i*10.5} width="10.5" height="68" fill={i%2?'#ffffff08':'#ffffff02'}/>)}
      <g fill="none" stroke="#ffffff65" strokeWidth=".35"><rect width="105" height="68"/><path d="M52.5 0V68M0 13.84H16.5V54.16H0M105 13.84H88.5V54.16H105M0 24.84H5.5V43.16H0M105 24.84H99.5V43.16H105M-2 30.34H0M-2 30.34V37.66H0M105 30.34H107V37.66H105"/><circle cx="52.5" cy="34" r="9.15"/></g>
      <text x="2" y="-2" fontSize="1.8" fill="#ffffffa0">{home.name.toUpperCase()} →</text><text x="103" y="-2" textAnchor="end" fontSize="1.8" fill="#ffffffa0">← {away.name.toUpperCase()}</text>
      {frame.players.map(p=><g key={p.player_id} transform={`translate(${p.x} ${p.y})`} role="button" tabIndex={0} aria-label={`Focus on ${names.get(p.player_id)}`} aria-pressed={p.player_id===focus} onClick={()=>update({...prefs,focus_player_id:p.player_id})} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();update({...prefs,focus_player_id:p.player_id})}}} className="fh-pitch-player"><title>{names.get(p.player_id)}</title><circle r="4" fill="transparent"/>{(p.highlighted||p.player_id===focus)&&<circle r="3.7" fill="none" stroke={p.player_id===focus?'#fff':'#e7cf82'} strokeWidth=".45" strokeDasharray={p.player_id===focus?undefined:'1.1 .7'}/>}<circle cy=".5" r="2.5" fill="#0005"/><circle r="2.4" fill={p.team_id===0?'#eee0ae':'#bcdff5'} stroke="#173e32" strokeWidth=".4"/><text y=".7" textAnchor="middle" fill="#173e32" fontSize="1.7" fontWeight="800">{shortName(names.get(p.player_id)??'')}</text></g>)}
      <circle cx={frame.ball.x} cy={frame.ball.y} r="1.05" fill="white" stroke="#193a2c" strokeWidth=".3"/>
    </svg><div className="fh-replay-controls"><button className="fh-button" onClick={()=>{if(at>=timeline.duration){setAt(0);setPlaying(true)}else setPlaying(!playing)}}>{at>=timeline.duration?t('Replay','重新播放'):playing?t('Pause','暂停'):t('Play','播放')} {playing?'Ⅱ':'▶'}</button><input type="range" aria-label="Highlight progress" min="0" max={timeline.duration} step="1" value={at} onChange={e=>{setPlaying(false);setAt(Number(e.target.value))}}/><span>{at>=timeline.duration?Math.ceil(timeline.duration/1000):Math.floor(at/1000)} / {Math.ceil(timeline.duration/1000)}s</span></div><p className="fh-play-caption">{name} {labels[frame.source.action.kind]}</p></div>
      <aside className="fh-live-insights"><AskFootie context={momentContext(replay.match_id,frame.source,frame.phase>=.8,`${home.name} × ${away.name} · ${clock}`)} onOpen={()=>setPlaying(false)}/><label>{t('Player focus','焦点球员')}<select aria-label="Highlight player focus" value={focus} onChange={e=>update({...prefs,focus_player_id:e.target.value})}>{initial.focus.active_player_ids.map(id=><option key={id} value={id}>{names.get(id)}</option>)}</select></label><p className="fh-eyebrow">{t('AS THE PLAY UNFOLDS','随比赛实时更新')}</p>{live.error?<div role="alert"><p>{t('Insights couldn’t be loaded.','暂时无法加载解读。')}</p><button className="fh-link" onClick={live.retry}>{t('Try again','重试')}</button></div>:!live.data?<p className="fh-muted" role="status">{t('Following the play…','正在跟进比赛…')}</p>:live.data.cards.map(card=><article className={card.kind==='career_goal_milestone'?'is-milestone':''} key={card.id}><small>{card.title}</small><h3>{card.text}</h3></article>)}
      </aside></div>
  </>
}
