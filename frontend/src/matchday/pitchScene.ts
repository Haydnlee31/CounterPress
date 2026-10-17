import type { Event } from '../types'
import { playerName, squads } from './identity'

export type Point = { x: number; y: number }
export const BALL_FOCUS_RADIUS = 26
const clamp = (n: number, min: number, max: number) => Math.min(max, Math.max(min, n))

/** Both sides share one stadium view; each source event attacks in its own +x direction. */
export function fieldPoint(point: Point, team: string): Point {
  return team === 'northport' ? { x: 105 - point.x, y: 68 - point.y } : point
}
function point(value: unknown): value is Point {
  return !!value && typeof value === 'object' && 'x' in value && 'y' in value
    && typeof value.x === 'number' && typeof value.y === 'number'
}
export function recipient(event: Event | undefined) {
  const r = event?.action.recipient
  return r && typeof r === 'object' && 'player_id' in r && typeof r.player_id === 'string' ? r.player_id : null
}
export function actionText(event: Event, zh = false) {
  const name = playerName(event.actor.player_id), target = recipient(event)
  switch (event.action.kind) {
    case 'shot': {
      const keeper = event.action.goalkeeper as {player_id?: string} | undefined
      const save = keeper?.player_id ? playerName(keeper.player_id) : (zh ? '门将' : 'the goalkeeper')
      if (event.action.outcome === 'goal') return zh ? `${name}射门得分！` : `${name} fires it home!`
      if (event.action.outcome === 'saved') return zh ? `${name}${event.action.situation==='penalty'?'主罚点球':'补射'}，${save}扑出！` : `${name} ${event.action.situation==='penalty'?'takes the penalty':'shoots'} — saved by ${save}!`
      return zh ? `${name}射门${event.action.outcome==='blocked'?'被挡出':'偏出球门'}` : `${name}'s shot is ${event.action.outcome==='blocked'?'blocked':'off target'}`
    }
    case 'pass':
      if (event.action.technique === 'cross') return zh ? `${name}传中寻找${target ? playerName(target) : '队友'}` : `${name} crosses for ${target ? playerName(target) : 'a teammate'}`
      if (event.action.technique === 'header') return zh ? `${name}头球摆渡给${target ? playerName(target) : '队友'}` : `${name} heads it down to ${target ? playerName(target) : 'a teammate'}`
      return zh ? `${name}${event.action.outcome === 'completed' ? '传球给' : '尝试传球给'}${target ? playerName(target) : '队友'}`
      : `${name} ${event.action.outcome === 'completed' ? 'passes to' : 'tries to find'} ${target ? playerName(target) : 'a teammate'}`
    case 'carry': return zh ? `${name}带球推进` : `${name} carries the ball`
    case 'recovery': return zh ? `${name}赢回球权` : `${name} wins the ball back`
    case 'duel': return zh ? `${name}争抢球权` : `${name} challenges for the ball`
    default: return zh ? `${name}参与这次进攻` : `${name} is involved in the play`
  }
}
export function actionLabel(event: Event | undefined, zh = false) {
  const labels: Record<string, [string, string]> = {
    shot: ['Shot', '射门'], pass: ['Pass', '传球'], carry: ['On the move', '带球推进'],
    recovery: ['Ball won back', '赢回球权'], duel: ['Challenge', '争抢'],
  }
  return (labels[event?.action.kind ?? ''] ?? ['Next play', '下一次进攻'])[zh ? 1 : 0]
}
export function pitchZone(event: Event, zh = false) {
  const { x, y } = event.position
  const zone = x >= 70 ? ['Final third', '前场'] : x >= 35 ? ['Midfield', '中场'] : ['Own third', '后场']
  const lane = y < 68 / 3 || y > 136 / 3 ? ['wide', '边路'] : ['centre', '中路']
  return `${zone[zh ? 1 : 0]} · ${lane[zh ? 1 : 0]}`
}

/** Illustrative team shape in each team's own attacking coordinates, not tracking inference. */
function shape(number: number, ball: Point, attacking: boolean): Point {
  if (number === 1) return { x: clamp(4 + ball.x * .055, 4, 10), y: clamp(34 + (ball.y - 34) * .12, 29, 39) }
  let positions: number[][]
  if (attacking) {
    const back = clamp(ball.x - 36, 18, 51)
    const middle = clamp(ball.x - 17, 31, 71)
    const front = clamp(ball.x + 10, 53, 95)
    positions = [[back + 7, 8], [back, 24], [back, 44], [back + 7, 60],
      [middle - 7, 34], [middle, 18], [middle, 50], [front, 10], [front + 1, 34], [front, 58]]
  } else {
    const back = clamp(ball.x - 23, 12, 43)
    positions = [[back + 2, 15], [back, 28], [back, 40], [back + 2, 53],
      [back + 14, 15], [back + 12, 28], [back + 12, 40], [back + 14, 53],
      [back + 27, 25], [back + 27, 43]]
  }
  const [x, y] = positions[number - 2]
  return { x: clamp(x, 4, 101), y: clamp(y + (ball.y - 34) * (attacking ? .18 : .35), 5, 63) }
}

export function pitchScene(event: Event | undefined, progress: number) {
  const start = event ? fieldPoint(event.position, event.actor.team_id) : { x: 52.5, y: 34 }
  const rawEnd = event?.action.end_position
  const end = event && point(rawEnd) ? fieldPoint(rawEnd, event.actor.team_id) : start
  const isShot = event?.action.kind === 'shot'
  const amount = clamp((progress - .2) / (isShot ? .4 : .6), 0, 1), smooth = amount * amount * (3 - 2 * amount)
  let ball = { x: start.x + (end.x - start.x) * smooth, y: start.y + (end.y - start.y) * smooth }
  const rawRebound = event?.action.rebound_position
  if (event && isShot && point(rawRebound) && progress > .6) {
    const rebound = fieldPoint(rawRebound, event.actor.team_id), t = clamp((progress-.6)/.35,0,1)
    ball = {x:end.x+(rebound.x-end.x)*t,y:end.y+(rebound.y-end.y)*t}
  }
  const keeper = isShot ? (event?.action.goalkeeper as {player_id?:string} | undefined)?.player_id : undefined
  const target = recipient(event)
  const players = squads.map(p => {
    const involved = p.player_id === event?.actor.player_id || p.player_id === target || p.player_id === keeper
    const teamBall = fieldPoint(ball, p.team_id)
    let position = fieldPoint(shape(p.number, teamBall, p.team_id === event?.actor.team_id), p.team_id)
    if (p.player_id === event?.actor.player_id) position = event.action.kind === 'carry' ? ball : start
    if (p.player_id === target && event?.action.outcome === 'completed' && point(rawEnd)) position = end
    if (p.player_id === keeper && event) {
      const from = fieldPoint({x:104,y:34},event.actor.team_id)
      const to = event.action.outcome === 'saved' ? end : fieldPoint({x:102.5,y:35.5},event.actor.team_id)
      position = {x:from.x+(to.x-from.x)*smooth,y:from.y+(to.y-from.y)*smooth}
    }
    // A penalty begins with all other outfield players outside the area and arc.
    if (event?.action.situation === 'penalty' && !involved && p.number !== 1) {
      const local = fieldPoint(position,event.actor.team_id)
      local.x = Math.min(local.x,84)
      position = fieldPoint(local,event.actor.team_id)
    }
    return { ...p, ...position, involved }
  })
  // One defender closes from the goal side; the others retain their compact lines.
  const nearest = event && players.filter(p => p.team_id !== event.actor.team_id && p.number !== 1 && !p.involved)
    .sort((a, b) => {
      const distance = (p: typeof a) => {
        const local = fieldPoint(start, p.team_id)
        const initial = shape(p.number, local, false)
        return Math.hypot(initial.x - local.x, initial.y - local.y)
      }
      return distance(a) - distance(b)
    })[0]
  if (nearest && event?.action.situation !== 'penalty') {
    const local = fieldPoint(event?.action.kind === 'carry' ? ball : start, nearest.team_id)
    Object.assign(nearest, fieldPoint({ x: clamp(local.x - 5, 6, 99), y: clamp(local.y + (local.y < 34 ? 3 : -3), 5, 63) }, nearest.team_id))
  }
  // Keep markers legible, preserving observed action anchors and goalkeeper positions.
  for (let pass = 0; pass < 8; pass++) for (let i = 0; i < players.length; i++) for (let j = i + 1; j < players.length; j++) {
    const a = players[i], b = players[j], dx = b.x - a.x, dy = b.y - a.y, distance = Math.hypot(dx, dy)
    const aFixed = a.involved || a.number === 1, bFixed = b.involved || b.number === 1
    if (distance >= 6 || (aFixed && bFixed)) continue
    const ux = distance > .01 ? dx / distance : 1, uy = distance > .01 ? dy / distance : 0
    const amount = 6 - distance, aShare = aFixed ? 0 : bFixed ? 1 : .5, bShare = bFixed ? 0 : aFixed ? 1 : .5
    a.x = clamp(a.x - ux * amount * aShare, 4, 101); a.y = clamp(a.y - uy * amount * aShare, 4, 64)
    b.x = clamp(b.x + ux * amount * bShare, 4, 101); b.y = clamp(b.y + uy * amount * bShare, 4, 64)
  }
  if (event?.action.situation === 'penalty') for (const p of players) {
    if (p.number === 1 || p.involved) continue
    const local=fieldPoint(p,event.actor.team_id)
    Object.assign(p,fieldPoint({...local,x:Math.min(local.x,84)},event.actor.team_id))
  }
  return { players, ball, start, end, kicking: (event?.action.kind === 'pass' || isShot) && progress >= .15 && progress <= .4 }
}

/** Remove future goals from an authoritative snapshot while its pitch replay is rewound. */
export function scoreAtPlayhead(score: Record<string,number>, events: Event[], index: number, resolved: boolean) {
  const result={...score}
  events.forEach((event,i)=>{
    if(event.action.kind==='shot' && event.action.outcome==='goal' && (i>index || (i===index&&!resolved))) result[event.actor.team_id]-=1
  })
  return result
}
