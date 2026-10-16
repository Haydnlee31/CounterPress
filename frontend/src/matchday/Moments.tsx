import { useEffect, useRef, useState } from 'react'
import type { Preferences } from '../types'
import { clock, windowLabel } from '../types'
import type { Story } from './stories'
import { clubName, playerName } from './identity'

export function Moments({
  story,
  language,
  onClose,
}: {
  story: Story
  language: Preferences['language']
  onClose: () => void
}) {
  const [selected, setSelected] = useState<string | null>(null)
  const title = useRef<HTMLHeadingElement>(null)
  const t = (en: string, zh: string) => (language === 'zh-Hans' ? zh : en)
  useEffect(() => {
    title.current?.focus()
  }, [story.key])
  const records = [...story.records].sort(
    (a, b) => a.occurrence_order - b.occurrence_order,
  )
  const event = records.find((e) => e.event_id === selected) ?? records[0]
  const actions: Record<string, string> = {
    recovery: t('Won the ball', '夺回球权'),
    pass: t('Pass', '传球'),
    duel: t('Contested the ball', '争抢球权'),
    carry: t('Carried the ball', '带球'),
    pressure: t('Recorded pressure event', '记录的压迫事件'),
  }
  return (
    <section className="fan-moments" aria-labelledby="moments-heading">
      <div className="fan-section-heading">
        <div>
          <p className="fan-kicker">
            {t('THE MOMENTS BEHIND THE STORY', '故事背后的事件')}
          </p>
          <h2 id="moments-heading" tabIndex={-1} ref={title}>
            {t('See it for yourself', '亲自查看')}
          </h2>
        </div>
        <button className="fan-secondary" onClick={onClose}>
          {t('Close moments', '关闭事件')}
        </button>
      </div>
      <p>
        {t('Earlier', '前一时段')} {windowLabel(story.windows[0])} ·{' '}
        {t('Later', '后一时段')} {windowLabel(story.windows[1])}.{' '}
        {t(
          'Each comparison excludes its start and includes its end.',
          '每个比较时段均不含起点、包含终点。',
        )}
      </p>
      <div className="fan-moment-grid">
        <ol className="fan-event-list">
          {records.map((record) => (
            <li key={`${record.event_id}:${record.revision}`}>
              <button
                aria-pressed={event?.event_id === record.event_id}
                onClick={() => setSelected(record.event_id)}
              >
                <time>
                  {clock(
                    record.occurred_at.elapsed_ms,
                    record.occurred_at.period,
                  )}
                </time>
                <span>
                  <strong>{playerName(record.actor.player_id)}</strong>
                  <small>
                    {actions[record.action.kind] ??
                      t('Recorded event', '记录事件')}{' '}
                    · {clubName(record.actor.team_id)}
                  </small>
                </span>
                <span aria-hidden="true">↗</span>
              </button>
            </li>
          ))}
        </ol>
        <div className="fan-event-preview">
          {event && (
            <>
              <p className="fan-kicker">
                {playerName(event.actor.player_id)} ·{' '}
                {clock(event.occurred_at.elapsed_ms, event.occurred_at.period)}
              </p>
              <svg
                viewBox="-3 -3 111 74"
                role="img"
                aria-label={`${t('Recorded location', '记录位置')}: ${event.position.x}, ${event.position.y} m`}
              >
                <rect width="105" height="68" fill="#1e392a" rx="1" />
                <rect
                  x="70"
                  width="35"
                  height="68"
                  fill="#c4ed91"
                  opacity=".08"
                />
                <g fill="none" stroke="#92ad98" strokeWidth=".4">
                  <rect width="105" height="68" />
                  <path d="M52.5 0v68 M0 14h16.5v40H0 M105 14H88.5v40H105" />
                  <circle cx="52.5" cy="34" r="9.15" />
                </g>
                <circle
                  cx={event.position.x}
                  cy={event.position.y}
                  r="3"
                  fill="#e0f5ac"
                  stroke="#10251a"
                  strokeWidth="1"
                />
              </svg>
              <p>
                {t(
                  'Recorded event illustration · 105 × 68 m.',
                  '记录事件示意图 · 105 × 68 米。',
                )}
                <br />
                {t(
                  'This player’s team attacks to the right. No inferred movement or match footage.',
                  '该球员的球队向右进攻。不推断移动轨迹，非比赛录像。',
                )}
              </p>
              <details>
                <summary>{t('Technical details', '技术详情')}</summary>
                <p>
                  {event.event_id} · {t('revision', '修订')} {event.revision}
                </p>
                <pre tabIndex={0}>{JSON.stringify(event, null, 2)}</pre>
              </details>
            </>
          )}
        </div>
      </div>
      <details className="fan-provenance">
        <summary>
          {t('Full evidence and counting rules', '完整证据与计数规则')}
        </summary>
        <p>
          {story.citation.evidence_id} · {t('revision', '修订')}{' '}
          {story.citation.revision}
        </p>
        <pre tabIndex={0}>{JSON.stringify(story.raw, null, 2)}</pre>
      </details>
    </section>
  )
}
