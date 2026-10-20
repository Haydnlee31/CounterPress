import {expect,it} from 'vitest'
import {highlightFrame,highlightTimeline,sourceCutoff} from './replay'
import type {Player,Replay} from './data'
import type {Event} from '../types'
const event=(id:string,at:number,kind:string):Event=>({schema_version:'1.0',match_id:'game',event_id:id,revision:1,source_delivery_sequence:1,occurrence_order:1,occurred_at:{period:2,elapsed_ms:at},available_at:{period:2,elapsed_ms:at+225},actor:{team_id:'redhaven',player_id:'rh08'},position:{x:70,y:30},action:{kind,outcome:kind==='shot'?'goal':'completed',end_position:{x:kind==='shot'?105:85,y:34}}})
const shot=event('goal',447000,'shot')
const replay:Replay={match_id:'game',teams:[{team_id:'southbank',name:'Southbank',player_ids:[]},{team_id:'redhaven',name:'Redhaven',player_ids:[]}],initial_state:{at:{period:2,elapsed_ms:440000},score:{southbank:1,redhaven:1}},events:[event('pass',441000,'pass'),shot]}
it('maps replay progress to source availability and does not reveal a goal early',()=>{
  expect(sourceCutoff(shot,false)).toEqual({period:2,elapsed_ms:446999})
  expect(sourceCutoff(shot,true)).toEqual({period:2,elapsed_ms:447225})
  const timeline=highlightTimeline(replay),last=timeline.actions.at(-1)!
  const before=highlightFrame(replay,timeline,last.at+last.duration*.79,[],[])
  const after=highlightFrame(replay,timeline,last.at+last.duration*.8,[],[])
  expect(before.cutoff.elapsed_ms).toBeLessThan(447225)
  expect(after.cutoff.elapsed_ms).toBe(447225)
})
it('keeps all active identities on the field and resolves the complete final action',()=>{
  const players=Array.from({length:22},(_,i)=>({player_id:i===18?'rh08':`player${i}`,name:`Player ${i}`,club_id:i<11?'southbank':'redhaven',number:i%11+1,role:i%11===0?'GK':'MF',featured:true,star:false,birth_year:2000,debut_year:2020} as Player)),ids=players.map(p=>p.player_id)
  const timeline=highlightTimeline(replay)
  const start=highlightFrame(replay,timeline,0,players,ids),end=highlightFrame(replay,timeline,timeline.duration,players,ids)
  expect(start.players.map(p=>p.player_id).sort()).toEqual(end.players.map(p=>p.player_id).sort())
  expect(end.players).toHaveLength(22)
  expect(end.phase).toBeCloseTo(1)
  expect(end.ball).toEqual({x:0,y:34}) // Redhaven attacks left in the shared stadium view.
  expect(end.cutoff).toEqual(shot.available_at)
  expect(end.players.some((p,i)=>p.x!==start.players[i].x||p.y!==start.players[i].y)).toBe(true)
})
