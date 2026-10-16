import type { ContributionView } from './types'
import { clock, windowLabel } from './types'

export function ContributionCard({ view, open, onToggle }: { view: ContributionView; open: boolean; onToggle: () => void }) {
  const publication = view.publication, variant = view.variant
  if (!publication || !variant || publication.operation === 'withdraw') return null
  const e = publication.evidence
  const t = (en: string, zh: string) => view.preferences.language === 'zh-Hans' ? zh : en
  const percent = (share: number | null) => share === null ? '—' : `${(100*share).toFixed(1)}%`
  const own = new Set(view.highlighted_events.map(ref => `${ref.event_id}:${ref.revision}`))
  const sources = new Set([...e.baseline.team_events, ...e.current.team_events].map(ref => `${ref.event_id}:${ref.revision}`))
  return <article className="insight-card contribution-card" aria-labelledby="contribution-title">
    <div className="card-eyebrow"><span className="signal-dot"/>{t('PLAYER CONTRIBUTION', '球员贡献')}<span className="fact-tag">{t('RECORDED SHARE', '记录占比')}</span></div>
    <h2 id="contribution-title">{variant.title}</h2>
    <p className="subject-label">{variant.subject_name}</p>
    <div className="comparison" aria-label={`${e.baseline.player_count}/${e.baseline.team_count} to ${e.current.player_count}/${e.current.team_count}`}>
      <div><strong>{percent(e.baseline.share)}</strong><span>{e.baseline.player_count} / {e.baseline.team_count} {t('team recoveries', '次球队夺回球权')}</span><small>{windowLabel(e.baseline.window)}</small></div>
      <span className="comparison-arrow" aria-hidden="true">→</span>
      <div className="current-count"><strong>{percent(e.current.share)}</strong><span>{e.current.player_count} / {e.current.team_count} {t('team recoveries', '次球队夺回球权')}</span><small>{windowLabel(e.current.window)}</small></div>
    </div>
    <p className="explanation">{variant.explanation}</p><p className="qualification">{variant.qualification}</p><p className="audience-note">{view.message}</p>
    <button className="evidence-button" aria-expanded={open} aria-controls="contribution-evidence" onClick={onToggle}>{open ? t('Hide evidence', '隐藏证据') : t('Show evidence', '查看证据')}<span aria-hidden="true">{open ? '−' : '↗'}</span></button>
    {open && <section id="contribution-evidence" aria-label="Player contribution evidence" className="pressure-evidence">
      <h3>{t('Recovery attribution', '夺回球权归属')} · {t('revision', '修订')} {publication.revision}</h3>
      <p className="qualification">{t('Open-play established control at x ≥ 70 m. Windows exclude the start and include the end.', '运动战中在 x ≥ 70 米处建立控球；时段不含起点、包含终点。')}</p>
      <div className="table-scroll"><table><caption>{t('Player and team counts', '球员与球队计数')}</caption><thead><tr><th>{t('Window', '时段')}</th><th>{t('Player', '球员')}</th><th>{t('Team', '球队')}</th><th>{t('Share', '占比')}</th></tr></thead><tbody>{[e.baseline,e.current].map(w => <tr key={w.window.start.elapsed_ms}><td>{windowLabel(w.window)}</td><td>{w.player_count}</td><td>{w.team_count}</td><td>{percent(w.share)}</td></tr>)}</tbody></table></div>
      <p className="qualification">{t('Eligibility', '资格阈值')}: ≥ {e.policy.minimum_team_recoveries} {t('team recoveries per window', '次球队夺回球权／时段')} · ≥ {e.policy.minimum_current_player_recoveries} {t('current player recoveries', '次球员后时段夺回球权')} · +{e.policy.minimum_count_increase} {t('player recoveries', '次球员夺回球权')} · +{e.policy.minimum_share_increase*100} {t('percentage points', '个百分点')}</p>
      <div className="episode-list">{e.records.filter(event => sources.has(`${event.event_id}:${event.revision}`)).map(event => <details className="source-detail" key={`${event.event_id}:${event.revision}`}><summary>{event.event_id}@r{event.revision} · {event.actor.player_id} · {clock(event.occurred_at.elapsed_ms)} · {own.has(`${event.event_id}:${event.revision}`) ? t('Attributed to this player', '归属该球员') : t('Team denominator only', '仅计入球队分母')}</summary><pre>{JSON.stringify(event,null,2)}</pre></details>)}</div>
      {view.preferences.depth === 'analyst' && <details className="pressure-provenance"><summary>{t('Evidence provenance', '证据来源')}</summary><p>{publication.evidence_id} · v{publication.revision} · {e.rule_version} · {t('Available', '可用时间')} {clock(publication.available_at.elapsed_ms)}</p></details>}
    </section>}
  </article>
}
