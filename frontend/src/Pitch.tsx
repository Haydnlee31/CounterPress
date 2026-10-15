import type { Evidence } from './types'

export function Pitch({ evidence, selected, onSelect, language = 'en' }: { evidence: Evidence | null; selected: string | null; onSelect: (id: string) => void; language?: 'en' | 'zh-Hans' }) {
  const t = (en: string, zh: string) => language === 'zh-Hans' ? zh : en
  const baseline = new Set(evidence?.packet.baseline.source_events.map(ref => ref.event_id))
  return <section className="pitch-panel" aria-labelledby="pitch-title">
    <div className="panel-heading"><div><span className="eyebrow">{t('THE PLAYING FIELD', '球场视图')}</span><h2 id="pitch-title">{t('Where control was recovered', '在哪里夺回球权')}</h2></div><span className="pitch-scale">105 × 68 m</span></div>
    <div className="pitch-wrap">
      <div className="attack-direction">{t('EASTBRIDGE ATTACKING', 'Eastbridge 进攻方向')} <span aria-hidden="true">⟶</span></div>
      <svg className="pitch" viewBox="-4 -4 113 76" role="group" aria-label={evidence ? `Recovery locations: ${evidence.packet.baseline.value} baseline and ${evidence.packet.current.value} current.` : 'Football pitch. Recovery markers appear when a supported comparison is available.'}>
        <defs><pattern id="grass" width="17.5" height="68" patternUnits="userSpaceOnUse"><rect width="8.75" height="68" fill="#ffffff" opacity=".018"/></pattern></defs>
        <rect width="105" height="68" fill="#1a2b21" rx=".5"/><rect width="105" height="68" fill="url(#grass)"/>
        <rect x="70" width="35" height="68" fill="#c2ee79" opacity=".075"/>
        <g fill="none" stroke="#78907c" strokeWidth=".25" opacity=".7">
          <rect width="105" height="68"/><path d="M52.5 0V68"/><circle cx="52.5" cy="34" r="9.15"/>
          <path d="M0 13.84H16.5V54.16H0 M105 13.84H88.5V54.16H105 M0 24.84H5.5V43.16H0 M105 24.84H99.5V43.16H105"/>
          <path d="M16.5 26.7 Q23.5 34 16.5 41.3 M88.5 26.7 Q81.5 34 88.5 41.3"/>
          <path d="M0 30.34H-1.8V37.66H0 M105 30.34H106.8V37.66H105"/>
        </g>
        <g fill="#78907c"><circle cx="52.5" cy="34" r=".4"/><circle cx="11" cy="34" r=".35"/><circle cx="94" cy="34" r=".35"/></g>
        <path d="M70 0V68" stroke="#c2ee79" strokeDasharray="1 1.2" strokeWidth=".28" opacity=".55"/>
        <text x="87.5" y="8" textAnchor="middle" fill="#b7ca9d" fontSize="2" letterSpacing=".3">{t('ATTACKING THIRD', '进攻三区')}</text>
        {evidence?.records.map((event, index) => {
          const isBaseline = baseline.has(event.event_id)
          const source = isBaseline ? evidence!.packet.baseline.source_events : evidence!.packet.current.source_events
          const ordinal = source.findIndex(ref => ref.event_id === event.event_id) + 1
          const label = `${isBaseline ? 'B' : 'C'}${ordinal}`
          const labelY = event.position.y - 6 - index * 3
          const color = isBaseline ? '#9ed8e5' : '#c4f27d'
          return <g key={event.event_id} className="marker" role="button" tabIndex={0} aria-label={`${label}, ${event.event_id}, x ${event.position.x}, y ${event.position.y}`} onClick={() => onSelect(event.event_id)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(event.event_id) } }}>
            <title>{event.event_id}: ({event.position.x}, {event.position.y}) metres</title>
            <circle cx={event.position.x} cy={event.position.y} r="2.2" fill="transparent"/>
            {selected === event.event_id && <circle cx={event.position.x} cy={event.position.y} r="2" fill="none" stroke={color} strokeWidth=".3"/>}
            <line x1={event.position.x} x2={event.position.x} y1={event.position.y - 1.3} y2={labelY + 1} stroke={color} strokeWidth=".2" opacity=".6"/>
            <circle cx={event.position.x} cy={event.position.y} r=".95" fill={isBaseline ? '#1a2b21' : color} stroke={color} strokeWidth=".35"/>
            <text x={event.position.x} y={labelY} fill={color} textAnchor="middle" fontSize="2" fontWeight="600">{label}</text>
          </g>
        })}
        {!evidence && <text x="52.5" y="62" fill="#b2c2b4" textAnchor="middle" fontSize="2.4">{t('Waiting for an eligible comparison', '等待符合条件的比较')}</text>}
      </svg>
    </div>
    <div className="pitch-legend"><span><i className="legend-dot baseline"/> Previous window</span><span><i className="legend-dot current"/> Latest window</span><span className="legend-note">{t('Recorded locations · No inferred movement', '记录的位置 · 不推断移动轨迹')}</span></div>
  </section>
}
