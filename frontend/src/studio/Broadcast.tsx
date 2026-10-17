import { useState } from 'react'
import { clock, windowLabel } from '../types'
import type { BroadcastSelection, Review } from './session'

export default function Broadcast({ review, enabled, download }: {
  review: Review; enabled: boolean; download: (selection: BroadcastSelection) => void
}) {
  const [insightId, setInsightId] = useState(review.recap.statements[0]?.citation.insight_id ?? '')
  const [format, setFormat] = useState<BroadcastSelection['format']>('presenter-cue')
  const [open, setOpen] = useState(false)
  const story = review.recap.statements.find(s => s.citation.insight_id === insightId)
  const label = format === 'presenter-cue' ? 'Presenter cue' : 'Lower-third preview'
  const allowed = enabled && Boolean(story)
  return <section className="studio-broadcast" aria-label="Broadcast desk">
    <p className="studio-eyebrow">FROM REVIEW TO REHEARSAL</p><h2>One story. Two ways to tell it.</h2>
    <p>Choose one complete approved statement for your presenter or graphic. Its wording and qualification stay together.</p>
    <div className="studio-broadcast-controls">
      <label>Broadcast story<select value={insightId} disabled={!allowed} onChange={e => setInsightId(e.target.value)}>
        {review.recap.statements.map(s => <option key={s.citation.insight_id} value={s.citation.insight_id}>{s.narrative.subject_name} · {s.narrative.title}</option>)}
      </select></label>
      <label>Output format<select value={format} disabled={!allowed} onChange={e => setFormat(e.target.value as BroadcastSelection['format'])}>
        <option value="presenter-cue">Presenter cue</option><option value="lower-third">Lower-third preview</option>
      </select></label>
      <button disabled={!allowed} onClick={() => setOpen(o => !o)}>{open && allowed ? 'Close broadcast preview' : 'Preview broadcast format'}</button>
      <button disabled={!allowed} onClick={() => download({ insight_id: insightId, format })}>Download broadcast format</button>
    </div>
    {!allowed && <p className="studio-muted">Approve the current snapshot to unlock broadcast formats. Downloads check approval again.</p>}
    {open && allowed && story && <section aria-label="Approved broadcast preview">
      <h3>{label}</h3><p>Read the full qualification with the claim. Rehearse timing before use; text is not shortened to fit a duration.</p>
      <div className={`studio-broadcast-stage ${format}`}><article lang={story.narrative.language}>
        <p className="studio-eyebrow">{story.narrative.subject_name} · Synthetic football</p>
        <h2>{story.narrative.title}</h2><p>{story.narrative.explanation}</p>
        <p className="studio-broadcast-qualification">{story.narrative.qualification}</p>
        <small>Facts through {clock(review.recap.cutoff.elapsed_ms)} · Evidence revision {story.citation.revision}</small>
      </article></div>
      <p className="studio-muted">{review.recap.windows.map(windowLabel).join(' → ')} · Start excluded, end included.</p>
      <details><summary>Approval and evidence</summary><p>Evidence: {story.citation.evidence_id} · Insight: {story.citation.insight_id} · Revision {story.citation.revision}</p>
        <p>Match: {review.recap.match_id} · Source version {review.source_version}<br />Approval: {review.approval_id}</p>
        {review.approved_at_unix_ms != null && <p>Approved {new Date(review.approved_at_unix_ms).toISOString()}</p>}
        {review.workflow?.applied && <p>AI wording approval expires {new Date(review.workflow.expires_at_unix_ms).toISOString()}</p>}
        <p>Fingerprint: {review.fingerprint}</p></details>
      <p className="studio-muted">Synthetic football · Fictional teams and players. Preview only, no broadcast playout. Downloads are static HTML; later corrections cannot recall them. Recheck Studio before use.</p>
    </section>}
  </section>
}
