import {usePlayerPeek} from './PlayerPeek'
import {useReplaySpeed} from './useReplaySpeed'
import {useEffect,useMemo,useRef,useState} from 'react'
import type {FanPreferences} from '../../../integrations/personalization/client'
import {contextKey,getData,useFan,useResource} from './data'
import type {Highlight,HighlightContext,LiveView,Replay,World} from './data'
import type {MatchTime} from '../types'
import {highlightFrame,highlightTimeline} from './replay'
import {Badge} from './visuals'
import {AskFootie} from '../assistant/AskFootie'
import {PitchIdentity,PitchFaceToggle,usePitchFaces} from './PitchIdentity'
import {momentContext} from '../assistant/context'
import './highlightUpdates.css'

const compareTime=(a:MatchTime,b:MatchTime)=>a.period-b.period||a.elapsed_ms-b.elapsed_ms
const observationClock=(at:MatchTime,lengths:number[])=>{
  const ms=at.elapsed_ms+(at.period===2?lengths[0]:0)
  return `${Math.floor(ms/60000)}:${String(Math.floor(ms/1000)%60).padStart(2,'0')}`
}

export function HighlightPlayer({highlight,world,prefs,update,close}:{highlight:Highlight;world:World;prefs:FanPreferences;update:(p:FanPreferences)=>void;close:()=>void}){
  const dialog=useRef<HTMLDialogElement>(null),zh=prefs.language==='zh-Hans'
  useEffect(()=>{
    const el=dialog.current!,old=document.body.style.overflow;el.showModal();document.body.style.overflow='hidden'
    return()=>{el.close();document.body.style.overflow=old}
  },[])
  // Context survives source replay withdrawal. Its confirmed revisions are hints
  // for an explicit review, never permission to advance the viewer's clock.
  const resource=useResource(`highlight-context:${highlight.highlight_id}`,signal=>getData<HighlightContext>(`/api/data/highlights/${highlight.highlight_id}/context`,signal),highlight.match_id??false)
  const [confirmed,setConfirmed]=useState<HighlightContext>()
  useEffect(()=>{if(resource.data)setConfirmed(resource.data)},[resource.data])
  const context=resource.data??(confirmed?.highlight_id===highlight.highlight_id?confirmed:undefined)
  // The immutable clip is fetched once. Revision polling must not destroy the
  // independently mounted insight panel or rewind a paused replay.
  const replay=useResource(`highlight:${highlight.highlight_id}`,signal=>getData<Replay>(highlight.action.replay_url!,signal),false)
  const title=context&&!context.replay_available?context.teams.map(team=>team.name).join(' × '):highlight.title
  return <dialog ref={dialog} className="fh-replay-dialog" aria-labelledby="fh-replay-title" onCancel={close} onClick={e=>{if(e.target===e.currentTarget)close()}}>
    <div className="fh-replay-top"><div><p className="fh-eyebrow">{context&&!context.replay_available?(zh?'比赛时刻':'MATCH MOMENT'):(zh?'精彩片段':'HIGHLIGHT')}</p><h2 id="fh-replay-title">{title}</h2></div><button className="fh-close" aria-label="Close highlight" onClick={close}>×</button></div>
    {!context?(resource.error?<div className="fh-empty" role="alert"><p>{zh?'暂时无法加载这个时刻。':'This moment couldn’t be loaded.'}</p><button className="fh-button" onClick={resource.retry}>{zh?'重试':'Try again'}</button></div>:<p className="fh-loading" role="status">{zh?'正在打开球场…':'Opening the pitch…'}</p>):<ReplayContent key={highlight.highlight_id} context={context} contextReady={!!resource.data} contextError={!!resource.error} retryContext={resource.retry} replay={replay.data} replayError={!!replay.error} retryReplay={replay.retry} world={world} prefs={prefs} update={update}/>}
  </dialog>
}
function ReplayContent({replay,replayError,retryReplay,context,contextReady,contextError,retryContext,world,prefs,update}:{replay?:Replay;replayError:boolean;retryReplay:()=>void;context:HighlightContext;contextReady:boolean;contextError:boolean;retryContext:()=>void;world:World;prefs:FanPreferences;update:(p:FanPreferences)=>void}){
  const timeline=useMemo(()=>replay?highlightTimeline(replay):null,[replay]),[at,setAt]=useState(0),[playing,setPlaying]=useState(()=>!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)
  const [review,setReview]=useState<{cutoff:MatchTime;sequence:number}|null>(null)
  const canReplay=contextReady&&context.replay_available&&!!replay&&!review
  const [faces,setFaces]=usePitchFaces(),[speed,setSpeed]=useReplaySpeed()
  const peek=usePlayerPeek(world.players)
  const zh=prefs.language==='zh-Hans',t=(en:string,cn:string)=>zh?cn:en
  useEffect(()=>{
    if(!playing||!canReplay||!timeline)return
    let previous=performance.now(),frameId:number
    const tick=(now:number)=>{const delta=Math.max(0,Math.min(100,now-previous));previous=now;setAt(v=>Math.max(0,Math.min(timeline.duration,v+delta*speed)));frameId=requestAnimationFrame(tick)}
    frameId=requestAnimationFrame(tick)
    const hidden=()=>{if(document.hidden)setPlaying(false)};document.addEventListener('visibilitychange',hidden)
    return()=>{cancelAnimationFrame(frameId);document.removeEventListener('visibilitychange',hidden)}
  },[playing,timeline,canReplay,speed])
  useEffect(()=>{if(!context.replay_available||timeline&&at>=timeline.duration)setPlaying(false)},[at,timeline,context.replay_available])
  const frame=replay&&timeline?highlightFrame(replay,timeline,at,world.players,context.active_player_ids):null
  const historicalCutoff=frame?.cutoff??(context.replay_available?context.initial_cutoff:context.original_cutoff)
  const cutoff=review?.cutoff??historicalCutoff,sequence=review?.sequence??context.original_sequence
  const hasUpdate=context.latest_sequence>sequence||(compareTime(context.latest_cutoff,context.original_cutoff)>0&&compareTime(context.latest_cutoff,cutoff)>0)
  const relevantPlayer=[replay?.events[0]?.actor.player_id,context.goal.player_id].find(id=>id&&context.active_player_ids.includes(id))
  const focus=context.active_player_ids.includes(prefs.focus_player_id??'')?prefs.focus_player_id!:prefs.favorite_player_ids.find(id=>context.active_player_ids.includes(id))??relevantPlayer??context.active_player_ids[0]
  const livePrefs=useMemo(()=>({...prefs,focus_player_id:focus}),[prefs,focus])
  const live=useFan<LiveView>(`live:${context.match_id}:${cutoff.period}:${cutoff.elapsed_ms}:${sequence}:${contextKey(livePrefs,'')}`,client=>client.match(context.match_id,cutoff,livePrefs,{card_budget:3,through_sequence:sequence}))
  const names=new Map(world.players.map(p=>[p.player_id,p.name])),home=context.teams[0],away=context.teams[1]
  const club=(id:string)=>world.catalog.clubs.find(c=>c.club_id===id)!
  const clock=observationClock(cutoff,context.period_lengths_ms)
  // An unchanged, validated clip can bridge short insight reads. Never carry
  // its old score into a corrected, withdrawn or explicitly updated view.
  const originalScore=canReplay&&replay&&sequence===context.original_sequence?{...replay.initial_state.score}:undefined
  if(originalScore&&replay)replay.events.forEach(event=>{
    if(event.action.outcome==='goal'&&compareTime(event.available_at,cutoff)<=0)originalScore[event.actor.team_id]++
  })
  const score=live.data?.facts.score??originalScore
  const activeInsight=live.data?.cards.find(card=>card.ask_footie)?.ask_footie
  const insightContext=activeInsight?{label:activeInsight.label,question:activeInsight.question,matchId:activeInsight.match_id,eventId:activeInsight.event_id,eventRevision:activeInsight.event_revision,cutoff:activeInsight.cutoff}:null
  const completed=!!frame&&frame.phase>=(frame.active?.resolved??.8),name=frame&&names.get(frame.source.actor.player_id)
  const labels:Record<string,string>={pass:t('plays the pass','传球'),carry:t('carries the ball','带球推进'),shot:completed&&frame.source.action.outcome==='goal'?t('scores!','射门得分！'):t('takes the shot','射门'),duel:t('challenges for the ball','争抢球权'),recovery:t('wins it back','赢回球权')}
  const askContext=contextReady&&!hasUpdate?(insightContext??(canReplay&&frame?momentContext(context.match_id,frame.source,completed,`${home.name} × ${away.name} · ${clock}`):null)):null
  return <><div className="fh-replay-score" aria-label={`Score at ${clock}`}><span><Badge club={club(home.team_id)}/>{home.name}</span><strong>{score?.[home.team_id]??'—'} <em>–</em> {score?.[away.team_id]??'—'}<small>{clock}</small></strong><span>{away.name}<Badge club={club(away.team_id)}/></span></div>
    <div className="fh-replay-layout"><div>{canReplay&&frame&&timeline?<><svg className="fh-replay-pitch" viewBox="-5 -6 115 80" role="group" aria-label="Highlight pitch with all active players">
      <rect x="-5" y="-6" width="115" height="80" rx="3" fill="#153e35"/>{Array.from({length:10},(_,i)=><rect key={i} x={i*10.5} width="10.5" height="68" fill={i%2?'#ffffff08':'#ffffff02'}/>)}
      <g fill="none" stroke="#ffffff65" strokeWidth=".35"><rect width="105" height="68"/><path d="M52.5 0V68M0 13.84H16.5V54.16H0M105 13.84H88.5V54.16H105M0 24.84H5.5V43.16H0M105 24.84H99.5V43.16H105M-2 30.34H0M-2 30.34V37.66H0M105 30.34H107V37.66H105"/><circle cx="52.5" cy="34" r="9.15"/></g>
      <text x="2" y="-2" fontSize="1.8" fill="#ffffffa0">{home.name.toUpperCase()} →</text><text x="103" y="-2" textAnchor="end" fontSize="1.8" fill="#ffffffa0">← {away.name.toUpperCase()}</text>
      <g opacity={frame.opacity} pointerEvents={frame.opacity<.5?'none':undefined}>
      {frame.players.map(p=><g key={p.player_id} {...peek.bind(p.player_id,names.get(p.player_id)??p.player_id)} transform={`translate(${p.x} ${p.y})`} role="group" tabIndex={0} aria-label={names.get(p.player_id)} className="fh-pitch-player"><circle r="4" fill="transparent"/>{(p.highlighted||p.player_id===focus)&&<circle r="3.7" fill="none" stroke={p.player_id===focus?'#fff':'#e7cf82'} strokeWidth=".45" strokeDasharray={p.player_id===focus?undefined:'1.1 .7'}/>}<circle cy=".5" r="2.5" fill="#0005"/><PitchIdentity playerId={p.player_id} name={names.get(p.player_id)??p.player_id} color={p.team_id===0?'#eee0ae':'#bcdff5'} r={faces?3.1:2.4} faces={faces}/></g>)}
      <circle cx={frame.ball.x} cy={frame.ball.y-frame.ballHeight*.65} r={1.05+frame.ballHeight*.09} fill="white" stroke="#193a2c" strokeWidth=".3"/>
      </g>
    </svg><div className="fh-replay-controls"><button className="fh-button" onClick={()=>{if(at>=timeline.duration){setAt(0);setPlaying(true)}else setPlaying(!playing)}}>{at>=timeline.duration?t('Replay','重新播放'):playing?t('Pause','暂停'):t('Play','播放')} {playing?'Ⅱ':'▶'}</button><input type="range" aria-label="Highlight progress" min="0" max={timeline.duration} step="1" value={at} onChange={e=>{setPlaying(false);setAt(Number(e.target.value))}}/><span>{at>=timeline.duration?Math.ceil(timeline.duration/1000):Math.floor(at/1000)} / {Math.ceil(timeline.duration/1000)}s</span></div><div className="fh-replay-settings"><PitchFaceToggle faces={faces} change={setFaces}/><label>Speed <select aria-label="Highlight playback speed" value={speed} onChange={e=>setSpeed(Number(e.target.value))}>{[.5,1,1.5,2].map(n=><option key={n} value={n}>{n}×</option>)}</select></label></div><p className="fh-play-caption">{name} {labels[frame.source.action.kind]}</p></>:<div className="fh-replay-withdrawn" role="status"><span aria-hidden="true">↺</span><h3>{!contextReady?(contextError?t('Update unavailable','暂时无法获取更新'):t('Checking this moment…','正在检查这个时刻…')):review?t('You’re reviewing the update','正在查看更新'):!context.replay_available?t('The play has been updated','这个时刻已更新'):replayError?t('Replay unavailable','暂时无法播放'):t('Opening the pitch…','正在打开球场…')}</h3><p>{review||!context.replay_available?t('The earlier replay is no longer shown. Your insights remain available.','原来的回放已撤下，你仍可查看比赛解读。'):t('Your insights are available alongside the replay.','你仍可查看比赛解读。')}</p>{contextError?<button className="fh-link" onClick={retryContext}>{t('Try again','重试')}</button>:context.replay_available&&replayError?<button className="fh-link" onClick={retryReplay}>{t('Try replay again','重试回放')}</button>:null}</div>}</div>
      <aside className="fh-live-insights" aria-label={t('Moment insights','时刻解读')}><div className="fh-observation"><p className="fh-eyebrow">{review?t('UPDATED VIEW','更新视角'):!context.replay_available?t('PAUSED MOMENT','暂停时刻'):t('AS THE PLAY UNFOLDS','随比赛实时更新')}</p><span>{clock}</span>{hasUpdate&&contextReady?<div className="fh-update-notice"><p>{context.review_available?t('An update is available for this moment.','这个时刻有新更新。'):t('The later update is available in Clubhouse.','后续更新可在 Clubhouse 中查看。')}</p>{context.review_available?<button className="fh-button" onClick={()=>{setPlaying(false);setReview({cutoff:{...context.latest_cutoff},sequence:context.latest_sequence})}}>{t('Review update','查看更新')} ↗</button>:focus?<a className="fh-link" href={`#football/player/${encodeURIComponent(focus)}`}>{t('View player','查看球员')} ↗</a>:null}</div>:null}{review?<button className="fh-link" onClick={()=>setReview(null)}>{t('Return to original moment','返回原来的时刻')}</button>:null}</div>{askContext&&<AskFootie context={{...askContext,throughSequence:sequence}} onOpen={()=>setPlaying(false)}/>}<label>{t('Player focus','焦点球员')}<select aria-label="Highlight player focus" value={focus} onChange={e=>update({...prefs,focus_player_id:e.target.value})}>{context.active_player_ids.map(id=><option key={id} value={id}>{names.get(id)}</option>)}</select></label>{live.error?<div role="alert"><p>{t('Insights couldn’t be loaded.','暂时无法加载解读。')}</p><button className="fh-link" onClick={live.retry}>{t('Try again','重试')}</button></div>:!live.data?<p className="fh-muted" role="status">{t('Following the play…','正在跟进比赛…')}</p>:live.data.cards.length?live.data.cards.map(card=><article className={card.kind==='career_goal_milestone'?'is-milestone':''} key={card.id}><small>{card.title}</small><h3>{card.text}</h3></article>):<p className="fh-muted">{t('No active insight at this point in the match.','比赛的这个时间点暂无解读。')}</p>}
      </aside></div>{canReplay&&peek.card}
  </>
}
