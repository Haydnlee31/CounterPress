import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { pitchScene, actionText } from './pitchScene'
import { knownPlayer, initials } from './identity'
import { MatchPitch } from './MatchPitch'
import type { Event } from '../types'
const pass: Event={schema_version:'1.0',match_id:'match',event_id:'pass-1',revision:1,source_delivery_sequence:1,occurrence_order:1,
  occurred_at:{period:2,elapsed_ms:180000},available_at:{period:2,elapsed_ms:180000},actor:{team_id:'northport',player_id:'np06'},
  position:{x:20,y:34},action:{kind:'pass',outcome:'completed',end_position:{x:28,y:25},recipient:{team_id:'northport',player_id:'np08'}}}
afterEach(()=>{cleanup();vi.unstubAllGlobals()})
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
