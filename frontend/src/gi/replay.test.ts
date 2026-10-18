import { expect,it } from 'vitest'
import { inFrame,replayActions } from './replay'
import type { GIEvent } from './data'
const event:GIEvent={event_id:'a',provider_event_id:1,revision:1,source_order:1,occurrence_order:1,period:2,elapsed_ms:10000,team_id:4418,player_id:'p',kind:'Shot',detail:'Shot',outcome:'goal',start:{x:85,y:45},end:{x:0,y:0},goal_for:4418,review:false,tags:[]}
it('rotates both coordinates for opponents in the selected team frame',()=>{
 expect(inFrame({x:13,y:26},9598,4418)).toEqual({x:92,y:42})
 expect(inFrame({x:13,y:26},4418,4418)).toEqual({x:13,y:26})
})
it('never treats a goal endpoint or goalkeeper sentinel as tracked motion',()=>{
 const rows=replayActions([event,{...event,event_id:'keeper',detail:'Reflexes',start:{x:105,y:68}}],event)
 expect(rows).toHaveLength(1);expect(rows[0].end).toBeNull()
})
it('follows a failed pass through the opponents controlled response, without crossing a restart',()=>{
 const pass={...event,kind:'Pass',detail:'Simple pass',outcome:'incomplete',goal_for:null}
 const response={...pass,event_id:'b',elapsed_ms:16000,team_id:9598,outcome:'complete'}
 const restart={...pass,event_id:'c',elapsed_ms:18000,detail:'Throw in'}
 const rows=replayActions([pass,response,restart],pass)
 expect(rows.map(a=>a.event.event_id)).toEqual(['a','b'])
})
it('keeps simultaneous paired challenges and excludes another half',()=>{
 const duel={...event,kind:'Duel',goal_for:null,detail:'Ground defending duel',team_id:9598,start:{x:20,y:23},end:{x:22,y:22}}
 const selected={...duel,event_id:'selected',team_id:4418}
 const rows=replayActions([duel,selected,{...event,period:1}],selected)
 expect(rows).toHaveLength(2);expect(rows[0].start).toEqual({x:85,y:45});expect(rows[0].end).toEqual({x:83,y:46})
})
it('continues through a blocked shot and rebound to the goal',()=>{
 const blocked={...event,event_id:'blocked',outcome:'blocked',goal_for:null}
 const touch={...event,event_id:'touch',kind:'Others on the ball',detail:'Touch',outcome:'unknown',goal_for:null,elapsed_ms:11500}
 const goal={...event,event_id:'goal',elapsed_ms:14000}
 expect(replayActions([blocked,touch,goal],blocked).map(a=>a.event.event_id)).toEqual(['blocked','touch','goal'])
})
it('retains a known synthetic build-up across a long on-ball interval',()=>{
 const pass={...event,event_id:'a00001',provider_event_id:null,kind:'Pass',detail:'Simple pass',outcome:'complete',goal_for:null,elapsed_ms:1000}
 const shot={...event,event_id:'a00002',provider_event_id:null,elapsed_ms:13000}
 expect(replayActions([pass,shot],shot).map(a=>a.event.event_id)).toEqual(['a00001','a00002'])
})

import { playTimeline,replayFrame,sequenceEvents } from './replay'
it('ends a goal at the finish, without a goalkeeper timestamp adding dead air',()=>{
 const keeper={...event,event_id:'keeper',elapsed_ms:14500,detail:'Reflexes',goal_for:null}
 expect(sequenceEvents([event,keeper],event)).toEqual([event])
 expect(playTimeline(replayActions([event,keeper],event)).duration).toBeLessThan(2500)
})
it('compresses a long source gap and keeps supporting players moving',()=>{
 const pass={...event,event_id:'pass',provider_event_id:null,kind:'Pass',detail:'Simple pass',goal_for:null,outcome:'complete',elapsed_ms:0,start:{x:60,y:34},end:{x:85,y:45}}
 const shot={...event,elapsed_ms:15000}
 const timeline=playTimeline(replayActions([pass,shot],shot))
 expect(timeline.duration).toBeLessThan(6000)
 const roster=[{player_id:'other',provider_player_id:null,team_id:4418,alias_id:'eb02'}]
 const a=replayFrame(timeline,500,roster,4418),b=replayFrame(timeline,1500,roster,4418)
 expect(a.players[0].y).not.toBe(b.players[0].y)
 const boundary=timeline.actions[1].at
 const left=replayFrame(timeline,boundary-.001,roster,4418),right=replayFrame(timeline,boundary,roster,4418)
 expect(Math.hypot(left.ball.x-right.ball.x,left.ball.y-right.ball.y)).toBeLessThan(.01)
})
it('includes the recovery and controlled reply after a lost challenge',()=>{
 const lost={...event,kind:'Duel',detail:'Ground attacking duel',outcome:'lost',goal_for:null,review:true}
 const recovery={...lost,event_id:'recover',kind:'Recovery',detail:'Possession won',team_id:9598,elapsed_ms:10700,review:false}
 const pass={...recovery,event_id:'pass',kind:'Pass',detail:'Simple pass',outcome:'complete',elapsed_ms:12000}
 const later={...pass,event_id:'later',elapsed_ms:14000}
 expect(sequenceEvents([lost,recovery,pass,later],lost).map(e=>e.event_id)).toEqual(['a','recover','pass'])
})
