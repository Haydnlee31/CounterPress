import type { Event } from '../types'
import { clubName, playerName } from '../matchday/identity'
import { recipient } from '../matchday/pitchScene'
import type { BroadcastPlayer } from './broadcast'
import { cue } from './evidence'

export function speechSummary(events:Event[],zh:boolean,detailed:boolean) {
  const shot=[...events].reverse().find(e=>e.action.kind==='shot')
  if(shot)return cue(shot,true,zh,detailed)
  const last=events.at(-1)!
  if(events.length>1 && events.every(e=>e.actor.team_id===last.actor.team_id && e.action.kind==='pass' && e.action.outcome==='completed')) {
    const target=recipient(last),name=target?playerName(target):clubName(last.actor.team_id)
    return zh?`${clubName(last.actor.team_id)}完成${events.length}次传球，球来到${name}脚下。`:`${clubName(last.actor.team_id)} complete ${events.length} passes, finding ${name}.`
  }
  return cue(last,true,zh,detailed)
}

/** One browser utterance at a time. Coalesce arrivals instead of cancelling speech. */
export class CommentarySpeech {
  private pending:Event[]=[]
  private active=false
  private generation=0
  private seen=new Set<string>()
  private cancelAudio:(()=>void)|undefined
  private useDevice=false
  constructor(private synth:SpeechSynthesis,private zh:boolean,private detailed:boolean,private fail:()=>void,private broadcast?:BroadcastPlayer,private fallback?:()=>void){}
  stop(){
    this.generation++;this.cancelAudio?.();this.cancelAudio=undefined;this.pending=[];this.active=false;this.seen.clear();this.synth.cancel()
  }
  offer(event:Event){
    const key=`${event.match_id}:${event.event_id}:${event.revision}`
    if(this.seen.has(key))return
    this.seen.add(key)
    this.pending.push(event)
    // Keep a short summary buffer, retaining the latest shot over routine arrivals.
    if(this.pending.length>4){
      const routine=this.pending.findIndex(e=>e.action.kind!=='shot')
      this.pending.splice(routine<0?0:routine,1)
    }
    this.drain()
  }
  private drain(){
    if(this.active || !this.pending.length)return
    const batch=this.pending;this.pending=[];this.active=true
    const generation=this.generation
    if(this.broadcast && !this.useDevice){
      this.cancelAudio=this.broadcast(batch,this.zh,this.detailed,()=>{
        if(generation!==this.generation)return
        this.cancelAudio=undefined;this.active=false;this.drain()
      },()=>{
        if(generation!==this.generation)return
        this.cancelAudio?.();this.cancelAudio=undefined;this.useDevice=true;this.fallback?.()
        this.speakDevice(batch,generation)
      })
      return
    }
    this.speakDevice(batch,generation)
  }
  private speakDevice(batch:Event[],generation:number){
    if(typeof SpeechSynthesisUtterance==='undefined'){this.stop();this.fail();return}
    const utterance=new SpeechSynthesisUtterance(speechSummary(batch,this.zh,this.detailed))
    utterance.lang=this.zh?'zh-CN':'en-GB'
    const voice=this.synth.getVoices().find(v=>v.lang.toLowerCase().startsWith(this.zh?'zh':'en'))
    if(voice)utterance.voice=voice
    utterance.onend=()=>{
      if(generation!==this.generation)return
      this.active=false;this.drain()
    }
    utterance.onerror=()=>{
      if(generation!==this.generation)return
      this.stop();this.fail()
    }
    try{this.synth.speak(utterance)}catch{this.stop();this.fail()}
  }
}
