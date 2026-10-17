import { windowLabel } from '../types'
import type {
  Event,
  Preferences,
  RecapCitation,
  Snapshot,
  Variant,
  Window,
} from '../types'
import { clubName, displayText, playerName } from './identity'
export type Story = {
  key: string
  citation: RecapCitation
  narrative: Variant
  records: Event[]
  windows: [Window, Window]
  before: string
  after: string
  unit: string
  subject: string
}

/** Present only publications in the accepted snapshot. Never fetch a newer evidence revision separately. */
export function storiesFor(s: Snapshot, preferences: Preferences): Story[] {
  const statements =
    s.recap?.statements ??
    (s.insight && s.audience?.variant
      ? [
          {
            narrative: s.audience.variant,
            citation: {
              kind: 'recovery' as const,
              insight_id: s.insight.insight_id,
              revision: s.insight.revision,
              evidence_id: s.insight.evidence_id,
              available_at: s.insight.eligible_at,
            },
          },
        ]
      : [])
  const stories = statements.flatMap<Story>(({ citation, narrative }) => {
    const base = {
      key: `${citation.kind}:${citation.insight_id}`,
      citation,
      narrative: {
        ...narrative,
        title: displayText(narrative.title),
        explanation: displayText(narrative.explanation),
      },
    }
    const zh = preferences.language === 'zh-Hans'
    if (citation.kind === 'recovery') {
      const e = s.lifecycle?.evidence ?? s.evidence
      if (
        !e ||
        e.packet.evidence_version !== citation.revision ||
        e.packet.evidence_id !== citation.evidence_id ||
        s.lifecycle?.operation === 'withdraw'
      )
        return []
      const p = e.packet,
        subject = clubName(p.subject_team_id)
      const who =
        preferences.club_id === p.subject_team_id
          ? zh
            ? '你的球队'
            : 'Your team'
          : subject
      return [
        {
          ...base,
          subject,
          records: e.records,
          windows: [p.baseline.window, p.current.window] as [Window, Window],
          before: String(p.baseline.value),
          after: String(p.current.value),
          unit: zh ? '前场夺回球权' : 'balls won in the attacking third',
          narrative: {
            ...base.narrative,
            title: zh
              ? `${who}在前场更多地夺回球权`
              : `${who} are winning it back more often`,
            explanation: zh
              ? `${who}在后五分钟于进攻三区夺回球权 ${p.current.value} 次，前五分钟为 ${p.baseline.value} 次。`
              : `${who} won the ball in the attacking third ${p.current.value} times in the latest five minutes, compared with ${p.baseline.value} in the previous five.`,
          },
        },
      ]
    }
    if (citation.kind === 'pressure') {
      const pub = s.pressure_lifecycle?.find(
        (p) =>
          p.insight_id === citation.insight_id &&
          p.revision === citation.revision,
      )
      if (
        !pub ||
        pub.operation === 'withdraw' ||
        pub.evidence_id !== citation.evidence_id
      )
        return []
      const d = pub.decision
      const subject = clubName(pub.evidence.subject_team_id)
      const up = d.direction === 'increase'
      const titles = {
        pressure_exposure: zh ? (up ? '后场争抢变多了' : '后场争抢变少了') : (up ? 'More challenges close to their own goal' : 'Fewer challenges close to their own goal'),
        pressured_escape: zh ? (up ? '更常摆脱后场争抢' : '更难摆脱后场争抢') : (up ? 'Finding a way out more often' : 'Finding a way out less often'),
        possession_without_progression: zh ? (up ? '更多控球停留在原地附近' : '更少控球停留在原地附近') : (up ? 'More spells with little ground gained' : 'Fewer spells with little ground gained'),
      }
      const count = `${d.current_numerator} of ${d.current_denominator}`
      const previous = `${d.baseline_numerator} of ${d.baseline_denominator}`
      const explanations = {
        pressure_exposure: zh ? `${subject}最近五分钟的 ${d.current_denominator} 次后场组织中有 ${d.current_numerator} 次出现争抢，之前为 ${d.baseline_denominator} 次中的 ${d.baseline_numerator} 次。` : `${subject} faced a challenge in ${count} spells building from the back in the latest five minutes, compared with ${previous} before.`,
        pressured_escape: zh ? `${subject}最近五分钟在 ${d.current_denominator} 次后场受挑战的控球中，${d.current_numerator} 次成功带球走出后场，之前为 ${d.baseline_denominator} 次中的 ${d.baseline_numerator} 次。` : `${subject} got the ball out of their own third in ${count} spells that included a challenge, compared with ${previous} in the previous five minutes.`,
        possession_without_progression: zh ? `${subject}最近五分钟的 ${d.current_denominator} 次较长控球中有 ${d.current_numerator} 次向前推进不足15米，之前为 ${d.baseline_denominator} 次中的 ${d.baseline_numerator} 次。` : `${subject} gained less than 15 metres upfield in ${count} longer spells on the ball, compared with ${previous} in the previous five minutes.`,
      }
      const percent = (n: number, total: number) => total ? `${Math.round(100*n/total)}%` : '—'
      return [
        {
          ...base,
          records: pub.evidence.records,
          windows: [
            pub.evidence.baseline.window,
            pub.evidence.current.window,
          ] as [Window, Window],
          before: percent(d.baseline_numerator, d.baseline_denominator),
          after: percent(d.current_numerator, d.current_denominator),
          unit: d.metric === 'pressure_exposure' ? (zh ? '后场组织中出现争抢的比例' : 'spells challenged in their own third')
            : d.metric === 'pressured_escape' ? (zh ? '争抢后成功走出后场的比例' : 'challenged spells that got out of their own third')
            : (zh ? '向前推进不足15米的较长控球比例' : 'longer spells gaining less than 15 metres'),
          subject,
          narrative: { ...base.narrative, title: titles[d.metric], explanation: explanations[d.metric] },
        },
      ]
    }
    const pub = s.contribution_lifecycle?.find(
      (p) =>
        p.insight_id === citation.insight_id &&
        p.revision === citation.revision,
    )
    if (
      !pub ||
      pub.operation === 'withdraw' ||
      pub.evidence_id !== citation.evidence_id
    )
      return []
    const e = pub.evidence
    const player = playerName(e.subject_player_id)
    return [
      {
        ...base,
        records: e.records,
        windows: [e.baseline.window, e.current.window] as [Window, Window],
        before: String(e.baseline.player_count),
        after: String(e.current.player_count),
        unit: zh
          ? '球员在前场夺回球权'
          : 'balls won high up the pitch',
        subject: clubName(e.subject_team_id),
        narrative: { ...base.narrative,
          title: zh ? `${player}更多地在前场赢回球权` : `${player} is winning more balls back upfield`,
          explanation: zh ? `${player}在最近五分钟拿下球队 ${e.current.team_count} 次前场夺回中的 ${e.current.player_count} 次，之前为 ${e.baseline.team_count} 次中的 ${e.baseline.player_count} 次。` : `${player} made ${e.current.player_count} of ${clubName(e.subject_team_id)}’s ${e.current.team_count} ball wins in the attacking third in the latest five minutes, up from ${e.baseline.player_count} of ${e.baseline.team_count} before.`,
        },
      },
    ]
  })
  if (preferences.depth === 'analyst') return stories.map(story=>({ ...story, narrative:{ ...story.narrative,
    explanation: story.narrative.explanation + (preferences.language==='zh-Hans'
      ? ` 比较时段为 ${windowLabel(story.windows[0])} 和 ${windowLabel(story.windows[1])}。`
      : ` The two periods are ${windowLabel(story.windows[0])} and ${windowLabel(story.windows[1])}.`),
  }}))
  return stories
}
