import {expect,test,vi} from 'vitest'
import type {Event} from '../types'
import {planTrack,trackPosition,TrackPlayer,trimSilence} from './highlightTrack'
const event=(kind:string,id:number)=>({match_id:'showcase-level-first-v1',event_id:String(id),position:{x:60,y:34},action:{kind},occurred_at:{period:1,elapsed_ms:id*2000}} as Event)
const buffer=(duration:number)=>({duration} as AudioBuffer)
test('opening voice is immediate, shot result aligns with resolution, no overlapping or stale calls',()=>{
 const events=[event('pass',0),event('pass',1),event('shot',2)]
 const track=planTrack(events,[{event:0,result:false,buffer:buffer(2)},{event:1,result:false,buffer:buffer(5)},
  {event:2,result:false,buffer:buffer(1.2)},{event:2,result:true,buffer:buffer(.9)}])
 expect(track.cues[0].at).toBe(0)
 expect(track.cues.some(c=>c.event===1)).toBe(false)
 const goal=track.cues.find(c=>c.result)!
 expect(trackPosition(track,goal.at).progress).toBeCloseTo(.6)
 expect(trackPosition(track,goal.at).index).toBe(2)
 expect(goal.at+goal.buffer.duration).toBeLessThan(track.duration)
 for(let i=1;i<track.cues.length;i++)expect(track.cues[i].at).toBeGreaterThan(track.cues[i-1].at+track.cues[i-1].buffer.duration)
 expect(trackPosition(track,track.duration)).toEqual({index:2,progress:1})
})
test('audio and picture share the clock at every speed, pause cancels all scheduled nodes, resume uses offset',()=>{
 const nodes:{start:ReturnType<typeof vi.fn>;stop:ReturnType<typeof vi.fn>;disconnect:ReturnType<typeof vi.fn>;playbackRate:{value:number}}[]=[]
 const context={currentTime:10,destination:{},createBufferSource:()=>{const node={connect:vi.fn(),start:vi.fn(),stop:vi.fn(),disconnect:vi.fn(),playbackRate:{value:1}};nodes.push(node);return node}} as unknown as AudioContext
 const track=planTrack([event('pass',0),event('shot',1)],[{event:0,result:false,buffer:buffer(.7)},{event:1,result:true,buffer:buffer(.8)}])
 for(const speed of [.5,1,1.5]){
  const player=new TrackPlayer(context,track,.2,speed);player.start()
  const first=nodes.at(-2)!
  expect(first.start).toHaveBeenCalledWith(10.03,.2)
  expect(first.playbackRate.value).toBe(speed)
  Object.defineProperty(context,'currentTime',{value:10.53,writable:true})
  expect(player.position()).toBeCloseTo(.2+.5*speed)
  player.stop();expect(nodes.every(n=>n.stop.mock.calls.length===1&&n.disconnect.mock.calls.length===1)).toBe(true)
  Object.defineProperty(context,'currentTime',{value:10,writable:true})
 }
})
test('synthesis silence is removed without cutting speech',()=>{
 const samples=new Float32Array(1000);samples.fill(.2,300,600)
 const copy=vi.fn(),create=vi.fn(()=>({copyToChannel:copy}))
 trimSilence({createBuffer:create} as unknown as AudioContext,{sampleRate:1000,numberOfChannels:1,getChannelData:()=>samples} as unknown as AudioBuffer)
 expect(create).toHaveBeenCalledWith(1,340,1000)
 expect(copy.mock.calls[0][0]).toHaveLength(340)
})
