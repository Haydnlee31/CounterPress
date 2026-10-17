import { useEffect, useRef, useState } from 'react'
import type { Preferences } from '../types'
import { clock, windowLabel } from '../types'
import type { Story } from './stories'
import { actionText } from './pitchScene'
import { MatchPitch } from './MatchPitch'

export function Moments({story,language,onClose}:{story:Story;language:Preferences['language'];onClose:()=>void}) {
  const [selected,setSelected]=useState<string|null>(null)
  const title=useRef<HTMLHeadingElement>(null)
  const t=(en:string,zh:string)=>language==='zh-Hans'?zh:en
  useEffect(()=>{title.current?.focus();setSelected(null)},[story.key])
  const records=[...story.records].sort((a,b)=>a.occurrence_order-b.occurrence_order)
  const event=records.find(e=>e.event_id===selected)??records[0]
  return <section className="fan-moments" aria-labelledby="moments-heading">
    <div className="fan-section-heading"><h2 id="moments-heading" tabIndex={-1} ref={title}>{t('See it for yourself','亲自查看')}</h2>
      <button className="fan-secondary" onClick={onClose}>{t('Close moments','关闭事件')}</button></div>
    <p>{t('Earlier','前一时段')} {windowLabel(story.windows[0])} · {t('Later','后一时段')} {windowLabel(story.windows[1])}</p>
    <div className="fan-moment-grid"><ol className="fan-event-list">{records.map(record=><li key={`${record.event_id}:${record.revision}`}>
      <button aria-pressed={event?.event_id===record.event_id} onClick={()=>setSelected(record.event_id)}>
        <time>{clock(record.occurred_at.elapsed_ms,record.occurred_at.period)}</time><strong>{actionText(record,language==='zh-Hans')}</strong><span aria-hidden="true">↗</span>
      </button></li>)}</ol>
      {event && <MatchPitch events={[event]} language={language} compact />}
    </div>
    <details className="fan-provenance"><summary>{t('How we counted it','这些数字怎么算')}</summary>
      <p>{story.narrative.explanation}</p>
      <p>{t(`We compared the plays in ${windowLabel(story.windows[0])} with ${windowLabel(story.windows[1])}.`, `我们比较了 ${windowLabel(story.windows[0])} 与 ${windowLabel(story.windows[1])} 两个时段。`)}</p>
    </details>
  </section>
}
