import {useEffect,useRef,useState} from 'react'
import {FootieMascot} from '../assistant/FootieMascot'
import './motion.css'

/** Loading feedback only: never delays, retries or starts the underlying request. */
export function FootieLoader({label,compact=false,dark=false,page=false,language='en'}:{label:string;compact?:boolean;dark?:boolean;page?:boolean;language?:string}){
  const root=useRef<HTMLDivElement>(null)
  const [visible,setVisible]=useState(true)
  const [foreground,setForeground]=useState(()=>!document.hidden)
  useEffect(()=>{
    const visibility=()=>setForeground(!document.hidden)
    document.addEventListener('visibilitychange',visibility)
    const observer=typeof IntersectionObserver==='undefined'?null:new IntersectionObserver(([entry])=>setVisible(entry.isIntersecting))
    if(root.current)observer?.observe(root.current)
    return()=>{observer?.disconnect();document.removeEventListener('visibilitychange',visibility)}
  },[])
  return <div ref={root} className={`footie-loading${compact?' is-compact':''}${dark?' is-dark':''}${page?' is-page':''}`} data-paused={!visible||!foreground} role="status" aria-live="polite" aria-atomic="true">
    <FootieMascot mood="juggling" size={compact?56:page?144:112}/>
    <div><span className="footie-loading-title" aria-hidden="true">{language==='zh-Hans'?'Footie 正在热身':'Footie’s warming up'}</span><p>{label}</p></div>
  </div>
}
