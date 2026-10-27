import { AppHeader } from '../shell/AppHeader'
import { useEffect, useRef, useState } from 'react'
import { clock, defaultPreferences, windowLabel, type Preferences } from '../types'
import { createSession, type BroadcastSelection, type Review, type Session } from './session'
import Broadcast from './Broadcast'
import { changedStories } from './presentation'
import { playerName } from '../matchday/identity'
import { readPreferences } from '../matchday/preferences'
import './studio.css'

const scenarios = [
  ['increase', 'Winning it back high'], ['pressure-increase', 'Handling pressure'],
  ['progression-increase', 'Moving the ball forward'], ['contribution-increase', 'A player’s contribution'],
  ['stream-recovery', 'Live correction desk'], ['control', 'When the numbers stay level'],
]

export default function Studio({ sessionFactory = createSession }: { sessionFactory?: () => Promise<Session | null> }) {
  const [uiLang]=useState(()=>readPreferences().language)
  const zh=uiLang==='zh-Hans',t=(en:string,cn:string)=>zh?cn:en
  const statusText: Record<Review['status'], string> = {
    unreviewed: t('Needs your review','需要您的审核'),
    approved: t('Approved for this snapshot','此快照已批准'),
    revoked: t('Approval revoked','批准已撤销'),
    changed: t('New version · review again','新版本 · 请重新审核'),
    unavailable: t('No supported story to approve','没有可批准的故事'),
  }
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
  const [search,setSearch]=useState('')
  const [changes,setChanges]=useState<string[]>([])
  const epoch = useRef(0)
  const acting = useRef(false)
  const expiryDeadline = useRef<number|null>(null)
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
    let timer: number | undefined
    const update = async () => {
      try {
        const started = performance.now()
        let next = await session.call('review', scenario, preferences, undefined, controller.signal, attemptId)
        if (generation !== epoch.current) return
        if(reviewRef.current && reviewRef.current.fingerprint!==next.fingerprint)setChanges(changedStories(reviewRef.current,next))
        if (reviewRef.current?.fingerprint !== next.fingerprint || next.status !== 'approved') setPreview(false)
        if (next.attempt_id && !next.workflow?.applied) setNotice('')
        if(next.valid_for_ms!=null)next={...next,valid_for_ms:Math.max(0,next.valid_for_ms-(performance.now()-started))}
        expiryDeadline.current=next.valid_for_ms==null?null:performance.now()+next.valid_for_ms
        reviewRef.current = next
        setReview(next); setError(''); setChecked(next.valid_for_ms!==0)
      } catch (e) {
        if (generation !== epoch.current || controller.signal.aborted) return
        setReview(null); setPreview(false); setError(e instanceof Error ? e.message : 'Review is unavailable.')
      } finally {
        if (generation === epoch.current) timer = window.setTimeout(() => { if (!acting.current) setTick(t => t + 1) }, 5000)
      }
    }
    void update()
    return () => { ++epoch.current; controller.abort(); window.clearTimeout(timer) }
  }, [session, signedIn, scenario, preferences, tick, attemptId])
  useEffect(() => {
    if(review?.valid_for_ms==null)return
    const timer=window.setTimeout(()=>{setChecked(false);setPreview(false);if(!acting.current)setTick(t=>t+1)},review.valid_for_ms)
    return ()=>window.clearTimeout(timer)
  },[review])
  useEffect(() => () => { ++epoch.current }, [])
  const reset = () => { ++epoch.current; setReview(null); reviewRef.current = null; expiryDeadline.current=null; setPreview(false); setChecked(false); setError(''); setAttemptId(null); setNotice('');setChanges([]) }
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
  const act = async (action: 'approve' | 'revoke' | 'export' | 'draft' | 'copy', broadcast?: BroadcastSelection) => {
    if (!session || !review || busy || !checked) return
    // Stop the polling effect from accepting an older response over this action.
    const generation = ++epoch.current
    acting.current = true
    setBusy(true); setChecked(false); setPreview(false); setError('')
    try {
      if (action === 'export' || action === 'copy') {
        const blob = await session.download(scenario, preferences, review.fingerprint, attemptId, broadcast)
        if (generation !== epoch.current) return
        if(expiryDeadline.current!==null&&performance.now()>=expiryDeadline.current)throw new Error('Approval expired. Review the current wording before exporting.')
        if(action==='copy'){
          const text=await blob.text()
          if(generation!==epoch.current)return
          if(expiryDeadline.current!==null&&performance.now()>=expiryDeadline.current)throw new Error('Approval expired. Review the current wording before copying.')
          await navigator.clipboard.writeText(text)
          if(generation===epoch.current)setNotice('Approved cue copied with its source reference.')
        } else {
        const url = URL.createObjectURL(blob), link = document.createElement('a')
        link.href = url; link.download = `counterpress-${broadcast?.format ?? 'producer-snapshot'}.html`; link.click()
        window.setTimeout(() => URL.revokeObjectURL(url), 1000)
        }
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
    <AppHeader active="studio" language={uiLang}/>
    <header className="studio-top"><a href={`${window.location.search}#tools`}>{t('← All tools','← 所有工具')}</a>
      {signedIn ? <button onClick={signOut}>{t('End Studio session','结束工作室会话')}</button> : <span>{t('Producer workspace','制作人工作区')}</span>}</header>
    <main className="studio-main">
      <div className="studio-intro"><p className="studio-eyebrow">{t('FOOTIE / PRODUCTION','FOOTIE / 制作')}</p><h1>Producer Studio</h1>
        <p>{t('Review match stories and prepare presenter cues, graphics and approved snapshots.','审核比赛故事，准备主持人提示、图形和已批准的快照。')}</p></div>
      <ol className="studio-steps" aria-label="Production steps"><li aria-current={!checked?'step':undefined}><span>01</span>{t(' Review the story',' 审核故事')}</li><li aria-current={checked&&!approved?'step':undefined}><span>02</span>{t(' Approve the wording',' 批准措辞')}</li><li aria-current={approved?'step':undefined}><span>03</span><button className="studio-step-link" disabled={!signedIn} onClick={()=>document.getElementById('coverage-desk')?.scrollIntoView({behavior:'instant',block:'start'})}>{t('Prepare coverage ↓','准备报道 ↓')}</button></li></ol>
      {error && <p className="studio-alert" role="alert">{error}</p>}
      {!signedIn ? <section className="studio-welcome"><div><h2>{t('Your production workflow','您的制作流程')}</h2>
        <ol><li>{t('Choose a story and audience.','选择故事和受众。')}</li><li>{t('Check the evidence and limits of the claim.','检查证据和声明的局限性。')}</li><li>{t('Approve, preview and download a snapshot.','批准、预览并下载快照。')}</li></ol>
        <p>{t('Revised events invalidate the earlier approval. Studio always checks the latest available version.','修订的事件将使之前的批准失效。工作室始终检查最新可用版本。')}</p></div>
        <div className="studio-signin"><h2>{t('Open your desk','打开您的工作台')}</h2><p>{t('Use the Microsoft account assigned CounterPress editor access.','使用分配了 CounterPress 编辑权限的 Microsoft 账户。')}</p>
          <button className="studio-primary" disabled={!configured || busy} onClick={signIn}>{busy ? t('Opening Microsoft sign-in…','正在打开 Microsoft 登录…') : t('Sign in with Microsoft','使用 Microsoft 登录')}</button>
          <p>{configured === null ? t('Checking availability…','正在检查可用性…') : configured === false ? t('Studio is not enabled on this deployment yet. Matchday remains available.','此部署尚未启用工作室。比赛日仍然可用。') : t('Ending this Studio session clears its local token cache. Your Microsoft account stays signed in.','结束此工作室会话将清除本地令牌缓存。您的 Microsoft 账户仍保持登录状态。')}</p></div>
      </section> : <>
        <div className="studio-workspace"><aside className="studio-sources" aria-label="Story sources">
          <p className="studio-eyebrow">{t('STORY SOURCES','故事来源')}</p><h2>{t('Choose your angle','选择您的角度')}</h2>
          <label className="studio-search">{t('Find a story','查找故事')}<input type="search" value={search} onChange={e=>setSearch(e.target.value)} placeholder={t('Search topics…','搜索话题…')} /></label>
          <div className="studio-source-list">{scenarios.filter(([id,title])=>`${id} ${title}`.toLowerCase().includes(search.toLowerCase())).map(([id,title],index)=><button key={id} disabled={busy} aria-pressed={scenario===id} onClick={()=>{if(id!==scenario){reset();setScenario(id)}}}><span>{String(index+1).padStart(2,'0')}</span><strong>{title}</strong><span aria-hidden="true">↗</span></button>)}</div>
          {!scenarios.some(([id,title])=>`${id} ${title}`.toLowerCase().includes(search.toLowerCase()))&&<p className="studio-muted">{t('No matching story. Try "pressure" or clear your search.','没有匹配的故事。尝试"pressure"或清除搜索。')}</p>}
          <p className="studio-muted">{t('Eastbridge × Northport','Eastbridge × Northport')}<br/>{t('Curated insight scenarios','精选洞察场景')}</p>
        </aside><div className="studio-work-area">
        <section className="studio-controls" aria-label="Review selection">
          <label>{t('Story language','故事语言')}<select disabled={busy} value={preferences.language} onChange={e => { reset(); setPreferences({ ...preferences, language: e.target.value as Preferences['language'] }) }}><option value="en">English</option><option value="zh-Hans">简体中文</option></select></label>
          <label>{t('Detail','详细程度')}<select disabled={busy} value={preferences.depth} onChange={e => { reset(); setPreferences({ ...preferences, depth: e.target.value as Preferences['depth'] }) }}><option value="casual">{t('Quick catch-up','快速了解')}</option><option value="analyst">{t('Full explanation','完整解释')}</option></select></label>
          <button disabled={busy} onClick={() => { setChecked(false); setTick(t => t + 1) }}>{t('Refresh evidence','刷新证据')}</button>
        </section>
        <details className="studio-editor" aria-label="AI editing"><summary>{t('Writing assistant','写作助手')}</summary><p>{t('The editor selects from verified stories and wording. It cannot add football facts. A draft expires within 60 seconds; approval expires with it.','编辑器从已验证的故事和措辞中选择，无法添加足球事实。草稿在60秒内过期，批准随之过期。')}</p>
          {review?.editor_enabled ? <button disabled={!ready} onClick={() => void act('draft')}>{t('Request AI draft','请求 AI 草稿')}</button> : <p>{review ? t('AI editing is not enabled. Factual wording is available.','AI 编辑未启用。事实性措辞可用。') : t('Checking editor availability…','正在检查编辑器可用性…')}</p>}
          {attemptId && <button disabled={busy} onClick={() => { reset(); setTick(t => t + 1) }}>{t('Use factual wording','使用事实性措辞')}</button>}
          {attemptId && <p>{review?.workflow?.applied ? t('AI-assisted selection · Review before expiry','AI 辅助选择 · 请在过期前审核') : t('AI draft expired or changed · Factual fallback shown; return to factual wording to approve.','AI 草稿已过期或更改 · 显示事实性回退，请返回事实性措辞以批准。')}</p>}
        </details>
        {notice&&<p className="studio-notice" role="status">{notice}</p>}
        {changes.length>0&&<details className="studio-changes" open><summary>{t('What changed since your last check','您上次检查后的变更')}</summary><ul>{changes.map((change,index)=><li key={index}>{change}</li>)}</ul></details>}
        <div className="studio-desk"><section aria-label="Story review">
          <div className="studio-section-title"><h2>1. Review the story</h2><span>{checked ? 'Latest check complete' : 'Checking current evidence…'}</span></div>
          {review ? <><p className="studio-review-context">Eastbridge × Northport <span>Facts through <strong>{clock(review.recap.cutoff.elapsed_ms)}</strong></span></p>
            {review.recap.statements.length ? review.recap.statements.map(({ narrative: n, citation: c }) => <article className="studio-story" key={c.insight_id} lang={n.language}>
              <p className="studio-eyebrow">{n.subject_name} / {c.kind}</p><h3>{n.title}</h3><p>{n.explanation}</p><p className="studio-qualification">{n.qualification}</p>
              <details><summary>Check supporting evidence · revision {c.revision}</summary><p>{review.recap.windows.map(windowLabel).join(' → ')} · Start excluded, end included.</p><dl><dt>Evidence</dt><dd>{c.evidence_id}</dd><dt>Insight</dt><dd>{c.insight_id}</dd><dt>Available from</dt><dd>{clock(c.available_at.elapsed_ms)}</dd></dl>
                {review.evidence.filter(e => e.evidence_id === c.evidence_id && e.revision === c.revision).map(e => <div key={e.evidence_id}>
                  <p>{e.definition}</p><p>Pitch: 105 × 68 metres. The actor’s team attacks towards increasing x.</p>
                  <div className="studio-events"><table><caption>Supporting recorded events · {e.records.length} records</caption><thead><tr><th>Match time</th><th>Player</th><th>Action</th><th>Position (m)</th><th>Event / revision</th></tr></thead>
                    <tbody>{e.records.map(event => <tr key={`${event.event_id}:${event.revision}`}><td>{clock(event.occurred_at.elapsed_ms)}</td><td>{playerName(event.actor.player_id)}</td><td>{event.action.kind.replaceAll('_', ' ')}</td><td>{event.position.x}, {event.position.y}</td><td>{event.event_id} / {event.revision}</td></tr>)}</tbody></table></div>
                </div>)}</details>
            </article>) : <div className="studio-story"><h3>{t('No supported story in this view','此视图中没有支持的故事')}</h3><p>{t('There is nothing to approve. Choose another story or wait for new evidence.','没有可批准的内容。请选择另一个故事或等待新证据。')}</p></div>}
          </> : <p>{error ? t('Refresh evidence to continue.','刷新证据以继续。') : t('Loading the latest story…','正在加载最新故事…')}</p>}
        </section><aside className="studio-approval"><p className="studio-eyebrow">{t('REVIEW STATUS','审核状态')}</p><h2>{t('2. Approve this version','2. 批准此版本')}</h2>
          <p className={`studio-status ${approved ? 'is-approved' : ''}`} role="status">{busy ? t('Saving and checking…','正在保存并检查…') : !checked ? t('Approval not verified','批准未验证') : attemptId && review?.status === 'unavailable' ? t('AI approval expired or changed','AI 批准已过期或更改') : review ? statusText[review.status] : t('Waiting for evidence','等待证据')}</p>
          <p>{t('Approval covers the displayed wording, evidence revisions, language and detail level. New source events or AI expiry require a fresh review.','批准涵盖显示的措辞、证据修订、语言和详细程度。新的源事件或 AI 过期需要重新审核。')}</p>
          {approved ? <button disabled={!approved} onClick={() => void act('revoke')}>{t('Revoke this approval','撤销此批准')}</button> : <button className="studio-primary" disabled={!ready} onClick={() => void act('approve')}>{t('I reviewed this version · Approve','我已审核此版本 · 批准')}</button>}
          <hr /><h2>{t('3. Prepare your snapshot','3. 准备您的快照')}</h2><p>{t('Preview and export unlock after approval. Neither sends content to a broadcast system.','批准后可解锁预览和导出。两者都不会将内容发送到广播系统。')}</p>
          <button disabled={!approved} onClick={() => setPreview(p => !p)}>{preview ? t('Close clean preview','关闭简洁预览') : t('Open clean preview','打开简洁预览')}</button>
          <button disabled={!approved} onClick={() => void act('export')}>{t('Download approved snapshot','下载已批准的快照')}</button>
          <p className="studio-muted">{t('Downloads are static HTML. Recheck Studio before use; later changes cannot recall a downloaded file.','下载文件为静态 HTML。使用前请重新检查工作室；后续更改无法召回已下载的文件。')}</p>
        </aside></div>
        {review && <Broadcast key={review.fingerprint} review={review} enabled={Boolean(approved)} download={selection => void act('export', selection)} copy={selection=>void act('copy',selection)} />}
        {preview && approved && review && <section className="studio-preview" aria-label="Approved clean preview"><p className="studio-eyebrow">{t('FOOTIE / APPROVED SNAPSHOT','FOOTIE / 已批准的快照')}</p><p>{t('Synthetic football · Facts through ','合成足球 · 数据截至 ')}{clock(review.recap.cutoff.elapsed_ms)}</p>
          {review.recap.statements.map(s => <article key={s.citation.insight_id} lang={s.narrative.language}><h2>{s.narrative.title}</h2><p>{s.narrative.explanation}</p><p>{s.narrative.qualification}</p><small>{t('Evidence revision ','证据修订 ')}{s.citation.revision}</small></article>)}<p>{t('Preview only · Revalidated every five seconds while this page is active.','仅供预览 · 页面活跃时每五秒重新验证。')}</p></section>}
        </div></div>
      </>}
      <footer className="studio-footer"><span>{t('Synthetic football · Fictional clubs and players. AI editing runs only when requested.','合成足球 · 虚构俱乐部和球员。AI 编辑仅在请求时运行。')}</span><a href={`${window.location.search}#analysis`}>{t('Evidence desk ↗','证据工作台 ↗')}</a></footer>
    </main>
  </div>
}
