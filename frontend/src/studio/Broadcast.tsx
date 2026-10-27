import { useEffect, useRef, useState } from 'react'
import { clock } from '../types'
import type { BroadcastSelection, Review } from './session'
import { readingEstimate } from './presentation'

export default function Broadcast({ review, enabled, download, copy }: {
  review: Review; enabled: boolean; download: (selection: BroadcastSelection) => void; copy: (selection: BroadcastSelection) => void
}) {
  const [order,setOrder]=useState(review.recap.statements.map(s=>s.citation.insight_id))
  const [insightId, setInsightId] = useState(order[0] ?? '')
  const [format, setFormat] = useState<'presenter-cue'|'lower-third'>('presenter-cue')
  const [open, setOpen] = useState(false), [draft,setDraft]=useState(false)
  const [presenting,setPresenting]=useState(false),[large,setLarge]=useState(true)
  const dialog=useRef<HTMLDialogElement>(null)
  const statementById=new Map(review.recap.statements.map(s=>[s.citation.insight_id,s]))
  const cueIds=[...order.filter(id=>statementById.has(id)),...statementById.keys()].filter((id,index,ids)=>ids.indexOf(id)===index)
  const stories=cueIds.map(id=>statementById.get(id)).filter(s=>s!==undefined)
  const story = statementById.get(insightId)
  const allowed = enabled && Boolean(story)
  const label = format === 'presenter-cue' ? 'Presenter cue' : 'Lower-third preview'
  const estimate=story?readingEstimate(story):null
  useEffect(()=>{
    if(presenting&&allowed)dialog.current?.showModal?.()
    else {dialog.current?.close?.();if(!allowed)setPresenting(false)}
  },[presenting,allowed])
  const move=(index:number,delta:number)=>setOrder(()=>{const next=[...cueIds];[next[index],next[index+delta]]=[next[index+delta],next[index]];return next})
  const content=story&&<article lang={story.narrative.language}>
    <p className="studio-eyebrow">{story.narrative.subject_name} · {clock(review.recap.cutoff.elapsed_ms)}</p>
    <h2>{story.narrative.title}</h2><p>{story.narrative.explanation}</p>
    <p className="studio-broadcast-qualification">{story.narrative.qualification}</p>
  </article>
  return <section className="studio-broadcast" aria-label="Broadcast desk" id="coverage-desk">
    <div className="studio-section-title"><div><p className="studio-eyebrow">COVERAGE DESK</p><h2>Prepare your coverage</h2></div><span>{stories.length} {stories.length===1?'cue':'cues'} in this review</span></div>
    <p className="studio-muted">Arrange the current stories in reading order. This running order stays in this browser view.</p>
    <ol className="studio-rundown" aria-label="Cue running order">{stories.map((s,index)=><li key={s.citation.insight_id} className={s.citation.insight_id===insightId?'is-selected':''}>
      <button aria-pressed={s.citation.insight_id===insightId} onClick={()=>setInsightId(s.citation.insight_id)}><span>{String(index+1).padStart(2,'0')}</span><strong>{s.narrative.title}</strong><small>~{readingEstimate(s).seconds}s</small></button>
      <div><button aria-label={`Move ${s.narrative.title} earlier`} disabled={index===0} onClick={()=>move(index,-1)}>↑</button><button aria-label={`Move ${s.narrative.title} later`} disabled={index===stories.length-1} onClick={()=>move(index,1)}>↓</button></div>
    </li>)}</ol>
    <div className="studio-broadcast-controls">
      <label>Broadcast story<select value={insightId} disabled={!stories.length} onChange={e => setInsightId(e.target.value)}>{stories.map(s=><option key={s.citation.insight_id} value={s.citation.insight_id}>{s.narrative.subject_name} · {s.narrative.title}</option>)}</select></label>
      <label>Output format<select value={format} disabled={!story} onChange={e => setFormat(e.target.value as typeof format)}><option value="presenter-cue">Presenter cue</option><option value="lower-third">Lower-third preview</option></select></label>
    </div>
    {estimate&&<p className="studio-read-time">Estimated read <strong>~{estimate.seconds}s</strong><span>at {estimate.basis} · includes the full wording; rehearse your pace.</span></p>}
    <div className="studio-output-actions">
      <button disabled={!story} onClick={()=>setDraft(v=>!v)}>{draft?'Close layout preview':'Check layout'}</button>
      <button disabled={!allowed} onClick={() => setOpen(o => !o)}>{open && allowed ? 'Close broadcast preview' : 'Preview broadcast format'}</button>
      <button className="studio-primary" disabled={!allowed} onClick={()=>setPresenting(true)}>Open presenter view</button>
      <button disabled={!allowed} onClick={()=>copy({insight_id:insightId,format:'presenter-text'})}>Copy approved cue</button>
      <button disabled={!allowed} onClick={() => download({ insight_id: insightId, format })}>Download broadcast format</button>
    </div>
    {!allowed&&<p className="studio-muted">Review and approve the current wording to unlock presenter view, copy and downloads.</p>}
    {draft&&story&&<section aria-label="Layout preview"><p className="studio-layout-status">LAYOUT CHECK · {enabled?'APPROVED WORDING':'NOT YET APPROVED'}</p><div className={`studio-broadcast-stage ${format}`}>{content}</div></section>}
    {open&&allowed&&story&&<section aria-label="Approved broadcast preview"><h3>{label}</h3><div className={`studio-broadcast-stage ${format}`}>{content}</div><small>Evidence revision {story.citation.revision} · Approved for this snapshot</small></section>}
    {presenting&&allowed&&story&&<dialog className={`studio-presenter ${large?'is-large':''}`} ref={dialog} onCancel={()=>setPresenting(false)} aria-label="Presenter view">
      <div className="studio-presenter-bar"><span>FOOTIE / PRESENTER</span><label>Text size<select value={large?'large':'standard'} onChange={e=>setLarge(e.target.value==='large')}><option value="standard">Standard</option><option value="large">Large</option></select></label><button onClick={()=>setPresenting(false)}>Close presenter view</button></div>
      {content}
      <div className="studio-presenter-nav"><button disabled={cueIds.indexOf(insightId)<=0} onClick={()=>setInsightId(cueIds[cueIds.indexOf(insightId)-1])}>Previous cue</button><span>{cueIds.indexOf(insightId)+1} / {cueIds.length}</span><button disabled={cueIds.indexOf(insightId)>=cueIds.length-1} onClick={()=>setInsightId(cueIds[cueIds.indexOf(insightId)+1])}>Next cue</button></div>
    </dialog>}
    <details><summary>Export details</summary><p>Downloads are standalone HTML. Copy produces the complete approved wording and its source reference. Both recheck approval on the server. Neither action sends to a broadcast system.</p><p>Later corrections cannot recall an exported file or copied text. Recheck before use.</p></details>
  </section>
}
