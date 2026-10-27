import {MetricMap} from './MetricBoard'
import {clockLabel} from './data'
import type {Analysis,Snapshot} from './data'
export function ContextualInsight({snapshot,rounds,focusPlayerId}:{snapshot:Snapshot|null;rounds:Analysis[];focusPlayerId:string|null}){
  if(!snapshot)return null
  const recent=rounds.filter(r=>r.cutoff.period===snapshot.cutoff.period&&r.cutoff.elapsed_ms<=snapshot.cutoff.elapsed_ms&&snapshot.cutoff.elapsed_ms-r.cutoff.elapsed_ms<=180000).at(-1)
  const message=recent?.messages?.at(-1)
  const cited=recent?.metrics?.filter(m=>message?.metric_ids.includes(m.id))??[]
  const supportedVisual=cited.some(m=>m.key==='shots'&&typeof m.value==='number'&&m.value>0)?'shot_map':cited.some(m=>['box_entries','final_third_entries'].includes(m.key)&&typeof m.value==='number'&&m.value>0)?'pass_routes':null
  const visual=focusPlayerId?'heatmap':message?.visual&&message.visual!=='none'?message.visual:supportedVisual
  if(!visual||visual==='momentum')return null
  const supporting=cited.find(m=>(visual==='shot_map'?m.key==='shots':['box_entries','final_third_entries'].includes(m.key))&&typeof m.value==='number'&&m.value>0)??cited.find(m=>m.player_id)??cited.find(m=>m.club_id)
  const player=focusPlayerId??supporting?.player_id??undefined
  const club=supporting?.club_id??snapshot.clubs[0]?.club_id??''
  const name=snapshot.players.find(p=>p.player_id===player)?.name
  return <section className="an-context-insight" aria-label="Conversation visual"><header><div><p className="an-eyebrow">IN FOCUS</p><h3>{visual==='shot_map'?'Where the chances are going':visual==='pass_routes'?'How the ball is moving':name?`${name} on the ball`:'Where the game is being played'}</h3></div><span>{name??snapshot.clubs.find(c=>c.club_id===club)?.name} · Match so far<br/>Live view · {clockLabel(snapshot.cutoff)}</span></header><MetricMap metrics={snapshot.metrics.filter(m=>m.window==='prefix')} view={visual} clubId={club} playerId={player}/></section>
}
