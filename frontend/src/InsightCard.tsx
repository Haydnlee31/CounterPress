import { useEffect, useState } from 'react'
import type { Adaptation, Insight, Variant } from './types'
import { windowLabel } from './types'

export function InsightCard({ insight, adaptation, variant, open, onToggle }: { insight: Insight; adaptation?: Adaptation | null; variant?: Variant | null; open: boolean; onToggle: () => void }) {
  const narrative = variant?.insight_id === insight.insight_id && variant.revision === insight.revision ? variant : null
  const t = (en: string, zh: string) => narrative?.language === 'zh-Hans' ? zh : en
  const [, refreshExpiry] = useState(0)
  useEffect(() => {
    if (!adaptation) return
    const timer = window.setTimeout(() => refreshExpiry(value => value + 1), Math.max(0, adaptation.expires_at_unix_ms - Date.now()))
    return () => window.clearTimeout(timer)
  }, [adaptation])
  const approved = adaptation && adaptation.evidence_id === insight.evidence_id
    && adaptation.evidence_version === insight.evidence_version && Date.now() < adaptation.expires_at_unix_ms
  return <article className="insight-card" aria-labelledby="insight-title">
    <div className="card-eyebrow"><span className="signal-dot"/> {t('MATCH INSIGHT', '比赛洞察')} <span className="fact-tag">{t('FACT', '事实')}</span></div>
    <h2 id="insight-title">{narrative?.title ?? insight.title}</h2>
    <p className="subject-label">{narrative?.subject_name ?? 'EASTBRIDGE'} · {t('ATTACKING THIRD', '进攻三区')}</p>
    <div className="comparison" aria-label={`${insight.facts.baseline_count} to ${insight.facts.current_count} high recoveries`}>
      <div><strong>{insight.facts.baseline_count}</strong><span>{windowLabel(insight.facts.baseline_window)}</span><small>{t('Previous 5 minutes', '前 5 分钟')}</small></div>
      <span className="comparison-arrow" aria-hidden="true">→</span>
      <div className="current-count"><strong>{insight.facts.current_count}</strong><span>{windowLabel(insight.facts.current_window)}</span><small>{t('Latest 5 minutes', '后 5 分钟')}</small></div>
    </div>
    <p className="explanation">{narrative?.explanation ?? (approved ? adaptation.text : insight.explanation)}</p>
    <p className="qualification">{narrative?.qualification ?? 'A comparison of recorded recoveries. It does not establish a pressure pattern.'}</p>
    <button className="evidence-button" aria-expanded={open} aria-controls="evidence-panel" onClick={onToggle}>{open ? t('Hide evidence', '隐藏证据') : t('Show evidence', '查看证据')} <span aria-hidden="true">{open ? '−' : '↗'}</span></button>
  </article>
}
