import type {
  Event,
  Preferences,
  RecapCitation,
  Snapshot,
  Variant,
  Window,
} from '../types'
import { clubName, displayText } from './identity'
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
  raw: unknown
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
  return statements.flatMap<Story>(({ citation, narrative }) => {
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
          raw: e,
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
      return [
        {
          ...base,
          records: pub.evidence.records,
          windows: [
            pub.evidence.baseline.window,
            pub.evidence.current.window,
          ] as [Window, Window],
          before: `${d.baseline_numerator}/${d.baseline_denominator}`,
          after: `${d.current_numerator}/${d.current_denominator}`,
          unit:
            d.metric === 'pressure_exposure'
              ? zh
                ? '受压回合 / 观察到的后场组织回合'
                : 'pressured / observed build-up episodes'
              : d.metric === 'pressured_escape'
                ? zh
                  ? '成功摆脱 / 受压回合'
                  : 'successful escapes / pressured episodes'
                : zh
                  ? '未推进 / 持续控球回合'
                  : 'without progression / sustained possessions',
          subject: clubName(pub.evidence.subject_team_id),
          raw: pub.evidence,
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
    return [
      {
        ...base,
        records: e.records,
        windows: [e.baseline.window, e.current.window] as [Window, Window],
        before: `${e.baseline.player_count}/${e.baseline.team_count}`,
        after: `${e.current.player_count}/${e.current.team_count}`,
        unit: zh
          ? '球员前场夺回次数 / 球队前场夺回总数'
          : 'player high recoveries / team high recoveries',
        subject: clubName(e.subject_team_id),
        raw: e,
      },
    ]
  })
}
