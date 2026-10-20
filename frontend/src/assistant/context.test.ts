import {expect,it} from 'vitest'
import {matchdayContext,momentContext} from './context'
import type {Event} from '../types'

it('translates a rebased highlight to its parent match clock and availability',()=>{
 const event={match_id:'showcase-level-first-v1',event_id:'a00500',revision:2,occurred_at:{period:2,elapsed_ms:760000},available_at:{period:2,elapsed_ms:761100}} as Event
 const after=matchdayContext('parent',event,true,'Moment')
 expect(after.cutoff).toEqual({period:1,elapsed_ms:2075886})
 expect(after.eventId).toBe('a00500');expect(after.eventRevision).toBe(2)
 const before=matchdayContext('parent',event,false,'Moment')
 expect(before.cutoff).toEqual({period:1,elapsed_ms:2074785})
})

it('captures a copy of the cutoff so later playback cannot mutate the question',()=>{
 const event={event_id:'e1',revision:1,occurred_at:{period:1 as const,elapsed_ms:100},available_at:{period:1 as const,elapsed_ms:1000}}
 const context=momentContext('match',event,true,'Moment')
 event.available_at.elapsed_ms=5000
 expect(context.cutoff?.elapsed_ms).toBe(1000)
})
