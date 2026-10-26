import assets from './preloaded-summaries.json'
import type {Event} from '../types'
import {FootieMascot} from '../assistant/FootieMascot'
import './highlights.css'

type Asset={mode:string;source:unknown[][];score:Record<string,number>;text:string[]}
const summaries=assets as Record<string,Asset>
function stable(value:unknown):string{
  if(Array.isArray(value))return `[${value.map(stable).join(',')}]`
  if(value&&typeof value==='object')return `{${Object.entries(value).sort(([a],[b])=>a.localeCompare(b)).map(([k,v])=>`${JSON.stringify(k)}:${stable(v)}`).join(',')}}`
  return JSON.stringify(value)??'null'
}
export function verifiedSummary(storyId:string,events:Event[],score?:Record<string,number>){
  const asset=summaries[storyId]
  if(!asset||asset.mode!=='azure_generated_verified'||!score)return null
  const rows=events.map(e=>[e.match_id,e.event_id,e.revision,e.occurred_at,e.available_at,e.actor,e.position,e.action.kind,e.action.outcome??null,e.action.recipient??null,e.action.end_position??null,e.action.goalkeeper??null,e.action.situation??null,e.action.technique??null,e.action.from_team_id??null,e.action.control??null])
  return stable(rows)===stable(asset.source)&&stable(score)===stable(asset.score)?asset:null
}
export function PreloadedSummary({storyId,events,score,language='en'}:{storyId:string;events:Event[];score?:Record<string,number>;language?:string}){
  const asset=verifiedSummary(storyId,events,score),zh=language==='zh-Hans'
  return <section className="hl-summary hl-preloaded-summary" aria-label="Highlight AI summary"><div className="hl-summary-heading"><FootieMascot size={46}/><div><p className="fan-kicker">{zh?'FOOTIE 解读':'FOOTIE’S TAKE'}</p><h3>{zh?'Footie 总结 · English':"Footie's Summary"}</h3></div></div>
    {asset?asset.text.map((text,i)=><p key={i}>{text}</p>):<p role="status">{zh?'集锦数据已更新，正在等待相应的总结。':'The highlight records have changed. Its summary needs to be refreshed.'}</p>}
  </section>
}
