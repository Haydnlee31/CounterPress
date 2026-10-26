import {useState} from 'react'
import type {GIMatch,GIEvent} from '../gi/data'
import {highlightId,highlightLink,saveMoment,useCollection} from './collection'
import {generateSummary} from './summary'
import './highlights.css'

export function ImportMoment({match,event}:{match:GIMatch;event:GIEvent}){
  const {items,error}=useCollection(),[failure,setFailure]=useState('')
  const saved=items.find(h=>h.id===highlightId(match.match_id,event.event_id))
  function add(){try{const h=saveMoment(match,event);setFailure('');void generateSummary(h)}catch(e){setFailure((e as Error).message)}}
  return <div className="hl-import"><div>{saved?<><span role="status">✓ Saved to Highlights</span><a href={highlightLink(saved.id)}>Open highlight ↗</a></>:<button type="button" onClick={add} disabled={!!error}>＋ Save to Highlights</button>}</div>{(failure||error)&&<p role="alert">{failure||error}</p>}</div>
}
