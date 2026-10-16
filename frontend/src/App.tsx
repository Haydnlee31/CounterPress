import { useEffect, useRef, useState } from 'react'
import { fetchScenarios, fetchSnapshot } from './api'
import { clock, defaultPreferences } from './types'
import type { Preferences, Scenario, Snapshot } from './types'
import { InsightCard } from './InsightCard'
import { Pitch } from './Pitch'
import { EvidencePanel } from './EvidencePanel'
import { PlaybackScope } from './playbackScope'
import { WorkflowActivity } from './WorkflowActivity'
import { AudienceControls } from './AudienceControls'
import { EventSequence } from './EventSequence'
import { PressureCard } from './PressureCard'
import { ContributionCard } from './ContributionCard'
import { SegmentRecap } from './SegmentRecap'
import { subscribeRevisions } from './revisions'
import type { RevisionStatus } from './revisions'

const START = 180000, END = 780000

export default function App() {
  const [viewer, setViewer] = useState('one')
  const [profiles, setProfiles] = useState<Record<string, Preferences>>({ one: { ...defaultPreferences }, two: { ...defaultPreferences, depth: 'casual' } })
  const preferences = profiles[viewer]
  const [teams, setTeams] = useState<NonNullable<Snapshot['teams']>>([])
  const t = (en: string, zh: string) => preferences.language === 'zh-Hans' ? zh : en
  const [scenario, setScenario] = useState('increase')
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const [atMs, setAtMs] = useState(START)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(30)
  const [data, setData] = useState<Snapshot | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [retry, setRetry] = useState(0)
  const [revisionTick, setRevisionTick] = useState(0)
  const [revisionStatus, setRevisionStatus] = useState<RevisionStatus>('polling')
  const revisionStatusRef = useRef<RevisionStatus>('polling')
  revisionStatusRef.current = revisionStatus
  const [evidenceOpen, setEvidenceOpen] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [scope, setScope] = useState(() => new PlaybackScope())
  const [horizons, setHorizons] = useState<Record<string, number>>({})
  const replayEnd = horizons[scenario] ?? scenarios.find(item => item.scenario_id === scenario)?.end.elapsed_ms ?? END

  useEffect(() => {
    const controller = new AbortController()
    fetchScenarios(controller.signal).then(options => { if (!controller.signal.aborted) setScenarios(options) }).catch(() => {})
    return () => controller.abort()
  }, [retry])

  useEffect(() => subscribeRevisions(scenario, () => setRevisionTick(value => value + 1), setRevisionStatus), [scenario])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    let pending = false, lastRefresh = 0
    async function refresh() {
      if (pending) return
      pending = true
      lastRefresh = Date.now()
      try {
        const snapshot = await fetchSnapshot(scenario, atMs, controller.signal, scope.id, preferences)
        if (!controller.signal.aborted && scope.accept(snapshot)) {
          setData(snapshot); setError(''); setLoading(false)
          if (snapshot.teams) setTeams(snapshot.teams)
          setHorizons(values => values[scenario] === snapshot.replay_end.elapsed_ms ? values : { ...values, [scenario]: snapshot.replay_end.elapsed_ms })
        }
      } catch (reason) {
        if (!controller.signal.aborted) { setError(reason instanceof Error ? reason.message : 'Replay unavailable.'); setLoading(false); setData(null); setPlaying(false) }
      } finally { pending = false }
    }
    void refresh()
    const poll = window.setInterval(() => { if (revisionStatusRef.current !== 'connected' || Date.now() - lastRefresh >= 30000) void refresh() }, 2000)
    return () => { controller.abort(); window.clearInterval(poll) }
  }, [scenario, atMs, retry, scope, preferences, revisionTick])

  useEffect(() => {
    if (!playing) return
    let previous = performance.now()
    const interval = window.setInterval(() => {
      const now = performance.now(), elapsed = now - previous
      previous = now
      setAtMs(value => Math.min(replayEnd, value + Math.round(elapsed * speed)))
    }, 250)
    return () => window.clearInterval(interval)
  }, [playing, speed, replayEnd])

  useEffect(() => { if (atMs >= replayEnd) setPlaying(false) }, [atMs, replayEnd])

  // A backward seek or scenario switch must never render later/other-scope facts.
  const snapshot = data?.scope_id === scope.id && data.scenario_id === scenario && data.state.at.elapsed_ms <= atMs ? data : null
  const audience = snapshot?.audience
  const pressureSelected = snapshot?.selected_kind === 'pressure'
  const contributionSelected = snapshot?.selected_kind === 'contribution'
  const specialSelected = pressureSelected || contributionSelected
  const contributionScenario = scenario.startsWith('contribution-')
  const episodeScenario = scenario.startsWith('pressure-') || scenario.startsWith('progression-') || contributionScenario
  const episodeView = contributionScenario ? snapshot?.contribution : snapshot?.pressure
  const episodeWithdrawal = contributionScenario ? snapshot?.contribution_lifecycle?.some(change => change.operation === 'withdraw' && (!preferences.player_id || change.evidence.subject_player_id === preferences.player_id)) : snapshot?.pressure_lifecycle?.some(change => change.operation === 'withdraw')
  const visible = !specialSelected && (!audience || audience.state === 'ready')
  const insight = visible ? snapshot?.insight ?? null : null
  const sourceEvidence = visible ? snapshot?.evidence ?? null : null
  const ids = new Set(audience?.highlighted_events.map(ref => `${ref.event_id}:${ref.revision}`))
  const evidence = sourceEvidence && audience ? { ...sourceEvidence, records: sourceEvidence.records.filter(event => ids.has(`${event.event_id}:${event.revision}`)) } : sourceEvidence
  const factsAt = snapshot?.state.at.elapsed_ms
  function seek(value: number) { setPlaying(false); setEvidenceOpen(false); setSelected(null); setAtMs(value); setData(null); setScope(new PlaybackScope()) }
  function changePreferences(value: Preferences) { setProfiles(previous => ({ ...previous, [viewer]: value })); seek(atMs) }
  function changeViewer(value: string) { setViewer(value); seek(atMs) }
  function reset() { seek(START) }
  function togglePlay() { if (atMs >= replayEnd) reset(); setPlaying(value => !value) }
  function selectEvent(id: string) { setSelected(id); setEvidenceOpen(true) }
  function changeScenario(value: string) { setScenario(value); reset() }

  return <div className="app-shell" lang={preferences.language}>
    <header className="topbar"><a className="brand" href="/" aria-label="CounterPress home"><span className="brand-mark" aria-hidden="true">↗</span>Counter<span>Press</span><span className="brand-period">.</span></a><div className="header-right"><span className="synthetic-label"><span/>{t('SYNTHETIC REPLAY', '模拟比赛回放')}</span><span className="local-label">{t('MATCH INTELLIGENCE', '比赛洞察')}</span></div></header>
    <main>
      <div className="page-heading"><div><p className="eyebrow">{t('BEYOND THE SCORELINE', '比分之外')}</p><h1>{t('Every phase tells a story.', '每个比赛阶段，都有迹可循。')}</h1><p className="page-description">{t('Follow the shift in play. See the events behind the insight.', '关注比赛变化，查看洞察背后的事件。')}</p></div><label className="scenario-label">{t('Replay scenario', '回放场景')}<select aria-label="Replay scenario" value={scenario} onChange={e => changeScenario(e.target.value)}>{scenarios.length ? scenarios.map(option => <option key={option.scenario_id} value={option.scenario_id}>{t(option.label, ({ increase: '夺回球权增加', 'stream-recovery': '实时夺回球权修订', control: '无增长对照', 'pressure-increase': '压迫与摆脱变化', 'pressure-control': '压迫与摆脱对照', 'progression-increase': '控球未推进', 'progression-control': '推进对照', 'contribution-increase': '球员夺回球权占比增加', 'contribution-control': '球员夺回球权占比对照' } as Record<string, string>)[option.scenario_id] ?? option.label)}</option>) : <><option key="increase" value="increase">Recovery increase</option><option key="control" value="control">No-increase control</option></>}</select></label></div>
      <AudienceControls preferences={preferences} teams={teams} viewer={viewer} onViewer={changeViewer} onChange={changePreferences}/>
      <section className="scoreboard" aria-label="Match scoreboard">
        <div className="team home"><span className="team-crest eastbridge" aria-hidden="true">EB</span><div><span className="team-caption">{t('HOME', '主队')}</span><h2>Eastbridge</h2></div></div>
        <div className="score-center"><div className="score"><span>{snapshot?.state.score.eastbridge ?? '–'}</span><span className="score-separator">:</span><span>{snapshot?.state.score.northport ?? '–'}</span></div><div className="match-clock"><span className={playing ? 'live-indicator running' : 'live-indicator'}/><time>{clock(atMs)}</time><span>{t('2ND HALF', '下半场')}</span></div></div>
        <div className="team away"><div><span className="team-caption">{t('AWAY', '客队')}</span><h2>Northport</h2></div><span className="team-crest northport" aria-hidden="true">NP</span></div>
        <div className="scoreboard-foot"><span>{t('Fictional match', '虚构比赛')} · 48:00–{clock(replayEnd)} {t('segment', '片段')}</span><span>{snapshot ? `${snapshot.state.applied_events.length} ${t('recorded events · Facts through', '条记录事件 · 数据截至')} ${clock(factsAt!)}` : t('Loading match state…', '正在加载比赛数据…')}</span></div>
      </section>
      {error && <div className="error-banner" role="alert"><span>{error}</span><button onClick={() => setRetry(value => value + 1)}>{t('Retry', '重试')}</button></div>}
      <section className="playback" aria-label="Replay controls"><div className="playback-buttons"><button className="play-button" onClick={togglePlay} disabled={!!error} aria-label={playing ? 'Pause replay' : 'Play replay'}>{playing ? 'Ⅱ' : '▶'}<span>{playing ? t('Pause', '暂停') : t('Play', '播放')}</span></button><button className="reset-button" onClick={reset} aria-label="Reset replay">↺</button></div><div className="timeline"><label className="sr-only" htmlFor="playhead">Match time</label><input id="playhead" aria-valuetext={clock(atMs)} type="range" min={START} max={replayEnd} step="1000" value={atMs} onChange={e => seek(Number(e.target.value))} style={{ '--progress': `${(atMs - START) / (replayEnd - START) * 100}%` } as React.CSSProperties}/><div className="timeline-labels"><span>48:00</span><span>53:00 <span className="window-split">· {t('Window split', '时段分界')}</span></span><span>{clock(replayEnd)}</span></div></div><label className="speed-label"><span className="sr-only">Playback speed</span><select aria-label="Playback speed" value={speed} onChange={e => setSpeed(Number(e.target.value))}><option value="1">1× speed</option><option value="10">10× speed</option><option value="30">30× speed</option><option value="60">60× speed</option></select></label></section>
      <p className="audience-note" role="status">{revisionStatus === 'connected' ? t('Live revision updates connected', '实时修订更新已连接') : t('Checking for updates periodically', '定期检查更新')}</p>
      {replayEnd > END && atMs < replayEnd && <button className="jump-button" onClick={() => seek(replayEnd)}>{t('View latest corrections', '查看最新修订')} · {clock(replayEnd)}</button>}
      <div className={`analysis-grid ${preferences.depth === 'casual' || specialSelected || episodeScenario ? 'casual-view' : ''}`}>{preferences.depth === 'analyst' && !specialSelected && !episodeScenario && <Pitch evidence={evidence} selected={selected} onSelect={selectEvent} language={preferences.language}/>}<div className="insight-column">
        {contributionSelected && snapshot?.contribution ? <ContributionCard key={`${snapshot.contribution.publication?.insight_id}:${snapshot.contribution.publication?.revision}`} view={snapshot.contribution} open={evidenceOpen} onToggle={() => setEvidenceOpen(value => !value)}/> : pressureSelected && snapshot?.pressure ? <PressureCard key={`${snapshot.pressure.publication?.insight_id}:${snapshot.pressure.publication?.revision}`} view={snapshot.pressure} open={evidenceOpen} onToggle={() => setEvidenceOpen(value => !value)}/> : insight ? <InsightCard insight={insight} adaptation={snapshot?.adaptation} variant={audience?.variant} open={evidenceOpen} onToggle={() => setEvidenceOpen(value => !value)}/> : <section className="empty-insight" aria-live="polite"><div className="card-eyebrow"><span className="signal-dot"/> {t('MATCH INSIGHT', '比赛洞察')}</div><span className="empty-icon" aria-hidden="true">{snapshot?.comparison_status === 'no_increase' ? '=' : '⌁'}</span><h2>{episodeScenario && snapshot?.comparison_status === 'no_increase' ? (episodeView?.state === 'budget_hidden' ? t('Cards hidden.', '卡片已隐藏。') : episodeWithdrawal ? t('Insight withdrawn.', '洞察已撤回。') : episodeView?.state === 'no_contribution' ? (contributionScenario ? t('No qualifying contribution.', '没有符合条件的贡献。') : t('No recorded involvement.', '没有记录的参与。')) : (contributionScenario ? t('No eligible player increase.', '没有符合条件的球员增长。') : t('No eligible rate change.', '没有符合条件的比例变化。'))) : audience?.state === 'no_contribution' ? t('No qualifying contribution.', '没有符合条件的贡献。') : audience?.state === 'budget_hidden' ? t('Cards hidden.', '卡片已隐藏。') : snapshot?.comparison_status === 'no_increase' ? (snapshot.lifecycle?.operation === 'withdraw' ? t('Insight withdrawn.', '洞察已撤回。') : t('No increase this time.', '本次没有增长。')) : t('Let the comparison unfold.', '等待比较时段结束。')}</h2><p>{(episodeScenario ? episodeView?.message : audience?.message) ?? (snapshot?.comparison_status === 'no_increase' ? 'Eastbridge’s latest window did not exceed the previous one. No increase card is eligible.' : 'Two five-minute windows. One clear comparison. The insight becomes eligible at 58:00.')}</p>{atMs < END && <button className="jump-button" onClick={() => seek(END)}>{t('Go to comparison', '前往比较时段')} <span aria-hidden="true">→</span></button>}<div className="empty-foot">{loading ? t('Updating match facts…', '正在更新比赛数据…') : snapshot?.comparison_status === 'no_increase' ? t('Evidence rules apply to every scenario.', '所有场景遵循同一证据规则。') : t('Only events available at this point are used.', '仅使用当前时刻可用的事件。')}</div></section>}
        {!specialSelected && audience?.state === 'ready' && <p className="audience-note">{audience.message}{preferences.depth === 'analyst' && insight && <><br/>{t('Supporting sample', '支持样本')}: {insight.facts.baseline_count} + {insight.facts.current_count} = {audience.supporting_event_count} {t('qualifying events; this is a count, not a rate.', '条符合条件的事件；这是计数，不是比率。')}</>}{preferences.player_id && <><br/>{t('Selected contributions', '所选贡献')}: {audience.selected_event_count} / {audience.supporting_event_count} · {t('Team totals stay unchanged.', '球队总数保持不变。')}</>}</p>}
        {preferences.depth === 'analyst' && !specialSelected && <WorkflowActivity workflow={snapshot?.workflow} language={preferences.language}/>}
        <div className="trust-note"><span aria-hidden="true">✓</span><p>{t('Calculated from recorded events.', '根据记录的事件计算。')}<br/><span>{t('Every displayed insight has inspectable evidence.', '每条洞察都有可查看的证据。')}</span></p></div>
      </div></div>
      {preferences.depth === 'analyst' && <section className="stats-strip" aria-label="Current match metrics"><div className="stats-label"><span className="eyebrow">{t('THIS REPLAY SEGMENT', '当前回放片段')}</span><h2>{t('Match in numbers', '比赛数据')}</h2></div>{snapshot?.metrics.map(metric => <div className="team-stats" key={metric.team_id}><h3>{metric.team_id === 'eastbridge' ? 'Eastbridge' : 'Northport'}</h3><div><span><strong>{metric.pass_completions}<small>/{metric.pass_attempts}</small></strong><em>{t('Passes completed', '传球成功')}</em></span><span><strong>{metric.high_recoveries.length}</strong><em>{t('High recoveries', '前场夺回球权')}</em></span></div></div>) ?? <p className="muted">{t('Waiting for match facts.', '等待比赛数据。')}</p>}</section>}
      {evidenceOpen && evidence && <EvidencePanel evidence={evidence} selected={selected} onSelect={selectEvent} language={preferences.language}/>}
      {preferences.depth === 'analyst' && !specialSelected && audience?.state === 'ready' && <EventSequence audience={audience}/>}
      {snapshot?.recap && <SegmentRecap key={`${scope.id}:${scenario}`} recap={snapshot.recap} adapted={snapshot.adapted_recap} workflow={snapshot.recap_workflow} scenario={scenario}/>}
      <footer><span>COUNTERPRESS <span className="footer-dot">/</span> {t('See the game. Understand the moment.', '看比赛，懂变化。')}</span><span>{t('Synthetic data · Evidence-backed comparisons', '模拟数据 · 基于证据的比较')}</span></footer>
    </main>
  </div>
}
