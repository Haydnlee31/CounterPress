import { useEffect, useState } from 'react'
import type { RecapCitation, RecapWorkflow, SegmentRecap as Recap } from './types'
import { clock } from './types'
import { WorkflowActivity } from './WorkflowActivity'

export function evidenceUrl(scenario: string, citation: RecapCitation, atMs: number) {
  const base = `/api/scenarios/${encodeURIComponent(scenario)}`
  const path = citation.kind === 'recovery' ? '' : `/${citation.kind === 'pressure' ? 'pressure' : 'contributions'}/${encodeURIComponent(citation.insight_id)}`
  return `${base}${path}/evidence/${citation.revision}?at_ms=${atMs}`
}

export function SegmentRecap({ recap: factual, scenario, adapted, workflow }: {
  recap: Recap; scenario: string; adapted?: Recap | null; workflow?: RecapWorkflow | null
}) {
  const [, refreshExpiry] = useState(0)
  useEffect(() => {
    if (!workflow?.applied) return
    const timer = window.setTimeout(() => refreshExpiry(value => value + 1), Math.max(0, workflow.expires_at_unix_ms - Date.now()))
    return () => window.clearTimeout(timer)
  }, [workflow?.attempt_id, workflow?.applied, workflow?.expires_at_unix_ms])
  const applied = !!adapted && !!workflow?.applied && Date.now() < workflow.expires_at_unix_ms
  const recap = applied ? adapted! : factual
  const zh = recap.preferences.language === 'zh-Hans'
  const t = (en: string, chinese: string) => zh ? chinese : en
  if (recap.state === 'budget_hidden') return null
  return <details className="segment-recap">
    <summary><span>{t('Catch up on this segment', '回顾当前比赛片段')}</span><span className="recap-count">{recap.statements.length} {t('cited stories', '条附证据的洞察')}</span></summary>
    <div className="recap-body">
      <p className="eyebrow">{applied && workflow?.heading === 'key_changes' ? t('KEY CHANGES IN THIS SEGMENT', '当前片段的关键变化') : t('SYNTHETIC SEGMENT RECAP', '模拟比赛片段回顾')}</p>
      <h2>{clock(recap.windows[0].start.elapsed_ms)}–{clock(recap.windows[1].end.elapsed_ms)}</h2>
      <p className="recap-scope">{t('Available evidence through', '可用证据截至')} {clock(recap.cutoff.elapsed_ms)}. {t('A summary of eligible published comparisons, not the full match. Window starts are excluded; ends are included.', '仅总结已发布且符合条件的比较，不代表整场比赛。比较时段不含起点、包含终点。')}</p>
      {recap.state === 'collecting' ? <p>{t('Waiting for both comparison windows to finish at 58:00.', '等待两个比较时段于 58:00 结束。')}</p> : recap.state === 'no_eligible' ? <p>{t('No current eligible stories for this viewpoint. This does not mean nothing happened.', '当前视角没有符合条件的洞察，并不表示比赛中没有事件发生。')}</p> :
        <ol>{recap.statements.map(({ narrative: n, citation: c }) => <li key={c.insight_id}>
          <h3>{n.title}</h3><p>{n.explanation}</p><p className="recap-qualification">{n.qualification}</p>
          <a href={evidenceUrl(scenario, c, recap.cutoff.elapsed_ms)} target="_blank" rel="noreferrer">{t('Open cited evidence', '打开引用证据')} · {t('revision', '修订')} {c.revision} <span aria-hidden="true">↗</span></a>
        </li>)}</ol>}
      {recap.omitted_count > 0 && <p>{recap.omitted_count} {t('additional eligible stories omitted from this four-story recap.', '条符合条件的洞察未列入此最多四条的回顾。')}</p>}
      {workflow && <p className="recap-foot">{applied ? t('AI-assisted selection · Verified facts and citations retained.', 'AI 辅助选择 · 保留已验证的事实与引用。') : t('Factual recap shown · No current validated adaptation.', '显示事实回顾 · 当前没有有效的改写。')}</p>}
      {workflow && recap.preferences.depth === 'analyst' && <WorkflowActivity workflow={workflow} language={recap.preferences.language}/>}
      <p className="recap-foot">{t('Corrections update or remove dependent statements. Evidence links open the exact cited revision as JSON in a new tab.', '修订会更新或移除相关陈述。证据链接在新标签页中打开所引用修订的 JSON 数据。')}</p>
    </div>
  </details>
}
