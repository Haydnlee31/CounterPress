import {expect,test} from 'vitest'
import type {Event} from '../types'
import {matchFrame,HALF,END} from './playback'
const goal:Event={schema_version:'1.0',match_id:'match',event_id:'goal',revision:1,source_delivery_sequence:1,occurrence_order:1,
 occurred_at:{period:1,elapsed_ms:10000},available_at:{period:1,elapsed_ms:10000},actor:{team_id:'eastbridge',player_id:'eb09'},position:{x:95,y:34},action:{kind:'shot',outcome:'goal'}}
test('full-match score and evidence wait for the action and rewind cleanly',()=>{
 expect(matchFrame([goal],9000).visible).toEqual([])
 expect(matchFrame([goal],11000).score.eastbridge).toBe(0)
 expect(matchFrame([goal],12000).score.eastbridge).toBe(1)
 expect(matchFrame([goal],9000).score.eastbridge).toBe(0)
 expect(matchFrame([goal],11000).completed).toEqual([])
})
test('second-half actions and delayed revisions are unavailable before their cutoff',()=>{
 const second={...goal,event_id:'second',occurrence_order:2,occurred_at:{period:2 as const,elapsed_ms:1000},available_at:{period:2 as const,elapsed_ms:1000}}
 expect(matchFrame([goal,second],HALF).score.eastbridge).toBe(1)
 expect(matchFrame([goal,second],END).score.eastbridge).toBe(2)
 const correction={...goal,revision:2,available_at:{period:1 as const,elapsed_ms:20000},action:{kind:'shot',outcome:'off_target'}}
 expect(matchFrame([goal,correction],15000).score.eastbridge).toBe(1)
 expect(matchFrame([goal,correction],23000).score.eastbridge).toBe(0)
})
