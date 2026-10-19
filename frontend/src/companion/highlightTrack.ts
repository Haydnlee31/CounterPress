import type {Event} from '../types'

export type Marker={at:number;position:number;text:string}
export type Track={markers:Marker[];duration:number;eventCount:number;audio:HTMLAudioElement;url:string}

/** Interpolate the replay between Azure's actual spoken-phrase bookmarks. */
export function trackPosition(track:Pick<Track,'markers'|'duration'|'eventCount'>,at:number){
  if(at>=track.duration)return {index:track.eventCount-1,progress:1}
  const markers=[{at:0,position:0},...track.markers,{at:track.duration,position:track.eventCount}]
  const right=markers.findIndex(m=>m.at>at),b=markers[right<0?markers.length-1:right],a=markers[Math.max(0,right-1)]
  const position=a.position+(b.position-a.position)*Math.max(0,(at-a.at)/Math.max(.001,b.at-a.at))
  const index=Math.min(track.eventCount-1,Math.floor(position))
  return {index,progress:position-index}
}

/** Seeking is the inverse of the same map, not an independent animation clock. */
export function trackTime(track:Track,index:number,progress:number){
  const position=index+progress
  if(position<=0)return 0
  if(position>=track.eventCount)return track.duration
  const markers=[{at:0,position:0},...track.markers,{at:track.duration,position:track.eventCount}]
  const right=markers.findIndex(m=>m.position>position),b=markers[right],a=markers[right-1]
  return a.at+(b.at-a.at)*(position-a.position)/(b.position-a.position)
}

const cache=new Map<string,{audio:string;markers:Marker[];duration:number;event_count:number}>()
export async function prepareTrack(context:AudioContext,events:Event[],zh:boolean,_timed:boolean,signal:AbortSignal,onProgress:(done:number,total:number)=>void):Promise<Track>{
  const body=JSON.stringify({match_id:events[0].match_id,events:events.map(e=>e.event_id),revisions:events.map(e=>e.revision),language:zh?'zh-Hans':'en'})
  let asset=cache.get(body)
  if(!asset){
    const response=await fetch('/api/voice/highlight',{method:'POST',headers:{'Content-Type':'application/json'},body,signal:AbortSignal.any([signal,AbortSignal.timeout(20000)])})
    if(!response.ok)throw Error('Narration unavailable')
    asset=await response.json()
  }
  if(!asset||asset.event_count!==events.length||!Number.isFinite(asset.duration)||asset.duration<=0||asset.duration>120||!Array.isArray(asset.markers)||asset.markers.length<2||typeof asset.audio!=='string'||asset.audio.length>1_500_000)throw Error('Invalid narration')
  let lastAt=-1,lastPosition=-1
  for(const marker of asset.markers){
    if(!Number.isFinite(marker.at)||!Number.isFinite(marker.position)||marker.at<=lastAt||marker.at>=asset.duration||marker.position<=lastPosition||marker.position>=events.length||typeof marker.text!=='string')throw Error('Invalid timing')
    lastAt=marker.at;lastPosition=marker.position
  }
  const bytes=Uint8Array.from(atob(asset.audio),c=>c.charCodeAt(0))
  const decoded=await context.decodeAudioData(bytes.buffer.slice(0))
  signal.throwIfAborted()
  if(Math.abs(decoded.duration-asset.duration)>.3)throw Error('Audio timing mismatch')
  // Keep the complete synthesized recording, including breaths and sentence cadence.
  const url=URL.createObjectURL(new Blob([bytes],{type:'audio/mpeg'})),audio=new Audio(url)
  audio.preload='auto';audio.preservesPitch=true
  if(cache.size>=16)cache.delete(cache.keys().next().value!)
  cache.set(body,asset);onProgress(1,1)
  return {markers:asset.markers,duration:decoded.duration,eventCount:events.length,audio,url}
}

/** One uncut recording. The browser time-stretches at other speeds without pitch shift. */
export class TrackPlayer {
  private static owners=new WeakMap<HTMLAudioElement,TrackPlayer>()
  constructor(private track:Track,private offset:number,private speed:number){}
  async start(){
    const audio=this.track.audio
    TrackPlayer.owners.set(audio,this)
    audio.currentTime=this.offset;audio.playbackRate=this.speed;audio.preservesPitch=true
    await audio.play()
  }
  position(){return Math.min(this.track.duration,this.track.audio.currentTime)}
  ended(){return this.track.audio.ended}
  stop(){if(TrackPlayer.owners.get(this.track.audio)===this){TrackPlayer.owners.delete(this.track.audio);this.track.audio.pause()}}
}
