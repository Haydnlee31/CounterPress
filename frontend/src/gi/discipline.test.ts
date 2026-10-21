import {expect,it} from 'vitest'
import {cardType,discipline} from './discipline'
import type {GIEvent} from './data'
const event:GIEvent={event_id:'a',provider_event_id:1,revision:1,source_order:1,occurrence_order:1,period:1,elapsed_ms:1000,team_id:4418,player_id:'p',kind:'Foul',detail:'Foul',outcome:'unknown',start:{x:20,y:30},end:null,goal_for:null,review:false,tags:[1702]}
it('resolves second-yellow and direct-red tags without double counting',()=>{
 const second={...event,event_id:'b',elapsed_ms:2000,tags:[1702,1703,1701]}
 expect(cardType(second)).toBe('second_yellow')
 const data=discipline([event,second,second])
 expect(data.cards).toHaveLength(2);expect(data.players[0].yellows).toBe(2);expect(data.players[0].sentOff).toBe(true)
 expect(discipline([{...event,tags:[1701]}]).players[0]).toMatchObject({yellows:0,sentOff:true})
})
it('two independent bookings dismiss a player even without an explicit second-yellow tag',()=>{
 expect(discipline([event,{...event,event_id:'b',elapsed_ms:2000}]).players[0].sentOff).toBe(true)
})
it('does not reveal cards before their availability and respects corrected records',()=>{
 const revised={...event,revision:2,available_ms:2000,available_period:1 as const,tags:[]}
 expect(discipline([event,revised],{period:1,elapsed_ms:999}).cards).toHaveLength(0)
 expect(discipline([event,revised],{period:1,elapsed_ms:1500}).cards).toHaveLength(1)
 expect(discipline([event,revised],{period:1,elapsed_ms:2000}).cards).toHaveLength(0)
})
