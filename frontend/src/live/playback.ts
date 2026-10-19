import type {Event, MatchTime} from '../types'
export const FULL_MATCH='synthetic-32fe41c5d304ce68d7d9'
export const HALF=45*60*1000, END=2*HALF
export const absolute=(at:MatchTime)=>(at.period-1)*HALF+at.elapsed_ms
export function matchFrame(events:Event[],at:number){
  const latest=new Map<string,Event>()
  for(const e of events){
    if(absolute(e.occurred_at)>at || absolute(e.available_at)>at)continue
    if(!latest.has(e.event_id) || latest.get(e.event_id)!.revision<e.revision)latest.set(e.event_id,e)
  }
  const visible=[...latest.values()].sort((a,b)=>a.occurrence_order-b.occurrence_order)
  const current=visible.at(-1),index=visible.length-1
  const next=current?events.find(e=>e.occurrence_order>current.occurrence_order):undefined
  const start=current?Math.max(absolute(current.occurred_at),absolute(current.available_at)):0
  const duration=next?Math.max(1,Math.min(3000,absolute(next.occurred_at)-start)):3000
  const progress=current?Math.min(1,Math.max(0,(at-start)/duration)):0
  const resolved=progress>=(current?.action.kind==='shot'?.6:.8)
  const completed=visible.slice(0,Math.max(0,index+(resolved?1:0)))
  const score={eastbridge:0,northport:0}
  for(const e of completed)if(e.action.kind==='shot' && e.action.outcome==='goal' && e.actor.team_id in score)score[e.actor.team_id as keyof typeof score]++
  return {visible,current,index,progress,resolved,completed,score}
}
