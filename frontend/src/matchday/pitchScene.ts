import type { Event } from '../types'
import { playerName, squads } from './identity'
export type Point = { x: number; y: number }
const formation = [[7,34],[25,9],[22,25],[22,43],[25,59],[43,17],[40,34],[43,51],[65,12],[69,34],[65,56]]
const clamp = (n:number, min:number,max:number) => Math.min(max,Math.max(min,n))
export function fieldPoint(point: Point, team: string): Point {
  return team === 'northport' ? { x:105-point.x,y:68-point.y } : point
}
function point(value: unknown): value is Point {
  return !!value && typeof value === 'object' && 'x' in value && 'y' in value
    && typeof value.x === 'number' && typeof value.y === 'number'
}
export function recipient(event: Event | undefined) {
  const r=event?.action.recipient
  return r && typeof r==='object' && 'player_id' in r && typeof r.player_id==='string' ? r.player_id : null
}
export function actionText(event: Event, zh=false) {
  const name=playerName(event.actor.player_id), target=recipient(event)
  switch(event.action.kind) {
    case 'pass': return zh ? `${name}${event.action.outcome==='completed' ? '传球给' : '尝试传球给'}${target ? playerName(target) : '队友'}`
      : `${name} ${event.action.outcome==='completed' ? 'passes to' : 'tries to find'} ${target ? playerName(target) : 'a teammate'}`
    case 'carry': return zh ? `${name}带球推进` : `${name} carries the ball`
    case 'recovery': return zh ? `${name}赢回球权` : `${name} wins the ball back`
    case 'duel': return zh ? `${name}争抢球权` : `${name} challenges for the ball`
    default: return zh ? `${name}参与这次进攻` : `${name} is involved in the play`
  }
}
/** Display-only formation/movement; event coordinates retain their authoritative meaning. */
export function pitchScene(event: Event | undefined, progress: number) {
  const start=event ? fieldPoint(event.position,event.actor.team_id) : {x:52.5,y:34}
  const rawEnd=event?.action.end_position
  const end=event && point(rawEnd) ? fieldPoint(rawEnd,event.actor.team_id) : start
  const amount=clamp((progress-.2)/.6,0,1), smooth=amount*amount*(3-2*amount)
  const ball={x:start.x+(end.x-start.x)*smooth, y:start.y+(end.y-start.y)*smooth}
  const target=recipient(event)
  const players=squads.map((p,i)=>{
    const [x,y]=formation[p.number-1]
    const base=fieldPoint({x,y},p.team_id)
    const involved=p.player_id===event?.actor.player_id || p.player_id===target
    let position={ x:clamp(base.x+(ball.x-52.5)*.09+Math.sin(progress*Math.PI*2+i)*1.3,4,101),
      y:clamp(base.y+(ball.y-34)*.08+Math.cos(progress*Math.PI*2+i)*1.2,4,64) }
    if (p.player_id===event?.actor.player_id) position=event.action.kind==='carry' ? ball : start
    if (p.player_id===target && event?.action.outcome==='completed' && point(rawEnd)) position=end
    return {...p,...position,involved}
  })
  // Keep illustrative off-ball markers apart without moving observed action anchors.
  for (let pass=0;pass<8;pass++) for(let i=0;i<players.length;i++) for(let j=i+1;j<players.length;j++) {
    const a=players[i], b=players[j], dx=b.x-a.x,dy=b.y-a.y,distance=Math.hypot(dx,dy)
    if(distance>=7.1 || (a.involved&&b.involved)) continue
    const ux=distance>.01?dx/distance:1,uy=distance>.01?dy/distance:0
    const amount=7.1-distance, aShare=a.involved?0:b.involved?1:.5, bShare=b.involved?0:a.involved?1:.5
    a.x=clamp(a.x-ux*amount*aShare,4,101);a.y=clamp(a.y-uy*amount*aShare,4,64)
    b.x=clamp(b.x+ux*amount*bShare,4,101);b.y=clamp(b.y+uy*amount*bShare,4,64)
  }
  return {players,ball,start,end,kicking:event?.action.kind==='pass' && progress>=.15 && progress<=.4}
}
