import type { Event } from '../types'
import { recipient } from '../matchday/pitchScene'

type Copy = [string, string]
export type Phase = { title: Copy; explanation: Copy; ids: string[] }
/** Editorial readings of specific recorded actions, not tracking-derived tactical claims. */
export const highlightPhases: Record<string, Phase[]> = {
  'last-gasp': [
    {title:['Keep the chance alive','守住希望'], explanation:['Ashford saves the penalty and the follow-up. Rowan then takes control of the loose ball, giving Eastbridge a way out.', 'Ashford连续扑出点球和补射，Rowan控制住落点，为Eastbridge找到出球机会。'], ids:['lg-penalty','lg-rebound','lg-recovery']},
    {title:['Take it down the wing','从边路推进'], explanation:['Rowan finds Mercer, who carries forward before releasing Hart. Hart takes the ball farther up the wing.', 'Rowan传给Mercer，后者带球向前，再分给Hart沿边路推进。'], ids:['lg-outlet','lg-break','lg-wide-pass','lg-wing-run']},
    {title:['Find the finish','完成最后一击'], explanation:['Hart crosses to Vale. His headed lay-off finds Ellis, who finishes the move with a goal.', 'Hart传中找到Vale，后者头球摆渡给Ellis完成破门。'], ids:['lg-cross','lg-knockdown','lg-winner']},
  ],
  'one-touch': [
    {title:['Bring the ball under control','控制住球'], explanation:['Ellis carries the ball before bringing Rowan into the move.', 'Ellis先带球控制局面，随后与Rowan展开配合。'], ids:['ot-control','ot-layoff']},
    {title:['Give it and get it back','传出，再接回'], explanation:['Rowan passes to Vale, whose return ball finds Ellis closer to goal.', 'Rowan传给Vale，Vale再找到更靠近球门的Ellis。'], ids:['ot-link','ot-return']},
    {title:['Finish the combination','完成配合'], explanation:['Ellis finishes from inside the penalty area after receiving Vale’s pass.', 'Ellis接到Vale传球后，在禁区内完成射门得分。'], ids:['ot-finish']},
  ],
  breakaway: [
    {title:['Release the attack','发动进攻'], explanation:['West finds Ellis, who sends the next pass forward to Mercer.', 'West找到Ellis，后者随即向前传给Mercer。'], ids:['ba-release','ba-through']},
    {title:['Carry, then switch the angle','推进后改变角度'], explanation:['Mercer carries towards the box, then passes across to Hart on the other side.', 'Mercer带球接近禁区，再横传另一侧的Hart。'], ids:['ba-run','ba-square']},
    {title:['Meet the final ball','迎接最后一传'], explanation:['Hart receives the final pass and scores from inside the penalty area.', 'Hart接到最后一传，在禁区内破门。'], ids:['ba-finish']},
  ],
}
export function phaseRecords(phase: Phase, events: Event[]) {
  return events.filter(e => phase.ids.includes(e.event_id))
}
export function availablePhases(story: string, events: Event[]) {
  const phases = highlightPhases[story] ?? []
  return phases.every(p => p.ids.every(id => events.some(e => e.event_id === id && e.revision === 1 && e.match_id === `showcase-${story}-v1`))) ? phases : []
}
export function keeper(event: Event): string | null {
  const value = event.action.goalkeeper
  return value && typeof value === 'object' && 'player_id' in value && typeof value.player_id === 'string' ? value.player_id : null
}
export function involvedIn(event: Event, player: string) {
  return event.actor.player_id === player || recipient(event) === player || keeper(event) === player
}
export function participants(events: Event[]) {
  return [...new Set(events.flatMap(e => [e.actor.player_id, recipient(e), keeper(e)].filter((id): id is string => !!id)))]
}
export function actionCounts(events: Event[]) {
  return [events.filter(e=>e.action.kind==='pass').length, events.filter(e=>e.action.kind==='carry').length,
    events.filter(e=>e.action.kind==='shot').length, events.filter(e=>e.action.kind==='shot' && e.action.outcome==='saved').length]
}
