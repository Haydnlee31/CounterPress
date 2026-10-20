import {useEffect,useId,useRef,useState} from 'react'
import './mascot.css'

export type FootieMood='greeting'|'idle'|'listening'|'thinking'|'celebrating'|'resting'

/** Decorative companion. Status text and controls remain separate and accessible. */
export function FootieMascot({mood='idle',size=64,trackPointer=false}:{mood?:FootieMood;size?:number;trackPointer?:boolean}){
  const root=useRef<HTMLSpanElement>(null)
  const gradient=useId().replace(/:/g,'')
  const [gaze,setGaze]=useState({x:0,y:0})
  const [settled,setSettled]=useState(false)
  useEffect(()=>{
    setSettled(false)
    if(mood!=='greeting'&&mood!=='celebrating')return
    const timer=window.setTimeout(()=>setSettled(true),2400)
    return()=>window.clearTimeout(timer)
  },[mood])
  const state=settled?'idle':mood
  useEffect(()=>{
    setGaze({x:0,y:0})
    if(!trackPointer||!['idle','greeting','listening'].includes(state)||typeof window.matchMedia!=='function')return
    const reduced=window.matchMedia('(prefers-reduced-motion: reduce)')
    const fine=window.matchMedia('(hover: hover) and (pointer: fine)')
    let frame=0
    const reset=()=>setGaze({x:0,y:0})
    const move=(event:PointerEvent)=>{
      if(reduced.matches||!fine.matches||event.pointerType==='touch')return
      cancelAnimationFrame(frame)
      frame=requestAnimationFrame(()=>{
        const box=root.current?.getBoundingClientRect()
        if(!box)return
        setGaze({x:Math.max(-3,Math.min(3,(event.clientX-box.x-box.width/2)/65)),y:Math.max(-2,Math.min(2,(event.clientY-box.y-box.height/2)/90))})
      })
    }
    window.addEventListener('pointermove',move,{passive:true})
    document.documentElement.addEventListener('pointerleave',reset)
    window.addEventListener('blur',reset)
    reduced.addEventListener('change',reset)
    fine.addEventListener('change',reset)
    return()=>{
      cancelAnimationFrame(frame)
      window.removeEventListener('pointermove',move)
      document.documentElement.removeEventListener('pointerleave',reset)
      window.removeEventListener('blur',reset)
      reduced.removeEventListener('change',reset)
      fine.removeEventListener('change',reset)
    }
  },[trackPointer,state])
  const closed=state==='celebrating'||state==='resting'
  const eyes=state==='thinking'?{x:2,y:-2}:gaze
  return <span ref={root} className={`footie-mascot is-${state}`} style={{width:size,height:size}} aria-hidden="true" data-mood={state}>
    <svg viewBox="0 0 200 190" focusable="false">
      <defs><radialGradient id={gradient} cx="42%" cy="30%" r="75%"><stop offset="55%" className="fm-cream-stop"/><stop offset="100%" className="fm-shade-stop"/></radialGradient></defs>
      <g className="fm-character">
        <g className="fm-feet">
          <g className="fm-foot-left"><path className="fm-green" d="M55 145L79 150L83 168Q80 177 63 177H31Q22 176 25 167Q29 157 48 156Z"/><path className="fm-boot-detail" d="M46 162l10 3m-4-8 10 3M29 172h49"/><path className="fm-green" d="M34 175h7v7h-7zm29 0h7v7h-7z"/></g>
          <g className="fm-foot-right"><path className="fm-green" d="M145 145L121 150L117 168Q120 177 137 177H169Q178 176 175 167Q171 157 152 156Z"/><path className="fm-boot-detail" d="M154 162l-10 3m4-8-10 3M171 172h-49"/><path className="fm-green" d="M159 175h7v7h-7zm-29 0h7v7h-7z"/></g>
        </g>
        <path fill={`url(#${gradient})`} d="M100 16C54 16 20 47 19 92C17 139 48 165 100 165C152 165 183 139 181 92C180 47 146 16 100 16Z"/>
        <path className="fm-green" d="M70 22Q100 11 130 22L138 43Q140 49 134 52L105 65Q100 68 95 65L66 52Q60 49 62 43Z"/>
        <path className="fm-green" d="M24 70Q27 65 32 70L48 82Q52 85 50 92L40 116Q37 122 31 119L20 112Q17 89 24 70Z"/>
        <path className="fm-green" d="M176 70Q173 65 168 70L152 82Q148 85 150 92L160 116Q163 122 169 119L180 112Q183 89 176 70Z"/>
        <path className="fm-arm fm-arm-left" d="M28 105C13 96 1 109 4 124C6 138 19 147 29 140C38 134 40 114 28 105Z"/>
        <path className="fm-arm fm-arm-right" d="M172 105C187 96 199 109 196 124C194 138 181 147 171 140C162 134 160 114 172 105Z"/>
        <g className="fm-face">
          {closed?<g className="fm-expression-lines">{state==='celebrating'?<path d="M68 104q10-17 20 0M112 104q10-17 20 0"/>:<path d="M68 99q10 16 20 0M112 99q10 16 20 0"/>}</g>:<g className="fm-eyes" style={{transform:`translate(${eyes.x}px,${eyes.y}px)`}}>
            <g className="fm-blink"><ellipse className="fm-green" cx="78" cy="101" rx="8.5" ry="13"/><ellipse className="fm-green" cx="122" cy="101" rx="8.5" ry="13"/><ellipse className="fm-highlight" cx="80" cy="96" rx="3" ry="4"/><ellipse className="fm-highlight" cx="124" cy="96" rx="3" ry="4"/></g>
          </g>}
          {state==='thinking'?<ellipse className="fm-green" cx="100" cy="127" rx="3.5" ry="4"/>:state==='celebrating'?<path className="fm-green" d="M90 123Q100 121 110 123C110 139 90 139 90 123Z"/>:<path className="fm-expression-lines" d="M93 125q10 10 18-3"/>}
        </g>
        {state==='thinking'&&<ellipse className="fm-arm" cx="147" cy="129" rx="14" ry="19" transform="rotate(-30 147 129)"/>}
      </g>
    </svg>
  </span>
}
