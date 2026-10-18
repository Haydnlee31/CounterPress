import type { Event } from '../types'
import { clubName, playerName } from '../matchday/identity'
import { actionText } from '../matchday/pitchScene'

export type Question = 'happened' | 'buildup' | 'numbers'
const time = (e: Event, available = false) => {
  const t = available ? e.available_at : e.occurred_at
  return t.period * 10_000_000 + t.elapsed_ms
}

/** Presentation order and source availability are separate gates. Never consult later plays. */
export function completedEvents(events: Event[], index: number, resolved: boolean): Event[] {
  const prefix = events.slice(0, Math.max(0, index + (resolved ? 1 : 0)))
  const cutoff = prefix.at(-1)
  if (!cutoff) return []
  const latest = new Map<string, Event>()
  for (const e of prefix) {
    if (e.match_id !== cutoff.match_id || time(e) > time(cutoff) || time(e, true) > time(cutoff)) continue
    const previous = latest.get(e.event_id)
    if (!previous || e.revision > previous.revision) latest.set(e.event_id, e)
  }
  return [...latest.values()].sort((a,b) => a.occurrence_order - b.occurrence_order)
}

export function location(event: Event, zh: boolean) {
  const third = event.position.x >= 70 ? (zh?'对方球门附近':'near the opposition goal')
    : event.position.x >= 35 ? (zh?'中场':'in midfield') : (zh?'己方半场':'deep in their own half')
  const lane = event.position.y < 68/3 || event.position.y > 136/3 ? (zh?'边路':'out wide') : (zh?'中路':'through the centre')
  return `${third}, ${lane}`
}

export function cue(event: Event | undefined, resolved: boolean, zh: boolean, detailed = false) {
  if (!event) return zh?'等待开球':'Ready for kick-off'
  const name = playerName(event.actor.player_id)
  const pending: Record<string, [string,string]> = {
    shot: [`${name} prepares to shoot.`,`${name}准备射门。`],
    pass: [`${name} looks for a teammate.`,`${name}寻找传球机会。`],
    carry: [`${name} moves with the ball.`,`${name}带球推进。`],
    duel: [`${name} challenges for the ball.`,`${name}争抢球权。`],
    recovery: [`${name} goes for the loose ball.`,`${name}上前争抢球权。`],
  }
  let text = resolved ? actionText(event, zh) : (pending[event.action.kind]?.[zh?1:0] ?? name)
  if (resolved && event.action.kind === 'recovery' && event.action.origin === 'restart')
    text = zh?`${name}重新开球。`:`${name} restarts play.`
  if (resolved && zh && event.action.kind === 'shot' && event.action.outcome === 'saved')
    text = `${name}射门被门将扑出！`
  if (resolved && event.action.kind === 'pass' && event.action.outcome === 'incomplete')
    text = zh?`${name}的传球未能找到队友。`:`${name}'s pass does not reach a teammate.`
  if (resolved && event.action.kind === 'duel')
    text = zh?`${name}${event.action.outcome==='won'?'赢得':'输掉'}这次争抢。`:`${name} ${event.action.outcome==='won'?'wins':'loses'} the challenge.`
  return detailed ? `${text} ${clubName(event.actor.team_id)} · ${location(event,zh)}.` : text
}

export function answer(question: Question, records: Event[], zh: boolean): {text:string; evidence:Event[]} {
  if (!records.length) return {text:zh?'这次进攻还在进行，完成后再来看看。':'The play is still unfolding. Check back when the action finishes.',evidence:[]}
  const last = records.at(-1)!
  if (question === 'happened') return {text:cue(last,true,zh,true),evidence:[last]}
  if (question === 'buildup') {
    const chain: Event[] = []
    for (let i=records.length-1;i>=0 && chain.length<4;i--) {
      const e=records[i]
      if(e.occurred_at.period!==last.occurred_at.period || time(last)-time(e)>30000) break
      chain.unshift(e)
      if(e.action.kind==='recovery') break
    }
    return {text:chain.map(e=>cue(e,true,zh)).join(zh?'。':' → '),evidence:chain}
  }
  const text = ['eastbridge','northport'].map(team=>{
    const own=records.filter(e=>e.actor.team_id===team)
    const passes=own.filter(e=>e.action.kind==='pass'), completed=passes.filter(e=>e.action.outcome==='completed').length
    const shots=own.filter(e=>e.action.kind==='shot').length
    return zh?`${clubName(team)}：${passes.length}次传球，${completed}次成功，${shots}次射门。`
      :`${clubName(team)}: ${completed} of ${passes.length} passes completed, ${shots} ${shots===1?'shot':'shots'}.`
  }).join(' ')
  return {text:(zh?'本片段截至目前：':'In this sequence so far: ')+text,evidence:records.filter(e=>e.action.kind==='pass'||e.action.kind==='shot')}
}
