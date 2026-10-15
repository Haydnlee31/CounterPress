import type { PressureView } from './types'
import { clock, windowLabel } from './types'

export function PressureCard({ view, open, onToggle }: { view: PressureView; open: boolean; onToggle: () => void }) {
  const publication = view.publication, variant = view.variant
  if (!publication || !variant || publication.operation === 'withdraw') return null
  const { decision: d, evidence: e } = publication
  const progression = d.metric === 'possession_without_progression'
  const t = (en: string, zh: string) => view.preferences.language === 'zh-Hans' ? zh : en
  const percent = (n: number, total: number) => total ? `${(100 * n / total).toFixed(1)}%` : '—'
  const highlights = new Set(view.highlighted_events.map(ref => `${ref.event_id}:${ref.revision}`))
  return <article className="insight-card pressure-card" aria-labelledby="pressure-title">
    <div className="card-eyebrow"><span className="signal-dot"/>{progression ? t('POSSESSION INSIGHT', '控球洞察') : t('BUILD-UP INSIGHT', '组织进攻洞察')}<span className="fact-tag">{t('OBSERVED RATE', '观测比例')}</span></div>
    <h2 id="pressure-title">{variant.title}</h2><p className="subject-label">{variant.subject_name} · {progression ? t('OBSERVED FORWARD GAIN', '观测向前推进') : t('DEFENSIVE THIRD', '防守三区')}</p>
    <div className="comparison" aria-label={`${d.baseline_numerator}/${d.baseline_denominator} to ${d.current_numerator}/${d.current_denominator}`}>
      <div><strong>{percent(d.baseline_numerator, d.baseline_denominator)}</strong><span>{d.baseline_numerator} / {d.baseline_denominator} {t('episodes', '个过程')}</span><small>{windowLabel(e.baseline.window)}</small></div>
      <span className="comparison-arrow" aria-hidden="true">→</span>
      <div className="current-count"><strong>{percent(d.current_numerator, d.current_denominator)}</strong><span>{d.current_numerator} / {d.current_denominator} {t('episodes', '个过程')}</span><small>{windowLabel(e.current.window)}</small></div>
    </div>
    <p className="explanation">{variant.explanation}</p><p className="qualification">{variant.qualification}</p>
    <p className="audience-note">{view.message}</p>
    <button className="evidence-button" aria-expanded={open} aria-controls="pressure-evidence" onClick={onToggle}>{open ? t('Hide evidence', '隐藏证据') : t('Show evidence', '查看证据')}<span aria-hidden="true">{open ? '−' : '↗'}</span></button>
    {open && <section id="pressure-evidence" aria-label={progression ? 'Possession evidence' : 'Pressure evidence'} className="pressure-evidence">
      <h3>{t('Episode evidence', '过程证据')} · {t('revision', '修订')} {publication.revision}</h3>
      <p className="qualification">{t('Windows exclude the start and include the end. Both episode endpoints must be inside.', '时段不含起点、包含终点；过程的开始和结束均须在时段内。')}</p>
      <div className="table-scroll"><table><caption>{t('Samples and exclusions', '样本与排除项')}</caption><thead><tr><th>{t('Window', '时段')}</th><th>{t('Complete', '完整')}</th><th>{progression ? t('No progression', '未推进') : t('Exposed', '受压')}</th><th>{t('Boundary', '跨界')}</th><th>{t('Unknown start', '起点未知')}</th><th>{t('Pending', '待定')}</th>{progression && <><th>{t('Brief', '短暂')}</th><th>{t('Limited space', '空间不足')}</th></>}</tr></thead><tbody>{[e.baseline, e.current].map(w => <tr key={w.window.start.elapsed_ms}><td>{windowLabel(w.window)}</td><td>{w.completed}</td><td>{'exposed' in w ? w.exposed : w.without_progression_count}</td><td>{w.boundary_excluded.length}</td><td>{w.left_censored.length}</td><td>{w.pending.length}</td>{'brief_excluded' in w && <><td>{w.brief_excluded.length}</td><td>{w.limited_space.length}</td></>}</tr>)}</tbody></table></div>
      <p className="qualification">{t('Minimum per window', '每时段最小样本')}: {e.policy.minimum_episodes} · {t('Change threshold', '变化阈值')}: {e.policy.minimum_rate_change * 100} {t('percentage points', '个百分点')}</p>
      {progression && <p className="qualification">{t('Sustained possession', '持续控球')}: ≥ {e.policy.minimum_completed_actions} {t('completed actions', '次完成动作')} · ≥ {(e.policy.minimum_controlled_span_ms ?? 0)/1000} s · {t('Progression', '推进')}: ≥ {e.policy.forward_gain_m} m</p>}
      <div className="episode-list">{e.episodes.map(episode => {
        const category = (w: typeof e.baseline) => w.included.includes(episode.episode_id) ? ('without_progression' in w && w.without_progression.includes(episode.episode_id) ? t('included: without progression','计入：未推进') : t('included', '计入')) : w.pending.includes(episode.episode_id) ? t('pending', '待定') : w.left_censored.includes(episode.episode_id) ? t('unknown start', '起点未知') : w.boundary_excluded.includes(episode.episode_id) ? t('boundary excluded', '跨界排除') : 'brief_excluded' in w && w.brief_excluded.includes(episode.episode_id) ? t('brief excluded','短暂排除') : 'limited_space' in w && w.limited_space.includes(episode.episode_id) ? t('limited space','空间不足') : '—'
        const refs = new Set(episode.source_events.map(ref => `${ref.event_id}:${ref.revision}`))
        const records = e.records.filter(event => refs.has(`${event.event_id}:${event.revision}`))
        const outcome = ({ escape: t('escape', '摆脱'), turnover: t('turnover', '失去球权'), restart: t('restart', '重新开球'), pending: t('pending', '待定') } as Record<string, string>)[episode.outcome]
        return <details key={episode.episode_id}><summary>{episode.episode_id} · {clock(episode.start.elapsed_ms)}–{episode.end ? clock(episode.end.elapsed_ms) : '…'} · {outcome}</summary>
          <p>{t('Baseline', '前时段')}: {category(e.baseline)} · {t('Current', '后时段')}: {category(e.current)}</p>
          {'pressure_events' in episode ? <p>{t('Pressure proxy events', '压迫代理事件')}: {episode.pressure_events.map(ref => `${ref.event_id}@r${ref.revision}`).join(', ') || '—'}</p> : <p>{t('Forward gain', '向前推进')}: {episode.forward_gain_m} m · x {episode.start_x} → {episode.maximum_x} {t('(maximum)', '（最远）')} · {episode.completed_actions} {t('completed actions', '次完成动作')} · {episode.controlled_span_ms/1000} s</p>}
          {records.map(event => <details className="source-detail" key={`${event.event_id}:${event.revision}`}><summary>{event.event_id}@r{event.revision} · {event.actor.player_id} · {event.action.kind}{view.preferences.player_id && highlights.has(`${event.event_id}:${event.revision}`) ? ` · ${t('selected player', '所选球员')}` : ''}</summary><pre>{JSON.stringify(event, null, 2)}</pre></details>)}
        </details>
      })}</div>
      {view.preferences.depth === 'analyst' && <details className="pressure-provenance"><summary>{t('Evidence provenance', '证据来源')}</summary><p>{publication.evidence_id} · v{publication.revision} · {e.rule_version} · {t('Available', '可用时间')} {clock(publication.available_at.elapsed_ms)}</p></details>}
    </section>}
  </article>
}
