import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { pitchScene, actionText, fieldPoint, sequenceScene } from './pitchScene'
import { knownPlayer, initials } from './identity'
import { MatchPitch } from './MatchPitch'
import type { Event } from '../types'
const pass: Event={schema_version:'1.0',match_id:'match',event_id:'pass-1',revision:1,source_delivery_sequence:1,occurrence_order:1,
  occurred_at:{period:2,elapsed_ms:180000},available_at:{period:2,elapsed_ms:180000},actor:{team_id:'northport',player_id:'np06'},
  position:{x:20,y:34},action:{kind:'pass',outcome:'completed',end_position:{x:28,y:25},recipient:{team_id:'northport',player_id:'np08'}}}
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks()})
test('22 display players, accurate mirrored pass endpoints, involved actors and readable identities',()=>{
  const start=pitchScene(pass,0),end=pitchScene(pass,1)
  expect(start.players).toHaveLength(22)
  expect(new Set(start.players.map(p=>p.player_id)).size).toBe(22)
  expect(start.ball).toEqual({x:85,y:34});expect(end.ball).toEqual({x:77,y:43})
  expect(end.players.filter(p=>p.involved).map(p=>p.player_id)).toEqual(['np06','np08'])
  expect(end.players.find(p=>p.player_id==='np08')).toMatchObject({x:77,y:43})
  expect(start.players.every(p=>p.x>=0&&p.x<=105&&p.y>=0&&p.y<=68)).toBe(true)
  expect(initials('np06')).toBe('SL');expect(actionText(pass)).toBe('Sam Linden passes to Leo Marlow')
  expect(knownPlayer('np01')).toBe(false) // Illustration-only cast must not become API filters.
})
test('carrying moves actor and ball together without changing the source record',()=>{
  const carry={...pass,action:{kind:'carry',end_position:{x:35,y:40}}}
  const serialized=JSON.stringify(carry), scene=pitchScene(carry,.5)
  expect(scene.players.find(p=>p.player_id==='np06')).toMatchObject(scene.ball)
  expect(JSON.stringify(carry)).toBe(serialized)
  expect(pitchScene(undefined,0).players).toHaveLength(22)
})
test('keyboard player selection, manual stepping, and revision reset preserve accessibility',()=>{
  const next={...pass,event_id:'pass-2',actor:{team_id:'eastbridge',player_id:'eb08'}}
  const ui=render(<MatchPitch events={[pass,next]}/>)
  const pitch=within(screen.getByRole('group',{name:'Interactive football pitch'}))
  expect(pitch.getAllByRole('button')).toHaveLength(22)
  fireEvent.keyDown(pitch.getByRole('button',{name:'Sam Linden, Northport'}),{key:'Enter'})
  expect(screen.getByText('Back to play')).toBeTruthy()
  expect(screen.getByText('2 / 2')).toBeTruthy()
  fireEvent.click(screen.getByRole('button',{name:'Previous play'}))
  expect(screen.getByText('1 / 2')).toBeTruthy()
  fireEvent.click(screen.getByRole('button',{name:'Next play'}))
  expect(screen.getByText('2 / 2')).toBeTruthy()
  ui.rerender(<MatchPitch events={[{...pass,revision:2}]}/>)
  expect(screen.getByText('1 / 1')).toBeTruthy()
  expect(screen.queryByText('Back to play')).toBeNull()
})
test('reduced motion provides a deliberate static start/end control',()=>{
  vi.stubGlobal('matchMedia',vi.fn((q:string)=>({matches:q.includes('reduced-motion'),addEventListener:vi.fn(),removeEventListener:vi.fn()})))
  const ui=render(<MatchPitch events={[pass]}/>)
  const before=ui.container.querySelector('.fan-ball')!.getAttribute('transform')
  fireEvent.click(screen.getByRole('button',{name:'Show ball movement'}))
  expect(ui.container.querySelector('.fan-ball')!.getAttribute('transform')).not.toBe(before)
  expect(screen.queryByRole('button',{name:/Pause play/})).toBeNull()
})

// Shape checks protect football-like constraints without treating generated positions as measurements.
test('keepers stay near goal, teams respond to possession, and static actions do not drift',()=>{
  for (const team of ['eastbridge','northport']) for (const x of [3,52,99]) {
    const event={...pass,actor:{team_id:team,player_id:team==='eastbridge'?'eb08':'np08'},position:{x,y:12},action:{kind:'recovery'}}
    const first=pitchScene(event,0),last=pitchScene(event,1)
    expect(last.players).toEqual(first.players)
    for(const p of first.players.filter(p=>p.number===1)) {
      const local=fieldPoint(p,p.team_id)
      expect(local.x).toBeGreaterThanOrEqual(4);expect(local.x).toBeLessThanOrEqual(10)
      expect(local.y).toBeGreaterThanOrEqual(29);expect(local.y).toBeLessThanOrEqual(39)
    }
    expect(first.players.every(p=>p.x>=0&&p.x<=105&&p.y>=0&&p.y<=68)).toBe(true)
    const width=(id:string)=>{const ys=first.players.filter(p=>p.team_id===id&&!p.involved&&p.number!==1).map(p=>p.y);return Math.max(...ys)-Math.min(...ys)}
    expect(width(team)).toBeGreaterThan(width(team==='eastbridge'?'northport':'eastbridge'))
  }
})
test('all 22 players remain full size and labelled without a spotlight control',()=>{
  const ui=render(<MatchPitch events={[pass]}/>)
  expect(screen.queryByRole('button',{name:'Near the ball'})).toBeNull()
  expect(ui.container.querySelectorAll('.fan-pitch-player')).toHaveLength(22)
  expect(ui.container.querySelectorAll('.is-distant')).toHaveLength(0)
  expect([...ui.container.querySelectorAll('.player-disc')].every(p=>p.getAttribute('r')==='2.7')).toBe(true)
})
test('commentary follows the playhead, rewinds without future entries and resets corrected wording',()=>{
  const next: Event={...pass,event_id:'pass-2',occurrence_order:2,occurred_at:{period:2,elapsed_ms:185000},available_at:{period:2,elapsed_ms:185000},action:{kind:'carry',end_position:{x:32,y:34}}}
  const ui=render(<MatchPitch events={[pass,next]}/>)
  const feed=within(screen.getByRole('complementary',{name:'Match commentary'}))
  expect(feed.getByRole('button',{name:/Replay 48:05: Sam Linden moves with the ball/}).getAttribute('aria-current')).toBe('step')
  fireEvent.click(feed.getByRole('button',{name:/Replay 48:00:/}))
  expect(feed.queryByRole('button',{name:/Replay 48:05:/})).toBeNull()
  fireEvent.click(screen.getByRole('button',{name:/Latest play/}))
  expect(feed.getByRole('button',{name:/Replay 48:05:/})).toBeTruthy()
  ui.rerender(<MatchPitch events={[{...pass,revision:2,actor:{team_id:'eastbridge',player_id:'eb09'}}]}/>)
  expect(feed.queryByRole('button',{name:/Sam Linden/})).toBeNull()
  expect(feed.getByRole('button',{name:/Rory Ellis/})).toBeTruthy()
})

test('playback restarts from the first play and stops at the end instead of silently looping',()=>{
  let callback: FrameRequestCallback=()=>{}
  vi.spyOn(performance,'now').mockReturnValue(0)
  vi.stubGlobal('requestAnimationFrame',vi.fn((cb:FrameRequestCallback)=>{callback=cb;return 1}))
  vi.stubGlobal('cancelAnimationFrame',vi.fn())
  render(<MatchPitch events={[pass,{...pass,event_id:'pass-2'}]}/>)
  expect(screen.getByText('2 / 2')).toBeTruthy()
  fireEvent.click(screen.getByRole('button',{name:/Play sequence/}))
  expect(screen.getByText('1 / 2')).toBeTruthy()
  for(let now=100;now<=6600;now+=100)act(()=>callback(now))
  expect(screen.getByText('2 / 2')).toBeTruthy()
  expect(screen.queryByRole('button',{name:/Pause play/})).toBeNull()
  expect(screen.getByRole('button',{name:/Play sequence/})).toBeTruthy()
})

test('saved shots reach the keeper then rebound continuously across the possession change',()=>{
  const shot:Event={...pass,actor:{team_id:'northport',player_id:'np08'},position:{x:94,y:34},action:{kind:'shot',situation:'penalty',outcome:'saved',end_position:{x:103,y:32},rebound_position:{x:99,y:33},goalkeeper:{team_id:'eastbridge',player_id:'eb01'}}}
  const contact=pitchScene(shot,.6),rebound=pitchScene(shot,1)
  for(const player of pitchScene(shot,0).players.filter(p=>p.number!==1&&!p.involved)) expect(fieldPoint(player,'northport').x).toBeLessThanOrEqual(84)
  expect(contact.ball).toEqual({x:2,y:36})
  expect(contact.players.find(p=>p.player_id==='eb01')).toMatchObject({...contact.ball,involved:true})
  expect(rebound.ball).toEqual({x:6,y:35})
  expect(actionText(shot)).toContain('penalty — saved by Theo Ashford')
  expect(contact.players.every(p=>p.x>=0&&p.x<=105&&p.y>=0&&p.y<=68)).toBe(true)
})

test('goal reveal and playhead score wait for the ball, undo on rewind and respect correction',async()=>{
  const {scoreAtPlayhead}=await import('./pitchScene')
  const goal:Event={...pass,event_id:'goal-1',actor:{team_id:'eastbridge',player_id:'eb09'},action:{kind:'shot',outcome:'goal',end_position:{x:105,y:33},goalkeeper:{team_id:'northport',player_id:'np01'}}}
  vi.stubGlobal('matchMedia',vi.fn((q:string)=>({matches:q.includes('reduced-motion'),addEventListener:vi.fn(),removeEventListener:vi.fn()})))
  const head=vi.fn(), events=[pass,goal], score={eastbridge:3,northport:1}
  const ui=render(<MatchPitch events={events} fromStart onPlayhead={head}/>)
  expect(screen.getByText('1 / 2')).toBeTruthy()
  expect(scoreAtPlayhead(score,events,0,true)).toEqual({eastbridge:2,northport:1})
  fireEvent.click(screen.getByRole('button',{name:'Next play'}))
  expect(ui.container.querySelector('.fan-goal-banner')).toBeNull()
  expect(scoreAtPlayhead(score,events,1,false)).toEqual({eastbridge:2,northport:1})
  fireEvent.click(screen.getByRole('button',{name:'Show ball movement'}))
  expect(ui.container.querySelector('.fan-goal-banner')?.textContent).toContain('GOAL!')
  expect(head).toHaveBeenLastCalledWith({index:1,resolved:true})
  expect(scoreAtPlayhead(score,events,1,true)).toEqual(score)
  fireEvent.click(screen.getByRole('button',{name:'Previous play'}))
  expect(ui.container.querySelector('.fan-goal-banner')).toBeNull()
  const corrected={...goal,revision:2,action:{...goal.action,outcome:'saved',end_position:{x:103,y:33}}}
  ui.rerender(<MatchPitch events={[corrected]} fromStart onPlayhead={head}/>)
  fireEvent.click(screen.getByRole('button',{name:'Show ball movement'}))
  expect(ui.container.querySelector('.fan-goal-banner')).toBeNull()
  expect(scoreAtPlayhead({eastbridge:2,northport:1},[corrected],0,true)).toEqual({eastbridge:2,northport:1})
  expect(pitchScene(goal,1).ball).toEqual({x:105,y:33})
})


test('reduced-motion viewers can listen to a manually completed play',()=>{
  vi.stubGlobal('matchMedia',vi.fn((q:string)=>({matches:q.includes('reduced-motion'),addEventListener:vi.fn(),removeEventListener:vi.fn()})))
  const synth={speak:vi.fn(),cancel:vi.fn(),getVoices:()=>[]}
  vi.stubGlobal('speechSynthesis',synth)
  vi.stubGlobal('SpeechSynthesisUtterance',class {text:string;constructor(text:string){this.text=text}})
  render(<MatchPitch events={[pass]} companion fromStart/>)
  fireEvent.click(screen.getByRole('button',{name:/Listen/}))
  expect(synth.speak).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button',{name:'Show ball movement'}))
  expect(synth.speak.mock.calls.at(-1)![0].text).toContain('passes to Leo Marlow')
  fireEvent.click(screen.getByRole('button',{name:'Show ball movement'}))
  expect(synth.cancel).toHaveBeenCalled()
})
