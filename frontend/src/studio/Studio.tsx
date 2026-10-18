import { AppHeader } from '../shell/AppHeader'
import { useEffect, useRef, useState } from 'react'
import { clock, defaultPreferences, windowLabel, type Preferences } from '../types'
import { createSession, type BroadcastSelection, type Review, type Session } from './session'
import Broadcast from './Broadcast'
import { playerName } from '../matchday/identity'
import './studio.css'

const scenarios = [
  ['increase', 'Winning it back high'], ['pressure-increase', 'Handling pressure'],
  ['progression-increase', 'Possession without progress'], ['contribution-increase', 'A player’s contribution'],
  ['stream-recovery', 'Live correction desk'], ['control', 'No-change control'],
]
const statusText: Record<Review['status'], string> = {
  unreviewed: 'Needs your review', approved: 'Approved for this snapshot', revoked: 'Approval revoked',
  changed: 'New version · review again', unavailable: 'No supported story to approve',
}

export default function Studio({ sessionFactory = createSession }: { sessionFactory?: () => Promise<Session | null> }) {
  const [session, setSession] = useState<Session | null>(null)
  const [configured, setConfigured] = useState<boolean | null>(null)
  const [signedIn, setSignedIn] = useState(false)
  const [scenario, setScenario] = useState('increase')
  const [preferences, setPreferences] = useState<Preferences>({ ...defaultPreferences, depth: 'casual' })
  const [review, setReview] = useState<Review | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [checked, setChecked] = useState(false)
  const [preview, setPreview] = useState(false)
  const [attemptId, setAttemptId] = useState<string | null>(null)
  const [notice, setNotice] = useState('')
  const [tick, setTick] = useState(0)
  const epoch = useRef(0)
  const acting = useRef(false)
  const reviewRef = useRef<Review | null>(null)
  useEffect(() => {
    let active = true
    void sessionFactory().then(s => { if (active) { setSession(s); setConfigured(Boolean(s)) } })
      .catch(() => { if (active) { setConfigured(false); setError('Studio sign-in is unavailable. Reload to try again.') } })
    return () => { active = false }
  }, [sessionFactory])
  useEffect(() => {
    const generation = ++epoch.current
    const controller = new AbortController()
    if (!session || !signedIn) return
    setChecked(false)
    let timer: number | undefined
    let expiryTimer: number | undefined
    const update = async () => {
      try {
        const started = performance.now()
        const next = await session.call('review', scenario, preferences, undefined, controller.signal, attemptId)
        if (generation !== epoch.current) return
        if (reviewRef.current?.fingerprint !== next.fingerprint || next.status !== 'approved') setPreview(false)
        if (next.attempt_id && !next.workflow?.applied) setNotice('')
        reviewRef.current = next
        setReview(next); setError(''); setChecked(true)
        if (next.valid_for_ms != null) {
          const remaining = Math.max(0, next.valid_for_ms - (performance.now() - started))
          expiryTimer = window.setTimeout(() => {
            if (generation !== epoch.current) return
            setChecked(false); setPreview(false); setTick(t => t + 1)
          }, remaining)
        }
      } catch (e) {
        if (generation !== epoch.current || controller.signal.aborted) return
        setReview(null); setPreview(false); setError(e instanceof Error ? e.message : 'Review is unavailable.')
      } finally {
        if (generation === epoch.current) timer = window.setTimeout(() => { if (!acting.current) setTick(t => t + 1) }, 5000)
      }
    }
    void update()
    return () => { ++epoch.current; controller.abort(); window.clearTimeout(timer); window.clearTimeout(expiryTimer) }
  }, [session, signedIn, scenario, preferences, tick, attemptId])
  useEffect(() => () => { ++epoch.current }, [])
  const reset = () => { ++epoch.current; setReview(null); reviewRef.current = null; setPreview(false); setChecked(false); setError(''); setAttemptId(null); setNotice('') }
  const signIn = async () => {
    if (!session) return
    setBusy(true); setError('')
    try { await session.signIn(); setSignedIn(true) }
    catch (e) { setError(e instanceof Error ? e.message : 'Sign-in did not finish.') }
    finally { setBusy(false) }
  }
  const signOut = async () => {
    reset(); acting.current = false; setSignedIn(false); setBusy(false)
    await session?.signOut().catch(() => setError('Session ended. Reload before signing in again.'))
  }
  const act = async (action: 'approve' | 'revoke' | 'export' | 'draft', broadcast?: BroadcastSelection) => {
    if (!session || !review || busy || !checked) return
    // Stop the polling effect from accepting an older response over this action.
    const generation = ++epoch.current
    acting.current = true
    setBusy(true); setChecked(false); setPreview(false); setError('')
    try {
      if (action === 'export') {
        const blob = await session.download(scenario, preferences, review.fingerprint, attemptId, broadcast)
        if (generation !== epoch.current) return
        const url = URL.createObjectURL(blob), link = document.createElement('a')
        link.href = url; link.download = `counterpress-${broadcast?.format ?? 'producer-snapshot'}.html`; link.click()
        window.setTimeout(() => URL.revokeObjectURL(url), 1000)
      } else {
        const next = await session.call(action, scenario, preferences, review.fingerprint, undefined, attemptId)
        if (generation !== epoch.current) return
        reviewRef.current = next; setReview(next)
        if (action === 'draft') {
          setAttemptId(next.attempt_id ?? null)
          const messages: Record<string, string> = { completed: 'AI draft ready. Check every statement before approval.', cached: 'Reused the current result; no new model request.', pending: 'A request is already running. Factual wording remains available; retry explicitly later.', busy: 'AI editing is busy. Factual wording remains available.', quota_exceeded: 'AI allowance reached. Factual wording remains available.', stale: 'Evidence changed during editing. Review the current factual wording.', fallback: 'AI editing did not produce a usable draft. Factual wording remains available.', ineligible: 'There is no eligible story for AI editing.' }
          setNotice(messages[next.editorial_status ?? 'fallback'] ?? messages.fallback)
        }
      }
    } catch (e) {
      if (generation === epoch.current) { setReview(null); setError(e instanceof Error ? e.message : 'Review could not be saved.') }
    } finally {
      if (generation === epoch.current) { acting.current = false; setBusy(false); setTick(t => t + 1) }
    }
  }
  const ready = checked && !busy && review?.recap.state === 'ready' && review?.status !== 'unavailable'
  const approved = ready && review?.status === 'approved'
  return <div className="studio">
    <AppHeader active="studio"/>
    <header className="studio-top"><a href={`${window.location.search}#tools`}>← All tools</a>
      {signedIn ? <button onClick={signOut}>End Studio session</button> : <span>Producer workspace</span>}</header>
    <main className="studio-main">
      <div className="studio-intro"><p className="studio-eyebrow">COUNTERPRESS / PRODUCTION</p><h1>Producer Studio</h1>
        <p>Review match stories and prepare presenter cues, graphics and approved snapshots.</p></div>
      <ol className="studio-steps" aria-label="Production steps"><li aria-current={!checked?'step':undefined}><span>01</span> Review the story</li><li aria-current={checked&&!approved?'step':undefined}><span>02</span> Approve the wording</li><li aria-current={approved?'step':undefined}><span>03</span> Prepare coverage</li></ol>
      {error && <p className="studio-alert" role="alert">{error}</p>}
      {!signedIn ? <section className="studio-welcome"><div><h2>Your production workflow</h2>
        <ol><li>Choose a story and audience.</li><li>Check the evidence and limits of the claim.</li><li>Approve, preview and download a snapshot.</li></ol>
        <p>Revised events invalidate the earlier approval. Studio always checks the latest available version.</p></div>
        <div className="studio-signin"><h2>Open your desk</h2><p>Use the Microsoft account assigned CounterPress editor access.</p>
          <button className="studio-primary" disabled={!configured || busy} onClick={signIn}>{busy ? 'Opening Microsoft sign-in…' : 'Sign in with Microsoft'}</button>
          <p>{configured === null ? 'Checking availability…' : configured === false ? 'Studio is not enabled on this deployment yet. Matchday remains available.' : 'Ending this Studio session clears its local token cache. Your Microsoft account stays signed in.'}</p></div>
      </section> : <>
        <section className="studio-controls" aria-label="Review selection">
          <label>Story<select disabled={busy} value={scenario} onChange={e => { reset(); setScenario(e.target.value) }}>{scenarios.map(([id, title]) => <option key={id} value={id}>{title}</option>)}</select></label>
          <label>Story language<select disabled={busy} value={preferences.language} onChange={e => { reset(); setPreferences({ ...preferences, language: e.target.value as Preferences['language'] }) }}><option value="en">English</option><option value="zh-Hans">简体中文</option></select></label>
          <label>Detail<select disabled={busy} value={preferences.depth} onChange={e => { reset(); setPreferences({ ...preferences, depth: e.target.value as Preferences['depth'] }) }}><option value="casual">Quick catch-up</option><option value="analyst">Full explanation</option></select></label>
          <button disabled={busy} onClick={() => { setChecked(false); setTick(t => t + 1) }}>Refresh evidence</button>
        </section>
        <section className="studio-editor" aria-label="AI editing">
          <h2>Optional AI editor</h2><p>The editor selects from verified stories and wording. It cannot add football facts. A draft expires within 60 seconds; approval expires with it.</p>
          {review?.editor_enabled ? <button disabled={!ready} onClick={() => void act('draft')}>Request AI draft</button> : <p>{review ? 'AI editing is not enabled. Factual wording is available.' : 'Checking editor availability…'}</p>}
          {attemptId && <button disabled={busy} onClick={() => { reset(); setTick(t => t + 1) }}>Use factual wording</button>}
          {notice && <p role="status">{notice}</p>}
          {attemptId && <p>{review?.workflow?.applied ? 'AI-assisted selection · Review before expiry' : 'AI draft expired or changed · Factual fallback shown; return to factual wording to approve.'}</p>}
        </section>
        <div className="studio-desk"><section aria-label="Story review">
          <div className="studio-section-title"><h2>1. Review the story</h2><span>{checked ? 'Latest check complete' : 'Checking current evidence…'}</span></div>
          {review ? <><p>Facts through <strong>{clock(review.recap.cutoff.elapsed_ms)}</strong> · Source version {review.source_version}</p>
            <p className="studio-muted">{review.recap.windows.map(windowLabel).join(' → ')} · Start excluded, end included.</p>
            {review.recap.statements.length ? review.recap.statements.map(({ narrative: n, citation: c }) => <article className="studio-story" key={c.insight_id} lang={n.language}>
              <p className="studio-eyebrow">{n.subject_name} / {c.kind}</p><h3>{n.title}</h3><p>{n.explanation}</p><p className="studio-qualification">{n.qualification}</p>
              <details><summary>Evidence reference · revision {c.revision}</summary><dl><dt>Evidence</dt><dd>{c.evidence_id}</dd><dt>Insight</dt><dd>{c.insight_id}</dd><dt>Available from</dt><dd>{clock(c.available_at.elapsed_ms)}</dd></dl>
                {review.evidence.filter(e => e.evidence_id === c.evidence_id && e.revision === c.revision).map(e => <div key={e.evidence_id}>
                  <p>{e.definition}</p><p>Pitch: 105 × 68 metres. The actor’s team attacks towards increasing x.</p>
                  <div className="studio-events"><table><caption>Supporting recorded events · {e.records.length} records</caption><thead><tr><th>Match time</th><th>Player</th><th>Action</th><th>Position (m)</th><th>Event / revision</th></tr></thead>
                    <tbody>{e.records.map(event => <tr key={`${event.event_id}:${event.revision}`}><td>{clock(event.occurred_at.elapsed_ms)}</td><td>{playerName(event.actor.player_id)}</td><td>{event.action.kind.replaceAll('_', ' ')}</td><td>{event.position.x}, {event.position.y}</td><td>{event.event_id} / {event.revision}</td></tr>)}</tbody></table></div>
                </div>)}</details>
            </article>) : <div className="studio-story"><h3>No supported story in this view</h3><p>There is nothing to approve. Choose another story or wait for new evidence.</p></div>}
          </> : <p>{error ? 'Refresh evidence to continue.' : 'Loading the latest story…'}</p>}
        </section><aside className="studio-approval"><p className="studio-eyebrow">PRODUCER CHECKPOINT</p><h2>2. Make the call</h2>
          <p className={`studio-status ${approved ? 'is-approved' : ''}`} role="status">{busy ? 'Saving and checking…' : !checked ? 'Approval not verified' : attemptId && review?.status === 'unavailable' ? 'AI approval expired or changed' : review ? statusText[review.status] : 'Waiting for evidence'}</p>
          <p>Approval covers the displayed wording, evidence revisions, language and detail level. New source events or AI expiry require a fresh review.</p>
          {approved ? <button disabled={!approved} onClick={() => void act('revoke')}>Revoke this approval</button> : <button className="studio-primary" disabled={!ready} onClick={() => void act('approve')}>I reviewed this version · Approve</button>}
          <hr /><h2>3. Prepare your snapshot</h2><p>Preview and export unlock after approval. Neither sends content to a broadcast system.</p>
          <button disabled={!approved} onClick={() => setPreview(p => !p)}>{preview ? 'Close clean preview' : 'Open clean preview'}</button>
          <button disabled={!approved} onClick={() => void act('export')}>Download approved snapshot</button>
          <p className="studio-muted">Downloads are static HTML. Recheck Studio before use; later changes cannot recall a downloaded file.</p>
        </aside></div>
        {review && <Broadcast key={review.fingerprint} review={review} enabled={Boolean(approved)} download={selection => void act('export', selection)} />}
        {preview && approved && review && <section className="studio-preview" aria-label="Approved clean preview"><p className="studio-eyebrow">COUNTERPRESS / APPROVED SNAPSHOT</p><p>Synthetic football · Facts through {clock(review.recap.cutoff.elapsed_ms)}</p>
          {review.recap.statements.map(s => <article key={s.citation.insight_id} lang={s.narrative.language}><h2>{s.narrative.title}</h2><p>{s.narrative.explanation}</p><p>{s.narrative.qualification}</p><small>Evidence revision {s.citation.revision}</small></article>)}<p>Preview only · Revalidated every five seconds while this page is active.</p></section>}
      </>}
      <footer className="studio-footer"><span>Synthetic football · Fictional clubs and players. AI editing runs only when requested.</span><a href={`${window.location.search}#analysis`}>Evidence desk ↗</a></footer>
    </main>
  </div>
}
