import {useEffect,useId,useState} from 'react'
import {pitchPortraits} from './portraits'
import './pitchIdentity.css'
const key='footie.pitch.faces.v1',eventName='footie:pitch-faces'
export function usePitchFaces(){
  const read=()=>{try{return localStorage.getItem(key)!=='off'}catch{return true}}
  const [faces,setFaces]=useState(read)
  useEffect(()=>{const sync=()=>setFaces(read());window.addEventListener(eventName,sync);window.addEventListener('storage',sync);return()=>{window.removeEventListener(eventName,sync);window.removeEventListener('storage',sync)}},[])
  const update=(value:boolean)=>{setFaces(value);try{localStorage.setItem(key,value?'on':'off')}catch{/* Keep the choice for this visit. */}window.dispatchEvent(new Event(eventName))}
  return [faces,update] as const
}
export function PitchFaceToggle({faces,change}:{faces:boolean;change:(value:boolean)=>void}){
  return <details className="pitch-display-settings"><summary>Display <span aria-hidden="true">⌄</span></summary><label className="pitch-display">Players <select aria-label="Pitch player display" value={faces?'faces':'initials'} onChange={e=>change(e.target.value==='faces')}><option value="faces">Faces</option><option value="initials">Initials</option></select></label></details>
}
/** A close head crop, with stable identity and initials if an image is missing. */
export function PitchIdentity({playerId,name,color,r=2.7,faces=true}:{playerId:string;name:string;color:string;r?:number;faces?:boolean}){
  const clip=useId().replaceAll(':',''),[failed,setFailed]=useState(false)
  const src=pitchPortraits[playerId],show=faces&&src&&!failed
  useEffect(()=>setFailed(false),[src])
  return <g className="pitch-identity" pointerEvents="none">
    <circle r={r} fill={color} stroke="#0e3028" strokeWidth=".35"/>
    {show?<><defs><clipPath id={clip}><circle r={r-.25}/></clipPath></defs><image aria-hidden="true" href={src} x={-r*1.8} y={-r*.92} width={r*3.6} height={r*3.6} clipPath={`url(#${clip})`} onError={()=>setFailed(true)}/><circle r={r} fill="none" stroke={color} strokeWidth=".55"/></>:<text className="player-initials" y=".7" textAnchor="middle" fontSize={r*.72} fontWeight="800" fill="#153e35">{name.split(' ').map(n=>n[0]).slice(0,2).join('')}</text>}
  </g>
}
