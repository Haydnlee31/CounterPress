import type { GIEvent, GIPlayer } from './data'
export type Point={x:number;y:number}
export function inFrame(point:Point,team:number,viewTeam:number):Point {
  return team===viewTeam?point:{x:105-point.x,y:68-point.y}
}
const usable=(p:Point|null):p is Point=>!!p&&!((p.x===0&&p.y===0)||(p.x===105&&p.y===68))
const restart=(e:GIEvent)=>e.detail==='Restart'||e.kind==='Free Kick'||/kick off|throw in|corner|free kick|penalty/i.test(e.detail)
const terminal=(e:GIEvent)=>(e.kind==='Shot'&&e.outcome!=='blocked')||e.goal_for!==null||e.kind==='Foul'||e.kind==='Interruption'
/** Follow the local possession through its outcome, stopping before the next restart. */
export function sequenceEvents(events:GIEvent[],selected:GIEvent) {
  const half=events.filter(e=>e.period===selected.period)
  const index=half.findIndex(e=>e.event_id===selected.event_id)
  if(index<0)return [selected]
  let first=index,last=index
  // A moment includes a short causal build-up, not the whole possession.
  let lead=0
  while(first>0&&lead<5){const prev=half[first-1],next=half[first]
    if(terminal(prev)||restart(next))break
    if(prev.team_id!==selected.team_id&&prev.kind==='Pass'&&prev.outcome==='complete')break
    first--;lead++
    if(restart(prev))break
  }
  // Resolve the selected action. A blocked shot/challenge follows the contest;
  // a pass includes its receiver's next action. Never wait through a restart.
  const contest=selected.outcome==='blocked'||selected.detail.includes('duel')||selected.review
  while(last<half.length-1){const current=half[last],next=half[last+1]
    if(terminal(current)||restart(next))break
    last++
    if(next.goal_for!==null||terminal(next))break
    const controlled=next.kind==='Pass'||next.kind==='Carry'||next.detail==='Acceleration'||next.detail==='Touch'
    if(controlled&&(!contest||next.team_id!==selected.team_id))break
    if(next.kind==='Recovery'&&!contest)break
  }
  return half.slice(first,last+1)
}
export function replayActions(events:GIEvent[], selected:GIEvent) {
  return sequenceEvents(events,selected)
    .filter(e=>usable(e.start)&&!['Reflexes','Save attempt','Goalkeeper leaving line'].includes(e.detail))
    .map(e=>({event:e,start:inFrame(e.start!,e.team_id,selected.team_id),
      end:(e.kind==='Shot'||e.outcome==='own_goal')&&e.provider_event_id!==null?null:usable(e.end)?inFrame(e.end,e.team_id,selected.team_id):null}))
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


export type ReplayAction=ReturnType<typeof replayActions>[number]
export type TimedAction=ReplayAction & {at:number;duration:number}
export function playTimeline(actions:ReplayAction[]) {
  let cursor=0
  const result:TimedAction[]=[]
  for(let i=0;i<actions.length;){
    const group=actions.filter(a=>a.event.elapsed_ms===actions[i].event.elapsed_ms)
    const distance=Math.max(...group.map(a=>a.end?Math.hypot(a.end.x-a.start.x,a.end.y-a.start.y):0))
    const kind=group[0].event.kind
    const duration=kind==='Shot'?Math.max(1100,Math.min(2200,distance/27*1000+400)):
      kind==='Pass'?Math.max(1100,Math.min(3000,distance/18*1000+400)):
      kind==='Carry'||group[0].event.detail==='Acceleration'?Math.max(1200,Math.min(3500,distance/6*1000)) : 1000
    for(const a of group)result.push({...a,at:cursor,duration})
    cursor+=duration;i+=group.length
  }
  return {actions:result,duration:Math.max(1000,cursor)}
}
const lerp=(a:Point,b:Point,t:number)=>({x:a.x+(b.x-a.x)*t,y:a.y+(b.y-a.y)*t})
export function replayFrame(timeline:ReturnType<typeof playTimeline>,clock:number,roster:GIPlayer[],viewTeam:number) {
  const actions=timeline.actions
  const active=actions.filter(a=>a.at<=clock).at(-1)??actions[0]
  const nextAt=actions.find(a=>a.at>(active?.at??0))?.at
  const next=actions.filter(a=>a.at===nextAt).at(-1)
  const phase=active?Math.min(1,Math.max(0,(clock-active.at)/active.duration)):0
  const destination=(a:TimedAction):Point=>a.end??(a.event.goal_for!==null?{x:a.event.outcome==='own_goal'?0:105,y:34}:
    a.event.kind==='Shot'?{x:a.event.outcome==='blocked'?Math.min(103,a.start.x+5):105,y:a.event.outcome==='off_target'?(a.start.y<34?26:42):34}:a.start)
  const end=active?destination(active):{x:52.5,y:34}
  const ball=active?(phase<.8?lerp(active.start,end,phase/.8):lerp(end,next?.start??end,(phase-.8)/.2)):end
  const involved=new Set(actions.filter(a=>a.at===active?.at).map(a=>a.event.player_id))
  const players=roster.map(p=>{
    const slot=roster.filter(x=>x.team_id===p.team_id).findIndex(x=>x.player_id===p.player_id)
    const initial=formation(slot,p.team_id,viewTeam,actions[0]?.start??ball)
    const final=formation(slot,p.team_id,viewTeam,actions.length?destination(actions[actions.length-1]):ball)
    // Continuous supporting runs, with observed touches taking precedence.
    final.y=Math.max(3,Math.min(65,final.y+(slot%2?2:-2)))
    const anchors:{at:number;point:Point}[]=[{at:0,point:initial},{at:timeline.duration,point:final}]
    for(const a of actions){
      if(a.event.player_id===p.player_id){anchors.push({at:a.at,point:a.start});
        if(a.end&&(a.event.kind==='Carry'||a.event.detail==='Acceleration'||a.event.detail.includes('duel')))anchors.push({at:a.at+a.duration*.8,point:a.end})
      }
      const receiving=actions.find(n=>n.at>a.at)
      if(a.event.kind==='Pass'&&a.event.outcome==='complete'&&receiving?.event.player_id===p.player_id&&receiving.event.team_id===a.event.team_id&&a.end)
        anchors.push({at:a.at+a.duration*.8,point:a.end})
    }
    const touches=anchors.slice(2).sort((a,b)=>a.at-b.at)
    const reachable=(from:Point,target:Point,seconds:number)=>{const distance=Math.hypot(target.x-from.x,target.y-from.y);return lerp(from,target,distance?Math.min(1,6.5*seconds/distance):0)}
    if(touches.length){anchors[0].point=reachable(touches[0].point,initial,touches[0].at/1000);const last=touches[touches.length-1];anchors[1].point=reachable(last.point,final,(timeline.duration-last.at)/1000)}
    // Touch anchors overwrite formation anchors at equal times.
    const unique=[...new Map(anchors.map(a=>[a.at,a])).values()].sort((a,b)=>a.at-b.at)
    const before=unique.filter(a=>a.at<=clock).at(-1)??unique[0],after=unique.find(a=>a.at>clock)??before
    const pos=lerp(before.point,after.point,after.at===before.at?0:Math.min(1,(clock-before.at)/(after.at-before.at)))
    return {...p,...pos,highlighted:involved.has(p.player_id)}
  })
  return {active,ball,players,phase}
}
