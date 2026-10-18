import { useEffect, useMemo, useState } from 'react'
import { outcomeText } from './data'
import type { GIEvent,GIPlayer } from './data'
import { playTimeline,replayFrame,replayActions,sceneRoster,sequenceEvents } from './replay'
export function PlaySequence({events,event,names,players}:{events:GIEvent[];event:GIEvent;names:Map<string,string>;players:GIPlayer[]}) {
  const sequence=useMemo(()=>sequenceEvents(events,event),[events,event])
  const actions=useMemo(()=>replayActions(events,event),[events,event])
  const roster=useMemo(()=>sceneRoster(players,sequence),[players,sequence])
  const timeline=useMemo(()=>playTimeline(actions),[actions])
  const duration=timeline.duration
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
  const {active,ball,players:scene}=replayFrame(timeline,progress*duration,roster,event.team_id)
  return <div className="gi-replay">
    <svg className="gi-pitch" viewBox="-5 -5 115 78" role="img" aria-label="Match replay, selected team attacking right">
      <defs><radialGradient id="gi-spotlight"><stop stopColor="#fff" stopOpacity=".2"/><stop offset="1" stopColor="#fff" stopOpacity="0"/></radialGradient></defs>
      <rect x="-5" y="-5" width="115" height="78" rx="3" fill="#153e35"/>
      {Array.from({length:7},(_,i)=><rect key={i} x={i*15} width="15" height="68" fill={i%2?'#ffffff08':'transparent'}/>)}
      <g fill="none" stroke="#ffffff65" strokeWidth=".35"><rect width="105" height="68"/><path d="M52.5 0V68M0 13.84H16.5V54.16H0M105 13.84H88.5V54.16H105M0 24.84H5.5V43.16H0M105 24.84H99.5V43.16H105M-2 30.34H0M-2 30.34V37.66H0M105 30.34H107V37.66H105"/><circle cx="52.5" cy="34" r="9.15"/></g>
      <text x="52" y="-1.5" textAnchor="middle" fill="#fff" fontSize="2">ATTACKING DIRECTION →</text>
      <circle cx={ball.x} cy={ball.y} r="15" fill="url(#gi-spotlight)"/>
      {scene.map(p=>{
        const pos=p,highlighted=p.highlighted,color=p.team_id===4418?'#e7c771':'#a9d5f7'
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
