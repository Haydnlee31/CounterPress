import { describe, expect, it } from 'vitest'
import { alias, matchClock, selectEvents } from './data'
import type { GIEvent } from './data'
const base:GIEvent={event_id:'a',provider_event_id:1,revision:1,source_order:1,occurrence_order:1,period:1,elapsed_ms:1000,team_id:4418,player_id:'p',kind:'Pass',detail:'Simple pass',outcome:'unknown',start:{x:10,y:20},end:null,goal_for:null,review:false,tags:[]}
describe('GI evidence selection',()=>{
 it('keeps unknown passes out of unsuccessful totals and respects all scopes',()=>{
  const events=[base,{...base,event_id:'b',outcome:'incomplete'},{...base,event_id:'c',outcome:'incomplete',team_id:9598,player_id:'q',period:2 as const}]
  expect(selectEvents(events,'incomplete','','','')).toHaveLength(2)
  expect(selectEvents(events,'incomplete','4418','p','1').map(e=>e.event_id)).toEqual(['b'])
  expect(selectEvents(events,'incomplete','4418','p','2')).toEqual([])
 })
 it('includes own goals without counting them as shots',()=>{
  const own={...base,kind:'Others on the ball',outcome:'own_goal',goal_for:9598}
  expect(selectEvents([own],'key','','','')).toEqual([own])
  expect(selectEvents([own],'shots','','','')).toEqual([])
 })
 it('keeps first-half stoppage time separate from second-half clock',()=>{
  expect(matchClock({...base,elapsed_ms:2765000})).toBe('45+1:05')
  expect(matchClock({...base,period:2,elapsed_ms:65000})).toBe('46:05')
  expect(matchClock({...base,period:2,elapsed_ms:2765000})).toBe('90+1:05')
 })
 it('reuses dashboard names with distinct substitutes',()=>{
  expect(alias({player_id:'p',provider_player_id:1,team_id:4418,alias_id:'eb04'})).toBe('Alex Rowan')
  expect(alias({player_id:'p',provider_player_id:2,team_id:4418,alias_id:'eb12'})).toBe('Eastbridge substitute 1')
 })
})
