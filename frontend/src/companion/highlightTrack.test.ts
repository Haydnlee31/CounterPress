import {expect,test,vi} from 'vitest'
import {trackPosition,trackTime,TrackPlayer,type Track} from './highlightTrack'
const track=()=>({duration:12,eventCount:3,markers:[{at:0,position:0,text:'Mercer brings it forward.'},{at:3,position:1,text:'He finds Ellis.'},{at:6,position:2,text:'Ellis shoots—'},{at:8,position:2.6,text:'and scores! A lovely move.'}],audio:{currentTime:0,playbackRate:1,preservesPitch:false,play:vi.fn().mockResolvedValue(undefined),pause:vi.fn(),ended:false},url:'blob:test'} as unknown as Track)
test('whole phrases map to visual actions using actual bookmark times, including goal resolution',()=>{
 const t=track()
 expect(trackPosition(t,8)).toEqual({index:2,progress:expect.closeTo(.6)})
 expect(trackPosition(t,4.5)).toEqual({index:1,progress:.5})
 expect(trackPosition(t,12)).toEqual({index:2,progress:1})
 for(const at of [0,1,3,4.5,6,8,10,12]){
  const p=trackPosition(t,at);expect(trackTime(t,p.index,p.progress)).toBeCloseTo(at)
 }
})
test('one uncut recording preserves voice pitch and resumes exactly at the requested offset',async()=>{
 const t=track(),player=new TrackPlayer(t,4.5,1.5)
 await player.start()
 expect(t.audio.play).toHaveBeenCalledTimes(1)
 expect(t.audio.currentTime).toBe(4.5)
 expect(t.audio.playbackRate).toBe(1.5)
 expect(t.audio.preservesPitch).toBe(true)
 t.audio.currentTime=8
 expect(player.position()).toBe(8)
 expect(player.ended()).toBe(false)
 player.stop();expect(t.audio.pause).toHaveBeenCalledTimes(1)
 const resume=new TrackPlayer(t,8,.5);await resume.start()
 expect(t.audio.currentTime).toBe(8)
 expect(t.audio.play).toHaveBeenCalledTimes(2)
 t.audio.currentTime=12;expect(resume.ended()).toBe(false)
 Object.defineProperty(t.audio,'ended',{value:true});expect(resume.ended()).toBe(true)
})

test('late cleanup from a previous play cannot pause a newer seek or speed change',async()=>{
 const t=track(),old=new TrackPlayer(t,0,1),current=new TrackPlayer(t,5,1.5)
 await old.start();await current.start();old.stop()
 expect(t.audio.pause).not.toHaveBeenCalled()
 expect(t.audio.currentTime).toBe(5)
 current.stop();expect(t.audio.pause).toHaveBeenCalledTimes(1)
})
test('keeps the audio as the clock at 2x while preserving vocal pitch',async()=>{
 const t=track();const player=new TrackPlayer(t,3,2)
 await player.start()
 expect(t.audio.playbackRate).toBe(2);expect(t.audio.preservesPitch).toBe(true)
 t.audio.currentTime=8
 expect(trackPosition(t,player.position())).toEqual({index:2,progress:expect.closeTo(.6,5)})
 player.stop()
})

import {readyAudio} from './highlightTrack'
test('does not declare commentary ready until the media element is buffered',async()=>{
 const media=Object.assign(new EventTarget(),{readyState:0,load:vi.fn(),play:vi.fn()}) as unknown as HTMLAudioElement
 const controller=new AbortController();let ready=false
 const pending=readyAudio(media,controller.signal).then(()=>{ready=true})
 await Promise.resolve();expect(ready).toBe(false);expect(media.load).toHaveBeenCalledOnce();expect(media.play).not.toHaveBeenCalled()
 media.dispatchEvent(new Event('canplaythrough'));await pending;expect(ready).toBe(true)
})
test('cancels audio preparation cleanly when the highlight changes',async()=>{
 const media=Object.assign(new EventTarget(),{readyState:0,load:vi.fn()}) as unknown as HTMLAudioElement
 const controller=new AbortController(),pending=readyAudio(media,controller.signal)
 controller.abort();await expect(pending).rejects.toMatchObject({name:'AbortError'})
 media.dispatchEvent(new Event('canplaythrough'))
})
