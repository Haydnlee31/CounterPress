import type {Event} from '../types'
import {playDuration} from '../matchday/pitchScene'

export type Clip = {event:number; result:boolean; buffer:AudioBuffer}
export type Cue = Clip & {at:number}
export type Track = {durations:number[]; starts:number[]; cues:Cue[]; duration:number}

/** Leave the football pace intact. Reserve only the short shot reaction tail.
 * Routine names yield to shots; there is never a queue of stale commentary. */
export function planTrack(events:Event[],clips:Clip[],timed=true):Track {
  const durations=events.map((e,i)=>(timed?playDuration(e,events[i+1]):3200)/1000)
  for(const clip of clips.filter(c=>c.result))
    durations[clip.event]=Math.max(durations[clip.event],(clip.buffer.duration+.08)/.4)
  // Always hear the opening call immediately; protect the build-up to each shot too.
  for(const clip of clips.filter(c=>!c.result&&(c.event===0||events[c.event].action.kind==='shot')))
    durations[clip.event]=Math.max(durations[clip.event],(clip.buffer.duration+.08)/(events[clip.event].action.kind==='shot'?.6:1))
  const starts=[0];durations.forEach(d=>starts.push(starts.at(-1)!+d))
  const results=clips.filter(c=>c.result).map(c=>({...c,at:starts[c.event]+.6*durations[c.event]}))
  const cues=[...results]
  for(const clip of clips.filter(c=>!c.result)) {
    const at=starts[clip.event],end=at+clip.buffer.duration+.06
    // Keep a clear breath between calls, including the next shot's result.
    if(end>starts[clip.event+1] || cues.some(c=>at<c.at+c.buffer.duration+.06 && end>c.at))continue
    cues.push({...clip,at})
  }
  return {durations,starts,cues:cues.sort((a,b)=>a.at-b.at),duration:starts.at(-1)!}
}

export function trackPosition(track:Track,at:number) {
  const index=Math.min(track.durations.length-1,Math.max(0,track.starts.findIndex((s,i)=>i>0&&s>at)-1))
  if(at>=track.duration)return {index:track.durations.length-1,progress:1}
  return {index,progress:Math.max(0,(at-track.starts[index])/track.durations[index])}
}

/** Strip synthesis padding, retaining 20ms around speech to avoid clipped consonants. */
export function trimSilence(context:AudioContext,buffer:AudioBuffer) {
  const data=buffer.getChannelData(0),padding=Math.ceil(buffer.sampleRate*.02)
  let first=0,last=data.length-1
  while(first<last&&Math.abs(data[first])<.003)first++
  while(last>first&&Math.abs(data[last])<.003)last--
  first=Math.max(0,first-padding);last=Math.min(data.length-1,last+padding)
  const result=context.createBuffer(buffer.numberOfChannels,last-first+1,buffer.sampleRate)
  for(let ch=0;ch<buffer.numberOfChannels;ch++)result.copyToChannel(buffer.getChannelData(ch).slice(first,last+1),ch)
  return result
}

const cache=new Map<string,ArrayBuffer>()
export async function prepareTrack(context:AudioContext,events:Event[],zh:boolean,timed:boolean,signal:AbortSignal,onProgress:(done:number,total:number)=>void) {
  const clips:Clip[]=[]
  const work=events.flatMap((event,i)=>[{event,i,result:false},...(event.action.kind==='shot'?[{event,i,result:true}]:[])])
  // Serial preparation respects the provider's free-tier throughput. No network in playback.
  for(const [index,{event,i,result}] of work.entries()) {
    signal.throwIfAborted()
    const body=JSON.stringify({match_id:event.match_id,events:[event.event_id],revisions:[event.revision],cutoff:event.available_at,language:zh?'zh-Hans':'en',delivery:result?'highlight-result':'highlight-action'})
    let bytes=cache.get(body)
    if(!bytes){
      const response=await fetch('/api/voice/commentary',{method:'POST',headers:{'Content-Type':'application/json'},body,signal:AbortSignal.any([signal,AbortSignal.timeout(20000)])})
      if(!response.ok||!response.headers.get('content-type')?.startsWith('audio/mpeg'))throw Error('Voice unavailable')
      bytes=await response.arrayBuffer()
      if(bytes.byteLength>1_000_000)throw Error('Invalid audio')
      if(cache.size>=120)cache.delete(cache.keys().next().value!)
      cache.set(body,bytes)
    }
    const buffer=trimSilence(context,await context.decodeAudioData(bytes.slice(0)))
    signal.throwIfAborted()
    clips.push({event:i,result,buffer});onProgress(index+1,work.length)
  }
  return planTrack(events,clips,timed)
}

/** Audio and pitch use this exact clock. Scheduling is independent of React renders. */
export class TrackPlayer {
  private nodes:AudioBufferSourceNode[]=[]
  private anchor=0
  constructor(private context:AudioContext,private track:Track,private offset:number,private speed:number){}
  start(){
    this.anchor=this.context.currentTime+.03
    for(const cue of this.track.cues){
      const end=cue.at+cue.buffer.duration
      if(end<=this.offset)continue
      const node=this.context.createBufferSource();node.buffer=cue.buffer;node.playbackRate.value=this.speed
      node.connect(this.context.destination)
      node.start(this.anchor+Math.max(0,cue.at-this.offset)/this.speed,Math.max(0,this.offset-cue.at))
      this.nodes.push(node)
    }
  }
  position(){return Math.min(this.track.duration,this.offset+Math.max(0,this.context.currentTime-this.anchor)*this.speed)}
  stop(){for(const node of this.nodes){node.stop();node.disconnect()}this.nodes=[]}
}
