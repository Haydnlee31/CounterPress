import type { Evidence } from './types'
import { clock, windowLabel } from './types'

export function EvidencePanel({ evidence, selected, onSelect, language = 'en' }: { evidence: Evidence; selected: string | null; onSelect: (id: string) => void; language?: 'en' | 'zh-Hans' }) {
  const t = (en: string, zh: string) => language === 'zh-Hans' ? zh : en
  const baseline = new Set(evidence.packet.baseline.source_events.map(ref => ref.event_id))
  const event = evidence.records.find(record => record.event_id === selected)
  return <section id="evidence-panel" className="evidence-panel" aria-labelledby="evidence-title">
    <div className="panel-heading"><div><span className="eyebrow">{t('BEHIND THE INSIGHT', '洞察背后的证据')}</span><h2 id="evidence-title">{t('The events. The exact count.', '事件与准确计数')}</h2></div><span className="record-count">{evidence.records.length} / {evidence.packet.baseline.value + evidence.packet.current.value} {t('supporting events shown', '条支持事件已显示')}</span></div>
    <p className="definition">{t(evidence.metric_definition, '运动战中在本队进攻方向 x ≥ 70 m 处建立控球的事件；不含争抢和重新开球。')}</p>
    <div className="evidence-windows"><span>{t('Baseline', '前一时段')}: ({windowLabel(evidence.packet.baseline.window)}]</span><span>{t('Current', '后一时段')}: ({windowLabel(evidence.packet.current.window)}]</span><span>{t('Start excluded · End included', '不含起点 · 包含终点')}</span></div>
    <div className="table-scroll"><table><thead><tr><th>{t('Window', '时段')}</th><th>{t('Source event', '来源事件')}</th><th>{t('Match time', '比赛时间')}</th><th>{t('Player', '球员')}</th><th>{t('Position (m)', '位置 (m)')}</th><th>{t('Revision', '修订版本')}</th></tr></thead>
      <tbody>{evidence.records.map(record => <tr key={record.event_id} className={selected === record.event_id ? 'selected-row' : ''}>
        <td><span className={`window-badge ${baseline.has(record.event_id) ? 'baseline-badge' : ''}`}>{baseline.has(record.event_id) ? t('Baseline', '前一时段') : t('Current', '后一时段')}</span></td>
        <td><button className="event-button" onClick={() => onSelect(record.event_id)} aria-pressed={selected === record.event_id}>{record.event_id} <span aria-hidden="true">↗</span></button></td>
        <td>{clock(record.occurred_at.elapsed_ms, record.occurred_at.period)}</td><td>{record.actor.player_id}</td><td>{record.position.x}, {record.position.y}</td><td>r{record.revision}</td>
      </tr>)}</tbody></table></div>
    {event && <div className="raw-record"><h3>Source record · {event.event_id}</h3><p>Available at {clock(event.available_at.elapsed_ms)} · Controlled possession from {event.action.from_team_id} to {event.actor.team_id}.</p><pre tabIndex={0}>{JSON.stringify(event, null, 2)}</pre></div>}
    <details className="provenance"><summary>{t('Evidence provenance', '证据来源')}</summary><dl><dt>{t('Evidence ID', '证据 ID')}</dt><dd>{evidence.packet.evidence_id}</dd><dt>{t('Rule', '规则')}</dt><dd>{evidence.packet.rule_version}</dd><dt>{t('Evidence version', '证据版本')}</dt><dd>{evidence.packet.evidence_version}</dd><dt>{t('Cutoff', '截止时间')}</dt><dd>{clock(evidence.packet.cutoff.elapsed_ms)}</dd><dt>{t('Coordinates', '坐标')}</dt><dd>105 × 68 m; attacking direction normalized toward positive x.</dd></dl></details>
  </section>
}
