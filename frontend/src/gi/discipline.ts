import type {GIEvent} from './data'
// Wyscout v2 event tags: 1701 red, 1702 yellow, 1703 second yellow.
export function cardType(event:GIEvent){
  if(event.tags.includes(1703))return 'second_yellow' as const
  if(event.tags.includes(1701))return 'red' as const
  if(event.tags.includes(1702))return 'yellow' as const
  return null
}
export function discipline(events:GIEvent[],cutoff?:{period:number;elapsed_ms:number}){
  const latest=new Map<string,GIEvent>()
  for(const e of events){
    if(cutoff&&((e.available_period??e.period)>cutoff.period||((e.available_period??e.period)===cutoff.period&&(e.available_ms??e.elapsed_ms)>cutoff.elapsed_ms)))continue
    const old=latest.get(e.event_id);if(!old||e.revision>old.revision)latest.set(e.event_id,e)
  }
  const cards=[...latest.values()].filter(e=>cardType(e)).sort((a,b)=>a.period-b.period||a.elapsed_ms-b.elapsed_ms||a.occurrence_order-b.occurrence_order)
  const players=new Map<string,{player_id:string;yellows:number;sentOff:boolean;event:GIEvent}>()
  for(const e of cards){
    const p=players.get(e.player_id)??{player_id:e.player_id,yellows:0,sentOff:false,event:e}
    const type=cardType(e)
    p.yellows=type==='second_yellow'?Math.max(2,p.yellows+1):p.yellows+(type==='yellow'?1:0)
    p.sentOff=p.sentOff||type==='red'||type==='second_yellow'||p.yellows>=2;p.event=e;players.set(e.player_id,p)
  }
  return {cards,players:[...players.values()]}
}
