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
  return positionedActions(sequenceEvents(events,selected),selected.team_id)
}
export function positionedActions(events:GIEvent[],viewTeam:number) {
  return events
    .filter(e=>usable(e.start)&&!['Reflexes','Save attempt','Goalkeeper leaving line'].includes(e.detail))
    .map(e=>({event:e,start:inFrame(e.start!,e.team_id,viewTeam),
      end:(e.kind==='Shot'||e.outcome==='own_goal')&&e.provider_event_id!==null?null:usable(e.end)?inFrame(e.end,e.team_id,viewTeam):null}))
}
export function sceneRoster(players:GIPlayer[],events:GIEvent[],at=events.at(-1)) {
  const reached=(t:{period:number;elapsed_ms:number})=>!!at&&(at.period>t.period||at.period===t.period&&at.elapsed_ms>=t.elapsed_ms)
  return players.filter(p=>(p.starter!==false||!!p.entered_at&&reached(p.entered_at))&&(!p.left_at||!reached(p.left_at)))
    .sort((a,b)=>a.team_id-b.team_id||(a.formation_slot??Number(a.alias_id.slice(2))-1)-(b.formation_slot??Number(b.alias_id.slice(2))-1))
}

/** Presentation defaults, constrained by recorded touches; never tracking measurements. */
export function formation(slot:number,team:number,viewTeam:number,ball:Point,home?:Point|null):Point {
  const shape=[[5,34],[24,9],[20,25],[20,43],[24,59],[43,16],[39,34],[43,52],[66,12],[70,34],[66,56]]
  const [x,y]=home?[home.x,home.y]:shape[(Number.isFinite(slot)?Math.max(0,slot):0)%11]
  const own=inFrame(ball,team,viewTeam)
  return inFrame({x:clamp(x+(slot?(own.x-52.5)*.32:Math.max(0,own.x-65)*.07),2,98),y:clamp(y+(own.y-34)*(slot?.22:.12),3,65)},team,viewTeam)
}
const clamp=(n:number,min:number,max:number)=>Math.max(min,Math.min(max,n))
const distance=(a:Point,b:Point)=>Math.hypot(a.x-b.x,a.y-b.y)
const lerp=(a:Point,b:Point,t:number)=>({x:a.x+(b.x-a.x)*t,y:a.y+(b.y-a.y)*t})
const smooth=(t:number)=>t*t*(3-2*t)
// Conservative presentation envelope, not athlete-specific measured performance.
export const MOTION={run:8,acceleration:5,walk:2.2,ball:32,fade:250} as const
const travelTime=(d:number)=>Math.max(1.5*d/MOTION.run,Math.sqrt(6*d/MOTION.acceleration))*1000
export type ReplayAction=ReturnType<typeof replayActions>[number]
export type TimedAction=ReplayAction & {at:number;duration:number;scene:number;destination:Point;loft:number;release:number;resolved:number}
type Anchor={at:number;point:Point}
type Group={actions:TimedAction[];at:number;duration:number;scene:number;cut:boolean}
export type ReplayTimeline={actions:TimedAction[];duration:number;groups:Group[];viewTeam:number}
const sameMoment=(a:GIEvent,b:GIEvent)=>a.period===b.period&&a.elapsed_ms===b.elapsed_ms
const carry=(a:ReplayAction)=>a.event.kind==='Carry'||a.event.detail==='Acceleration'
function destination(a:ReplayAction,viewTeam:number):Point {
  const e=a.event
  if(e.kind==='Shot'||e.outcome==='own_goal'){
    if(a.end)return a.end
    const direction=e.outcome==='own_goal'?(e.team_id===viewTeam?-1:1):(e.team_id===viewTeam?1:-1)
    const goalX=direction===1?105:0
    if(e.goal_for!==null)return {x:goalX,y:34}
    if(e.outcome==='blocked')return {x:clamp(a.start.x+direction*5,1,104),y:a.start.y}
    if(e.outcome==='off_target')return {x:goalX,y:a.start.y<34?27:41}
    if(e.outcome==='woodwork')return {x:goalX,y:a.start.y<34?30.34:37.66}
    // Non-goal on-target shots finish in front of the goal, rather than in the net.
    return {x:goalX-direction*2.5,y:clamp(a.start.y,31,37)}
  }
  return a.end??a.start
}
function breakBetween(previous:TimedAction,next:ReplayAction,viewTeam:number,players:GIPlayer[]) {
  const a=previous.event,b=next.event,gap=b.elapsed_ms-a.elapsed_ms
  if(a.period!==b.period||a.goal_for!==null||restart(b)||a.kind==='Foul'||a.kind==='Interruption'||a.kind==='Offside')return true
  if(a.kind==='Shot'&&['off_target','unknown'].includes(a.outcome))return true
  if(gap>12000||gap<0||distance(previous.destination,next.start)>14)return true
  if(players.length&&sceneRoster(players,[],a).map(p=>p.player_id).join()!==sceneRoster(players,[],b).map(p=>p.player_id).join())return true
  return false
}
function mandatory(groups:Group[],playerId:string,viewTeam:number):Anchor[] {
  const points:Anchor[]=[]
  for(let i=0;i<groups.length;i++){
    const group=groups[i],next=groups[i+1]
    const own=group.actions.filter(a=>a.event.player_id===playerId)
    for(const a of own){
      // A duel records the ball's travel. Both contestants stay at the contest.
      const p=a.event.kind==='Duel'?{x:a.start.x,y:clamp(a.start.y+(a.event.team_id===viewTeam?-.55:.55),.5,67.5)}:a.start
      points.push({at:a.at,point:p})
      if(carry(a))points.push({at:a.at+a.duration*.12,point:a.start},{at:a.at+a.duration*.8,point:a.destination})
      else if(a.event.kind==='Shot'||a.event.outcome==='own_goal')points.push({at:a.at+a.duration*a.resolved,point:p})
    }
    const pass=group.actions.find(a=>a.event.kind==='Pass'&&a.event.outcome==='complete')
    const receiver=next?.actions.find(a=>a.event.player_id===playerId&&a.event.team_id===pass?.event.team_id)
    if(pass&&receiver&&distance(pass.destination,receiver.start)<5)points.push({at:pass.at+pass.duration*.8,point:receiver.event.kind==='Duel'?{x:receiver.start.x,y:clamp(receiver.start.y+(receiver.event.team_id===viewTeam?-.55:.55),.5,67.5)}:receiver.start})
  }
  return [...new Map(points.map(p=>[p.at,p])).values()].sort((a,b)=>a.at-b.at)
}
function stamp(groups:Group[]){let at=0;for(const g of groups){g.at=at;for(const a of g.actions){a.at=at;a.duration=g.duration}at+=g.duration}return Math.max(at,1000)}
export function playTimeline(actions:ReplayAction[],players:GIPlayer[]=[],viewTeam=actions[0]?.event.team_id??4418):ReplayTimeline {
  const groups:Group[]=[];let scene=0
  for(let i=0;i<actions.length;){
    let end=i+1;while(end<actions.length&&sameMoment(actions[end].event,actions[i].event))end++
    const source=actions.slice(i,end),previous=groups.at(-1)?.actions.at(-1)
    const cut=!!previous&&breakBetween(previous,source[0],viewTeam,players)
    if(cut)scene++
    const timed=source.map(a=>({...a,at:0,duration:0,scene,release:.12,resolved:.8,destination:destination(a,viewTeam),loft:/high pass|cross|clearance|air duel|head pass/i.test(a.event.detail)?3:0}))
    const d=Math.max(...timed.map(a=>distance(a.start,a.destination)))
    const speed=carry(source[0])?4.5:source[0].event.kind==='Shot'?23.5:timed[0].loft?16:18
    let duration=Math.max(1300,1000*d/speed/.68)
    if(source.some(a=>a.event.goal_for!==null)){duration=Math.max(1800,200+1000*d/speed+1000);for(const a of timed){a.release=200/duration;a.resolved=1-1000/duration}}
    if(carry(source[0]))duration=Math.max(duration,travelTime(d)/.68)
    groups.push({actions:timed,at:0,duration,scene,cut});i=end
  }
  // Connecting a small positional mismatch needs actual travel time, not a 200ms jump.
  for(let i=0;i<groups.length-1;i++)if(!groups[i+1].cut){const g=groups[i],next=groups[i+1];g.duration=Math.max(g.duration,distance(g.actions.at(-1)!.destination,next.actions.at(-1)!.start)/18*1000/.2)}
  stamp(groups)
  // Lengthen feasible contacts locally. Contradictory or missing travel becomes a
  // scene boundary instead of forcing a sprint or slowing an entire possession.
  for(let iteration=0;iteration<20;iteration++){
    const factors=new Map<Group,number>();let newCuts=false
    for(let sid=0;sid<=scene;sid++){
      const local=groups.filter(g=>g.scene===sid),ids=new Set(local.flatMap(g=>g.actions.map(a=>a.event.player_id)))
      for(const id of ids){const points=mandatory(local,id,viewTeam)
        for(let j=1;j<points.length;j++){
          const a=points[j-1],b=points[j],gap=b.at-a.at,need=travelTime(distance(a.point,b.point))
          if(gap<=0||need<=gap+1)continue
          const affected=local.filter(g=>g.at<b.at&&g.at+g.duration>a.at),factor=need/gap*1.001
          const boundary=local.find(g=>g.at>a.at&&g.at<=b.at)
          if(boundary&&(factor>3||affected.some(g=>g.duration*factor>10000))){boundary.cut=true;newCuts=true}
          else for(const g of affected)factors.set(g,Math.max(factors.get(g)??1,factor))
        }
      }
    }
    if(newCuts){scene=0;for(const [i,g] of groups.entries()){if(i&&g.cut)scene++;g.scene=scene;for(const a of g.actions)a.scene=scene}}
    else for(const [g,factor] of factors)g.duration*=factor
    stamp(groups);if(!newCuts&&!factors.size)break
  }
  return {groups,actions:groups.flatMap(g=>g.actions),duration:stamp(groups),viewTeam}
}
function boundedToward(from:Point,to:Point,available:number){
  const d=distance(from,to),seconds=Math.max(0,available)/1000
  const max=Math.min(MOTION.run*seconds/1.5,MOTION.acceleration*seconds*seconds/6)
  return lerp(from,to,d?Math.min(1,max/d):0)
}
function tactical(p:GIPlayer,ball:Point,viewTeam:number,possessing:number):Point {
  const slot=p.formation_slot??Math.max(0,Number(p.alias_id.slice(2))-1)
  const base=formation(slot,p.team_id,viewTeam,ball,p.formation_position),own=inFrame(base,p.team_id,viewTeam)
  const localBall=inFrame(ball,p.team_id,viewTeam)
  if(p.role==='GK'||slot===0)return inFrame({x:clamp(2.5+localBall.x*.045,2.5,7),y:clamp(34+(localBall.y-34)*.17,29,39)},p.team_id,viewTeam)
  if(p.team_id!==possessing){own.x=Math.min(own.x,Math.max(10,localBall.x+8));own.y=34+(own.y-34)*.82}
  return inFrame({x:clamp(own.x,2,103),y:clamp(own.y,2,66)},p.team_id,viewTeam)
}
const pathCache=new WeakMap<ReplayTimeline,Map<string,Anchor[]>>()
function playerPath(t:ReplayTimeline,groups:Group[],p:GIPlayer,viewTeam:number) {
  let cached=pathCache.get(t);if(!cached){cached=new Map();pathCache.set(t,cached)}
  const key=`${groups[0].scene}:${viewTeam}:${p.player_id}:${p.formation_slot??p.alias_id}`
  const saved=cached.get(key);if(saved)return saved
  const first=groups[0],last=groups.at(-1)!,start=first.at,end=last.at+last.duration
  const points=mandatory(groups,p.player_id,viewTeam)
  if(p.role==='GK'||p.formation_slot===0){
    for(const g of groups){const shot=g.actions.find(a=>a.event.kind==='Shot'||a.event.outcome==='own_goal')
      if(!shot||shot.event.player_id===p.player_id)continue
      const defending=shot.event.outcome==='own_goal'?shot.event.team_id===p.team_id:shot.event.team_id!==p.team_id
      if(!defending)continue
      const setup=tactical(p,shot.start,viewTeam,shot.event.team_id)
      const target={x:clamp(shot.destination.x,2,103),y:clamp(shot.destination.y,28,40)}
      const reaction=boundedToward(setup,target,g.duration*(shot.resolved-shot.release)*.9)
      const candidates=[{at:g.at+g.duration*shot.release,point:setup},{at:g.at+g.duration*shot.resolved,point:reaction}]
      for(const candidate of candidates){
        const before=points.filter(a=>a.at<candidate.at).at(-1),after=points.find(a=>a.at>candidate.at)
        if(points.some(a=>a.at===candidate.at))continue
        if(before&&travelTime(distance(before.point,candidate.point))>candidate.at-before.at||after&&travelTime(distance(candidate.point,after.point))>after.at-candidate.at)continue
        points.push(candidate);points.sort((a,b)=>a.at-b.at)
      }
    }
  }
  const initial=tactical(p,first.actions[0].start,viewTeam,first.actions[0].event.team_id)
  const final=tactical(p,last.actions.at(-1)!.destination,viewTeam,last.actions.at(-1)!.event.team_id)
  if(!points.length||points[0].at>start){const next=points[0];points.unshift({at:start,point:next?boundedToward(next.point,initial,next.at-start):initial})}
  if(points.at(-1)!.at<end){const prev=points.at(-1)!;points.push({at:end,point:boundedToward(prev.point,final,end-prev.at)})}
  // Add feasible supporting movements between observed contacts, keeping enough time to arrive.
  const result:Anchor[]=[]
  for(let i=0;i<points.length-1;i++){
    const a=points[i],b=points[i+1];result.push(a);let previous=a
    for(const g of groups){
      const at=g.at+g.duration*.5
      if(at<=previous.at+1500||at>=b.at-1500)continue
      const ball=g.actions.at(-1)!.destination,target=tactical(p,ball,viewTeam,g.actions.at(-1)!.event.team_id)
      const direct=lerp(a.point,b.point,(at-a.at)/(b.at-a.at))
      let desired=points.length===2?target:lerp(direct,target,.35)
      const budget=Math.min(4,(at-previous.at)/1000*MOTION.walk)
      const d=distance(previous.point,desired);if(d>budget)desired=lerp(previous.point,desired,budget/d)
      if(travelTime(distance(previous.point,desired))<=at-previous.at&&travelTime(distance(desired,b.point))<=b.at-at){previous={at,point:desired};result.push(previous)}
    }
  }
  result.push(points.at(-1)!);cached.set(key,result);return result
}
export function replayFrame(timeline:ReplayTimeline,clock:number,roster:GIPlayer[],viewTeam:number) {
  const group=timeline.groups.find(g=>clock>=g.at&&clock<g.at+g.duration)??timeline.groups.at(-1)
  const active=group?.actions.at(-1),phase=active?clamp((clock-active.at)/active.duration,0,1):0
  if(!active||!group)return {active,phase,ball:{x:52.5,y:34},ballHeight:0,opacity:1,transition:false,players:[]}
  const next=timeline.groups[timeline.groups.indexOf(group)+1]
  const flight=clamp((phase-active.release)/(active.resolved-active.release),0,1)
  const motion=carry(active)?smooth(flight):flight*(1.35-.35*flight)
  let ball=lerp(active.start,active.destination,motion)
  if(phase>=active.resolved&&next&&!next.cut)ball=lerp(active.destination,next.actions.at(-1)!.start,(phase-active.resolved)/(1-active.resolved))
  const scene=timeline.groups.filter(g=>g.scene===group.scene),first=scene[0],last=scene.at(-1)!
  const elapsed=clock-first.at,remaining=last.at+last.duration-clock
  const hasExit=!!timeline.groups.find(g=>g.scene===group.scene+1)
  const opacity=Math.min(first.cut?clamp(elapsed/MOTION.fade,0,1):1,hasExit?clamp(remaining/MOTION.fade,0,1):1)
  const involved=new Set(group.actions.map(a=>a.event.player_id))
  const players=roster.map(original=>{
    const slot=Number(original.alias_id.slice(2))-1
    const p={...original,formation_slot:original.formation_slot??(Number.isFinite(slot)?slot:roster.filter(x=>x.team_id===original.team_id).indexOf(original))}
    const path=playerPath(timeline,scene,p,viewTeam)
    const before=path.filter(a=>a.at<=clock).at(-1)??path[0],after=path.find(a=>a.at>clock)??before
    const pos=lerp(before.point,after.point,after.at===before.at?0:smooth(clamp((clock-before.at)/(after.at-before.at),0,1)))
    return {...p,...pos,highlighted:involved.has(p.player_id)}
  })
  return {active,ball,ballHeight:active.loft*Math.sin(Math.PI*flight),phase,players,opacity,transition:opacity<1}
}
