import {useEffect,useRef,useState} from 'react'
import type {Event} from '../types'
import {prepareTrack,type Track} from './highlightTrack'

export function useHighlightTrack(events:Event[],language:string,timed:boolean,enabled:boolean,onReset:()=>void){
  const [available,setAvailable]=useState(false),[listen,setListen]=useState(false)
  const [status,setStatus]=useState<'idle'|'loading'|'ready'|'error'>('idle')
  const [progress,setProgress]=useState(''),[loaded,setLoaded]=useState<{key:string;track:Track}|null>(null)
  const context=useRef<AudioContext|null>(null),reset=useRef(onReset);reset.current=onReset
  const key=JSON.stringify([events.map(e=>[e.match_id,e.event_id,e.revision]),language,timed])
  const track=loaded?.key===key?loaded.track:null
  useEffect(()=>{
    if(!enabled||typeof AudioContext==='undefined')return
    const abort=new AbortController()
    fetch('/api/voice/config',{signal:abort.signal}).then(r=>r.ok?r.json():null).then(c=>setAvailable(c?.azure===true)).catch(()=>{})
    return()=>abort.abort()
  },[enabled])
  useEffect(()=>{
    if(!listen||!enabled)return
    reset.current()
    if(track){setStatus('ready');return}
    const abort=new AbortController();setStatus('loading');setProgress('')
    if(!context.current)context.current=new AudioContext()
    prepareTrack(context.current,events,language==='zh-Hans',timed,abort.signal,(n,total)=>setProgress(`${n}/${total}`))
      .then(track=>{if(!abort.signal.aborted){setLoaded({key,track});setStatus('ready')}})
      .catch(()=>{if(!abort.signal.aborted){setStatus('error');setListen(false)}})
    return()=>abort.abort()
  },[listen,key,enabled])
  useEffect(()=>()=>{void context.current?.close()},[])
  useEffect(()=>()=>{if(loaded){loaded.track.audio.pause();URL.revokeObjectURL(loaded.track.url)}},[loaded])
  const resume=()=>context.current?.resume()
  const toggle=()=>{
    reset.current()
    if(!listen){
      if(!context.current)context.current=new AudioContext()
      void context.current.resume().catch(()=>{setStatus('error');setListen(false)})
    }
    setListen(v=>!v)
  }
  return {available,listen,status,progress,track:listen?track:null,context,resume,toggle,
    preparing:listen&&(!track||status==='loading')}
}
