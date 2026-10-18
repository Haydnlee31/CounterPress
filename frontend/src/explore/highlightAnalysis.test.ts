import {readFileSync} from 'node:fs'
import {expect,test} from 'vitest'
import type {Event} from '../types'
import {actionCounts,availablePhases,highlightPhases,involvedIn,participants,phaseRecords} from './highlightAnalysis'
const load=(id:string):Event[]=>JSON.parse(readFileSync(`../fixtures/showcases/${(['level-first','take-lead','level-late'].includes(id)?id:id.replaceAll('-','_'))}.json`,'utf8')).events
for(const [id,expected] of [['last-gasp',[4,2,3,2]],['one-touch',[3,1,1,0]],['breakaway',[3,1,1,0]]] as const) test(`${id}: phases partition the source actions, and totals count the actual events`,()=>{
 const events=load(id),phases=availablePhases(id,events)
 expect(phases).toHaveLength(3)
 expect(phases.flatMap(p=>phaseRecords(p,events).map(e=>e.event_id))).toEqual(events.map(e=>e.event_id))
 expect(actionCounts(events)).toEqual(expected)
 expect(new Set(phases.flatMap(p=>p.ids)).size).toBe(events.length)
})
test('outdated, missing or foreign evidence suppresses editorial phase explanations',()=>{
 const events=load('last-gasp')
 expect(availablePhases('last-gasp',events.slice(1))).toEqual([])
 expect(availablePhases('last-gasp',events.map((e,i)=>i?e:{...e,revision:2}))).toEqual([])
 expect(availablePhases('last-gasp',events.map(e=>({...e,match_id:'another-match'})))).toEqual([])
 expect(highlightPhases['last-gasp']).toHaveLength(3)
})
test('involvement includes recipients and keepers without inventing off-ball actions',()=>{
 const events=load('last-gasp')
 expect(participants(events)).toContain('eb01')
 expect(events.filter(e=>involvedIn(e,'eb01')).map(e=>e.event_id)).toEqual(['lg-penalty','lg-rebound'])
 expect(events.filter(e=>involvedIn(e,'eb09')).map(e=>e.event_id)).toEqual(['lg-knockdown','lg-winner'])
 expect(events.filter(e=>involvedIn(e,'eb02'))).toEqual([])
})

for(const id of ['level-first','take-lead','level-late']) test(`${id}: derived phases cover the exact parent actions`,()=>{
 const events=load(id)
 const phases=availablePhases(id,events)
 expect(phases).toHaveLength(2)
 expect(phases.flatMap(p=>p.ids)).toEqual(events.map(e=>e.event_id))
})
