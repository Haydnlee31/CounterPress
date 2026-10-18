import { useEffect, useMemo, useState } from 'react'
import { outcomeText } from './data'
import type { GIEvent,GIPlayer } from './data'
import { formation,replayActions,sceneRoster,sequenceEvents } from './replay'
export function PlaySequence({events,event,names,players}:{events:GIEvent[];event:GIEvent;names:Map<string,string>;players:GIPlayer[]}) {
  const sequence=useMemo(()=>sequenceEvents(events,event),[events,event])
  const actions=useMemo(()=>replayActions(events,event),[events,event])
  const roster=useMemo(()=>sceneRoster(players,sequence),[players,sequence])
  const origin=sequence[0]?.elapsed_ms??event.elapsed_ms
  const finish=(sequence.at(-1)?.elapsed_ms??event.elapsed_ms)+1400
  const duration=Math.max(1400,finish-origin)
  const [progress,setProgress]=useState(0),[playing,setPlaying]=useState(true)
  useEffect(()=>{
    if(!playing)return
    let previous=performance.now(),frame:number
    const tick=(now:number)=>{const delta=now-previous;previous=now
      if(!document.hidden)setProgress(p=>Math.min(1,p+delta/duration))
      frame=requestAnimationFrame(tick)
    }
    frame=requestAnimationFrame(tick);return()=>cancelAnimationFrame(frame)
  },[playing,duration])
  useEffect(()=>{if(progress>=1)setPlaying(false)},[progress])
  const clock=origin+progress*duration
  const index=Math.max(0,actions.reduce((last,a,i)=>a.event.elapsed_ms<=clock?i:last,-1))
  const active=actions[index],next=actions[index+1]
  const actionDuration=active?Math.max(700,Math.min(1800,(next?.event.elapsed_ms??finish)-active.event.elapsed_ms)):1400
  const phase=active?Math.min(1,Math.max(0,(clock-active.event.elapsed_ms)/actionDuration)):0
  const isGoal=active&&(active.event.outcome==='goal'||active.event.outcome==='own_goal')
  const destination=active?.end??(isGoal?{x:active.event.outcome==='own_goal'?0:105,y:34}:active?.start)
  let ball=active&&destination?{x:active.start.x+(destination.x-active.start.x)*phase,y:active.start.y+(destination.y-active.start.y)*phase}:{x:52.5,y:34}
  // Bridge action anchors continuously so the ball never teleports between records.
  if(active&&next&&destination&&phase>=1){const start=active.event.elapsed_ms+actionDuration;const t=Math.min(1,Math.max(0,(clock-start)/Math.max(1,next.event.elapsed_ms-start)));ball={x:destination.x+(next.start.x-destination.x)*t,y:destination.y+(next.start.y-destination.y)*t}}
  const involved=new Set(actions.filter(a=>Math.abs(a.event.elapsed_ms-(active?.event.elapsed_ms??origin))<900).map(a=>a.event.player_id))
  return <div className="gi-replay">
    <svg className="gi-pitch" viewBox="-5 -5 115 78" role="img" aria-label="Match replay, selected team attacking right">
      <defs><radialGradient id="gi-spotlight"><stop stopColor="#fff" stopOpacity=".2"/><stop offset="1" stopColor="#fff" stopOpacity="0"/></radialGradient></defs>
      <rect x="-5" y="-5" width="115" height="78" rx="3" fill="#153e35"/>
      {Array.from({length:7},(_,i)=><rect key={i} x={i*15} width="15" height="68" fill={i%2?'#ffffff08':'transparent'}/>)}
      <g fill="none" stroke="#ffffff65" strokeWidth=".35"><rect width="105" height="68"/><path d="M52.5 0V68M0 13.84H16.5V54.16H0M105 13.84H88.5V54.16H105M0 24.84H5.5V43.16H0M105 24.84H99.5V43.16H105M-2 30.34H0M-2 30.34V37.66H0M105 30.34H107V37.66H105"/><circle cx="52.5" cy="34" r="9.15"/></g>
      <text x="52" y="-1.5" textAnchor="middle" fill="#fff" fontSize="2">ATTACKING DIRECTION →</text>
      <circle cx={ball.x} cy={ball.y} r="15" fill="url(#gi-spotlight)"/>
      {roster.map(p=>{
        const slot=roster.filter(x=>x.team_id===p.team_id).findIndex(x=>x.player_id===p.player_id)
        const anchors=actions.filter(a=>a.event.player_id===p.player_id)
        const before=anchors.filter(a=>a.event.elapsed_ms<=clock).at(-1),after=anchors.find(a=>a.event.elapsed_ms>clock)
        let pos=formation(slot,p.team_id,event.team_id,ball)
        if(before&&after){const t=Math.min(1,(clock-before.event.elapsed_ms)/(after.event.elapsed_ms-before.event.elapsed_ms||1));pos={x:before.start.x+(after.start.x-before.start.x)*t,y:before.start.y+(after.start.y-before.start.y)*t}}
        else if(before){const t=Math.min(1,Math.max(0,(clock-before.event.elapsed_ms)/1800));const end=before.event.detail.includes('duel')||before.event.detail==='Acceleration'?before.end:before.start;pos=end?{x:before.start.x+(end.x-before.start.x)*t,y:before.start.y+(end.y-before.start.y)*t}:before.start}
        else if(after)pos=after.start
        const highlighted=involved.has(p.player_id),color=p.team_id===4418?'#e7c771':'#a9d5f7'
        return <g key={p.player_id} className="gi-replay-player" data-active={highlighted}>
          {highlighted&&<><circle cx={pos.x} cy={pos.y} r="4.3" fill="none" stroke={color} strokeWidth=".45" strokeDasharray="1.5 .8"/><path d={`M${pos.x-1} ${pos.y-6}L${pos.x} ${pos.y-4.8}L${pos.x+1} ${pos.y-6}`} fill={color}/></>}
          <circle cx={pos.x} cy={pos.y+.45} r="2.4" fill="#0005"/>
          <circle cx={pos.x} cy={pos.y} r={highlighted?2.7:2.2} fill={color} fillOpacity={highlighted?1:.65} stroke={highlighted?'white':'#153e35'} strokeWidth=".35"/>
          <text x={pos.x} y={pos.y+.7} fontSize="1.8" fontWeight="700" textAnchor="middle" fill="#153e35">{names.get(p.player_id)?.split(' ').map(n=>n[0]).slice(0,2).join('')}</text><title>{names.get(p.player_id)}</title>
        </g>
      })}
      <circle cx={ball.x} cy={ball.y} r="1.05" fill="white" stroke="#102d27" strokeWidth=".35"/>
    </svg>
    <div className="gi-playback"><button onClick={()=>{if(progress>=1){setProgress(0);setPlaying(true)}else setPlaying(!playing)}}>{progress>=1?'Replay sequence':playing?'Pause':'Resume'}</button><input type="range" aria-label="Play sequence progress" min="0" max="1" step=".001" value={progress} onChange={e=>{setPlaying(false);setProgress(Number(e.target.value))}}/><span>{Math.floor(progress*duration/1000)} / {Math.ceil(duration/1000)}s</span></div>
    <p className="gi-replay-caption" aria-live="off">{active?`${names.get(active.event.player_id)} · ${outcomeText(active.event)}`:'Following the play'}{progress>=1?' · Full sequence':''}</p>
  </div>
}
