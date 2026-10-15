import type { Audience } from './types'
import { clock } from './types'

export function EventSequence({ audience }: { audience: Audience }) {
  if (!audience.sequence.length) return null
  const zh = audience.preferences.language === 'zh-Hans'
  const highlighted = new Set(audience.highlighted_events.map(ref => `${ref.event_id}:${ref.revision}`))
  const actions: Record<string, string> = { recovery: '夺回球权', pass: '传球', carry: '带球', duel: '争抢' }
  return <section className="event-sequence" aria-label={zh ? '事件序列' : 'Event sequence'}>
    <h2>{zh ? '夺回球权前后发生了什么' : 'The sequence around each recovery'}</h2>
    <p>{zh ? '标记的是符合条件的贡献；相邻事件仅提供上下文。' : 'Marked events are qualifying contributions; neighboring events provide context only.'}</p>
    <ol>{audience.sequence.map(event => <li key={`${event.event_id}:${event.revision}`} className={highlighted.has(`${event.event_id}:${event.revision}`) ? 'qualifying-event' : ''}>
      <time>{clock(event.occurred_at.elapsed_ms, event.occurred_at.period)}</time><strong>{event.event_id}</strong><span>{event.actor.player_id}</span><span>{zh ? actions[event.action.kind] ?? event.action.kind : event.action.kind}</span><span>r{event.revision}</span>
    </li>)}</ol>
  </section>
}
