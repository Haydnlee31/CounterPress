import type {Event,MatchTime} from '../types'
import type {GIEvent,GIPlayer} from '../gi/data'
import {inFrame,playTimeline,replayFrame} from '../gi/replay'
import type {Player,Replay} from './data'

export function highlightTimeline(replay:Replay){
  const home=replay.teams[0].team_id
  const actions=replay.events.map(e=>{
    const team=e.actor.team_id===home?0:1,end=e.action.end_position as {x:number;y:number}|undefined
    const event:GIEvent={event_id:e.event_id,provider_event_id:null,revision:e.revision,source_order:e.source_delivery_sequence,occurrence_order:e.occurrence_order,period:e.occurred_at.period,elapsed_ms:e.occurred_at.elapsed_ms,team_id:team,player_id:e.actor.player_id,kind:{pass:'Pass',shot:'Shot',carry:'Carry',duel:'Duel',recovery:'Recovery'}[e.action.kind]??e.action.kind,detail:e.action.kind==='duel'?'Ground attacking duel':'',outcome:e.action.outcome==='completed'?'complete':String(e.action.outcome??''),start:e.position,end:end??null,goal_for:e.action.outcome==='goal'?team:null,review:false,tags:[]}
    return {event,start:inFrame(e.position,team,0),end:end?inFrame(end,team,0):null}
  })
  return playTimeline(actions,[],0)
}
export function sourceCutoff(event:Event,resolved:boolean):MatchTime{
  return resolved?event.available_at:{period:event.occurred_at.period,elapsed_ms:Math.max(0,Math.min(event.occurred_at.elapsed_ms-1,event.available_at.elapsed_ms-1))}
}
export function highlightFrame(replay:Replay,timeline:ReturnType<typeof highlightTimeline>,at:number,players:Player[],activeIds:string[]){
  const home=replay.teams[0].team_id
  const roster:GIPlayer[]=activeIds.map(id=>players.find(p=>p.player_id===id)).filter((p):p is Player=>!!p).sort((a,b)=>a.club_id.localeCompare(b.club_id)||Number(b.role==='GK')-Number(a.role==='GK')||a.number-b.number).map(p=>({player_id:p.player_id,provider_player_id:null,team_id:p.club_id===home?0:1,alias_id:p.player_id,role:p.role}))
  const frame=replayFrame(timeline,at,roster,0)
  const source=replay.events.find(e=>e.event_id===frame.active?.event.event_id)??replay.events[0]
  const recipient=source.action.recipient as {player_id:string}|undefined,keeper=source.action.goalkeeper as {player_id:string}|undefined,opponent=source.action.opponent as {player_id:string}|undefined
  const involved=new Set([source.actor.player_id,recipient?.player_id,keeper?.player_id,opponent?.player_id])
  const scene=frame.players.map(p=>({...p,highlighted:involved.has(p.player_id)}))
  return {...frame,players:scene,source,cutoff:sourceCutoff(source,frame.phase>=(frame.active?.resolved??.8))}
}
