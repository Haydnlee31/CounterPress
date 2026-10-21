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
import {positionedActions} from './replay'
it('keeps identical timestamps in different halves separate in full-match playback',()=>{
 const first={...event,period:1 as const,event_id:'half-one',elapsed_ms:1000}
 const second={...event,period:2 as const,event_id:'half-two',elapsed_ms:1000,team_id:9598}
 const t=playTimeline(positionedActions([first,second],4418))
 expect(t.actions).toHaveLength(2);expect(t.actions[1].at).toBe(t.actions[0].duration)
 expect(t.duration).toBe(t.actions[0].duration+t.actions[1].duration)
 const frame=replayFrame(t,t.duration,[],4418)
 expect(frame.ball.x).toBe(0) // Away goal goes into the opposite net in a fixed view.
})
it('does not merge separate nonadjacent timestamp groups or lose records',()=>{
 const events=[event,{...event,event_id:'b',elapsed_ms:20000},{...event,event_id:'c'}]
 expect(playTimeline(positionedActions(events,4418)).actions.map(a=>a.event.event_id)).toEqual(['a','b','c'])
})

import {sceneRoster,MOTION} from './replay'
import type {GIPlayer} from './data'
const goalkeeper:GIPlayer={player_id:'keeper',alias_id:'np01',team_id:9598,provider_player_id:null,role:'GK',formation_slot:0,starter:true}
const runner:GIPlayer={player_id:'runner',alias_id:'eb09',team_id:4418,provider_player_id:null,role:'FW',formation_slot:9,starter:true}
it('uses stable recorded lineup intervals, including backwards seeking',()=>{
 const outgoing={...runner,left_at:{period:2 as const,elapsed_ms:560000}},incoming={...runner,player_id:'sub',alias_id:'eb12',starter:false,entered_at:{period:2 as const,elapsed_ms:560000}}
 const players=[goalkeeper,outgoing,incoming]
 for(const [at,expected] of [[560000,'sub'],[550000,'runner'],[570000,'sub']] as const){
  expect(sceneRoster(players,[],{...event,elapsed_ms:at}).map(p=>p.player_id).sort()).toEqual(['keeper',expected].sort())
 }
})
it('does not drag aerial contestants along the ball endpoint',()=>{
 const duel={...event,kind:'Duel',detail:'Air duel',goal_for:null,outcome:'unknown',player_id:'runner',start:{x:45,y:20},end:{x:70,y:28}}
 const t=playTimeline(positionedActions([duel],4418),[runner],4418)
 const start=replayFrame(t,0,[runner],4418),later=replayFrame(t,t.duration*.8,[runner],4418)
 expect(Math.hypot(later.players[0].x-start.players[0].x,later.players[0].y-start.players[0].y)).toBeLessThan(5)
 expect(later.ball.x).toBeCloseTo(70)
 expect(replayFrame(t,t.duration*.45,[runner],4418).ballHeight).toBeGreaterThan(2)
})
it('holds a goal outcome and cuts to restart instead of flying the ball back',()=>{
 const goal={...event,player_id:'runner',start:{x:95,y:34}}
 const kickoff={...goal,event_id:'restart',kind:'Pass',detail:'Simple pass',outcome:'complete',goal_for:null,elapsed_ms:95000,start:{x:52.5,y:34},end:{x:45,y:34}}
 const t=playTimeline(positionedActions([goal,kickoff],4418),[runner],4418),cut=t.actions[1].at
 expect(t.groups[1].cut).toBe(true)
 expect(replayFrame(t,cut-1,[runner],4418).ball.x).toBeCloseTo(105)
 expect(replayFrame(t,cut-1,[runner],4418).opacity).toBeLessThan(.01)
 expect(replayFrame(t,cut,[runner],4418).opacity).toBe(0)
 expect(replayFrame(t,cut,[runner],4418).ball.x).toBe(52.5)
})
it('keeps saves in front of goal and gives the keeper a bounded response',()=>{
 const shot={...event,player_id:'runner',outcome:'on_target',goal_for:null,start:{x:88,y:42}}
 const t=playTimeline(positionedActions([shot],4418),[runner,goalkeeper],4418)
 const a=replayFrame(t,t.duration*.2,[runner,goalkeeper],4418),b=replayFrame(t,t.duration*.8,[runner,goalkeeper],4418)
 expect(b.ball.x).toBeLessThan(105);expect(b.ball.x).toBeGreaterThan(100)
 const pa=a.players.find(p=>p.role==='GK')!,pb=b.players.find(p=>p.role==='GK')!
 expect(Math.hypot(pb.x-pa.x,pb.y-pa.y)).toBeGreaterThan(.1)
})
it('bounds player speed and acceleration through connected carries and passes',()=>{
 const carry={...event,player_id:'runner',provider_event_id:null,kind:'Carry',detail:'Acceleration',goal_for:null,outcome:'unknown',start:{x:35,y:22},end:{x:70,y:30}}
 const pass={...carry,event_id:'pass',kind:'Pass',detail:'Simple pass',outcome:'complete',elapsed_ms:16000,start:{x:70,y:30},end:{x:90,y:34}}
 const t=playTimeline(positionedActions([carry,pass],4418),[runner],4418)
 let previous:ReturnType<typeof replayFrame>|undefined,velocity:{x:number;y:number}|undefined
 for(let at=0;at<t.duration;at+=20){const f=replayFrame(t,at,[runner],4418)
  if(previous){const p=f.players[0],q=previous.players[0],v={x:(p.x-q.x)/.02,y:(p.y-q.y)/.02}
   expect(Math.hypot(v.x,v.y)).toBeLessThanOrEqual(MOTION.run+.01)
   if(velocity)expect(Math.hypot(v.x-velocity.x,v.y-velocity.y)/.02).toBeLessThanOrEqual(MOTION.acceleration+.01)
   velocity=v
  }previous=f
 }
 const later=replayFrame(t,t.duration*.7,[runner],4418)
 replayFrame(t,t.duration*.1,[runner],4418)
 expect(replayFrame(t,t.duration*.7,[runner],4418)).toEqual(later)
})
