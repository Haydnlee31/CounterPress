import type { GIEvent, GIPlayer } from './data'
export type Point={x:number;y:number}
export function inFrame(point:Point,team:number,viewTeam:number):Point {
  return team===viewTeam?point:{x:105-point.x,y:68-point.y}
}
const usable=(p:Point|null):p is Point=>!!p&&!((p.x===0&&p.y===0)||(p.x===105&&p.y===68))
const restart=(e:GIEvent)=>e.kind==='Free Kick'||/kick off|throw in|corner|free kick|penalty/i.test(e.detail)
const terminal=(e:GIEvent)=>(e.kind==='Shot'&&e.outcome!=='blocked')||e.goal_for!==null||e.kind==='Foul'||e.kind==='Interruption'
/** Follow the local possession through its outcome, stopping before the next restart. */
export function sequenceEvents(events:GIEvent[],selected:GIEvent) {
  const half=events.filter(e=>e.period===selected.period)
  const index=half.findIndex(e=>e.event_id===selected.event_id)
  if(index<0)return [selected]
  let first=index,last=index
  while(first>0){const prev=half[first-1],next=half[first];if(terminal(prev)||restart(next)||next.elapsed_ms-prev.elapsed_ms>8000)break
    if(prev.team_id!==selected.team_id&&prev.kind==='Pass'&&prev.outcome==='complete')break
    first--
  }
  while(last<half.length-1){const current=half[last],next=half[last+1]
    if(terminal(current)||restart(next)||next.elapsed_ms-current.elapsed_ms>8000)break
    last++
    // Once possession is lost, include the opponent's next controlled action.
    if(next.team_id!==selected.team_id&&next.kind==='Pass'&&next.outcome==='complete')break
  }
  // Keep the recorded response to a shot, but do not roll into the restart.
  if(terminal(half[last]))while(last+1<half.length&&/Reflexes|Save attempt/.test(half[last+1].detail)&&half[last+1].elapsed_ms-half[last].elapsed_ms<5000)last++
  return half.slice(first,last+1)
}
export function replayActions(events:GIEvent[], selected:GIEvent) {
  return sequenceEvents(events,selected)
    .filter(e=>usable(e.start)&&!['Reflexes','Save attempt','Goalkeeper leaving line'].includes(e.detail))
    .map(e=>({event:e,start:inFrame(e.start!,e.team_id,selected.team_id),
      end:e.kind==='Shot'||e.outcome==='own_goal'?null:usable(e.end)?inFrame(e.end,e.team_id,selected.team_id):null}))
}
export function sceneRoster(players:GIPlayer[],events:GIEvent[]) {
  return [4418,9598].flatMap(team=>{
    const candidates=players.filter(p=>p.team_id===team)
    const involved=new Set(events.filter(e=>e.team_id===team).map(e=>e.player_id))
    return [...candidates.filter(p=>involved.has(p.player_id)),...candidates.filter(p=>!involved.has(p.player_id))].slice(0,11).sort((a,b)=>a.alias_id.localeCompare(b.alias_id))
  })
}
/** Supporting shape is presentation geometry, never a tracking measurement. */
export function formation(slot:number,team:number,viewTeam:number,ball:Point):Point {
  const shape=[[5,34],[24,9],[20,25],[20,43],[24,59],[43,16],[39,34],[43,52],[66,12],[70,34],[66,56]]
  const [x,y]=shape[slot%11]
  const p=inFrame({x,y},team,viewTeam)
  return {x:Math.max(2,Math.min(103,p.x+(slot? (ball.x-52.5)*.16:0))),y:Math.max(3,Math.min(65,p.y+(ball.y-34)*.12))}
}
